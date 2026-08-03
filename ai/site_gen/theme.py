"""
Detecção de nicho + tema visual por nicho.
Cada nicho define: cores, arquétipo de layout, ícones padrão, rótulos das
seções e se mostra preço nos serviços.
"""


def _escurecer(hex_cor, fator=0.72):
    h = (hex_cor or "").lstrip("#")
    if len(h) != 6:
        return hex_cor
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_cor
    r, g, b = (max(0, int(c * fator)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _clarear(hex_cor, fator=1.35):
    h = (hex_cor or "").lstrip("#")
    if len(h) != 6:
        return hex_cor
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_cor
    r, g, b = (min(255, int(c * fator)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Nichos ─────────────────────────────────────────────────────────────────────
# archetype: qual função de layout usar (ver layouts.py)
# mostra_preco: exibe preço nos cards de serviço
# icones: ícones padrão dos cards (usados se a IA não sugerir)

_NICHOS = {
    "barbearia": {
        "keywords": ["barbearia", "barber", "barbeir"],
        "cor_primaria": "#15151f", "cor_acento": "#c8a96e", "emoji": "💈",
        "archetype": "agendamento", "mostra_preco": True,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Nossos Cortes",
        "termo_agendar": "Agende seu horário",
        "icones": ["tesoura", "navalha", "pente", "spray", "premio", "relogio"],
    },
    "salao": {
        "keywords": ["salão", "salao", "beleza", "cabeler", "estética", "estetica",
                     "manicure", "nail", "sobrancelha", "depila", "maquiagem", "spa"],
        "cor_primaria": "#2d1b4e", "cor_acento": "#e8709f", "emoji": "💅",
        "archetype": "agendamento", "mostra_preco": True,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Nossos Trabalhos",
        "termo_agendar": "Agende seu horário",
        "icones": ["batom", "tesoura", "spray", "coracao", "premio", "estrela"],
    },
    "pet": {
        "keywords": ["petshop", "pet shop", "pet ", "banho e tosa", "banho & tosa",
                     "tosa", "agropet", "agro pet", "ração", "racao", "aquarismo"],
        "cor_primaria": "#12333a", "cor_acento": "#ff8c42", "emoji": "🐾",
        "archetype": "pet", "mostra_preco": True,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Nossos Pets",
        "termo_agendar": "Agende banho & tosa",
        "icones": ["pata", "osso", "tesoura", "coracao", "premio", "relogio"],
    },
    "academia": {
        "keywords": ["academia", "fitness", "musculação", "musculacao", "crossfit",
                     "pilates", "yoga", "personal", "gym"],
        "cor_primaria": "#0d0d12", "cor_acento": "#00d9a3", "emoji": "💪",
        "archetype": "agendamento", "mostra_preco": True,
        "rotulo_servicos": "Modalidades", "rotulo_galeria": "Nossa Estrutura",
        "termo_agendar": "Faça sua aula experimental",
        "icones": ["haltere", "chama", "coracao-batida", "raio", "premio", "relogio"],
    },
    "restaurante": {
        "keywords": ["restaurante", "lanchonete", "pizzaria", "hamburger", "hamburguer",
                     "açougue", "acougue", "padaria", "pastelaria", "sushi", "churrascaria",
                     "comida", "boteco", "bar ", "cafeteria", "cafe", "café", "sorveteria",
                     "doceria", "confeitaria", "marmita", "espetinho"],
        "cor_primaria": "#1a0a03", "cor_acento": "#e07b1a", "emoji": "🍽️",
        "archetype": "gastronomia", "mostra_preco": True,
        "rotulo_servicos": "Nosso Cardápio", "rotulo_galeria": "Nossos Pratos",
        "termo_agendar": "Peça agora",
        "icones": ["prato", "talheres", "chef", "cafe", "delivery", "estrela"],
    },
    "educacao": {
        "keywords": ["escola", "colégio", "colegio", "curso", "idiomas", "inglês", "ingles",
                     "reforço", "reforco", "autoescola", "auto escola", "auto-escola", "cfc",
                     "faculdade", "universidade", "creche", "berçário", "bercario", "ensino",
                     "pré-escola", "educação", "educacao", "vestibular", "concurso"],
        "cor_primaria": "#12224a", "cor_acento": "#ffb703", "emoji": "🎓",
        "archetype": "educacao", "mostra_preco": False,
        "rotulo_servicos": "Cursos & Turmas", "rotulo_galeria": "Nossa Estrutura",
        "termo_agendar": "Faça sua matrícula",
        "icones": ["livro", "formatura", "lousa", "grupo", "premio", "check"],
    },
    "clinica": {
        "keywords": ["clínica", "clinica", "médico", "medico", "dentista", "odonto",
                     "saúde", "saude", "farmácia", "farmacia", "hospital", "veterinár",
                     "veterinar", "fisioterapia", "psicolog", "nutric", "laboratório",
                     "laboratorio", "consultório", "consultorio"],
        "cor_primaria": "#0a3d62", "cor_acento": "#2ea3f2", "emoji": "⚕️",
        "archetype": "saude", "mostra_preco": False,
        "rotulo_servicos": "Especialidades", "rotulo_galeria": "Nossa Estrutura",
        "termo_agendar": "Agende sua consulta",
        "icones": ["cruz-medica", "estetoscopio", "coracao-batida", "escudo", "relogio", "check"],
    },
    "auto": {
        "keywords": ["automotiv", "automóvel", "automovel", "mecânic", "mecanica", "oficina",
                     "car wash", "borracharia", "funilaria", "pneu", "lava jato", "lava-jato",
                     "lava rápido", "guincho", "auto center", "autopeças", "auto peças",
                     "auto elétric", "insulfilm", "martelinho"],
        "cor_primaria": "#17171a", "cor_acento": "#e63946", "emoji": "🚗",
        "archetype": "tecnico", "mostra_preco": False,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Nosso Trabalho",
        "termo_agendar": "Solicite um orçamento",
        "icones": ["carro", "chave-fenda", "engrenagem", "escudo", "relogio", "check"],
    },
    "construcao": {
        "keywords": ["construtora", "construção", "construcao", "reforma", "pedreiro",
                     "pintor", "pintura", "marcenaria", "marceneiro", "serralheria",
                     "serralheiro", "vidraçaria", "vidracaria", "gesso", "drywall",
                     "engenharia", "empreiteira", "eletricista", "encanador", "hidráulic",
                     "telhado", "obra", "marmoraria", "esquadrias", "arquitet"],
        "cor_primaria": "#1c1c1e", "cor_acento": "#f4a300", "emoji": "🏗️",
        "archetype": "tecnico", "mostra_preco": False,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Obras & Projetos",
        "termo_agendar": "Solicite um orçamento",
        "icones": ["capacete", "rolo", "trena", "martelo", "escudo", "check"],
    },
    "limpeza": {
        "keywords": ["limpeza", "diarista", "faxina", "faxineira", "dedetiza", "dedetização",
                     "higieniz", "lavanderia", "lava a seco", "passadoria", "desentupidora",
                     "conservação e limpeza", "jardinagem e limpeza"],
        "cor_primaria": "#063a4f", "cor_acento": "#22c1a4", "emoji": "🧽",
        "archetype": "tecnico", "mostra_preco": False,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Antes & Depois",
        "termo_agendar": "Solicite um orçamento",
        "icones": ["vassoura", "balde", "spray", "escudo", "relogio", "check"],
    },
    "assistencia": {
        "keywords": ["assistência técnica", "assistencia tecnica", "conserto", "celular",
                     "smartphone", "informática", "informatica", "notebook", "eletrônic",
                     "eletronico", "refrigeração", "refrigeracao", "ar-condicionado",
                     "ar condicionado", "climatização", "reparo"],
        "cor_primaria": "#101826", "cor_acento": "#2f80ed", "emoji": "🔧",
        "archetype": "tecnico", "mostra_preco": False,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Nosso Trabalho",
        "termo_agendar": "Solicite um orçamento",
        "icones": ["celular", "computador", "chave-fenda", "engrenagem", "escudo", "relogio"],
    },
    "moda": {
        "keywords": ["loja de roupas", "boutique", "moda", "confecção", "calçados", "calcados",
                     "sapataria", "ótica", "otica", "joalheria", "joias", "semijoias",
                     "semijoia", "acessórios", "bijuteria", "vestuário", "vestuario",
                     "brechó", "brecho", "lingerie"],
        "cor_primaria": "#1a1420", "cor_acento": "#d6336c", "emoji": "🛍️",
        "archetype": "varejo", "mostra_preco": True,
        "rotulo_servicos": "Nossos Produtos", "rotulo_galeria": "Coleção",
        "termo_agendar": "Ver novidades",
        "icones": ["sacola", "cabide", "etiqueta", "estrela", "premio", "coracao"],
    },
    "floricultura": {
        "keywords": ["floricultura", "flores", "floral", "buquê", "buque", "jardinagem",
                     "paisagismo", "viveiro de plantas", "flores e presentes"],
        "cor_primaria": "#14331f", "cor_acento": "#e8639b", "emoji": "🌸",
        "archetype": "varejo", "mostra_preco": True,
        "rotulo_servicos": "Nossos Produtos", "rotulo_galeria": "Nossos Arranjos",
        "termo_agendar": "Fazer pedido",
        "icones": ["flor", "coracao", "sacola", "estrela", "premio", "delivery"],
    },
    "eventos": {
        "keywords": ["buffet", "festa", "eventos", "cerimonial", "salão de festa",
                     "salao de festa", "decoração de festa", "fotografia", "fotógrafo",
                     "fotografo", "filmagem", "banda", "assessoria de eventos", "casamento",
                     "aluguel de brinquedo", "recreação"],
        "cor_primaria": "#241436", "cor_acento": "#f7b500", "emoji": "🎉",
        "archetype": "eventos", "mostra_preco": False,
        "rotulo_servicos": "Nossos Pacotes", "rotulo_galeria": "Momentos",
        "termo_agendar": "Solicite um orçamento",
        "icones": ["balao", "bolo", "camera", "musica", "estrela", "premio"],
    },
    "hotel": {
        "keywords": ["hotel", "pousada", "hostel", "turismo", "resort", "chalé", "chale",
                     "camping", "flat"],
        "cor_primaria": "#16263f", "cor_acento": "#d4af37", "emoji": "🏨",
        "archetype": "hospitalidade", "mostra_preco": False,
        "rotulo_servicos": "Acomodações & Comodidades", "rotulo_galeria": "Conheça o Espaço",
        "termo_agendar": "Reserve agora",
        "icones": ["cama", "wifi", "piscina", "cafe", "mapa", "chave-hotel"],
    },
    "transporte": {
        "keywords": ["transportadora", "mudança", "mudanca", "mudanças", "frete", "carreto",
                     "logística", "logistica", "transporte de", "fretes"],
        "cor_primaria": "#14202e", "cor_acento": "#ff6b35", "emoji": "🚚",
        "archetype": "tecnico", "mostra_preco": False,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Nossa Frota",
        "termo_agendar": "Solicite um orçamento",
        "icones": ["caminhao", "delivery", "mapa", "escudo", "relogio", "check"],
    },
    "imobiliaria": {
        "keywords": ["imobiliária", "imobiliaria", "imóveis", "imoveis", "corretor de imóveis",
                     "corretor", "incorporadora", "loteamento"],
        "cor_primaria": "#10233b", "cor_acento": "#2ec4b6", "emoji": "🏠",
        "archetype": "profissional", "mostra_preco": False,
        "rotulo_servicos": "Nossos Imóveis", "rotulo_galeria": "Destaques",
        "termo_agendar": "Agende uma visita",
        "icones": ["casa", "chave-casa", "predio", "mapa", "documento", "check"],
    },
    "advocacia": {
        "keywords": ["advogad", "advocacia", "jurídic", "juridico", "contábil", "contabil",
                     "contador", "escritório", "escritorio", "consultoria", "seguros",
                     "despachante"],
        "cor_primaria": "#0d1b2a", "cor_acento": "#c9a24a", "emoji": "⚖️",
        "archetype": "profissional", "mostra_preco": False,
        "rotulo_servicos": "Áreas de Atuação", "rotulo_galeria": "Nosso Escritório",
        "termo_agendar": "Agende uma consulta",
        "icones": ["balanca", "documento", "escudo", "predio", "check", "premio"],
    },
    "generico": {
        "keywords": [],
        "cor_primaria": "#1a1a2a", "cor_acento": "#e67e22", "emoji": "⭐",
        "archetype": "generico", "mostra_preco": False,
        "rotulo_servicos": "Nossos Serviços", "rotulo_galeria": "Galeria",
        "termo_agendar": "Fale conosco",
        "icones": ["estrela", "check", "escudo", "coracao", "premio", "raio"],
    },
}


def detectar_nicho(categoria):
    """Retorna a chave do nicho a partir da categoria/descrição."""
    cat = (categoria or "").lower()
    for chave, cfg in _NICHOS.items():
        if chave == "generico":
            continue
        if any(kw in cat for kw in cfg["keywords"]):
            return chave
    return "generico"


_ROTULO_NICHO = {
    "barbearia": "Barbearia", "salao": "Salão & Beleza", "pet": "Pet Shop / Banho & Tosa",
    "academia": "Academia & Fitness", "restaurante": "Restaurante & Alimentação",
    "educacao": "Escola / Curso / Autoescola", "clinica": "Clínica & Saúde",
    "auto": "Automotivo & Oficina", "construcao": "Construção & Reforma",
    "limpeza": "Limpeza & Conservação", "assistencia": "Assistência Técnica",
    "moda": "Moda & Varejo", "floricultura": "Floricultura & Jardim",
    "eventos": "Eventos & Festas", "hotel": "Hotel & Pousada",
    "transporte": "Transporte & Mudanças", "imobiliaria": "Imobiliária",
    "advocacia": "Advocacia & Contabilidade", "generico": "Outros (layout genérico)",
}


def listar_nichos():
    """Lista os nichos suportados (para exibir no painel). generico é o fallback."""
    out = []
    for chave, cfg in _NICHOS.items():
        out.append({
            "nicho": chave,
            "rotulo": _ROTULO_NICHO.get(chave, chave.capitalize()),
            "emoji": cfg.get("emoji", "⭐"),
            "archetype": cfg["archetype"],
            "fallback": chave == "generico",
        })
    return out


def tema(categoria):
    """Retorna o tema completo (dict) para a categoria informada."""
    chave = detectar_nicho(categoria)
    base = dict(_NICHOS[chave])
    base["nicho"] = chave
    base["cor_primaria_escura"] = _escurecer(base["cor_primaria"])
    base["cor_acento_escura"] = _escurecer(base["cor_acento"], 0.85)
    base["cor_acento_clara"] = _clarear(base["cor_acento"])
    return base
