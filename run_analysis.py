# run_analysis.py
import os
import traceback
from datetime import datetime
import json

from analyzer.vcs_scanner import discover_microservices, build_service_dependency_graph
from analyzer.graph_builder import build_knowledge_graph, impacted_services_from_files, knowledge_graph_to_json
from analyzer.rag_retriever import get_relevant_snippets
from analyzer.impact_analyzer import analyze


def load_changed_files() -> list:
    raw = os.getenv("CHANGED_FILES", "").strip()
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def safe_output(txt: str) -> str:
    if not txt or not txt.strip():
        return (
            "# Impact Analysis Report\n"
            "⚠️ AI engine returned no content.\n"
            "This may occur when no relevant code changes were detected."
        )
    return txt


def run_analysis():
    pr_title = os.getenv("PR_TITLE", "(no PR title)")
    base_dir = os.getenv("REPOS_BASE_DIR", ".")
    changed_files = load_changed_files()

    header = f"<!-- Impact Analysis Generated: {datetime.utcnow().isoformat()}Z -->\n"
    if not changed_files:
        return header + "# Impact Analysis Report\nNo changed files detected."

    # 1) Discover microservices
    services = discover_microservices(base_dir)

    # 2) Basic service graph
    svc_graph = build_service_dependency_graph(services)

    # 3) Knowledge graph
    KG = build_knowledge_graph(svc_graph)
    impacted, edges = impacted_services_from_files(changed_files, services, KG)
    graph_json = knowledge_graph_to_json(KG)

    # 4) RAG snippets (best-effort)
    try:
        snippets = get_relevant_snippets(base_dir, services, impacted, changed_files, max_snippets=12)
    except Exception as e:
        snippets = []
        # keep non-fatal
        print(f"<!-- RAG retrieval failed: {e} -->")

    # 5) LLM analysis -> HTML+Markdown comment
    try:
        ai_comment = analyze(pr_title, changed_files, impacted, graph_json, snippets)
    except Exception as e:
        ai_comment = f"# Impact Analysis Error\nLLM analysis failed: {e}\n\n```\n{traceback.format_exc()}\n```"

    # 6) Optional: write artifact summary
    try:
        summary = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "pr_title": pr_title,
            "changed_files": changed_files,
            "impacted": impacted,
            "risk_estimate": len(impacted),
        }
        with open("impact-summary.json", "w") as f:
            json.dump(summary, f, indent=2)
    except Exception:
        pass

    return header + ai_comment


if __name__ == "__main__":
    try:
        print(safe_output(run_analysis()))
    except Exception as e:
        print("# Impact Analysis Error")
        print(str(e))
        print("```")
        print(traceback.format_exc())
        print("```")
