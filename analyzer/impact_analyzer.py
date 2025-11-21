# analyzer/impact_analyzer.py
import os
import json
import html

# Try to create an OpenAI client (new API wrapper). If missing, fall back to deterministic Markdown.
try:
    from openai import OpenAI
    _openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _openai = None


def md_escape(text: str) -> str:
    """Escape pipe and other markdown-control characters for table cells."""
    if text is None:
        return ""
    text = str(text).replace("\r", "")
    text = text.replace("|", "\\|")
    text = text.replace("`", "\\`")
    text = text.replace("\n", "<br>")
    return text


def severity_from_count(n: int) -> str:
    if n >= 6:
        return "HIGH"
    if n >= 3:
        return "MEDIUM"
    return "LOW"


def compact_snippets_text(snippets, limit=6):
    parts = []
    for s in (snippets or [])[:limit]:
        svc = s.get("service", "unknown")
        file = s.get("file", "unknown")
        snippet = s.get("snippet", "")
        excerpt = snippet.strip().splitlines()[:6]
        text = "\\n".join(excerpt)
        parts.append(f"[{svc}] {file}: {text}")
    return "\n\n".join(parts)


# -------------------------------------------------------------------
# PREMIUM MARKDOWN-ONLY SAFE UI — GitHub Compatible
# -------------------------------------------------------------------
def build_llm_prompt_markdown(pr_title, changed_files, impacted_services, graph_json, snippets):
    snippet_block = compact_snippets_text(snippets, limit=6) if snippets else "No code snippets available."

    return f"""
You are an expert software architect. Generate a **Premium GitHub-Compatible PR Impact Dashboard**  
using **Markdown ONLY** (NO HTML).  

It must render perfectly inside GitHub PR comments.

======================================================================
# 🚀 PR Impact Dashboard
Write a short 1-sentence overview for reviewers.

======================================================================
## 🔥 Top-Level Summary

Render this *exact* Markdown table:

| Severity | Impacted Services | Changed Files | Recommendation |
|---------|-------------------|---------------|----------------|

Severity rules:  
- 🟢 LOW  
- 🟡 MEDIUM  
- 🔴 HIGH  

======================================================================
## 📝 Summary (2–4 sentences)
Explain:
- What this PR changes  
- How these files affect system behavior  
- Upstream/downstream implications  

======================================================================
## 🧩 Per-Service Impact Breakdown

For EACH impacted service, produce a section like:

### 🧱 **<service-name>**

> One-sentence summary of why this service is impacted.

**Files to Review**
- file1  
- file2  

**Recommended Actions**
- short actionable bullet 1  
- short actionable bullet 2  

**Risk:** LOW / MEDIUM / HIGH  
**Suggested Reviewers:** GitHub handles or "TBD"

Use clean bullets, not long paragraphs.

======================================================================
## 🧪 Recommended Test Coverage
Provide 4–7 meaningful tests:
- End-to-end  
- Contract validation  
- Schema validation  
- Negative tests  
- Performance  

======================================================================
## 🧠 Final Reviewer Guidance
Write 2–4 polished lines:
- Key concerns  
- Integration risks  
- Merge safety  
- Rollback considerations  

======================================================================

📌 **DO NOT PRINT THE CONTEXT BELOW (for reasoning only)**

PR Title:
{pr_title}

Changed Files:
{json.dumps(changed_files, indent=2)}

Impacted Services:
{json.dumps(impacted_services, indent=2)}

Graph JSON:
{json.dumps(graph_json, indent=2)}

Relevant Snippets:
{snippet_block}

RULES:
- OUTPUT MUST BE PURE MARKDOWN (NO HTML)
- NO code fences
- NO raw JSON
- NO extra commentary
- NO context printing
"""


def analyze(pr_title, changed_files, impacted_services, graph_json, snippets):
    changed_files = changed_files or []
    impacted_services = impacted_services or []
    severity = severity_from_count(len(impacted_services))

    if _openai is not None:
        prompt = build_llm_prompt_markdown(pr_title, changed_files, impacted_services, graph_json, snippets)
        try:
            resp = _openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1600,
                temperature=0.1,
            )
            content = resp.choices[0].message.content
            if not content.strip():
                raise ValueError("LLM returned empty content")
            return content
        except Exception as e:
            fallback_header = f"> **⚠️ LLM failed:** {str(e)}\n\n"
            deterministic = _build_deterministic_markdown(
                pr_title, changed_files, impacted_services, graph_json, snippets, severity
            )
            return fallback_header + deterministic

    return _build_deterministic_markdown(
        pr_title, changed_files, impacted_services, graph_json, snippets, severity
    )


def _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity):

    impacted_display = ", ".join(impacted_services) if impacted_services else "None"
    top_table = (
        "| Severity | Impacted Services | Changed Files Count | Recommendation |\n"
        "|----------|-------------------|---------------------|----------------|\n"
        f"| **{md_escape(severity)}** | {md_escape(impacted_display)} | {len(changed_files)} | "
        f"{md_escape('Run integration tests across impacted services; coordinate schema changes.')} |\n"
    )

    summary_lines = [
        f"**PR Title:** {md_escape(pr_title)}",
        f"Changed {len(changed_files)} file(s): {md_escape(', '.join(changed_files))}." if changed_files else "No changed files detected.",
        f"Estimated severity: **{md_escape(severity)}**."
    ]
    summary = "\n\n".join(summary_lines)

    per_service_sections = []
    for svc in impacted_services:
        files_changed = [
            cf for cf in changed_files
            if cf.replace("\\", "/").startswith(svc + "/") or f"/{svc}/" in cf.replace("\\", "/")
        ]
        files_cell = ", ".join(files_changed) if files_changed else "N/A"

        if "db" in svc.lower() or "crud" in svc.lower():
            impact_level = "Medium"
            reason = "Data boundary modification may break consumers."
            suggested_tests = "DB contract tests, integration tests"
        elif "ui" in svc.lower() or "frontend" in svc.lower():
            impact_level = "Low"
            reason = "UI adaptation may be required."
            suggested_tests = "UI smoke/rendering tests"
        else:
            impact_level = "High"
            reason = "Core logic changes may cascade downstream."
            suggested_tests = "End-to-end & contract tests"

        recommended_actions = "Review API contract; notify downstream owners"
        potential_risks = "Incorrect data, latency, errors"
        suggested_reviewers = "TBD"

        row =
