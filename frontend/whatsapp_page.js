/* ===== WhatsApp Management ===== */

let _qrTimer = null;
let _pollTimer = null;

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  atualizarStatus();
  carregarStats();
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
