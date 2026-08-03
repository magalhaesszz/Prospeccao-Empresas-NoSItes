"""
Componentes HTML reutilizáveis + design system CSS.
Todos os layouts (layouts.py) montam a página a partir daqui.
HTML autocontido, mobile-first, zero dependências externas.
"""
import html as _html
from .icons import svg


# ── Helpers ─────────────────────────────────────────────────────────────────────

def esc(texto):
    """Escapa texto para uso seguro em conteúdo HTML."""
    return _html.escape(str(texto or ""), quote=False)


def attr(texto):
    """Escapa texto para uso seguro em atributo HTML."""
    return _html.escape(str(texto or ""), quote=True)


def estrelas(nota=5.0, tamanho=20):
    """Linha de estrelas SVG cheias/vazias conforme a nota (0-5)."""
    try:
        n = float(nota)
    except (TypeError, ValueError):
        n = 5.0
    cheias = int(round(n))
    out = []
    for i in range(5):
        preenchida = i < cheias
        fill = "currentColor" if preenchida else "none"
        opac = "1" if preenchida else "0.3"
        out.append(
            f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 24 24" '
            f'fill="{fill}" stroke="currentColor" stroke-width="1.5" '
            f'style="opacity:{opac}" aria-hidden="true">'
            '<path d="M12 2l2.9 6.3 6.9.7-5.2 4.6 1.5 6.8L12 17.8 5.9 21.2l1.5-6.8L2.2 9.8l6.9-.7L12 2z"/>'
            '</svg>'
        )
    return f'<span class="estrelas">{"".join(out)}</span>'


# ── CSS design system ────────────────────────────────────────────────────────────

def css_base(t):
    """Retorna o <style> completo, parametrizado pelo tema `t`."""
    return f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; -webkit-text-size-adjust:100%; }}
img {{ display:block; max-width:100%; height:auto; }}
a {{ color:inherit; text-decoration:none; }}
ul {{ list-style:none; }}
:root {{
  --primaria:{t['cor_primaria']};
  --primaria-escura:{t['cor_primaria_escura']};
  --acento:{t['cor_acento']};
  --acento-escura:{t['cor_acento_escura']};
  --acento-clara:{t['cor_acento_clara']};
  --texto:#1f2933;
  --texto-suave:#5a6472;
  --linha:#e8ebef;
  --fundo-claro:#f7f8fa;
  --sombra:0 4px 24px rgba(16,24,40,.08);
  --sombra-forte:0 18px 48px rgba(16,24,40,.18);
  --radius:16px;
  --radius-sm:10px;
  --radius-btn:50px;
  --transicao:.28s cubic-bezier(.16,1,.3,1);
  --container:1180px;
}}
body {{
  font-family:"Segoe UI", system-ui, -apple-system, Roboto, Helvetica, Arial, sans-serif;
  color:var(--texto); line-height:1.65; font-size:16px;
  background:#fff; overflow-x:hidden;
}}
h1,h2,h3,h4 {{ line-height:1.15; letter-spacing:-.02em; font-weight:800; }}
.container {{ max-width:var(--container); margin:0 auto; padding:0 24px; width:100%; }}
section {{ padding:clamp(60px,9vw,104px) 0; }}
.fundo-claro {{ background:var(--fundo-claro); }}
.fundo-primaria {{ background:var(--primaria); color:#fff; }}

/* ── Header ── */
header.topo {{
  position:sticky; top:0; z-index:1000; background:var(--primaria); color:#fff;
  box-shadow:0 2px 16px rgba(0,0,0,.18);
}}
.topo .container {{ display:flex; align-items:center; justify-content:space-between; height:70px; }}
.logo {{ font-size:1.35rem; font-weight:800; letter-spacing:-.02em; display:flex; align-items:center; gap:10px; }}
.logo .ponto {{ color:var(--acento); }}
nav.menu {{ display:flex; align-items:center; gap:30px; }}
nav.menu a {{ font-size:.96rem; font-weight:600; opacity:.9; transition:var(--transicao); }}
nav.menu a:hover {{ opacity:1; color:var(--acento); }}
.btn-topo {{
  background:var(--acento); color:#fff !important; padding:11px 22px;
  border-radius:var(--radius-btn); font-weight:700; display:inline-flex;
  align-items:center; gap:8px; opacity:1 !important;
}}
.btn-topo:hover {{ filter:brightness(1.08); transform:translateY(-2px); }}
.hamburguer {{ display:none; background:none; border:none; color:#fff; cursor:pointer; padding:6px; }}
.menu-mobile {{ display:none; }}

/* ── Botões ── */
.btn {{
  display:inline-flex; align-items:center; justify-content:center; gap:9px;
  padding:15px 34px; border-radius:var(--radius-btn); font-weight:700;
  font-size:1rem; letter-spacing:.2px; cursor:pointer; border:none;
  transition:var(--transicao); text-align:center;
}}
.btn-acento {{ background:var(--acento); color:#fff; box-shadow:0 8px 24px color-mix(in srgb,var(--acento) 40%,transparent); }}
.btn-acento:hover {{ filter:brightness(1.08); transform:translateY(-3px); box-shadow:0 14px 32px color-mix(in srgb,var(--acento) 50%,transparent); }}
.btn-outline {{ background:transparent; color:#fff; border:2px solid rgba(255,255,255,.7); }}
.btn-outline:hover {{ background:#fff; color:var(--primaria); transform:translateY(-3px); }}
.btn-primaria {{ background:var(--primaria); color:#fff; }}
.btn-primaria:hover {{ filter:brightness(1.15); transform:translateY(-3px); }}

/* ── Hero ── */
.hero {{ position:relative; min-height:90vh; display:flex; align-items:center; text-align:center; color:#fff; }}
.hero.com-foto {{ background-size:cover; background-position:center; }}
.hero.sem-foto {{
  background:
    radial-gradient(circle at 78% 12%, color-mix(in srgb,var(--acento) 22%,transparent), transparent 45%),
    linear-gradient(135deg, var(--primaria), var(--primaria-escura));
}}
.hero .container {{ position:relative; z-index:2; }}
.hero-badge {{
  display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.14);
  border:1px solid rgba(255,255,255,.22); backdrop-filter:blur(6px);
  padding:8px 18px; border-radius:var(--radius-btn); font-size:.9rem; font-weight:600;
  margin-bottom:26px; color:#fff;
}}
.hero-badge svg {{ color:var(--acento); }}
.hero h1 {{ font-size:clamp(2.3rem,6vw,4rem); color:#fff; text-shadow:0 2px 20px rgba(0,0,0,.35); max-width:860px; margin:0 auto; }}
.hero p.sub {{ color:rgba(255,255,255,.94); font-size:clamp(1.08rem,2.6vw,1.4rem); max-width:640px; margin:22px auto 0; font-weight:400; }}
.hero-ctas {{ display:flex; flex-wrap:wrap; gap:16px; justify-content:center; margin-top:38px; }}
.hero-nota {{ display:inline-flex; align-items:center; gap:10px; margin-top:34px; font-size:.98rem; color:rgba(255,255,255,.9); }}
.hero-nota .estrelas {{ color:var(--acento); display:inline-flex; }}

/* ── Títulos de seção ── */
.secao-cabecalho {{ text-align:center; max-width:680px; margin:0 auto clamp(38px,5vw,58px); }}
.secao-titulo {{ font-size:clamp(1.75rem,4vw,2.6rem); }}
.fundo-primaria .secao-titulo, .fundo-primaria .secao-sub {{ color:#fff; }}
.secao-titulo::after {{
  content:""; display:block; width:64px; height:4px; background:var(--acento);
  border-radius:2px; margin:16px auto 0;
}}
.secao-sub {{ color:var(--texto-suave); margin-top:18px; font-size:1.06rem; }}
.rotulo {{ color:var(--acento); font-weight:700; letter-spacing:1.5px; text-transform:uppercase; font-size:.82rem; }}

/* ── Grid + cards ── */
.grid {{ display:grid; gap:24px; }}
.grid-3 {{ grid-template-columns:repeat(auto-fit, minmax(280px,1fr)); }}
.grid-2 {{ grid-template-columns:repeat(auto-fit, minmax(320px,1fr)); }}
.card {{
  background:#fff; border-radius:var(--radius); box-shadow:var(--sombra);
  padding:32px 28px; border-top:4px solid var(--acento); transition:var(--transicao);
  height:100%;
}}
.card:hover {{ transform:translateY(-6px); box-shadow:var(--sombra-forte); }}
.card h3 {{ font-size:1.28rem; margin-bottom:10px; }}
.card p {{ color:var(--texto-suave); font-size:.98rem; }}
.icone-circulo {{
  width:60px; height:60px; border-radius:50%; display:inline-flex;
  align-items:center; justify-content:center; margin-bottom:20px;
  background:color-mix(in srgb,var(--acento) 14%,transparent); color:var(--acento);
}}
.card .preco {{
  display:inline-block; margin-top:14px; font-weight:800; color:var(--primaria);
  font-size:1.15rem;
}}
.card .preco small {{ font-weight:600; color:var(--texto-suave); font-size:.8rem; }}

/* ── Google badge ── */
.google-badge {{
  max-width:560px; margin:0 auto; background:#fff; border-radius:var(--radius);
  box-shadow:var(--sombra); padding:40px 32px; text-align:center;
  border:2px solid color-mix(in srgb,var(--acento) 30%,transparent);
}}
.google-badge .nota-grande {{ font-size:3.6rem; font-weight:800; color:var(--primaria); line-height:1; }}
.google-badge .estrelas {{ color:var(--acento); display:inline-flex; margin:12px 0 6px; }}
.google-badge .qtd {{ color:var(--texto-suave); }}
.google-badge a {{
  display:inline-flex; align-items:center; gap:8px; margin-top:20px; color:var(--acento);
  font-weight:700;
}}
.selo-google {{
  display:inline-flex; align-items:center; gap:8px; font-weight:700; color:var(--texto-suave);
  font-size:.9rem; margin-bottom:8px;
}}

/* ── Galeria ── */
.galeria {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
.galeria img {{ width:100%; height:240px; object-fit:cover; border-radius:var(--radius-sm); transition:var(--transicao); }}
.galeria img:hover {{ transform:scale(1.03); box-shadow:var(--sombra-forte); }}
.galeria-vazia {{ text-align:center; color:var(--texto-suave); padding:40px; grid-column:1/-1; }}

/* ── Sobre ── */
.sobre-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:clamp(30px,5vw,60px); align-items:center; }}
.sobre-texto p {{ color:var(--texto-suave); font-size:1.06rem; margin-bottom:16px; }}
.sobre-visual {{ border-radius:var(--radius); overflow:hidden; box-shadow:var(--sombra-forte); min-height:340px; }}
.sobre-visual img {{ width:100%; height:100%; min-height:340px; object-fit:cover; }}
.sobre-visual.bloco {{ background:linear-gradient(135deg,var(--primaria),var(--primaria-escura)); display:flex; align-items:center; justify-content:center; }}
.sobre-visual.bloco svg {{ color:color-mix(in srgb,var(--acento) 60%,transparent); }}

/* ── Depoimentos ── */
.depoimento {{ background:#fff; border-radius:var(--radius); box-shadow:var(--sombra); padding:30px 28px; height:100%; }}
.depoimento .estrelas {{ color:var(--acento); display:inline-flex; margin-bottom:14px; }}
.depoimento p {{ font-style:italic; color:var(--texto); margin-bottom:18px; }}
.depoimento .autor {{ display:flex; align-items:center; gap:12px; }}
.depoimento .avatar {{
  width:46px; height:46px; border-radius:50%; background:var(--primaria); color:#fff;
  display:flex; align-items:center; justify-content:center; font-weight:800; flex-shrink:0;
}}
.depoimento .autor b {{ display:block; }}
.depoimento .autor span {{ color:var(--texto-suave); font-size:.86rem; }}

/* ── Contato ── */
.contato-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:clamp(30px,5vw,56px); }}
.contato-info li {{ display:flex; align-items:flex-start; gap:16px; margin-bottom:22px; }}
.contato-info .ic {{
  width:48px; height:48px; border-radius:12px; flex-shrink:0; display:flex;
  align-items:center; justify-content:center;
  background:color-mix(in srgb,var(--acento) 14%,transparent); color:var(--acento);
}}
.contato-info b {{ display:block; }}
.contato-info span {{ color:var(--texto-suave); }}
.contato-botoes {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:8px; }}
form.contato {{ background:#fff; border-radius:var(--radius); box-shadow:var(--sombra); padding:32px; }}
form.contato label {{ display:block; font-weight:600; font-size:.9rem; margin-bottom:6px; }}
form.contato .campo {{ margin-bottom:18px; }}
form.contato input, form.contato textarea {{
  width:100%; border:2px solid var(--linha); border-radius:var(--radius-sm);
  padding:13px 16px; font-size:1rem; font-family:inherit; transition:var(--transicao);
}}
form.contato input:focus, form.contato textarea:focus {{ border-color:var(--acento); outline:none; }}
form.contato textarea {{ resize:vertical; min-height:110px; }}
form.contato .btn {{ width:100%; }}

/* ── Faixa CTA ── */
.faixa-cta {{ text-align:center; }}
.faixa-cta h2 {{ font-size:clamp(1.7rem,4vw,2.6rem); color:#fff; max-width:720px; margin:0 auto; }}
.faixa-cta p {{ color:rgba(255,255,255,.9); margin:18px auto 32px; max-width:560px; }}

/* ── Footer ── */
footer.rodape {{ background:var(--primaria-escura); color:rgba(255,255,255,.75); padding:44px 0; text-align:center; }}
footer.rodape .logo {{ justify-content:center; margin-bottom:12px; color:#fff; }}
footer.rodape .mini {{ font-size:.85rem; opacity:.6; margin-top:14px; }}

/* ── Números / estatísticas ── */
.numeros {{ background:linear-gradient(135deg,var(--primaria),var(--primaria-escura)); }}
.numeros-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:24px; }}
.stat {{ text-align:center; color:#fff; }}
.stat .stat-ic {{
  width:52px; height:52px; border-radius:14px; display:inline-flex; align-items:center;
  justify-content:center; margin-bottom:14px; color:var(--acento);
  background:color-mix(in srgb,var(--acento) 20%,transparent);
}}
.stat .valor {{ font-size:clamp(2rem,5vw,3rem); font-weight:800; line-height:1; color:#fff; }}
.stat .valor small {{ font-size:1.6rem; color:var(--acento); }}
.stat .rotulo {{ margin-top:8px; color:rgba(255,255,255,.82); font-size:.98rem; }}

/* ── FAQ ── */
.faq-lista {{ max-width:820px; margin:0 auto; display:flex; flex-direction:column; gap:14px; }}
.faq-item {{
  background:#fff; border:1px solid var(--linha); border-radius:var(--radius-sm);
  box-shadow:var(--sombra); overflow:hidden;
}}
.faq-item summary {{
  list-style:none; cursor:pointer; padding:20px 24px; font-weight:700; font-size:1.05rem;
  display:flex; align-items:center; justify-content:space-between; gap:16px; color:var(--texto);
}}
.faq-item summary::-webkit-details-marker {{ display:none; }}
.faq-item summary .chev {{ color:var(--acento); transition:var(--transicao); flex-shrink:0; }}
.faq-item[open] summary .chev {{ transform:rotate(180deg); }}
.faq-item .resposta {{ padding:0 24px 22px; color:var(--texto-suave); }}

/* ── WhatsApp flutuante ── */
.wa-float {{
  position:fixed; bottom:24px; right:24px; z-index:9999; width:60px; height:60px;
  border-radius:50%; background:#25D366; color:#fff; display:flex; align-items:center;
  justify-content:center; box-shadow:0 8px 24px rgba(37,211,102,.5);
  animation:pulso 2.4s infinite;
}}
.wa-float:hover {{ transform:scale(1.08); }}
@keyframes pulso {{ 0%{{box-shadow:0 0 0 0 rgba(37,211,102,.5)}} 70%{{box-shadow:0 0 0 16px rgba(37,211,102,0)}} 100%{{box-shadow:0 0 0 0 rgba(37,211,102,0)}} }}

/* ── Animação de entrada ── */
.revelar {{ opacity:0; transform:translateY(30px); transition:opacity .7s ease, transform .7s ease; }}
.revelar.visivel {{ opacity:1; transform:none; }}
@media (prefers-reduced-motion: reduce) {{
  .revelar {{ opacity:1 !important; transform:none !important; }}
  html {{ scroll-behavior:auto; }}
  .wa-float {{ animation:none; }}
}}

/* ── Barra CTA fixa (mobile) ── */
.barra-mobile {{ display:none; }}
@media (max-width:720px) {{
  .barra-mobile {{
    display:flex; position:fixed; bottom:0; left:0; right:0; z-index:9998;
    gap:10px; padding:10px 12px calc(10px + env(safe-area-inset-bottom));
    background:rgba(255,255,255,.96); backdrop-filter:blur(8px);
    box-shadow:0 -4px 20px rgba(16,24,40,.14);
  }}
  .barra-mobile a {{
    flex:1; display:inline-flex; align-items:center; justify-content:center; gap:8px;
    padding:14px; border-radius:var(--radius-btn); font-weight:700; font-size:1rem;
  }}
  .barra-mobile .wa {{ background:#25D366; color:#fff; }}
  .barra-mobile .tel {{ background:var(--primaria); color:#fff; }}
  .wa-float {{ display:none; }}
  body {{ padding-bottom:76px; }}
}}

/* ── Responsivo ── */
@media (max-width:860px) {{
  nav.menu {{ display:none; }}
  .hamburguer {{ display:block; }}
  .menu-mobile {{
    display:none; position:absolute; top:70px; left:0; right:0; background:var(--primaria);
    flex-direction:column; padding:18px 24px; gap:6px; box-shadow:0 12px 24px rgba(0,0,0,.25);
  }}
  .menu-mobile.aberto {{ display:flex; }}
  .menu-mobile a {{ padding:12px 0; border-bottom:1px solid rgba(255,255,255,.1); font-weight:600; }}
  .sobre-grid, .contato-grid {{ grid-template-columns:1fr; }}
  .galeria {{ grid-template-columns:repeat(2,1fr); }}
  .galeria img {{ height:180px; }}
  .sobre-visual {{ order:-1; }}
}}
@media (min-width:768px) {{ body {{ font-size:17px; }} }}
"""


# ── Componentes ──────────────────────────────────────────────────────────────────

def header(ctx, links):
    """links: lista de (rotulo, ancora)."""
    nome = esc(ctx["nome"])
    itens = "".join(f'<a href="#{a}">{esc(r)}</a>' for r, a in links)
    itens_m = "".join(f'<a href="#{a}">{esc(r)}</a>' for r, a in links)
    return f"""
<header class="topo">
  <div class="container">
    <div class="logo">{nome}<span class="ponto">.</span></div>
    <nav class="menu">{itens}
      <a href="{attr(ctx['wa_link'])}" class="btn-topo" target="_blank" rel="noopener">{svg('whatsapp',18)} WhatsApp</a>
    </nav>
    <button class="hamburguer" aria-label="Abrir menu" onclick="document.getElementById('menuMobile').classList.toggle('aberto')">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>
  </div>
  <div class="menu-mobile" id="menuMobile">{itens_m}
    <a href="{attr(ctx['wa_link'])}" target="_blank" rel="noopener">WhatsApp</a>
  </div>
</header>"""


def hero(ctx, titulo, sub, badge="", cta_secundario=("Ver mais", "servicos"), mostrar_nota=True):
    c = ctx
    if c["hero_img"]:
        estilo = (f'background-image:linear-gradient(rgba(0,0,0,.38),rgba(0,0,0,.74)),'
                  f'url(\'{attr(c["hero_img"])}\')')
        classe = "hero com-foto"
    else:
        estilo = ""
        classe = "hero sem-foto"
    badge_html = ""
    if badge:
        badge_html = f'<div class="hero-badge">{svg("premio",16)} {esc(badge)}</div>'
    nota_html = ""
    if mostrar_nota and c.get("tem_nota"):
        nota_html = (f'<div class="hero-nota">{estrelas(c["nota"],18)} '
                     f'<span><b>{esc(c["nota_fmt"])}</b> · {esc(c["avaliacoes"])} avaliações no Google</span></div>')
    rot_sec, anc_sec = cta_secundario
    return f"""
<section class="{classe}" id="inicio" style="{estilo}">
  <div class="container">
    {badge_html}
    <h1>{esc(titulo)}</h1>
    <p class="sub">{esc(sub)}</p>
    <div class="hero-ctas">
      <a href="{attr(c['wa_link'])}" class="btn btn-acento" target="_blank" rel="noopener">{svg('whatsapp',20)} {esc(c['termo_agendar'])}</a>
      <a href="#{attr(anc_sec)}" class="btn btn-outline">{esc(rot_sec)}</a>
    </div>
    {nota_html}
  </div>
</section>"""


def cabecalho_secao(rotulo, titulo, sub=""):
    r = f'<div class="rotulo">{esc(rotulo)}</div>' if rotulo else ""
    s = f'<p class="secao-sub">{esc(sub)}</p>' if sub else ""
    return f'<div class="secao-cabecalho revelar">{r}<h2 class="secao-titulo">{esc(titulo)}</h2>{s}</div>'


def card_servico(icone, titulo, desc, preco=None):
    p = ""
    if preco:
        p = f'<div class="preco"><small>a partir de</small><br>{esc(preco)}</div>'
    return f"""<div class="card revelar">
  <div class="icone-circulo">{svg(icone, 30)}</div>
  <h3>{esc(titulo)}</h3>
  <p>{esc(desc)}</p>{p}
</div>"""


def grid_servicos(ctx, servicos):
    """servicos: lista de dicts {titulo, descricao, preco?, icone?}."""
    icones = ctx["icones"]
    cards = []
    for i, s in enumerate(servicos):
        ic = s.get("icone") or icones[i % len(icones)]
        preco = s.get("preco") if ctx["mostra_preco"] else None
        cards.append(card_servico(ic, s.get("titulo", ""), s.get("descricao", ""), preco))
    return f'<div class="grid grid-3">{"".join(cards)}</div>'


def google_badge(ctx):
    c = ctx
    if not c.get("tem_nota"):
        return ""
    link = c["maps_url"] or "#"
    return f"""
<section class="fundo-claro" id="avaliacoes">
  <div class="container">
    <div class="google-badge revelar">
      <div class="selo-google">{svg('mapa',18)} Avaliações no Google</div>
      <div class="nota-grande">{esc(c['nota_fmt'])}</div>
      {estrelas(c['nota'], 24)}
      <p class="qtd">Baseado em <b>{esc(c['avaliacoes'])}</b> avaliações reais de clientes</p>
      <a href="{attr(link)}" target="_blank" rel="noopener">Ver no Google Maps {svg('mapa',16)}</a>
    </div>
  </div>
</section>"""


def galeria(ctx, rotulo=None):
    fotos = ctx["fotos"]
    rotulo = rotulo or ctx["rotulo_galeria"]
    if not fotos:
        return ""  # sem fotos reais: omite a seção inteira
    imgs = "".join(
        f'<img src="{attr(f)}" alt="{attr(ctx["nome"])} — {attr(ctx["categoria"])}" loading="lazy">'
        for f in fotos
    )
    return f"""
<section id="galeria">
  <div class="container">
    {cabecalho_secao("Galeria", rotulo)}
    <div class="galeria revelar">{imgs}</div>
  </div>
</section>"""


def sobre(ctx, texto):
    c = ctx
    if c["fotos"]:
        visual = f'<div class="sobre-visual revelar"><img src="{attr(c["fotos"][0])}" alt="{attr(c["nome"])}" loading="lazy"></div>'
    else:
        visual = f'<div class="sobre-visual bloco revelar">{svg(c["icones"][0], 90)}</div>'
    end = ""
    if c["endereco"]:
        end = f'<p><b>{svg("mapa",16)} Onde estamos:</b> {esc(c["endereco"])}</p>'
    paras = "".join(f"<p>{esc(p)}</p>" for p in texto.split("\n") if p.strip())
    return f"""
<section id="sobre">
  <div class="container">
    <div class="sobre-grid">
      <div class="sobre-texto revelar">
        <div class="rotulo">Sobre nós</div>
        <h2 class="secao-titulo" style="text-align:left">Conheça a {esc(c['nome'])}</h2>
        <div style="margin-top:20px">{paras}{end}</div>
      </div>
      {visual}
    </div>
  </div>
</section>"""


def _iniciais(nome):
    partes = [p for p in (nome or "").split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def depoimentos(ctx, lista):
    if not lista:
        return ""
    cards = []
    for d in lista:
        nome = d.get("nome", "Cliente")
        cards.append(f"""<div class="depoimento revelar">
  {estrelas(5,18)}
  <p>"{esc(d.get('texto',''))}"</p>
  <div class="autor">
    <div class="avatar">{esc(_iniciais(nome))}</div>
    <div><b>{esc(nome)}</b><span>{esc(d.get('meta','Cliente'))}</span></div>
  </div>
</div>""")
    return f"""
<section class="fundo-claro" id="depoimentos">
  <div class="container">
    {cabecalho_secao("Depoimentos", "O que dizem nossos clientes")}
    <div class="grid grid-3">{"".join(cards)}</div>
  </div>
</section>"""


def faixa_cta(ctx, titulo, texto):
    c = ctx
    return f"""
<section class="fundo-primaria faixa-cta">
  <div class="container revelar">
    <h2>{esc(titulo)}</h2>
    <p>{esc(texto)}</p>
    <a href="{attr(c['wa_link'])}" class="btn btn-acento" target="_blank" rel="noopener">{svg('whatsapp',20)} {esc(c['termo_agendar'])}</a>
  </div>
</section>"""


def contato(ctx):
    c = ctx
    itens = []
    if c["endereco"]:
        itens.append(f'<li><span class="ic">{svg("mapa",22)}</span><div><b>Endereço</b><span>{esc(c["endereco"])}</span></div></li>')
    if c["telefone"]:
        itens.append(f'<li><span class="ic">{svg("telefone",22)}</span><div><b>Telefone</b><span>{esc(c["telefone"])}</span></div></li>')
    itens.append(f'<li><span class="ic">{svg("relogio",22)}</span><div><b>Atendimento</b><span>Entre em contato e agende o melhor horário</span></div></li>')
    botoes = [f'<a href="{attr(c["wa_link"])}" class="btn btn-acento" target="_blank" rel="noopener">{svg("whatsapp",18)} WhatsApp</a>']
    if c["tel_link"] != "#":
        botoes.append(f'<a href="{attr(c["tel_link"])}" class="btn btn-primaria">{svg("telefone",18)} Ligar agora</a>')
    if c["maps_url"]:
        botoes.append(f'<a href="{attr(c["maps_url"])}" class="btn btn-primaria" target="_blank" rel="noopener">{svg("mapa",18)} Como chegar</a>')
    return f"""
<section id="contato" class="fundo-claro">
  <div class="container">
    {cabecalho_secao("Contato", "Fale com a gente")}
    <div class="contato-grid">
      <div class="revelar">
        <ul class="contato-info">{"".join(itens)}</ul>
        <div class="contato-botoes">{"".join(botoes)}</div>
      </div>
      <form class="contato revelar" onsubmit="return false">
        <div class="campo"><label>Nome</label><input type="text" placeholder="Seu nome" required></div>
        <div class="campo"><label>E-mail</label><input type="email" placeholder="seu@email.com"></div>
        <div class="campo"><label>Telefone / WhatsApp</label><input type="tel" placeholder="(00) 00000-0000"></div>
        <div class="campo"><label>Mensagem</label><textarea placeholder="Como podemos ajudar?"></textarea></div>
        <button type="submit" class="btn btn-acento">Enviar mensagem</button>
      </form>
    </div>
  </div>
</section>"""


def rodape(ctx):
    c = ctx
    ano = 2026
    return f"""
<footer class="rodape">
  <div class="container">
    <div class="logo">{esc(c['nome'])}<span class="ponto">.</span></div>
    <p>{esc(c['categoria'])}{(' em ' + esc(c['cidade'])) if c['cidade'] else ''}</p>
    <p class="mini">© {ano} {esc(c['nome'])} · Todos os direitos reservados</p>
  </div>
</footer>"""


_ICONES_STAT = ["premio", "grupo", "estrela", "relogio", "crescimento", "polegar"]


def numeros(ctx, itens):
    """Faixa de estatísticas. itens: lista de {valor, rotulo}."""
    if not itens:
        return ""
    cards = []
    for i, n in enumerate(itens[:4]):
        valor = str(n.get("valor", "")).strip()
        # separa sufixo (+, %, etc.) para estilizar
        num, suf = valor, ""
        if valor and valor[-1] in "+%kKmM":
            num, suf = valor[:-1], valor[-1]
        ic = _ICONES_STAT[i % len(_ICONES_STAT)]
        cards.append(f"""<div class="stat revelar">
  <div class="stat-ic">{svg(ic, 26)}</div>
  <div class="valor">{esc(num)}<small>{esc(suf)}</small></div>
  <div class="rotulo">{esc(n.get('rotulo',''))}</div>
</div>""")
    return f"""
<section class="numeros" id="numeros">
  <div class="container">
    <div class="numeros-grid">{"".join(cards)}</div>
  </div>
</section>"""


def faq(ctx, itens):
    """Perguntas frequentes (accordion nativo). itens: lista de {pergunta, resposta}."""
    if not itens:
        return ""
    linhas = []
    for f in itens[:6]:
        linhas.append(f"""<details class="faq-item revelar">
  <summary>{esc(f.get('pergunta',''))}<span class="chev">{svg('seta-baixo',20)}</span></summary>
  <div class="resposta">{esc(f.get('resposta',''))}</div>
</details>""")
    return f"""
<section id="faq">
  <div class="container">
    {cabecalho_secao("Dúvidas", "Perguntas frequentes")}
    <div class="faq-lista">{"".join(linhas)}</div>
  </div>
</section>"""


def wa_float(ctx):
    return (f'<a href="{attr(ctx["wa_link"])}" class="wa-float" target="_blank" '
            f'rel="noopener" aria-label="Falar no WhatsApp">{svg("whatsapp",30)}</a>')


def barra_mobile(ctx):
    """Barra fixa de ação no rodapé (só mobile via CSS)."""
    c = ctx
    tel = ""
    if c["tel_link"] != "#":
        tel = f'<a href="{attr(c["tel_link"])}" class="tel">{svg("telefone",18)} Ligar</a>'
    return (f'<div class="barra-mobile">'
            f'<a href="{attr(c["wa_link"])}" class="wa" target="_blank" rel="noopener">'
            f'{svg("whatsapp",18)} WhatsApp</a>{tel}</div>')


def scripts():
    return """
<script>
(function(){
  var m=document.getElementById('menuMobile');
  if(m){m.querySelectorAll('a').forEach(function(a){a.addEventListener('click',function(){m.classList.remove('aberto');});});}
  var obs=new IntersectionObserver(function(es){
    es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('visivel'); obs.unobserve(e.target); } });
  },{threshold:0.12});
  document.querySelectorAll('.revelar').forEach(function(el){obs.observe(el);});
})();
</script>"""


def _jsonld(ctx):
    import json
    c = ctx
    dados = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": c["nome"],
        "description": f'{c["categoria"]}{(" em " + c["cidade"]) if c["cidade"] else ""}',
    }
    if c["endereco"] or c["cidade"]:
        dados["address"] = {
            "@type": "PostalAddress",
            "streetAddress": c["endereco"],
            "addressLocality": c["cidade"],
            "addressCountry": "BR",
        }
    if c["telefone"]:
        dados["telephone"] = c["telefone"]
    if c.get("tem_nota"):
        dados["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": c["nota_fmt"],
            "reviewCount": str(c["avaliacoes"]),
        }
    if c["fotos"]:
        dados["image"] = c["fotos"][0]
    return ('<script type="application/ld+json">'
            + json.dumps(dados, ensure_ascii=False) + '</script>')


def _favicon(ctx):
    """Favicon emoji do nicho, embutido como SVG data URI (zero requisição externa)."""
    from urllib.parse import quote
    emoji = ctx.get("emoji") or "⭐"
    svg_ico = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
        f"<text y='.9em' font-size='90'>{emoji}</text></svg>"
    )
    return f'<link rel="icon" href="data:image/svg+xml,{quote(svg_ico)}">'


def documento(ctx, corpo, meta_desc=""):
    """Monta o HTML final completo."""
    c = ctx
    titulo = f'{c["nome"]} — {c["categoria"]}' + (f' em {c["cidade"]}' if c["cidade"] else "")
    desc = meta_desc or f'{c["nome"]}: {c["categoria"]}{(" em " + c["cidade"]) if c["cidade"] else ""}. Entre em contato e agende.'
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(titulo)}</title>
<meta name="description" content="{attr(desc[:155])}">
{_favicon(ctx)}
<meta property="og:title" content="{attr(titulo)}">
<meta property="og:description" content="{attr(desc[:155])}">
<meta property="og:type" content="website">
{f'<meta property="og:image" content="{attr(c["fotos"][0])}">' if c["fotos"] else ""}
<style>{css_base(c)}</style>
{_jsonld(ctx)}
</head>
<body>
{corpo}
{barra_mobile(ctx)}
{wa_float(ctx)}
{scripts()}
</body>
</html>"""
