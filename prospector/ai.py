from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from .settings import Settings

logger = logging.getLogger(__name__)


class AIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    model: str
    api_key: str
    headers: dict[str, str]


class AIService:
    def __init__(self, settings: Settings, db=None, session=None):
        self.settings = settings
        self.db = db
        self.session = session or requests.Session()

    def provider_spec(self, provider: str) -> ProviderSpec:
        provider = provider.lower()
        key = self.settings.ai_key(provider)
        model = self.settings.ai_model(provider)
        if provider == "groq":
            base = "https://api.groq.com/openai/v1"
            headers = {}
        elif provider == "openrouter":
            base = "https://openrouter.ai/api/v1"
            headers = {"X-OpenRouter-Title": "Prospector V2"}
            if self.settings.app_url:
                headers["HTTP-Referer"] = self.settings.app_url
        elif provider == "xai":
            base = "https://api.x.ai/v1"
            headers = {}
        else:
            raise AIError(f"provider desconhecido: {provider}")
        return ProviderSpec(provider, base, model, key, headers)

    def provider_order(self, preferred: str | None = None) -> list[str]:
        order: list[str] = []
        for p in (preferred or self.settings.ai_provider, *self.settings.ai_fallback_order):
            if p and p not in order and self.settings.ai_key(p):
                order.append(p)
        return order

    def _request(self, spec: ProviderSpec, messages: list[dict], max_tokens: int, temperature: float) -> str:
        if not spec.api_key:
            raise AIError(f"API key não configurada para {spec.name}")
        headers = {"Authorization": f"Bearer {spec.api_key}", "Content-Type": "application/json", **spec.headers}
        payload = {"model": spec.model,"messages": messages,"max_tokens": max_tokens,"temperature": temperature}
        response = self.session.post(f"{spec.base_url}/chat/completions", headers=headers, json=payload, timeout=self.settings.ai_timeout)
        if not response.ok:
            raise AIError(f"{spec.name} HTTP {response.status_code}: {response.text[:300]}")
        try:
            text = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise AIError(f"resposta inválida de {spec.name}") from exc
        if not isinstance(text, str) or not text.strip():
            raise AIError(f"resposta vazia de {spec.name}")
        return text.strip()

    def generate(self, prompt: str, *, system: str = "", preferred: str | None = None, purpose: str = "general", company_id: int | None = None, max_tokens: int = 800, temperature: float = 0.6) -> dict:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        errors: list[str] = []
        order = self.provider_order(preferred)
        if not order:
            raise AIError("nenhum provider de IA configurado")
        for provider in order:
            spec = self.provider_spec(provider)
            started = time.monotonic()
            try:
                text = self._request(spec, messages, max_tokens=max_tokens, temperature=temperature)
                latency = int((time.monotonic() - started) * 1000)
                if self.db:
                    self.db.log_ai_event(company_id=company_id, provider=provider, model=spec.model, purpose=purpose, status="ok", latency_ms=latency)
                return {"text": text, "provider": provider, "model": spec.model, "latency_ms": latency}
            except Exception as exc:
                latency = int((time.monotonic() - started) * 1000)
                errors.append(f"{provider}: {exc}")
                if self.db:
                    try:
                        self.db.log_ai_event(company_id=company_id, provider=provider, model=spec.model, purpose=purpose, status="error", latency_ms=latency, error=str(exc))
                    except Exception:
                        logger.exception("Falha ao registrar ai_event")
                logger.warning("AI provider %s falhou: %s", provider, exc)
        raise AIError("todos os providers falharam: " + " | ".join(errors))

    def test_provider(self, provider: str) -> dict:
        spec = self.provider_spec(provider)
        if not spec.api_key:
            return {"provider": provider, "configured": False, "ok": False, "model": spec.model, "error": "API key ausente"}
        started = time.monotonic()
        try:
            text = self._request(spec, [{"role": "user", "content": "Responda apenas OK"}], max_tokens=20, temperature=0)
            return {"provider": provider, "configured": True, "ok": True, "model": spec.model, "latency_ms": int((time.monotonic()-started)*1000), "response": text[:50]}
        except Exception as exc:
            return {"provider": provider, "configured": True, "ok": False, "model": spec.model, "latency_ms": int((time.monotonic()-started)*1000), "error": str(exc)}

    def sales_message(self, company: dict, preview_url: str = "") -> dict:
        details = [f"Empresa: {company.get('nome','')}",f"Segmento: {company.get('descricao_google') or company.get('categoria') or 'negócio local'}",f"Cidade/endereço: {company.get('endereco') or company.get('cidade_norm') or ''}"]
        if company.get("nota"):
            details.append(f"Nota: {company['nota']} com {company.get('avaliacoes') or 0} avaliações")
        if preview_url:
            details.append(f"Prévia preparada: {preview_url}")
        prompt = "\n".join(details) + "\n\nCrie uma mensagem curta, personalizada e respeitosa, pedindo permissão para conversar sobre presença digital. Não pressione, não invente dados, não diga que analisou algo que não está acima. Máximo 65 palavras, PT-BR, uma pergunta final simples."
        return self.generate(prompt, system="Você escreve mensagens B2B claras, consentidas e não invasivas.", purpose="sales_message", company_id=company.get("id"), max_tokens=180, temperature=0.7)

    def analyze_company(self, company: dict) -> dict:
        prompt = f"Analise este lead para priorização comercial. Dados: {company}. Retorne em PT-BR: prioridade (alta/média/baixa), 3 motivos objetivos e próxima ação. Não invente fatos."
        return self.generate(prompt, system="Você é analista de prospecção B2B.", purpose="lead_analysis", company_id=company.get("id"), max_tokens=300, temperature=0.3)
