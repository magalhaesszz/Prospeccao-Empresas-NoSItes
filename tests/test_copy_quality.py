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


def test_fallback_primeiro_contato_e_curto_e_nao_inventa_previa():
    msg = fallback_primeiro_contato("Barbearia Central")
    assert msg == "Oi, tudo certo? Tô falando com o pessoal da Barbearia Central?"
    assert "site" not in msg.lower()
    assert "🚀" not in msg


def test_limpeza_remove_caracteres_invisiveis_e_markdown():
    msg = limpar_texto_whatsapp('**Oi,\u200b tudo certo?**')
    assert msg == "Oi, tudo certo?"
    assert "\u200b" not in msg


def test_humanizacao_nao_insere_variacao_invisivel():
    msg = humanizar_mensagem("Oi, tudo certo?", variar_invisivel=True)
    assert msg == "Oi, tudo certo?"


def test_validador_rejeita_template_comercial_legado():
    legado = (
        "Olá, Empresa! 👋 Meu nome é Matheus e trabalho com presença digital. "
        "Gostaria de apresentar uma solução personalizada para potencializar seus resultados. 🚀"
    )
    natural = "Oi, tudo certo? Fiz uma prévia de site pra vocês aqui. Posso te mandar?"

    assert mensagem_prospeccao_aceitavel(legado) is False
    assert mensagem_prospeccao_aceitavel(natural) is True


def test_compat_aplica_system_so_em_tarefa_de_whatsapp():
    wa = [{"role": "user", "content": "Crie uma mensagem curta para WhatsApp."}]
    analise = [{"role": "user", "content": "Analise estes prospects e gere um ranking."}]

    assert is_whatsapp_task(wa) is True
    assert with_whatsapp_system(wa)[0]["role"] == "system"
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
