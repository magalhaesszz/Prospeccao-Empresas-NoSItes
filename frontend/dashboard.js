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

document.addEventListener("DOMContentLoaded", carregarDashboard);
