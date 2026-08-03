"""
Ícones SVG inline (stroke currentColor) — zero dependências externas.
Todos 24x24 viewBox, herdam a cor do elemento pai via `currentColor`.
Use ICONES.get(chave, ICONES["estrela"]) para nunca quebrar.
"""

# Cada valor é o miolo do <svg> (paths). O wrapper é aplicado por `svg()`.
_PATHS = {
    # genéricos / confiança
    "estrela":     '<path d="M12 2l2.9 6.3 6.9.7-5.2 4.6 1.5 6.8L12 17.8 5.9 21.2l1.5-6.8L2.2 9.8l6.9-.7L12 2z"/>',
    "escudo":      '<path d="M12 2l8 4v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10V6l8-4z"/><path d="M9 12l2 2 4-4"/>',
    "check":       '<path d="M20 6L9 17l-5-5"/>',
    "relogio":     '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "mapa":        '<path d="M12 21s7-5.7 7-11a7 7 0 10-14 0c0 5.3 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "telefone":    '<path d="M22 16.9v3a2 2 0 01-2.2 2 19.8 19.8 0 01-8.6-3.1 19.5 19.5 0 01-6-6A19.8 19.8 0 012 4.2 2 2 0 014 2h3a2 2 0 012 1.7c.1 1 .4 1.9.7 2.8a2 2 0 01-.5 2.1L8.1 9.8a16 16 0 006 6l1.2-1.1a2 2 0 012.1-.5c.9.3 1.8.6 2.8.7a2 2 0 011.7 2z"/>',
    "whatsapp":    '<path d="M12 2a10 10 0 00-8.5 15.2L2 22l4.9-1.3A10 10 0 1012 2z"/><path d="M8.5 7.5c-.3 0-.6.1-.8.4-.3.3-1 1-1 2.3s1 2.7 1.2 2.9c.1.2 2 3.1 4.9 4.3 2.4 1 2.9.8 3.4.8.5-.1 1.6-.7 1.9-1.3.2-.6.2-1.2.2-1.3l-.9-.5c-.4-.2-1.2-.6-1.4-.7-.2-.1-.4-.1-.5.1l-.7.9c-.1.2-.3.2-.5.1-.7-.3-1.5-.7-2.4-1.7-.7-.7-1.1-1.5-1.3-1.8-.1-.2 0-.4.1-.5l.4-.5c.1-.2.2-.3.2-.5v-.5c0-.1-.5-1.3-.7-1.7-.2-.4-.4-.4-.5-.4z"/>',
    "email":       '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "coracao":     '<path d="M12 21s-7-4.5-9.5-9A5 5 0 0112 4a5 5 0 019.5 8c-2.5 4.5-9.5 9-9.5 9z"/>',
    "raio":        '<path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z"/>',
    "premio":      '<circle cx="12" cy="8" r="6"/><path d="M8.2 13.5L7 22l5-3 5 3-1.2-8.5"/>',

    # beleza / barbearia
    "tesoura":     '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 12.5L20 20M8.1 8.1L12 12"/>',
    "navalha":     '<path d="M4 20l7-7"/><path d="M11 13l7-7a2.8 2.8 0 00-4-4l-7 7 4 4z"/>',
    "pente":       '<path d="M3 7h18M6 7v6M10 7v6M14 7v6M18 7v6"/>',
    "spray":       '<rect x="7" y="9" width="8" height="12" rx="2"/><path d="M9 9V6h4v3M18 4h.01M20 6h.01M18 8h.01"/>',
    "batom":       '<path d="M9 21h6v-8H9z"/><path d="M10 13l-1-6 3-4 3 4-1 6"/>',

    # gastronomia
    "prato":       '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    "talheres":    '<path d="M6 3v7a2 2 0 002 2v9M6 3v4M9 3v4M18 3s-2 2-2 6 2 4 2 4v8"/>',
    "chef":        '<path d="M6 13a4 4 0 01-1-7.9A4 4 0 0112 4a4 4 0 017 1 4 4 0 01-1 8v6a2 2 0 01-2 2H8a2 2 0 01-2-2v-6z"/>',
    "cafe":        '<path d="M4 8h13v5a4 4 0 01-4 4H8a4 4 0 01-4-4V8z"/><path d="M17 9h2a2 2 0 010 4h-2M7 3v2M11 3v2"/>',
    "delivery":    '<circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/><path d="M3 5h2l1.5 10h10l2-7H6"/>',

    # saúde
    "cruz-medica": '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>',
    "estetoscopio":'<path d="M6 3v6a4 4 0 008 0V3"/><path d="M10 15a5 5 0 0010 0v-1"/><circle cx="20" cy="12" r="2"/>',
    "dente":       '<path d="M12 5c-2-2-6-2-7 1s0 6 1 9 1 5 2.5 5 1.5-4 3.5-4 2 4 3.5 4 1-6 2-9 1-6-2-7-4 0-5 1z"/>',
    "coracao-batida":'<path d="M3 12h4l2-5 3 10 2-7 2 2h5"/>',

    # academia
    "haltere":     '<path d="M4 8v8M8 6v12M16 6v12M20 8v8M8 12h8"/>',
    "chama":       '<path d="M12 3c2 4-1 5 0 8a3 3 0 11-4 0c-1-3 2-3 0-6 3 1 4 4 4 4s2-2 1-4a5 5 0 11-1 6"/>',

    # auto
    "carro":       '<path d="M3 13l2-6h14l2 6M5 13h14v5H5z"/><circle cx="7.5" cy="18" r="1.5"/><circle cx="16.5" cy="18" r="1.5"/>',
    "chave-fenda": '<path d="M14 4l6 6-3 3-6-6zM11 7L3 15v6h6l8-8"/>',
    "engrenagem":  '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',

    # hotel
    "cama":        '<path d="M3 18v-6h18v6M3 12V7h18M7 12v-2h4v2"/>',
    "wifi":        '<path d="M5 12a10 10 0 0114 0M8 15a6 6 0 018 0M12 18h.01"/>',
    "piscina":     '<path d="M3 18c1.5 0 1.5-1 3-1s1.5 1 3 1 1.5-1 3-1 1.5 1 3 1 1.5-1 3-1M6 15V6a2 2 0 014 0M6 10h4"/>',
    "chave-hotel": '<circle cx="8" cy="8" r="4"/><path d="M11 11l7 7M16 16l2-2M18 18l2-2"/>',

    # jurídico / profissional
    "balanca":     '<path d="M12 3v18M7 21h10M5 7l7-2 7 2M5 7l-2 6a4 4 0 008 0L5 7M19 7l-2 6a4 4 0 008 0l-2-6"/>',
    "documento":   '<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v4h4M9 12h6M9 16h6"/>',
    "predio":      '<rect x="4" y="3" width="16" height="18"/><path d="M8 7h2M14 7h2M8 11h2M14 11h2M8 15h2M14 15h2"/>',

    # pet
    "pata":        '<circle cx="5.5" cy="12" r="1.8"/><circle cx="9.5" cy="7.5" r="1.8"/><circle cx="14.5" cy="7.5" r="1.8"/><circle cx="18.5" cy="12" r="1.8"/><path d="M12 21c-2.5 0-4.5-1.8-4.5-3.5 0-2 2-3 4.5-3s4.5 1 4.5 3C16.5 19.2 14.5 21 12 21z"/>',
    "osso":        '<path d="M6 8a2.5 2.5 0 10-1 3l6 6a2.5 2.5 0 103-3l-6-6a2.5 2.5 0 10-2 0z"/>',

    # educação
    "livro":       '<path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2z"/><path d="M4 19a2 2 0 012-2h13"/>',
    "formatura":   '<path d="M12 4l10 5-10 5L2 9z"/><path d="M6 11v5c0 1 2.7 2.5 6 2.5s6-1.5 6-2.5v-5"/><path d="M22 9v5"/>',
    "lousa":       '<rect x="3" y="4" width="18" height="13" rx="1"/><path d="M8 21l1.5-4M16 21l-1.5-4M7 9h6M7 12h4"/>',

    # construção / reforma
    "rolo":        '<rect x="4" y="4" width="14" height="6" rx="1"/><path d="M18 7h2a1 1 0 011 1v2a1 1 0 01-1 1h-6M11 11v3a1 1 0 01-1 1 1 1 0 00-1 1v5"/>',
    "capacete":    '<path d="M3 16a9 9 0 0118 0z"/><path d="M3 16h18v2H3z"/><path d="M9 8V6a1 1 0 011-1h4a1 1 0 011 1v2"/><path d="M9 8a6 6 0 00-2 4M15 8a6 6 0 012 4"/>',
    "trena":       '<path d="M3 7a2 2 0 012-2h14a2 2 0 012 2v6a2 2 0 01-2 2H8l-5 4z"/><path d="M7 5v3M11 5v2M15 5v3M19 5v2"/>',
    "martelo":     '<path d="M14 6l4 4M17 3l4 4-3 3-4-4zM15 8L4 19l-1 2 2-1 11-11"/>',

    # limpeza
    "vassoura":    '<path d="M14 3l4 4-7 7-4-4z"/><path d="M11 14l-8 7M8 11l-5 8h9l3-5"/>',
    "balde":       '<path d="M5 8h14l-1.5 11a2 2 0 01-2 1.8H8.5a2 2 0 01-2-1.8z"/><path d="M4 8a8 3 0 0116 0"/>',

    # eventos / festas
    "balao":       '<path d="M12 3a5 6 0 015 6c0 4-5 7-5 7s-5-3-5-7a5 6 0 015-6z"/><path d="M12 16v3M10.5 21h3"/>',
    "bolo":        '<path d="M4 21h16v-7H4z"/><path d="M4 14c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"/><path d="M8 11V8M12 11V6M16 11V8"/>',
    "camera":      '<path d="M3 8a2 2 0 012-2h2l1.5-2h7L17 6h2a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><circle cx="12" cy="13" r="3.5"/>',
    "musica":      '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',

    # moda / varejo
    "sacola":      '<path d="M6 8h12l-1 12a1 1 0 01-1 1H8a1 1 0 01-1-1z"/><path d="M9 8V6a3 3 0 016 0v2"/>',
    "cabide":      '<path d="M12 3a2 2 0 00-1 3.7c.6.3 1 .8 1 1.3M3 20l9-6 9 6a1 1 0 01-1 1H4a1 1 0 01-1-1z"/>',
    "oculos":      '<circle cx="6" cy="14" r="3.5"/><circle cx="18" cy="14" r="3.5"/><path d="M9.5 13c1.5-1 3.5-1 5 0M2.5 12l2-6h2M21.5 12l-2-6h-2"/>',
    "etiqueta":    '<path d="M3 12l9-9 8 1 1 8-9 9z"/><circle cx="15.5" cy="8.5" r="1.5"/>',

    # floricultura
    "flor":        '<path d="M12 11c-3 0-5-2-5-5 2 0 3 1 5 3 2-2 3-3 5-3 0 3-2 5-5 5z"/><path d="M12 11v10M8 21h8"/>',

    # transporte
    "caminhao":    '<path d="M3 6h11v10H3z"/><path d="M14 9h4l3 3v4h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',

    # imobiliária
    "casa":        '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "chave-casa":  '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 3l3 3M15 5l2 2"/>',

    # assistência técnica
    "celular":     '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
    "computador":  '<rect x="3" y="4" width="18" height="12" rx="1"/><path d="M8 20h8M12 16v4"/>',
    "floco":       '<path d="M12 2v20M4.2 7l15.6 10M19.8 7L4.2 17"/>',

    # utilitários (seções novas)
    "seta-baixo":  '<path d="M6 9l6 6 6-6"/>',
    "grupo":       '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0114 0"/><path d="M16 5a3.5 3.5 0 010 6.5M17 20a7 7 0 00-3-5.5"/>',
    "calendario":  '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
    "crescimento": '<path d="M3 17l6-6 4 4 8-8"/><path d="M21 7v5h-5"/>',
    "polegar":     '<path d="M7 11v9H4a1 1 0 01-1-1v-7a1 1 0 011-1z"/><path d="M7 11l4-8a2 2 0 013 2l-1 4h5a2 2 0 012 2.3l-1.2 6A2 2 0 0117 20H7"/>',
}


def svg(chave, tamanho=28):
    """Retorna um <svg> completo. Herda cor via currentColor."""
    corpo = _PATHS.get(chave) or _PATHS["estrela"]
    return (
        f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'{corpo}</svg>'
    )


def existe(chave):
    return chave in _PATHS
