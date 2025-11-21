import os
from run_analysis import run_analysis
from analyzer.vcs_scanner import discover_microservices, build_service_dependency_graph
from analyzer.graph_builder import build_knowledge_graph, knowledge_graph_to_json


def test_graph_metrics_tmp(tmp_path, monkeypatch):
    # create minimal repo with two services like existing test
    svc_a = tmp_path / "svc-a"
    svc_b = tmp_path / "svc-b"
    svc_a.mkdir()
    svc_b.mkdir()
    file_a = svc_a / "app.py"
    file_a.write_text("import svc_b\n")
    file_b = svc_b / "handler.py"
    file_b.write_text("def handler():\n    pass\n")
    monkeypatch.setenv("REPOS_BASE_DIR", str(tmp_path))
    # discover and build graph directly
    services = discover_microservices(str(tmp_path))
    svc_graph = build_service_dependency_graph(services)
    G = build_knowledge_graph(svc_graph)
    gj = knowledge_graph_to_json(G)
    # assert nodes have enrichment fields
    found = False
    for n in gj.get("nodes", []):
        attr = n.get("attr", {})
        if "pagerank" in attr and "downstream_count" in attr and "betweenness" in attr:
            found = True
            break
    assert found, "Graph enrichment metrics missing"
