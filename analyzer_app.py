# app.py  (OpenAI SDK v1+ compatible)
import os
import tempfile
import shutil
import json
import re
import ast
import time
from pathlib import Path
from typing import List, Dict

from flask import Flask, request, render_template, jsonify
import requests
import git
import numpy as np
from dotenv import load_dotenv

# NEW OpenAI client
from openai import OpenAI

load_dotenv()

# -------------------------
# ENV CONFIG
# -------------------------
GIT_ORG = os.getenv("GIT_ORG", "simpsonorg")
GITHUB_API = f"https://api.github.com/orgs/{GIT_ORG}/repos"
REPO_CLONE_LIMIT = int(os.getenv("REPO_CLONE_LIMIT", "5"))
GITHUB_TOKEN = "github_pat"
OPENAI_API_KEY = "sk-proj-"

# MODELS
EMBED_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__, template_folder="templates")


# -------------------------
# LOG HELPER
# -------------------------
def log(logs, msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    logs.append(line)
    print(line)


# -------------------------
# ROUTES
# -------------------------
@app.before_request
def f_log():
    print(f"[REQ] {request.method} {request.path}", flush=True)


@app.route("/keycheck")
def keycheck():
    return jsonify({"key_present": bool(OPENAI_API_KEY)})


@app.route("/")
def index():
    return render_template("analyzer.html")


# -------------------------
# GitHub repo fetching
# -------------------------
def list_repos(logs):
    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    log(logs, "Fetching repos from GitHub...")
    resp = requests.get(GITHUB_API, headers=headers)
    if resp.status_code != 200:
        log(logs, f"GitHub failed: {resp.text}")
        return []

    repos = resp.json()[:REPO_CLONE_LIMIT]
    log(logs, f"Found {len(repos)} repos (limit {REPO_CLONE_LIMIT})")
    return repos


def clone_repo(tmp, logs, name, url):
    path = os.path.join(tmp, name)
    log(logs, f"Cloning {name}...")
    try:
        git.Repo.clone_from(url, path)
        log(logs, f"Cloned {name}")
        return path
    except Exception as e:
        log(logs, f"Clone failed: {e}")
        return None


# -------------------------
# File scanning / indexing
# -------------------------
def get_files(path):
    exts = {".py", ".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".cfg"}
    files = []
    for p in Path(path).rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(str(p))
    return files


def summarize_files(files):
    out = []
    for f in files:
        try:
            txt = Path(f).read_text(errors="ignore")
            summary = f"FILE: {Path(f).name}\n" + "\n".join(txt.splitlines()[:30])
            out.append((f, summary))
        except:
            continue
    return out


# -------------------------
# Embeddings (NEW API)
# -------------------------
def embed(texts, logs):
    log(logs, f"Embedding {len(texts)} items...")
    try:
        resp = client.embeddings.create(
            model=EMBED_MODEL,
            input=texts
        )
        return np.array([d.embedding for d in resp.data])
    except Exception as e:
        log(logs, f"Embedding error: {e}")
        return None


def sim(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0: return 0
    return float(np.dot(a, b) / (na * nb))


# -------------------------
# LLM PR generation (NEW API)
# -------------------------
def generate_pr(requirement, matches, logs):
    log(logs, "Generating PR text via OpenAI...")

    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": "You are a senior reviewer. Generate a PR description."},
                {
                    "role": "user",
                    "content": f"Requirement:\n{requirement}\n\nMatches:\n{json.dumps(matches, indent=2)}"
                }
            ]
        )
        md = resp.choices[0].message.content
        return f"<pre>{md}</pre>"
    except Exception as e:
        log(logs, f"PR generation failed: {e}")
        return "<pre>PR generation failed.</pre>"


# -------------------------
# /analyze
# -------------------------
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    req = data.get("requirement", "").strip()
    logs = []
    if not req:
        return jsonify({"error": "Missing requirement"}), 400

    tmp = tempfile.mkdtemp(prefix="impact_")
    log(logs, "Workspace created")

    all_matches = []

    try:
        repos = list_repos(logs)

        for r in repos:
            name = r["name"]
            url = r["clone_url"]

            path = clone_repo(tmp, logs, name, url)
            if not path:
                continue

            files = get_files(path)
            log(logs, f"{name}: {len(files)} files")

            summaries = summarize_files(files)

            # Use embeddings if API key works
            if OPENAI_API_KEY:
                file_texts = [s for _, s in summaries]
                F = embed(file_texts, logs)
                q = embed([req], logs)

                if F is None or q is None:
                    log(logs, f"Embedding fallback for {name}")
                    continue

                q = q[0]

                scored = []
                for i, (fp, summary) in enumerate(summaries):
                    scored.append({
                        "repo": name,
                        "file": str(Path(fp).relative_to(path)),
                        "score": sim(q, F[i]),
                        "excerpt": summary
                    })

                top = sorted(scored, key=lambda x: x["score"], reverse=True)[:5]
                all_matches.extend(top)

            else:
                # Fallback keyword matching
                tokens = set(re.findall(r"\w{4,}", req.lower()))
                scored = []
                for fp, summary in summaries:
                    t2 = set(re.findall(r"\w{4,}", summary.lower()))
                    score = len(tokens & t2)
                    scored.append({
                        "repo": name,
                        "file": str(Path(fp).relative_to(path)),
                        "score": score,
                        "excerpt": summary
                    })
                all_matches.extend(sorted(scored, key=lambda x: x["score"], reverse=True)[:5])

        # Global top matches
        all_matches = sorted(all_matches, key=lambda x: x["score"], reverse=True)[:20]

        # PR
        if OPENAI_API_KEY:
            pr_html = generate_pr(req, all_matches, logs)
        else:
            pr_html = "<pre>OpenAI key missing → fallback mode.</pre>"

        return jsonify({
            "matches": [
                {"repo": m["repo"], "file": m["file"], "score": round(m["score"], 3)}
                for m in all_matches
            ],
            "pr_html": pr_html,
            "logs": logs
        })

    finally:
        try:
            shutil.rmtree(tmp)
            log(logs, "Workspace cleaned")
        except:
            pass


if __name__ == "__main__":
    print("Starting Impact Analyzer (OpenAI v1.x compatible)")
    print("GITHUB_TOKEN:", bool(GITHUB_TOKEN))
    print("OPENAI_API_KEY:", bool(OPENAI_API_KEY))
    app.run(debug=True)
