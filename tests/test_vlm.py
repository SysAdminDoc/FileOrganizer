from __future__ import annotations

import io
import json
import subprocess

import asset_db
import classify_design
import vlm_run
from fileorganizer import vlm
from fileorganizer.sidecar_protocol import SidecarEmitter


def test_parse_classification_accepts_thinking_and_fenced_json():
    result = vlm.parse_classification(
        '<think>check the visible title</think>\n```json\n'
        '{"category":"Print - Flyers & Posters","confidence":88,'
        '"description":"A title card","ocr_text":"SUMMER SALE",'
        '"requires_ocr":true,"has_text_overlay":true}\n```',
        model="Qwen2.5-VL-7B",
        allowed_categories=["Print - Flyers & Posters"],
    )

    assert result.category == "Print - Flyers & Posters"
    assert result.confidence == 88
    assert result.ocr_text == "SUMMER SALE"
    assert result.requires_ocr is True
    assert result.has_text_overlay is True


def test_parse_classification_rejects_untrusted_fields():
    for raw in (
        '{"category":"Unknown","confidence":88}',
        '{"category":"Print","confidence":101}',
        '{"category":"Print","confidence":88,"requires_ocr":"yes"}',
    ):
        try:
            vlm.parse_classification(
                raw,
                model="test",
                allowed_categories=["Print"],
            )
        except vlm.VlmResponseError:
            pass
        else:
            raise AssertionError("invalid VLM response was accepted")


def test_run_cli_builds_hidden_qwen_command(tmp_path, monkeypatch):
    image = tmp_path / "poster.png"
    model = tmp_path / "qwen.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    image.write_bytes(b"image")
    model.write_bytes(b"model")
    mmproj.write_bytes(b"projector")
    captured: dict[str, object] = {}

    monkeypatch.setattr(vlm, "find_cli", lambda _explicit=None: "fake-qwen-cli")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, '{"category":"Print","confidence":80}', "")

    monkeypatch.setattr(vlm.subprocess, "run", fake_run)
    output = vlm.run_cli(
        image,
        model_path=model,
        mmproj_path=mmproj,
        prompt="Return JSON",
        context_size=4096,
        max_tokens=128,
    )

    command = captured["command"]
    assert output.startswith('{"category"')
    assert isinstance(command, list)
    assert "--mmproj" in command and str(mmproj) in command
    assert "--image" in command and str(image) in command
    assert "--ctx-size" in command and "4096" in command
    if vlm.os.name == "nt":
        assert "creationflags" in captured["kwargs"]


def test_asset_db_persists_vlm_evidence(tmp_path):
    db_path = tmp_path / "assets.db"
    con = asset_db.init_db(str(db_path))
    con.execute(
        "INSERT INTO assets (clean_name, category, folder_fingerprint, added_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Poster", "_Review", "fingerprint", "2026-08-10T00:00:00Z", "2026-08-10T00:00:00Z"),
    )
    con.commit()
    asset_id = con.execute("SELECT id FROM assets").fetchone()[0]
    con.close()

    asset_db.update_vlm_record(
        asset_id,
        ocr_text="SUMMER SALE",
        vmodel_used="Qwen2.5-VL-7B",
        category="Print",
        confidence=91,
        db_path=str(db_path),
    )

    con = asset_db.init_db(str(db_path))
    row = con.execute(
        "SELECT ocr_text, vmodel_used, category, confidence FROM assets WHERE id = ?",
        (asset_id,),
    ).fetchone()
    con.close()
    assert tuple(row) == ("SUMMER SALE", "Qwen2.5-VL-7B", "Print", 91)


def test_vlm_sidecar_fails_closed_when_cli_capability_is_missing(tmp_path, monkeypatch):
    image = tmp_path / "poster.png"
    image.write_bytes(b"image")
    model = tmp_path / "qwen.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    model.write_bytes(b"model")
    mmproj.write_bytes(b"projector")
    stream = io.StringIO()
    monkeypatch.setattr(
        vlm_run,
        "_PROTOCOL",
        SidecarEmitter("vlm", stream=stream),
    )
    monkeypatch.setattr(
        vlm_run,
        "get_capability",
        lambda *_args: {"status": "unavailable"},
    )

    result = vlm_run.main([
        "--file", str(image), "--model", str(model), "--mmproj", str(mmproj),
    ])

    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert result == 3
    assert rows[-1]["event"] == "error"
    assert rows[-1]["code"] == "capability_unavailable"
    assert rows[-1]["terminal"] is True


def test_design_vision_stage_falls_back_to_configured_qwen(tmp_path, monkeypatch):
    image = tmp_path / "diagram.png"
    image.write_bytes(b"image")
    monkeypatch.setenv("FILEORGANIZER_QWEN_MODEL", str(tmp_path / "qwen.gguf"))
    monkeypatch.setenv("FILEORGANIZER_QWEN_MMPROJ", str(tmp_path / "mmproj.gguf"))
    monkeypatch.setattr(
        classify_design,
        "get_runtime_categories",
        lambda: ["Print - Flyers & Posters"],
    )
    from fileorganizer import ollama

    monkeypatch.setattr(ollama, "ollama_classify_visual", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        vlm,
        "classify_qwen",
        lambda *_args, **_kwargs: vlm.VlmClassification(
            category="Print - Flyers & Posters",
            confidence=86,
            description="A labeled diagram",
            ocr_text="PROCESS",
            requires_ocr=True,
            has_text_overlay=True,
            model="Qwen2.5-VL-7B",
        ),
    )

    result = classify_design._try_vision_classify([{
        "name": "diagram.png",
        "path": str(image),
        "is_file": True,
        "file_ext": ".png",
    }])

    assert result[0]["_classifier"] == "vlm"
    assert result[0]["metadata"]["ocr_text"] == "PROCESS"
    assert result[0]["confidence"] == 86
