
import os
import json
import traceback
from datetime import datetime
from impact_analyzer import analyze

def load_changed_files() -> list:
    raw = os.getenv("CHANGED_FILES", "").strip()
    if not raw:
        return []
    if "\n" in raw:
        return [l.strip() for l in raw.splitlines() if l.strip()]
    return [p.strip() for p in raw.split(",") if p.strip()]

def discover_microservices(base_dir="."):
    # Minimal heuristic: expected service folders; fallback to sample list.
    svc = []
    for name in ["ui-account-load","apigee-mock-gateway","psg-mock-router","domain-ms-account-load","crud-ms-account-load-db","crud-ms-account-load-fdr","fdr-vendor-mock"]:
        if os.path.exists(os.path.join(base_dir, name)):
            svc.append(name)
    return svc or ["psg-mock-router","domain-ms-account-load","crud-ms-account-load-db"]

def build_service_dependency_graph(services):
    nodes = [{"id": s, "attr": {}} for s in services]
    edges = []
    return {"nodes": nodes, "edges": edges}

def build_knowledge_graph(svc_graph):
    return svc_graph

def impacted_services_from_files(changed_files, services, KG):
    # For prototype, mark all services impacted if ambiguous
    return services, []

def knowledge_graph_to_json(KG):
    return KG

def get_relevant_snippets(base_dir, services, impacted, changed_files, max_snippets=8):
    snippets = []
    for cf in changed_files:
        path = os.path.join(base_dir, cf)
        if os.path.exists(path):
            try:
                with open(path, "r", errors="ignore") as f:
                    txt = f.read(1000)
            except Exception:
                txt = ""
        else:
            txt = f"sample snippet for {cf}"
        snippets.append({"service": cf.split("/")[0] if "/" in cf else cf, "file": cf, "snippet": txt})
    return snippets

def run_analysis():
    pr_title = os.getenv("PR_TITLE", "(no PR title)")
    base_dir = os.getenv("REPOS_BASE_DIR", ".")
    changed_files = load_changed_files()
    header = f"<!-- Impact Analysis Generated: {datetime.utcnow().isoformat()}Z -->\n"
    if not changed_files:
        return header + "# Impact Analysis Report\nNo changed files detected."

    services = discover_microservices(base_dir)
    svc_graph = build_service_dependency_graph(services)
    KG = build_knowledge_graph(svc_graph)
    impacted, edges = impacted_services_from_files(changed_files, services, KG)
    graph_json = knowledge_graph_to_json(KG)

    try:
        snippets = get_relevant_snippets(base_dir, services, impacted, changed_files, max_snippets=8)
    except Exception:
        snippets = []

    try:
        ai_comment = analyze(pr_title, changed_files, impacted, graph_json, snippets)
    except Exception as e:
        ai_comment = "# Impact Analysis Error\nLLM analysis failed: " + str(e) + "\n\n" + traceback.format_exc()

    # Write simple artifact
    try:
        with open("impact-summary.json","w") as f:
            json.dump({"pr_title": pr_title, "changed_files": changed_files, "impacted": impacted}, f, indent=2)
    except Exception:
        pass

    return header + ai_comment

if __name__ == "__main__":
    print(run_analysis())
