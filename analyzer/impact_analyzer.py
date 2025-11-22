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
    Build a premium Markdown-only prompt:
    - Dashboard-style summary (cards/tables)
    - Engineering deep-dive per service
    - Recommended tests + reviewer guidance
    """
    snippet_block = compact_snippets_text(snippets, limit=6) if snippets else "No code snippets available."

    prompt = f"""
You are a senior software architect. Generate a **Premium GitHub PR Impact Dashboard** using **pure Markdown only**.
The result will be posted as a GitHub Pull Request comment.

Your style should combine:
- A clean, high-level dashboard summary (Option A)
- A deeper engineering analysis per impacted service (Option B)

Do NOT use HTML tags. Use only Markdown: headings, lists, tables, blockquotes, and emojis.

======================================================================
# 1️⃣ HEADER
======================================================================

Start with:

# 🚀 PR Impact Dashboard

Then add 1 short sentence describing the PR impact at a high level.

======================================================================
# 2️⃣ IMPACT SUMMARY (DASHBOARD CARDS)
======================================================================

Render a compact summary table:

| Metric | Value |
|--------|-------|
| Severity | one of: 🟢 LOW / 🟡 MEDIUM / 🔴 HIGH |
| Impacted Services | number of impacted services + short list |
| Changed Files | total count of changed files |
| Risk Profile | short phrase (e.g., "Localized", "Cross-service", "High blast radius") |
| Recommended Action | short action phrase ("Run full E2E", "Focus on contracts", etc.) |

Choose severity, risk profile, and recommended action based on the context.

======================================================================
# 3️⃣ HIGH-LEVEL SUMMARY (ENGINEERING NARRATIVE)
======================================================================

Section heading:

## 📝 High-Level Summary

Write 3–5 sentences that:
- Explain what this PR does using the PR title and changed files.
- Describe how the changes affect upstream/downstream services or contracts.
- Mention any notable schema, API, or behavioral changes.
- Briefly call out main risks.

Keep it clear and readable for reviewers.

======================================================================
# 4️⃣ PER-SERVICE IMPACT DEEP DIVE
======================================================================

Heading:

## 🧩 Service Impact Deep Dive

For EACH impacted service, create a subsection:

### 🧱 <service-name>

Then include the following structure in Markdown:

- **Role in system:** 1 short sentence (e.g., "API gateway for account load requests").
- **Why impacted:** 1–3 sentences explaining why this PR touches this service.
- **Key changes:**
  - Bullet list of 2–4 concrete changes related to this service.
- **Risk level:** LOW / MEDIUM / HIGH (and a short justification).
- **Files to review:**
  - Bullet list of actual changed files associated with this service (if any).
- **Recommended tests:**
  - 2–5 bullets with specific, realistic tests for this service.
- **Potential failure modes:**
  - 2–4 bullets describing how things could break.
- **Suggested reviewers:** GitHub handles, team names, or "TBD".

If a service has no directly mapped files but is impacted via the graph, explain that it is downstream/upstream.

======================================================================
# 5️⃣ CROSS-SERVICE / GRAPH INSIGHTS
======================================================================

Heading:

## 🔗 Cross-Service & Dependency Insights

Use 2–5 bullet points to describe:
- Which services are central or high-risk from the graph.
- Any downstream services that might be indirectly affected.
- Whether blast radius is mostly internal or spans external vendors.
- Any notable contracts or schemas in the dependency graph.

Base this on the service dependency graph JSON and snippets.

======================================================================
# 6️⃣ RECOMMENDED TEST COVERAGE
======================================================================

Heading:

## 🧪 Recommended Test Coverage

Produce 5–10 bullet points combining:
- End-to-end scenarios (e.g., full account load flow).
- API/contract compatibility tests.
- Schema validation.
- Negative/error path tests.
- Performance or latency checks if appropriate.
- Observability/logging/alerting validation.

Make each bullet practical and concrete.

======================================================================
# 7️⃣ FINAL REVIEWER GUIDANCE
======================================================================

Heading:

## 🧠 Final Reviewer Guidance

Write 3–6 sentences that:
- Summarize the overall risk and confidence.
- Call out what the reviewer MUST pay attention to (e.g., contracts, DB migrations).
- Suggest whether a staged rollout or feature flag is advisable.
- Mention any recommended follow-up monitoring after deployment.

======================================================================
CONTEXT (DO NOT PRINT THIS SECTION)
======================================================================

PR Title:
{pr_title}

Changed files:
{json.dumps(changed_files, indent=2)}

Impacted services:
{json.dumps(impacted_services, indent=2)}

Service dependency graph (JSON):
{json.dumps(graph_json, indent=2)}

Relevant code snippets (for reasoning only, do NOT print raw):
{snippet_block}

RULES:
- OUTPUT MUST BE PURE MARKDOWN (NO HTML, NO CODE FENCES).
- DO NOT include the "CONTEXT" section or any raw JSON in the output.
- Avoid hallucination: if unsure about reviewers/tests, use 'TBD' or 'N/A'.
- Keep the tone professional, concise, and helpful for PR reviewers.
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
            deterministic = _build_deterministic_markdown(
                pr_title, changed_files, impacted_services, graph_json, snippets, severity
            )
            return fallback_header + deterministic

    # No OpenAI configured: deterministic markdown
    return _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity)


def _build_deterministic_markdown(pr_title, changed_files, impacted_services, graph_json, snippets, severity):
    """
    Deterministic Markdown fallback, upgraded to match the premium dashboard style.
    Logic is the same; only formatting/text is richer.
    """
    impacted_display = ", ".join(impacted_services) if impacted_services else "None"

    # Map severity to emoji for nicer UI (UI-only change)
    severity_label = severity
    if severity == "HIGH":
        severity_display = "🔴 HIGH"
    elif severity == "MEDIUM":
        severity_display = "🟡 MEDIUM"
    else:
        severity_display = "🟢 LOW"

    # 1) Top dashboard summary table
    top_table = (
        "| Metric | Value |\n"
        "|--------|-------|\n"
        f"| Severity | **{md_escape(severity_display)}** |\n"
        f"| Impacted Services | {md_escape(impacted_display)} |\n"
        f"| Changed Files | {len(changed_files)} |\n"
        f"| Recommended Action | {md_escape('Run integration tests across impacted services; coordinate schema changes.')} |\n"
    )

    # 2) High-level summary
    summary_lines = []
    summary_lines.append(f"**PR Title:** {md_escape(pr_title)}")
    if changed_files:
        summary_lines.append(
            f"**Changed files ({len(changed_files)}):** {md_escape(', '.join(changed_files))}."
        )
    else:
        summary_lines.append("**Changed files:** No changed files found in CHANGED_FILES env variable.")
    summary_lines.append(f"**Estimated severity (based on impacted services):** {md_escape(severity_display)}.")
    summary_lines.append(
        "This change may affect core flows across the impacted services. Please review API contracts, "
        "schemas, and downstream dependencies before merging."
    )
    summary = "\n\n".join(summary_lines)

    # 3) Per-service deep dive (in a more narrative, non-table format)
    per_service_sections = []
    for svc in impacted_services:
        # attempt to extract files for service from changed_files
        files_changed = []
        for cf in changed_files:
            norm = cf.replace("\\", "/")
            if norm.startswith(svc + "/") or f"/{svc}/" in norm:
                files_changed.append(cf)

        if "db" in svc.lower() or "crud" in svc.lower():
            impact_level = "Medium"
            reason = "Data read/write boundary; schema or field changes may break consumers."
            suggested_tests = [
                "DB contract tests covering main entities",
                "Integration tests for account-load or core flows hitting this DB",
            ]
            risk_level = "🟡 MEDIUM"
        elif "ui" in svc.lower() or "frontend" in svc.lower():
            impact_level = "Low"
            reason = "UI surface may need adaptation for new fields or error formats."
            suggested_tests = [
                "UI smoke tests across main screens",
                "Rendering checks for new/changed fields",
            ]
            risk_level = "🟢 LOW"
        else:
            impact_level = "High"
            reason = "Core domain or integration logic may cascade to downstream services and vendors."
            suggested_tests = [
                "End-to-end tests for impacted business flows",
                "Contract tests for upstream/downstream APIs",
            ]
            risk_level = "🔴 HIGH"

        files_list_md = (
            "\n".join([f"- `{md_escape(f)}`" for f in files_changed]) if files_changed else "- N/A"
        )
        tests_list_md = "\n".join([f"- {md_escape(t)}" for t in suggested_tests])

        svc_block = [
            f"### 🧱 {md_escape(svc)}",
            "",
            f"- **Impact level:** {md_escape(impact_level)} ({risk_level})",
            f"- **Why impacted:** {md_escape(reason)}",
            "",
            "**Files to review:**",
            files_list_md,
            "",
            "**Recommended tests:**",
            tests_list_md,
            "",
            "- **Recommended actions:** Review API/DB contracts, add/adjust integration tests, notify downstream owners.",
            "- **Potential risks:** Incorrect data propagation, increased latency, or runtime errors in dependent services.",
            "- **Suggested reviewers:** TBD",
        ]
        per_service_sections.append("\n".join(svc_block))

    per_service_md = (
        "\n\n---\n\n".join(per_service_sections) if per_service_sections else "_No impacted services detected._"
    )

    # 4) Recommended tests list (generic + applicable to the whole PR)
    recommended_tests = [
        "End-to-end account-load (or equivalent) flow validation.",
        "Backward compatibility contract tests between core services.",
        "Schema validation for new/changed payload fields at boundaries.",
        "Performance smoke test for the modified critical path.",
        "Audit logs and observability checks post-deploy (dashboards/alerts).",
    ]
    tests_md = "\n".join([f"- {md_escape(t)}" for t in recommended_tests])

    # 5) Final guidance
    final_guidance = (
        "Before merging, ensure key integration tests pass for all impacted services, "
        "validate that downstream consumers continue to function as expected, and align with "
        "service owners on rollback and monitoring plans. If the blast radius is high, "
        "consider a phased rollout or feature flag strategy."
    )

    # Assemble full document
    parts = [
        "# 🚀 PR Impact Dashboard",
        "",
        "## 🔥 Impact Summary",
        "",
        top_table,
        "",
        "## 📝 High-Level Summary",
        "",
        summary,
        "",
        "## 🧩 Service Impact Deep Dive",
        "",
        per_service_md,
        "",
        "## 🧪 Recommended Test Coverage",
        "",
        tests_md,
        "",
        "## 🧠 Final Reviewer Guidance",
        "",
        final_guidance,
        "",
    ]
    return "\n".join(parts)
