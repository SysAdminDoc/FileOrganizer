from pathlib import Path

from fileorganizer import ollama, workers


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_startup_setup_contains_no_implicit_installer_or_model_download():
    source = (REPO_ROOT / "fileorganizer/workers.py").read_text(encoding="utf-8")

    assert "OllamaSetup.exe" not in source
    assert "urlretrieve" not in source
    assert "curl -fsSL" not in source
    assert "pull automatically" not in source.lower()


def test_setup_reports_missing_binary_without_installing(monkeypatch):
    worker = workers.OllamaSetupWorker(model="model-a", url="http://localhost:11434")
    logs = []
    statuses = []
    worker.log.connect(logs.append)
    worker.status.connect(statuses.append)
    monkeypatch.setattr(workers, "_find_ollama_binary", lambda: "")

    worker._setup()

    assert any("not found" in message.lower() for message in logs)
    assert statuses == ["LLM: install Ollama manually"]


def test_missing_model_does_not_trigger_an_implicit_pull(monkeypatch):
    worker = workers.ScanFilesLLMWorker(
        src_dir=".",
        dst_dir=".",
        categories=[],
    )
    monkeypatch.setattr(workers, "_is_ollama_server_running", lambda _url: True)
    monkeypatch.setattr(workers, "_ollama_has_model", lambda _model, _url: False)

    def fail_pull(*_args, **_kwargs):
        raise AssertionError("implicit model pull called")

    monkeypatch.setattr(workers, "_ollama_pull_model_streaming", fail_pull)

    assert not worker._ensure_ollama_ready(
        {"url": "http://localhost:11434", "model": "model-a"}
    )


def test_model_router_never_downloads_when_no_task_model_is_installed(monkeypatch):
    monkeypatch.setattr(
        ollama.ModelRouter,
        "_installed",
        classmethod(lambda _cls, _url=None: []),
    )

    def fail_pull(*_args, **_kwargs):
        raise AssertionError("implicit model pull called")

    monkeypatch.setattr(ollama, "_ollama_pull_model_streaming", fail_pull)
    logs = []

    result = ollama.ModelRouter.get_model(
        "text_classify",
        url="http://localhost:11434",
        log_cb=logs.append,
        auto_pull=True,
    )

    assert result == ollama.load_ollama_settings().get("model", "")
    assert any("download" in message.lower() for message in logs)
