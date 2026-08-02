/* ===== Gemini AI Hub ===== */

let _paginaAtualUrl  = "";
let _todasEmpresas   = [];
let _empresaSelecionada = null;

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  verificarStatusGemini();
  carregarPaginas();
  carregarEmpresasDB();
});

// ── Status Gemini ─────────────────────────────────────────────────────────────

async function verificarStatusGemini() {
  try {
    const d = await fetch("/api/gemini/status").then(r => r.json());
    const dot = document.getElementById("gemini-status-dot");
    const txt = document.getElementById("gemini-status-txt");
    if (d.configurado) {
      dot.style.background = "#10B981";
      txt.textContent      = "Gemini configurado";
    } else {
      dot.style.background = "#EF4444";
      txt.textContent      = "Configure GEMINI_API_KEY no Railway";
    }
  } catch (e) {
    console.error("Status Gemini:", e);
  }
}

// ── Busca de empresas do banco ────────────────────────────────────────────────

async function carregarEmpresasDB() {
  try {
    const dados = await fetch("/api/empresas").then(r => r.json());
    _todasEmpresas = dados || [];
  } catch (e) { _todasEmpresas = []; }
}

function buscarEmpresaDB() {
  const q   = (document.getElementById("gp-busca-db")?.value || "").trim().toLowerCase();
  const box = document.getElementById("gp-sugestoes");
  if (!box) return;
  if (!q || q.length < 2) { box.style.display = "none"; return; }

  const resultados = _todasEmpresas.filter(e =>
    (e.nome || "").toLowerCase().includes(q)
  ).slice(0, 8);

  if (!resultados.length) { box.style.display = "none"; return; }

  box.style.display = "block";
  box.innerHTML = resultados.map(e => `
    <div onclick="selecionarEmpresa(${e.id})"
         style="padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--border);transition:background .15s"
         onmouseover="this.style.background='var(--surface-2)'"
         onmouseout="this.style.background='transparent'">
      <strong style="font-size:.875rem">${esc(e.nome)}</strong>
      <span style="font-size:.75rem;color:var(--muted);margin-left:6px">${esc(e.categoria||'')} • ${esc(e.cidade||'')}</span>
    </div>`).join("");
}

function selecionarEmpresa(id) {
  const emp = _todasEmpresas.find(e => e.id === id);
  if (!emp) return;
  _empresaSelecionada = emp;

  const set = (el, val) => { const e = document.getElementById(el); if (e) e.value = val || ""; };
  set("gp-nome",      emp.nome);
  set("gp-categoria", emp.categoria || "");
  set("gp-cidade",    emp.cidade    || "");
  set("gm-nome",      emp.nome);
  set("gm-categoria", emp.categoria || "");
  set("gm-cidade",    emp.cidade    || "");

  const box = document.getElementById("gp-sugestoes");
  if (box) box.style.display = "none";
  const inp = document.getElementById("gp-busca-db");
  if (inp) inp.value = "";

  mostrarToast(`Empresa selecionada: ${emp.nome}`, "success");
}

// Fecha sugestões ao clicar fora
document.addEventListener("click", e => {
  const box = document.getElementById("gp-sugestoes");
  const inp = document.getElementById("gp-busca-db");
  if (box && !box.contains(e.target) && e.target !== inp) {
    box.style.display = "none";
  }
});

// ── Gerador de Landing Page ───────────────────────────────────────────────────

async function gerarPagina() {
  const nome      = (document.getElementById("gp-nome")?.value      || "").trim();
  const categoria = (document.getElementById("gp-categoria")?.value || "").trim();
  const cidade    = (document.getElementById("gp-cidade")?.value    || "").trim();
  const btn       = document.getElementById("btn-gerar-pagina");
  const resultado = document.getElementById("gp-resultado");

  if (!nome) { mostrarToast("Informe o nome da empresa.", "error"); return; }

  btn.disabled  = true;
  if (resultado) resultado.style.display = "none";

  const _btnOriginal = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg> Gerar Site com Gemini`;
  const _setSpinner = (msg) => {
    btn.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite">⟳</span> ${msg}`;
  };

  try {
    const payload = { nome, categoria, cidade };
    if (_empresaSelecionada?.id) payload.empresa_id = _empresaSelecionada.id;

    _setSpinner("Iniciando geração...");

    // 1. Dispara job em background
    const r0 = await fetch("/api/gemini/gerar-pagina", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const d0 = await r0.json();
    if (d0.erro) throw new Error(d0.erro);

    const jobId = d0.job_id;
    let tentativas = 0;
    const MAX_TENTATIVAS = 120; // 120 × 2s = 240s máximo

    // 2. Polling até terminar ou dar erro
    while (tentativas < MAX_TENTATIVAS) {
      await new Promise(res => setTimeout(res, 2000));
      tentativas++;
      _setSpinner(`Gemini gerando o site... (${tentativas * 2}s)`);

      let rs;
      try {
        const resp = await fetch(`/api/gemini/gerar-pagina/status/${jobId}`);
        rs = await resp.json();
        // 404 = servidor reiniciou e perdeu o job em memória
        if (resp.status === 404) throw new Error("Servidor reiniciou durante a geração. Tente novamente.");
      } catch (fetchErr) {
        // erro de rede temporário — continua polling
        if (fetchErr.message.includes("reiniciou")) throw fetchErr;
        continue;
      }

      if (rs.status === "ok") {
        _paginaAtualUrl = rs.url;
        const urlInp = document.getElementById("gp-url");
        const urlBar = document.getElementById("gp-url-bar");
        const iframe = document.getElementById("gp-iframe");
        const gmLink = document.getElementById("gm-link");
        if (urlInp) urlInp.value       = rs.url;
        if (urlBar) urlBar.textContent = rs.url;
        if (iframe) iframe.src         = rs.url;
        if (gmLink) gmLink.value       = rs.url;
        if (resultado) resultado.style.display = "block";
        mostrarToast("Site gerado com sucesso!", "success");
        carregarPaginas();
        return;
      }

      if (rs.status === "erro") throw new Error(rs.erro || "Erro na geração.");
      // rs.status === "gerando" → continua polling
    }

    throw new Error("Tempo limite atingido (4 min). Gemini não respondeu. Tente novamente.");
  } catch (e) {
    mostrarToast("Erro: " + e.message, "error");
    console.error(e);
  } finally {
    btn.disabled  = false;
    btn.innerHTML = _btnOriginal;
  }
}

function copiarUrlPagina() {
  const url = document.getElementById("gp-url")?.value || _paginaAtualUrl;
  if (!url) return;
  navigator.clipboard.writeText(url).then(() => mostrarToast("Link copiado!", "success"));
}

function abrirPagina() {
  const url = document.getElementById("gp-url")?.value || _paginaAtualUrl;
  if (url) window.open(url, "_blank");
}

function usarLinkNaMensagem() {
  const url  = document.getElementById("gp-url")?.value || _paginaAtualUrl;
  const nome = document.getElementById("gp-nome")?.value || "";
  if (url) {
    const gml = document.getElementById("gm-link");
    if (gml) gml.value = url;
    const chk = document.getElementById("gm-incluir-link");
    if (chk) { chk.checked = true; toggleLinkInput(); }
    const nomeInp = document.getElementById("gm-nome");
    if (nomeInp && !nomeInp.value) nomeInp.value = nome;
  }
  document.getElementById("card-gerador-msg")?.scrollIntoView({ behavior: "smooth", block: "start" });
  mostrarToast("Link adicionado — clique em Gerar Mensagem.", "info");
}

// ── Gerador de Mensagem ───────────────────────────────────────────────────────

function toggleLinkInput() {
  const chk = document.getElementById("gm-incluir-link");
  const box = document.getElementById("gm-link-box");
  if (box) box.style.display = chk?.checked ? "block" : "none";
}

async function gerarMensagemGemini() {
  const nome      = (document.getElementById("gm-nome")?.value      || "").trim();
  const categoria = (document.getElementById("gm-categoria")?.value || "").trim();
  const cidade    = (document.getElementById("gm-cidade")?.value    || "").trim();
  const incluirLink = document.getElementById("gm-incluir-link")?.checked;
  const link      = incluirLink ? (document.getElementById("gm-link")?.value || "").trim() : "";
  const btn       = document.getElementById("btn-gerar-msg");
  const resultado = document.getElementById("gm-resultado");
  const erroEl    = document.getElementById("gm-erro");

  if (!nome) { mostrarToast("Informe o nome da empresa.", "error"); return; }

  btn.disabled    = true;
  btn.textContent = "Gerando...";
  if (resultado) resultado.style.display = "none";
  if (erroEl)    erroEl.style.display    = "none";

  try {
    const r = await fetch("/api/gemini/gerar-mensagem", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ nome, categoria, cidade, link }),
    });
    const d = await r.json();
    if (d.erro) throw new Error(d.erro);

    const ta = document.getElementById("gm-mensagem");
    if (ta) ta.value = d.mensagem;
    if (resultado) resultado.style.display = "block";
    mostrarToast("Mensagem gerada!", "success");
  } catch (e) {
    if (erroEl) { erroEl.textContent = "Erro: " + e.message; erroEl.style.display = "block"; }
    mostrarToast("Erro ao gerar mensagem.", "error");
  } finally {
    btn.disabled    = false;
    btn.innerHTML   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Gerar Mensagem`;
  }
}

function copiarMensagemGemini() {
  const ta = document.getElementById("gm-mensagem");
  if (!ta) return;
  navigator.clipboard.writeText(ta.value).then(() => mostrarToast("Mensagem copiada!", "success"));
}

function usarMensagemGeminiNoTeste() {
  const ta  = document.getElementById("gm-mensagem");
  const msg = ta?.value || "";
  if (!msg) return;
  localStorage.setItem("_gemini_msg_para_teste", msg);
  mostrarToast("Mensagem salva! Vá para WhatsApp > Teste para usá-la.", "info");
}

// ── Lista de Páginas Geradas ──────────────────────────────────────────────────

async function carregarPaginas() {
  const lista  = document.getElementById("lista-paginas");
  const count  = document.getElementById("paginas-count");
  if (!lista) return;

  try {
    const paginas = await fetch("/api/gemini/paginas").then(r => r.json());
    if (count) count.textContent = paginas.length;

    if (!paginas.length) {
      lista.innerHTML = '<p class="vazio" style="padding:12px 0">Nenhum site gerado ainda.</p>';
      return;
    }

    lista.innerHTML = `
      <div class="tabela-wrapper">
        <table>
          <thead>
            <tr>
              <th>Empresa</th>
              <th>Link</th>
              <th style="text-align:center">Vistas</th>
              <th>Data</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            ${paginas.map(p => {
              const data = p.criado_em
                ? new Date(p.criado_em).toLocaleDateString("pt-BR", { day:"2-digit", month:"2-digit", year:"2-digit" })
                : "—";
              return `<tr>
                <td><strong style="font-size:.875rem">${esc(p.nome_empresa)}</strong></td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  <a href="${esc(p.url)}" target="_blank" style="color:var(--brand-l);font-size:.8rem">${esc(p.url)}</a>
                </td>
                <td style="text-align:center">
                  <span class="badge ${p.vistas > 0 ? 'badge-verde' : ''}">${p.vistas}</span>
                </td>
                <td style="font-size:.8rem;color:var(--muted)">${data}</td>
                <td style="display:flex;gap:5px;flex-wrap:wrap">
                  <button class="btn btn-sm btn-secondary" data-url="${esc(p.url)}" onclick="window.open(this.dataset.url,'_blank')">Ver</button>
                  <button class="btn btn-sm btn-secondary" data-url="${esc(p.url)}" onclick="navigator.clipboard.writeText(this.dataset.url).then(()=>mostrarToast('Copiado!','success'))">Copiar</button>
                  <button class="btn btn-sm btn-secondary" data-nome="${esc(p.nome_empresa)}" data-url="${esc(p.url)}" onclick="preencherGerador(this.dataset.nome,this.dataset.url)">+ Msg</button>
                  <button class="btn btn-sm btn-danger" data-pid="${p.id}" onclick="deletarPagina(parseInt(this.dataset.pid))">Excluir</button>
                </td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    lista.innerHTML = `<p style="color:var(--brand)">Erro: ${esc(e.message)}</p>`;
  }
}

function preencherGerador(nome, url) {
  const nomeInp = document.getElementById("gm-nome");
  const linkInp = document.getElementById("gm-link");
  const chk     = document.getElementById("gm-incluir-link");
  if (nomeInp) nomeInp.value = nome;
  if (linkInp) linkInp.value = url;
  if (chk) { chk.checked = true; toggleLinkInput(); }
  document.getElementById("card-gerador-msg")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deletarPagina(id) {
  if (!confirm("Excluir este site gerado? O link para o prospect vai parar de funcionar.")) return;
  await fetch(`/api/gemini/paginas/${id}`, { method: "DELETE" });
  mostrarToast("Site excluído.", "info");
  carregarPaginas();
}

// ── Utils ─────────────────────────────────────────────────────────────────────

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

// CSS para animação do spinner
const style = document.createElement("style");
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);
