# analyzer/impact_analyzer.py
import os
import json

# OpenAI client for LLM calls (new API wrapper)
try:
    from openai import OpenAI
    _openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _openai = None

HTML_CARD_CSS = """
<style>
.card {
  padding:16px;
  margin:12px 0;
  border:1px solid #e1e4e8;
  border-radius:8px;
  background:#fafbfc;
}
.card h2, .card h3 { margin-top:0; }
.sev-high { color:white; background:#d73a49; padding:2px 6px; border-radius:4px; }
.sev-med  { color:white; background:#fb8c00; padding:2px 6px; border-radius:4px; }
.sev-low  { color:white; background:#28a745; padding:2px 6px; border-radius:4px; }
.service-card {
  padding:12px;
  margin-bottom:12px;
  border:1px solid #e1e4e8;
  border-radius:6px;
  background:#ffffff;
}
</style>
"""


def _estimate_severity(impacted_services):
    n = len(impacted_services)
    if n >= 6:
        return "HIGH"
    if n >= 3:
        return "MEDIUM"
    return "LOW"


def _compact_snippets(snippets, limit=8):
    out = []
    for s in snippets[:limit]:
        text = s.get("snippet", "")
        # keep small excerpt
        out.append(f"[{s.get('service')}] {s.get('file')}:\\n{text[:800]}")
    return "\\n\\n".join(out)


def build_prompt(pr_title, changed_files, impacted_services, graph_json, snippets):
    severity = _estimate_severity(impacted_services)
    snippet_block = _compact_snippets(snippets, limit=8) if snippets else "No code snippets available."

    prompt = f"""You are a senior software architect writing a GitHub PR comment using inline HTML cards (safe for GitHub).
Start the comment with the CSS block exactly as provided, then produce:

1) TOP DASHBOARD CARD using class="card" with:
   - Title
   - Severity badge (.sev-high/.sev-med/.sev-low)
   - Impacted services (comma list)
   - Changed files count
   - One line recommendation

2) SUMMARY: 3-5 lines explaining what changed and why it matters.

3) For each impacted service produce a service-card div:
   - <h3>service name</h3>
   - Why impacted
   - Files to review (list)
   - Recommended fixes (bullets)
   - Risk (LOW/MEDIUM/HIGH)

4) Recommended tests (4-7 bullets)

5) Final reviewer guidance (3-6 lines)

Use the context below to reason. Output MUST be HTML+Markdown (no JSON, no code fence block wrapping the whole output).

--- CONTEXT ---
PR Title:
{pr_title}

Changed files:
{json.dumps(changed_files, indent=2)}

Impacted services:
{json.dumps(impacted_services, indent=2)}

Service graph:
{json.dumps(graph_json, indent=2)}

Relevant code snippets (for reasoning):
{snippet_block}
--- END CONTEXT ---
"""
    return prompt


def analyze(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Returns an HTML+Markdown string suitable to post as a GitHub PR comment.
    """
    if _openai is None:
        # graceful fallback: construct a plain HTML summary without LLM
        severity = _estimate_severity(impacted_services)
        sev_class = "sev-high" if severity == "HIGH" else ("sev-med" if severity == "MEDIUM" else "sev-low")
        services = ", ".join(impacted_services) or "None"
        changed_count = len(changed_files)
        header = HTML_CARD_CSS + (
                "\n<div class=\"card\">\n"
                "<h2>🎛️ Impact Analysis Dashboard</h2>\n"
                f"<p><b>Severity:</b> <span class=\"{sev_class}\">{severity}</span></p>\n"
                f"<p><b>Impacted Services:</b> {services}</p>\n"
                f"<p><b>Changed Files:</b> {changed_count}</p>\n"
                "<p><b>Recommendation:</b> Run full regression and notify downstream owners.</p>\n"
                "</div>\n"
            )
        # minimal per-service cards
        parts = [header, "<h3>📝 Summary</h3>", "<p>OpenAI API key not configured; showing best-effort static analysis.</p>", "<h3>🧩 Impacted Services</h3>"]
        for s in impacted_services:
            parts.append(f'<div class="service-card"><h3>{s}</h3><p><b>Why impacted:</b> Service appears downstream of changed files.</p><p><b>Files to review:</b></p><ul>')
            # try to list up to 6 files from graph_json nodes
            # graph_json contains nodes/edges but not file lists here; keep generic
            parts.append("<li>Review service entry points & API handlers</li>")
            parts.append("</ul><p><b>Recommended fixes:</b></p><ul><li>Coordinate schema changes</li></ul><p><b>Risk:</b> MEDIUM</p></div>")
        parts.append("<h3>🧪 Recommended Tests</h3><ul><li>End-to-end account-load flow</li><li>Backward compatibility checks</li></ul>")
        parts.append("<h3>🧠 Final Guidance</h3><p>Configure OPENAI_API_KEY to enable richer RAG-based analysis.</p>")
        return "\n".join(parts)

    prompt = build_prompt(pr_title, changed_files, impacted_services, graph_json, snippets)
    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.18,
            max_tokens=1700,
        )
        content = resp.choices[0].message.content
        # ensure CSS present
        if HTML_CARD_CSS.strip() not in content:
            content = HTML_CARD_CSS + "\n" + content
        return content
    except Exception as e:
        return f"⚠️ LLM call failed: {e}\n\n(Partial context included)\n\n" + HTML_CARD_CSS + f"\n<div class='card'><h2>Impact Analysis (partial)</h2><p>LLM failed: {e}</p></div>"
