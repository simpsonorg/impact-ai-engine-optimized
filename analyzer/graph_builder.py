# analyzer/graph_builder.py
import networkx as nx
from typing import Dict, List, Tuple
import os


def build_knowledge_graph(service_graph: Dict[str, dict]) -> nx.DiGraph:
    """
    Convert the service-level graph to a NetworkX directed graph.
    Nodes: service names
    Edges: svc -> dep (weight = number of occurrences)
    """
    G = nx.DiGraph()
    for svc, data in service_graph.items():
        if svc not in G:
            G.add_node(svc, type="service", file_count=len(data.get("files", [])))
        for dep, count in data.get("deps", {}).items():
            if dep not in G:
                G.add_node(dep, type="service", file_count=0)
            G.add_edge(svc, dep, weight=count)
    return G


def impacted_services_from_files(changed_files: List[str], services: Dict[str, List[str]], G: nx.DiGraph) -> Tuple[List[str], List[dict]]:
    """
    Map changed file paths to service names, then BFS to find impacted downstream services.
    Returns: (impacted_services_sorted, edges_list)
    """
    start_services = set()
    # map by path prefix: if changed path starts with service folder
    for cf in changed_files:
        cf_norm = cf.replace("\\", "/")
        for svc in services.keys():
            if cf_norm.startswith(svc + "/") or cf_norm.startswith("./" + svc + "/") or f"/{svc}/" in cf_norm:
                start_services.add(svc)
    # fallback: if none matched, pick first service (conservative)
    if not start_services:
        if len(services) > 0:
            start_services.add(list(services.keys())[0])

    impacted = set()
    edges = []
    for s in start_services:
        if s not in G:
            continue
        impacted.add(s)
        for u, v, d in nx.bfs_edges(G, s, data=True):
            impacted.add(v)
            edges.append({"from": u, "to": v, "attr": d})
    return sorted(list(impacted)), edges


def knowledge_graph_to_json(G: nx.DiGraph) -> dict:
    nodes = []
    edges = []
    for n, a in G.nodes(data=True):
        nodes.append({"id": n, "attr": a})
    for u, v, a in G.edges(data=True):
        edges.append({"from": u, "to": v, "attr": a})
    return {"nodes": nodes, "edges": edges}
