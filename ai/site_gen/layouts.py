"""
Layouts por arquétipo de nicho. Cada função compõe as seções em ordem e
estrutura próprias, reutilizando os componentes de components.py.
Todas recebem (ctx, cont) e retornam o HTML completo via documento().
"""
from . import components as C
from .icons import svg


def _diferenciais(ctx, difs, fundo="fundo-claro", titulo="Informações úteis"):
    """Mostra somente diferenciais/informações que tenham dados reais."""
    if not difs:
        return ""
    icones = ctx["icones"]
    cards = []
    for i, d in enumerate(difs):
        ic = d.get("icone") or icones[(i + 2) % len(icones)]
        cards.append(f"""<div class="card revelar">
  <div class="icone-circulo">{svg(ic, 30)}</div>
  <h3>{C.esc(d.get('titulo',''))}</h3>
  <p>{C.esc(d.get('descricao',''))}</p>
</div>""")
    return f"""
<section class="{fundo}" id="diferenciais">
  <div class="container">
    {C.cabecalho_secao("Informações", titulo)}
    <div class="grid grid-3">{"".join(cards)}</div>
  </div>
</section>"""


def _servicos(ctx, cont, fundo="", rotulo=None, ancora="servicos"):
    servicos = cont.get("servicos") or []
    if not servicos:
        return ""
    rotulo = rotulo or ctx["rotulo_servicos"]
    cls = f' class="{fundo}"' if fundo else ""
    return f"""
<section id="{ancora}"{cls}>
  <div class="container">
    {C.cabecalho_secao(rotulo, rotulo)}
    {C.grid_servicos(ctx, servicos)}
  </div>
</section>"""


# ── Arquétipos ───────────────────────────────────────────────────────────────────

def gastronomia(ctx, cont):
    links = [("Início", "inicio"), ("Cardápio", "servicos"), ("Galeria", "galeria"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont, rotulo=ctx["rotulo_servicos"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.galeria(ctx),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def agendamento(ctx, cont):
    links = [("Início", "inicio"), ("Serviços", "servicos"), ("Galeria", "galeria"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        _diferenciais(ctx, cont["diferenciais"]),
        C.galeria(ctx),
        C.google_badge(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def pet(ctx, cont):
    links = [("Início", "inicio"), ("Serviços", "servicos"), ("Galeria", "galeria"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        _diferenciais(ctx, cont["diferenciais"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.galeria(ctx),
        C.google_badge(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def saude(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Sobre", "sobre"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _diferenciais(ctx, cont["diferenciais"], fundo=""),
        _servicos(ctx, cont, fundo="fundo-claro"),
        C.google_badge(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.galeria(ctx),
        C.faq(ctx, cont["faq"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def tecnico(ctx, cont):
    links = [("Início", "inicio"), ("Serviços", "servicos"), ("Sobre", "sobre"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.galeria(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def hospitalidade(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Galeria", "galeria"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        C.galeria(ctx),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def eventos(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Galeria", "galeria"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        C.galeria(ctx),
        _servicos(ctx, cont),
        _diferenciais(ctx, cont["diferenciais"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.google_badge(ctx),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.sobre(ctx, cont["sobre"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def educacao(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Sobre", "sobre"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.galeria(ctx),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faq(ctx, cont["faq"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def varejo(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Galeria", "galeria"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        C.galeria(ctx),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.sobre(ctx, cont["sobre"]),
        C.faq(ctx, cont["faq"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def profissional(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Sobre", "sobre"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        C.sobre(ctx, cont["sobre"]),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.galeria(ctx),
        C.faq(ctx, cont["faq"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


def generico(ctx, cont):
    links = [("Início", "inicio"), ("Informações", "servicos"), ("Sobre", "sobre"), ("Contato", "contato")]
    corpo = "".join([
        C.header(ctx, links),
        C.hero(ctx, cont["hero_titulo"], cont["hero_subtitulo"], cont["hero_badge"],
               cta_secundario=("Ver informações", "servicos")),
        C.numeros(ctx, cont["numeros"]),
        _servicos(ctx, cont),
        _diferenciais(ctx, cont["diferenciais"]),
        C.google_badge(ctx),
        C.galeria(ctx),
        C.sobre(ctx, cont["sobre"]),
        C.depoimentos(ctx, cont["depoimentos"]),
        C.faq(ctx, cont["faq"]),
        C.faixa_cta(ctx, cont["cta_titulo"], cont["cta_texto"]),
        C.contato(ctx),
        C.rodape(ctx),
    ])
    return C.documento(ctx, corpo, cont["meta_description"])


LAYOUTS = {
    "gastronomia": gastronomia,
    "agendamento": agendamento,
    "pet": pet,
    "saude": saude,
    "tecnico": tecnico,
    "hospitalidade": hospitalidade,
    "eventos": eventos,
    "educacao": educacao,
    "varejo": varejo,
    "profissional": profissional,
    "generico": generico,
}


def renderizar(ctx, cont):
    fn = LAYOUTS.get(ctx["archetype"], generico)
    return fn(ctx, cont)
