"""Interface simples para geração de texto resiliente."""
from __future__ import annotations

from ai.providers import generate_messages, model_candidates, provider_order


def gerar_texto(prompt: str, config: dict, *, preferred: str | None = None, legacy_api_key: str = "", max_tokens: int = 4096, timeout: float | None = None, temperature: float = 0.7, system: str | None = None) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return generate_messages(
        messages,
        config,
        preferred=preferred,
        legacy_api_key=legacy_api_key,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
    )


__all__ = ["gerar_texto", "generate_messages", "model_candidates", "provider_order"]
