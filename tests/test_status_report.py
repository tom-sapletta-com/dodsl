from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("dodsl_status_report", ROOT / "scripts/status_report.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_status_report_keeps_skipped_distinct_from_passed():
    module = _module()
    report = {
        "generatedAt": "2026-08-10T00:00:00+00:00",
        "stages": [
            {"name": "tests", "status": "pass", "detail": "26 passed"},
            {"name": "external-e2e", "status": "skipped", "detail": "not requested"},
        ],
        "nextActions": [],
    }

    rendered = module.render_markdown(report)

    assert "| tests | PASS | 26 passed |" in rendered
    assert "| external-e2e | SKIPPED | not requested |" in rendered


def test_makefile_exposes_one_command_for_local_status():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "report:" in makefile
    assert "scripts/status_report.py" in makefile
    assert '$(REDUP) check packages --ext .py --min-lines 8' in makefile
    assert "timeout=timeout_seconds" in (ROOT / "scripts/status_report.py").read_text(encoding="utf-8")
