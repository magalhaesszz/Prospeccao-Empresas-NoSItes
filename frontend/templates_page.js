/* ===== Templates de Mensagem ===== */

let _templates  = [];
let _editandoId = null;

async function carregarTemplates() {
  _templates = await fetch("/api/templates").then(r => r.json());
  renderizarLista();
}

function renderizarLista() {
  const lista = document.getElementById("lista-templates");

  if (!_templates.length) {
    lista.innerHTML = '<p class="vazio">Nenhum template criado. Crie o primeiro!</p>';
    return;
  }

  lista.innerHTML = _templates.map(t => `
    <div class="template-item">
      <div class="template-header">
        <span class="template-nome">
          ${esc(t.nome)}
          ${t.ativo ? '<span class="badge-ativo">✓ Ativo</span>' : ""}
        </span>
        <span style="font-size:.78rem;color:var(--muted)">${t.enviados} envios</span>
      </div>
      <div class="template-preview">${esc(t.mensagem.substring(0, 200))}${t.mensagem.length > 200 ? "..." : ""}</div>
      <div class="template-footer">
        <div class="template-acoes">
          ${!t.ativo ? `<button class="btn btn-sm btn-primary" onclick="ativarTemplate(${t.id})">⭐ Ativar</button>` : ""}
          <button class="btn btn-sm btn-secondary" onclick="editarTemplate(${t.id})">✏️ Editar</button>
          <button class="btn btn-sm btn-danger"    onclick="deletarTemplate(${t.id})">🗑️</button>
        </div>
      </div>
    </div>`).join("");
}

// ── Editor ────────────────────────────────────────────────────────────────────

function abrirEditor(templateId = null) {
  _editandoId = templateId;

  if (templateId) {
    const t = _templates.find(t => t.id === templateId);
    document.getElementById("modal-titulo").textContent     = "Editar Template";
    document.getElementById("ed-nome").value                = t.nome;
    document.getElementById("ed-mensagem").value            = t.mensagem;
  } else {
    document.getElementById("modal-titulo").textContent     = "Novo Template";
    document.getElementById("ed-nome").value                = "";
    document.getElementById("ed-mensagem").value            = "";
  }

  atualizarPreview();
  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById("modal-editor").classList.remove("hidden");
}

function fecharEditor() {
  document.getElementById("modal-overlay").classList.add("hidden");
  document.getElementById("modal-editor").classList.add("hidden");
  _editandoId = null;
}

function atualizarPreview() {
  const msg     = document.getElementById("ed-mensagem").value;
  const preview = msg.replace(/\{NOME_DA_EMPRESA\}/g, "Barbearia do João");
  document.getElementById("ed-preview").textContent = preview || "(escreva a mensagem acima)";
}

async function salvarTemplate() {
  const nome     = document.getElementById("ed-nome").value.trim();
  const mensagem = document.getElementById("ed-mensagem").value.trim();

  if (!nome || !mensagem) {
    mostrarToast("Preencha nome e mensagem.", "warning");
    return;
  }

  const url    = _editandoId ? `/api/templates/${_editandoId}` : "/api/templates";
  const method = _editandoId ? "PUT" : "POST";

  const r = await fetch(url, {
    method, headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ nome, mensagem }),
  });

  if (r.ok) {
    mostrarToast("Template salvo!", "success");
    fecharEditor();
    carregarTemplates();
  } else {
    const d = await r.json();
    mostrarToast("Erro: " + d.erro, "error");
  }
}

async function ativarTemplate(id) {
  await fetch(`/api/templates/${id}/ativar`, { method: "POST" });
  mostrarToast("Template ativado!", "success");
  carregarTemplates();
}

async function editarTemplate(id) {
  abrirEditor(id);
}

async function deletarTemplate(id) {
  if (!confirm("Deletar este template?")) return;
  await fetch(`/api/templates/${id}`, { method: "DELETE" });
  mostrarToast("Template removido.", "info");
  carregarTemplates();
}

// ── Utilitários ───────────────────────────────────────────────────────────────

function esc(t) {
  const d = document.createElement("div");
  d.appendChild(document.createTextNode(String(t || "")));
  return d.innerHTML;
}

function mostrarToast(msg, tipo = "info") {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.className   = "toast " + tipo;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = "toast oculto", 3500);
}

// ── IA — Gerar template ───────────────────────────────────────────────────────

async function gerarTemplateIA() {
  const desc   = (document.getElementById("ia-desc-template")?.value || "").trim();
  const status = document.getElementById("ia-template-status");
  const btn    = document.getElementById("btn-gerar-template-ia");

  if (!desc) { mostrarToast("Descreva o template que quer gerar.", "warning"); return; }

  if (btn)    { btn.disabled = true; btn.textContent = "⏳"; }
  if (status) { status.textContent = "Gerando com IA..."; status.style.display = "block"; }

  try {
    const r = await fetch("/api/ai/gerar-template", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ descricao: desc }),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro");

    const ta = document.getElementById("ed-mensagem");
    if (ta) { ta.value = d.template; atualizarPreview(); }
    if (status) { status.textContent = "✓ Pronto! Edite se necessário."; }
    mostrarToast("Template gerado com IA!", "success");
  } catch (e) {
    if (status) { status.textContent = "Erro: " + e.message; }
    mostrarToast("Erro IA: " + e.message, "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Gerar"; }
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  carregarTemplates();

  // Preview ao vivo
  document.getElementById("ed-mensagem").addEventListener("input", atualizarPreview);

  // Fecha modal com Escape
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") fecharEditor();
  });
});
