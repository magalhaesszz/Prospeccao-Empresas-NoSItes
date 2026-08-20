"""Compatibilidade para o uso legado do SDK OpenAI apontando para OpenRouter.

O app antigo instancia ``OpenAI(base_url='https://openrouter.ai/api/v1')``
diretamente. Este adaptador preserva essa API e injeta as mesmas regras de
WhatsApp usadas no restante do projeto, sem alterar outras instâncias do SDK.
"""
from __future__ import annotations

import logging

from ai.copy_rules import is_whatsapp_task, with_whatsapp_system
from ai.providers import generate_messages

logger = logging.getLogger(__name__)


def install_openrouter_compat(config: dict) -> bool:
    try:
        import openai as sdk
    except Exception as exc:
        logger.warning("[IA] SDK OpenAI indisponível: %s", exc)
        return False

    original = getattr(sdk, "OpenAI", None)
    if original is None:
        return False
    if getattr(original, "_prospector_openrouter_compat", False):
        return True

    class CompletionsCompat:
        def __init__(self, inner):
            self._inner = inner

        def create(self, *args, **kwargs):
            original_messages = [
                m for m in (kwargs.get("messages") or [])
                if isinstance(m, dict) and isinstance(m.get("content"), str)
            ]
            whatsapp = is_whatsapp_task(original_messages)
            attempt = dict(kwargs)
            if whatsapp:
                attempt["messages"] = with_whatsapp_system(original_messages)
                attempt["max_tokens"] = min(int(attempt.get("max_tokens") or 220), 220)
                attempt["temperature"] = min(float(attempt.get("temperature", 0.55)), 0.6)

            configured_model = (config.get("openrouter_model") or "").strip()
            if configured_model:
                attempt["model"] = configured_model

            try:
                return self._inner.create(*args, **attempt)
            except Exception as first_exc:
                if not original_messages:
                    raise
                # Mantém o comportamento de fallback do projeto também neste
                # caminho legado, sem depender novamente do SDK OpenAI.
                try:
                    result = generate_messages(
                        attempt.get("messages") or original_messages,
                        config,
                        preferred="groq",
                        max_tokens=int(attempt.get("max_tokens") or 700),
                        temperature=float(attempt.get("temperature", 0.5)),
                        timeout=float(config.get("ai_timeout") or 90),
                    )
                    from types import SimpleNamespace
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content=result["text"]))]
                    )
                except Exception:
                    raise first_exc

    class ChatCompat:
        def __init__(self, inner):
            self._inner = inner
            self.completions = CompletionsCompat(inner.completions)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    class OpenAICompat:
        _prospector_openrouter_compat = True

        def __init__(self, *args, **kwargs):
            self._inner = original(*args, **kwargs)
            base_url = str(kwargs.get("base_url") or "")
            self.chat = ChatCompat(self._inner.chat) if "openrouter.ai" in base_url else self._inner.chat

        def __getattr__(self, name):
            return getattr(self._inner, name)

    sdk.OpenAI = OpenAICompat
    logger.info("[IA] Compat OpenRouter ativo para chamadas legadas")
    return True
