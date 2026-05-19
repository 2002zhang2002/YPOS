(function () {
  const data = window.DIAGNOSIS_APP_DATA || {};
  const weekly = data.weeklyStockCompareRows || [];
  const summary = data.summary || {};

  const $ = (id) => document.getElementById(id);
  const n = (value, digits = 0) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  };
  const pct = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return `${(Number(value) * 100).toFixed(1)}%`;
  };

  function renderMeta() {
    $("generatedAt").textContent = `生成时间：${data.generatedAt || "-"}`;
    $("periodText").textContent = `数据周期：${data.trendStart || "-"} 至 ${data.periodEnd || "-"}`;
  }

  function renderCards() {
    const latest = weekly[weekly.length - 1] || {};
    const cards = [
      ["客户数", n(summary.customerCount), "二星 / 三星客户"],
      ["最新周六", latest.biz_date || "-", "周期快照"],
      ["库存总量", n(latest.stock_qty || summary.stockQty, 1), "周六合计库存"],
      ["库存同比", pct(latest.stock_yoy_pct), "较去年同期"],
      ["月化7天存销比", n(latest.stock_sale_ratio_7d_monthly || summary.ratio7dMonthly, 2), "周六口径"],
      ["30天存销比", n(summary.ratio30d, 2), "最新日口径参考"],
    ];
    $("summaryCards").innerHTML = cards.map(([label, value, hint]) => `
      <article class="card cockpit-card">
        <span>${label}</span>
        <b>${value}</b>
        <em>${hint}</em>
      </article>
    `).join("");
  }

  function drawLineChart(svg, sourceRows) {
    if (!svg || !sourceRows.length) return;
    const width = 1100;
    const height = 360;
    const pad = { left: 62, right: 28, top: 30, bottom: 44 };
    const series = [
      { key: "stock_qty", color: "#113f35", width: 3.5 },
      { key: "last_year_stock_qty", color: "#aab7ad", width: 3 },
    ];
    const values = sourceRows.flatMap((row) => series.map((item) => Number(row[item.key])).filter(Number.isFinite));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const yMin = Math.min(0, min);
    const yMax = max === yMin ? max + 1 : max;
    const x = (index) => pad.left + (index / Math.max(1, sourceRows.length - 1)) * (width - pad.left - pad.right);
    const y = (value) => height - pad.bottom - ((value - yMin) / (yMax - yMin || 1)) * (height - pad.top - pad.bottom);
    const path = (key) => sourceRows.map((row, index) => {
      const value = Number(row[key]);
      return Number.isFinite(value) ? `${index ? "L" : "M"}${x(index).toFixed(2)},${y(value).toFixed(2)}` : "";
    }).join(" ");
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((rate) => {
      const value = yMin + (yMax - yMin) * rate;
      const yy = y(value);
      return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" stroke="rgba(21,45,38,.12)"/><text x="12" y="${yy + 4}">${n(value)}</text>`;
    }).join("");
    svg.innerHTML = `
      ${ticks}
      ${series.map((item) => `<path d="${path(item.key)}" fill="none" stroke="${item.color}" stroke-width="${item.width}" stroke-linecap="round"/>`).join("")}
      <text x="${pad.left}" y="${height - 14}">${sourceRows[0].biz_date}</text>
      <text x="${width - 118}" y="${height - 14}">${sourceRows[sourceRows.length - 1].biz_date}</text>
    `;
  }

  function renderWeeklyTable() {
    const latest = weekly.slice(-12).reverse();
    $("weeklyTable").innerHTML = latest.map((row) => `
      <tr>
        <td>${row.biz_date || "-"}</td>
        <td>${n(row.stock_qty, 1)}</td>
        <td>${n(row.last_year_stock_qty, 1)}</td>
        <td>${n(row.stock_yoy_diff, 1)}</td>
        <td>${pct(row.stock_yoy_pct)}</td>
        <td>${n(row.stock_sale_ratio_7d_monthly, 2)}</td>
        <td>${n(row.last_year_stock_sale_ratio_7d_monthly, 2)}</td>
      </tr>
    `).join("");
  }

  renderMeta();
  renderCards();
  drawLineChart($("dashboardStockChart"), weekly);
  renderWeeklyTable();
})();
