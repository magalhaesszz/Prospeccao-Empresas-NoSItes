/* Marca contatos feitos manualmente como já enviados, sem disparar mensagem. */
(function () {
  const corpo = document.getElementById("corpo-cards");
  if (!corpo) return;

  function empresaDoCard(card) {
    const id = Number((card.id || "").replace("card-", ""));
    if (!id || typeof APP === "undefined") return null;
    return APP.empresas.find(e => Number(e.id) === id) || null;
  }

  function adicionarControles() {
    corpo.querySelectorAll(".empresa-card").forEach(card => {
      if (card.querySelector(".btn-marcar-enviado-manual")) return;

      const emp = empresaDoCard(card);
      if (!emp || emp.mensagem_enviada) return;

      const linha = document.createElement("div");
      linha.className = "acao-disparo-manual";
      linha.style.cssText = "margin-top:8px;padding-top:8px;border-top:1px dashed var(--border);display:flex;align-items:center;gap:8px;flex-wrap:wrap";

      const dica = document.createElement("span");
      dica.textContent = "Enviou por fora do sistema?";
      dica.style.cssText = "font-size:.7rem;color:var(--muted)";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm btn-secondary btn-marcar-enviado-manual";
      btn.style.cssText = "font-size:.72rem;display:inline-flex;align-items:center;gap:5px";
      btn.innerHTML = "✓ Marcar como enviado";
      btn.onclick = () => marcarDisparoManual(emp.id, btn);

      linha.appendChild(dica);
      linha.appendChild(btn);
      card.appendChild(linha);
    });
  }

  window.marcarDisparoManual = async function (empresaId, btn) {
    const emp = typeof APP !== "undefined"
      ? APP.empresas.find(e => Number(e.id) === Number(empresaId))
      : null;

    const nome = emp?.nome || "esta empresa";
    if (!confirm(`Marcar ${nome} como mensagem já enviada manualmente?`)) return;

    const textoOriginal = btn?.textContent || "✓ Marcar como enviado";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Marcando...";
    }

    try {
      const resp = await fetch(`/api/crm/empresa/${empresaId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "contatado", mensagem_enviada: 1 }),
      });
      const dados = await resp.json().catch(() => ({}));
      if (!resp.ok || dados.erro) {
        throw new Error(dados.erro || `HTTP ${resp.status}`);
      }

      if (emp) {
        emp.status = "contatado";
        emp.mensagem_enviada = 1;
        APP.selecionados?.delete?.(Number(empresaId));
      }

      if (typeof _aplicarFiltro === "function") {
        _aplicarFiltro();
      } else {
        const card = document.getElementById(`card-${empresaId}`);
        card?.classList.add("empresa-card-enviada");
      }

      if (typeof mostrarToast === "function") {
        mostrarToast(`${nome} marcada como já enviada.`, "success");
      }
    } catch (e) {
      if (btn) {
        btn.disabled = false;
        btn.textContent = textoOriginal;
      }
      if (typeof mostrarToast === "function") {
        mostrarToast("Erro ao marcar como enviada: " + e.message, "error");
      }
    }
  };

  const observer = new MutationObserver(adicionarControles);
  observer.observe(corpo, { childList: true, subtree: false });
  adicionarControles();
})();
