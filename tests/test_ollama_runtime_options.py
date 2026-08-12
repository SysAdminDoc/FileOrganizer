import json
import urllib.request

from fileorganizer import ollama


def test_runtime_options_omit_auto_gpu_and_thread_defaults():
    options = ollama.build_ollama_options({
        'temperature': 0.4,
        'num_predict': 2048,
        'num_gpu': -1,
        'num_thread': 0,
    })

    assert options == {'temperature': 0.4, 'num_predict': 2048}


def test_runtime_options_include_explicit_gpu_and_thread_controls():
    options = ollama.build_ollama_options({
        'temperature': 9,
        'num_predict': 'bad',
        'num_gpu': 22,
        'num_thread': 12,
    })

    assert options == {
        'temperature': 2.0,
        'num_predict': 4096,
        'num_gpu': 22,
        'num_thread': 12,
    }


def test_ollama_generate_forwards_runtime_options(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json.dumps({'message': {'content': 'ok'}}).encode()

    monkeypatch.setattr(ollama, 'load_ollama_settings', lambda: {
        'url': 'http://localhost:11434', 'model': 'model-a', 'timeout': 5,
        'temperature': 0.2, 'num_predict': 256, 'num_gpu': 18, 'num_thread': 6,
        'think': False,
    })

    def fake_urlopen(request, timeout):
        captured['payload'] = json.loads(request.data.decode())
        captured['timeout'] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    assert ollama._ollama_generate('prompt') == 'ok'
    assert captured['payload']['options'] == {
        'temperature': 0.2, 'num_predict': 256, 'num_gpu': 18, 'num_thread': 6,
    }
    assert captured['timeout'] == 120


def test_benchmark_reports_eval_tokens_per_second(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json.dumps({
                'eval_count': 40,
                'eval_duration': 2_000_000_000,
            }).encode()

    monkeypatch.setattr(ollama, 'load_ollama_settings', lambda: {
        **ollama._OLLAMA_DEFAULTS,
        'url': 'http://localhost:11434', 'model': 'model-a',
        'quantization': 'Q5',
    })
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *_args, **_kwargs: FakeResponse())

    result = ollama.benchmark_ollama_speed()

    assert result['ok'] is True
    assert result['tokens_per_second'] == 20.0
    assert result['quantization'] == 'Q5'
