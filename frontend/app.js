/* =====================================================================
   Busca principal — usa SSE para atualizações em tempo real
   ===================================================================== */

const APP = {
  empresas: [], filtradas: [], selecionados: new Set(),
  pagina: 1, porPagina: 10, buscaId: null,
  filaBuscas: [],       // fila de busca em lote
  _enviandoAtivo: false,
};

// ── SSE ───────────────────────────────────────────────────────────────────────

let sse = null;

function conectarSSE() {
  if (sse) sse.close();
  sse = new EventSource("/api/events");
  sse.onmessage = (e) => {
    try { processarEvento(JSON.parse(e.data)); } catch (_) {}
  };
  sse.onerror = () => {
    // reconecta após 5s se cair
    setTimeout(conectarSSE, 5000);
  };
}

function processarEvento(ev) {
  switch (ev.tipo) {
    case "estado_inicial":
      if (ev.scraping) mostrar("secao-progresso");
      if (ev.empresas && ev.empresas.length > 0) {
        APP.buscaId = ev.busca_id;
        carregarResultados(ev.empresas);
      }
      APP._enviandoAtivo = ev.enviando;
      break;

    case "progresso":
      const pct = ev.total > 0 ? Math.round((ev.atual / ev.total) * 100) : 0;
      setProgresso(`Extraindo ${ev.atual}/${ev.total}...`, ev.atual, ev.total, ev.empresa, pct);
      break;

    case "validando_inicio":
      setProgresso("Validando sites (verificação real)...", 0, ev.total, "", 0);
      break;

    case "validando_progresso":
      const pv = ev.total > 0 ? Math.round((ev.atual / ev.total) * 100) : 0;
      setProgresso(`Validando sites ${ev.atual}/${ev.total}...`, ev.atual, ev.total, ev.empresa, pv);
      break;

    case "scraping_fim":
      document.getElementById("btn-buscar").disabled = false;
      const reclass = ev.reclassificadas ? ` · ${ev.reclassificadas} tinham site falso` : "";
      setProgresso(`Concluído! ${ev.total} empresas (${ev.sem_site} sem site${reclass}).`, ev.total, ev.total, "", 100);
      if (ev.funil) {
        const f = ev.funil;
        console.log("Funil scraping:", f);
        // Se raspou bem menos que o pedido, mostra onde perdeu (feed/URLs/extração).
        if ((f.extraidas || 0) < (f.pedidas || 0)) {
          mostrarToast(`Funil: pediu ${f.pedidas}, feed ${f.cards} cards, ${f.urls} URLs, ${f.extraidas} extraídas (${f.sem_dados} sem dados, ${f.dup_tel} tel. duplicado).`, "info");
        }
      }
      carregarHistorico();
      APP._prontosDisparo = ev.prontos_disparo || [];
      // Mostra painel IA e auto-inicia geração de mensagens + análise
      if (ev.total > 0) {
        mostrar("secao-gemini-enriq");
        const elTxt = document.getElementById("gemini-txt");
        if (elTxt) elTxt.textContent = `${ev.total} empresas — clique "Gerar Sites" para enriquecer`;
        const elCnt = document.getElementById("gemini-cnt");
        if (elCnt) elCnt.textContent = "";
        const elBar = document.getElementById("gemini-barra");
        if (elBar) elBar.style.width = "0%";
        // Auto-start: analisa prospects e gera mensagens em background
        setTimeout(analisarProspects, 600);
        setTimeout(gerarMensagensEmLote, 1800);
      }
      // busca em lote: dispara próxima
      if (APP.filaBuscas.length > 0) {
        setTimeout(_executarProximaBuscaLote, 800);
      } else if (APP._prontosDisparo.length > 0) {
        setTimeout(prepararDisparoAutomatico, 400);
      }
      break;

    case "scraping_inicio":
      mostrar("secao-progresso");
      esconder("secao-resultados");
      esconder("secao-acoes");
      esconder("secao-gemini-enriq");
      break;

    case "envio_inicio":
      APP._enviandoAtivo = true;
      mostrarToast(`📱 Enviando para ${ev.total} empresa(s)...`, "info");
      break;

    case "envio_progresso":
      const t = document.getElementById("toast");
      if (t) t.textContent = `📱 Enviando ${ev.atual}/${ev.total} — ${ev.empresa}`;
      break;

    case "envio_fim":
      APP._enviandoAtivo = false;
      if (ev.falhas) {
        mostrarToast(`⚠️ ${ev.enviados||0} enviada(s), ${ev.falhas} falha(s). ${ev.ultimo_erro ? "Erro: " + ev.ultimo_erro : ""}`, "error");
      } else {
        mostrarToast(`✅ ${ev.enviados||0} mensagem(ns) enviada(s)!`, "success");
      }
      // Recarrega empresas da busca ativa para atualizar status
      if (APP.buscaId) verBusca(APP.buscaId);
      break;

    case "erro":
      mostrarToast("❌ Erro: " + ev.mensagem, "error");
      document.getElementById("btn-buscar").disabled = false;
      esconder("secao-progresso");
      break;

    case "enriquecimento_inicio":
      mostrarProgressoIA(0, ev.total, "Iniciando enriquecimento com IA...");
      break;

    case "enriquecimento_progresso":
      mostrarProgressoIA(ev.atual, ev.total, ev.empresa);
      break;

    case "enriquecimento_fim":
      finalizarProgressoIA(ev.total);
      if (APP.buscaId) verBusca(APP.buscaId);
      break;

    case "prospect_respondeu":
      mostrarToast(`Resposta recebida: ${ev.nome || ev.numero}`, "success");
      break;
  }

  // Atualiza empresas na tabela se vieram no evento
  if (ev.empresas && ev.empresas.length > 0) {
    APP.buscaId = ev.busca_id || APP.buscaId;
    carregarResultados(ev.empresas);
  }
}

// ── Busca ─────────────────────────────────────────────────────────────────────

async function iniciarBusca() {
  const cidade      = document.getElementById("cidade").value.trim();
  const categoria   = document.getElementById("categoria").value.trim();
  const quantidade  = parseInt(document.getElementById("quantidade")?.value || "50", 10);
  if (!cidade || !categoria) { mostrarToast("Preencha cidade e categoria.", "warning"); return; }
  await _dispararBusca(cidade, categoria, quantidade);
}

async function _dispararBusca(cidade, categoria, quantidade = 50) {
  document.getElementById("btn-buscar").disabled = true;
  setProgresso("Iniciando Chrome...", 0, 0, "", 0);
  mostrar("secao-progresso");

  try {
    const r = await fetch("/api/buscar", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ cidade, categoria, quantidade }),
    });
    const d = await r.json();
    if (!r.ok) {
      document.getElementById("btn-buscar").disabled = false;
      // Busca presa? Oferece destravar e tentar de novo.
      if ((d.erro || "").includes("em andamento")) {
        if (confirm("Uma busca parece presa. Destravar e iniciar de novo?")) {
          await destravarBusca(false);
          return _dispararBusca(cidade, categoria, quantidade);
        }
        return;
      }
      mostrarToast("Erro: " + d.erro, "error");
    }
  } catch (e) {
    mostrarToast("Erro de rede: " + e.message, "error");
    document.getElementById("btn-buscar").disabled = false;
  }
}

async function destravarBusca(avisar = true) {
  try {
    await fetch("/api/buscar/reset", { method: "POST" });
    document.getElementById("btn-buscar").disabled = false;
    if (avisar) mostrarToast("Busca destravada. Pode iniciar de novo.", "success");
  } catch (e) {
    if (avisar) mostrarToast("Erro ao destravar: " + e.message, "error");
  }
}

// ── Busca em lote ─────────────────────────────────────────────────────────────

async function iniciarLote() {
  const texto = (document.getElementById("lote-texto").value || "").trim();
  if (!texto) { mostrarToast("Cole as buscas no formato: categoria, cidade", "warning"); return; }

  const linhas = texto.split("\n").map(l => l.trim()).filter(Boolean);
  const buscas = linhas.map(l => {
    const partes = l.split(",").map(p => p.trim());
    return { categoria: partes[0] || "", cidade: partes.slice(1).join(",").trim() };
  }).filter(b => b.categoria && b.cidade);

  if (!buscas.length) { mostrarToast("Nenhuma busca válida encontrada.", "warning"); return; }

  APP.filaBuscas = [...buscas];
  mostrarToast(`Lote: ${buscas.length} buscas na fila.`, "info");
  _executarProximaBuscaLote();
}

function _executarProximaBuscaLote() {
  if (!APP.filaBuscas.length) {
    mostrarToast("✅ Lote concluído!", "success");
    return;
  }
  const { cidade, categoria } = APP.filaBuscas.shift();
  document.getElementById("cidade").value    = cidade;
  document.getElementById("categoria").value = categoria;
  _dispararBusca(cidade, categoria);
}

// ── Progresso ─────────────────────────────────────────────────────────────────

function setProgresso(texto, atual, total, empresa, pct) {
  document.getElementById("txt-progresso").textContent = texto;
  document.getElementById("txt-contagem").textContent  = `${atual} / ${total}`;
  document.getElementById("txt-empresa").textContent   = empresa || "";
  document.getElementById("barra-fill").style.width    = (pct || 0) + "%";
}

// ── Cards de resultado ────────────────────────────────────────────────────────

function carregarResultados(empresas) {
  APP.empresas     = empresas;
  APP.selecionados = new Set();
  APP.pagina       = 1;
  _aplicarFiltro();
  mostrar("secao-resultados");
  mostrar("secao-acoes");
}

function filtrarTabela() {
  APP.pagina = 1;
  _aplicarFiltro();
}

function _aplicarFiltro() {
  const soSemSite = document.getElementById("chk-sem-site").checked;
  // Sempre exclui empresas já disparadas da prospecção
  let base = APP.empresas.filter(e => !e.mensagem_enviada);
  APP.filtradas = soSemSite ? base.filter(e => !e.tem_site) : base;
  renderizarCards();
  renderizarPaginacao();
  atualizarContador();
}

function renderizarCards() {
  const corpo  = document.getElementById("corpo-cards");
  const inicio = (APP.pagina - 1) * APP.porPagina;
  const pag    = APP.filtradas.slice(inicio, inicio + APP.porPagina);

  document.getElementById("badge-total").textContent = APP.filtradas.length;
  corpo.innerHTML = "";

  if (!pag.length) {
    corpo.innerHTML = '<div style="padding:32px;text-align:center;color:var(--muted)">Nenhum resultado.</div>';
    return;
  }

  pag.forEach(emp => {
    const temSite   = Boolean(emp.tem_site);
    const enviado   = Boolean(emp.mensagem_enviada);
    const duplicado = Boolean(emp._duplicado);
    const podeSel   = !temSite && !enviado && emp.telefone;
    const sc       = emp.score || 0;
    const scoreCls = sc >= 70 ? "score-alto" : sc >= 40 ? "score-medio" : "score-baixo";
    const checked  = APP.selecionados.has(emp.id) ? "checked" : "";
    const nota     = emp.nota;
    const avs      = emp.avaliacoes;
    const cat      = emp.descricao_google || "";
    const mapsUrl  = emp.maps_url || "";
    const fotoUrl  = emp.foto_url || "";
    const slug     = emp.gemini_pagina_slug || "";

    const starsHtml = nota ? (() => {
      const full  = Math.round(nota);
      const stars = "★".repeat(full) + "☆".repeat(5 - full);
      const avsPart = (avs && avs > 0)
        ? ` · ${avs.toLocaleString('pt-BR')} avaliação${avs !== 1 ? "ões" : ""}`
        : "";
      return `<div style="color:#f59e0b;font-size:.82rem;margin-top:4px">
        ${stars}
        <span style="color:var(--muted);font-size:.75rem;margin-left:4px">${nota.toFixed(1)}${avsPart}</span>
      </div>`;
    })() : "";

    const card = document.createElement("div");
    card.id        = `card-${emp.id}`;
    card.className = "empresa-card" + (enviado ? " empresa-card-enviada" : "");
    card.innerHTML = `
      <div style="display:flex;gap:12px;align-items:flex-start">
        <div style="padding-top:3px;flex-shrink:0">
          <input type="checkbox" ${checked} ${!podeSel ? "disabled" : ""}
            style="width:16px;height:16px;cursor:pointer;accent-color:var(--primary)"
            onchange="toggleSel(${emp.id},this.checked)"/>
        </div>
        ${fotoUrl ? `<img src="${esc(fotoUrl)}" alt="${esc(emp.nome)}"
          style="width:60px;height:60px;object-fit:cover;border-radius:10px;flex-shrink:0;box-shadow:0 2px 8px rgba(0,0,0,.15)">` : ""}
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <strong style="font-size:.95rem">${esc(emp.nome)}</strong>
            <span class="${scoreCls}" style="font-size:.68rem;padding:2px 7px;border-radius:10px">${sc}</span>
            ${!temSite
              ? '<span class="badge badge-verde" style="font-size:.68rem">Sem site</span>'
              : '<span class="badge badge-vermelho" style="font-size:.68rem">Tem site</span>'}
            ${_badgeStatus(emp.status, enviado, duplicado)}
          </div>
          ${cat ? `<div style="margin-top:5px">
            <span style="font-size:.73rem;background:rgba(66,133,244,.12);color:#4285F4;padding:2px 9px;border-radius:12px">${esc(cat)}</span>
          </div>` : ""}
          ${starsHtml}
          <div style="margin-top:7px;font-size:.8rem;color:var(--muted);display:flex;flex-direction:column;gap:3px">
            ${emp.telefone ? `<span>📞 ${esc(emp.telefone)}</span>` : ""}
            ${emp.endereco ? `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:480px">📍 ${esc(emp.endereco)}</span>` : ""}
            ${emp.email    ? `<span>✉ ${esc(emp.email)}</span>` : ""}
          </div>
        </div>
      </div>
      <div style="margin-top:13px;padding-top:11px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:8px">

        <!-- Linha 1: navegação -->
        <div style="display:flex;gap:7px;flex-wrap:wrap">
          ${mapsUrl ? `<a href="${esc(mapsUrl)}" target="_blank" rel="noopener"
              class="btn btn-sm btn-secondary" style="font-size:.73rem;text-decoration:none;display:inline-flex;align-items:center;gap:4px">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              Ver no Maps
            </a>` : ""}
          ${podeSel ? `<button class="btn btn-sm btn-whatsapp" style="font-size:.73rem;display:inline-flex;align-items:center;gap:4px"
              onclick="enviarUm(${emp.id})">
              <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/></svg>
              WhatsApp
            </button>` : ""}
        </div>

        <!-- Linha 2: ações IA independentes -->
        <div style="display:flex;gap:7px;flex-wrap:wrap;padding:8px;background:rgba(99,102,241,.05);border-radius:8px;border:1px solid rgba(99,102,241,.12)">
          <span style="font-size:.65rem;color:#6366f1;font-weight:700;width:100%;margin-bottom:2px">⚡ AÇÕES IA — escolha uma ou as duas independentemente</span>

          <!-- Mensagem IA -->
          <button class="btn btn-sm" ${!emp.telefone ? "disabled title='Sem telefone cadastrado'" : `data-empid="${emp.id}" data-tel="${esc(emp.telefone||'')}" onclick="gerarMensagemEmpresa(this.dataset.empid,this.dataset.tel)"`}
              style="font-size:.73rem;background:${emp.telefone ? "linear-gradient(135deg,#6366f1,#8b5cf6)" : "rgba(99,102,241,.2)"};color:${emp.telefone ? "#fff" : "rgba(99,102,241,.5)"};border:none;display:inline-flex;align-items:center;gap:4px;cursor:${emp.telefone ? "pointer" : "not-allowed"}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            Mensagem IA${!emp.telefone ? " (sem tel)" : ""}
          </button>

          <!-- Site Demo -->
          <button id="btn-gerar-${emp.id}" class="btn btn-sm"
              onclick="gerarSiteEmpresa(${emp.id})"
              style="font-size:.73rem;background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff;border:none;display:inline-flex;align-items:center;gap:4px">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
            ${slug ? "Regenerar Site Demo" : "Criar Site Demo"}
          </button>

          ${slug ? `<a href="/p/${slug}" target="_blank" rel="noopener"
              class="btn btn-sm" style="font-size:.73rem;background:rgba(66,133,244,.1);color:#4285F4;border:1px solid rgba(66,133,244,.3);text-decoration:none;display:inline-flex;align-items:center;gap:4px">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              Ver Site Demo
            </a>` : ""}
        </div>

      </div>`;
    corpo.appendChild(card);
  });
}

function _badgeStatus(status, enviado, duplicado) {
  if (enviado) return '<span class="badge" style="font-size:.68rem;background:#10B981;color:#fff;font-weight:700">✓ JÁ DISPARADA</span>';
  if (status === "contatado") return '<span class="badge badge-azul" style="font-size:.68rem">Contatado</span>';
  if (status === "interessado")          return '<span class="badge badge-roxo" style="font-size:.68rem">Interessado</span>';
  if (status === "fechado")              return '<span class="badge badge-verde" style="font-size:.68rem">Fechado</span>';
  if (status === "perdido")              return '<span class="badge badge-vermelho" style="font-size:.68rem">Perdido</span>';
  if (duplicado) return '<span class="badge" style="font-size:.68rem;background:rgba(245,158,11,.15);color:#d97706;border:1px solid rgba(245,158,11,.3)">Já no BD</span>';
  return '<span class="badge badge-cinza" style="font-size:.68rem">Novo</span>';
}

async function gerarSiteEmpresa(empresaId) {
  const btn = document.getElementById(`btn-gerar-${empresaId}`);
  const _spinner = (msg) => {
    if (btn) btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" style="animation:spin .8s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> ${msg}`;
  };
  if (btn) { btn.disabled = true; _spinner("Iniciando..."); }

  try {
    // 1. Dispara job em background
    const r0 = await fetch("/api/ai/enriquecer-empresa", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ empresa_id: empresaId }),
    });
    const d0 = await r0.json();
    if (!r0.ok || d0.erro) throw new Error(d0.erro || "Erro desconhecido");

    const jobId = d0.job_id;
    let tentativas = 0;
    const MAX = 120; // 240s máximo

    // 2. Polling
    while (tentativas < MAX) {
      await new Promise(res => setTimeout(res, 2000));
      tentativas++;
      _spinner(`Gerando... (${tentativas * 2}s)`);

      const resp = await fetch(`/api/ai/gerar-pagina/status/${jobId}`);
      if (resp.status === 404) throw new Error("Servidor reiniciou. Tente novamente.");
      const rs = await resp.json();

      if (rs.status === "ok") {
        const emp = APP.empresas.find(e => e.id === empresaId);
        if (emp) {
          if (rs.slug)     emp.gemini_pagina_slug = rs.slug;
          if (rs.mensagem) emp.gemini_mensagem    = rs.mensagem;
        }
        if (btn && rs.url) {
          btn.outerHTML = `
            <a href="${rs.url}" target="_blank" rel="noopener"
                class="btn btn-sm" style="font-size:.73rem;background:rgba(66,133,244,.1);color:#4285F4;border:1px solid rgba(66,133,244,.3);text-decoration:none;display:inline-flex;align-items:center;gap:4px">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              Ver Site Demo
            </a>
            <button id="btn-gerar-${empresaId}" class="btn btn-sm" onclick="gerarSiteEmpresa(${empresaId})"
                style="font-size:.73rem;background:linear-gradient(135deg,#f59e0b,#ef4444);color:#fff;border:none;display:inline-flex;align-items:center;gap:4px">
              Regenerar
            </button>`;
        }
        mostrarToast(`Site gerado: ${emp?.nome || "empresa"}!`, "success");
        return;
      }

      if (rs.status === "erro") throw new Error(rs.erro || "Erro na geração.");
    }

    throw new Error("Tempo limite atingido (4 min). Tente novamente.");
  } catch (e) {
    mostrarToast("Erro ao gerar site: " + e.message, "error");
    if (btn) {
      btn.disabled  = false;
      btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg> Criar Site Demo`;
    }
  }
}

function renderizarPaginacao() {
  const total = Math.ceil(APP.filtradas.length / APP.porPagina);
  const pag   = document.getElementById("paginacao");
  pag.innerHTML = "";
  if (total <= 1) return;
  const add = (label, p, ativo) => {
    const btn = document.createElement("button");
    btn.className = "btn-pag" + (ativo ? " ativa" : "");
    btn.textContent = label;
    btn.onclick = () => { APP.pagina = p; renderizarCards(); renderizarPaginacao(); };
    pag.appendChild(btn);
  };
  if (APP.pagina > 1)     add("◀", APP.pagina - 1, false);
  for (let i = 1; i <= total; i++) add(i, i, i === APP.pagina);
  if (APP.pagina < total) add("▶", APP.pagina + 1, false);
}

// ── Disparo automático pós-busca ──────────────────────────────────────────────

function prepararDisparoAutomatico() {
  const prontos = APP._prontosDisparo || [];
  if (!prontos.length) return;

  // Ativa filtro "só sem site" e seleciona todos os prontos
  const chk = document.getElementById("chk-sem-site");
  if (chk) { chk.checked = true; filtrarTabela(); }

  prontos.forEach(id => APP.selecionados.add(id));
  renderizarCards();
  atualizarContador();

  // Banner destacado de disparo rápido
  mostrarBannerDisparo(prontos.length);
  mostrarToast(`✅ ${prontos.length} número(s) sem site prontos pra disparar!`, "success");
}

function mostrarBannerDisparo(qtd) {
  let banner = document.getElementById("banner-disparo");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "banner-disparo";
    banner.className = "banner-disparo";
    const acoes = document.getElementById("secao-acoes");
    acoes.parentNode.insertBefore(banner, acoes);
  }
  banner.innerHTML = `
    <div class="banner-disparo-txt">
      <strong>${qtd} empresa(s) sem site</strong> prontas para disparo imediato.
    </div>
    <button class="btn btn-whatsapp" onclick="enviarSelecionados()">Disparar agora</button>
    <button class="btn btn-secondary btn-sm" onclick="fecharBannerDisparo()">✕</button>
  `;
  banner.classList.remove("hidden");
}

function fecharBannerDisparo() {
  const b = document.getElementById("banner-disparo");
  if (b) b.classList.add("hidden");
}

// ── Seleção ───────────────────────────────────────────────────────────────────

function toggleSel(id, checked) {
  checked ? APP.selecionados.add(id) : APP.selecionados.delete(id);
  atualizarContador();
}

function toggleCheckboxTodos(chk) {
  const inicio = (APP.pagina - 1) * APP.porPagina;
  const pag    = APP.filtradas.slice(inicio, inicio + APP.porPagina);
  pag.forEach(e => {
    if (!e.tem_site && !e.mensagem_enviada && e.telefone)
      chk.checked ? APP.selecionados.add(e.id) : APP.selecionados.delete(e.id);
  });
  renderizarCards();
  atualizarContador();
}

function selecionarTodos() {
  APP.filtradas.forEach(e => {
    if (!e.tem_site && !e.mensagem_enviada && e.telefone) APP.selecionados.add(e.id);
  });
  renderizarCards();
  atualizarContador();
}

function atualizarContador() {
  document.getElementById("txt-selecionados").textContent = `${APP.selecionados.size} selecionado(s)`;
}

// ── WhatsApp ──────────────────────────────────────────────────────────────────

async function enviarSelecionados() {
  if (!APP.selecionados.size) { mostrarToast("Selecione ao menos uma empresa.", "warning"); return; }
  if (!confirm(`Enviar para ${APP.selecionados.size} empresa(s)?`)) return;
  await _enviarIds([...APP.selecionados]);
}

async function enviarUm(id) {
  if (!confirm("Enviar mensagem para esta empresa?")) return;
  await _enviarIds([id]);
}

// Gera uma mensagem IA ÚNICA por empresa (as que faltam) e dispara o lote.
async function dispararComIA() {
  // Alvos: selecionados; se nada marcado, todas sem site + com telefone + não enviadas.
  let alvos = [...APP.selecionados];
  if (!alvos.length) {
    alvos = APP.empresas
      .filter(e => !e.tem_site && e.telefone && !e.mensagem_enviada)
      .map(e => e.id);
  }
  if (!alvos.length) { mostrarToast("Nenhuma empresa elegível para disparo.", "warning"); return; }
  if (!confirm(`Gerar mensagem IA única para ${alvos.length} empresa(s) e disparar?`)) return;

  const faltam = alvos.filter(id => {
    const e = APP.empresas.find(x => x.id === id);
    return e && !e.gemini_mensagem;
  });

  let feitos = 0;
  for (const id of faltam) {
    const e = APP.empresas.find(x => x.id === id);
    mostrarToast(`🤖 Gerando IA ${++feitos}/${faltam.length}${e ? " — " + e.nome : ""}...`, "info");
    try {
      const r = await fetch("/api/ai/gerar-mensagem-empresa", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ empresa_id: id }),
      });
      const d = await r.json();
      if (r.ok && d.mensagem && e) e.gemini_mensagem = d.mensagem;
    } catch (_) {}
  }

  // Mapa id -> mensagem IA (usa o que temos local; o backend também lê do banco).
  const mensagens = {};
  alvos.forEach(id => {
    const e = APP.empresas.find(x => x.id === id);
    if (e && e.gemini_mensagem) mensagens[id] = e.gemini_mensagem;
  });

  try {
    const r = await fetch("/api/enviar", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ ids: alvos, mensagens }),
    });
    const d = await r.json();
    if (!r.ok) { mostrarToast("Erro: " + d.erro, "error"); return; }
    mostrarToast("📤 " + d.mensagem, "success");
  } catch (e) {
    mostrarToast("Erro de rede: " + e.message, "error");
  }
}

async function _enviarIds(ids) {
  try {
    const r = await fetch("/api/enviar", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ ids }),
    });
    const d = await r.json();
    if (!r.ok) { mostrarToast("Erro: " + d.erro, "error"); return; }
    mostrarToast("⏳ " + d.mensagem, "info");
  } catch (e) {
    mostrarToast("Erro de rede: " + e.message, "error");
  }
}

// ── Export ────────────────────────────────────────────────────────────────────

function exportar(fmt = "xlsx") {
  let url = `/api/exportar?formato=${fmt}`;
  if (APP.buscaId) url += `&busca_id=${APP.buscaId}`;
  window.location.href = url;
}

// ── Histórico ─────────────────────────────────────────────────────────────────

async function carregarHistorico() {
  try {
    const hist  = await fetch("/api/historico").then(r => r.json());
    const lista = document.getElementById("historico-lista");
    lista.innerHTML = hist.length === 0
      ? '<p class="vazio">Nenhuma busca ainda.</p>'
      : hist.map(h => `
          <div class="historico-item">
            <div class="historico-info">
              <strong>${esc(h.categoria)} em ${esc(h.cidade)}</strong>
              <small>${h.total_encontradas} encontradas · ${h.sem_site} sem site · ${fmtData(h.data_busca)}</small>
            </div>
            <div class="historico-acoes">
              <button class="btn btn-sm btn-secondary" onclick="verBusca(${h.id})">Ver</button>
              <button class="btn btn-sm btn-excel"     onclick="exportarBusca(${h.id})">Excel</button>
            </div>
          </div>`).join("");

    // Auto-carrega a busca mais recente se nenhuma empresa está na tela
    // (acontece após redeploy — servidor perde estado em memória)
    if (hist.length > 0 && APP.empresas.length === 0) {
      await verBusca(hist[0].id);
    }
  } catch (_) {}
}

async function verBusca(buscaId) {
  const emps = await fetch(`/api/empresas?busca_id=${buscaId}`).then(r => r.json());
  APP.buscaId = buscaId;
  carregarResultados(emps);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function exportarBusca(buscaId) {
  window.location.href = `/api/exportar?busca_id=${buscaId}`;
}

// ── Utilitários ───────────────────────────────────────────────────────────────

function mostrar(id) { document.getElementById(id).classList.remove("hidden"); }
function esconder(id) { document.getElementById(id).classList.add("hidden"); }

function esc(t) {
  const d = document.createElement("div");
  d.appendChild(document.createTextNode(String(t || "")));
  return d.innerHTML;
}

function fmtData(s) {
  try { return new Date(s).toLocaleString("pt-BR", {day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"}); }
  catch (_) { return s || ""; }
}

function mostrarToast(msg, tipo = "info") {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.className   = "toast " + tipo;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = "toast oculto", 3500);
}

// ── AI Enrichment ─────────────────────────────────────────────────────────────

function mostrarProgressoIA(atual, total, empresa) {
  const secao = document.getElementById("secao-gemini-enriq");
  if (!secao) return;
  secao.classList.remove("hidden");
  const pct = total > 0 ? Math.round((atual / total) * 100) : 0;
  const el  = secao.querySelector("#gemini-barra");
  const txt = secao.querySelector("#gemini-txt");
  const cnt = secao.querySelector("#gemini-cnt");
  if (el)  el.style.width = pct + "%";
  if (txt) txt.textContent = empresa ? `Gerando para: ${empresa}` : "Processando...";
  if (cnt) cnt.textContent = `${atual} / ${total}`;
}

function finalizarProgressoIA(total) {
  const secao = document.getElementById("secao-gemini-enriq");
  const txt   = secao?.querySelector("#gemini-txt");
  const barra = secao?.querySelector("#gemini-barra");
  if (txt)   txt.textContent = `Enriquecimento concluído! ${total} empresa(s) processadas com IA.`;
  if (barra) barra.style.width = "100%";
  mostrarToast(`IA:${total} mensagens + sites gerados!`, "success");

  // Atualiza botão
  const btn = document.getElementById("btn-gemini-enriq");
  if (btn) {
    btn.disabled    = false;
    btn.textContent = "Enriquecer com IA";
  }
}

async function iniciarEnriquecimento() {
  const btn = document.getElementById("btn-gemini-enriq");
  if (btn) { btn.disabled = true; btn.textContent = "Processando..."; }
  // Mostra sub-painel de progresso do enriquecimento
  const sub = document.getElementById("gemini-enriq-sub");
  if (sub) sub.style.display = "block";

  try {
    const payload = {};
    if (APP.buscaId) payload.busca_id = APP.buscaId;

    const r = await fetch("/api/ai/enriquecer", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro desconhecido");
    mostrarToast(`IA:processando ${d.total} empresa(s)...`, "info");
  } catch (e) {
    mostrarToast("Erro IA:" + e.message, "error");
    if (btn) { btn.disabled = false; btn.textContent = "Enriquecer com IA"; }
  }
}

// ── Modal Mensagem IA ─────────────────────────────────────────────────────────

let _msgModalEmpId = null;   // empresa aberta no modal de Mensagem IA

async function gerarMensagemEmpresa(empresaId, telefone) {
  empresaId = parseInt(empresaId, 10);
  _msgModalEmpId = empresaId;
  const modal   = document.getElementById("modal-msg-ia");
  const txtArea = document.getElementById("modal-msg-texto");
  const nomePar = document.getElementById("modal-msg-nome");
  const btnWa   = document.getElementById("modal-btn-wa");

  const emp = APP.empresas.find(e => e.id === empresaId);
  nomePar.textContent = emp ? emp.nome : "empresa";

  // Se já tem mensagem gerada, mostra direto
  if (emp?.gemini_mensagem) {
    txtArea.value    = emp.gemini_mensagem;
    txtArea.disabled = false;
  } else {
    txtArea.value    = "Gerando mensagem personalizada com IA...";
    txtArea.disabled = true;
  }

  modal.style.display = "flex";

  // Configura botão WhatsApp
  btnWa.onclick = () => {
    const msg = encodeURIComponent(txtArea.value);
    const tel = (telefone || "").replace(/\D/g, "");
    if (tel) window.open(`https://wa.me/${tel}?text=${msg}`, "_blank");
    else mostrarToast("Número não disponível.", "warning");
  };

  if (emp?.gemini_mensagem) return;

  try {
    const r = await fetch("/api/ai/gerar-mensagem-empresa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ empresa_id: empresaId }),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro desconhecido");

    txtArea.value    = d.mensagem;
    txtArea.disabled = false;
    if (emp) emp.gemini_mensagem = d.mensagem;
  } catch (e) {
    txtArea.value    = "Erro ao gerar mensagem: " + e.message;
    txtArea.disabled = false;
  }
}

function copiarMsgModal() {
  const txt = document.getElementById("modal-msg-texto").value;
  navigator.clipboard.writeText(txt).then(() => mostrarToast("Mensagem copiada!", "success"));
}

// Envia a mensagem IA do modal (texto editável) direto pela Evolution.
async function enviarMsgModal() {
  const id  = _msgModalEmpId;
  const txt = (document.getElementById("modal-msg-texto").value || "").trim();
  if (!id)  { mostrarToast("Empresa não identificada.", "error"); return; }
  if (!txt) { mostrarToast("Mensagem vazia.", "warning"); return; }
  const emp = APP.empresas.find(e => e.id === id);
  if (emp && emp.mensagem_enviada) { mostrarToast("Já enviada para esta empresa.", "warning"); return; }
  const btn = document.getElementById("modal-btn-enviar");
  if (btn) btn.disabled = true;
  try {
    const r = await fetch("/api/enviar", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ ids: [id], mensagens: { [id]: txt } }),
    });
    const d = await r.json();
    if (!r.ok) { mostrarToast("Erro: " + d.erro, "error"); return; }
    mostrarToast("📤 " + d.mensagem, "success");
    fecharModalMsg();
  } catch (e) {
    mostrarToast("Erro de rede: " + e.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function fecharModalMsg() {
  document.getElementById("modal-msg-ia").style.display = "none";
}

// Fecha modal ao clicar fora
document.addEventListener("click", (e) => {
  const modal = document.getElementById("modal-msg-ia");
  if (modal && e.target === modal) fecharModalMsg();
});

// ── IA em Lote — Geração automática de mensagens ─────────────────────────────

async function gerarMensagensEmLote() {
  const setStatus = t => { const e = document.getElementById("ia-lote-status"); if (e) e.textContent = t; };
  const setTxt    = t => { const e = document.getElementById("ia-lote-txt");    if (e) e.textContent = t; };
  const setBarra  = p => { const e = document.getElementById("ia-lote-barra");  if (e) e.style.width = p + "%"; };

  const alvos = APP.empresas.filter(e => e.telefone && !e.gemini_mensagem);
  if (!alvos.length) {
    const prontas = APP.empresas.filter(e => e.gemini_mensagem).length;
    setStatus(`✓ ${prontas} mensagens já prontas!`);
    setTxt(`${prontas} de ${APP.empresas.length} empresas com mensagem IA`);
    setBarra(100);
    return;
  }

  const btn = document.getElementById("btn-lote-ia");
  if (btn) btn.disabled = true;
  setStatus(`Gerando ${alvos.length} mensagens em segundo plano...`);
  setBarra(0);

  let feitos = 0;
  for (const emp of alvos) {
    setTxt(`Gerando para "${emp.nome}"... (${feitos}/${alvos.length})`);
    try {
      const r = await fetch("/api/ai/gerar-mensagem-empresa", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ empresa_id: emp.id }),
      });
      const d = await r.json();
      if (r.ok && d.mensagem) {
        const local = APP.empresas.find(e => e.id === emp.id);
        if (local) local.gemini_mensagem = d.mensagem;
      }
    } catch (_) {}
    feitos++;
    setBarra(Math.round((feitos / alvos.length) * 100));
  }

  const total_prontas = APP.empresas.filter(e => e.gemini_mensagem).length;
  setStatus(`✓ ${feitos} mensagens geradas! Clique "Mensagem IA" em qualquer card — aparece instantâneo.`);
  setTxt(`${total_prontas} de ${APP.empresas.length} empresas com mensagem IA`);
  setBarra(100);
  mostrarToast(`✓ ${feitos} mensagens IA prontas!`, "success");
  if (btn) btn.disabled = false;
}

async function analisarProspects() {
  if (!APP.empresas.length) return;
  const box = document.getElementById("ia-analise-box");
  const txt = document.getElementById("ia-analise-txt");
  if (box) box.style.display = "block";
  if (txt) txt.textContent = "🔍 Analisando os melhores prospects...";

  try {
    const top25 = [...APP.empresas]
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 25)
      .map(e => ({ nome: e.nome, telefone: !!e.telefone, tem_site: !!e.tem_site, score: e.score || 0, nota: e.nota, avaliacoes: e.avaliacoes }));

    const r = await fetch("/api/ai/analisar-prospects", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ empresas: top25 }),
    });
    const d = await r.json();
    if (r.ok && d.analise) {
      if (txt) txt.textContent = d.analise;
    } else {
      if (box) box.style.display = "none";
    }
  } catch (_) {
    if (box) box.style.display = "none";
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  conectarSSE();
  carregarHistorico();
  ["cidade", "categoria"].forEach(id => {
    document.getElementById(id).addEventListener("keydown", e => {
      if (e.key === "Enter") iniciarBusca();
    });
  });
});
