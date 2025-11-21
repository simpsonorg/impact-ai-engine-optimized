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
        excerpt = snippet.strip().splitlines()
        excerpt = excerpt[:6]
        text = "\\n".join(excerpt)
        parts.append(f"[{svc}] {file}: {text}")
    return "\n\n".join(parts)


# 🔥🔥🔥 REPLACED FUNCTION → Premium Elegant UI Prompt
def build_llm_prompt_markdown(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Premium Elegant UI (Markdown-only) for GitHub PR Impact Dashboards.
    Zero HTML. Zero CSS. Pure visually appealing GitHub Markdown.
    """

    snippet_block = compact_snippets_text(snippets, limit=6) if snippets else "No code snippets available."

    return f"""
You are a senior principal software architect. Produce a **Premium Elegant GitHub PR Impact Dashboard** using **PURE MARKDOWN ONLY**.

The output must be visually stunning, incredibly readable, and formatted like a polished product UI.  
Use emojis, structured hierarchy, dividers, callouts, bullet sections, spacing and clarity.  
No HTML, no JSON, no code blocks — only Markdown.

==============================================================================
# 🚀 **PR Impact Dashboard**
A rich, premium-quality visual summary for PR reviewers.

==============================================================================
## 🔥 **Top-Level Summary**
Create a clean, visually appealing Markdown table:

| Severity | Impacted Services | Changed Files | Recommendation |
|:-------:|-------------------|:-------------:|----------------|

- Use emoji severity badges: 🟢 LOW · 🟡 MEDIUM · 🔴 HIGH  
- Keep text clean and concise  
- Services = comma-separated  
- Recommendation = short actionable insight

==============================================================================
## 📝 **Executive Summary**
Write 3–5 polished sentences explaining:
- What this PR is doing  
- How the changed files affect the system  
- High-level upstream/downstream impact  
- Key risks  
Make this read like a reviewer briefing note.

==============================================================================
## 🧩 **Per-Service Impact Analysis**
For **each impacted service**, generate a premium, well-structured section:

### 🧱 **<service-name>**
> One elegant sentence summarizing why this service is impacted.

**📄 Files to Review:**  
- Actual changed files related to this service

**🛠 Recommended Actions:**  
- Bullet list of what devs must validate or fix

**⚠️ Risk Level:** LOW / MEDIUM / HIGH  
**👥 Suggested Reviewers:** Github handles or "TBD"

Keep each block short, crisp, and visually appealing.

==============================================================================
## 🧪 **Recommended Test Coverage**
Provide **4–7 meaningful test recommendations**, such as:
- Full end-to-end flow tests  
- Contract/backward-compatibility tests  
- Schema validation  
- Negative/error scenario tests  
- Performance/scalability checks  

==============================================================================
## 🧠 **Final Reviewer Guidance**
A 3–5 sentence professional summary:
- Key items to double-check  
- Integration risks  
- Signals indicating safe merge  
- Deployment/rollback considerations  

==============================================================================
### 🔍 **CONTEXT (must NOT appear in output)**

PR Title:
{pr_title}

Changed Files:
{json.dumps(changed_files, indent=2)}

Impacted Services:
{json.dumps(impacted_services, indent=2)}

Service Graph:
{json.dumps(graph_json, indent=2)}

Relevant Snippets:
{snippet_block}

RULES:
- DO NOT output the context section.
- DO NOT include HTML or code fences.
- MUST be pure Markdown.
- Be elegant, structured, readable, and visually rich.
"""


def analyze(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Produce a Markdown report. If OpenAI available, request Markdown via prompt;
    otherwise construct a deterministic Markdown summary from graph + changed files.
    """
    changed_files = changed_files or []
    impacted_services = impacted_services or []

    severity = severity_from_count(len(impacted_services))

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

    return _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity)


def _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity):
    impacted_display = ", ".join(impacted_services) if impacted_services else "None"
    top_table = (
        "| Severity | Impacted Services | Changed Files Count | Recommendation |\n"
        "|---:|---|---:|---|\n"
        f"| **{md_escape(severity)}** | {md_escape(impacted_display)} | {len(changed_files)} | "
        f"{md_escape('Run integration tests across impacted services; coordinate schema changes.')} |\n"
    )

    summary_lines = []
    summary_lines.append(f"**PR Title:** {md_escape(pr_title)}")
    if changed_files:
        summary_lines.append(f"Changed {len(changed_files)} file(s): {md_escape(', '.join(changed_files))}.")
    else:
        summary_lines.append("No changed files found in CHANGED_FILES env variable.")
    summary_lines.append(f"Estimated severity based on impacted services: **{md_escape(severity)}**.")
    summary = "\n\n".join(summary_lines)

    per_service_sections = []
    for svc in impacted_services:
        files_changed = []
        for cf in changed_files:
            if cf.replace("\\", "/").startswith(svc + "/") or f"/{svc}/" in cf.replace("\\", "/"):
                files_changed.append(cf)
        files_cell = md_escape(", ".join(files_changed)) if files_changed else "N/A"

        if "db" in svc.lower() or "crud" in svc.lower():
            impact_level = "Medium"
            reason = "Data read/write boundary; schema or field changes may break consumers."
            suggested_tests = "DB contract tests, integration account-load flow"
        elif "ui" in svc.lower() or "frontend" in svc.lower():
            impact_level = "Low"
            reason = "UI may require adaptation for new fields or error formats."
            suggested_tests = "UI smoke tests, rendering checks"
        else:
            impact_level = "High"
            reason = "Core domain changes may cascade to downstream services and vendors."
            suggested_tests = "End-to-end account-load flow, contract tests"

        recommended_actions = "Review API contracts; add integration tests; notify downstream owners"
        potential_risks = "Incorrect data, increased latency, service errors"
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
            "| Service | Impact Level | Reason | Files Changed | Suggested Tests | "
            "Recommended Actions | Potential Risks | Suggested Reviewers |\n"
            "|---|---|---|---|---|---|---|---|\n"
        )
        per_service_sections.append(f"### {md_escape(svc)}\n\n{header}{svc_row}")

    per_service_md = "\n\n".join(per_service_sections) if per_service_sections else "_No impacted services detected._"

    recommended_tests = [
        "End-to-end account-load integration test",
        "Backward compatibility contract tests",
        "Schema validation for new/changed payload fields",
        "Performance smoke test for the modified flow",
        "Audit logs/observability checks post-deploy",
    ]
    tests_md = "\n".join([f"- {md_escape(t)}" for t in recommended_tests])

    final_guidance = (
        "Before merging, ensure integration tests pass between the affected services, notify downstream owners, "
        "and schedule a quick runbook review in case of rollback."
    )

    parts = [
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
    ]
    return "\n".join(parts)
