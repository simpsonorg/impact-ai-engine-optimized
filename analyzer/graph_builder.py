# analyzer/graph_builder.py
import networkx as nx
from typing import Dict, List, Tuple
import os
from analyzer.vcs_scanner import map_file_to_service


# include contracts attached in service graph into node attrs when building knowledge graph
def build_knowledge_graph(service_graph: Dict[str, dict]) -> nx.DiGraph:
    """
    Convert the service-level graph to a NetworkX directed graph.
    Nodes: service names
    Edges: svc -> dep (weight = number of occurrences)
    """
    G = nx.DiGraph()
    for svc, data in service_graph.items():
        if svc not in G:
            node_attr = {"type": "service", "file_count": len(data.get("files", []))}
            # attach contracts if present
            if data.get("contracts"):
                node_attr["contracts"] = data.get("contracts")
            G.add_node(svc, **node_attr)
        for dep, count in data.get("deps", {}).items():
            if dep not in G:
                G.add_node(dep, type="service", file_count=0)
            G.add_edge(svc, dep, weight=count)

    # Enrich graph with metrics to help prioritize impact (pagerank, centrality, downstream count)
    try:
        enrich_graph_with_metrics(G)
    except Exception:
        # Do not fail if metrics cannot be computed
        pass

    return G


def impacted_services_from_files(changed_files: List[str], services: Dict[str, List[str]], G: nx.DiGraph) -> Tuple[List[str], List[dict]]:
    """
    Map changed file paths to service names, then BFS to find impacted downstream services.
    Returns: (impacted_services_sorted, edges_list)
    """
    start_services = set()
    # Prefer robust mapping via map_file_to_service
    for cf in changed_files:
        svc = map_file_to_service(os.getcwd(), cf, services)
        if svc:
            start_services.add(svc)
            continue
        # older heuristics fallback (preserve existing behavior)
        cf_norm = cf.replace("\\", "/")
        for svc in services.keys():
            if cf_norm.startswith(svc + "/") or cf_norm.startswith("./" + svc + "/") or f"/{svc}/" in cf_norm:
                start_services.add(svc)
                break
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
        # Use bfs_edges without the 'data' kw to maintain compatibility with different networkx versions
        for u, v in nx.bfs_edges(G, s):
            impacted.add(v)
            edge_attr = G.get_edge_data(u, v) or {}
            edges.append({"from": u, "to": v, "attr": edge_attr})
    return sorted(list(impacted)), edges


def knowledge_graph_to_json(G: nx.DiGraph) -> dict:
    nodes = []
    edges = []
    for n, a in G.nodes(data=True):
        nodes.append({"id": n, "attr": a})
    for u, v, a in G.edges(data=True):
        edges.append({"from": u, "to": v, "attr": a})
    return {"nodes": nodes, "edges": edges}


# New helper: compute pagerank, degree centrality, and downstream counts
def enrich_graph_with_metrics(G: nx.DiGraph) -> None:
    """
    Annotate nodes with 'pagerank', 'centrality', 'downstream_count', 'betweenness', 'scc_size'.
    Non-fatal: swallow exceptions so existing behavior stays intact.
    """
    if G is None or G.number_of_nodes() == 0:
        return
    try:
        pr = nx.pagerank(G)
    except Exception:
        pr = {}
    try:
        deg = nx.degree_centrality(G)
    except Exception:
        deg = {}
    try:
        btw = nx.betweenness_centrality(G)
    except Exception:
        btw = {}
    # strongly connected components sizes
    try:
        sccs = list(nx.strongly_connected_components(G))
        node_scc_size = {}
        for comp in sccs:
            for n in comp:
                node_scc_size[n] = len(comp)
    except Exception:
        node_scc_size = {}

    for n in G.nodes():
        G.nodes[n]["pagerank"] = float(pr.get(n, 0.0))
        G.nodes[n]["centrality"] = float(deg.get(n, 0.0))
        G.nodes[n]["betweenness"] = float(btw.get(n, 0.0))
        G.nodes[n]["scc_size"] = int(node_scc_size.get(n, 1))
        try:
            G.nodes[n]["downstream_count"] = len(nx.descendants(G, n))
        except Exception:
            G.nodes[n]["downstream_count"] = 0
    # normalize edge weights to be more comparable
    try:
        max_w = 0.0
        for _, _, a in G.edges(data=True):
            w = a.get("weight", 1)
            if isinstance(w, (int, float)) and w > max_w:
                max_w = float(w)
        if max_w > 0:
            for u, v, a in G.edges(data=True):
                a["normalized_weight"] = float(a.get("weight", 1)) / max_w
    except Exception:
        pass
