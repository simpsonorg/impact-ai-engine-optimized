from flask import Flask, request, render_template_string
import os

app = Flask(__name__)

# --------------------------------------------------------------------------
# CONFIG – CHANGE THIS TO YOUR REPO ROOT
# --------------------------------------------------------------------------
REPO_ROOT = r"C:\data\finalcodepls\git_repo"

# --------------------------------------------------------------------------
# LOAD REPO STRUCTURE (SKIPS .git / .github / venv / pycache)
# --------------------------------------------------------------------------
def load_repo_structure():
    repo_map = {}

    SKIP_DIRS = {".git", ".github", "__pycache__", "venv", "env", ".idea"}

    for repo in os.listdir(REPO_ROOT):
        repo_path = os.path.join(REPO_ROOT, repo)

        if os.path.isdir(repo_path):
            file_list = []

            # Walk with filters
            for root, dirs, files in os.walk(repo_path):
                # filter folders before descending
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

                for f in files:
                    # Skip hidden files
                    if f.startswith("."):
                        continue

                    full_path = os.path.join(root, f)
                    relative = full_path.replace(REPO_ROOT + "/", "")
                    file_list.append(relative)

            repo_map[repo] = file_list

    return repo_map


REPO_FILES = load_repo_structure()

# --------------------------------------------------------------------------
# KEYWORD MATCHING LOGIC
# --------------------------------------------------------------------------
CHANGE_HINTS = {
    "api": ["controller", "handler", "route", "api"],
    "database": ["repository", "dao", "db", "entity", "model"],
    "customer": ["customer", "account", "demographic"],
    "load": ["loader", "load", "processor", "service"],
    "crud": ["create", "update", "delete"],
}


def infer_changed_files(story, service_name):
    story = story.lower()
    candidates = []

    service_files = REPO_FILES.get(service_name, [])

    # Match keywords
    for keyword, hints in CHANGE_HINTS.items():
        if keyword in story:
            for file in service_files:
                f = file.lower()
                if any(h in f for h in hints):
                    candidates.append(file)

    # Fallback heuristic
    if not candidates:
        for file in service_files:
            if "src" in file.lower():
                candidates.append(file)

    return sorted(set(candidates))


# --------------------------------------------------------------------------
# FIND IMPACTED REPOSITORIES
# --------------------------------------------------------------------------
def find_impacted_repos(changed_files):
    impacted = {}

    for repo, files in REPO_FILES.items():
        for changed in changed_files:
            base = os.path.basename(changed)
            if base == "":
                continue
            for f in files:
                if base in f:
                    impacted.setdefault(repo, []).append(f)

    return impacted


# --------------------------------------------------------------------------
# HTML TEMPLATE FOR RESULT
# --------------------------------------------------------------------------
HTML_RESULT = """
<!DOCTYPE html>
<html>
<head>
    <title>Impact Result</title>
    <style>
        body { font-family: Arial; background:#f2f2f2; }
        .container { width: 700px; margin:auto; background:white; padding:20px; margin-top:30px; border-radius:10px; }
        li { margin-bottom:4px; }
    </style>
</head>
<body>
<div class="container">

<h2>Impact Analysis Result</h2>

<h3>Chosen Microservice: {{ service }}</h3>
<h4>Story:</h4>
<p>{{ story }}</p>

<h3>Predicted Changed Files</h3>
<ul>
{% for f in changed %}
    <li>{{ f }}</li>
{% endfor %}
</ul>

<h3>Impacted Repositories</h3>
{% if impacted %}
    {% for repo, files in impacted.items() %}
        <h4>{{ repo }}</h4>
        <ul>
        {% for f in files %}
            <li>{{ f }}</li>
        {% endfor %}
        </ul>
    {% endfor %}
{% else %}
<p>No impacted repos found.</p>
{% endif %}

</div>
</body>
</html>
<style>
    body {
        font-family: "Segoe UI", Roboto, Arial, sans-serif;
        background: linear-gradient(135deg, #eef2f3, #dfe9f3);
        margin: 0;
        padding: 40px 0;
        color: #333;
    }

    .container {
        width: 700px;
        margin: auto;
        background: white;
        padding: 30px;
        border-radius: 14px;
        box-shadow: 0 8px 28px rgba(0,0,0,0.12);
        animation: fadein 0.4s ease-in-out;
    }

    h2 {
        text-align: center;
        font-size: 26px;
        margin-bottom: 20px;
        font-weight: 600;
        color: #222;
    }

    label {
        font-weight: 600;
        margin-bottom: 8px;
        display: block;
        font-size: 14px;
    }

    textarea {
        width: 100%;
        height: 150px;
        border-radius: 8px;
        border: 1px solid #bbb;
        padding: 12px;
        resize: vertical;
        font-size: 14px;
        outline: none;
        transition: 0.2s;
    }

    textarea:focus {
        border-color: #5a8dee;
        box-shadow: 0 0 6px rgba(90,141,238,0.4);
    }

    select, button {
        width: 100%;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 20px;
        font-size: 15px;
        border: 1px solid #bbb;
        outline: none;
        transition: 0.2s;
    }

    select:focus {
        border-color: #5a8dee;
        box-shadow: 0 0 6px rgba(90,141,238,0.4);
    }

    button {
        background: #5a8dee;
        color: white;
        font-weight: 600;
        border: none;
        cursor: pointer;
        letter-spacing: 0.5px;
        transition: 0.25s ease;
    }

    button:hover {
        background: #4479e0;
        box-shadow: 0 6px 16px rgba(68,121,224,0.4);
        transform: translateY(-1px);
    }

    ul {
        background: #f8f9fb;
        padding: 16px 20px;
        border-radius: 10px;
        border: 1px solid #ddd;
        list-style-type: square;
    }

    li {
        padding: 4px 0;
        font-size: 14px;
        color: #444;
    }

    h3 {
        margin-top: 30px;
        font-size: 20px;
        border-left: 5px solid #5a8dee;
        padding-left: 10px;
        color: #222;
    }

    h4 {
        margin-top: 15px;
        color: #333;
    }

    @keyframes fadein {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
</style>

"""


# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Impact Analyzer</title>
    <style>
        body { font-family: Arial; background:#f6f6f6; }
        .container { width:600px; margin:auto; margin-top:40px; background:white; padding:25px; border-radius:10px; }
        textarea { width:100%; height:150px; margin-bottom:20px; }
        select, button { width:100%; padding:10px; margin-bottom:20px; }
    </style>
</head>
<body>

<div class="container">
<h2>Cross-Repo Story Impact Analyzer</h2>

<form action="/analyze" method="post">
    <label>Enter Story / Requirement:</label>
    <textarea name="story" required></textarea>

    <label>Select Microservice:</label>
    <select name="service" required>
        <option>apigee-mock-gateway</option>
        <option>crud-ms-account-load-db</option>
        <option>crud-ms-account-load-fdr</option>
        <option>domain-ms-account-load</option>
        <option>fdr-vendor-mock</option>
        <option>impact-ai-engine</option>
        <option>impact-ai-engine-optimized</option>
        <option>impact-listener</option>
        <option>oraas-db-mock</option>
        <option>psg-mock-router</option>
        <option>ui-account-load</option>
    </select>

    <button type="submit">Analyze Impact</button>
</form>
</div>

</body>
</html>
"""


@app.route("/analyze", methods=["POST"])
def analyze():
    story = request.form["story"]
    service = request.form["service"]

    changed_files = infer_changed_files(story, service)
    impacted_repos = find_impacted_repos(changed_files)

    return render_template_string(
        HTML_RESULT,
        story=story,
        service=service,
        changed=changed_files,
        impacted=impacted_repos
    )


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
