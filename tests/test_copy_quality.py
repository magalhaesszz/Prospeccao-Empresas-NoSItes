from ai.copy_rules import (
    fallback_primeiro_contato,
    is_whatsapp_task,
    limpar_texto_whatsapp,
    mensagem_prospeccao_aceitavel,
    with_whatsapp_system,
)
from ai.site_gen.content import gerar_conteudo
from ai.site_gen.factual_components import contato
from whatsapp.humanizar import humanizar_mensagem


def test_fallback_primeiro_contato_oferece_site_de_imediato():
    msg = fallback_primeiro_contato("Barbearia Central")
    assert "Barbearia Central" in msg
    assert "site" in msg.lower()
    assert "trabalho com criação de sites" in msg.lower()
    assert "🚀" not in msg


def test_fallback_usa_nota_e_avaliacoes_reais_para_elogio():
    msg = fallback_primeiro_contato(
        nome="Barbearia Central",
        nota=4.8,
        avaliacoes=137,
        categoria="Barbearia",
        cidade="Goiânia",
    )
    baixo = msg.lower()
    assert "4,8" in msg
    assert "137 avaliações" in msg
    assert "muito bem avaliados" in baixo
    assert "site" in baixo


def test_fallback_nao_elogia_nota_baixa_como_excelente():
    msg = fallback_primeiro_contato(
        nome="Oficina Central",
        nota=3.9,
        avaliacoes=42,
    )
    baixo = msg.lower()
    assert "3,9" in msg
    assert "42 avaliações" in msg
    assert "muito bem avaliados" not in baixo
    assert "avaliação bem forte" not in baixo
    assert "site" in baixo


def test_fallback_com_previa_oferece_site_e_mantem_link_exato():
    link = "https://exemplo.com/p/barbearia-central"
    msg = fallback_primeiro_contato(
        nome="Barbearia Central",
        preview_url=link,
        nota=4.9,
        avaliacoes=220,
    )
    assert link in msg
    assert "montei uma prévia" in msg.lower()
    assert "site" in msg.lower()


def test_limpeza_remove_caracteres_invisiveis_e_markdown():
    msg = limpar_texto_whatsapp('**Oi,\u200b tudo certo?**')
    assert msg == "Oi, tudo certo?"
    assert "\u200b" not in msg


def test_humanizacao_nao_insere_variacao_invisivel():
    msg = humanizar_mensagem("Oi, tudo certo?", variar_invisivel=True)
    assert msg == "Oi, tudo certo?"


def test_validador_rejeita_template_comercial_legado_e_abertura_sem_oferta():
    legado = (
        "Olá, Empresa! 👋 Meu nome é Matheus e trabalho com presença digital. "
        "Gostaria de apresentar uma solução personalizada para potencializar seus resultados. 🚀"
    )
    sem_oferta = "Oi, tudo certo? Tô falando com o pessoal da Empresa?"
    direto = (
        "Oi, vi a Empresa no Google, com nota 4,8 e 120 avaliações. "
        "Eu trabalho com criação de sites e queria montar um site profissional pra vocês. Posso te mostrar uma ideia?"
    )

    assert mensagem_prospeccao_aceitavel(legado) is False
    assert mensagem_prospeccao_aceitavel(sem_oferta) is False
    assert mensagem_prospeccao_aceitavel(direto) is True


def test_compat_aplica_system_so_em_tarefa_de_whatsapp():
    wa = [{"role": "user", "content": "Crie uma mensagem curta para WhatsApp."}]
    analise = [{"role": "user", "content": "Analise estes prospects e gere um ranking."}]

    assert is_whatsapp_task(wa) is True
    system = with_whatsapp_system(wa)[0]
    assert system["role"] == "system"
    assert "oferecer criação de site já na primeira mensagem" in system["content"].lower()
    assert is_whatsapp_task(analise) is False
    assert with_whatsapp_system(analise) == analise


def test_site_descarta_fatos_inventados_pelo_modelo():
    ctx = {
        "nome": "Oficina Central",
        "categoria": "Oficina mecânica",
        "cidade": "Goiânia",
        "endereco": "Rua A, 10",
        "telefone": "62999999999",
        "tem_nota": True,
        "nota_fmt": "4.8",
        "avaliacoes": 137,
    }

    def gerar_fn(*args, **kwargs):
        return '''{
          "hero_titulo": "Oficina Central em Goiânia",
          "hero_subtitulo": "Oficina mecânica em Goiânia.",
          "hero_badge": "Goiânia",
          "sobre": "Oficina Central — oficina mecânica em Goiânia.",
          "cta_titulo": "Fale com a Oficina Central",
          "cta_texto": "Entre em contato para tirar dúvidas.",
          "meta_description": "Oficina Central — oficina mecânica em Goiânia.",
          "servicos": [{"titulo": "Troca de óleo", "preco": "R$ 89"}],
          "depoimentos": [{"nome": "Carlos", "texto": "Excelente!"}],
          "numeros": [{"valor": "+500", "rotulo": "clientes"}],
          "faq": [{"pergunta": "Horário?", "resposta": "8h às 18h"}]
        }'''

    conteudo = gerar_conteudo(ctx, "fake-key", gerar_fn)

    assert conteudo["depoimentos"] == []
    assert all("500" not in item["valor"] for item in conteudo["numeros"])
    assert {item["valor"] for item in conteudo["numeros"]} == {"4.8", "137"}
    assert "R$ 89" not in str(conteudo["servicos"])
    assert "8h às 18h" not in str(conteudo["faq"])
    assert conteudo["servicos"][0]["titulo"] == "Oficina mecânica"


def test_contato_nao_inventa_horario_agendamento_ou_formulario():
    html = contato({
        "nome": "Oficina Central",
        "endereco": "Rua A, 10",
        "telefone": "(62) 99999-9999",
        "wa_link": "https://wa.me/5562999999999",
        "tel_link": "tel:+5562999999999",
        "maps_url": "https://maps.google.com/example",
    })

    baixo = html.lower()
    assert "agende" not in baixo
    assert "horário" not in baixo
    assert "<form" not in baixo
    assert "rua a, 10" in baixo
    assert "(62) 99999-9999" in html
