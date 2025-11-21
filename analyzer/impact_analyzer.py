import os
import json
import textwrap
import traceback
from typing import List, Dict, Any

# Optional LLM client. If not configured, analyzer uses deterministic fallback markdown.
try:
    from openai import OpenAI
    _openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _openai = None


def _estimate_severity(impacted_services: List[str]) -> str:
    n = len(impacted_services or [])
    if n >= 6:
        return "HIGH"
    if n >= 3:
        return "MEDIUM"
    return "LOW"


def _compact_snippets(snippets: List[Dict[str, Any]], limit: int = 6) -> str:
    out = []
    for s in (snippets or [])[:limit]:
        svc = s.get("service") or "svc"
        file = s.get("file") or s.get("path") or "<unknown>"
        txt = s.get("snippet") or s.get("text") or ""
        out.append(f"[{svc}] {file}:\n{txt[:600]}")
    return "\n\n".join(out) or "No snippets available."


def build_unified_prompt(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Unified prompt: request structured JSON (strict schema) + markdown_comment (Markdown only).
    The LLM is explicitly told not to emit HTML/CSS.
    """
    system = textwrap.dedent(
        """You are an expert software architect assistant.

Return a JSON object EXACTLY matching the schema described below, then append the markdown_comment text (same content).
The markdown_comment must be **pure GitHub Markdown** (no HTML/CSS), use emoji badges (🔴/🟠/🟢) and Markdown tables for summary cards.
Output nothing outside the JSON and the appended markdown_comment.

JSON schema:
- brief_summary (string)
- overall_risk ("low"|"medium"|"high")
- confidence (float 0.0-1.0)
- top_summary_card: { severity_label, impacted_services_count, changed_files_count, one_line_recommendation }
- microservice_dependency_summary (string)
- impact_by_service: array of {
    service, impact_level (low|medium|high), why_impacted, files_to_review: [{path, snippets}],
    recommended_fixes: [str], recommended_tests: [str], risk, count_changed_files:int, suggested_reviewers:[str]
  }
- recommended_tests (array of strings)
- next_steps (array of strings)
- markdown_comment (string)  <-- pure Markdown (<= 800 words)
"""
    )
    payload = {
        "pr_title": pr_title,
        "changed_files": changed_files,
        "impacted_services": impacted_services,
        "service_graph": {"nodes": graph_json.get("nodes", []), "edges": graph_json.get("edges", [])},
        "node_attributes": {n.get("id"): n.get("attr", {}) for n in graph_json.get("nodes", [])},
        "top_snippets": snippets or [],
        "severity_hint": _estimate_severity(impacted_services),
    }
    user = "CONTEXT:\n" + json.dumps(payload, indent=2) + "\n\nProduce the JSON then append the markdown_comment (pure Markdown)."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _call_llm_messages(messages, max_tokens=1400, temperature=0.15):
    if _openai is None:
        raise RuntimeError("LLM client not configured.")
    try:
        resp = _openai.chat.completions.create(messages=messages, model="gpt-4o-mini", max_tokens=max_tokens, temperature=temperature)
        if hasattr(resp, "choices") and resp.choices:
            choice = resp.choices[0]
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                return choice.message.content
            if isinstance(choice, dict) and "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
        return str(resp)
    except Exception:
       
        import openai
        resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages, max_tokens=max_tokens, temperature=temperature)
        return resp.choices[0].message["content"]


def build_markdown_report(summary: Dict[str, Any]) -> str:
    """Deterministic Markdown renderer (used as fallback or to convert parsed JSON)."""
    def badge(sev: str) -> str:
        s = (sev or "").lower()
        return "🔴 HIGH" if s == "high" else ("🟠 MEDIUM" if s == "medium" else "🟢 LOW")

    lines = []
    lines.append("# 🎛️ Impact Analysis Summary\n")
    lines.append(f"**Brief:** {summary.get('brief_summary','-')}\n")
    lines.append(f"**Overall risk:** {badge(summary.get('overall_risk','medium'))}  ")
    lines.append(f"**Confidence:** {int(round(summary.get('confidence', 0.0)*100))}%\n")

    # Top summary table
    top = summary.get("top_summary_card", {})
    lines.append("### Summary Card\n")
    lines.append("| Severity | Impacted services | Changed files | Recommendation |")
    lines.append("|---|---|---:|---|")
    lines.append(f"| {badge(top.get('severity_label','medium'))} | {top.get('impacted_services_count',0)} | {top.get('changed_files_count',0)} | {top.get('one_line_recommendation','-')} |")
    lines.append("\n---\n")

    # Dependency summary
    lines.append("### 🔗 Microservice Dependency Summary\n")
    lines.append(summary.get("microservice_dependency_summary","") + "\n")

    # What changed
    lines.append("### 📝 Summary of Change\n")
    lines.append(summary.get("brief_summary","") + "\n")

    # Impact by service: concise table + details
    lines.append("### 🔎 Downstream Impact Breakdown\n")
    svc_rows = ["| Service | Impact | Risk | Changed files | Suggested reviewers |", "|---|---|---|---|---|"]
    for s in summary.get("impact_by_service", []):
        svc_rows.append(f"| {s.get('service')} | {s.get('impact_level','medium').upper()} | {s.get('risk','medium').upper()} | {s.get('count_changed_files',0)} | {', '.join(s.get('suggested_reviewers',[]))} |")
    if len(svc_rows) > 2:
        lines.extend(svc_rows)
        lines.append("")

    for s in summary.get("impact_by_service", []):
        lines.append(f"#### {s.get('service')} — **Impact: {s.get('impact_level','medium').upper()}**")
        lines.append(f"- **Why impacted:** {s.get('why_impacted','')}")
        files = s.get("files_to_review", [])
        if files:
            lines.append("- **Files to review:**")
            for f in files:
                lines.append(f"  - `{f.get('path','')}`")
                if f.get("snippets"):
                    lines.append("    ```")
                    lines.append(f.get("snippets"))
                    lines.append("    ```")
        fixes = s.get("recommended_fixes", [])
        if fixes:
            lines.append("- **Recommended fixes:**")
            for fx in fixes:
                lines.append(f"  - {fx}")
        rtests = s.get("recommended_tests", [])
        if rtests:
            lines.append("- **Recommended tests:**")
            for rt in rtests:
                lines.append(f"  - `{rt}`")
        if s.get("suggested_reviewers"):
            lines.append(f"- **Suggested reviewers:** {', '.join(s.get('suggested_reviewers'))}")
        lines.append("")

    # Recommended tests
    lines.append("### 🧪 Recommended Tests")
    for t in summary.get("recommended_tests", []):
        lines.append(f"- {t}")
    lines.append("")

    # Next steps
    lines.append("### ▶️ Next Steps / Rollout Guidance")
    for n in summary.get("next_steps", []):
        lines.append(f"- {n}")
    lines.append("\n---\n*Generated by impact-ai-engine.*")
    return "\n".join(lines)


def analyze(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Entrypoint: returns Markdown-only string.
    Flow:
      - If LLM configured: request structured JSON+markdown and return markdown_comment.
      - If no LLM or parsing fails: return deterministic Markdown from fallback.
    """
    # Fallback path (no LLM configured)
    if _openai is None:
        severity = _estimate_severity(impacted_services)
        summary = {
            "brief_summary": f"PR touches {len(changed_files)} file(s). Core impacted services: {', '.join(impacted_services)}.",
            "overall_risk": severity.lower(),
            "confidence": 0.78,
            "top_summary_card": {
                "severity_label": severity,
                "impacted_services_count": len(impacted_services),
                "changed_files_count": len(changed_files),
                "one_line_recommendation": "Run E2E tests and coordinate schema changes."
            },
            "microservice_dependency_summary": "PSG is between APIGEE/UI and Domain MS; Domain MS calls CRUD DB and FDR vendor.",
            "impact_by_service": [
                {
                    "service": s,
                    "impact_level": "high" if ("psg" in s.lower() or "domain" in s.lower()) else "medium",
                    "why_impacted": "Downstream of changed routing layer." if "psg" in s.lower() else "Consumer of PSG output.",
                    "files_to_review": [{"path": cf, "snippets": ""} for cf in changed_files][:2],
                    "recommended_fixes": ["Add schema validation", "Add integration test"],
                    "recommended_tests": ["curl -s -X POST http://localhost:8001/api/account/load -d '<payload>' -H 'Content-Type: application/json'"],
                    "risk": "high" if ("psg" in s.lower() or "domain" in s.lower()) else "medium",
                    "count_changed_files": len(changed_files),
                    "suggested_reviewers": [f"owner-{s.split('-')[0]}" if "-" in s else f"owner-{s}"]
                } for s in impacted_services
            ],
            "recommended_tests": [
                "E2E: UI -> APIGEE -> PSG -> Domain -> CRUD_DB (staging)",
                "Contract test: openapi-diff between base and head for /api/account/load",
                "Unit tests for Domain MS mapping logic"
            ],
            "next_steps": [
                "Coordinate schema change with downstream owners",
                "Run staging E2E and a 1% canary rollout",
                "Prepare nullable DB migration if writing new fields"
            ]
        }
        return build_markdown_report(summary)

    # LLM path
    messages = build_unified_prompt(pr_title, changed_files, impacted_services, graph_json, snippets)
    try:
        assistant_text = _call_llm_messages(messages)
    except Exception as e:
        return build_markdown_report({
            "brief_summary": f"LLM call failed: {e}",
            "overall_risk": "medium",
            "confidence": 0.2,
            "top_summary_card": {"severity_label": "MEDIUM", "impacted_services_count": len(impacted_services), "changed_files_count": len(changed_files), "one_line_recommendation": "LLM failed - run local tests"},
            "microservice_dependency_summary": "LLM failure fallback",
            "impact_by_service": [],
            "recommended_tests": [],
            "next_steps": ["Investigate LLM error"]
        })

    # parse JSON then return markdown_comment
    try:
        start = assistant_text.index("{")
        end = assistant_text.rfind("}") + 1
        json_blob = assistant_text[start:end]
        parsed = json.loads(json_blob)
        if isinstance(parsed, dict) and parsed.get("markdown_comment"):
            md = parsed.get("markdown_comment", "")
            # sanitize any accidental HTML (extra safety)
            import re
            md = re.sub(r"(?is)<style.*?>.*?</style>", "", md)
            md = re.sub(r"(?is)<\/?div.*?>", "", md)
            return md
        elif isinstance(parsed, dict):
            return build_markdown_report(parsed)
    except Exception:
        pass

    # final fallback
    return build_markdown_report({
        "brief_summary": "Unable to parse LLM output; manual review required.",
        "overall_risk": "medium",
        "confidence": 0.25,
        "top_summary_card": {"severity_label": "MEDIUM", "impacted_services_count": len(impacted_services), "changed_files_count": len(changed_files), "one_line_recommendation": "Manual review."},
        "microservice_dependency_summary": "Parsing fallback",
        "impact_by_service": [],
        "recommended_tests": [],
        "next_steps": ["Inspect LLM raw output in CI logs"]
    })
