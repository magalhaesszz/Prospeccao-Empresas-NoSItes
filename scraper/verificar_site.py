"""
Verificação de site ativo via requests.
Usado para confirmar se a URL do Google Maps realmente abre uma página.
"""
import requests
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def verificar_site(url):
    """
    Retorna True se a URL responder com status 200.
    Timeout de 6 segundos — falha silenciosa se inacessível.
    """
    if not url:
        return False

    try:
        resposta = requests.get(
            url,
            headers=HEADERS,
            timeout=6,
            allow_redirects=True,
        )
        ativo = resposta.status_code < 400
        logger.debug("Site %s → status %d (ativo=%s)", url, resposta.status_code, ativo)
        return ativo
    except requests.exceptions.RequestException as exc:
        logger.debug("Site inacessível (%s): %s", url, exc)
        return False


def filtrar_sem_site_ativo(empresas):
    """
    Recebe lista de empresas e retorna só as que não têm site ativo.
    Faz verificação HTTP extra além do flag do Google Maps.
    """
    resultado = []
    for emp in empresas:
        if not emp.get("tem_site"):
            resultado.append(emp)
        else:
            # Confirma que o site listado realmente funciona
            if not verificar_site(emp.get("site_url")):
                emp["tem_site"] = False
                emp["site_url"] = ""
                resultado.append(emp)
    return resultado


def validar_flags_site(empresas, callback_progresso=None):
    """
    Percorre TODAS as empresas e corrige o flag tem_site via HTTP real.
    NÃO remove ninguém da lista — só ajusta tem_site/site_url.

    - Empresa marcada 'tem site' cujo site não abre → vira 'sem site'.
    - Empresa marcada 'sem site' fica como está (Google não listou URL).

    Retorna dict: {"reclassificadas": int, "total_sem_site": int}
    """
    reclassificadas = 0
    total = len(empresas)

    for i, emp in enumerate(empresas):
        if emp.get("tem_site") and emp.get("site_url"):
            if not verificar_site(emp.get("site_url")):
                emp["tem_site"] = False
                emp["site_url"] = ""
                reclassificadas += 1
        if callback_progresso:
            callback_progresso({"atual": i + 1, "total": total, "empresa": emp.get("nome", "")})

    sem_site = sum(1 for e in empresas if not e.get("tem_site"))
    logger.info("Validação de sites: %d reclassificadas, %d sem site.", reclassificadas, sem_site)
    return {"reclassificadas": reclassificadas, "total_sem_site": sem_site}
