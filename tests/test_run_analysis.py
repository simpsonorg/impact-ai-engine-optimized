import os
from pathlib import Path
from run_analysis import run_analysis


def test_basic_analysis(tmp_path, monkeypatch):
    # Create minimal repo with two services
    svc_a = tmp_path / "svc-a"
    svc_b = tmp_path / "svc-b"
    svc_a.mkdir()
    svc_b.mkdir()

    file_a = svc_a / "app.py"
    file_a.write_text("import svc_b\n\ndef handler():\n    pass\n")

    file_b = svc_b / "handler.py"
    file_b.write_text("def handler():\n    pass\n")

    # Configure environment for run_analysis
    monkeypatch.setenv("REPOS_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("CHANGED_FILES", os.path.relpath(str(file_a), start=str(tmp_path)))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    out = run_analysis()
    assert isinstance(out, str)
    assert ("Impact Analysis" in out) or ("Impact Analysis Dashboard" in out) or ("Impacted Services" in out)
    assert "svc-a" in out
