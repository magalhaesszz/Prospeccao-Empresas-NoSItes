/* ===== CRM Kanban ===== */

const COLUNAS = [
  { id:"novo",        label:"🆕 Novo",        cor:"#2563EB" },
  { id:"contatado",   label:"📤 Contatado",    cor:"#F59E0B" },
  { id:"interessado", label:"💬 Interessado",  cor:"#8B5CF6" },
  { id:"fechado",     label:"✅ Fechado",       cor:"#10B981" },
  { id:"perdido",     label:"❌ Perdido",       cor:"#EF4444" },
];

let _dados = {};         // { status: [empresas] }
let _filtro = "";        // filtro de texto
let _arrastandoId = null;
let _empresaAbertaId = null;
let _empresaAbertaObj = null;

// ── Kanban ────────────────────────────────────────────────────────────────────

async function carregarKanban() {
  try {
    _dados = await fetch("/api/crm/kanban").then(r => r.json());
    renderizarKanban();
  } catch (e) {
    console.error("Erro ao carregar CRM:", e);
  }
}

function filtrarCards() {
  _filtro = document.getElementById("filtro-crm").value.toLowerCase();
  renderizarKanban();
}

function renderizarKanban() {
  const board = document.getElementById("kanban-board");
  board.innerHTML = "";

  COLUNAS.forEach(col => {
    let empresas = (_dados[col.id] || []);

    // Aplica filtro de texto
    if (_filtro) {
      empresas = empresas.filter(e =>
        (e.nome||"").toLowerCase().includes(_filtro) ||
        (e.telefone||"").includes(_filtro)
      );
    }

    const colEl = document.createElement("div");
    colEl.className = "kanban-col";
    colEl.innerHTML = `
      <div class="kanban-header" style="border-top-color:${col.cor}">
        <span>${col.label}</span>
        <span class="kanban-count">${empresas.length}</span>
      </div>
      <div class="kanban-cards" id="col-${col.id}"
        ondragover="onDragOver(event)"
        ondragleave="onDragLeave(event)"
        ondrop="onDrop(event,'${col.id}')">
        ${empresas.map(e => _renderCard(e, col.cor)).join("")}
      </div>
    `;
    board.appendChild(colEl);
  });
}

function _renderCard(emp, cor) {
  const sc   = emp.score || 0;
  const cls  = sc >= 70 ? "score-alto" : sc >= 40 ? "score-medio" : "score-baixo";
  const tel  = emp.telefone ? `<div class="card-tel">${esc(emp.telefone)}</div>` : "";
  const meta = [emp.cidade, emp.categoria].filter(Boolean).join(" · ");
  const notasInfo = emp.qtd_notas ? ` ${emp.qtd_notas}` : "";

  return `
    <div class="kanban-card"
      draggable="true"
      ondragstart="onDragStart(event,${emp.id})"
      onclick="abrirPainel(${emp.id})">
      <div class="card-header">
        <span class="card-nome">${esc(emp.nome)}</span>
        <span class="card-score ${cls}">${sc}pts</span>
      </div>
      ${tel}
      ${meta ? `<div class="card-meta">${esc(meta)}</div>` : ""}
      <div class="card-acoes">
        ${emp.telefone && emp.status !== "fechado" ?
          `<button class="btn-card btn-wa" onclick="event.stopPropagation();enviarWaCard(${emp.id},'${esc(emp.nome).replace(/'/g,"\\'")}')">📱</button>` : ""}
        <button class="btn-card" onclick="event.stopPropagation();abrirPainel(${emp.id})">📝${notasInfo}</button>
      </div>
    </div>
  `;
}

// ── Drag & Drop ───────────────────────────────────────────────────────────────

function onDragStart(e, id) {
  _arrastandoId = id;
  e.dataTransfer.effectAllowed = "move";
}

function onDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add("drag-over");
}

function onDragLeave(e) {
  e.currentTarget.classList.remove("drag-over");
}

async function onDrop(e, novoStatus) {
  e.preventDefault();
  e.currentTarget.classList.remove("drag-over");
  if (!_arrastandoId) return;

  await fetch(`/api/crm/empresa/${_arrastandoId}`, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ status: novoStatus }),
  });

  _arrastandoId = null;
  carregarKanban();
}

// ── Painel lateral ────────────────────────────────────────────────────────────

async function abrirPainel(empresaId) {
  _empresaAbertaId = empresaId;

  // Busca empresa em todos os status
  let emp = null;
  for (const lista of Object.values(_dados)) {
    emp = lista.find(e => e.id === empresaId);
    if (emp) break;
  }
  _empresaAbertaObj = emp;

  if (emp) {
    document.getElementById("painel-nome").textContent = emp.nome;
    const info = [
      emp.telefone ? `📱 ${emp.telefone}` : "",
      emp.email    ? `✉️ ${emp.email}`    : "",
      emp.cidade   ? `📍 ${emp.cidade} — ${emp.categoria||""}` : "",
      `⭐ Score: ${emp.score || 0}pts`,
    ].filter(Boolean).join("\n");
    document.getElementById("painel-info").innerHTML = `<pre style="font-family:inherit;white-space:pre-wrap">${esc(info)}</pre>`;

    // Botões de status
    const cont = document.getElementById("painel-status-btns");
    cont.innerHTML = COLUNAS
      .filter(c => c.id !== emp.status)
      .map(c => `
        <button class="btn-status" style="border-color:${c.cor};color:${c.cor}"
          onclick="moverParaStatus(${emp.id},'${c.id}')">
          ${c.label}
        </button>`).join("");

    // Botão WhatsApp
    const btnWa = document.getElementById("btn-wa-painel");
    if (emp.telefone && emp.status !== "fechado") {
      btnWa.style.display = "";
    } else {
      btnWa.style.display = "none";
    }
  }

  await carregarNotas(empresaId);

  document.getElementById("painel-notas").classList.add("aberto");
  document.getElementById("overlay-painel").classList.remove("hidden");
  document.body.classList.add("painel-aberto");
}

function fecharPainel() {
  document.getElementById("painel-notas").classList.remove("aberto");
  document.getElementById("overlay-painel").classList.add("hidden");
  document.body.classList.remove("painel-aberto");
  _empresaAbertaId = null;
}

async function moverParaStatus(empresaId, novoStatus) {
  await fetch(`/api/crm/empresa/${empresaId}`, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ status: novoStatus }),
  });
  fecharPainel();
  carregarKanban();
  mostrarToast("Status atualizado!", "success");
}

// ── Notas ─────────────────────────────────────────────────────────────────────

async function carregarNotas(empresaId) {
  const notas = await fetch(`/api/crm/notas/${empresaId}`).then(r => r.json());
  const lista = document.getElementById("lista-notas");
  lista.innerHTML = notas.length === 0
    ? '<p class="vazio">Nenhuma nota.</p>'
    : notas.map(n => `
        <div class="nota-item">
          <p class="nota-texto">${esc(n.texto)}</p>
          <div class="nota-meta">
            <small>${fmtData(n.criado_em)}</small>
            <button onclick="deletarNota(${n.id})" title="Apagar">🗑️</button>
          </div>
        </div>`).join("");
}

async function adicionarNota() {
  const input = document.getElementById("input-nota");
  const texto = input.value.trim();
  if (!texto || !_empresaAbertaId) return;

  await fetch(`/api/crm/notas/${_empresaAbertaId}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ texto }),
  });
  input.value = "";
  await carregarNotas(_empresaAbertaId);
  carregarKanban();  // atualiza contador de notas
}

async function deletarNota(notaId) {
  if (!confirm("Apagar esta nota?")) return;
  await fetch(`/api/crm/notas/item/${notaId}`, { method: "DELETE" });
  if (_empresaAbertaId) await carregarNotas(_empresaAbertaId);
}

// ── IA Follow-up ─────────────────────────────────────────────────────────────

async function gerarFollowupIA() {
  if (!_empresaAbertaId) return;
  const btn = document.getElementById("btn-followup-ia");
  const res = document.getElementById("followup-resultado");
  const txt = document.getElementById("followup-texto");

  btn.disabled     = true;
  btn.textContent  = "⏳ Gerando...";
  if (res) res.style.display = "none";

  try {
    const r = await fetch("/api/gemini/crm-followup", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ empresa_id: _empresaAbertaId }),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro");
    if (txt) txt.value = d.mensagem;
    if (res) res.style.display = "block";
    mostrarToast("Follow-up gerado!", "success");
  } catch (e) {
    mostrarToast("Erro IA: " + e.message, "error");
  } finally {
    btn.disabled    = false;
    btn.textContent = "⚡ Gerar Follow-up com IA";
  }
}

function copiarFollowup() {
  const txt = document.getElementById("followup-texto")?.value;
  if (txt) navigator.clipboard.writeText(txt).then(() => mostrarToast("Copiado!", "success"));
}

function enviarFollowupWa() {
  const txt = document.getElementById("followup-texto")?.value;
  const tel = (_empresaAbertaObj?.telefone || "").replace(/\D/g, "");
  if (!txt || !tel) { mostrarToast("Sem mensagem ou telefone.", "warning"); return; }
  window.open(`https://wa.me/${tel}?text=${encodeURIComponent(txt)}`, "_blank");
}

// ── WhatsApp rápido ───────────────────────────────────────────────────────────

async function enviarWaPainel() {
  if (!_empresaAbertaObj) return;
  if (!confirm(`Enviar WhatsApp para ${_empresaAbertaObj.nome}?`)) return;
  await _enviarIds([_empresaAbertaObj.id]);
}

async function enviarWaCard(id, nome) {
  if (!confirm(`Enviar WhatsApp para ${nome}?`)) return;
  await _enviarIds([id]);
}

async function _enviarIds(ids) {
  try {
    const r = await fetch("/api/enviar", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ ids }),
    });
    const d = await r.json();
    mostrarToast(r.ok ? "⏳ " + d.mensagem : "Erro: " + d.erro, r.ok ? "info" : "error");
    if (r.ok) { fecharPainel(); setTimeout(carregarKanban, 2000); }
  } catch (e) {
    mostrarToast("Erro de rede.", "error");
  }
}

// ── Utilitários ───────────────────────────────────────────────────────────────

function esc(t) {
  const d = document.createElement("div");
  d.appendChild(document.createTextNode(String(t || "")));
  return d.innerHTML;
}

function fmtData(s) {
  try { return new Date(s).toLocaleString("pt-BR", {day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}); }
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
  carregarKanban();
  // Enter na nota
  document.getElementById("input-nota").addEventListener("keydown", e => {
    if (e.key === "Enter" && e.ctrlKey) adicionarNota();
  });
});
