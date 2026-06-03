/* Accounting system – shared front-end behaviour (vanilla JS + HTMX + Chart.js) */
(function () {
  "use strict";

  // --- CSRF for HTMX requests ---------------------------------------------
  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }
  document.body.addEventListener("htmx:configRequest", function (evt) {
    evt.detail.headers["X-CSRFToken"] = getCsrfToken();
  });

  // --- Money formatting ----------------------------------------------------
  const RUB = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  window.formatMoney = function (value) {
    return RUB.format(Number(value) || 0);
  };

  // --- Chart registry (destroy before redraw to avoid leaks) ---------------
  const charts = {};
  function draw(id, config) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(canvas.getContext("2d"), config);
  }

  const PALETTE = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
                   "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#14b8a6"];
  const moneyTick = { callbacks: { label: (c) => " " + window.formatMoney(c.parsed.y ?? c.parsed) } };

  // --- Dashboard charts ----------------------------------------------------
  window.initDashboardCharts = function (data) {
    if (!data) return;
    const rev = data.revenue_expense_week || { labels: [], income: [], expense: [] };
    draw("chartRevenueExpense", {
      type: "bar",
      data: {
        labels: rev.labels,
        datasets: [
          { label: "Доходы", data: rev.income, backgroundColor: "#10b981", borderRadius: 6 },
          { label: "Расходы", data: rev.expense, backgroundColor: "#ef4444", borderRadius: 6 },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { tooltip: moneyTick }, scales: { y: { beginAtZero: true } } },
    });

    const trend = data.profit_trend || { labels: [], profit: [] };
    draw("chartProfitTrend", {
      type: "line",
      data: { labels: trend.labels, datasets: [{
        label: "Прибыль", data: trend.profit, borderColor: "#6366f1",
        backgroundColor: "rgba(99,102,241,.12)", fill: true, tension: .35, pointRadius: 3 }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { tooltip: moneyTick }, scales: { y: { beginAtZero: true } } },
    });

    const top = data.top_expenses || { labels: [], data: [], colors: [] };
    draw("chartTopExpenses", {
      type: "doughnut",
      data: { labels: top.labels, datasets: [{
        data: top.data, backgroundColor: top.colors.length ? top.colors : PALETTE }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%",
        plugins: { legend: { position: "bottom" } } },
    });
  };

  // --- Reports charts ------------------------------------------------------
  window.initReportCharts = function (data) {
    if (!data) return;
    const inc = data.revenue_by_category || { labels: [], data: [], colors: [] };
    draw("chartRevenueByCategory", {
      type: "bar",
      data: { labels: inc.labels, datasets: [{
        label: "Выручка", data: inc.data,
        backgroundColor: inc.colors.length ? inc.colors : PALETTE, borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: "y",
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          label: (c) => " " + window.formatMoney(c.parsed.x) } } } },
    });

    const exp = data.expense_breakdown || { labels: [], data: [], colors: [] };
    draw("chartExpenseBreakdown", {
      type: "doughnut",
      data: { labels: exp.labels, datasets: [{
        data: exp.data, backgroundColor: exp.colors.length ? exp.colors : PALETTE }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%",
        plugins: { legend: { position: "bottom" } } },
    });

    const cf = data.cash_flow || { labels: [], income: [], expense: [] };
    draw("chartCashFlow", {
      type: "bar",
      data: { labels: cf.labels, datasets: [
        { label: "Поступления", data: cf.income, backgroundColor: "#10b981", borderRadius: 6 },
        { label: "Списания", data: cf.expense, backgroundColor: "#ef4444", borderRadius: 6 } ] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { tooltip: moneyTick }, scales: { y: { beginAtZero: true } } },
    });
  };

  // --- Invoice line-item live totals (event delegation) --------------------
  function recalcInvoice() {
    const rows = document.querySelectorAll("#invoice-items .invoice-row");
    let subtotal = 0;
    rows.forEach(function (row) {
      if (row.querySelector("input[type=checkbox][name$='-DELETE']:checked")) return;
      const qty = parseFloat((row.querySelector(".js-qty") || {}).value) || 0;
      const price = parseFloat((row.querySelector(".js-unit-price") || {}).value) || 0;
      const amount = qty * price;
      const cell = row.querySelector(".js-amount");
      if (cell) cell.textContent = window.formatMoney(amount);
      subtotal += amount;
    });
    const rate = parseFloat((document.getElementById("id_tax_rate") || {}).value) || 0;
    const tax = subtotal * rate / 100;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = window.formatMoney(val); };
    set("inv-subtotal", subtotal);
    set("inv-tax", tax);
    set("inv-total", subtotal + tax);
  }
  window.recalcInvoice = recalcInvoice;

  document.addEventListener("input", function (e) {
    if (e.target.closest && e.target.closest("#invoice-items")) recalcInvoice();
    if (e.target.id === "id_tax_rate") recalcInvoice();
  });
  document.addEventListener("change", function (e) {
    if (e.target.name && e.target.name.endsWith("-DELETE")) {
      const row = e.target.closest(".invoice-row");
      if (row) row.classList.toggle("opacity-40", e.target.checked);
      recalcInvoice();
    }
  });

  // Remove a line-item row: existing rows are flagged DELETE, new rows removed.
  document.addEventListener("click", function (e) {
    const btn = e.target.closest && e.target.closest(".js-remove-row");
    if (!btn) return;
    const row = btn.closest(".invoice-row");
    if (!row) return;
    const idField = row.querySelector("input[name$='-id']");
    const del = row.querySelector("input[type=checkbox][name$='-DELETE']");
    if (idField && idField.value && del) {
      del.checked = true;
      row.classList.add("hidden");
    } else {
      row.remove();
      const totalInput = document.getElementById("id_items-TOTAL_FORMS");
      if (totalInput) {
        totalInput.value = document.querySelectorAll("#invoice-items .invoice-row").length;
      }
    }
    recalcInvoice();
  });

  // Re-run totals after HTMX inserts a new line-item row.
  document.body.addEventListener("htmx:afterSwap", function () { recalcInvoice(); });
  document.addEventListener("DOMContentLoaded", recalcInvoice);
})();
