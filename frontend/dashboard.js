/* ===== Dashboard ===== */

let _charts = {};

async function carregarDashboard() {
  try {
    const dados = await fetch("/api/dashboard/stats").then(r => r.json());
    renderizarKPIs(dados.kpis);
    renderizarGraficos(dados);
    renderizarErros(dados.erros || []);
  } catch (e) {
    console.error("Erro dashboard:", e);
  }
}

function renderizarKPIs(kpis) {
  const set = (id, val) => { const el=document.getElementById(id); if(el) el.textContent = val ?? "—"; };
  set("kpi-total",        kpis.total_prospectadas);
  set("kpi-sem-site",     kpis.sem_site);
  set("kpi-enviadas",     kpis.enviadas);
  set("kpi-interessados", kpis.interessados);
  set("kpi-fechados",     kpis.fechados);
  set("kpi-blacklist",    kpis.blacklist);
}

function _destruirChart(id) {
  if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
}

function renderizarGraficos(dados) {
  const CORES = ["#2563EB","#10B981","#F59E0B","#8B5CF6","#EF4444","#06B6D4","#EC4899"];

  // ── Funil CRM ─────────────────────────────────────────────────────────────
  _destruirChart("funil");
  const crm = dados.crm || {};
  _charts["funil"] = new Chart(document.getElementById("chart-funil"), {
    type: "bar",
    data: {
      labels: ["Novo","Contatado","Interessado","Fechado","Perdido"],
      datasets: [{
        label: "Empresas",
        data: [crm.novo||0, crm.contatado||0, crm.interessado||0, crm.fechado||0, crm.perdido||0],
        backgroundColor: ["#2563EB","#F59E0B","#8B5CF6","#10B981","#EF4444"],
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
    },
  });

  // ── Site vs Sem Site ──────────────────────────────────────────────────────
  _destruirChart("site");
  const dist = dados.distribuicao || {};
  _charts["site"] = new Chart(document.getElementById("chart-site"), {
    type: "doughnut",
    data: {
      labels: ["Sem site","Com site"],
      datasets: [{
        data: [dist.sem_site||0, dist.com_site||0],
        backgroundColor: ["#10B981","#EF4444"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom" } },
      cutout: "65%",
    },
  });

  // ── Prospecções por dia ───────────────────────────────────────────────────
  _destruirChart("dia");
  const pd = dados.por_dia || [];
  _charts["dia"] = new Chart(document.getElementById("chart-por-dia"), {
    type: "line",
    data: {
      labels: pd.map(d => d.data),
      datasets: [{
        label: "Empresas prospectadas",
        data: pd.map(d => d.total),
        borderColor: "#2563EB",
        backgroundColor: "rgba(37,99,235,.1)",
        fill: true,
        tension: 0.3,
        pointRadius: 4,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
    },
  });

  // ── Top Categorias ────────────────────────────────────────────────────────
  _destruirChart("cat");
  const cats = dados.top_categorias || [];
  _charts["cat"] = new Chart(document.getElementById("chart-categorias"), {
    type: "doughnut",
    data: {
      labels: cats.map(c => c.categoria),
      datasets: [{
        data: cats.map(c => c.total),
        backgroundColor: CORES,
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom", labels: { font: { size: 11 } } } },
    },
  });

  // ── Top Cidades ───────────────────────────────────────────────────────────
  _destruirChart("cid");
  const cids = dados.top_cidades || [];
  _charts["cid"] = new Chart(document.getElementById("chart-cidades"), {
    type: "bar",
    data: {
      labels: cids.map(c => c.cidade),
      datasets: [{
        label: "Empresas",
        data: cids.map(c => c.total),
        backgroundColor: "#06B6D4",
        borderRadius: 6,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { x: { beginAtZero: true, ticks: { stepSize: 1 } } },
    },
  });
}

function renderizarErros(erros) {
  const sec = document.getElementById("secao-erros");
  if (!erros.length) { sec.style.display = "none"; return; }
  sec.style.display = "";
  const tb = document.getElementById("tabela-erros");
  tb.innerHTML = erros.map(e => `
    <tr>
      <td>${esc(e.nome)}</td>
      <td>${esc(e.telefone||"—")}</td>
      <td>${e.tentativas_envio||0}</td>
      <td style="font-size:.8rem;color:var(--muted)">${esc(e.erro_envio||"—")}</td>
    </tr>`).join("");
}

function esc(t) {
  const d = document.createElement("div");
  d.appendChild(document.createTextNode(String(t||"")));
  return d.innerHTML;
}

async function carregarFunilConversao() {
  const container = document.getElementById("funil-container");
  if (!container) return;
  try {
    const funil = await fetch("/api/dashboard/funil").then(r => r.json());
    const etapas = [
      { label: "Prospectadas",  val: funil.prospectadas, cor: "#6366F1" },
      { label: "Sem Site",      val: funil.sem_site,     cor: "#2563EB" },
      { label: "Disparadas",    val: funil.disparadas,   cor: "#F59E0B" },
      { label: "Responderam",   val: funil.responderam,  cor: "#8B5CF6" },
      { label: "Interessadas",  val: funil.interessadas, cor: "#10B981" },
      { label: "Fechadas",      val: funil.fechadas,     cor: "#E11D48" },
    ];
    const max = Math.max(...etapas.map(e => e.val), 1);
    container.innerHTML = etapas.map((e, i) => {
      const pct   = Math.max(4, Math.round((e.val / max) * 100));
      const conv  = i > 0 && etapas[i-1].val > 0
        ? ` <span style="font-size:.7rem;color:var(--muted)">(${Math.round(e.val/etapas[i-1].val*100)}% da etapa anterior)</span>`
        : "";
      return `
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
            <span style="font-size:.82rem;font-weight:600;color:var(--text)">${e.label}${conv}</span>
            <span style="font-size:.88rem;font-weight:700;color:${e.cor}">${e.val.toLocaleString("pt-BR")}</span>
          </div>
          <div style="background:var(--surface-2);border-radius:6px;overflow:hidden;height:10px">
            <div style="width:${pct}%;height:100%;background:${e.cor};border-radius:6px;transition:width .4s"></div>
          </div>
        </div>`;
    }).join("");
  } catch (e) {
    console.error("Funil:", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  carregarDashboard();
  carregarFunilConversao();
});
