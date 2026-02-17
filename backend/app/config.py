import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    provider: str


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str
    model: str = "gpt-4.1-mini"


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1:8b"


@dataclass(frozen=True)
class GeminiSettings:
    api_key: str
    model: str = "gemini-1.5-flash"


def get_llm_settings() -> LLMSettings:
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama"
    if provider not in {"ollama", "openai", "gemini"}:
        raise RuntimeError("LLM_PROVIDER must be 'ollama', 'openai', or 'gemini'.")
    return LLMSettings(provider=provider)


def get_openai_settings() -> OpenAISettings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    return OpenAISettings(api_key=api_key, model=model)


def get_ollama_settings() -> OllamaSettings:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip() or "llama3.1:8b"
    return OllamaSettings(base_url=base_url.rstrip("/"), model=model)


def get_gemini_settings() -> GeminiSettings:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini or Gemini fallback is enabled.")
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
    return GeminiSettings(api_key=api_key, model=model)
