# Prospector V2

Prospector V2 reorganiza a ferramenta em serviços independentes para prospecção territorial, deduplicação persistente, CRM, IA multi-provider, geração de landing pages e WhatsApp com elegibilidade/consentimento.

## O que mudou

A busca antiga fazia essencialmente uma consulta de `categoria em cidade`, o que tendia a repetir o mesmo ranking. A V2 resolve o centro da cidade, cria uma grade geográfica e prioriza células que ainda não foram varridas. A quantidade solicitada representa **leads novos**; empresas conhecidas são contabilizadas, mas não encerram a busca.

A identidade de uma empresa usa, nesta ordem, telefone normalizado, identificador estável extraído da URL do Google Maps e fingerprint de nome + endereço. O banco mantém a empresa uma única vez e registra em `busca_empresas` cada busca em que ela reapareceu.

A camada de IA suporta **Groq**, **OpenRouter** e **xAI/Grok** com um único contrato, modelos configuráveis por ambiente e fallback automático entre providers configurados. O modelo padrão do Groq foi migrado para `openai/gpt-oss-120b`; xAI usa `grok-4.5` por padrão.

O módulo de WhatsApp deixou de tentar mascarar automação. Leads coletados começam sem elegibilidade de saída. O envio exige opt-in registrado, respeita limite diário, horário e cooldown por contato, e oferece `WA_DRY_RUN=true` para validar o fluxo sem transmitir mensagens. Há adapters para Evolution API e Meta WhatsApp Cloud API.

## Arquitetura

```text
app.py                     entrada WSGI
prospector/
  settings.py              configuração tipada
  identity.py              normalização + deduplicação
  coverage.py              grade e prioridade territorial
  db.py                    schema/migração/repositório PostgreSQL
  migration.py             preflight seguro para bancos legados
  prospecting.py           orquestração das buscas
  ai.py                    Groq/OpenRouter/xAI + failover
  messaging.py             política de saída + providers WhatsApp
  inbound.py               webhooks/opt-out
  landing.py               landing demo determinística
  diagnostics.py           health checks
  jobs.py                  jobs em background
  web.py                   rotas Flask/API
scraper/google_maps.py      scraper por célula geográfica
frontend/v2.*               painel SPA
```

## Migração sem apagar dados

Na inicialização, o preflight em `prospector/migration.py` remove apenas o índice único legado de telefone que poderia colidir durante a normalização e registra as associações originais de busca antes da deduplicação. Em seguida, `Database.init_schema()` mantém as tabelas legadas `empresas` e `buscas`, adiciona campos V2, faz backfill de telefone/place ID/fingerprint, consolida duplicatas e cria as tabelas auxiliares de cobertura, aparições, permissões e auditoria. Notas e previews são repontados para o registro vencedor durante deduplicação.

Faça backup do banco antes do primeiro deploy de qualquer migração estrutural. A migração é idempotente e também é executada pela suíte de integração em PostgreSQL no CI.

## Rodando localmente

```bash
cp .env.example .env
docker compose up --build
```

Abra `http://localhost:8080`.

## Variáveis principais

Consulte `.env.example`. Em produção, configure obrigatoriamente `DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD` e as chaves dos providers que realmente usar.

Para IA, selecione `AI_PROVIDER=groq|openrouter|xai`; os fallbacks ficam em `AI_FALLBACK_ORDER`. Para WhatsApp, `WA_PROVIDER=evolution|meta|disabled`. Mantenha `WA_DRY_RUN=true` até concluir os testes do número e do provider.

## Validação

O CI executa:

```bash
python -m compileall -q app.py prospector scraper
node --check frontend/v2.js
pytest
```

Os testes incluem identidade/deduplicação, planejamento de cobertura, fallback de IA, política de WhatsApp, landing page, smoke da aplicação, upsert entre buscas e migração realista do schema legado em PostgreSQL 16 — inclusive duplicatas que convergem após normalização de telefone e preservação de histórico/notas.

O painel também possui **Diagnóstico**, com validação de banco, Chrome/ChromeDriver, configuração dos providers e testes ao vivo opcionais das APIs configuradas.
