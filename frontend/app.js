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
      // Guarda os prontos pra auto-seleção após a tabela carregar
      APP._prontosDisparo = ev.prontos_disparo || [];
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

// ── Tabela ────────────────────────────────────────────────────────────────────

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
  renderizarTabela();
  renderizarPaginacao();
  atualizarContador();
}

function renderizarTabela() {
  const corpo  = document.getElementById("corpo-tabela");
  const inicio = (APP.pagina - 1) * APP.porPagina;
  const pag    = APP.filtradas.slice(inicio, inicio + APP.porPagina);

  document.getElementById("badge-total").textContent = APP.filtradas.length;
  corpo.innerHTML = "";

  if (!pag.length) {
    corpo.innerHTML = '<tr><td colspan="8" class="vazio">Nenhum resultado.</td></tr>';
    return;
  }

  pag.forEach(emp => {
    const temSite = Boolean(emp.tem_site);
    const enviado = Boolean(emp.mensagem_enviada);
    const podeSel = !temSite && !enviado && emp.telefone;
    const sc      = emp.score || 0;
    const scoreCls = sc >= 70 ? "score-alto" : sc >= 40 ? "score-medio" : "score-baixo";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" ${APP.selecionados.has(emp.id)?"checked":""} ${!podeSel?"disabled":""} onchange="toggleSel(${emp.id},this.checked)"/></td>
      <td><span class="${scoreCls}">${sc}</span></td>
      <td><strong>${esc(emp.nome)}</strong>${emp.email?`<br><small style="color:var(--muted)">${esc(emp.email)}</small>`:''}</td>
      <td>${esc(emp.telefone||"—")}</td>
      <td class="hide-mobile" style="font-size:.8rem;color:var(--muted);max-width:200px">${esc(emp.endereco||"—")}</td>
      <td>${temSite?'<span class="badge badge-vermelho">Tem site</span>':'<span class="badge badge-verde">Sem site</span>'}</td>
      <td>${_badgeStatus(emp.status, enviado)}</td>
      <td>${podeSel?`<button class="btn btn-sm btn-whatsapp" onclick="enviarUm(${emp.id})">📱</button>`:""}</td>
    `;
    corpo.appendChild(tr);
  });

  // Checkbox "selecionar todos"
  const chkTodos = document.getElementById("chk-todos");
  const selecionaveis = pag.filter(e => !e.tem_site && !e.mensagem_enviada && e.telefone);
  chkTodos.checked = selecionaveis.length > 0 && selecionaveis.every(e => APP.selecionados.has(e.id));
}

function _badgeStatus(status, enviado) {
  if (enviado || status === "contatado") return '<span class="badge badge-azul">Contatado</span>';
  if (status === "interessado")          return '<span class="badge badge-roxo">Interessado</span>';
  if (status === "fechado")             return '<span class="badge badge-verde">Fechado</span>';
  if (status === "perdido")             return '<span class="badge badge-vermelho">Perdido</span>';
  return '<span class="badge badge-cinza">Novo</span>';
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
      <strong>🎯 ${qtd} empresa(s) sem site</strong> prontas para disparo imediato.
    </div>
    <button class="btn btn-whatsapp" onclick="enviarSelecionados()">📱 Disparar agora</button>
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
  renderizarTabela();
  atualizarContador();
}

function selecionarTodos() {
  APP.filtradas.forEach(e => {
    if (!e.tem_site && !e.mensagem_enviada && e.telefone) APP.selecionados.add(e.id);
  });
  renderizarTabela();
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
