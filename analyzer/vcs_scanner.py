# analyzer/vcs_scanner.py
import os
import re
from typing import Dict, List

SOURCE_EXTENSIONS = (".py", ".ts", ".js", ".json", ".yml", ".yaml", ".html", ".jsx", ".tsx")
SERVICE_PREFIXES = ("ui-", "crud-", "domain-", "fdr-", "psg-", "apigee-", "svc-")

IMPORT_PAT = re.compile(r"from\s+([\w_\.]+)\s+import|import\s+([\w_\.]+)")
JS_IMPORT_PAT = re.compile(r"from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)")
URL_PAT = re.compile(r"https?://[^\s'\"<>]+")


def read_file_content(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def discover_microservices(base_dir: str) -> Dict[str, List[str]]:
    """
    Discover top-level folders that look like microservices and collect their source files.
    Returns: { service_name: [file_paths...] }
    """
    services = {}
    for entry in sorted(os.listdir(base_dir)):
        full_path = os.path.join(base_dir, entry)
        if not os.path.isdir(full_path):
            continue
        if not any(entry.startswith(p) for p in SERVICE_PREFIXES):
            continue
        files = []
        for root, _, fs in os.walk(full_path):
            for f in fs:
                if f.endswith(SOURCE_EXTENSIONS):
                    files.append(os.path.join(root, f))
        services[entry] = files
    return services


def extract_dependencies(file_content: str) -> List[str]:
    """
    Lightweight static extraction:
    - Python import module roots
    - JS/TS import paths
    - HTTP URLs
    """
    deps = set()

    for match in IMPORT_PAT.findall(file_content):
        for m in match:
            if m:
                deps.add(m.split(".")[0])

    for match in JS_IMPORT_PAT.findall(file_content):
        for m in match:
            if m and "/" in m:
                deps.add(m.split("/")[0])

    for url in URL_PAT.findall(file_content):
        deps.add(url)

    return list(deps)


def build_service_dependency_graph(services: Dict[str, List[str]]) -> Dict[str, dict]:
    """
    Build a service-level dependency summary:
    { svc: { "files": [...], "deps": {other_svc: count} } }
    """
    graph = {}
    for svc, files in services.items():
        graph[svc] = {"files": files, "deps": {}}
        for fp in files:
            content = read_file_content(fp)
            if not content:
                continue
            deps = extract_dependencies(content)
            for dep in deps:
                for target in services.keys():
                    # simple substring match; good heuristic for microservice hostnames/folders
                    if target in dep and target != svc:
                        graph[svc]["deps"].setdefault(target, 0)
                        graph[svc]["deps"][target] += 1
    return graph
