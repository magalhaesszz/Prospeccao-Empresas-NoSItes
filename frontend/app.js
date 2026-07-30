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
      carregarHistorico();
      APP._prontosDisparo = ev.prontos_disparo || [];
      // Mostra botão Groq se houver empresas
      if (ev.total > 0) {
        mostrar("secao-gemini-enriq");
        document.getElementById("gemini-txt").textContent = `${ev.total} empresas prontas para enriquecimento com IA`;
        document.getElementById("gemini-cnt").textContent = "";
        document.getElementById("gemini-barra").style.width = "0%";
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
      mostrarToast("✅ Envios concluídos!", "success");
      // Recarrega empresas da busca ativa para atualizar status
      if (APP.buscaId) verBusca(APP.buscaId);
      break;

    case "erro":
      mostrarToast("❌ Erro: " + ev.mensagem, "error");
      document.getElementById("btn-buscar").disabled = false;
      esconder("secao-progresso");
      break;

    case "enriquecimento_inicio":
      mostrarProgressoGroq(0, ev.total, "Iniciando enriquecimento com Groq...");
      break;

    case "enriquecimento_progresso":
      mostrarProgressoGroq(ev.atual, ev.total, ev.empresa);
      break;

    case "enriquecimento_fim":
      finalizarProgressoGroq(ev.total);
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
  const cidade    = document.getElementById("cidade").value.trim();
  const categoria = document.getElementById("categoria").value.trim();
  if (!cidade || !categoria) { mostrarToast("Preencha cidade e categoria.", "warning"); return; }
  await _dispararBusca(cidade, categoria);
}

async function _dispararBusca(cidade, categoria) {
  document.getElementById("btn-buscar").disabled = true;
  setProgresso("Iniciando Chrome...", 0, 0, "", 0);
  mostrar("secao-progresso");

  try {
    const r = await fetch("/api/buscar", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ cidade, categoria }),
    });
    const d = await r.json();
    if (!r.ok) {
      mostrarToast("Erro: " + d.erro, "error");
      document.getElementById("btn-buscar").disabled = false;
    }
  } catch (e) {
    mostrarToast("Erro de rede: " + e.message, "error");
    document.getElementById("btn-buscar").disabled = false;
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
  APP.filtradas = soSemSite ? APP.empresas.filter(e => !e.tem_site) : [...APP.empresas];
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
    const temSite  = Boolean(emp.tem_site);
    const enviado  = Boolean(emp.mensagem_enviada);
    const podeSel  = !temSite && !enviado && emp.telefone;
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
      return `<div style="color:#f59e0b;font-size:.82rem;margin-top:4px">
        ${stars}
        <span style="color:var(--muted);font-size:.75rem;margin-left:4px">${nota.toFixed(1)} · ${avs || 0} avaliação${(avs||0)!==1?"ões":""}</span>
      </div>`;
    })() : "";

    const card = document.createElement("div");
    card.id        = `card-${emp.id}`;
    card.className = "empresa-card";
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
            ${_badgeStatus(emp.status, enviado)}
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
      <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:13px;padding-top:11px;border-top:1px solid var(--border)">
        ${mapsUrl ? `<a href="${esc(mapsUrl)}" target="_blank" rel="noopener"
            class="btn btn-sm btn-secondary" style="font-size:.73rem;text-decoration:none;display:inline-flex;align-items:center;gap:4px">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            Ver no Maps
          </a>` : ""}
        ${!temSite ? `<button id="btn-gerar-${emp.id}" class="btn btn-sm"
            onclick="gerarSiteEmpresa(${emp.id})"
            style="font-size:.73rem;background:linear-gradient(135deg,#4285F4,#34A853);color:#fff;border:none;display:inline-flex;align-items:center;gap:4px">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            ${slug ? "Regenerar Site" : "Gerar Site"}
          </button>` : ""}
        ${slug ? `<a href="/p/${slug}" target="_blank" rel="noopener"
            class="btn btn-sm" style="font-size:.73rem;background:rgba(66,133,244,.1);color:#4285F4;border:1px solid rgba(66,133,244,.3);text-decoration:none;display:inline-flex;align-items:center;gap:4px">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            Ver Preview
          </a>` : ""}
        ${podeSel ? `<button class="btn btn-sm btn-whatsapp" style="font-size:.73rem;display:inline-flex;align-items:center;gap:4px"
            onclick="enviarUm(${emp.id})">
            <svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/></svg>
            WhatsApp
          </button>` : ""}
      </div>`;
    corpo.appendChild(card);
  });
}

function _badgeStatus(status, enviado) {
  if (enviado || status === "contatado") return '<span class="badge badge-azul" style="font-size:.68rem">Contatado</span>';
  if (status === "interessado")          return '<span class="badge badge-roxo" style="font-size:.68rem">Interessado</span>';
  if (status === "fechado")              return '<span class="badge badge-verde" style="font-size:.68rem">Fechado</span>';
  if (status === "perdido")              return '<span class="badge badge-vermelho" style="font-size:.68rem">Perdido</span>';
  return '<span class="badge badge-cinza" style="font-size:.68rem">Novo</span>';
}

async function gerarSiteEmpresa(empresaId) {
  const btn = document.getElementById(`btn-gerar-${empresaId}`);
  if (btn) {
    btn.disabled   = true;
    btn.innerHTML  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"
      style="animation:spin .8s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Gerando...`;
  }
  try {
    const r = await fetch("/api/gemini/enriquecer-empresa", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ empresa_id: empresaId }),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro desconhecido");

    const emp = APP.empresas.find(e => e.id === empresaId);
    if (emp) {
      if (d.slug)     emp.gemini_pagina_slug = d.slug;
      if (d.mensagem) emp.gemini_mensagem    = d.mensagem;
    }

    if (btn && d.preview_url) {
      btn.outerHTML = `<a href="${d.preview_url}" target="_blank" rel="noopener"
          class="btn btn-sm" style="font-size:.73rem;background:rgba(66,133,244,.1);color:#4285F4;border:1px solid rgba(66,133,244,.3);text-decoration:none;display:inline-flex;align-items:center;gap:4px">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          Ver Preview
        </a>
        <button class="btn btn-sm" onclick="gerarSiteEmpresa(${empresaId})"
            style="font-size:.73rem;background:linear-gradient(135deg,#4285F4,#34A853);color:#fff;border:none;display:inline-flex;align-items:center;gap:4px">
          Regenerar
        </button>`;
    }
    mostrarToast(`Site gerado: ${emp?.nome || "empresa"}!`, "success");
  } catch (e) {
    mostrarToast("Erro ao gerar site: " + e.message, "error");
    if (btn) {
      btn.disabled  = false;
      btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg> Gerar Site`;
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
    btn.onclick = () => { APP.pagina = p; renderizarTabela(); renderizarPaginacao(); };
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
  renderizarTabela();
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

// ── Groq Enrichment ─────────────────────────────────────────────────────────

function mostrarProgressoGroq(atual, total, empresa) {
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

function finalizarProgressoGroq(total) {
  const secao = document.getElementById("secao-gemini-enriq");
  const txt   = secao?.querySelector("#gemini-txt");
  const barra = secao?.querySelector("#gemini-barra");
  if (txt)   txt.textContent = `Enriquecimento concluído! ${total} empresa(s) processadas com Groq.`;
  if (barra) barra.style.width = "100%";
  mostrarToast(`Groq: ${total} mensagens + sites gerados!`, "success");

  // Atualiza botão
  const btn = document.getElementById("btn-gemini-enriq");
  if (btn) {
    btn.disabled    = false;
    btn.textContent = "Enriquecer com Groq";
  }
}

async function iniciarEnriquecimento() {
  const btn = document.getElementById("btn-gemini-enriq");
  if (btn) { btn.disabled = true; btn.textContent = "Processando..."; }

  try {
    const payload = {};
    if (APP.buscaId) payload.busca_id = APP.buscaId;

    const r = await fetch("/api/gemini/enriquecer", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro desconhecido");
    mostrarToast(`Groq: processando ${d.total} empresa(s)...`, "info");
  } catch (e) {
    mostrarToast("Erro Groq: " + e.message, "error");
    if (btn) { btn.disabled = false; btn.textContent = "Enriquecer com Groq"; }
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
