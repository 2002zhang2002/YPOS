(function () {
  const data = window.DIAGNOSIS_APP_DATA || {};
  const rawWeeklyRows = data.weeklyStockCompareRows || [];
  const rawDailyRows = data.trendRows || [];
  const comparableStartDate = "2025-01-01";
  const $ = (id) => document.getElementById(id);

  function num(value) {
    return Number(value) || 0;
  }

  function safeDiv(a, b) {
    return Number(b) > 0 ? Number(a) / Number(b) : null;
  }

  function n(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  }

  function pct(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return `${(Number(value) * 100).toFixed(1)}%`;
  }

  function trendTone(value) {
    const diff = Number(value);
    if (!Number.isFinite(diff) || Math.abs(diff) < 0.000001) return "neutral";
    return diff > 0 ? "risk" : "good";
  }

  function saleTone(value) {
    return trendTone(-Number(value));
  }

  function addDays(dateText, days) {
    const date = new Date(`${dateText}T00:00:00`);
    date.setDate(date.getDate() + days);
    return date.toISOString().slice(0, 10);
  }

  function dateDiffDays(start, end) {
    return Math.round((new Date(`${end}T00:00:00`) - new Date(`${start}T00:00:00`)) / 86400000) + 1;
  }

  function sumSaleByRange(start, end) {
    const rows = rawDailyRows.filter((row) => row.biz_date >= start && row.biz_date <= end);
    return {
      rows,
      total: rows.reduce((sum, row) => sum + num(row.sale_qty), 0),
    };
  }

  const allRows = rawWeeklyRows
    .filter((row) => (
      row.biz_date >= comparableStartDate &&
      row.last_year_stock_qty !== null &&
      row.last_year_stock_qty !== undefined
    ))
    .map((row) => {
      const previous = rawWeeklyRows
        .filter((item) => item.biz_date < row.biz_date)
        .sort((a, b) => a.biz_date.localeCompare(b.biz_date))
        .slice(-1)[0] || null;

      const stockWoWDiff = previous ? num(row.stock_qty) - num(previous.stock_qty) : null;
      const stockWoWPct = previous && num(previous.stock_qty) > 0 ? stockWoWDiff / num(previous.stock_qty) : null;
      const avgStock = safeDiv(row.stock_qty, row.customer_count);
      const previousAvgStock = previous ? safeDiv(previous.stock_qty, previous.customer_count) : null;
      const lastYearAvgStock = safeDiv(row.last_year_stock_qty, row.last_year_customer_count);

      const ratioWoWDiff = previous
        ? num(row.stock_sale_ratio_7d_monthly) - num(previous.stock_sale_ratio_7d_monthly)
        : null;

      const saleWoWDiff = previous ? num(row.sale_qty_7d) - num(previous.sale_qty_7d) : null;
      const saleWoWPct = previous && num(previous.sale_qty_7d) > 0 ? saleWoWDiff / num(previous.sale_qty_7d) : null;
      const avgSale7d = safeDiv(row.sale_qty_7d, row.customer_count);
      const previousAvgSale7d = previous ? safeDiv(previous.sale_qty_7d, previous.customer_count) : null;
      const lastYearAvgSale7d = safeDiv(row.last_year_sale_qty_7d, row.last_year_customer_count);

      return {
        ...row,
        previous_week_date: previous?.biz_date || "",
        previous_week_stock_qty: previous ? num(previous.stock_qty) : null,
        previous_week_stock_sale_ratio_7d_monthly: previous ? num(previous.stock_sale_ratio_7d_monthly) : null,
        previous_week_sale_qty_7d: previous ? num(previous.sale_qty_7d) : null,
        stock_wow_diff: stockWoWDiff,
        stock_wow_pct: stockWoWPct,
        avg_stock_per_customer: avgStock,
        previous_avg_stock_per_customer: previousAvgStock,
        last_year_avg_stock_per_customer: lastYearAvgStock,
        avg_stock_wow_diff: avgStock !== null && previousAvgStock !== null ? avgStock - previousAvgStock : null,
        avg_stock_yoy_diff: avgStock !== null && lastYearAvgStock !== null ? avgStock - lastYearAvgStock : null,
        ratio_wow_diff: ratioWoWDiff,
        sale_wow_diff: saleWoWDiff,
        sale_wow_pct: saleWoWPct,
        avg_sale_7d_per_customer: avgSale7d,
        previous_avg_sale_7d_per_customer: previousAvgSale7d,
        last_year_avg_sale_7d_per_customer: lastYearAvgSale7d,
        avg_sale_wow_diff: avgSale7d !== null && previousAvgSale7d !== null ? avgSale7d - previousAvgSale7d : null,
        avg_sale_yoy_diff: avgSale7d !== null && lastYearAvgSale7d !== null ? avgSale7d - lastYearAvgSale7d : null,
      };
    });

  const rangeState = { start: 0, end: Math.max(0, allRows.length - 1) };
  const saleDateBounds = {
    min: rawDailyRows[0]?.biz_date || "",
    max: rawDailyRows[rawDailyRows.length - 1]?.biz_date || "",
  };
  const saleRangeState = { start: "", end: "" };
  let selectedDay = allRows.length ? allRows[allRows.length - 1].biz_date : "";

  const color = {
    current: "#113f35",
    previous: "#aab7ad",
    gold: "#d69a2d",
    sale: "#0f766e",
    grid: "rgba(21, 45, 38, .12)",
  };

  function stockMeaning(value) {
    const tone = trendTone(value);
    if (tone === "risk") return "库存上升，压力增加";
    if (tone === "good") return "库存下降，压力缓解";
    return "库存基本持平";
  }

  function ratioMeaning(value) {
    const tone = trendTone(value);
    if (tone === "risk") return "存销比抬升，周转变慢";
    if (tone === "good") return "存销比下降，周转改善";
    return "存销比基本持平";
  }

  function saleMeaning(value) {
    const tone = saleTone(value);
    if (tone === "good") return "动销上升，需求改善";
    if (tone === "risk") return "动销下降，需求走弱";
    return "动销基本持平";
  }

  function stockCrossInsight(row) {
    const wowUp = Number(row.stock_wow_diff) > 0;
    const yoyUp = Number(row.stock_yoy_diff) > 0;
    const ratioUp = Number(row.ratio_wow_diff) > 0;

    if (wowUp && yoyUp) {
      return {
        tone: "risk",
        title: "持续库存压力",
        summary: `库存环比上升 ${n(row.stock_wow_diff, 1)}（${pct(row.stock_wow_pct)}），同比也上升 ${n(row.stock_yoy_diff, 1)}（${pct(row.stock_yoy_pct)}），更像持续累积，不是单周噪声。`,
        action: ratioUp ? "存销比也在抬升，优先下钻看哪些客户订多或动销变慢。" : "同比仍偏高，建议下钻看库存增量贡献客户。",
      };
    }
    if (wowUp && !yoyUp) {
      return {
        tone: "neutral",
        title: "短期库存抬升",
        summary: `库存环比上升 ${n(row.stock_wow_diff, 1)}（${pct(row.stock_wow_pct)}），但同比未上升，暂时更像本周补货或节奏波动。`,
        action: "先看订购环比和客户贡献，确认是否是集中订货带来的短期抬升。",
      };
    }
    if (!wowUp && yoyUp) {
      return {
        tone: "risk",
        title: "高位开始回落",
        summary: `库存本周环比下降 ${n(Math.abs(row.stock_wow_diff), 1)}（${pct(Math.abs(row.stock_wow_pct))}），但同比仍上升 ${n(row.stock_yoy_diff, 1)}（${pct(row.stock_yoy_pct)}）。`,
        action: "短期有消化迹象，但整体水位仍偏高，继续盯同比高位客户。",
      };
    }
    return {
      tone: "good",
      title: "库存压力缓解",
      summary: "库存环比未上升，同比也未上升，当前库存压力相对缓和。",
      action: ratioUp ? "不过存销比环比抬升，仍要关注销量下滑带来的周转变慢。" : "可以把关注点放到局部客户或品类结构上。",
    };
  }

  function visibleRows() {
    return allRows.slice(rangeState.start, rangeState.end + 1);
  }

  function comparableRows(rows, keys) {
    return rows.filter((row) => keys.every((key) => Number.isFinite(Number(row[key]))));
  }

  function niceNumber(value) {
    const safe = Math.max(Math.abs(value), 1);
    const exponent = Math.floor(Math.log10(safe));
    const fraction = safe / 10 ** exponent;
    let niceFraction = 1;
    if (fraction <= 1) niceFraction = 1;
    else if (fraction <= 2) niceFraction = 2;
    else if (fraction <= 5) niceFraction = 5;
    else niceFraction = 10;
    return niceFraction * 10 ** exponent;
  }

  function niceScale(values) {
    const valid = values.filter((value) => Number.isFinite(Number(value))).map(Number);
    if (!valid.length) return { min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1] };
    const rawMin = Math.min(...valid);
    const rawMax = Math.max(...valid);
    if (rawMin === rawMax) {
      const pad = Math.max(Math.abs(rawMax) * 0.1, 1);
      return { min: rawMin - pad, max: rawMax + pad, ticks: [rawMin - pad, rawMin, rawMax + pad] };
    }
    const span = rawMax - rawMin;
    const step = niceNumber(span / 4);
    const min = Math.floor((rawMin - span * 0.08) / step) * step;
    const max = Math.ceil((rawMax + span * 0.08) / step) * step;
    const ticks = [];
    for (let value = min; value <= max + step * 0.5; value += step) {
      ticks.push(Number(value.toFixed(10)));
    }
    return { min, max, ticks: ticks.slice(0, 7) };
  }

  function linePath(rows, key, x, y) {
    let started = false;
    return rows.map((row, index) => {
      const value = Number(row[key]);
      if (!Number.isFinite(value)) {
        started = false;
        return "";
      }
      const command = started ? "L" : "M";
      started = true;
      return `${command}${x(index).toFixed(2)},${y(value).toFixed(2)}`;
    }).join(" ");
  }

  function drawChart(config) {
    const { svg, tooltip, rows, series, formatter, onPick, pointClass } = config;
    if (!svg || !rows.length) {
      if (svg) svg.innerHTML = "";
      return;
    }

    const [, , widthText, heightText] = svg.getAttribute("viewBox").split(" ");
    const width = Number(widthText) || 1160;
    const height = Number(heightText) || 380;
    const pad = { left: 76, right: 34, top: 34, bottom: 56 };
    const values = rows.flatMap((row) => series.map((item) => Number(row[item.key])).filter(Number.isFinite));
    const scale = niceScale(values);
    const yMin = scale.min;
    const yMax = scale.max === scale.min ? scale.max + 1 : scale.max;
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const x = (index) => pad.left + (index / Math.max(1, rows.length - 1)) * plotWidth;
    const y = (value) => height - pad.bottom - ((value - yMin) / (yMax - yMin || 1)) * plotHeight;

    const axis = scale.ticks.map((value) => {
      const yy = y(value);
      return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" stroke="${color.grid}"/><text x="16" y="${yy + 4}">${n(value, 1)}</text>`;
    }).join("");
    const paths = series.map((item) => `
      <path d="${linePath(rows, item.key, x, y)}" fill="none" stroke="${item.color}" stroke-width="${item.width || 3}" stroke-linecap="round" stroke-linejoin="round"/>
    `).join("");
    const points = rows.map((row, index) => {
      const active = row.biz_date === selectedDay ? " active" : "";
      const extraClass = pointClass ? ` ${pointClass(row)}` : "";
      const current = Number(row[series[0].key]);
      if (!Number.isFinite(current)) return "";
      return `<circle class="chart-point${extraClass}${active}" data-index="${index}" cx="${x(index)}" cy="${y(current)}" r="${active ? 6 : 4}"></circle>`;
    }).join("");

    svg.innerHTML = `
      ${axis}
      ${paths}
      ${points}
      <g id="${svg.id}-hover"></g>
      <text x="${pad.left}" y="${height - 18}">${rows[0].biz_date}</text>
      <text x="${width - 132}" y="${height - 18}">${rows[rows.length - 1].biz_date}</text>
      <rect class="chart-hit" x="${pad.left}" y="${pad.top}" width="${plotWidth}" height="${plotHeight}" fill="transparent"></rect>
    `;

    const hover = svg.querySelector(`#${svg.id}-hover`);
    const hit = svg.querySelector(".chart-hit");

    function nearest(evt) {
      const rect = svg.getBoundingClientRect();
      const rate = (evt.clientX - rect.left) / rect.width;
      const plotRate = Math.min(1, Math.max(0, (rate * width - pad.left) / plotWidth));
      return Math.round(plotRate * (rows.length - 1));
    }

    function show(evt, index) {
      const row = rows[index];
      const xx = x(index);
      hover.innerHTML = `<line x1="${xx}" y1="${pad.top}" x2="${xx}" y2="${height - pad.bottom}" stroke="#113f35" stroke-dasharray="5 5" opacity=".3"/>`;
      tooltip.style.display = "block";
      tooltip.innerHTML = formatter(row);
      const gap = 18;
      const safe = 10;
      const boxWidth = tooltip.offsetWidth || 320;
      const boxHeight = tooltip.offsetHeight || 180;
      const hostWidth = svg.clientWidth || width;
      const hostHeight = svg.clientHeight || height;
      let left = evt.offsetX + gap;
      let top = evt.offsetY + gap;
      if (left + boxWidth + safe > hostWidth) left = evt.offsetX - boxWidth - gap;
      if (top + boxHeight + safe > hostHeight) top = evt.offsetY - boxHeight - gap;
      tooltip.style.left = `${Math.max(safe, left)}px`;
      tooltip.style.top = `${Math.max(safe, top)}px`;
    }

    hit.addEventListener("mousemove", (evt) => show(evt, nearest(evt)));
    hit.addEventListener("mouseleave", () => {
      hover.innerHTML = "";
      tooltip.style.display = "none";
    });
    hit.addEventListener("click", (evt) => {
      const row = rows[nearest(evt)];
      selectedDay = row.biz_date;
      if (onPick) onPick(row);
    });
  }

  function drawTimeline(svgId, key, stroke = "rgba(17,63,53,.45)") {
    const svg = $(svgId);
    if (!svg || !allRows.length) return;
    const [, , widthText, heightText] = svg.getAttribute("viewBox").split(" ");
    const width = Number(widthText) || 1160;
    const height = Number(heightText) || 56;
    const pad = { left: 28, right: 28, top: 9, bottom: 16 };
    const values = allRows.map((row) => Number(row[key])).filter(Number.isFinite);
    if (!values.length) {
      svg.innerHTML = "";
      return;
    }
    const scale = niceScale(values);
    const x = (index) => pad.left + (index / Math.max(1, allRows.length - 1)) * (width - pad.left - pad.right);
    const y = (value) => height - pad.bottom - ((value - scale.min) / (scale.max - scale.min || 1)) * (height - pad.top - pad.bottom);
    const d = allRows.map((row, index) => {
      const value = Number(row[key]);
      if (!Number.isFinite(value)) return "";
      return `${index ? "L" : "M"}${x(index).toFixed(2)},${y(value).toFixed(2)}`;
    }).join(" ");
    const sx = x(rangeState.start);
    const ex = x(rangeState.end);
    svg.innerHTML = `
      <path d="${d}" fill="none" stroke="${stroke}" stroke-width="2"/>
      <rect x="${sx}" y="7" width="${Math.max(3, ex - sx)}" height="${height - 18}" rx="8" fill="rgba(214,154,45,.20)" stroke="rgba(214,154,45,.75)"/>
      <text x="${pad.left}" y="${height - 3}">${allRows[0].biz_date}</text>
      <text x="${width - 124}" y="${height - 3}">${allRows[allRows.length - 1].biz_date}</text>
    `;
  }

  function renderTimelines() {
    drawTimeline("timelineChart", "stock_qty", "rgba(17,63,53,.5)");
    drawTimeline("ratioTimelineChart", "stock_sale_ratio_7d_monthly", "rgba(214,154,45,.58)");
    drawTimeline("saleTimelineChart", "sale_qty_7d", "rgba(15,118,110,.58)");
  }

  function stockTooltip(row) {
    const wowTone = trendTone(row.stock_wow_diff);
    const yoyTone = trendTone(row.stock_yoy_diff);
    const insight = stockCrossInsight(row);
    return `
      <div class="tip-head"><b>${row.biz_date}</b><em class="${insight.tone}">${insight.title}</em></div>
      <div class="tip-grid">
        <span>今年库存</span><strong>${n(row.stock_qty, 1)}</strong>
        <span>上周库存</span><strong>${n(row.previous_week_stock_qty, 1)}</strong>
        <span>去年同期</span><strong>${n(row.last_year_stock_qty, 1)}</strong>
        <span>户均库存</span><strong>${n(row.avg_stock_per_customer, 2)}</strong>
      </div>
      <div class="tip-split">
        <div class="delta-row ${wowTone}"><small>环比</small><b>${n(row.stock_wow_diff, 1)}</b><em>${pct(row.stock_wow_pct)}</em></div>
        <div class="delta-row ${yoyTone}"><small>同比</small><b>${n(row.stock_yoy_diff, 1)}</b><em>${pct(row.stock_yoy_pct)}</em></div>
      </div>
      <p class="tip-insight">${insight.summary}</p>
      <span class="tip-muted">点击进入客户明细</span>
    `;
  }

  function ratioTooltip(row) {
    const wowTone = trendTone(row.ratio_wow_diff);
    const yoyTone = trendTone(row.ratio_yoy_diff);
    return `
      <div class="tip-head"><b>${row.biz_date}</b><em class="${wowTone}">${ratioMeaning(row.ratio_wow_diff)}</em></div>
      <div class="tip-grid">
        <span>今年存销比</span><strong>${n(row.stock_sale_ratio_7d_monthly, 2)}</strong>
        <span>上周存销比</span><strong>${n(row.previous_week_stock_sale_ratio_7d_monthly, 2)}</strong>
        <span>去年同期</span><strong>${n(row.last_year_stock_sale_ratio_7d_monthly, 2)}</strong>
      </div>
      <div class="tip-split">
        <div class="delta-row ${wowTone}"><small>环比差额</small><b>${n(row.ratio_wow_diff, 2)}</b></div>
        <div class="delta-row ${yoyTone}"><small>同比差额</small><b>${n(row.ratio_yoy_diff, 2)}</b></div>
      </div>
      <span class="tip-muted">存销比只看差额，不按百分比解释</span>
    `;
  }

  function saleTooltip(row) {
    const wowTone = saleTone(row.sale_wow_diff);
    const yoyTone = saleTone(row.sale_yoy_diff);
    const avgTone = saleTone(row.avg_sale_wow_diff);
    return `
      <div class="tip-head"><b>${row.biz_date}</b><em class="${wowTone}">${saleMeaning(row.sale_wow_diff)}</em></div>
      <div class="tip-grid">
        <span>本周7天动销</span><strong>${n(row.sale_qty_7d, 1)}</strong>
        <span>上周7天动销</span><strong>${n(row.previous_week_sale_qty_7d, 1)}</strong>
        <span>去年同期</span><strong>${n(row.last_year_sale_qty_7d, 1)}</strong>
        <span>户均条数</span><strong>${n(row.avg_sale_7d_per_customer, 2)}</strong>
      </div>
      <div class="tip-split">
        <div class="delta-row ${wowTone}"><small>环比</small><b>${n(row.sale_wow_diff, 1)}</b><em>${pct(row.sale_wow_pct)}</em></div>
        <div class="delta-row ${yoyTone}"><small>同比</small><b>${n(row.sale_yoy_diff, 1)}</b><em>${pct(row.sale_yoy_pct)}</em></div>
      </div>
      <div class="delta-row ${avgTone}"><small>户均环比变化</small><b>${n(row.avg_sale_wow_diff, 2)}</b></div>
      <span class="tip-muted">动销为 7 天累计，户均条数 = 7天动销 / 客户数</span>
    `;
  }

  function openDetail(row) {
    selectedDay = row.biz_date;
    window.location.href = `inventory_detail.html?date=${encodeURIComponent(row.biz_date)}`;
  }

  function renderCharts() {
    const rows = visibleRows();
    const stockRows = comparableRows(rows, ["stock_qty", "last_year_stock_qty"]);
    const ratioRows = comparableRows(rows, ["stock_sale_ratio_7d_monthly", "last_year_stock_sale_ratio_7d_monthly"]);
    const saleRows = comparableRows(rows, ["sale_qty_7d", "last_year_sale_qty_7d"]);

    drawChart({
      svg: $("stockTrendChart"),
      tooltip: $("stockTooltip"),
      rows: stockRows,
      series: [
        { key: "stock_qty", color: color.current, width: 3.5 },
        { key: "last_year_stock_qty", color: color.previous, width: 3 },
      ],
      formatter: stockTooltip,
      onPick: openDetail,
      pointClass: (row) => `stock-${trendTone(row.stock_wow_diff)}`,
    });

    drawChart({
      svg: $("ratioCompareChart"),
      tooltip: $("ratioTooltip"),
      rows: ratioRows,
      series: [
        { key: "stock_sale_ratio_7d_monthly", color: color.gold, width: 3.5 },
        { key: "last_year_stock_sale_ratio_7d_monthly", color: color.previous, width: 3 },
      ],
      formatter: ratioTooltip,
      onPick: openDetail,
      pointClass: (row) => `stock-${trendTone(row.ratio_wow_diff)}`,
    });

    drawChart({
      svg: $("saleTrendChart"),
      tooltip: $("saleTooltip"),
      rows: saleRows,
      series: [
        { key: "sale_qty_7d", color: color.sale, width: 3.5 },
        { key: "last_year_sale_qty_7d", color: color.previous, width: 3 },
      ],
      formatter: saleTooltip,
      onPick: openDetail,
      pointClass: (row) => `stock-${saleTone(row.sale_wow_diff)}`,
    });

    renderTimelines();
    renderRangeLabel();
    renderSaleRangeCompare();
  }

  function metricSection(title, rows) {
    return `
      <div class="metric-section">
        <div class="metric-section-title">${title}</div>
        <div class="metric-grid">
          ${rows.map((item) => `<span>${item.label}</span><strong class="${item.tone || ""}">${item.value}</strong>`).join("")}
        </div>
      </div>
    `;
  }

  function renderKpis() {
    const latest = allRows[allRows.length - 1] || {};
    const stockWoWTone = trendTone(latest.stock_wow_diff);
    const stockYoYTone = trendTone(latest.stock_yoy_diff);
    const avgStockWoWTone = trendTone(latest.avg_stock_wow_diff);
    const avgStockYoYTone = trendTone(latest.avg_stock_yoy_diff);
    const ratioWoWTone = trendTone(latest.ratio_wow_diff);
    const ratioYoYTone = trendTone(latest.ratio_yoy_diff);
    const saleWoWTone = saleTone(latest.sale_wow_diff);
    const saleYoYTone = saleTone(latest.sale_yoy_diff);
    const avgSaleWoWTone = saleTone(latest.avg_sale_wow_diff);
    const avgSaleYoYTone = saleTone(latest.avg_sale_yoy_diff);

    $("weeklyKpis").innerHTML = `
      <article class="weekly-kpi metric-card tone-${stockWoWTone}">
        <span>库存</span>
        <b>${n(latest.stock_qty, 1)}</b>
        <div class="metric-sections">
          ${metricSection("环比", [
            { label: "上周库存", value: n(latest.previous_week_stock_qty, 1) },
            { label: "环比差值", value: n(latest.stock_wow_diff, 1), tone: stockWoWTone },
            { label: "环比幅度", value: pct(latest.stock_wow_pct), tone: stockWoWTone },
          ])}
          ${metricSection("同比", [
            { label: "去年同期", value: n(latest.last_year_stock_qty, 1) },
            { label: "同比差值", value: n(latest.stock_yoy_diff, 1), tone: stockYoYTone },
            { label: "同比幅度", value: pct(latest.stock_yoy_pct), tone: stockYoYTone },
          ])}
          ${metricSection("户均库存", [
            { label: "本周户均", value: n(latest.avg_stock_per_customer, 2) },
            { label: "户均环比", value: n(latest.avg_stock_wow_diff, 2), tone: avgStockWoWTone },
            { label: "户均同比", value: n(latest.avg_stock_yoy_diff, 2), tone: avgStockYoYTone },
          ])}
        </div>
        <em class="metric-judgement ${stockWoWTone}">${stockMeaning(latest.stock_wow_diff)}</em>
      </article>

      <article class="weekly-kpi metric-card tone-${ratioWoWTone}">
        <span>存销比</span>
        <b>${n(latest.stock_sale_ratio_7d_monthly, 2)}</b>
        <div class="metric-sections two-section">
          ${metricSection("环比", [
            { label: "上周存销比", value: n(latest.previous_week_stock_sale_ratio_7d_monthly, 2) },
            { label: "环比差额", value: n(latest.ratio_wow_diff, 2), tone: ratioWoWTone },
          ])}
          ${metricSection("同比", [
            { label: "去年同期", value: n(latest.last_year_stock_sale_ratio_7d_monthly, 2) },
            { label: "同比差额", value: n(latest.ratio_yoy_diff, 2), tone: ratioYoYTone },
          ])}
        </div>
        <em class="metric-judgement ${ratioWoWTone}">${ratioMeaning(latest.ratio_wow_diff)}</em>
      </article>

      <article class="weekly-kpi metric-card tone-${saleWoWTone}">
        <span>7天动销</span>
        <b>${n(latest.sale_qty_7d, 1)}</b>
        <div class="metric-sections">
          ${metricSection("环比", [
            { label: "上周动销", value: n(latest.previous_week_sale_qty_7d, 1) },
            { label: "环比差值", value: n(latest.sale_wow_diff, 1), tone: saleWoWTone },
            { label: "环比幅度", value: pct(latest.sale_wow_pct), tone: saleWoWTone },
          ])}
          ${metricSection("同比", [
            { label: "去年同期", value: n(latest.last_year_sale_qty_7d, 1) },
            { label: "同比差值", value: n(latest.sale_yoy_diff, 1), tone: saleYoYTone },
            { label: "同比幅度", value: pct(latest.sale_yoy_pct), tone: saleYoYTone },
          ])}
          ${metricSection("户均动销", [
            { label: "本周户均", value: n(latest.avg_sale_7d_per_customer, 2) },
            { label: "户均环比", value: n(latest.avg_sale_wow_diff, 2), tone: avgSaleWoWTone },
            { label: "户均同比", value: n(latest.avg_sale_yoy_diff, 2), tone: avgSaleYoYTone },
          ])}
        </div>
        <em class="metric-judgement ${saleWoWTone}">${saleMeaning(latest.sale_wow_diff)}</em>
      </article>
    `;
  }

  function statusGrid(rows) {
    return `<div class="status-grid">${rows.map((item) => `<span>${item.label}</span><b class="${item.tone || ""}">${item.value}</b>`).join("")}</div>`;
  }

  function renderSaleRangeCompare() {
    const host = $("saleRangeCompare");
    const rows = visibleRows();
    if (!host || !rows.length) return;

    if (!saleRangeState.start || !saleRangeState.end) {
      saleRangeState.start = rows[0].biz_date;
      saleRangeState.end = rows[rows.length - 1].biz_date;
    }

    const start = saleRangeState.start;
    const end = saleRangeState.end;
    const lastYearStart = addDays(start, -364);
    const lastYearEnd = addDays(end, -364);
    const current = sumSaleByRange(start, end);
    const previous = sumSaleByRange(lastYearStart, lastYearEnd);
    const diff = current.total - previous.total;
    const diffPct = previous.total > 0 ? diff / previous.total : null;
    const days = dateDiffDays(start, end);
    const toneClass = saleTone(diff);
    const title = toneClass === "good" ? "区间动销优于去年" : toneClass === "risk" ? "区间动销弱于去年" : "区间动销基本持平";

    host.innerHTML = `
      <div>
        <div class="modal-head">
          <div>
            <p class="eyebrow">Range Sales Compare</p>
            <h3>${title}</h3>
          </div>
          <button class="modal-close" id="saleRangeCompareClose" type="button">×</button>
        </div>
        <p>${start} 至 ${end}，与去年同期 ${lastYearStart} 至 ${lastYearEnd} 对比。口径：二三星终端每日销售，按日销售额累计，不使用 7 天滚动值。</p>
        <div class="range-date-controls">
          <label>开始日期<input id="saleCompareStart" type="date" min="${saleDateBounds.min}" max="${saleDateBounds.max}" value="${start}"></label>
          <label>结束日期<input id="saleCompareEnd" type="date" min="${saleDateBounds.min}" max="${saleDateBounds.max}" value="${end}"></label>
        </div>
      </div>
      <div class="range-compare-grid">
        <span>今年区间累计</span><b>${n(current.total, 1)}</b>
        <span>去年同期累计</span><b>${previous.rows.length ? n(previous.total, 1) : "-"}</b>
        <span>同比差值</span><b class="${toneClass}">${previous.rows.length ? n(diff, 1) : "-"}</b>
        <span>同比幅度</span><b class="${toneClass}">${previous.rows.length ? pct(diffPct) : "-"}</b>
        <span>今年日均</span><b>${n(current.total / Math.max(days, 1), 1)}</b>
        <span>区间天数</span><b>${days}</b>
      </div>
    `;

    const startInput = $("saleCompareStart");
    const endInput = $("saleCompareEnd");
    if (startInput && endInput) {
      startInput.addEventListener("change", () => {
        saleRangeState.start = startInput.value <= saleRangeState.end ? startInput.value : saleRangeState.end;
        renderSaleRangeCompare();
      });
      endInput.addEventListener("change", () => {
        saleRangeState.end = endInput.value >= saleRangeState.start ? endInput.value : saleRangeState.start;
        renderSaleRangeCompare();
      });
    }
    const closeBtn = $("saleRangeCompareClose");
    if (closeBtn) closeBtn.addEventListener("click", closeSaleRangeModal);
  }

  function openSaleRangeModal() {
    const modal = $("saleRangeModal");
    if (!modal) return;
    renderSaleRangeCompare();
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
  }

  function closeSaleRangeModal() {
    const modal = $("saleRangeModal");
    if (!modal) return;
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  }

  function renderStatusCards() {
    const latest = allRows[allRows.length - 1] || {};
    const insight = stockCrossInsight(latest);
    const stockWowTone = trendTone(latest.stock_wow_diff);
    const stockYoyTone = trendTone(latest.stock_yoy_diff);
    const ratioWowTone = trendTone(latest.ratio_wow_diff);
    const ratioYoyTone = trendTone(latest.ratio_yoy_diff);
    const saleWowTone = saleTone(latest.sale_wow_diff);
    const saleYoyTone = saleTone(latest.sale_yoy_diff);

    const stockHost = $("stockStatusCard");
    if (stockHost) {
      stockHost.innerHTML = `
        <p class="eyebrow">Selected Week</p>
        <h2>${latest.biz_date || "-"}</h2>
        <p class="snapshot-insight ${insight.tone}">${insight.title}：${insight.action}</p>
        ${statusGrid([
          { label: "库存", value: n(latest.stock_qty, 1) },
          { label: "上周库存", value: n(latest.previous_week_stock_qty, 1) },
          { label: "库存环比差值", value: n(latest.stock_wow_diff, 1), tone: stockWowTone },
          { label: "库存环比幅度", value: pct(latest.stock_wow_pct), tone: stockWowTone },
          { label: "去年同期", value: n(latest.last_year_stock_qty, 1) },
          { label: "库存同比幅度", value: pct(latest.stock_yoy_pct), tone: stockYoyTone },
        ])}
        <a class="detail-link" href="inventory_detail.html?date=${encodeURIComponent(latest.biz_date || "")}">查看客户明细</a>
      `;
    }

    const ratioHost = $("ratioStatusCard");
    if (ratioHost) {
      ratioHost.innerHTML = `
        <p class="eyebrow">Selected Week</p>
        <h2>${latest.biz_date || "-"}</h2>
        <p class="snapshot-insight ${ratioWowTone}">${ratioMeaning(latest.ratio_wow_diff)}</p>
        ${statusGrid([
          { label: "存销比", value: n(latest.stock_sale_ratio_7d_monthly, 2) },
          { label: "上周存销比", value: n(latest.previous_week_stock_sale_ratio_7d_monthly, 2) },
          { label: "环比差额", value: n(latest.ratio_wow_diff, 2), tone: ratioWowTone },
          { label: "去年同期", value: n(latest.last_year_stock_sale_ratio_7d_monthly, 2) },
          { label: "同比差额", value: n(latest.ratio_yoy_diff, 2), tone: ratioYoyTone },
        ])}
        <a class="detail-link" href="inventory_detail.html?date=${encodeURIComponent(latest.biz_date || "")}">查看客户明细</a>
      `;
    }

    const saleHost = $("saleStatusCard");
    if (saleHost) {
      saleHost.innerHTML = `
        <p class="eyebrow">Selected Week</p>
        <h2>${latest.biz_date || "-"}</h2>
        <p class="snapshot-insight ${saleWowTone}">${saleMeaning(latest.sale_wow_diff)}</p>
        ${statusGrid([
          { label: "7天动销", value: n(latest.sale_qty_7d, 1) },
          { label: "上周动销", value: n(latest.previous_week_sale_qty_7d, 1) },
          { label: "动销环比差值", value: n(latest.sale_wow_diff, 1), tone: saleWowTone },
          { label: "动销环比幅度", value: pct(latest.sale_wow_pct), tone: saleWowTone },
          { label: "去年同期", value: n(latest.last_year_sale_qty_7d, 1) },
          { label: "动销同比幅度", value: pct(latest.sale_yoy_pct), tone: saleYoyTone },
        ])}
        <a class="detail-link" href="inventory_detail.html?date=${encodeURIComponent(latest.biz_date || "")}">查看客户明细</a>
      `;
    }
  }

  function renderRangeLabel() {
    const rows = visibleRows();
    const label = rows.length ? `${rows[0].biz_date} 至 ${rows[rows.length - 1].biz_date}` : "-";
    ["rangeLabel", "ratioRangeLabel", "saleRangeLabel"].forEach((id) => {
      const el = $(id);
      if (el) el.textContent = label;
    });
  }

  const rangeControlPairs = [
    ["rangeStart", "rangeEnd"],
    ["ratioRangeStart", "ratioRangeEnd"],
    ["saleRangeStart", "saleRangeEnd"],
  ];

  function syncRangeControls() {
    rangeControlPairs.forEach(([startId, endId]) => {
      const start = $(startId);
      const end = $(endId);
      if (!start || !end) return;
      [start, end].forEach((input) => {
        input.max = String(allRows.length - 1);
      });
      start.value = String(rangeState.start);
      end.value = String(rangeState.end);
    });
  }

  function initRangeControls() {
    if (!allRows.length) return;
    syncRangeControls();
    rangeControlPairs.forEach(([startId, endId]) => {
      const start = $(startId);
      const end = $(endId);
      if (!start || !end) return;
      start.addEventListener("input", () => {
        rangeState.start = Math.min(Number(start.value), rangeState.end - 1);
        if (startId === "saleRangeStart") saleRangeState.start = allRows[rangeState.start]?.biz_date || saleRangeState.start;
        syncRangeControls();
        renderCharts();
      });
      end.addEventListener("input", () => {
        rangeState.end = Math.max(Number(end.value), rangeState.start + 1);
        if (endId === "saleRangeEnd") saleRangeState.end = allRows[rangeState.end]?.biz_date || saleRangeState.end;
        syncRangeControls();
        renderCharts();
      });
    });
    const openButton = $("saleRangeCompareOpen");
    if (openButton) openButton.addEventListener("click", openSaleRangeModal);
    const modal = $("saleRangeModal");
    if (modal) {
      modal.addEventListener("click", (event) => {
        if (event.target === modal) closeSaleRangeModal();
      });
    }
  }

  if (allRows.length) {
    renderKpis();
    renderStatusCards();
    initRangeControls();
    renderCharts();
  }
})();
