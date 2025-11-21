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


def build_llm_prompt_markdown(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Build a strict prompt that asks the LLM to return ONLY Markdown:
    - Top summary table
    - Per-service tables with specific columns
    - Recommended test list
    - Final guidance paragraph
    """
    snippet_block = compact_snippets_text(snippets, limit=6) if snippets else "No code snippets available."
    prompt = f"""
You are an expert software architect. Produce a GitHub PR impact comment in PURE MARKDOWN ONLY (no HTML).
Return the following sections **exactly** (use Markdown tables where indicated):

1) Top-level summary table with columns:
| Severity | Impacted Services | Changed Files Count | Recommendation |
|---:|---|---:|---|

2) A short "Summary" paragraph (2-4 sentences).

3) For each impacted service produce a table with columns:
| Service | Impact Level | Reason | Files Changed | Suggested Tests | Recommended Actions | Potential Risks | Suggested Reviewers |
|---|---|---|---|---|---|---|---|

- Fill the table rows. Keep text concise (1-3 short sentences per cell).
- Files Changed should be comma-separated relative paths.
- Suggested Tests should be a comma-separated list (or 'N/A').
- Suggested Reviewers should be GitHub handles if known or team names.

4) "Recommended Tests" section as a Markdown bulleted list (4-7 items).

5) "Final Reviewer Guidance" short paragraph (2-4 lines).

CONTEXT (do not print this block; use it to reason):

PR Title:
{pr_title}

Changed files:
{json.dumps(changed_files, indent=2)}

Impacted services:
{json.dumps(impacted_services, indent=2)}

Service dependency graph (JSON):
{json.dumps(graph_json, indent=2)}

Relevant code snippets (for reasoning):
{snippet_block}

RULES:
- OUTPUT MUST BE PURE MARKDOWN. Do NOT include any explanations outside the requested sections.
- Avoid hallucination: if you don't know reviewers or tests, write 'TBD' or 'N/A'.
- Keep each table cell reasonably short. Use line breaks (<br>) if multiple short items are needed.
"""
    return prompt


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
            # enforce that it returns markdown only; if not, fallback to deterministic
            if not content.strip():
                raise ValueError("LLM returned empty content")
            return content
        except Exception as e:
            # fall back to deterministic markdown below but include an error header
            fallback_header = f"> **⚠️ LLM failed:** {str(e)}\n\n"
            deterministic = _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity)
            return fallback_header + deterministic

    # No OpenAI configured: deterministic markdown
    return _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity)


def _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity):
    # Top summary table
    impacted_display = ", ".join(impacted_services) if impacted_services else "None"
    top_table = (
        "| Severity | Impacted Services | Changed Files Count | Recommendation |\n"
        "|---:|---|---:|---|\n"
        f"| **{md_escape(severity)}** | {md_escape(impacted_display)} | {len(changed_files)} | {md_escape('Run integration tests across impacted services; coordinate schema changes.') } |\n"
    )

    # Summary paragraph
    summary_lines = []
    summary_lines.append(f"**PR Title:** {md_escape(pr_title)}")
    if changed_files:
        summary_lines.append(f"Changed {len(changed_files)} file(s): {md_escape(', '.join(changed_files))}.")
    else:
        summary_lines.append("No changed files found in CHANGED_FILES env variable.")
    summary_lines.append(f"Estimated severity based on impacted services: **{md_escape(severity)}**.")
    summary = "\n\n".join(summary_lines)

    # Per-service tables
    per_service_sections = []
    for svc in impacted_services:
        # attempt to extract files for service from graph_json (if available)
        files_changed = []
        # graph_json might not contain files list; so check changed_files for path prefixes
        for cf in changed_files:
            if cf.replace("\\", "/").startswith(svc + "/") or f"/{svc}/" in cf.replace("\\", "/"):
                files_changed.append(cf)
        files_cell = md_escape(", ".join(files_changed)) if files_changed else "N/A"

        # simple heuristics for impact and reasons
        if svc.lower().find("db") >= 0 or svc.lower().find("crud") >= 0:
            impact_level = "Medium"
            reason = "Data read/write boundary; schema or field changes may break consumers."
            suggested_tests = "DB contract tests, integration account-load flow"
        elif svc.lower().find("ui") >= 0 or svc.lower().find("frontend") >= 0:
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

        # assemble a single-row table for the service (we keep one row per service)
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

    # Recommended tests list (generic)
    recommended_tests = [
        "End-to-end account-load integration test",
        "Backward compatibility contract tests",
        "Schema validation for new/changed payload fields",
        "Performance smoke test for the modified flow",
        "Audit logs/observability checks post-deploy"
    ]
    tests_md = "\n".join([f"- {md_escape(t)}" for t in recommended_tests])

    # Final guidance
    final_guidance = (
        "Before merging, ensure integration tests pass between the affected services, "
        "notify the downstream owners listed above, and schedule a quick runbook review in case of rollback."
    )

    # Assemble full document
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
