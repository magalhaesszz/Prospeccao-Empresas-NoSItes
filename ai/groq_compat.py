"""Compatibilidade do SDK Groq para chamadas antigas do projeto.

Não remove nem reescreve os chamadores existentes. Apenas troca IDs de modelos
aposentados e fornece fallback quando o provider/modelo deixa de responder.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

from ai.providers import AIProviderError, generate_messages, model_candidates, split_csv

logger = logging.getLogger(__name__)

_RETIRED_MODELS = {"llama-3.3-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"}


def _messages_to_fallback(messages):
    return [m for m in (messages or []) if isinstance(m, dict) and isinstance(m.get("content"), str)]


def _status(exc):
    return getattr(exc, "status_code", None)


def _can_fallback(exc) -> bool:
    text = str(exc).lower()
    status = _status(exc)
    if status in {400, 404, 408, 409, 410, 422, 425, 429, 500, 502, 503, 504}:
        return True
    return any(x in text for x in ("model", "deprecated", "decommission", "retired", "rate limit", "timeout", "overloaded"))


def install_groq_compat(config: dict) -> bool:
    try:
        import groq as sdk
    except Exception as exc:
        logger.warning("[IA] SDK Groq indisponível: %s", exc)
        return False

    original = getattr(sdk, "Groq", None)
    if original is None:
        return False
    if getattr(original, "_prospector_compat", False):
        return True

    class CompletionsCompat:
        def __init__(self, inner, api_key: str):
            self.inner = inner
            self.api_key = api_key

        def create(self, *args, **kwargs):
            requested = str(kwargs.get("model") or "").strip()
            if not requested or requested in _RETIRED_MODELS:
                requested = (config.get("groq_model") or "openai/gpt-oss-120b").strip()
            candidates = split_csv([requested, *model_candidates(config, "groq")])
            last_exc = None
            for model in candidates:
                attempt = dict(kwargs)
                attempt["model"] = model
                try:
                    return self.inner.create(*args, **attempt)
                except Exception as exc:
                    last_exc = exc
                    logger.warning("[IA] Groq %s falhou: %s", model, exc)
                    if _can_fallback(exc):
                        continue
                    raise

            messages = _messages_to_fallback(kwargs.get("messages"))
            if messages:
                try:
                    result = generate_messages(
                        messages,
                        config,
                        preferred="openrouter",
                        max_tokens=int(kwargs.get("max_tokens") or 4096),
                        temperature=float(kwargs.get("temperature", 0.7)),
                        timeout=float(config.get("ai_timeout") or 90),
                        include_groq=False,
                    )
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=result["text"]))]
                    )
                except Exception as exc:
                    logger.warning("[IA] Fallback de provider também falhou: %s", exc)

            if last_exc:
                raise last_exc
            raise AIProviderError("Groq sem modelo disponível")

    class ChatCompat:
        def __init__(self, inner, api_key: str):
            self._inner = inner
            self.completions = CompletionsCompat(inner.completions, api_key)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    class GroqCompat:
        _prospector_compat = True

        def __init__(self, *args, **kwargs):
            self._inner = original(*args, **kwargs)
            self.chat = ChatCompat(self._inner.chat, str(kwargs.get("api_key") or ""))

        def __getattr__(self, name):
            return getattr(self._inner, name)

    sdk.Groq = GroqCompat
    logger.info("[IA] Groq compat ativo: %s", config.get("groq_model") or "openai/gpt-oss-120b")
    return True
