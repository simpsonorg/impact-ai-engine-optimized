# analyzer/impact_analyzer.py
import os
import json
import textwrap

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


def _build_rich_prompt(pr_title, changed_files, impacted_services, graph_json, snippets, severity_estimates=None):
    """
    Build a deterministic, structured prompt that asks the LLM to return both:
      1) a JSON object with explicit fields (for programmatic consumption)
      2) a Markdown string ready to paste into a GitHub PR
    Returns a list of messages suitable for chat completions.
    """
    system_prompt = textwrap.dedent("""
    You are a concise, pragmatic engineering assistant that produces actionable PR impact summaries.
    Output MUST include a top-level JSON object with the exact fields:
      - brief_summary (string, 1-2 sentences)
      - overall_risk (one of: low, medium, high)
      - confidence (0.0-1.0)
      - impact_by_service (array of objects):
          { service: string, impact_level: low|medium|high, reason: string, files_changed: [string],
            suggested_tests: [string], recommended_actions: [string], potential_risks: [string],
            suggested_reviewers: [string] }
      - recommended_next_steps (array of strings)
      - markdown_comment (string)  <-- A ready-to-post GitHub Markdown/HTML string
    Be succinct. Use the provided knowledge graph node attributes (pagerank, betweenness, scc_size, downstream_count, normalized_weight, and contracts) to prioritize and justify impact reasoning.
    When explaining "why" for each service, reference changed files, node attributes, or snippets.
    After the JSON, also append the markdown_comment text exactly as provided in the json field.
    Do NOT include extra commentary outside the JSON and the markdown_comment.
    """)

    # build a node_attrs map so the LLM gets direct access to node metrics and contracts
    node_attrs = {}
    for n in graph_json.get("nodes", []):
        nid = n.get("id")
        if nid:
            node_attrs[nid] = n.get("attr", {})

    payload = {
        "pr_title": pr_title,
        "changed_files": changed_files,
        "impacted_services": impacted_services,
        "service_graph": {
            "nodes": graph_json.get("nodes", []),
            "edges": graph_json.get("edges", [])
        },
        "node_attributes": node_attrs,
        "top_snippets": snippets or [],
        "severity_estimates": severity_estimates or {}
    }

    # Attach changed file hunks and contract references to the payload for stronger LLM reasoning
    try:
        base_dir = os.getenv("REPOS_BASE_DIR", ".")
        changed_hunks = [__import__('analyzer.vcs_scanner').vcs_scanner.get_changed_file_hunk(base_dir, cf) for cf in changed_files]
        payload["changed_hunks"] = changed_hunks
        # gather contract refs per file
        contract_refs = {}
        services = {n['id']: n.get('attr', {}) for n in graph_json.get('nodes', [])}
        for h in changed_hunks:
            content = h.get('snippet', '')
            # aggregate all contracts from services
            all_contracts = {}
            for sid, attr in services.items():
                if attr.get('contracts'):
                    all_contracts[sid] = attr.get('contracts')
            refs = __import__('analyzer.vcs_scanner').vcs_scanner.extract_contract_references(content, all_contracts)
            if refs:
                contract_refs[h.get('file')] = refs
        payload['contract_references'] = contract_refs
    except Exception:
        pass

    user_prompt = textwrap.dedent(f"""
    Input (JSON):
    {json.dumps(payload, indent=2)}

    Requirements:
    - Produce the JSON object (exact schema above) then produce the markdown_comment.
    - Use node_attributes to identify which services are critical (high pagerank / betweenness / scc_size) and explicitly cite them when recommending action/prioritization.
    - For each impacted service recommend specific tests, rollout strategies, CI job lines, and reviewers where possible.
    - If a service node includes 'contracts' (openapi/proto), explicitly check for potential contract-breaking changes against changed files and mention any risky endpoints.
    - Provide one-line suggested test commands / CI jobs when you can (e.g., `pytest services/A/tests/test_x.py::test_y`).
    - Keep the overall brief_summary to 1-2 sentences.
    - Keep markdown_comment concise (~<= 800 words), with:
        * A short header summary
        * A checklist of recommended actions
        * Per-service sections (use headings)
        * Code-snippet references where relevant (include file paths and line ranges)
    """)

    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def _call_llm_messages(messages, max_tokens=1500, temperature=0.15):
    """
    Wrapper to call the configured OpenAI client. Returns assistant text.
    Tries the module-level _openai (new client) first, falls back to legacy openai package.
    """
    if _openai is None:
        raise RuntimeError("No LLM client configured")

    # Try new-style client first
    try:
        resp = _openai.chat.completions.create(messages=messages, model="gpt-4o-mini", max_tokens=max_tokens, temperature=temperature)
        # new client: resp.choices[0].message.content
        if hasattr(resp, "choices") and len(resp.choices) > 0:
            choice = resp.choices[0]
            # choice.message.content or choice['message']['content']
            content = None
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                content = choice.message.content
            elif isinstance(choice, dict) and "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]
            if content is not None:
                return content
        return str(resp)
    except Exception:
        # fallback to legacy openai package if available
        try:
            import openai
            resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages, max_tokens=max_tokens, temperature=temperature)
            return resp.choices[0].message['content']
        except Exception as e:
            raise


def analyze(pr_title, changed_files, impacted_services, graph_json, snippets):
    """
    Returns an HTML+Markdown string suitable to post as a GitHub PR comment.
    Attempts a structured JSON+Markdown LLM call first (if OpenAI client present). Falls back to
    the original behavior when no client is configured or when structured generation fails.
    """
    # If no client, keep original graceful fallback unchanged
    if _openai is None:
        print("[impact_analyzer] FALLBACK: no LLM client configured - using static summary")
        # existing static fallback retained
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
        parts = [header, "<h3>📝 Summary</h3>", "<p>OpenAI API key not configured; showing best-effort static analysis.</p>", "<h3>🧩 Impacted Services</h3>"]
        for s in impacted_services:
            parts.append(f'<div class="service-card"><h3>{s}</h3><p><b>Why impacted:</b> Service appears downstream of changed files.</p><p><b>Files to review:</b></p><ul>')
            parts.append("<li>Review service entry points & API handlers</li>")
            parts.append("</ul><p><b>Recommended fixes:</b></p><ul><li>Coordinate schema changes</li></ul><p><b>Risk:</b> MEDIUM</p></div>")
        parts.append("<h3>🧪 Recommended Tests</h3><ul><li>End-to-end account-load flow</li><li>Backward compatibility checks</li></ul>")
        parts.append("<h3>🧠 Final Guidance</h3><p>Configure OPENAI_API_KEY to enable richer RAG-based analysis.</p>")
        return "\n".join(parts)

    # Try structured JSON+Markdown generation first
    try:
        print("[impact_analyzer] Attempting structured LLM call")
        messages = _build_rich_prompt(pr_title, changed_files, impacted_services, graph_json, snippets)
        assistant_text = _call_llm_messages(messages)
        if assistant_text:
            # attempt to extract JSON object from the assistant text
            try:
                start = assistant_text.index("{")
                end = assistant_text.rindex("}") + 1
                json_blob = assistant_text[start:end]
                parsed = json.loads(json_blob)
                # If the assistant returned the required markdown_comment, use it as the reply body
                if isinstance(parsed, dict) and "markdown_comment" in parsed:
                    print("[impact_analyzer] USING_LLM: structured response received")
                    content = parsed.get("markdown_comment") or ""
                    # ensure CSS present
                    if HTML_CARD_CSS.strip() not in content:
                        content = HTML_CARD_CSS + "\n" + content
                    return content
                # otherwise, if it's parseable but without markdown_comment, fall through to legacy prompt
            except Exception:
                # parsing failed; fall back to legacy prompt flow below
                print("[impact_analyzer] Structured LLM returned unparsable response; falling back")
                assistant_text = assistant_text
    except Exception as e:
        print(f"[impact_analyzer] Structured LLM call failed: {e}")
        # structured LLM path failed; fall back to existing behavior
        assistant_text = None

    # Legacy LLM behavior: keep existing prompt and usage to avoid breaking prior callers
    prompt = build_prompt(pr_title, changed_files, impacted_services, graph_json, snippets)
    try:
        print("[impact_analyzer] Attempting legacy LLM call")
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.18,
            max_tokens=1700,
        )
        content = resp.choices[0].message.content
        print("[impact_analyzer] USING_LLM: legacy response received")
        if HTML_CARD_CSS.strip() not in content:
            content = HTML_CARD_CSS + "\n" + content
        return content
    except Exception as e:
        print(f"[impact_analyzer] Legacy LLM call failed: {e}")
        return f"⚠️ LLM call failed: {e}\n\n(Partial context included)\n\n" + HTML_CARD_CSS + f"\n<div class='card'><h2>Impact Analysis (partial)</h2><p>LLM failed: {e}</p></div>"
