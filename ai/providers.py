"""Providers de IA com fallback de modelo/provider, sem dependência do SDK Groq."""
from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    pass


def split_csv(value, default: Iterable[str] = ()) -> list[str]:
    raw = default if value is None else (value if isinstance(value, (list, tuple)) else str(value).split(","))
    out = []
    for item in raw:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out


def provider_key(config: dict, provider: str, legacy_key: str = "") -> str:
    return {
        "groq": config.get("groq_api_key") or legacy_key,
        "openrouter": config.get("openrouter_api_key"),
        "xai": config.get("xai_api_key"),
    }.get(provider, "") or ""


def provider_order(config: dict, preferred: str | None = None, include_groq: bool = True) -> list[str]:
    preferred = (preferred or config.get("ai_provider") or "groq").strip().lower()
    fallback = split_csv(config.get("ai_fallback_order"), ("openrouter", "xai", "groq"))
    order = []
    for provider in (preferred, *fallback):
        if provider not in {"groq", "openrouter", "xai"}:
            continue
        if provider == "groq" and not include_groq:
            continue
        if provider not in order:
            order.append(provider)
    return order


def model_candidates(config: dict, provider: str) -> list[str]:
    if provider == "groq":
        primary = (config.get("groq_model") or "openai/gpt-oss-120b").strip()
        fallbacks = split_csv(config.get("groq_fallback_models"), ("qwen/qwen3.6-27b", "openai/gpt-oss-20b"))
        return split_csv([primary, *fallbacks])
    if provider == "openrouter":
        return [(config.get("openrouter_model") or "google/gemini-2.5-flash-lite").strip()]
    if provider == "xai":
        return [(config.get("xai_model") or "grok-4.5").strip()]
    return []


def _base_url(provider: str) -> str:
    return {
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "xai": "https://api.x.ai/v1",
    }[provider]


def _retryable(status: int | None, detail: str) -> bool:
    text = (detail or "").lower()
    return status in {408, 409, 425, 429, 500, 502, 503, 504} or any(
        token in text for token in ("timeout", "rate limit", "overloaded", "temporarily unavailable", "connection reset")
    )


def _model_error(status: int | None, detail: str) -> bool:
    text = (detail or "").lower()
    if status in {404, 410}:
        return True
    return status in {400, 403, 422} and any(
        token in text for token in ("model", "deprecated", "decommission", "retired", "not found", "not available", "unsupported")
    )


def _request(session, config: dict, provider: str, key: str, model: str, messages: list[dict], max_tokens: int, temperature: float, timeout: float) -> str:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["X-OpenRouter-Title"] = "Prospector"
        if config.get("app_url"):
            headers["HTTP-Referer"] = config["app_url"]
    response = session.post(
        f"{_base_url(provider)}/chat/completions",
        headers=headers,
        json={"model": model, "messages": messages, "max_tokens": int(max_tokens), "temperature": float(temperature)},
        timeout=timeout,
    )
    if not response.ok:
        exc = AIProviderError(f"{provider}/{model} HTTP {response.status_code}: {(response.text or '')[:500]}")
        exc.status_code = response.status_code
        raise exc
    try:
        text = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        raise AIProviderError(f"Resposta inválida de {provider}/{model}") from exc
    if not isinstance(text, str) or not text.strip():
        raise AIProviderError(f"Resposta vazia de {provider}/{model}")
    return text.strip()


def generate_messages(messages: list[dict], config: dict, *, preferred: str | None = None, legacy_api_key: str = "", max_tokens: int = 4096, temperature: float = 0.7, timeout: float | None = None, include_groq: bool = True) -> dict:
    """Executa a mesma conversa tentando modelos e providers em ordem segura."""
    timeout = float(timeout or config.get("ai_timeout") or 90)
    errors = []
    with requests.Session() as session:
        for provider in provider_order(config, preferred, include_groq=include_groq):
            key = str(provider_key(config, provider, legacy_api_key if provider == preferred else "")).strip()
            if not key:
                continue
            for model in model_candidates(config, provider):
                for attempt in range(3):
                    started = time.monotonic()
                    try:
                        text = _request(session, config, provider, key, model, messages, max_tokens, temperature, timeout)
                        return {
                            "text": text,
                            "provider": provider,
                            "model": model,
                            "latency_ms": int((time.monotonic() - started) * 1000),
                        }
                    except Exception as exc:
                        detail = str(exc)
                        status = getattr(exc, "status_code", None)
                        errors.append(f"{provider}/{model}: {detail[:220]}")
                        logger.warning("[IA] %s/%s falhou: %s", provider, model, detail)
                        if _model_error(status, detail):
                            break
                        if _retryable(status, detail) and attempt < 2:
                            time.sleep(2 * (attempt + 1))
                            continue
                        break
    raise AIProviderError("Nenhum provider respondeu: " + " | ".join(errors[-8:]))
