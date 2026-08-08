from __future__ import annotations

import json

from dodsl.knowledge.intent_compile import COMPILER_ID, compile_tree


def test_local_evidence_compiler_is_deterministic_and_source_anchored(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "device.md").write_text("# Device\n\nMeasured width is 42 mm.\n", encoding="utf-8")

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_report = compile_tree(source, first, only_english=False)
    second_report = compile_tree(source, second, only_english=False)

    assert first_report["compiler"] == COMPILER_ID
    assert first_report["files"] == second_report["files"] == 1
    first_pack = json.loads((first / "device.md.intent.json").read_text(encoding="utf-8"))
    second_pack = json.loads((second / "device.md.intent.json").read_text(encoding="utf-8"))
    assert first_pack == second_pack
    record = first_pack["records"][0]
    assert record["type"] == "claim"
    assert record["source"]["artifactUri"] == "subactor://markdown/device.md"
