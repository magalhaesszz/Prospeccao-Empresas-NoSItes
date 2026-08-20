from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "").strip())
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "").strip())
    admin_password: str = field(default_factory=lambda: (os.getenv("ADMIN_PASSWORD") or os.getenv("SENHA_PAINEL") or "").strip())
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").strip().rstrip("/"))
    supabase_anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", "").strip())
    app_url: str = field(default_factory=lambda: os.getenv("APP_URL", "").strip().rstrip("/"))
    port: int = field(default_factory=lambda: _int("PORT", 8080, 1, 65535))
    headless: bool = field(default_factory=lambda: _bool("HEADLESS", True))
    max_results: int = field(default_factory=lambda: _int("MAX_RESULTADOS", 50, 5, 300))
    max_coverage_cells: int = field(default_factory=lambda: _int("PROSPECT_MAX_CELLS", 25, 1, 64))
    coverage_spacing_km: float = field(default_factory=lambda: float(os.getenv("PROSPECT_CELL_SPACING_KM", "3.5")))
    per_cell_results: int = field(default_factory=lambda: _int("PROSPECT_PER_CELL", 18, 5, 50))

    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "groq").strip().lower())
    ai_fallback_order: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip().lower() for x in os.getenv("AI_FALLBACK_ORDER", "openrouter,xai,groq").split(",") if x.strip()
    ))
    ai_timeout: int = field(default_factory=lambda: _int("AI_TIMEOUT", 90, 10, 300))
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", "").strip())
    groq_model: str = field(default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip())
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "").strip())
    openrouter_model: str = field(default_factory=lambda: os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite").strip())
    xai_api_key: str = field(default_factory=lambda: os.getenv("XAI_API_KEY", "").strip())
    xai_model: str = field(default_factory=lambda: os.getenv("XAI_MODEL", "grok-4.5").strip())

    wa_provider: str = field(default_factory=lambda: os.getenv("WA_PROVIDER", "evolution").strip().lower())
    wa_daily_limit: int = field(default_factory=lambda: _int("WA_DAILY_LIMIT", 50, 0, 1000))
    wa_contact_cooldown_hours: int = field(default_factory=lambda: _int("WA_CONTACT_COOLDOWN_HOURS", 72, 1, 720))
    wa_dry_run: bool = field(default_factory=lambda: _bool("WA_DRY_RUN", True))
    wa_business_start_hour: int = field(default_factory=lambda: _int("WA_HORA_INICIO", 9, 0, 23))
    wa_business_end_hour: int = field(default_factory=lambda: _int("WA_HORA_FIM", 18, 1, 24))

    evolution_url: str = field(default_factory=lambda: (os.getenv("EVOLUTION_URL") or os.getenv("WEBHOOK_WHATSAPP") or "").strip().rstrip("/"))
    evolution_instance: str = field(default_factory=lambda: os.getenv("EVOLUTION_INSTANCE", "prospector").strip())
    evolution_api_key: str = field(default_factory=lambda: os.getenv("EVOLUTION_API_KEY", "").strip())

    meta_access_token: str = field(default_factory=lambda: os.getenv("META_WHATSAPP_TOKEN", "").strip())
    meta_phone_number_id: str = field(default_factory=lambda: os.getenv("META_PHONE_NUMBER_ID", "").strip())
    meta_graph_version: str = field(default_factory=lambda: os.getenv("META_GRAPH_VERSION", "v23.0").strip())
    meta_template_name: str = field(default_factory=lambda: os.getenv("META_TEMPLATE_NAME", "").strip())
    meta_template_language: str = field(default_factory=lambda: os.getenv("META_TEMPLATE_LANGUAGE", "pt_BR").strip())
    evolution_webhook_secret: str = field(default_factory=lambda: os.getenv("EVOLUTION_WEBHOOK_SECRET", "").strip())
    meta_verify_token: str = field(default_factory=lambda: os.getenv("META_VERIFY_TOKEN", "").strip())

    def validate(self, production: bool = False) -> list[str]:
        errors: list[str] = []
        if not self.database_url:
            errors.append("DATABASE_URL não configurada")
        if production and (not self.secret_key or self.secret_key == "prospector-secret-2024"):
            errors.append("SECRET_KEY forte é obrigatória em produção")
        if self.ai_provider not in {"groq", "openrouter", "xai"}:
            errors.append("AI_PROVIDER deve ser groq, openrouter ou xai")
        if self.wa_provider not in {"evolution", "meta", "disabled"}:
            errors.append("WA_PROVIDER deve ser evolution, meta ou disabled")
        if self.wa_business_end_hour <= self.wa_business_start_hour:
            errors.append("WA_HORA_FIM deve ser maior que WA_HORA_INICIO")
        return errors

    def ai_key(self, provider: str) -> str:
        return {
            "groq": self.groq_api_key,
            "openrouter": self.openrouter_api_key,
            "xai": self.xai_api_key,
        }.get(provider, "")

    def ai_model(self, provider: str) -> str:
        return {
            "groq": self.groq_model,
            "openrouter": self.openrouter_model,
            "xai": self.xai_model,
        }.get(provider, "")

    def configured_ai_providers(self) -> list[str]:
        return [p for p in ("groq", "openrouter", "xai") if self.ai_key(p)]

    def legacy_config(self) -> dict:
        """Compatibility for the few legacy helpers that still import CONFIG."""
        return {
            "headless": self.headless,
            "usar_undetected": False,
            "max_resultados": self.max_results,
            "porta": self.port,
            "secret_key": self.secret_key,
            "senha_painel": self.admin_password,
            "supabase_url": self.supabase_url,
            "supabase_anon_key": self.supabase_anon_key,
            "app_url": self.app_url,
            "ai_provider": self.ai_provider,
            "groq_api_key": self.groq_api_key,
            "openrouter_api_key": self.openrouter_api_key,
            "xai_api_key": self.xai_api_key,
            "webhook_whatsapp": self.evolution_url,
            "evolution_instance": self.evolution_instance,
            "evolution_api_key": self.evolution_api_key,
            "horario_inicio": self.wa_business_start_hour,
            "horario_fim": self.wa_business_end_hour,
            "apenas_dias_uteis": True,
            "intervalo_min": 0,
            "intervalo_max": 0,
            "categorias_alto_valor": [
                "advogado", "advocacia", "médico", "clínica", "dentista", "odontologia",
                "psicólogo", "fisioterapeuta", "contador", "contabilidade", "arquiteto",
                "engenheiro", "imobiliária", "academia", "pet shop", "veterinário",
            ],
        }


settings = Settings()
