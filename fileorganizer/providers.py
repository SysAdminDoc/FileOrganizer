"""FileOrganizer — Multi-provider AI system: GitHub Models (Claude), DeepSeek, Ollama.

Provider routing:
  Lightweight (name cleanup, category refinement) → GitHubModelsProvider
  Heavy (catalog lookup, batch classification, dynamic categories) → DeepSeekProvider
  Fallback / offline → OllamaProvider (existing)
"""
import os, re, json, time, logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Provider settings ──────────────────────────────────────────────────────────
from fileorganizer.config import _APP_DATA_DIR

_PROVIDER_SETTINGS_FILE = os.path.join(_APP_DATA_DIR, 'provider_settings.json')

_PROVIDER_DEFAULTS = {
    # GitHub Models
    'github_enabled': False,
    'github_token': '',          # GITHUB_TOKEN env var takes precedence
    'github_endpoint': 'https://models.github.ai/inference',
    'github_model': 'Anthropic/claude-3-5-sonnet-20241022',
    'github_timeout': 60,
    # DeepSeek
    'deepseek_enabled': False,
    'deepseek_api_key': '',      # DEEPSEEK_API_KEY env var takes precedence
    'deepseek_endpoint': 'https://api.deepseek.com',
    'deepseek_model': 'deepseek-chat',
    'deepseek_timeout': 120,
    # Routing
    'routing': 'auto',  # auto | github_only | deepseek_only | ollama_only
    'lightweight_provider': 'github',   # github | deepseek | ollama
    'heavy_provider': 'deepseek',       # deepseek | github | ollama
    'catalog_provider': 'deepseek',     # deepseek | github
    'fallback_to_ollama': True,
}

_GITHUB_MODEL_CATALOG = [
    {
        'group': 'Anthropic Claude (Recommended)',
        'name': 'Anthropic/claude-3-5-sonnet-20241022',
        'label': 'Claude 3.5 Sonnet  ·  Best balance  ·  200K ctx',
        'description': 'Best accuracy for name cleanup and category refinement.',
    },
    {
        'group': 'Anthropic Claude (Recommended)',
        'name': 'Anthropic/claude-3-7-sonnet-20250219',
        'label': 'Claude 3.7 Sonnet  ·  Latest  ·  200K ctx',
        'description': 'Highest accuracy. Best for complex classification.',
    },
    {
        'group': 'Anthropic Claude',
        'name': 'Anthropic/claude-3-5-haiku-20241022',
        'label': 'Claude 3.5 Haiku  ·  Fastest  ·  200K ctx',
        'description': 'Best for high-volume lightweight passes.',
    },
    {
        'group': 'OpenAI',
        'name': 'openai/gpt-4o',
        'label': 'GPT-4o  ·  Strong  ·  128K ctx',
        'description': 'Solid all-rounder with good JSON reliability.',
    },
    {
        'group': 'OpenAI',
        'name': 'openai/gpt-4o-mini',
        'label': 'GPT-4o Mini  ·  Fast + cheap  ·  128K ctx',
        'description': 'High volume, cost-efficient classification.',
    },
    {
        'group': 'Meta Llama',
        'name': 'meta/meta-llama-3.3-70b-instruct',
        'label': 'Llama 3.3 70B  ·  Open weights  ·  128K ctx',
        'description': 'Strong open-weight model. Good category accuracy.',
    },
]

_DEEPSEEK_MODEL_CATALOG = [
    {
        'group': 'DeepSeek Chat (Recommended)',
        'name': 'deepseek-chat',
        'label': 'DeepSeek Chat  ·  Fast + affordable  ·  Best for catalog lookup',
        'description': 'Best cost/performance. Ideal for batch classification and catalog ID.',
    },
    {
        'group': 'DeepSeek Reasoner',
        'name': 'deepseek-reasoner',
        'label': 'DeepSeek Reasoner (R1)  ·  Max accuracy  ·  Slower',
        'description': 'Chain-of-thought reasoning. Use for ambiguous or complex items.',
    },
]


def load_provider_settings() -> dict:
    try:
        with open(_PROVIDER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            stored = json.load(f)
        return {**_PROVIDER_DEFAULTS, **stored}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return dict(_PROVIDER_DEFAULTS)


def save_provider_settings(settings: dict):
    try:
        with open(_PROVIDER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        log.warning("Could not save provider settings: %s", e)


# ── Base provider ──────────────────────────────────────────────────────────────

class AIProvider:
    """Abstract base for AI providers."""
    name = 'base'

    def is_available(self) -> bool:
        return False

    def classify(self, prompt: str, system: str = '', timeout: int = 60,
                 temperature: float = 0.1, max_tokens: int = 1024) -> Optional[str]:
        raise NotImplementedError

    def classify_batch(self, items: list, system: str = '', timeout: int = 120,
                       temperature: float = 0.1, max_tokens: int = 4096) -> Optional[str]:
        raise NotImplementedError

    def test_connection(self) -> tuple:
        """Returns (success: bool, message: str)."""
        return (False, "Not implemented")


# ── OpenAI-compatible provider base ───────────────────────────────────────────

class _OpenAICompatProvider(AIProvider):
    """Base for OpenAI-SDK-compatible providers (GitHub Models, DeepSeek)."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
            except ImportError:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def classify(self, prompt: str, system: str = '', timeout: int = 0,
                 temperature: float = 0.1, max_tokens: int = 1024) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            client = self._get_client()
            messages = []
            if system:
                messages.append({'role': 'system', 'content': system})
            messages.append({'role': 'user', 'content': prompt})
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout or self.timeout,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning("%s classify error: %s", self.name, e)
            return None

    def classify_batch(self, items: list, system: str = '', timeout: int = 0,
                       temperature: float = 0.1, max_tokens: int = 4096) -> Optional[str]:
        """Send a multi-item batch prompt; returns raw response string."""
        if not self.is_available():
            return None
        if not items:
            return None
        try:
            client = self._get_client()
            prompt = _build_batch_prompt(items)
            messages = []
            if system:
                messages.append({'role': 'system', 'content': system})
            messages.append({'role': 'user', 'content': prompt})
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout or self.timeout,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning("%s batch error: %s", self.name, e)
            return None

    def test_connection(self) -> tuple:
        if not self.api_key:
            return (False, "No API key configured.")
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': 'Reply with just the word OK.'}],
                max_tokens=10,
                timeout=15,
            )
            reply = resp.choices[0].message.content.strip()
            return (True, f"Connected. Reply: {reply!r}")
        except Exception as e:
            return (False, str(e))


# ── GitHub Models provider ─────────────────────────────────────────────────────

class GitHubModelsProvider(_OpenAICompatProvider):
    """GitHub Models marketplace — Claude, GPT-4o, Llama via GitHub PAT."""
    name = 'github'

    def __init__(self, settings: dict):
        token = (os.environ.get('GITHUB_TOKEN', '')
                 or settings.get('github_token', ''))
        super().__init__(
            base_url=settings.get('github_endpoint', _PROVIDER_DEFAULTS['github_endpoint']),
            api_key=token,
            model=settings.get('github_model', _PROVIDER_DEFAULTS['github_model']),
            timeout=settings.get('github_timeout', 60),
        )

    def is_available(self) -> bool:
        # Also accept legacy Azure inference endpoint
        return bool(self.api_key) and bool(self.model)


# ── DeepSeek provider ──────────────────────────────────────────────────────────

class DeepSeekProvider(_OpenAICompatProvider):
    """DeepSeek API — heavy batch classification and catalog lookup."""
    name = 'deepseek'

    def __init__(self, settings: dict):
        key = (os.environ.get('DEEPSEEK_API_KEY', '')
               or settings.get('deepseek_api_key', ''))
        super().__init__(
            base_url=settings.get('deepseek_endpoint', _PROVIDER_DEFAULTS['deepseek_endpoint']),
            api_key=key,
            model=settings.get('deepseek_model', _PROVIDER_DEFAULTS['deepseek_model']),
            timeout=settings.get('deepseek_timeout', 120),
        )


# ── Ollama provider wrapper ────────────────────────────────────────────────────

class OllamaProvider(AIProvider):
    """Wraps existing Ollama integration as a provider."""
    name = 'ollama'

    def is_available(self) -> bool:
        try:
            from fileorganizer.ollama import _is_ollama_server_running
            return _is_ollama_server_running()
        except Exception:
            return False

    def classify(self, prompt: str, system: str = '', timeout: int = 0,
                 temperature: float = 0.1, max_tokens: int = 1024) -> Optional[str]:
        try:
            from fileorganizer.ollama import _ollama_chat_raw, load_ollama_settings
            s = load_ollama_settings()
            return _ollama_chat_raw(
                prompt=prompt,
                system=system,
                model=s['model'],
                temperature=s.get('temperature', 0.1),
                num_predict=max_tokens or s.get('num_predict', 2048),
                timeout=timeout or s.get('timeout', 120),
            )
        except Exception as e:
            log.warning("Ollama classify error: %s", e)
            return None

    def classify_batch(self, items: list, system: str = '', timeout: int = 0,
                       temperature: float = 0.1, max_tokens: int = 4096) -> Optional[str]:
        try:
            from fileorganizer.ollama import ollama_classify_batch, load_ollama_settings
            s = load_ollama_settings()
            return ollama_classify_batch(items, s)
        except Exception as e:
            log.warning("Ollama batch error: %s", e)
            return None

    def test_connection(self) -> tuple:
        try:
            from fileorganizer.ollama import _is_ollama_server_running, ollama_test_connection
            if not _is_ollama_server_running():
                return (False, "Ollama server not running.")
            return ollama_test_connection()
        except Exception as e:
            return (False, str(e))


# ── Provider router ────────────────────────────────────────────────────────────

class ProviderRouter:
    """Routes classification tasks to the appropriate provider based on task type.

    Task types:
      'lightweight' — name cleanup, single-item refine, confidence boost
      'heavy'       — batch classification, complex/ambiguous items
      'catalog'     — marketplace catalog lookup (requires DeepSeek knowledge)
    """

    def __init__(self, settings: Optional[dict] = None):
        if settings is None:
            settings = load_provider_settings()
        self._settings = settings
        self._github = GitHubModelsProvider(settings) if settings.get('github_enabled') else None
        self._deepseek = DeepSeekProvider(settings) if settings.get('deepseek_enabled') else None
        self._ollama = OllamaProvider()

    def reload(self):
        """Re-read settings from disk."""
        self._settings = load_provider_settings()
        self._github = GitHubModelsProvider(self._settings) if self._settings.get('github_enabled') else None
        self._deepseek = DeepSeekProvider(self._settings) if self._settings.get('deepseek_enabled') else None

    def _resolve(self, task_type: str) -> list:
        """Return ordered provider list for a task type."""
        s = self._settings
        routing = s.get('routing', 'auto')

        if routing == 'ollama_only':
            return [self._ollama]
        if routing == 'github_only':
            return [p for p in [self._github, self._ollama] if p]
        if routing == 'deepseek_only':
            return [p for p in [self._deepseek, self._ollama] if p]

        # auto routing
        if task_type == 'catalog':
            preferred = s.get('catalog_provider', 'deepseek')
        elif task_type == 'heavy':
            preferred = s.get('heavy_provider', 'deepseek')
        else:  # lightweight
            preferred = s.get('lightweight_provider', 'github')

        order = []
        if preferred == 'deepseek' and self._deepseek:
            order.append(self._deepseek)
        if preferred == 'github' and self._github:
            order.append(self._github)

        # Add the other cloud provider as secondary
        if self._deepseek and self._deepseek not in order:
            order.append(self._deepseek)
        if self._github and self._github not in order:
            order.append(self._github)

        # Ollama fallback
        if s.get('fallback_to_ollama', True):
            order.append(self._ollama)

        return [p for p in order if p is not None]

    def classify(self, prompt: str, system: str = '', task_type: str = 'lightweight',
                 temperature: float = 0.1, max_tokens: int = 1024) -> Optional[str]:
        """Run prompt through the appropriate provider, with fallback chain."""
        for provider in self._resolve(task_type):
            if not provider.is_available():
                continue
            result = provider.classify(
                prompt, system=system, temperature=temperature, max_tokens=max_tokens
            )
            if result:
                return result
        return None

    def classify_batch(self, items: list, system: str = '', task_type: str = 'heavy',
                       temperature: float = 0.1, max_tokens: int = 4096) -> Optional[str]:
        """Run batch through the appropriate provider, with fallback chain."""
        for provider in self._resolve(task_type):
            if not provider.is_available():
                continue
            result = provider.classify_batch(
                items, system=system, temperature=temperature, max_tokens=max_tokens
            )
            if result:
                return result
        return None

    def get_provider_for(self, task_type: str) -> Optional[AIProvider]:
        """Return the first available provider for a task type."""
        for p in self._resolve(task_type):
            if p.is_available():
                return p
        return None

    def status(self) -> dict:
        """Return availability status for all providers."""
        return {
            'github': self._github.is_available() if self._github else False,
            'deepseek': self._deepseek.is_available() if self._deepseek else False,
            'ollama': self._ollama.is_available(),
        }


# ── Singleton router (lazy-loaded) ─────────────────────────────────────────────

_router: Optional[ProviderRouter] = None

def get_router() -> ProviderRouter:
    """Return the global ProviderRouter (creates on first call)."""
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router

def reset_router():
    """Force re-initialization of the global router (call after settings change)."""
    global _router
    _router = None


# ── Prompt helpers ─────────────────────────────────────────────────────────────

def _build_batch_prompt(items: list) -> str:
    """Build a numbered batch prompt from a list of FileItem-like objects."""
    lines = []
    for i, item in enumerate(items, 1):
        name = getattr(item, 'folder_name', None) or getattr(item, 'name', str(item))
        ext = ''
        src = getattr(item, 'full_source_path', None) or getattr(item, 'full_src', '')
        if src:
            ext = Path(src).suffix.lower()
        meta = getattr(item, 'metadata', {}) or {}
        hint = ''
        if meta.get('title'):
            hint = f' [title: {meta["title"]}]'
        elif meta.get('author'):
            hint = f' [author: {meta["author"]}]'
        lines.append(f"{i}. {name}{ext}{hint}")
    return '\n'.join(lines)


SYSTEM_CLASSIFY = (
    "You are a creative asset librarian. Classify design files into categories. "
    "Respond ONLY with a valid JSON array, one object per item, in the same order as input. "
    "Each object: {\"n\":1,\"category\":\"Category Name\",\"display_name\":\"Clean Name\",\"confidence\":85}. "
    "category must be a concise folder name (2-4 words, Title Case). "
    "display_name is the clean human-readable project name with noise stripped. "
    "confidence is 0-100. No extra text, no markdown fences."
)

SYSTEM_CATALOG = (
    "You are an expert in creative asset marketplaces: Videohive, Envato Elements, "
    "Motion Array, Creative Market, Freepik, Shutterstock, Adobe Stock, FilterGrade, "
    "Storyblocks, Pond5, and similar. "
    "Given a filename or folder name, identify: the marketplace it came from, the clean "
    "product name (strip IDs, version numbers, marketplace prefixes), the most accurate category, "
    "and the type of asset. "
    "Respond ONLY with valid JSON. No extra text, no markdown fences."
)

SYSTEM_REFINE = (
    "You are a file naming expert for creative assets. Clean up the given name: "
    "strip marketplace IDs (numeric IDs, item codes), version tags, and noise. "
    "Return just the clean display name — Title Case, concise, descriptive. "
    "No explanation, no quotes, just the name."
)


def build_catalog_prompt(names: list) -> str:
    """Build a batch catalog lookup prompt."""
    numbered = '\n'.join(f"{i}. {n}" for i, n in enumerate(names, 1))
    return (
        f"Identify each of these creative asset filenames/folder names. "
        f"For each, return a JSON object with: "
        f"n (number), display_name (clean name), category (folder path like 'After Effects Templates/Transitions'), "
        f"marketplace (Videohive/Envato/MotionArray/CreativeMarket/Freepik/Unknown), "
        f"asset_type (AEP/PSD/AI/PRPROJ/Audio/Font/Video/Other), confidence (0-100).\n\n"
        f"Names:\n{numbered}\n\n"
        f"Respond with a JSON array only."
    )


def parse_json_response(text: str) -> Optional[list]:
    """Extract and parse a JSON array from an LLM response."""
    if not text:
        return None
    # Strip markdown fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text.strip(), flags=re.MULTILINE)
    text = text.strip()
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        pass
    # Try extracting JSON array from embedded text
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return None
