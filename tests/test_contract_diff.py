import os
from analyzer.vcs_scanner import _parse_openapi_file, _parse_proto_file, _discover_service_contracts


def test_parse_openapi(tmp_path):
    svc = tmp_path / "svc-a"
    svc.mkdir()
    openapi = svc / "openapi.json"
    openapi.write_text('{"openapi":"3.0.0","info":{},"paths":{"/items":{"get":{}}}}')
    contracts = _discover_service_contracts(str(svc))
    assert 'openapi' in contracts


def test_parse_proto(tmp_path):
    svc = tmp_path / "svc-b"
    svc.mkdir()
    proto = svc / "service.proto"
    proto.write_text('''service MyService {\n  rpc DoThing (Request) returns (Response);\n}\n''')
    contracts = _discover_service_contracts(str(svc))
    assert 'proto' in contracts
