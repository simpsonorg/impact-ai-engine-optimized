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
    # Basic escaping: pipe and backslash; preserve newlines but replace CR
    text = str(text).replace("\r", "")
    text = text.replace("|", "\\|")
    text = text.replace("`", "\\`")
    # Keep newlines but ensure cell rendering: GitHub supports newlines in table cells if wrapped in <br>
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
        excerpt = snippet.strip().splitlines()
        excerpt = excerpt[:6]  # first few lines
        text = "\\n".join(excerpt)
        parts.append(f"[{svc}] {file}: {text}")
    return "\n\n".join(parts)


# -------------------------------------------------------------------------
# ONLY THIS FUNCTION IS CHANGED → UI UPGRADE ONLY
# -------------------------------------------------------------------------
def build_llm_prompt_markdown(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Premium Elegant UI Prompt — NO functional changes.
    """
    snippet_block = compact_snippets_text(snippets, limit=6) if snippets else "No code snippets available."

    return f"""
You are a senior software architect. Produce a **visually stunning, premium GitHub PR Impact Dashboard** using **PURE MARKDOWN ONLY** (no HTML).

Your Markdown must be clean, elegant, readable, and structured like a polished product UI.
Use emojis, spacing, hierarchy, clarity, and professional tone.
DO NOT output JSON, HTML, code blocks, or the context section.

==============================================================================
# 🚀 **PR Impact Dashboard**
A premium visual overview for reviewers.

==============================================================================
## 🔥 **Top-Level Summary**
Render a clean table:

| Severity | Impacted Services | Changed Files Count | Recommendation |
|:-------:|-------------------|:-------------------:|----------------|

- Severity should use emoji badges:  
  🟢 LOW 🟡 MEDIUM 🔴 HIGH  

==============================================================================
## 📝 **Executive Summary**
Write 3–5 refined sentences describing:
- What this PR changes  
- How the modified files affect system behavior  
- Upstream/downstream impact  
- Any key risks  

==============================================================================
## 🧩 **Per-Service Impact Analysis**
For **each impacted service**, generate this block:

### 🧱 **<service-name>**
> One elegant sentence explaining why this service is impacted.

**📄 Files to Review:**  
- List of changed files relevant to this service

**🛠 Recommended Actions:**  
- 2–4 bullet points  
- Keep concise and technical

**⚠️ Risk Level:** LOW / MEDIUM / HIGH  
**👥 Suggested Reviewers:** GitHub handles or "TBD"

==============================================================================
## 🧪 **Recommended Test Coverage**
Provide 4–7 meaningful test recommendations:
- End-to-end tests  
- Contract validation  
- Schema checks  
- Negative/error paths  
- Performance considerations  

==============================================================================
## 🧠 **Final Reviewer Guidance**
Provide 3–5 polished sentences summarizing:
- Critical items to verify  
- Integration concerns  
- Merge safety  
- Rollback readiness  

==============================================================================
### 🔍 CONTEXT (DO NOT OUTPUT THIS)

PR Title:
{pr_title}

Changed Files:
{json.dumps(changed_files, indent=2)}

Impacted Services:
{json.dumps(impacted_services, indent=2)}

Service Dependency Graph:
{json.dumps(graph_json, indent=2)}

Code Snippets:
{snippet_block}

RULES:
- MUST output only Markdown.
- DO NOT output this context.
- No HTML, no code blocks.
"""


# -------------------------------------------------------------------------
# NO CHANGES BELOW THIS LINE
# -------------------------------------------------------------------------

def analyze(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Produce a Markdown report. If OpenAI available, request Markdown via prompt;
    otherwise construct a deterministic Markdown summary from graph + changed files.
    """
    # Basic inputs normalization
    changed_files = changed_files or []
    impacted_services = impacted_services or []

    # Severity estimate
    severity = severity_from_count(len(impacted_services))

    # If OpenAI is available, ask it to produce pure Markdown (RAG-enhanced prompt)
    if _openai is not None:
        prompt = build_llm_prompt_markdown(pr_title, changed_files, impacted_services, graph_json, snippets)
        try:
            resp = _openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1400,
                temperature=0.12,
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

    # No OpenAI configured: deterministic markdown
    return _build_deterministic_markdown(
        pr_title, changed_files, impacted_services, graph_json, snippets, severity
    )


def _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity):
    # Top summary table
    impacted_display = ", ".join(impacted_services) if impacted_services else "None"
    top_table = (
        "| Severity | Impacted Services | Changed Files Count | Recommendation |\n"
        "|---:|---|---:|---|\n"
        f"| **{md_escape(severity)}** | {md_escape(impacted_display)} | {len(changed_files)} | "
        f"{md_escape('Run integration tests across impacted services; coordinate schema changes.')} |\n"
    )

    # Summary paragraph
    summary_lines = [
        f"**PR Title:** {md_escape(pr_title)}",
        f"Changed {len(changed_files)} file(s): {md_escape(', '.join(changed_files))}."
        if changed_files else "No changed files found in CHANGED_FILES env variable.",
        f"Estimated severity based on impacted services: **{md_escape(severity)}**."
    ]
    summary = "\n\n".join(summary_lines)

    # Per-service tables
    per_service_sections = []
    for svc in impacted_services:
        files_changed = []
        for cf in changed_files:
            if cf.replace("\\", "/").startswith(svc + "/") or f"/{svc}/" in cf.replace("\\", "/"):
                files_changed.append(cf)
        files_cell = md_escape(", ".join(files_changed)) if files_changed else "N/A"

        if "db" in svc.lower() or "crud" in svc.lower():
            impact_level = "Medium"
            reason = "Data read/write boundary; schema changes may break consumers."
            suggested_tests = "DB contract tests, integration account-load flow"
        elif "ui" in svc.lower() or "frontend" in svc.lower():
            impact_level = "Low"
            reason = "UI may need adaptation for new fields or formats."
            suggested_tests = "UI smoke tests, rendering checks"
        else:
            impact_level = "High"
            reason = "Core domain changes may cascade to downstream services."
            suggested_tests = "End-to-end account-load flow, contract tests"

        recommended_actions = "Review API contracts; add integration tests; notify downstream owners"
        potential_risks = "Incorrect data, latency issues, service errors"
        suggested_reviewers = "TBD"

        svc_row = (
            "| " + md_escape(svc) + " | "
            + md_escape(impact_level) + " | "
            + md_escape(reason) + " | "
            + files_cell + " | "
            + md_escape(suggested_tests) + " | "
            + md_escape(recommended_actions) + " | "
            + md_escape(potential_risks) + " | "
            + md_escape(suggested_reviewers) + " |\n"
        )

        header = (
            "| Service | Impact Level | Reason | Files Changed | Suggested Tests | Recommended Actions | Potential Risks | Suggested Reviewers |\n"
            "|---|---|---|---|---|---|---|---|\n"
        )

        per_service_sections.append(f"### {md_escape(svc)}\n\n{header}{svc_row}")

    per_service_md = "\n\n".join(per_service_sections) if per_service_sections else "_No impacted services detected._"

    # Recommended tests list
    tests_md = "\n".join([
        "- End-to-end account-load integration test",
        "- Backward compatibility contract tests",
        "- Schema validation for new/changed payload fields",
        "- Performance smoke test",
        "- Audit logs/observability checks"
    ])

    # Final guidance
    final_guidance = (
        "Before merging, ensure integration tests pass between affected services, "
        "notify downstream owners, and prepare a rollback plan."
    )

    return "\n".join([
        "# PR Impact Summary",
        "",
        top_table,
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Per-Service Impact",
        "",
        per_service_md,
        "",
        "## Recommended Tests",
        "",
        tests_md,
        "",
        "## Final Reviewer Guidance",
        "",
        final_guidance,
        ""
    ])
