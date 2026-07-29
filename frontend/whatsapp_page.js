/* ===== WhatsApp Management ===== */

let _qrTimer = null;
let _pollTimer = null;

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  atualizarStatus();
  carregarStats();
  carregarPendentes();
  // Poll status a cada 8s enquanto na página
  _pollTimer = setInterval(() => atualizarStatus(true), 8000);
});

window.addEventListener("beforeunload", () => {
  clearInterval(_pollTimer);
  clearTimeout(_qrTimer);
});

// ── Status ────────────────────────────────────────────────────────────────────

async function atualizarStatus(silencioso = false) {
  try {
    const r = await fetch("/api/whatsapp/status");
    const d = await r.json();
    renderizarStatus(d);
  } catch (e) {
    if (!silencioso) renderizarStatusErro("Erro ao comunicar com o servidor.");
  }
}

function renderizarStatus(d) {
  const icon   = document.getElementById("status-icon");
  const titulo = document.getElementById("status-titulo");
  const sub    = document.getElementById("status-sub");
  const acoes  = document.getElementById("status-acoes");
  const cardQr = document.getElementById("card-qr");

  if (!d.configurado) {
    icon.textContent   = "⚙️";
    titulo.textContent = "Evolution API não configurada";
    sub.textContent    = "Configure as variáveis de ambiente (veja o guia abaixo)";
    acoes.innerHTML    = "";
    cardQr.classList.add("hidden");
    renderizarConfig(d.config);
    return;
  }

  renderizarConfig(d.config);

  if (d.conectado) {
    icon.textContent   = "✅";
    icon.style.filter  = "none";
    titulo.textContent = "WhatsApp Conectado";
    sub.textContent    = d.numero ? `Número: ${d.numero}` : "Conexão ativa";
    acoes.innerHTML    = `<button class="btn btn-danger btn-sm" onclick="desconectar()">Desconectar</button>`;
    cardQr.classList.add("hidden");
    clearTimeout(_qrTimer);
  } else {
    icon.textContent   = "🔴";
    titulo.textContent = "WhatsApp Desconectado";
    sub.textContent    = "Escaneie o QR Code para conectar";
    acoes.innerHTML    = `<button class="btn btn-primary" onclick="iniciarConexao()">Conectar</button>`;
    cardQr.classList.remove("hidden");
    if (!document.getElementById("qr-img").src.startsWith("data:")) {
      buscarQR();
    }
  }
}

function renderizarStatusErro(msg) {
  document.getElementById("status-icon").textContent   = "❌";
  document.getElementById("status-titulo").textContent = "Erro";
  document.getElementById("status-sub").textContent    = msg;
}

function renderizarConfig(cfg) {
  if (!cfg) return;
  const grid = document.getElementById("config-grid");
  const statusEl = document.getElementById("config-status");

  const itens = [
    { label: "API URL",   valor: cfg.webhook_url,  ok: !!cfg.webhook_url },
    { label: "Instância", valor: cfg.instance,     ok: !!cfg.instance },
    { label: "API Key",   valor: cfg.api_key_mask, ok: !!cfg.api_key_mask },
  ];

  const todos_ok = itens.every(i => i.ok);
  statusEl.innerHTML = todos_ok
    ? '<p class="wa-config-ok">✅ Todas as variáveis configuradas.</p>'
    : '<p class="wa-config-warn">⚠️ Configure as variáveis faltantes no Railway → Variables.</p>';

  grid.innerHTML = itens.map(i => `
    <div class="wa-config-item ${i.ok ? "ok" : "faltando"}">
      <span class="wa-config-label">${i.label}</span>
      <span class="wa-config-valor">${i.ok ? esc(i.valor) : "Não configurado"}</span>
      <span class="wa-config-badge">${i.ok ? "✓" : "✗"}</span>
    </div>`).join("");
}

// ── QR Code ───────────────────────────────────────────────────────────────────

async function iniciarConexao() {
  mostrarToast("Iniciando conexão...", "info");
  await buscarQR();
}

async function buscarQR() {
  const img     = document.getElementById("qr-img");
  const loading = document.getElementById("qr-loading");
  const timer   = document.getElementById("qr-timer");

  img.style.display     = "none";
  loading.style.display = "block";
  clearTimeout(_qrTimer);

  try {
    const r = await fetch("/api/whatsapp/qrcode");
    const d = await r.json();

    if (d.erro) {
      loading.textContent = "Erro: " + d.erro;
      return;
    }

    if (d.conectado) {
      loading.style.display = "none";
      atualizarStatus();
      mostrarToast("WhatsApp já está conectado!", "success");
      return;
    }

    if (d.base64) {
      img.src              = d.base64;
      img.style.display    = "block";
      loading.style.display = "none";

      // QR expira em ~30s — countdown
      let seg = 29;
      timer.textContent = `QR expira em ${seg}s`;
      const countdown = setInterval(() => {
        seg--;
        timer.textContent = `QR expira em ${seg}s`;
        if (seg <= 0) {
          clearInterval(countdown);
          timer.textContent = "QR expirado — clique em Novo QR Code";
        }
      }, 1000);

      // Verifica se conectou após scan
      _qrTimer = setTimeout(async () => {
        clearInterval(countdown);
        timer.textContent = "";
        await atualizarStatus();
      }, 30000);
    } else {
      loading.textContent = "QR não disponível. Tente novamente.";
    }
  } catch (e) {
    loading.textContent = "Erro ao buscar QR Code.";
  }
}

// ── Desconectar ───────────────────────────────────────────────────────────────

async function desconectar() {
  if (!confirm("Desconectar o WhatsApp? Você precisará escanear o QR novamente.")) return;
  try {
    const r = await fetch("/api/whatsapp/desconectar", { method: "POST" });
    const d = await r.json();
    mostrarToast(d.ok ? "WhatsApp desconectado." : "Erro ao desconectar.", d.ok ? "info" : "error");
    setTimeout(atualizarStatus, 1000);
  } catch (e) {
    mostrarToast("Erro de rede.", "error");
  }
}

// ── Enviar Teste ──────────────────────────────────────────────────────────────

async function enviarTeste() {
  const numero   = document.getElementById("teste-numero").value.trim();
  const mensagem = document.getElementById("teste-mensagem").value.trim() || "Olá! Teste de conexão do Prospector. 🚀";
  const resultado = document.getElementById("teste-resultado");
  const btn       = document.getElementById("btn-teste");

  if (!numero) { mostrarToast("Informe o telefone.", "warning"); return; }

  btn.disabled        = true;
  resultado.textContent = "Enviando...";
  resultado.style.color = "var(--muted)";

  try {
    const r = await fetch("/api/whatsapp/teste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ numero, mensagem }),
    });
    const d = await r.json();

    if (d.ok) {
      resultado.textContent = "✅ Mensagem enviada com sucesso!";
      resultado.style.color = "var(--green)";
      mostrarToast("Mensagem enviada!", "success");
    } else {
      resultado.textContent = "❌ Erro: " + (d.erro || "Falha no envio.");
      resultado.style.color = "var(--red)";
      mostrarToast("Erro no envio.", "error");
    }
  } catch (e) {
    resultado.textContent = "❌ Erro de conexão.";
    resultado.style.color = "var(--red)";
  } finally {
    btn.disabled = false;
  }
}

// ── Stats ─────────────────────────────────────────────────────────────────────

async function carregarStats() {
  try {
    const r = await fetch("/api/whatsapp/stats");
    const d = await r.json();
    document.getElementById("st-hoje").textContent     = d.enviadas_hoje ?? "—";
    document.getElementById("st-total").textContent    = d.total_enviadas ?? "—";
    document.getElementById("st-erros").textContent    = d.com_erro ?? "—";
    document.getElementById("st-pendentes").textContent = d.pendentes ?? "—";
  } catch (_) {}
}

// ── Disparo em massa (pendentes) ──────────────────────────────────────────────

async function carregarPendentes() {
  try {
    const r = await fetch("/api/whatsapp/pendentes");
    const d = await r.json();
    const el = document.getElementById("qtd-pendentes");
    if (el) el.textContent = d.pendentes ?? 0;
    const btn = document.getElementById("btn-disparar-pendentes");
    if (btn) btn.disabled = !d.pendentes;
  } catch (_) {}
}

async function dispararPendentes() {
  const limiteRaw = document.getElementById("disparo-limite").value.trim();
  const limite = limiteRaw ? parseInt(limiteRaw, 10) : null;
  const qtd = document.getElementById("qtd-pendentes").textContent;

  const msg = limite
    ? `Disparar para até ${limite} empresa(s) pendente(s)?`
    : `Disparar para TODAS as ${qtd} empresa(s) pendentes?`;
  if (!confirm(msg)) return;

  const btn = document.getElementById("btn-disparar-pendentes");
  btn.disabled = true;

  try {
    const r = await fetch("/api/whatsapp/disparar-pendentes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(limite ? { limite } : {}),
    });
    const d = await r.json();
    if (!r.ok) {
      mostrarToast("Erro: " + (d.erro || "falha"), "error");
      btn.disabled = false;
      return;
    }
    mostrarToast("⏳ " + d.mensagem, "info");
    // Recarrega stats/pendentes depois de um tempo
    setTimeout(() => { carregarStats(); carregarPendentes(); }, 5000);
  } catch (e) {
    mostrarToast("Erro de rede.", "error");
    btn.disabled = false;
  }
}

// ── Conversas (WhatsApp Web) ──────────────────────────────────────────────────

let _chatAtual = null;
let _conversas = [];

let _fsAncora = null;  // marcador do lugar original do card

function toggleTelaCheia() {
  const card = document.getElementById("card-conversas");
  const btn  = document.getElementById("btn-fullscreen");
  const entrando = !card.classList.contains("fullscreen");

  if (entrando) {
    // Move o card pra fora (direto no body) — evita que transform de ancestral
    // quebre o position:fixed. Deixa um marcador pra restaurar depois.
    _fsAncora = document.createComment("chat-anchor");
    card.parentNode.insertBefore(_fsAncora, card);
    document.body.appendChild(card);
    card.classList.add("fullscreen");
    document.body.classList.add("chat-fullscreen");
    if (btn) btn.textContent = "✕";
  } else {
    card.classList.remove("fullscreen");
    card.classList.remove("ver-conversa");
    document.body.classList.remove("chat-fullscreen");
    if (btn) btn.textContent = "⛶";
    // Restaura pro lugar original
    if (_fsAncora && _fsAncora.parentNode) {
      _fsAncora.parentNode.insertBefore(card, _fsAncora);
      _fsAncora.remove();
      _fsAncora = null;
    }
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const card = document.getElementById("card-conversas");
    if (card && card.classList.contains("fullscreen")) toggleTelaCheia();
  }
});

async function carregarConversas() {
  const lista = document.getElementById("chat-lista");
  lista.innerHTML = '<p class="vazio" style="padding:24px">Carregando...</p>';
  try {
    const r = await fetch("/api/whatsapp/conversas");
    const d = await r.json();
    if (d.erro) {
      lista.innerHTML = `<p class="vazio" style="padding:24px">${esc(d.erro)}</p>`;
      return;
    }
    _conversas = d.conversas || [];
    document.getElementById("chat-contador").textContent = _conversas.length ? `(${_conversas.length})` : "";
    renderConversas(_conversas);
  } catch (e) {
    lista.innerHTML = '<p class="vazio" style="padding:24px">Erro ao carregar conversas.</p>';
  }
}

function renderConversas(convs) {
  const lista = document.getElementById("chat-lista");
  if (!convs.length) {
    lista.innerHTML = '<p class="vazio" style="padding:24px">Nenhuma conversa.</p>';
    return;
  }
  lista.innerHTML = convs.map((c, i) => `
    <div class="wa-chat-item ${_chatAtual && _chatAtual.jid === c.jid ? "ativo" : ""}" onclick="abrirConversaIdx(${i})">
      <div class="wa-chat-avatar">${c.foto ? `<img src="${esc(c.foto)}" onerror="this.parentNode.innerHTML=iniciais('${esc(c.nome)}')"/>` : iniciais(c.nome)}</div>
      <div class="wa-chat-item-info">
        <div class="wa-chat-item-linha1">
          <span class="wa-chat-item-nome">${esc(c.nome)}</span>
          ${c.timestamp ? `<span class="wa-chat-item-hora">${fmtHora(c.timestamp)}</span>` : ""}
        </div>
        <div class="wa-chat-item-linha2">
          <span class="wa-chat-item-prev">${esc(c.ultima_msg || "—")}</span>
          ${c.nao_lidas ? `<span class="wa-chat-badge">${c.nao_lidas}</span>` : ""}
        </div>
        ${c.cliente ? '<span class="wa-chat-tag">🎯 Prospectado</span>' : ""}
      </div>
    </div>`).join("");
}

function filtrarConversas() {
  const termo = (document.getElementById("chat-busca").value || "").toLowerCase().trim();
  if (!termo) { renderConversas(_conversas); return; }
  const filtradas = _conversas.filter(c =>
    (c.nome || "").toLowerCase().includes(termo) ||
    (c.numero || "").includes(termo) ||
    (c.ultima_msg || "").toLowerCase().includes(termo)
  );
  renderConversas(filtradas);
}

function abrirConversaIdx(i) {
  const c = _conversas[i];
  if (c) abrirConversa(c);
}

function voltarLista() {
  document.getElementById("card-conversas").classList.remove("ver-conversa");
}

async function abrirConversa(c) {
  _chatAtual = c;
  renderConversas(_conversas.filter(x =>
    !document.getElementById("chat-busca").value.trim() ||
    JSON.stringify(x).toLowerCase().includes(document.getElementById("chat-busca").value.toLowerCase())
  ));

  // Mobile em tela cheia: mostra painel, esconde lista
  document.getElementById("card-conversas").classList.add("ver-conversa");

  document.getElementById("chat-vazio").classList.add("hidden");
  document.getElementById("chat-conteudo").classList.remove("hidden");
  document.getElementById("chat-cabecalho").innerHTML = `
    <button class="wa-chat-voltar" onclick="voltarLista()" title="Voltar">‹</button>
    <div class="wa-chat-avatar">${c.foto ? `<img src="${esc(c.foto)}" onerror="this.parentNode.textContent='👤'"/>` : "👤"}</div>
    <div>
      <div class="wa-chat-cab-nome">${esc(c.nome)} ${c.cliente ? '<span class="wa-chat-tag">🎯 Prospectado</span>' : ""}</div>
      <div class="wa-chat-cab-num">+${esc(c.numero)}</div>
    </div>`;

  const cont = document.getElementById("chat-mensagens");
  cont.innerHTML = '<p class="vazio" style="margin:auto">Carregando mensagens...</p>';

  try {
    const r = await fetch("/api/whatsapp/mensagens?jid=" + encodeURIComponent(c.jid));
    const d = await r.json();
    if (d.erro || !d.mensagens || !d.mensagens.length) {
      cont.innerHTML = `<p class="vazio" style="margin:auto">${d.erro ? esc(d.erro) : "Nenhuma mensagem nesta conversa."}</p>`;
      return;
    }
    cont.innerHTML = renderMensagens(d.mensagens);
    cont.scrollTop = cont.scrollHeight;   // começa no fim; rola pra cima = histórico
  } catch (e) {
    cont.innerHTML = '<p class="vazio" style="margin:auto">Erro ao carregar mensagens.</p>';
  }
}

function renderMensagens(msgs) {
  let html = "";
  let ultimaData = "";
  msgs.forEach(m => {
    const data = fmtDataSep(m.timestamp);
    if (data && data !== ultimaData) {
      html += `<div class="wa-msg-data"><span>${data}</span></div>`;
      ultimaData = data;
    }
    html += `
      <div class="wa-msg ${m.de_mim ? "wa-msg-eu" : "wa-msg-outro"}">
        <div class="wa-msg-bolha">
          ${renderConteudoMsg(m)}
          <span class="wa-msg-hora">${fmtHora(m.timestamp)}${m.de_mim ? " ✓✓" : ""}</span>
        </div>
      </div>`;
  });
  return html;
}

function renderConteudoMsg(m) {
  const tipo = m.tipo || "texto";
  const url  = m.url  || "";
  const txt  = esc(m.texto || "");

  if (tipo === "imagem" && url) {
    return `<img class="wa-msg-img" src="${esc(url)}" loading="lazy"
              onclick="abrirLightbox('${esc(url)}')" alt="Imagem"/>
            ${txt ? `<div style="margin-top:4px">${txt}</div>` : ""}`;
  }
  if (tipo === "figurinha" && url) {
    return `<img class="wa-msg-figurinha" src="${esc(url)}" loading="lazy" alt="Figurinha"/>`;
  }
  if (tipo === "audio" && url) {
    return `<audio class="wa-msg-audio" controls src="${esc(url)}" preload="none"></audio>`;
  }
  if (tipo === "video" && url) {
    return `<video class="wa-msg-video" controls src="${esc(url)}" preload="none"></video>`;
  }
  if (tipo === "documento" && url) {
    return `<a class="wa-msg-doc" href="${esc(url)}" target="_blank" rel="noopener">
              📄 ${txt || "Documento"}
            </a>`;
  }
  if (tipo === "localizacao") {
    return `<span>${txt}</span>`;
  }
  // texto e fallback
  return txt || "[mensagem]";
}

// ── Lightbox ──────────────────────────────────────────────────────────────────
function abrirLightbox(url) {
  document.getElementById("wa-lightbox-img").src = url;
  document.getElementById("wa-lightbox").classList.remove("hidden");
}
function fecharLightbox() {
  document.getElementById("wa-lightbox").classList.add("hidden");
}
document.addEventListener("keydown", e => {
  if (e.key === "Escape") fecharLightbox();
});

// ── Emoji picker ──────────────────────────────────────────────────────────────
const EMOJIS = [
  "😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇","🙂","🙃","😉","😌","😍",
  "🥰","😘","😗","😙","😚","😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🥸",
  "😏","😒","😞","😔","😟","😕","🙁","☹️","😣","😖","😫","😩","🥺","😢","😭",
  "😤","😠","😡","🤬","🤯","😳","🥵","🥶","😱","😨","😰","😥","😓","🤗","🤔",
  "🤭","🤫","🤥","😶","😑","😬","🙄","😯","😦","😧","😮","😲","🥱","😴","🤤",
  "😪","😵","🤐","🥴","🤢","🤮","🤧","😷","🤒","🤕","🤑","🤠","😈","👿","👹",
  "💀","☠️","💩","🤡","👻","👽","👾","🤖","😺","😸","😹","😻","😼","😽","🙀",
  "👍","👎","👌","✌️","🤞","🤟","🤘","🤙","👋","🤚","🖐️","✋","🖖","👏","🙌",
  "🤲","🤜","🤛","✊","👊","🤛","💪","🦾","🖕","☝️","👆","👇","👈","👉","🤳",
  "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❣️","💕","💞","💓","💗",
  "💖","💘","💝","💟","♥️","🔥","✨","⭐","🌟","💫","❄️","🎉","🎊","🎈","🏆",
  "🙏","💯","✅","❌","⚡","🚀","💡","💬","👀","🎯","💼","📱","💻","🌎","🏠",
];

function toggleEmoji() {
  const picker = document.getElementById("emoji-picker");
  if (picker.classList.contains("hidden")) {
    if (!picker.innerHTML) {
      picker.innerHTML = EMOJIS.map(e =>
        `<span onclick="inserirEmoji('${e}')">${e}</span>`).join("");
    }
    picker.classList.remove("hidden");
  } else {
    picker.classList.add("hidden");
  }
}

function inserirEmoji(e) {
  const inp = document.getElementById("chat-resposta");
  const pos = inp.selectionStart || inp.value.length;
  inp.value = inp.value.slice(0, pos) + e + inp.value.slice(pos);
  inp.focus();
  inp.setSelectionRange(pos + e.length, pos + e.length);
}

// Fecha picker ao clicar fora
document.addEventListener("click", e => {
  const picker = document.getElementById("emoji-picker");
  if (picker && !picker.contains(e.target) && !e.target.classList.contains("wa-emoji-btn")) {
    picker.classList.add("hidden");
  }
});

async function responderConversa() {
  if (!_chatAtual) return;
  const input = document.getElementById("chat-resposta");
  const texto = input.value.trim();
  if (!texto) return;
  input.value = "";

  const cont = document.getElementById("chat-mensagens");
  const agora = Math.floor(Date.now() / 1000);
  cont.insertAdjacentHTML("beforeend", `
    <div class="wa-msg wa-msg-eu">
      <div class="wa-msg-bolha">${esc(texto)}<span class="wa-msg-hora">${fmtHora(agora)} 🕓</span></div>
    </div>`);
  cont.scrollTop = cont.scrollHeight;

  try {
    const r = await fetch("/api/whatsapp/responder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ numero: _chatAtual.numero, texto }),
    });
    const d = await r.json();
    if (!d.ok) mostrarToast("Erro: " + (d.erro || "falha no envio"), "error");
  } catch (e) {
    mostrarToast("Erro de rede.", "error");
  }
}

function iniciais(nome) {
  const parts = (nome || "?").trim().split(/\s+/);
  return (parts[0][0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
}

// Timestamp Evolution vem em segundos (unix) ou ms — normaliza
function _tsMs(ts) {
  const n = Number(ts) || 0;
  if (!n) return 0;
  return n > 1e12 ? n : n * 1000;   // <1e12 => segundos
}
function fmtHora(ts) {
  const ms = _tsMs(ts);
  if (!ms) return "";
  try { return new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
  catch (_) { return ""; }
}
function fmtDataSep(ts) {
  const ms = _tsMs(ts);
  if (!ms) return "";
  const d = new Date(ms), hoje = new Date();
  const ontem = new Date(); ontem.setDate(hoje.getDate() - 1);
  if (d.toDateString() === hoje.toDateString()) return "Hoje";
  if (d.toDateString() === ontem.toDateString()) return "Ontem";
  try { return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }); }
  catch (_) { return ""; }
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
