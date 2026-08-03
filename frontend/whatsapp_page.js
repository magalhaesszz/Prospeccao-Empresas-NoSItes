/* ===== WhatsApp Management ===== */

let _qrTimer = null;
let _pollTimer = null;

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  atualizarStatus();
  carregarStats();
  carregarPendentes();
  carregarAgendamentos();
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
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#6B7280" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
    titulo.textContent = "Evolution API não configurada";
    sub.textContent    = "Configure as variáveis de ambiente (veja o guia abaixo)";
    acoes.innerHTML    = "";
    cardQr.classList.add("hidden");
    renderizarConfig(d.config);
    return;
  }

  renderizarConfig(d.config);

  if (d.conectado) {
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/><polyline points="9 12 11 14 15 10"/></svg>';
    icon.style.filter  = "none";
    titulo.textContent = "WhatsApp Conectado";
    sub.textContent    = d.numero ? `Número: ${d.numero}` : "Conexão ativa";
    acoes.innerHTML    = `<button class="btn btn-danger btn-sm" onclick="desconectar()">Desconectar</button>`;
    cardQr.classList.add("hidden");
    clearTimeout(_qrTimer);
  } else {
    icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#E11D48" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22z"/></svg>';
    titulo.textContent = "WhatsApp Desconectado";
    sub.textContent    = "Escaneie o QR Code para conectar";
    acoes.innerHTML    = `<button class="btn btn-primary" onclick="iniciarConexao()">Conectar</button>`;
    cardQr.classList.remove("hidden");
    // Limpa conversas ao detectar desconexão (evita mostrar dados de sessão anterior)
    if (_conversas.length) {
      _conversas = [];
      _chatAtual = null;
      _msgAtual  = [];
      const lista = document.getElementById("chat-lista");
      if (lista) lista.innerHTML = '<p class="vazio" style="padding:24px">Nenhuma conversa.</p>';
      document.getElementById("chat-conteudo")?.classList.add("hidden");
      document.getElementById("chat-vazio")?.classList.remove("hidden");
      document.getElementById("chat-contador").textContent = "";
    }
    if (!document.getElementById("qr-img").src.startsWith("data:")) {
      buscarQR();
    }
  }
}

function renderizarStatusErro(msg) {
  document.getElementById("status-icon").innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#E11D48" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="28" height="28"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
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
    if (d.ok) {
      // Limpa estado local para não mostrar dados da sessão anterior
      _conversas = [];
      _chatAtual = null;
      _msgAtual  = [];
      const lista = document.getElementById("chat-lista");
      if (lista) lista.innerHTML = '<p class="vazio" style="padding:24px">Nenhuma conversa.</p>';
      document.getElementById("chat-conteudo")?.classList.add("hidden");
      document.getElementById("chat-vazio")?.classList.remove("hidden");
      document.getElementById("chat-contador").textContent = "";
      mostrarToast("WhatsApp desconectado.", "info");
    } else {
      mostrarToast("Erro ao desconectar: " + (d.erro || ""), "error");
    }
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
        ${c.cliente ? '<span class="wa-chat-tag">Prospectado</span>' : ""}
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
  cancelarReply();
  c.nao_lidas = 0;  // zera badge local ao abrir
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
      <div class="wa-chat-cab-nome">${esc(c.nome)} ${c.cliente ? '<span class="wa-chat-tag">Prospectado</span>' : ""}</div>
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
    _marcarLida(d.mensagens);             // marca as recebidas como lidas
  } catch (e) {
    cont.innerHTML = '<p class="vazio" style="margin:auto">Erro ao carregar mensagens.</p>';
  }
}

function renderMensagens(msgs) {
  _msgAtual = msgs;
  Object.keys(_mediaCache).forEach(k => delete _mediaCache[k]); // limpa cache

  let html = "";
  let ultimaData = "";
  let ultimaDeMim = null;

  msgs.forEach((m, idx) => {
    const data = fmtDataSep(m.timestamp);
    if (data && data !== ultimaData) {
      html += `<div class="wa-msg-data"><span>${data}</span></div>`;
      ultimaData = data;
      ultimaDeMim = null;
    }

    // Agrupa mensagens do mesmo remetente (margem menor)
    const mesmaDe = ultimaDeMim === m.de_mim;
    ultimaDeMim = m.de_mim;

    const temKey    = m.key && m.key.id && !m.apagada;
    const podeApagar = m.de_mim && temKey;
    const acoes = temKey ? `
        <div class="wa-msg-acoes">
          <button title="Reagir" onclick="abrirReacoes(${idx}, this)">😀</button>
          <button title="Responder" onclick="responderCitando(${idx})">↩</button>
          <button title="Encaminhar" onclick="encaminharMsg(${idx})">➡</button>
          ${podeApagar ? `<button title="Apagar para todos" onclick="apagarMsg(${idx})">🗑</button>` : ""}
        </div>` : "";
    const reacao = m.reacao ? `<span class="wa-msg-reacao">${esc(m.reacao)}</span>` : "";
    html += `
      <div class="wa-msg ${m.de_mim ? "wa-msg-eu" : "wa-msg-outro"}${mesmaDe ? " wa-msg-seq" : ""}">
        <div class="wa-msg-bolha${m.tipo !== "texto" ? " wa-msg-bolha-midia" : ""}${m.apagada ? " wa-msg-apagada" : ""}">
          ${renderConteudoMsg(m, idx)}
          <span class="wa-msg-hora">${fmtHora(m.timestamp)}${m.de_mim ? " ✓✓" : ""}</span>
          ${reacao}
        </div>
        ${acoes}
      </div>`;
  });
  return html;
}

// Cache de mídia já carregada (key = índice da msg)
const _mediaCache = {};

function renderConteudoMsg(m, idx) {
  const tipo = m.tipo || "texto";
  const txt  = esc(m.texto || "");

  // Texto puro
  if (tipo === "texto") return txt || "[mensagem]";
  if (tipo === "localizacao") return `📍 ${txt}`;
  if (tipo === "contato") return `👤 ${txt}`;

  // Se já temos base64 em cache, usa direto
  if (_mediaCache[idx]) return _renderMidiaBase64(tipo, _mediaCache[idx], txt);

  // Placeholder com botão carregar (lazy)
  const icone = {
    imagem: "🖼️", audio: "🎵", video: "🎥",
    figurinha: "🌟", documento: "📄"
  }[tipo] || "📎";

  const label = {
    imagem: "Foto", audio: "Áudio", video: "Vídeo",
    figurinha: "Figurinha", documento: txt || "Documento"
  }[tipo] || tipo;

  return `<div class="wa-midia-placeholder" onclick="carregarMidia(${idx}, this)">
    <span class="wa-midia-icone">${icone}</span>
    <span class="wa-midia-label">${label}</span>
    <span class="wa-midia-btn">▶ Carregar</span>
  </div>`;
}

function _renderMidiaBase64(tipo, src, txt) {
  if (tipo === "audio") {
    return `<audio class="wa-msg-audio" controls src="${src}" preload="auto"></audio>`;
  }
  if (tipo === "imagem") {
    return `<img class="wa-msg-img" src="${src}" loading="lazy"
              onclick="abrirLightbox('${src.replace(/'/g,"\\'")}')"/>
            ${txt ? `<div class="wa-msg-legenda">${txt}</div>` : ""}`;
  }
  if (tipo === "figurinha") {
    return `<img class="wa-msg-figurinha" src="${src}" loading="lazy"/>`;
  }
  if (tipo === "video") {
    return `<video class="wa-msg-video" controls src="${src}" preload="none"></video>`;
  }
  if (tipo === "documento") {
    return `<a class="wa-msg-doc" href="${src}" target="_blank" rel="noopener">📄 ${txt || "Documento"}</a>`;
  }
  return `<a href="${src}" target="_blank">📎 Abrir arquivo</a>`;
}

async function carregarMidia(idx, el) {
  const m = _msgAtual[idx];
  if (!m || !m.raw_msg) {
    el.innerHTML = '<span style="color:var(--red)">Mídia não disponível</span>';
    return;
  }
  el.innerHTML = '<span class="wa-midia-carregando">⏳ Carregando...</span>';
  try {
    const r = await fetch("/api/whatsapp/media", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: m.raw_msg }),
    });
    const d = await r.json();
    if (!d.base64 || d.erro) {
      el.innerHTML = `<span style="color:var(--red)">Erro: ${esc(d.erro || "sem dados")}</span>`;
      return;
    }
    _mediaCache[idx] = d.base64;
    // Substitui o placeholder pelo conteúdo real
    const bolha = el.closest(".wa-msg-bolha");
    if (bolha) {
      const hora = bolha.querySelector(".wa-msg-hora")?.outerHTML || "";
      bolha.innerHTML = _renderMidiaBase64(m.tipo, d.base64, m.texto || "") + hora;
    }
  } catch (e) {
    el.innerHTML = '<span style="color:var(--red)">Erro de rede</span>';
  }
}

// Array das msgs da conversa aberta (pra carregarMidia acessar raw_msg)
let _msgAtual = [];

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

  // Se estiver respondendo/citando uma mensagem, monta o quoted
  let quoted = null;
  if (_respondendo != null) {
    const m = _msgAtual[_respondendo];
    if (m && m.key && m.key.id) quoted = { key: m.key, message: m.raw_msg || undefined };
  }
  const citando = _respondendo != null;
  cancelarReply();

  const cont = document.getElementById("chat-mensagens");
  const agora = Math.floor(Date.now() / 1000);
  cont.insertAdjacentHTML("beforeend", `
    <div class="wa-msg wa-msg-eu">
      <div class="wa-msg-bolha">${citando ? '<span class="wa-msg-citada">↩ resposta</span>' : ""}${esc(texto)}<span class="wa-msg-hora">${fmtHora(agora)} 🕓</span></div>
    </div>`);
  cont.scrollTop = cont.scrollHeight;

  try {
    const r = await fetch("/api/whatsapp/responder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ numero: _chatAtual.numero, texto, quoted }),
    });
    const d = await r.json();
    if (!d.ok) mostrarToast("Erro: " + (d.erro || "falha no envio"), "error");
  } catch (e) {
    mostrarToast("Erro de rede.", "error");
  }
}

// ── Responder citando / Encaminhar / Reagir ───────────────────────────────────
let _respondendo = null;

function responderCitando(idx) {
  const m = _msgAtual[idx];
  if (!m) return;
  _respondendo = idx;
  const prev = (m.texto || { imagem: "🖼️ Foto", audio: "🎤 Áudio", video: "🎥 Vídeo", documento: "📄 Documento", figurinha: "🌟 Figurinha" }[m.tipo] || "Mídia").slice(0, 90);
  document.getElementById("reply-titulo").textContent = m.de_mim ? "Você" : (_chatAtual?.nome || "Contato");
  document.getElementById("reply-texto").textContent = prev;
  document.getElementById("reply-bar").classList.remove("hidden");
  document.getElementById("chat-resposta").focus();
}

function cancelarReply() {
  _respondendo = null;
  document.getElementById("reply-bar")?.classList.add("hidden");
}

async function encaminharMsg(idx) {
  const m = _msgAtual[idx];
  if (!m) return;
  const texto = (m.texto || "").trim();
  if (!texto) { mostrarToast("Só é possível encaminhar texto por aqui.", "warning"); return; }
  const destino = prompt("Encaminhar para qual número? (com DDD, ex: 62999998888)");
  if (!destino) return;
  try {
    const r = await fetch("/api/whatsapp/encaminhar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ numero: destino.trim(), texto }),
    });
    const d = await r.json();
    if (!d.ok) mostrarToast("Erro: " + (d.erro || "falha"), "error");
    else mostrarToast("Encaminhado!", "success");
  } catch (e) { mostrarToast("Erro de rede.", "error"); }
}

const REACOES = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

function abrirReacoes(idx, btn) {
  // remove picker anterior
  document.querySelectorAll(".wa-reacao-picker").forEach(p => p.remove());
  const pick = document.createElement("div");
  pick.className = "wa-reacao-picker";
  pick.innerHTML = REACOES.map(e => `<span onclick="reagirMsg(${idx}, '${e}')">${e}</span>`).join("") +
    `<span class="wa-reacao-x" onclick="reagirMsg(${idx}, '')" title="Remover">🚫</span>`;
  btn.parentNode.appendChild(pick);
  setTimeout(() => {
    document.addEventListener("click", function fecha(ev) {
      if (!pick.contains(ev.target) && ev.target !== btn) { pick.remove(); document.removeEventListener("click", fecha); }
    });
  }, 0);
}

async function reagirMsg(idx, emoji) {
  document.querySelectorAll(".wa-reacao-picker").forEach(p => p.remove());
  const m = _msgAtual[idx];
  if (!m || !m.key || !m.key.id) { mostrarToast("Não é possível reagir a esta mensagem.", "warning"); return; }
  try {
    const r = await fetch("/api/whatsapp/reagir", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: m.key, emoji }),
    });
    const d = await r.json();
    if (!d.ok) { mostrarToast("Erro: " + (d.erro || "falha"), "error"); return; }
    m.reacao = emoji;
    const cont = document.getElementById("chat-mensagens");
    const scroll = cont.scrollTop;
    cont.innerHTML = renderMensagens(_msgAtual);
    cont.scrollTop = scroll;
  } catch (e) { mostrarToast("Erro de rede.", "error"); }
}

async function _marcarLida(msgs) {
  const keys = msgs.filter(m => !m.de_mim && m.key && m.key.id)
                   .slice(-30)
                   .map(m => ({ id: m.key.id, remoteJid: m.key.remoteJid, fromMe: false }));
  if (!keys.length) return;
  try {
    await fetch("/api/whatsapp/marcar-lida", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys }),
    });
  } catch (_) {}
}

// ── Apagar mensagem ───────────────────────────────────────────────────────────
async function apagarMsg(idx) {
  const m = _msgAtual[idx];
  if (!m || !m.key || !m.key.id) { mostrarToast("Não é possível apagar esta mensagem.", "warning"); return; }
  if (!confirm("Apagar esta mensagem para todos?")) return;
  try {
    const r = await fetch("/api/whatsapp/apagar-msg", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: m.key }),
    });
    const d = await r.json();
    if (!d.ok) { mostrarToast("Erro: " + (d.erro || "falha"), "error"); return; }
    m.apagada = true; m.tipo = "texto"; m.texto = "🚫 Você apagou esta mensagem";
    const cont = document.getElementById("chat-mensagens");
    cont.innerHTML = renderMensagens(_msgAtual);
    cont.scrollTop = cont.scrollHeight;
    mostrarToast("Mensagem apagada.", "info");
  } catch (e) { mostrarToast("Erro de rede.", "error"); }
}

// ── Anexos (imagem / vídeo / documento) ───────────────────────────────────────
function abrirAnexo() {
  if (!_chatAtual) { mostrarToast("Abra uma conversa primeiro.", "warning"); return; }
  document.getElementById("anexo-input").click();
}

function _fileToBase64(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
}

async function enviarAnexo(input) {
  const file = input.files && input.files[0];
  input.value = "";
  if (!file || !_chatAtual) return;
  if (file.size > 16 * 1024 * 1024) { mostrarToast("Arquivo muito grande (máx 16MB).", "warning"); return; }

  let mediatype = "document";
  if (file.type.startsWith("image/")) mediatype = "image";
  else if (file.type.startsWith("video/")) mediatype = "video";

  const b64 = await _fileToBase64(file);
  const cont = document.getElementById("chat-mensagens");
  const agora = Math.floor(Date.now() / 1000);
  const icone = mediatype === "image" ? "🖼️" : mediatype === "video" ? "🎥" : "📄";
  cont.insertAdjacentHTML("beforeend", `
    <div class="wa-msg wa-msg-eu">
      <div class="wa-msg-bolha wa-msg-bolha-midia">${icone} ${esc(file.name)}<span class="wa-msg-hora">${fmtHora(agora)} 🕓</span></div>
    </div>`);
  cont.scrollTop = cont.scrollHeight;

  try {
    const r = await fetch("/api/whatsapp/enviar-midia", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ numero: _chatAtual.numero, media: b64, mediatype, filename: file.name, mimetype: file.type }),
    });
    const d = await r.json();
    if (!d.ok) mostrarToast("Erro: " + (d.erro || "falha no envio"), "error");
    else mostrarToast("Enviado!", "success");
  } catch (e) { mostrarToast("Erro de rede.", "error"); }
}

// ── Áudio de voz (gravação) ───────────────────────────────────────────────────
let _mediaRecorder = null, _audioChunks = [], _gravTimer = null, _gravSeg = 0, _enviarAudio = false;

function _blobToBase64(blob) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(blob);
  });
}

function _barraGrav(on) {
  document.getElementById("chat-input-normal").classList.toggle("hidden", on);
  document.getElementById("chat-input-gravando").classList.toggle("hidden", !on);
}

function _tickTimer() {
  const mm = Math.floor(_gravSeg / 60), ss = String(_gravSeg % 60).padStart(2, "0");
  const el = document.getElementById("grav-timer");
  if (el) el.textContent = `${mm}:${ss}`;
  if (_gravSeg >= 300) { pararEnviarGravacao(); return; }  // limite 5 min
  _gravSeg++;
}

function _pararGravUI() { clearInterval(_gravTimer); _gravTimer = null; _barraGrav(false); }

async function toggleGravacao() {
  if (_mediaRecorder && _mediaRecorder.state === "recording") { pararEnviarGravacao(); return; }
  if (!_chatAtual) { mostrarToast("Abra uma conversa primeiro.", "warning"); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    mostrarToast("Gravação de áudio não suportada neste navegador.", "error"); return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    let mime = "audio/ogg;codecs=opus";
    if (!MediaRecorder.isTypeSupported(mime)) mime = "audio/webm;codecs=opus";
    if (!MediaRecorder.isTypeSupported(mime)) mime = "";
    _mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    _audioChunks = []; _enviarAudio = false;
    _mediaRecorder.ondataavailable = e => { if (e.data.size > 0) _audioChunks.push(e.data); };
    _mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      const enviar = _enviarAudio;
      _mediaRecorder = null;
      if (enviar) _finalizarEnvioAudio();
    };
    _mediaRecorder.start();
    _barraGrav(true); _gravSeg = 0; _tickTimer();
    _gravTimer = setInterval(_tickTimer, 1000);
  } catch (e) {
    mostrarToast("Permita o acesso ao microfone para gravar.", "error");
  }
}

function pararEnviarGravacao() {
  if (!_mediaRecorder) { _barraGrav(false); return; }
  _enviarAudio = true; _pararGravUI();
  if (_mediaRecorder.state !== "inactive") _mediaRecorder.stop();
}

function cancelarGravacao() {
  if (!_mediaRecorder) { _barraGrav(false); return; }
  _enviarAudio = false; _pararGravUI();
  if (_mediaRecorder.state !== "inactive") _mediaRecorder.stop();
}

async function _finalizarEnvioAudio() {
  const tipo = (_audioChunks[0] && _audioChunks[0].type) || "audio/ogg";
  const blob = new Blob(_audioChunks, { type: tipo });
  _audioChunks = [];
  if (!blob.size || !_chatAtual) return;

  const b64 = await _blobToBase64(blob);
  const cont = document.getElementById("chat-mensagens");
  const agora = Math.floor(Date.now() / 1000);
  cont.insertAdjacentHTML("beforeend", `
    <div class="wa-msg wa-msg-eu">
      <div class="wa-msg-bolha wa-msg-bolha-midia">🎤 Áudio enviado<span class="wa-msg-hora">${fmtHora(agora)} 🕓</span></div>
    </div>`);
  cont.scrollTop = cont.scrollHeight;

  try {
    const r = await fetch("/api/whatsapp/enviar-audio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ numero: _chatAtual.numero, audio: b64 }),
    });
    const d = await r.json();
    if (!d.ok) mostrarToast("Erro no áudio: " + (d.erro || "falha"), "error");
    else mostrarToast("Áudio enviado!", "success");
  } catch (e) { mostrarToast("Erro de rede.", "error"); }
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

// ── IA — Responder conversa ───────────────────────────────────────────────────

async function iaResponderConversa() {
  if (!_chatAtual) { mostrarToast("Abra uma conversa primeiro.", "warning"); return; }

  const ultima = [..._msgAtual].reverse().find(m => !m.de_mim);
  if (!ultima) { mostrarToast("Nenhuma mensagem do prospect encontrada.", "warning"); return; }

  const hist = _msgAtual.slice(-8).map(m =>
    `${m.de_mim ? "Eu" : _chatAtual.nome}: ${m.texto || "[mídia]"}`
  ).join("\n");

  const input = document.getElementById("chat-resposta");
  const btn   = document.getElementById("btn-ia-chat");

  if (btn) { btn.disabled = true; btn.textContent = "⏳"; }
  input.value    = "Gerando resposta com IA...";
  input.disabled = true;

  try {
    const r = await fetch("/api/ai/responder-conversa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        nome:              _chatAtual.nome,
        ultima_msg:        ultima.texto || "",
        historico_resumo:  hist,
      }),
    });
    const d = await r.json();
    if (!r.ok || d.erro) throw new Error(d.erro || "Erro");
    input.value = d.mensagem;
    input.focus();
    mostrarToast("Resposta IA gerada!", "success");
  } catch (e) {
    input.value = "";
    mostrarToast("Erro IA: " + e.message, "error");
  } finally {
    input.disabled = false;
    if (btn) { btn.disabled = false; btn.textContent = "⚡ IA"; }
  }
}

// ── IA — Gerar mensagem ───────────────────────────────────────────────────────

async function gerarMensagemIA() {
  const nome      = (document.getElementById("ia-nome")?.value      || "").trim();
  const categoria = (document.getElementById("ia-categoria")?.value || "").trim();
  const cidade    = (document.getElementById("ia-cidade")?.value    || "").trim();
  const btn       = document.getElementById("btn-ia-gerar");
  const resultado = document.getElementById("ia-resultado");
  const erroEl    = document.getElementById("ia-erro");

  if (!nome) { mostrarToast("Informe o nome da empresa.", "error"); return; }

  btn.disabled    = true;
  btn.textContent = "Gerando...";
  if (resultado) resultado.style.display = "none";
  if (erroEl)    erroEl.style.display    = "none";

  try {
    const r = await fetch("/api/whatsapp/gerar-mensagem", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ nome, categoria, cidade }),
    });
    const d = await r.json();
    if (d.erro) throw new Error(d.erro);

    const ta = document.getElementById("ia-mensagem-gerada");
    if (ta) ta.value = d.mensagem;
    if (resultado) resultado.style.display = "block";
    mostrarToast("Mensagem gerada!", "success");
  } catch (e) {
    if (erroEl) { erroEl.textContent = "Erro: " + e.message; erroEl.style.display = "block"; }
    mostrarToast("Erro ao gerar mensagem.", "error");
  } finally {
    btn.disabled    = false;
    btn.textContent = "Gerar";
  }
}

function copiarMensagemIA() {
  const ta = document.getElementById("ia-mensagem-gerada");
  if (!ta) return;
  navigator.clipboard.writeText(ta.value).then(() => mostrarToast("Copiado!", "success"));
}

function usarMensagemIA() {
  const ta  = document.getElementById("ia-mensagem-gerada");
  const inp = document.getElementById("teste-mensagem");
  if (!ta || !inp) return;
  inp.value = ta.value;
  inp.scrollIntoView({ behavior: "smooth", block: "center" });
  mostrarToast("Mensagem copiada para o campo de teste.", "info");
}

// ── Agendamentos ──────────────────────────────────────────────────────────────

async function carregarAgendamentos() {
  const lista = document.getElementById("lista-agendamentos");
  if (!lista) return;
  try {
    const r = await fetch("/api/agendamentos");
    const dados = await r.json();
    if (!dados.length) {
      lista.innerHTML = '<p class="vazio" style="padding:12px 0">Nenhum agendamento criado.</p>';
      return;
    }
    const DIAS = ["", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
    lista.innerHTML = dados.map(ag => {
      const diasStr = String(ag.dias_semana || "1,2,3,4,5").split(",")
        .map(d => DIAS[parseInt(d)] || d).join(", ");
      const ultima  = ag.ultima_execucao
        ? new Date(ag.ultima_execucao).toLocaleString("pt-BR", { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" })
        : "Nunca";
      const ativo   = ag.ativo === 1 || ag.ativo === true;
      return `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);flex-wrap:wrap">
          <div style="flex:1;min-width:150px">
            <strong style="font-size:.9rem">${esc(ag.nome)}</strong>
            <div style="font-size:.78rem;color:var(--muted);margin-top:2px">
              ${ag.hora_inicio}h–${ag.hora_fim}h &bull; ${diasStr} &bull; até ${ag.limite_dia}/dia
            </div>
            <div style="font-size:.75rem;color:var(--muted);margin-top:1px">Última execução: ${ultima}</div>
          </div>
          <div style="display:flex;gap:6px;align-items:center">
            <span class="badge" style="${ativo ? "background:#D1FAE5;color:#065F46" : "background:var(--surface-2);color:var(--muted)"}">${ativo ? "Ativo" : "Pausado"}</span>
            <button class="btn btn-sm btn-secondary" onclick="toggleAgendamento(${ag.id}, ${!ativo})">
              ${ativo ? "Pausar" : "Ativar"}
            </button>
            <button class="btn btn-sm btn-danger" onclick="deletarAgendamento(${ag.id})">Excluir</button>
          </div>
        </div>`;
    }).join("");
  } catch (e) {
    lista.innerHTML = `<p style="color:var(--brand)">Erro ao carregar: ${esc(e.message)}</p>`;
  }
}

async function criarAgendamento() {
  const nome   = (document.getElementById("ag-nome")?.value   || "").trim() || "Agendamento";
  const hIni   = parseInt(document.getElementById("ag-h-ini")?.value  || "9");
  const hFim   = parseInt(document.getElementById("ag-h-fim")?.value  || "18");
  const limite = parseInt(document.getElementById("ag-limite")?.value || "20");
  const dias   = (document.getElementById("ag-dias")?.value   || "1,2,3,4,5").trim();

  try {
    const r = await fetch("/api/agendamentos", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ nome, hora_inicio: hIni, hora_fim: hFim, limite_dia: limite, dias_semana: dias }),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.erro || "Falha");
    mostrarToast("Agendamento criado!", "success");
    carregarAgendamentos();
  } catch (e) {
    mostrarToast("Erro: " + e.message, "error");
  }
}

async function toggleAgendamento(id, ativo) {
  await fetch(`/api/agendamentos/${id}`, {
    method:  "PUT",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ ativo }),
  });
  carregarAgendamentos();
}

async function deletarAgendamento(id) {
  if (!confirm("Excluir este agendamento?")) return;
  await fetch(`/api/agendamentos/${id}`, { method: "DELETE" });
  mostrarToast("Agendamento excluído.", "info");
  carregarAgendamentos();
}
