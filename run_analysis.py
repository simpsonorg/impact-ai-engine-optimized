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


def premium_dashboard_wrapper(pr_title, changed_files, impacted_services, inner_ai_output):
    """
    Wraps LLM output in Premium Markdown Dashboard UI + STATIC dependency summary
    """

    # Risk level determination
    risk_level = (
        "🟩 Low" if len(impacted_services) <= 1
        else "🟨 Medium" if len(impacted_services) <= 3
        else "🟥 High"
    )

    # Table for impacted services
    impacted_table = "\n".join(
        [f"| {svc} | ✅ Impacted |" for svc in impacted_services]
    ) if impacted_services else "| None | No impact detected |"

    # STATIC MICROERVICE DEPENDENCY SUMMARY (always injected)
    static_dependencies = """
## 🔗 Microservice Dependency Summary (Static)
- **psg-mock-router** → ui-account-load, domain-ms-account-load, fdr-vendor-mock, apigee-mock-gateway, crud-ms-account-load-db, crud-ms-account-load-fdr  
- **ui-account-load** → psg-mock-router, domain-ms-account-load, fdr-vendor-mock, apigee-mock-gateway, crud-ms-account-load-db, crud-ms-account-load-fdr  
- **domain-ms-account-load** → psg-mock-router, ui-account-load, fdr-vendor-mock, apigee-mock-gateway, crud-ms-account-load-db, crud-ms-account-load-fdr  
- **fdr-vendor-mock** → psg-mock-router, ui-account-load, domain-ms-account-load, apigee-mock-gateway, crud-ms-account-load-db, crud-ms-account-load-fdr  
- **apigee-mock-gateway** → psg-mock-router, ui-account-load, domain-ms-account-load, fdr-vendor-mock, crud-ms-account-load-db, crud-ms-account-load-fdr  
- **crud-ms-account-load-db** → psg-mock-router, ui-account-load, domain-ms-account-load, fdr-vendor-mock, apigee-mock-gateway, crud-ms-account-load-fdr  
- **crud-ms-account-load-fdr** → psg-mock-router, ui-account-load, domain-ms-account-load, fdr-vendor-mock, apigee-mock-gateway, crud-ms-account-load-db  
"""

    # FULL PREMIUM UI
    return f"""
<!-- PREMIUM IMPACT DASHBOARD -->
# 🚀 Impact Analysis Dashboard  
**PR Title:** _{pr_title}_  
**Generated:** `{datetime.utcnow().isoformat()}Z`

---

## 🧭 Change Summary  
**Files changed:** `{len(changed_files)}`  
**Impacted Services:** `{len(impacted_services)}`  
**Estimated Risk:** {risk_level}

---

## 🗂️ Impacted Microservices  
| Service | Status |
|--------|--------|
{impacted_table}

---

{static_dependencies}

---

## 📊 Detailed Analysis  
<details>
<summary><strong>Click to expand full AI Analysis</strong></summary>

{inner_ai_output}

</details>

---

## 🧠 Engine Metadata
- Knowledge graph computed  
- RAG snippets applied (best effort)  
- Dashboard UI: **Premium Markdown Edition**

---
🏁 _End of Impact Report_
"""


def run_analysis():
    pr_title = os.getenv("PR_TITLE", "(no PR title)")
    base_dir = os.getenv("REPOS_BASE_DIR", ".")
    changed_files = load_changed_files()

    header = f"<!-- Impact Analysis Generated: {datetime.utcnow().isoformat()}Z -->\n"

    if not changed_files:
        return header + "# Impact Analysis Report\nNo changed files detected."

    # 1) Discover microservices
    services = discover_microservices(base_dir)

    # 2) Build microservice dependency graph
    svc_graph = build_service_dependency_graph(services)

    # 3) Knowledge graph
    KG = build_knowledge_graph(svc_graph)
    impacted, edges = impacted_services_from_files(changed_files, services, KG)
    graph_json = knowledge_graph_to_json(KG)

    # 4) RAG retrieval
    try:
        snippets = get_relevant_snippets(
            base_dir, services, impacted, changed_files, max_snippets=12
        )
    except Exception as e:
        snippets = []
        print(f"<!-- RAG retrieval failed: {e} -->")

    # 5) LLM analysis
    try:
        ai_core_output = analyze(
            pr_title, changed_files, impacted, graph_json, snippets
        )
    except Exception as e:
        ai_core_output = (
            f"# Impact Analysis Error\nLLM analysis failed: {e}\n\n```\n"
            f"{traceback.format_exc()}\n```"
        )

    # Wrap AI analysis in Premium Dashboard
    final_comment = premium_dashboard_wrapper(
        pr_title, changed_files, impacted, ai_core_output
    )

    # 6) Write artifact summary
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

    return header + final_comment


if __name__ == "__main__":
    try:
        print(safe_output(run_analysis()))
    except Exception as e:
        print("# Impact Analysis Error")
        print(str(e))
        print("```")
        print(traceback.format_exc())
        print("```")
