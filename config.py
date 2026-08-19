import os

# Em produção (Replit/Railway): configure via Secrets/env vars no painel.
# Localmente: edite os valores padrão aqui.

CONFIG = {
    # ── Chrome ──────────────────────────────────────────────────────────────
    # No servidor: sempre headless=True, usar_undetected=False (usa chromium do sistema)
    "headless":        os.environ.get("HEADLESS",        "true").lower()  == "true",
    "usar_undetected": os.environ.get("USAR_UNDETECTED", "false").lower() == "true",
    "max_resultados":  int(os.environ.get("MAX_RESULTADOS", "50")),

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
    "intervalo_min":    int(os.environ.get("WA_INTERVALO_MIN", "40")),
    "intervalo_max":    int(os.environ.get("WA_INTERVALO_MAX", "90")),
    "horario_inicio":   int(os.environ.get("WA_HORA_INICIO",  "9")),
    "horario_fim":      int(os.environ.get("WA_HORA_FIM",     "18")),
    "apenas_dias_uteis": os.environ.get("WA_DIAS_UTEIS", "true").lower() == "true",
    # Evolution API — configure no Railway > Variables
    "webhook_whatsapp":   os.environ.get("WEBHOOK_WHATSAPP",   ""),
    "evolution_instance": os.environ.get("EVOLUTION_INSTANCE", "prospector"),
    "evolution_api_key":  os.environ.get("EVOLUTION_API_KEY",  ""),
    # IA — Anthropic (opcional)
    "anthropic_api_key":  os.environ.get("ANTHROPIC_API_KEY",  ""),
    # IA — Provider: "groq" ou "openrouter" (define via AI_PROVIDER no Railway)
    "ai_provider":        os.environ.get("AI_PROVIDER",        "groq"),
    "groq_api_key":       os.environ.get("GROQ_API_KEY",       ""),
    "openrouter_api_key": os.environ.get("OPENROUTER_API_KEY", ""),
    "groq_model":         os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    "openrouter_model":   os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"),
    # URL pública do app (Railway) — usada nos links de preview
    "app_url":            os.environ.get("APP_URL",            ""),

    # ── Score ────────────────────────────────────────────────────────────────
    "categorias_alto_valor": [
        "advogado", "advocacia", "médico", "clínica", "dentista",
        "odontologia", "psicólogo", "fisioterapeuta", "contador",
        "contabilidade", "arquiteto", "engenheiro", "imobiliária",
        "coach", "academia", "pet shop", "veterinário",
    ],

    # ── Mensagem padrão (fallback quando não há template ativo) ──────────────
    "mensagem_whatsapp": (
        "Olá, *{NOME_DA_EMPRESA}*! 👋\n\n"
        "Meu nome é Matheus Magalhães, trabalho com automação de processos "
        "e criação de sites profissionais.\n\n"
        "Identifiquei que vocês ainda não possuem presença digital — posso ajudar com isso!\n\n"
        "✅ Automação de tarefas manuais (planilhas, controles, atendimento)\n"
        "✅ Sites profissionais para seu negócio\n\n"
        "*Cobro apenas após a entrega finalizada.*\n\n"
        "Gostaria de ver um modelo antes? Me responda aqui! 🚀"
    ),
}
