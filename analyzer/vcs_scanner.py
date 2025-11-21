# analyzer/vcs_scanner.py
import os
import re
import ast
import json
from typing import Dict, List, Set
from pathlib import PurePosixPath

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


def _parse_openapi_file(path: str) -> dict:
    """Attempt to parse OpenAPI/Swagger JSON or YAML and return a minimal contract shape."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        # try JSON
        try:
            data = json.loads(txt)
        except Exception:
            if yaml:
                try:
                    data = yaml.safe_load(txt)
                except Exception:
                    return {}
            else:
                return {}
        contract = {"paths": {}, "info": {}}
        if isinstance(data, dict):
            contract["info"] = data.get("info", {})
            paths = data.get("paths", {})
            for p, methods in (paths or {}).items():
                contract["paths"][p] = list(methods.keys()) if isinstance(methods, dict) else []
        return contract
    except Exception:
        return {}


def _parse_proto_file(path: str) -> dict:
    """Simple .proto parser to extract service RPC names and messages (best-effort)."""
    svc = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                m = re.match(r"^service\s+(\w+)", line)
                if m:
                    cur = m.group(1)
                    svc.setdefault(cur, [])
                m2 = re.match(r"^\s*rpc\s+(\w+)", line)
                if m2 and cur:
                    svc[cur].append(m2.group(1))
        return {"services": svc}
    except Exception:
        return {}


def _discover_service_contracts(service_root: str) -> dict:
    """Look for openapi/swagger files or .proto files under the service root and return summarized contracts."""
    contracts = {}
    try:
        for root, dirs, files in os.walk(service_root):
            for fn in files:
                fnl = fn.lower()
                path = os.path.join(root, fn)
                if fnl.endswith(('.yaml', '.yml', '.json')) and ('openapi' in fnl or 'swagger' in fnl):
                    c = _parse_openapi_file(path)
                    if c:
                        contracts.setdefault('openapi', []).append({'path': os.path.relpath(path, service_root), 'contract': c})
                elif fnl.endswith('.proto'):
                    c = _parse_proto_file(path)
                    if c:
                        contracts.setdefault('proto', []).append({'path': os.path.relpath(path, service_root), 'contract': c})
    except Exception:
        pass
    return contracts


# Add optional YAML and esprima imports
try:
    import yaml
except Exception:
    yaml = None

try:
    import esprima
except Exception:
    esprima = None


# Enhance extract_dependencies to use esprima for JS/TS when available
def extract_dependencies(file_content: str, filename: str = "") -> List[str]:
    """
    Lightweight static extraction:
    - Python import module roots (via AST)
    - JS/TS import paths (via esprima if available)
    - HTTP URLs
    """
    deps = set()

    # 1) Try Python AST parsing (more accurate than regex)
    try:
        tree = ast.parse(file_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps.add(node.module.split(".")[0])
    except Exception:
        # fallback to original regex-based extraction for non-Python content
        for match in IMPORT_PAT.findall(file_content):
            for m in match:
                if m:
                    deps.add(m.split(".")[0])

    # 2) JS/TS style imports / require
    try:
        if esprima and filename and filename.lower().endswith(('.js', '.ts', '.jsx', '.tsx')):
            # parse JS/TS module and extract import declarations and require() calls
            try:
                tree = esprima.parseModule(file_content, tolerant=True)
                for node in tree.body:
                    if hasattr(node, 'type') and node.type == 'ImportDeclaration':
                        src = node.source.value
                        deps.add(src)
                    # look inside var declarations for require calls (CommonJS)
                    if hasattr(node, 'declarations'):
                        for d in getattr(node, 'declarations'):
                            init = getattr(d, 'init', None)
                            if init and getattr(init, 'type', None) == 'CallExpression' and getattr(init.callee, 'name', '') == 'require':
                                args = getattr(init, 'arguments', [])
                                if args and hasattr(args[0], 'value'):
                                    deps.add(args[0].value)
            except Exception:
                # fall back to regex if esprima parse fails
                for match in JS_IMPORT_PAT.findall(file_content):
                    for m in match:
                        if m and "/" in m:
                            deps.add(m.split("/")[0])
                        elif m:
                            deps.add(m)
        else:
            for match in JS_IMPORT_PAT.findall(file_content):
                for m in match:
                    if m:
                        # prefer path segments (e.g., @org/svc-name or ./lib)
                        if "/" in m:
                            deps.add(m.split("/")[0])
                        else:
                            deps.add(m)
    except Exception:
        pass

    # 3) URLs (could point to services / API hosts)
    for url in URL_PAT.findall(file_content):
        deps.add(url)

    return list(deps)


def _read_manifest_name(service_root: str) -> str:
    """
    Try to read a canonical package name from package.json or pyproject.toml in the service root.
    Return empty string if not found.
    """
    try:
        pj = os.path.join(service_root, "package.json")
        if os.path.exists(pj):
            with open(pj, "r", encoding="utf-8") as f:
                data = json.load(f)
                name = data.get("name") or data.get("package")
                if isinstance(name, str) and name:
                    return name
    except Exception:
        pass
    try:
        py = os.path.join(service_root, "pyproject.toml")
        if os.path.exists(py):
            # simple parse for 'name = "..."' under [tool.poetry] or [project]
            with open(py, "r", encoding="utf-8") as f:
                txt = f.read()
            m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', txt)
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def _build_service_identifiers(base_dir: str, services: Dict[str, List[str]]) -> Dict[str, Set[str]]:
    """
    For each discovered service (folder key), build a set of identifier tokens that
    may appear in imports/urls (e.g., folder name, package.json name, short tokens).
    Returns mapping service_key -> set(identifier strings).
    """
    id_map: Dict[str, Set[str]] = {}
    for svc, files in services.items():
        ids: Set[str] = set()
        ids.add(svc)
        # short tokens from svc (split on -/_)
        for tok in re.split(r"[-_\.]", svc):
            if tok:
                ids.add(tok)
        # try to find service root on disk (first file that contains svc in its path)
        svc_root = None
        for fp in files:
            norm = fp.replace("\\", "/")
            if f"/{svc}/" in norm:
                parts = norm.split(f"/{svc}/", 1)
                svc_root = parts[0] + "/" + svc
                break
        if not svc_root and files:
            # fallback: parent directory of first file up to svc name if present
            fp = files[0]
            if svc in fp:
                idx = fp.index(svc)
                svc_root = fp[: idx + len(svc)]
        if not svc_root:
            svc_root = os.path.join(base_dir or ".", svc)
        manifest_name = _read_manifest_name(svc_root)
        if manifest_name:
            ids.add(manifest_name)
            # add last path segment from manifest (e.g., @org/name -> name)
            if "/" in manifest_name:
                ids.add(manifest_name.split("/")[-1])
        id_map[svc] = ids
    return id_map


def build_service_dependency_graph(services: Dict[str, List[str]]) -> Dict[str, dict]:
    """
    Build a service-level dependency summary:
    { svc: { "files": [...], "deps": {other_svc: count} } }
    """
    graph = {}
    # try to infer base dir from file paths (if any)
    base_dir = "."
    for files in services.values():
        if files:
            try:
                base_dir = os.path.commonpath([base_dir] + files)
            except Exception:
                base_dir = "."
            break
    id_map = _build_service_identifiers(base_dir, services)

    for svc, files in services.items():
        # determine service root for contract discovery
        svc_root = None
        if files:
            for fp in files:
                norm = fp.replace("\\", "/")
                if f"/{svc}/" in norm:
                    svc_root = os.path.join(base_dir, svc)
                    break
        if not svc_root:
            svc_root = os.path.join(base_dir, svc)

        contracts = _discover_service_contracts(svc_root)

        graph[svc] = {"files": files, "deps": {}, "contracts": contracts}
        for fp in files:
            content = read_file_content(fp)
            if not content:
                continue
            deps = extract_dependencies(content, filename=fp)
            for dep in deps:
                for target, idents in id_map.items():
                    if target == svc:
                        continue
                    # match if any identifier token appears in dep (handles folder name, package name, short token)
                    matched = False
                    for ident in idents:
                        if ident and ident in dep:
                            graph[svc]["deps"].setdefault(target, 0)
                            graph[svc]["deps"][target] += 1
                            matched = True
                            break
                    if matched:
                        break
    return graph


def map_file_to_service(base_dir: str, path: str, services: Dict[str, List[str]]) -> str:
    """
    Best-effort map a changed file path to a service name.
    Strategy:
      - Normalize path (handle absolute/relative, Windows separators)
      - Longest matching service folder prefix
      - Fallback: search file content for occurrences of service keys (token match)
    Returns service name or empty string.
    """
    if not path:
        return ""
    # normalize separators
    p = path.replace("\\", "/")
    # if absolute, try to relativize to base_dir
    try:
        base = (base_dir or ".").replace("\\", "/")
        if p.startswith(base):
            rel = p[len(base):].lstrip("/").lstrip("./")
        else:
            rel = p.lstrip("./")
    except Exception:
        rel = p

    # find longest matching prefix service (svc/)
    best = ("", -1)
    for svc in services.keys():
        svc_prefix = svc.rstrip("/") + "/"
        if rel.startswith(svc_prefix) and len(svc_prefix) > best[1]:
            best = (svc, len(svc_prefix))
    if best[0]:
        return best[0]

    # last-resort: check token occurrences in path parts
    parts = PurePosixPath(rel).parts
    for svc in services.keys():
        if svc in parts:
            return svc

    # fallback: inspect file content for service name tokens
    full = path if os.path.isabs(path) else os.path.join(base_dir or ".", path)
    try:
        content = read_file_content(full)
        if content:
            for svc in services.keys():
                # token match (avoid accidental substrings)
                if re.search(rf"\b{re.escape(svc)}\b", content):
                    return svc
    except Exception:
        pass

    return ""


def get_changed_file_hunk(base_dir: str, path: str, context_lines: int = 5) -> dict:
    """Return a best-effort hunk (with line numbers) for a changed file.
    Returns {'file': rel_path, 'start_line': 1, 'end_line': n, 'snippet': text}
    """
    try:
        full = path if os.path.isabs(path) else os.path.join(base_dir or ".", path)
        with open(full, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        total = len(lines)
        # provide the whole file as a single hunk for now, with line ranges
        snippet = "".join(lines[:])
        rel = os.path.relpath(full, base_dir) if base_dir else path
        return {"file": rel.replace('\\\\', '/'), "start_line": 1, "end_line": total, "snippet": snippet}
    except Exception:
        return {"file": path, "start_line": 0, "end_line": 0, "snippet": ""}


def extract_contract_references(file_content: str, contracts: dict) -> list:
    """Scan file content for any references to contract paths or proto service/rpc names.
    Returns list of matched contract items like {'type':'openapi','path':'/items','service':'svc-a'}
    """
    matches = []
    try:
        # openapi paths
        for k, v in (contracts or {}).items():
            if k == 'openapi':
                for entry in v:
                    c = entry.get('contract', {})
                    for p in c.get('paths', {}).keys():
                        if p and p in file_content:
                            matches.append({'type': 'openapi', 'path': p, 'contract_file': entry.get('path')})
            if k == 'proto':
                for entry in v:
                    c = entry.get('contract', {})
                    for svc, rpcs in c.get('services', {}).items():
                        if svc and svc in file_content:
                            matches.append({'type': 'proto_service', 'service': svc, 'contract_file': entry.get('path')})
                        for rpc in rpcs:
                            if rpc and rpc in file_content:
                                matches.append({'type': 'proto_rpc', 'rpc': rpc, 'contract_file': entry.get('path')})
    except Exception:
        pass
    return matches
