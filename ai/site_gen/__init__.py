"""
Motor de geração de sites demo por nicho.

Uso:
    from ai.site_gen import gerar_site
    slug, html = gerar_site(empresa, api_key, gerar_fn=_gerar, validar_fotos_fn=_validar_fotos)

- Layout distinto por nicho (ver theme.py / layouts.py).
- HTML/CSS profissional FIXO em Python (nunca gerado pela IA) → sempre bonito.
- IA gera SOMENTE o conteúdo textual em JSON, com fallback → página nunca quebra.
"""
import json
import logging
import secrets

from .theme import tema
from .content import gerar_conteudo
from . import components as _components
from .factual_components import contato as _contato_factual, faixa_cta as _faixa_cta_factual
from .layouts import renderizar

# Os layouts antigos chamam funções do módulo components. Mantemos essa API e
# trocamos só os dois componentes que continham suposições de atendimento e um
# formulário sem backend.
_components.contato = _contato_factual
_components.faixa_cta = _faixa_cta_factual

logger = logging.getLogger(__name__)


def _montar_fotos(empresa, validar_fotos_fn):
    foto_url = empresa.get("foto_url") or ""
    fotos_raw = empresa.get("fotos_urls") or "[]"
    try:
        fotos_lista = json.loads(fotos_raw) if isinstance(fotos_raw, str) else list(fotos_raw or [])
    except Exception:
        fotos_lista = []
    if foto_url and foto_url not in fotos_lista:
        fotos_lista.insert(0, foto_url)
    fotos_lista = [f for f in fotos_lista if f][:6]
    if validar_fotos_fn:
        try:
            fotos_lista = validar_fotos_fn(fotos_lista)
        except Exception as e:
            logger.warning("[site_gen] Validação de fotos falhou: %s", e)
    return fotos_lista


def _telefone(empresa):
    tel = empresa.get("telefone") or ""
    digits = "".join(d for d in tel if d.isdigit())
    wa_num = f"55{digits}" if digits and not digits.startswith("55") else digits
    wa_link = f"https://wa.me/{wa_num}" if wa_num else "#"
    tel_link = f"tel:+{wa_num}" if wa_num else "#"
    return wa_link, tel_link


def _contexto(empresa, validar_fotos_fn):
    categoria = empresa.get("descricao_google") or empresa.get("categoria") or "Negócio Local"
    t = tema(categoria)
    # O tema visual pode conhecer o nicho, mas não deve presumir que o negócio
    # aceita agendamento, reservas, pedidos ou orçamento. CTAs permanecem factuais.
    t["termo_agendar"] = "Falar no WhatsApp"
    t["rotulo_servicos"] = "Informações"

    fotos = _montar_fotos(empresa, validar_fotos_fn)
    wa_link, tel_link = _telefone(empresa)

    nota = empresa.get("nota")
    avs = empresa.get("avaliacoes")
    try:
        tem_nota = bool(nota) and float(nota) > 0
    except (TypeError, ValueError):
        tem_nota = False

    ctx = dict(t)  # cores, archetype, icones, rótulos, mostra_preco, nicho
    ctx.update({
        "nome":       empresa.get("nome", "") or "Sua Empresa",
        "categoria":  categoria,
        "cidade":     empresa.get("cidade") or "",
        "endereco":   empresa.get("endereco") or "",
        "telefone":   empresa.get("telefone") or "",
        "nota":       float(nota) if tem_nota else None,
        "nota_fmt":   f"{float(nota):.1f}" if tem_nota else "",
        "avaliacoes": avs if avs is not None else 0,
        "tem_nota":   tem_nota,
        "maps_url":   empresa.get("maps_url") or "",
        "fotos":      fotos,
        "hero_img":   fotos[0] if fotos else "",
        "wa_link":    wa_link,
        "tel_link":   tel_link,
    })
    return ctx


def gerar_site(empresa, api_key, gerar_fn, validar_fotos_fn=None):
    """
    Gera o site demo completo de uma empresa.
    Retorna (slug, html). Nunca levanta por falha da IA (usa fallback).
    """
    ctx = _contexto(empresa, validar_fotos_fn)
    logger.info("[site_gen] Gerando site '%s' — nicho=%s layout=%s",
                ctx["nome"], ctx["nicho"], ctx["archetype"])
    cont = gerar_conteudo(ctx, api_key, gerar_fn)
    html = renderizar(ctx, cont)

    # Validação defensiva
    baixo = html.strip().lower()
    if not baixo.startswith("<!doctype") or not baixo.endswith("</html>"):
        raise Exception("HTML gerado inválido pelo motor de sites.")

    slug = secrets.token_urlsafe(8)
    return slug, html
