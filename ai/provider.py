"""Cliente central de IA do Prospector.

Todos os fluxos (enriquecimento, templates, respostas e páginas) devem passar
por este módulo para que provider/modelo/retry não fiquem duplicados no app.
"""
import logging
import time

from config import CONFIG

logger = logging.getLogger(__name__)


def get_provider():
    provider = (CONFIG.get("ai_provider") or "groq").strip().lower()
    if provider not in ("groq", "openrouter"):
        raise ValueError(f"Provider de IA inválido: {provider!r}")
    return provider


def get_api_key(provider=None):
    provider = provider or get_provider()
    if provider == "openrouter":
        return (CONFIG.get("openrouter_api_key") or "").strip()
    return (CONFIG.get("groq_api_key") or "").strip()


def get_model(provider=None):
    provider = provider or get_provider()
    if provider == "openrouter":
        return (CONFIG.get("openrouter_model") or "google/gemini-2.5-flash-lite").strip()
    return (CONFIG.get("groq_model") or "openai/gpt-oss-120b").strip()


def _retryable(exc):
    texto = str(exc).lower()
    return any(s in texto for s in (
        "429", "rate limit", "rate_limit", "timeout", "timed out",
        "502", "503", "504", "temporarily unavailable",
    ))


def gerar_texto(prompt, api_key=None, max_tokens=4096, timeout=90.0,
                temperature=0.7, system=None):
    """Gera texto usando o provider configurado, com retry apenas para falhas transitórias."""
    provider = get_provider()
    api_key = (api_key or get_api_key(provider) or "").strip()
    if not api_key:
        raise ValueError(f"API key não configurada para provider '{provider}'.")

    model = get_model(provider)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for tentativa in range(3):
        try:
            if provider == "openrouter":
                from openai import OpenAI
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                    timeout=timeout,
                )
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            else:
                from groq import Groq
                client = Groq(api_key=api_key, timeout=timeout, max_retries=0)
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            conteudo = resp.choices[0].message.content
            if not conteudo:
                raise RuntimeError(f"{provider}/{model} retornou resposta vazia.")
            return conteudo.strip()

        except Exception as exc:
            if tentativa < 2 and _retryable(exc):
                espera = (tentativa + 1) * 5
                logger.warning(
                    "[%s/%s] falha transitória; nova tentativa em %ss: %s",
                    provider, model, espera, str(exc)[:180],
                )
                time.sleep(espera)
                continue
            raise

    raise RuntimeError(f"Falha inesperada ao gerar texto com {provider}/{model}.")
