"""Componentes de landing page que dependem estritamente de dados confirmados.

Mantidos separados do arquivo visual grande para que as regras de conteúdo
factual sejam fáceis de revisar sem reescrever a biblioteca de componentes.
"""
from .components import attr, cabecalho_secao, esc
from .icons import svg


def faixa_cta(ctx, titulo, texto):
    """CTA sem presumir agendamento, reserva, orçamento ou outro serviço."""
    botao = ""
    if ctx.get("wa_link") and ctx["wa_link"] != "#":
        botao = (
            f'<a href="{attr(ctx["wa_link"])}" class="btn btn-acento" '
            f'target="_blank" rel="noopener">{svg("whatsapp", 20)} WhatsApp</a>'
        )
    return f"""
<section class="fundo-primaria faixa-cta">
  <div class="container revelar">
    <h2>{esc(titulo)}</h2>
    <p>{esc(texto)}</p>
    {botao}
  </div>
</section>"""


def contato(ctx):
    """Mostra somente endereço/telefone/Maps que realmente existem no contexto."""
    itens = []
    botoes = []

    if ctx.get("endereco"):
        itens.append(
            f'<li><span class="ic">{svg("mapa",22)}</span>'
            f'<div><b>Endereço</b><span>{esc(ctx["endereco"])}</span></div></li>'
        )
    if ctx.get("telefone"):
        itens.append(
            f'<li><span class="ic">{svg("telefone",22)}</span>'
            f'<div><b>Telefone</b><span>{esc(ctx["telefone"])}</span></div></li>'
        )
    if ctx.get("wa_link") and ctx["wa_link"] != "#":
        botoes.append(
            f'<a href="{attr(ctx["wa_link"])}" class="btn btn-acento" '
            f'target="_blank" rel="noopener">{svg("whatsapp",18)} WhatsApp</a>'
        )
    if ctx.get("tel_link") and ctx["tel_link"] != "#":
        botoes.append(
            f'<a href="{attr(ctx["tel_link"])}" class="btn btn-primaria">'
            f'{svg("telefone",18)} Ligar</a>'
        )
    if ctx.get("maps_url"):
        botoes.append(
            f'<a href="{attr(ctx["maps_url"])}" class="btn btn-primaria" '
            f'target="_blank" rel="noopener">{svg("mapa",18)} Como chegar</a>'
        )

    if not itens and not botoes:
        return ""

    return f"""
<section id="contato" class="fundo-claro">
  <div class="container">
    {cabecalho_secao("Contato", f"Fale com a {ctx.get('nome') or 'empresa'}")}
    <div class="revelar">
      <ul class="contato-info">{"".join(itens)}</ul>
      <div class="contato-botoes">{"".join(botoes)}</div>
    </div>
  </div>
</section>"""
