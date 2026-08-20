import os

# Em produção (Replit/Railway): configure via Secrets/env vars no painel.
# Localmente: edite os valores padrão aqui.

CONFIG = {
    # ── Chrome ──────────────────────────────────────────────────────────────
    # No servidor: sempre headless=True, usar_undetected=False (usa chromium do sistema)
    "headless":        os.environ.get("HEADLESS",        "true").lower()  == "true",
    "usar_undetected": os.environ.get("USAR_UNDETECTED", "false").lower() == "true",
    "max_resultados":  int(os.environ.get("MAX_RESULTADOS", "50")),

    # Cobertura territorial incremental. Não substitui o scraper legado: se a
    # extensão falhar, a busca antiga é executada automaticamente.
    "prospect_coverage_enabled": os.environ.get("PROSPECT_COVERAGE_ENABLED", "true").lower() == "true",
    "prospect_max_cells":        int(os.environ.get("PROSPECT_MAX_CELLS", "25")),
    "prospect_cell_spacing_km":  float(os.environ.get("PROSPECT_CELL_SPACING_KM", "3.5")),
    "prospect_per_cell":         int(os.environ.get("PROSPECT_PER_CELL", "18")),

    # ── Servidor ─────────────────────────────────────────────────────────────
    # Replit usa porta 8080 por padrão; localmente usa 5000
    "porta":       int(os.environ.get("PORT", "8080")),
    "senha_painel": os.environ.get("SENHA_PAINEL", ""),   # legado: senha única (fallback)
    "secret_key":   os.environ.get("SECRET_KEY",  "prospector-secret-2024"),

    # ── Auth Supabase (email + senha) ────────────────────────────────────────
    # SUPABASE_URL: https://<ref>.supabase.co  |  SUPABASE_ANON_KEY: chave anon (public)
    "supabase_url":      os.environ.get("SUPABASE_URL",      "").rstrip("/"),
    "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),

    # ── WhatsApp ─────────────────────────────────────────────────────────────
    "intervalo_min":    int(os.environ.get("WA_INTERVALO_MIN", "8")),
    "intervalo_max":    int(os.environ.get("WA_INTERVALO_MAX", "15")),
    "horario_inicio":   int(os.environ.get("WA_HORA_INICIO",  "9")),
    "horario_fim":      int(os.environ.get("WA_HORA_FIM",     "18")),
    "apenas_dias_uteis": os.environ.get("WA_DIAS_UTEIS", "true").lower() == "true",
    # Evolution API — configure no Railway > Variables
    "webhook_whatsapp":   os.environ.get("WEBHOOK_WHATSAPP",   ""),
    "evolution_instance": os.environ.get("EVOLUTION_INSTANCE", "prospector"),
    "evolution_api_key":  os.environ.get("EVOLUTION_API_KEY",  ""),
    # IA — Anthropic (opcional)
    "anthropic_api_key":  os.environ.get("ANTHROPIC_API_KEY", ""),
    # IA — mantém Groq/OpenRouter existentes e adiciona modelos configuráveis + fallback.
    "ai_provider":          os.environ.get("AI_PROVIDER", "groq").lower(),
    "ai_fallback_order":    os.environ.get("AI_FALLBACK_ORDER", "openrouter,xai,groq"),
    "ai_timeout":           int(os.environ.get("AI_TIMEOUT", "90")),
    "groq_api_key":         os.environ.get("GROQ_API_KEY", ""),
    "groq_model":           os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    "groq_fallback_models": os.environ.get("GROQ_FALLBACK_MODELS", "qwen/qwen3.6-27b,openai/gpt-oss-20b"),
    "openrouter_api_key":   os.environ.get("OPENROUTER_API_KEY", ""),
    "openrouter_model":     os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"),
    "xai_api_key":          os.environ.get("XAI_API_KEY", ""),
    "xai_model":            os.environ.get("XAI_MODEL", "grok-4.5"),
    # URL pública do app (Railway) — usada nos links de preview
    "app_url":            os.environ.get("APP_URL",            ""),

    # ── Score ────────────────────────────────────────────────────────────────
    "categorias_alto_valor": [
        "advogado", "advocacia", "médico", "clínica", "dentista",
        "odontologia", "psicólogo", "fisioterapeuta", "contador",
        "contabilidade", "arquiteto", "engenheiro", "imobiliária",
        "coach", "academia", "pet shop", "veterinário",
    ],

    # ── Mensagem padrão ─────────────────────────────────────────────────────
    # Usada somente quando não existe mensagem de IA nem template ativo.
    # Mesmo nesse último fallback, o primeiro contato oferece o serviço de site.
    "mensagem_whatsapp": (
        "Oi, tudo bem? Vi a {NOME_DA_EMPRESA} e trabalho criando sites profissionais para negócios locais. "
        "Queria oferecer um site pra vocês, pra apresentar bem o negócio e deixar o contato fácil pelo WhatsApp. "
        "Posso te mostrar uma ideia?"
    ),
}

# O app antigo possui alguns usos diretos dos SDKs Groq/OpenAI. As camadas de
# compatibilidade preservam essas funções, respeitam os modelos configurados e
# aplicam as mesmas regras de WhatsApp aos prompts legados.
try:
    from ai.groq_compat import install_groq_compat
    install_groq_compat(CONFIG)
except Exception:
    pass

try:
    from ai.openai_compat import install_openrouter_compat
    install_openrouter_compat(CONFIG)
except Exception:
    # Configuração nunca deve impedir o restante da ferramenta de iniciar.
    pass

# O CRM já usa status='contatado'. Esta compatibilidade faz esse status também
# marcar mensagem_enviada=1, incluindo contatos feitos manualmente fora do app.
try:
    from database.contact_status import install_contact_status_compat
    install_contact_status_compat()
except Exception:
    # Sem DATABASE_URL, por exemplo em alguns comandos locais, o config ainda
    # deve poder ser importado normalmente.
    pass
