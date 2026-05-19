(function () {
  const data = window.DIAGNOSIS_APP_DATA || {};
  const params = new URLSearchParams(window.location.search);
  const day = params.get("date") || (data.weeklyStockCompareRows || []).slice(-1)[0]?.biz_date || "";
  const initialShop = params.get("shop") || "";
  const state = {
    rows: [],
    selectedShopId: initialShop,
    trendCache: new Map(),
    nearbySameLevel: false,
    nearbySameMarket: false,
    nearbyRadiusKm: 3,
    nearbyMap: null,
    nearbyLayer: null,
    customerGeoMap: new Map(),
    profileFocus: "trend",
    currentTrendRows: [],
  };

  const $ = (id) => document.getElementById(id);

  function num(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function finite(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function n(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  }

  function safeText(value) {
    return String(value ?? "-")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function shopKey(row) {
    return String(row?.shop_id || row?.cust_id || "");
  }

  function buildCustomerGeoMap() {
    state.customerGeoMap = new Map();
    (data.customerRows || []).forEach((row) => {
      const key = shopKey(row);
      if (key) state.customerGeoMap.set(key, row);
    });
    (data.abnormalRows || []).forEach((row) => {
      const key = shopKey(row);
      if (key && !state.customerGeoMap.has(key)) state.customerGeoMap.set(key, row);
    });
  }

  function mergeCustomerGeo(row) {
    const geo = state.customerGeoMap.get(shopKey(row));
    return geo ? { ...geo, ...row, latitude: geo.latitude, longitude: geo.longitude } : row;
  }

  function hasLocation(row) {
    return Number.isFinite(Number(row?.latitude)) && Number.isFinite(Number(row?.longitude));
  }

  function distanceKm(a, b) {
    if (!hasLocation(a) || !hasLocation(b)) return Infinity;
    const earthRadiusKm = 6371;
    const lat1 = Number(a.latitude) * Math.PI / 180;
    const lat2 = Number(b.latitude) * Math.PI / 180;
    const dLat = (Number(b.latitude) - Number(a.latitude)) * Math.PI / 180;
    const dLng = (Number(b.longitude) - Number(a.longitude)) * Math.PI / 180;
    const h = Math.sin(dLat / 2) ** 2
      + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
    return 2 * earthRadiusKm * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  function rowsForDay(targetDay) {
    const src = data.dayDetailIndex && data.dayDetailIndex[targetDay];
    if (!src) return [];
    if (window.INVENTORY_DAY_DETAILS && window.INVENTORY_DAY_DETAILS[targetDay]) {
      return window.INVENTORY_DAY_DETAILS[targetDay];
    }
    return [];
  }

  function loadDay(targetDay, callback) {
    const ready = rowsForDay(targetDay);
    if (ready.length || !targetDay) {
      callback(ready);
      return;
    }
    const src = data.dayDetailIndex && data.dayDetailIndex[targetDay];
    if (!src) {
      callback([]);
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => callback(rowsForDay(targetDay));
    script.onerror = () => callback([]);
    document.body.appendChild(script);
  }

  function trendScriptPath(shopId) {
    return (data.customerTrendIndex && data.customerTrendIndex[shopId])
      || `data/customer_trends/${encodeURIComponent(shopId)}.js`;
  }

  function readLoadedTrend(shopId) {
    if (window.CUSTOMER_TREND_DATA && String(window.CUSTOMER_TREND_DATA.shopId) === String(shopId)) {
      return window.CUSTOMER_TREND_DATA.rows || [];
    }
    if (window.INVENTORY_CUSTOMER_TRENDS && window.INVENTORY_CUSTOMER_TRENDS[shopId]) {
      return window.INVENTORY_CUSTOMER_TRENDS[shopId];
    }
    return [];
  }

  function loadCustomerTrend(shopId, callback) {
    if (!shopId) {
      callback([]);
      return;
    }
    if (state.trendCache.has(shopId)) {
      callback(state.trendCache.get(shopId));
      return;
    }
    const path = trendScriptPath(shopId);
    if (!path) {
      callback([]);
      return;
    }
    if (window.CUSTOMER_TREND_DATA && String(window.CUSTOMER_TREND_DATA.shopId) !== String(shopId)) {
      window.CUSTOMER_TREND_DATA = null;
    }
    let settled = false;
    const finish = (rows) => {
      if (settled) return;
      settled = true;
      const safeRows = Array.isArray(rows) ? rows : [];
      state.trendCache.set(shopId, safeRows);
      callback(safeRows);
    };
    const script = document.createElement("script");
    script.src = path;
    script.onload = () => {
      const rows = readLoadedTrend(shopId);
      finish(rows);
    };
    script.onerror = () => finish([]);
    document.body.appendChild(script);
    window.setTimeout(() => {
      finish(readLoadedTrend(shopId));
    }, 2500);
  }

  function daySerial(dateText) {
    const parts = String(dateText || "").split("-").map(Number);
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return null;
    return Math.floor(Date.UTC(parts[0], parts[1] - 1, parts[2]) / 86400000);
  }

  function weeklyTrendRows(trendRows) {
    const rows = trendRows
      .filter((row) => row.biz_date >= "2025-01-01" && row.biz_date <= (day || "9999-99-99"))
      .slice()
      .sort((a, b) => String(a.biz_date).localeCompare(String(b.biz_date)));
    if (!rows.length) return trendRows.slice().sort((a, b) => String(a.biz_date).localeCompare(String(b.biz_date)));
    const anchor = rows.find((row) => row.biz_date === day) || rows[rows.length - 1];
    const anchorSerial = daySerial(anchor.biz_date);
    if (anchorSerial === null) return rows;
    const weekly = rows.filter((row) => {
      const serial = daySerial(row.biz_date);
      return serial !== null && (anchorSerial - serial) % 7 === 0;
    });
    return weekly.length >= 2 ? weekly : rows.filter((_, index) => index % 7 === rows.length % 7);
  }

  function latestRows(trendRows) {
    const rows = weeklyTrendRows(trendRows);
    const currentIndex = rows.findIndex((row) => row.biz_date === day);
    if (currentIndex >= 0) {
      const current = rows[currentIndex];
      const prev = rows[Math.max(0, currentIndex - 1)] || null;
      return { current, prev };
    }
    return {
      current: rows[rows.length - 1] || null,
      prev: rows[rows.length - 2] || null,
    };
  }

  function deltaTone(diff, mode = "stock") {
    if (!Number.isFinite(diff) || Math.abs(diff) < 1e-9) return "neutral";
    if (mode === "sale") return diff > 0 ? "good" : "risk";
    return diff > 0 ? "risk" : "good";
  }

  function renderTrendStats(trendRows) {
    const host = $("customerTrendStats");
    const { current, prev } = latestRows(trendRows);
    if (!current) {
      host.innerHTML = "";
      return;
    }
    const stockDiff = prev ? num(current.stock_qty) - num(prev.stock_qty) : null;
    const ratioDiff = prev ? num(current.stock_sale_ratio_7d_monthly) - num(prev.stock_sale_ratio_7d_monthly) : null;
    const saleDiff = prev ? num(current.sale_qty_7d) - num(prev.sale_qty_7d) : null;
    const cards = [
      ["库存", n(current.stock_qty, 1), stockDiff === null ? "无上周期" : `较上周期 ${stockDiff > 0 ? "+" : ""}${n(stockDiff, 1)}`, deltaTone(stockDiff, "stock")],
      ["存销比", n(current.stock_sale_ratio_7d_monthly, 2), ratioDiff === null ? "无上周期" : `差额 ${ratioDiff > 0 ? "+" : ""}${n(ratioDiff, 2)}`, deltaTone(ratioDiff, "stock")],
      ["7天动销", n(current.sale_qty_7d, 1), saleDiff === null ? "无上周期" : `较上周期 ${saleDiff > 0 ? "+" : ""}${n(saleDiff, 1)}`, deltaTone(saleDiff, "sale")],
    ];
    host.innerHTML = cards.map(([label, value, hint, tone]) => `
      <div class="customer-stat ${tone}">
        <span>${label}</span>
        <b>${value}</b>
        <em>${hint}</em>
      </div>
    `).join("");
  }

  function renderLoadingCharts(message) {
    ["customerStockChart", "customerRatioChart", "customerSaleChart"].forEach((id) => {
      const svg = $(id);
      if (!svg) return;
      svg.setAttribute("viewBox", "0 0 520 220");
      svg.innerHTML = `<text x="260" y="112" text-anchor="middle" class="empty-chart-text">${safeText(message)}</text>`;
    });
  }

  function setTrendCaptions() {
    const captions = ["7天周期库存快照", "7天周期月化口径", "7天周期累计"];
    document.querySelectorAll(".customer-mini-card").forEach((card, index) => {
      const caption = card.querySelector(".mini-card-head span");
      if (caption && captions[index]) caption.textContent = captions[index];
    });
  }

  function niceDomain(values) {
    const valid = values.map(finite).filter((value) => value !== null);
    if (!valid.length) return { min: 0, max: 1 };
    let min = Math.min(...valid);
    let max = Math.max(...valid);
    if (min === max) {
      const pad = Math.max(1, Math.abs(max) * 0.1);
      min -= pad;
      max += pad;
    }
    const span = max - min;
    const pad = span * 0.12;
    min = Math.max(0, min - pad);
    max += pad;
    return { min, max };
  }

  function niceStep(rawStep) {
    if (!Number.isFinite(rawStep) || rawStep <= 0) return 1;
    const base = 10 ** Math.floor(Math.log10(rawStep));
    const multiples = [1, 2, 2.5, 5, 10];
    const picked = multiples.find((multiple) => rawStep <= multiple * base) || 10;
    return picked * base;
  }

  function readableScale(values, tickCount = 6) {
    const valid = values.map(finite).filter((value) => value !== null);
    if (!valid.length) return { min: 0, max: 1, ticks: [0, 1] };
    let min = Math.min(...valid);
    let max = Math.max(...valid);
    if (min === max) {
      const pad = Math.max(1, Math.abs(max) * 0.08);
      min -= pad;
      max += pad;
    }
    const step = niceStep((max - min) / Math.max(1, tickCount - 1));
    let axisMin = Math.floor(min / step) * step;
    let axisMax = Math.ceil(max / step) * step;
    if (axisMin > 0 && axisMin < step) axisMin = 0;
    if (axisMin === axisMax) axisMax = axisMin + step;
    const ticks = [];
    for (let value = axisMin; value <= axisMax + step * 0.5; value += step) {
      ticks.push(Math.abs(value) < 1e-9 ? 0 : value);
    }
    return { min: axisMin, max: axisMax, ticks };
  }

  function peerAverageForCurrentCustomer(key) {
    const current = state.rows.find((item) => shopKey(item) === state.selectedShopId);
    if (!current) return null;
    const level = String(current.cust_seg_name || "");
    const market = String(current.market_type || current.work_port_name || "");
    if (!level || !market) return null;
    const peers = state.rows
      .filter((row) => String(row.cust_seg_name || "") === level)
      .filter((row) => String(row.market_type || row.work_port_name || "") === market)
      .map((row) => finite(row[key]))
      .filter((value) => value !== null);
    if (!peers.length) return null;
    return {
      value: peers.reduce((sum, value) => sum + value, 0) / peers.length,
      count: peers.length,
      level,
      market,
    };
  }

  function drawMiniTrend(svgId, tipId, trendRows, config) {
    const svg = $(svgId);
    const tip = $(tipId);
    if (!svg) return;
    const plotRows = weeklyTrendRows(trendRows);
    const box = svg.parentElement?.getBoundingClientRect();
    const width = Math.max(420, Math.round(box?.width || 640));
    const height = Math.max(190, Math.round(box?.height || 248));
    const pad = { left: 44, right: 12, top: 10, bottom: 28 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const peerAverage = peerAverageForCurrentCustomer(config.key);
    const scaleValues = plotRows.map((row) => row[config.key]);
    if (peerAverage) scaleValues.push(peerAverage.value);
    const domain = readableScale(scaleValues, 7);
    const x = (index) => pad.left + (plotRows.length <= 1 ? innerW / 2 : index / (plotRows.length - 1) * innerW);
    const y = (value) => pad.top + (domain.max - value) / (domain.max - domain.min || 1) * innerH;
    const points = plotRows
      .map((row, index) => ({ row, value: finite(row[config.key]), x: x(index) }))
      .filter((point) => point.value !== null)
      .map((point) => ({ ...point, y: y(point.value) }));

    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    if (!points.length) {
      svg.innerHTML = `<text x="260" y="112" text-anchor="middle" class="empty-chart-text">鏆傛棤瓒嬪娍鏁版嵁</text>`;
      return;
    }

    const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    const area = `${pad.left},${pad.top + innerH} ${line} ${pad.left + innerW},${pad.top + innerH}`;
    const tickValues = domain.ticks;
    const selectedIndex = plotRows.findIndex((row) => row.biz_date === day);
    const selectedX = selectedIndex >= 0 ? x(selectedIndex) : null;
    const selectedPoint = selectedX === null ? null : points.find((point) => point.row.biz_date === day);
    const firstDate = plotRows[0]?.biz_date || "";
    const lastDate = plotRows[plotRows.length - 1]?.biz_date || "";
    const peerY = peerAverage ? y(peerAverage.value) : null;
    const peerLabel = peerAverage
      ? `${innerW < 470 ? "均值" : "同档同市场均值"} ${n(peerAverage.value, config.digits)}`
      : "";
    const peerLabelWidth = Math.min(innerW - 18, Math.max(74, peerLabel.length * 11));
    const selectedNearRight = selectedX !== null && selectedX > pad.left + innerW * 0.62;
    const peerLabelX = peerAverage
      ? (selectedNearRight ? pad.left + 8 : pad.left + innerW - peerLabelWidth - 8)
      : 0;
    const peerLabelY = peerY === null ? 0 : Math.min(pad.top + innerH - 24, Math.max(pad.top + 10, peerY - 24));
    const peerTextAnchor = selectedNearRight ? "start" : "end";
    const peerTextX = selectedNearRight ? peerLabelX + 8 : peerLabelX + peerLabelWidth - 8;

    svg.innerHTML = `
      <defs>
        <linearGradient id="${svgId}Fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="${config.color}" stop-opacity=".22"></stop>
          <stop offset="100%" stop-color="${config.color}" stop-opacity=".02"></stop>
        </linearGradient>
      </defs>
      <rect x="${pad.left}" y="${pad.top}" width="${innerW}" height="${innerH}" rx="14" class="mini-chart-bg"></rect>
      ${tickValues.map((value) => {
        const ty = y(value);
        return `<line x1="${pad.left}" x2="${pad.left + innerW}" y1="${ty}" y2="${ty}" class="mini-grid"></line>
          <text x="${pad.left - 8}" y="${ty + 4}" text-anchor="end" class="mini-axis-label">${n(value, config.digits)}</text>`;
      }).join("")}
      ${peerY === null ? "" : `
        <line x1="${pad.left}" x2="${pad.left + innerW}" y1="${peerY}" y2="${peerY}" class="mini-peer-line"></line>
        <rect x="${peerLabelX}" y="${peerLabelY}" width="${peerLabelWidth}" height="20" rx="10" class="mini-peer-label-bg"></rect>
        <text x="${peerTextX}" y="${peerLabelY + 14}" text-anchor="${peerTextAnchor}" class="mini-peer-label">${safeText(peerLabel)}</text>
      `}
      <polygon points="${area}" fill="url(#${svgId}Fill)"></polygon>
      <polyline points="${line}" fill="none" stroke="${config.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      ${selectedX === null ? "" : `<line x1="${selectedX}" x2="${selectedX}" y1="${pad.top}" y2="${pad.top + innerH}" class="selected-week-line"></line>`}
      ${selectedPoint ? `<circle cx="${selectedPoint.x}" cy="${selectedPoint.y}" r="5" class="selected-week-dot"></circle>` : ""}
      ${points.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="8" fill="transparent" class="hover-capture" data-date="${safeText(point.row.biz_date)}" data-value="${safeText(point.value)}"></circle>`).join("")}
      <text x="${pad.left}" y="${height - 10}" class="mini-axis-label">${safeText(firstDate)}</text>
      <text x="${pad.left + innerW}" y="${height - 10}" text-anchor="end" class="mini-axis-label">${safeText(lastDate)}</text>
    `;

    if (!tip) return;
    svg.querySelectorAll(".hover-capture").forEach((dot) => {
      dot.addEventListener("mousemove", (event) => {
        const rect = svg.getBoundingClientRect();
        const value = Number(dot.dataset.value);
        tip.innerHTML = `
          <div class="tip-head">
            <b>${safeText(dot.dataset.date || "")}</b>
            <em>${safeText(config.label)} ${n(value, config.digits)}</em>
          </div>
          ${peerAverage ? `<div class="tip-grid single"><span>同档同市场均值</span><b>${n(peerAverage.value, config.digits)}</b></div>` : ""}
        `;
        tip.style.display = "block";
        tip.style.left = `${Math.min(rect.width - 260, Math.max(8, event.offsetX + 12))}px`;
        tip.style.top = `${Math.max(8, event.offsetY - 44)}px`;
      });
      dot.addEventListener("mouseleave", () => {
        tip.style.display = "none";
      });
    });
  }

  function redrawCustomerTrends() {
    if (!state.currentTrendRows.length) return;
    drawMiniTrend("customerStockChart", "customerStockTip", state.currentTrendRows, {
      key: "stock_qty",
      label: "库存",
      color: "#0f766e",
      digits: 1,
    });
    drawMiniTrend("customerRatioChart", "customerRatioTip", state.currentTrendRows, {
      key: "stock_sale_ratio_7d_monthly",
      label: "存销比",
      color: "#d69a2d",
      digits: 2,
    });
    drawMiniTrend("customerSaleChart", "customerSaleTip", state.currentTrendRows, {
      key: "sale_qty_7d",
      label: "7天动销",
      color: "#2563eb",
      digits: 1,
    });
  }

  function drawDiagnosticTrend(svgId, tipId, trendRows, config) {
    const svg = $(svgId);
    const tip = $(tipId);
    if (!svg) return;
    if (svgId === "customerStockChart" || svgId === "customerRatioChart") config.pressureUp = true;
    if (svgId === "customerSaleChart") {
      config.mode = "bar";
      config.pressureUp = false;
    }
    const plotRows = weeklyTrendRows(trendRows);
    const width = 520;
    const height = 238;
    const pad = { left: 48, right: 22, top: 28, bottom: 42 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const domain = niceDomain(plotRows.map((row) => row[config.key]));
    const x = (index) => pad.left + (plotRows.length <= 1 ? innerW / 2 : index / (plotRows.length - 1) * innerW);
    const y = (value) => pad.top + (domain.max - value) / (domain.max - domain.min || 1) * innerH;
    const points = plotRows
      .map((row, index) => ({ row, value: finite(row[config.key]), x: x(index) }))
      .filter((point) => point.value !== null)
      .map((point) => ({ ...point, y: y(point.value) }));

    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    if (!points.length) {
      svg.innerHTML = `<text x="260" y="118" text-anchor="middle" class="empty-chart-text">鏆傛棤瓒嬪娍鏁版嵁</text>`;
      return;
    }

    const pointByDate = new Map(points.map((point) => [point.row.biz_date, point]));
    const indexed = plotRows
      .map((row, index) => {
        const value = finite(row[config.key]);
        const prev = index > 0 ? finite(plotRows[index - 1][config.key]) : null;
        return {
          row,
          value,
          diff: value !== null && prev !== null ? value - prev : null,
          point: pointByDate.get(row.biz_date),
        };
      })
      .filter((item) => item.value !== null && item.point);
    const maxAbsDiff = Math.max(1, ...indexed.map((item) => Math.abs(item.diff || 0)));
    const deltaBase = pad.top + innerH + 16;
    const deltaMaxH = 20;
    const barW = Math.max(3, Math.min(11, innerW / Math.max(1, plotRows.length) * 0.46));
    const isBarChart = config.mode === "bar";
    const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
    const area = `${pad.left},${pad.top + innerH} ${line} ${pad.left + innerW},${pad.top + innerH}`;
    const tickValues = domain.ticks;
    const selectedIndex = plotRows.findIndex((row) => row.biz_date === day);
    const selectedX = selectedIndex >= 0 ? x(selectedIndex) : null;
    const selectedPoint = selectedX === null ? null : points.find((point) => point.row.biz_date === day);
    const firstDate = plotRows[0]?.biz_date || "";
    const lastDate = plotRows[plotRows.length - 1]?.biz_date || "";

    svg.innerHTML = `
      <defs>
        <linearGradient id="${svgId}DiagnosticFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="${config.color}" stop-opacity=".2"></stop>
          <stop offset="100%" stop-color="${config.color}" stop-opacity=".02"></stop>
        </linearGradient>
      </defs>
      <rect x="${pad.left}" y="${pad.top}" width="${innerW}" height="${innerH}" rx="14" class="mini-chart-bg"></rect>
      ${tickValues.map((value) => {
        const ty = y(value);
        return `<line x1="${pad.left}" x2="${pad.left + innerW}" y1="${ty}" y2="${ty}" class="mini-grid"></line>
          <text x="${pad.left - 8}" y="${ty + 4}" text-anchor="end" class="mini-axis-label">${n(value, config.digits)}</text>`;
      }).join("")}
      ${isBarChart ? "" : `<polygon points="${area}" fill="url(#${svgId}DiagnosticFill)"></polygon>`}
      ${isBarChart ? points.map((point) => {
        const barH = Math.max(2, pad.top + innerH - point.y);
        return `<rect x="${(point.x - barW / 2).toFixed(1)}" y="${point.y.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" rx="3" fill="${config.color}" opacity=".58"></rect>`;
      }).join("") : `<polyline points="${line}" fill="none" stroke="${config.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>`}
      <line x1="${pad.left}" x2="${pad.left + innerW}" y1="${deltaBase}" y2="${deltaBase}" class="mini-delta-base"></line>
      ${indexed.map((item) => {
        if (item.diff === null) return "";
        const h = Math.max(2, Math.min(deltaMaxH, Math.abs(item.diff) / maxAbsDiff * deltaMaxH));
        const rising = item.diff >= 0;
        const pressure = config.pressureUp ? rising : !rising;
        const y1 = rising ? deltaBase - h : deltaBase;
        return `<rect x="${(item.point.x - barW / 2).toFixed(1)}" y="${y1.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2" class="${pressure ? "mini-delta-risk" : "mini-delta-good"}"></rect>`;
      }).join("")}
      ${selectedX === null ? "" : `<line x1="${selectedX}" x2="${selectedX}" y1="${pad.top}" y2="${pad.top + innerH}" class="selected-week-line"></line>`}
      ${minItem && minItem.point ? `<circle cx="${minItem.point.x}" cy="${minItem.point.y}" r="4" class="mini-extreme-dot low"></circle>` : ""}
      ${maxItem && maxItem.point ? `<circle cx="${maxItem.point.x}" cy="${maxItem.point.y}" r="4" class="mini-extreme-dot high"></circle>` : ""}
      ${selectedPoint ? `<circle cx="${selectedPoint.x}" cy="${selectedPoint.y}" r="6" class="selected-week-dot"></circle>` : ""}
      ${latestItem ? `<text x="${Math.min(pad.left + innerW - 4, latestItem.point.x + 8)}" y="${Math.max(pad.top + 12, latestItem.point.y - 8)}" class="mini-latest-label">${n(latestItem.value, config.digits)}</text>` : ""}
      ${maxJumpItem ? `<text x="${pad.left}" y="18" class="mini-jump-label">鏈€澶у懆鍙?${maxJumpItem.diff > 0 ? "+" : ""}${n(maxJumpItem.diff, config.digits)}</text>` : ""}
      ${points.map((point) => `<circle cx="${point.x}" cy="${point.y}" r="8" fill="transparent" class="hover-capture" data-date="${safeText(point.row.biz_date)}" data-value="${safeText(point.value)}"></circle>`).join("")}
      <text x="${pad.left}" y="${height - 10}" class="mini-axis-label">${safeText(firstDate)}</text>
      <text x="${pad.left + innerW}" y="${height - 10}" text-anchor="end" class="mini-axis-label">${safeText(lastDate)}</text>
    `;

    if (!tip) return;
    svg.querySelectorAll(".hover-capture").forEach((dot) => {
      dot.addEventListener("mousemove", (event) => {
        const rect = svg.getBoundingClientRect();
        const value = Number(dot.dataset.value);
        const item = indexed.find((entry) => entry.row.biz_date === dot.dataset.date);
        tip.innerHTML = `
          <div class="tip-head">
            <b>${safeText(dot.dataset.date || "")}</b>
            <em>${safeText(config.label)} ${n(value, config.digits)}</em>
          </div>
          <div class="tip-grid single"><span>较上周期</span><b>${item?.diff === null || item?.diff === undefined ? "-" : `${item.diff > 0 ? "+" : ""}${n(item.diff, config.digits)}`}</b></div>
        `;
        tip.style.display = "block";
        tip.style.left = `${Math.min(rect.width - 270, Math.max(8, event.offsetX + 12))}px`;
        tip.style.top = `${Math.max(8, event.offsetY - 76)}px`;
      });
      dot.addEventListener("mouseleave", () => {
        tip.style.display = "none";
      });
    });
  }

  function initNearbyControls() {
    const sameLevel = $("nearbySameLevel");
    const sameMarket = $("nearbySameMarket");
    const radiusInput = $("nearbyRadiusKm");
    const radiusValue = $("nearbyRadiusValue");
    const updateRadius = () => {
      const raw = Number(radiusInput?.value);
      state.nearbyRadiusKm = Number.isFinite(raw) ? Math.max(0.1, Math.min(50, raw)) : 3;
      if (radiusInput) radiusInput.value = state.nearbyRadiusKm;
      if (radiusValue) radiusValue.textContent = `${n(state.nearbyRadiusKm, 1)} km`;
      renderNearbyMap();
    };
    if (sameLevel) {
      sameLevel.addEventListener("change", () => {
        state.nearbySameLevel = sameLevel.checked;
        renderNearbyMap();
      });
    }
    if (sameMarket) {
      sameMarket.addEventListener("change", () => {
        state.nearbySameMarket = sameMarket.checked;
        renderNearbyMap();
      });
    }
    if (radiusInput) {
      radiusInput.value = state.nearbyRadiusKm;
      radiusInput.addEventListener("change", updateRadius);
      radiusInput.addEventListener("keyup", (event) => {
        if (event.key === "Enter") updateRadius();
      });
    }
    if (radiusValue) radiusValue.textContent = `${n(state.nearbyRadiusKm, 1)} km`;
  }

  function setProfileFocus(mode) {
    state.profileFocus = mode === "map" ? "map" : "trend";
    const layout = $("customerProfileLayout");
    if (layout) {
      layout.classList.toggle("is-map-focus", state.profileFocus === "map");
      layout.classList.toggle("is-trend-focus", state.profileFocus !== "map");
    }
    window.setTimeout(() => {
      redrawCustomerTrends();
      if (state.nearbyMap) state.nearbyMap.invalidateSize();
    }, 160);
  }

  function initProfileFocusControls() {
    const trendPanel = document.querySelector(".customer-profile-panel");
    const mapPanel = document.querySelector(".customer-map-profile-panel");
    if (trendPanel) {
      trendPanel.addEventListener("pointerdown", (event) => {
        if (event.target.closest("a, button, input, label")) return;
        setProfileFocus("trend");
      });
    }
    if (mapPanel) {
      mapPanel.addEventListener("pointerdown", (event) => {
        if (event.target.closest("a, button, input, label")) return;
        setProfileFocus("map");
      });
    }
    setProfileFocus(state.profileFocus);
  }

  function initNearbyMap() {
    if (state.nearbyMap || typeof L === "undefined" || !$("nearbyMap")) return;
    state.nearbyMap = L.map("nearbyMap", {
      zoomControl: true,
      attributionControl: false,
      preferCanvas: true,
    }).setView([36.58, 116.25], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
    }).addTo(state.nearbyMap);
    state.nearbyLayer = L.layerGroup().addTo(state.nearbyMap);
  }

  function nearbyRows(target) {
    if (!target || !hasLocation(target)) return [];
    const radiusKm = Number.isFinite(Number(state.nearbyRadiusKm)) ? Number(state.nearbyRadiusKm) : 3;
    return state.rows
      .filter(hasLocation)
      .map((row) => ({ row, distance: distanceKm(target, row) }))
      .filter((item) => item.distance <= radiusKm + 0.0001)
      .filter((item) => !state.nearbySameLevel || String(item.row.cust_seg_name || "") === String(target.cust_seg_name || ""))
      .filter((item) => !state.nearbySameMarket || String(item.row.market_type || item.row.work_port_name || "") === String(target.market_type || target.work_port_name || ""))
      .sort((a, b) => a.distance - b.distance || num(b.row.stock_qty) - num(a.row.stock_qty));
  }

  function markerColor(row, selected) {
    const ratio = finite(row.stock_sale_ratio_7d_monthly);
    if (ratio !== null && ratio >= 15) return "#dc2626";
    if (ratio !== null && ratio >= 8) return "#f97316";
    if (ratio !== null && ratio >= 4) return "#eab308";
    return "#16a34a";
  }

  function customerDetailUrl(shopId) {
    return `customer_detail.html?date=${encodeURIComponent(day)}&shop=${encodeURIComponent(shopId)}`;
  }

  function drillToCustomer(row) {
    const id = shopKey(row);
    if (id) window.location.href = customerDetailUrl(id);
  }

  function storeMarkerIcon(row, selected) {
    const color = markerColor(row, selected);
    const size = selected ? Math.max(15, Math.min(28, Math.sqrt(num(row.stock_qty)) / 3.2 + 11)) : Math.max(10, Math.min(24, Math.sqrt(num(row.stock_qty)) / 3.2 + 9));
    return L.divIcon({
      className: "nearby-store-marker",
      html: `<span class="nearby-store-dot ${selected ? "is-current" : ""}" style="--store-color:${color};width:${size}px;height:${size}px;" title="${safeText(row.cust_name || row.shop_id || "-")}"></span>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }

  function nearbyPopup(row, distance, selected) {
    return `
      <div class="nearby-popup">
        <b>${safeText(row.cust_name || row.shop_id || "-")}</b>
        <span>${selected ? "当前客户" : `距中心 ${n(distance, 2)} km`}</span>
        <dl>
          <dt>客户档位</dt><dd>${safeText(row.cust_seg_name || "-")}</dd>
          <dt>市场类型</dt><dd>${safeText(row.market_type || row.work_port_name || "-")}</dd>
          <dt>库存</dt><dd>${n(row.stock_qty, 1)}</dd>
          <dt>7天动销</dt><dd>${n(row.sale_qty_7d, 1)}</dd>
          <dt>存销比</dt><dd>${n(row.stock_sale_ratio_7d_monthly, 2)}</dd>
        </dl>
      </div>
    `;
  }

  function nearbyTooltip(row, distance, selected) {
    return `
      <div class="nearby-hover-card">
        <div class="nearby-hover-title">
          <b>${safeText(row.cust_name || row.shop_id || "-")}</b>
          <span>${selected ? "当前客户" : `${n(distance, 2)} km`}</span>
        </div>
        <em>${safeText(row.cust_seg_name || "-")} / ${safeText(row.terminal_level || "-")} / ${safeText(row.market_type || row.work_port_name || "-")}</em>
        <div class="nearby-hover-metrics">
          <span><small>库存</small><strong>${n(row.stock_qty, 1)}</strong></span>
          <span><small>7天动销</small><strong>${n(row.sale_qty_7d, 1)}</strong></span>
          <span><small>存销比</small><strong>${n(row.stock_sale_ratio_7d_monthly, 2)}</strong></span>
        </div>
        ${selected ? "" : "<p>点击点位进入画像</p>"}
      </div>
    `;
  }

  function renderNearbyMap() {
    const target = state.rows.find((row) => shopKey(row) === state.selectedShopId);
    const meta = $("nearbyMapMeta");
    const strip = $("nearbyCustomerStrip");
    initNearbyMap();
    if (!state.nearbyMap || !state.nearbyLayer) {
      if (meta) meta.textContent = "地图组件未加载。";
      return;
    }
    state.nearbyLayer.clearLayers();
    if (!target || !hasLocation(target)) {
      state.nearbyMap.setView([36.58, 116.25], 11);
      if (meta) meta.textContent = "该客户没有经纬度，无法查看附近客户。";
      if (strip) strip.innerHTML = "";
      return;
    }
    const items = nearbyRows(target);
    const radiusKm = Number.isFinite(Number(state.nearbyRadiusKm)) ? Number(state.nearbyRadiusKm) : 3;
    const bounds = [];
    items.forEach((item) => {
      const row = item.row;
      const selected = shopKey(row) === state.selectedShopId;
      const marker = L.marker([Number(row.latitude), Number(row.longitude)], {
        icon: storeMarkerIcon(row, selected),
        riseOnHover: true,
        keyboard: true,
        title: row.cust_name || row.shop_id || "",
      });
      marker.bindTooltip(nearbyTooltip(row, item.distance, selected), {
        direction: "top",
        offset: [0, -18],
        opacity: 1,
        sticky: true,
        className: "nearby-hover-tooltip",
      });
      marker.on("click", () => drillToCustomer(row));
      marker.addTo(state.nearbyLayer);
      bounds.push([Number(row.latitude), Number(row.longitude)]);
    });
    L.circle([Number(target.latitude), Number(target.longitude)], {
      radius: radiusKm * 1000,
      color: "#d69a2d",
      weight: 1,
      fillColor: "#d69a2d",
      fillOpacity: 0.05,
      dashArray: "6 6",
    }).addTo(state.nearbyLayer);
    if (bounds.length > 1) state.nearbyMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
    else state.nearbyMap.setView([Number(target.latitude), Number(target.longitude)], 15);
    window.setTimeout(() => state.nearbyMap.invalidateSize(), 80);
    const nearbyCount = Math.max(0, items.length - 1);
    if (meta) {
      meta.textContent = `${n(radiusKm, 1)}km 内显示 ${nearbyCount} 个附近客户；地图圆点可直接点击钻取。`;
    }
    if (strip) {
      strip.innerHTML = items.slice(0, 10).map((item) => {
        const row = item.row;
        const selected = shopKey(row) === state.selectedShopId;
        return `
          <button type="button" class="${selected ? "is-selected" : ""}" data-shop-id="${safeText(shopKey(row))}">
            <b>${safeText(row.cust_name || row.shop_id || "-")}</b>
            <span>${selected ? "当前客户" : `${n(item.distance, 2)}km`} / 库存 ${n(row.stock_qty, 1)}</span>
          </button>
        `;
      }).join("");
      strip.querySelectorAll("button[data-shop-id]").forEach((button) => {
        button.addEventListener("click", () => {
          const id = button.dataset.shopId || "";
          if (id && id !== state.selectedShopId) {
            window.location.href = customerDetailUrl(id);
          }
        });
      });
    }
  }

  function selectCustomer(shopId) {
    if (!shopId) return;
    state.selectedShopId = shopId;
    const row = state.rows.find((item) => shopKey(item) === shopId);
    $("customerTrendTitle").textContent = row ? (row.cust_name || shopId) : shopId;
    $("customerTrendMeta").textContent = row
      ? `客户档位 ${row.cust_seg_name || "-"} / ${row.terminal_level || "-"} / ${row.market_type || row.work_port_name || "-"} / 周期 ${day || "-"}`
      : "正在加载客户趋势";
    renderNearbyMap();
    renderLoadingCharts("趋势加载中...");
    loadCustomerTrend(shopId, (trendRows) => {
      if (!trendRows.length) {
        $("customerTrendMeta").textContent = "未找到该客户趋势文件。";
        renderLoadingCharts("暂无趋势数据");
        $("customerTrendStats").innerHTML = "";
        state.currentTrendRows = [];
        return;
      }
      state.currentTrendRows = trendRows;
      renderTrendStats(trendRows);
      redrawCustomerTrends();
    });
  }

  function init() {
    setTrendCaptions();
    buildCustomerGeoMap();
    initNearbyControls();
    initProfileFocusControls();
    if ($("backToList")) {
      $("backToList").href = `inventory_detail.html?date=${encodeURIComponent(day || "")}`;
    }
    loadDay(day, (rows) => {
      state.rows = rows.map(mergeCustomerGeo).sort((a, b) => num(b.stock_qty) - num(a.stock_qty));
      const fallback = state.rows[0] ? shopKey(state.rows[0]) : "";
      selectCustomer(state.selectedShopId || fallback);
    });
    window.addEventListener("resize", () => {
      window.clearTimeout(state.resizeTimer);
      state.resizeTimer = window.setTimeout(redrawCustomerTrends, 120);
    });
  }

  init();
})();

