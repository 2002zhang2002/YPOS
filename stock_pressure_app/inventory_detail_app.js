(function () {
  const data = window.DIAGNOSIS_APP_DATA || {};
  const params = new URLSearchParams(window.location.search);
  const day = params.get("date") || (data.weeklyStockCompareRows || []).slice(-1)[0]?.biz_date || "";
  const state = {
    rows: [],
    filteredRows: [],
    query: "",
    filters: {},
    sortKey: "stock_qty",
    sortDir: "desc",
    customerGeoMap: new Map(),
    colWidths: {},
  };

  const columns = [
    { key: "_index", label: "#", type: "index", width: 58, filter: false },
    { key: "cust_name", label: "客户", type: "text", width: 280, filter: "text", className: "customer-name-col" },
    { key: "license_no", label: "许可证号", type: "text", width: 150, filter: "text" },
    { key: "cust_seg_name", label: "客户档位", type: "text", width: 110, filter: "select" },
    { key: "terminal_level", label: "终端等级", type: "text", width: 110, filter: "select" },
    { key: "market_type", label: "市场类型", type: "text", width: 110, filter: "select" },
    { key: "ss_name", label: "市场部", type: "text", width: 170, filter: "select" },
    { key: "slsman", label: "营销线路", type: "text", width: 170, filter: "select" },
    { key: "stock_qty", label: "库存", type: "number", width: 110, digits: 1, filter: false },
    { key: "sale_qty_7d", label: "7天动销", type: "number", width: 120, digits: 1, filter: false },
    { key: "purchase_qty_7d", label: "7天订购", type: "number", width: 120, digits: 1, filter: false },
    { key: "stock_sale_ratio_7d_monthly", label: "存销比", type: "number", width: 120, digits: 2, filter: false },
    { key: "sale_qty_30d", label: "30天动销", type: "number", width: 120, digits: 1, filter: false },
    { key: "_action", label: "操作", type: "action", width: 110, filter: false },
  ];

  const $ = (id) => document.getElementById(id);

  function num(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
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

  function getCellValue(row, key) {
    if (key === "license_no") {
      return row.license_no;
    }
    if (key === "purchase_qty_7d") return row.purchase_qty_7d ?? row.purchase_qty;
    return row[key];
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
    if (!geo) return row;
    return {
      ...geo,
      ...row,
      latitude: geo.latitude,
      longitude: geo.longitude,
      ss_name: row.ss_name ?? geo.ss_name,
      slsman: row.slsman ?? geo.slsman,
    };
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
    script.dataset.day = targetDay;
    script.onload = () => callback(rowsForDay(targetDay));
    script.onerror = () => callback([]);
    document.body.appendChild(script);
  }

  function renderSummary(rows) {
    const stockTotal = rows.reduce((sum, row) => sum + num(row.stock_qty), 0);
    const sale7Total = rows.reduce((sum, row) => sum + num(row.sale_qty_7d), 0);
    const purchase7Total = rows.reduce((sum, row) => sum + num(row.purchase_qty_7d ?? row.purchase_qty), 0);
    const ratio = sale7Total > 0 ? stockTotal / (sale7Total / 7 * 30) : null;
    const perShopStock = rows.length ? stockTotal / rows.length : null;
    const perShopSale7 = rows.length ? sale7Total / rows.length : null;
    const activeCustomers = rows.filter((row) => num(row.sale_qty_7d) > 0).length;
    const cards = [
      ["客户数", n(rows.length), "当前周期二三星客户"],
      ["库存合计", n(stockTotal, 1), `户均库存 ${n(perShopStock, 1)}`],
      ["7天动销", n(sale7Total, 1), `户均动销 ${n(perShopSale7, 1)}`],
      ["7天订购", n(purchase7Total, 1), "近7天累计订购"],
      ["存销比", n(ratio, 2), `有动销客户 ${n(activeCustomers)}`],
    ];
    $("detailSummary").innerHTML = cards.map(([label, value, hint]) => `
      <article class="weekly-kpi">
        <span>${label}</span>
        <b>${value}</b>
        <em>${hint}</em>
      </article>
    `).join("");
    $("detailTitle").textContent = `${day || "-"} 周期客户明细`;
    const hint = $("customerListHint");
    if (hint) hint.textContent = `${day || "-"} 周期快照，可筛选、排序、拖拽列宽；点击客户进入客户画像页。`;
  }

  function rowSearchText(row) {
    return [
      row.cust_name,
      row.shop_id,
      row.cust_id,
      getCellValue(row, "license_no"),
      row.cust_seg_name,
      row.terminal_level,
      row.market_type,
      row.work_port_name,
      row.group_name,
      row.base_type_name,
      row.ss_name,
      row.slsman,
    ].join(" ").toLowerCase();
  }

  function customerUrl(row) {
    return `customer_detail.html?date=${encodeURIComponent(day)}&shop=${encodeURIComponent(shopKey(row))}`;
  }

  function optionValues(key) {
    const values = new Set();
    state.rows.forEach((row) => {
      const value = getCellValue(row, key);
      if (value !== undefined && value !== null && String(value).trim() !== "") values.add(String(value));
    });
    return Array.from(values).sort((a, b) => a.localeCompare(b, "zh-CN", { numeric: true }));
  }

  function renderTableHead() {
    const table = $("customerExcelTable");
    const colgroup = columns.map((col) => {
      const width = state.colWidths[col.key] || col.width || 120;
      return `<col data-col-key="${safeText(col.key)}" style="width:${width}px">`;
    }).join("");
    const heads = columns.map((col) => {
      const sorted = state.sortKey === col.key ? state.sortDir : "";
      return `
        <th data-key="${safeText(col.key)}" class="${col.type === "number" ? "is-number" : ""}">
          <button class="excel-sort-btn" type="button" data-sort-key="${safeText(col.key)}">
            <span>${safeText(col.label)}</span>
            <em>${sorted === "asc" ? "↑" : sorted === "desc" ? "↓" : "↕"}</em>
          </button>
          <span class="col-resizer" data-resize-key="${safeText(col.key)}"></span>
        </th>
      `;
    }).join("");
    const filters = columns.map((col) => {
      if (col.filter === "text") {
        return `<th><input class="excel-filter-input" data-filter-key="${safeText(col.key)}" value="${safeText(state.filters[col.key] || "")}" placeholder="筛选"></th>`;
      }
      if (col.filter === "select") {
        const current = String(state.filters[col.key] || "");
        const options = optionValues(col.key).map((value) => `<option value="${safeText(value)}" ${value === current ? "selected" : ""}>${safeText(value)}</option>`).join("");
        return `<th><select class="excel-filter-select" data-filter-key="${safeText(col.key)}"><option value="">全部</option>${options}</select></th>`;
      }
      return `<th></th>`;
    }).join("");
    table.innerHTML = `
      <colgroup>${colgroup}</colgroup>
      <thead>
        <tr class="excel-head-row">${heads}</tr>
        <tr class="excel-filter-row">${filters}</tr>
      </thead>
      <tbody id="dayDetailTable"></tbody>
    `;
    bindTableHeadEvents();
  }

  function formatCell(row, col, index) {
    if (col.type === "index") return index + 1;
    if (col.type === "action") return `<a class="detail-link inline" href="${customerUrl(row)}">查看画像</a>`;
    if (col.key === "cust_name") {
      return `
        <a class="customer-name-btn" href="${customerUrl(row)}">${safeText(row.cust_name || row.shop_id || "-")}</a>
        <small>${safeText(row.group_name || row.work_port_name || "")}</small>
      `;
    }
    const value = getCellValue(row, col.key);
    if (col.type === "number") return n(value, col.digits || 0);
    return safeText(value || "-");
  }

  function compareRows(a, b) {
    const col = columns.find((item) => item.key === state.sortKey);
    if (!col || col.type === "index" || col.type === "action") return 0;
    const av = getCellValue(a, col.key);
    const bv = getCellValue(b, col.key);
    let result;
    if (col.type === "number") {
      result = num(av) - num(bv);
    } else {
      result = String(av || "").localeCompare(String(bv || ""), "zh-CN", { numeric: true });
    }
    return state.sortDir === "asc" ? result : -result;
  }

  function rowPassesFilters(row) {
    const q = state.query.trim().toLowerCase();
    if (q && !rowSearchText(row).includes(q)) return false;
    return Object.entries(state.filters).every(([key, raw]) => {
      const filter = String(raw || "").trim().toLowerCase();
      if (!filter) return true;
      const value = String(getCellValue(row, key) || "").toLowerCase();
      const col = columns.find((item) => item.key === key);
      return col?.filter === "select" ? value === filter : value.includes(filter);
    });
  }

  function renderCustomerTable() {
    const tbody = $("dayDetailTable");
    const rows = state.filteredRows;
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="${columns.length}">暂无当前周期客户数据</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((row, index) => `
      <tr data-shop-id="${safeText(shopKey(row))}">
        ${columns.map((col) => `<td class="${col.type === "number" ? "is-number" : ""} ${col.className || ""}">${formatCell(row, col, index)}</td>`).join("")}
      </tr>
    `).join("");
    tbody.querySelectorAll("tr[data-shop-id]").forEach((tr) => {
      tr.addEventListener("click", (event) => {
        if (event.target.closest("a, input, select, button")) return;
        const row = state.filteredRows.find((item) => shopKey(item) === tr.dataset.shopId);
        if (row) window.location.href = customerUrl(row);
      });
    });
  }

  function applyFilter() {
    state.filteredRows = state.rows.filter(rowPassesFilters).sort(compareRows);
    renderCustomerTable();
  }

  function bindTableHeadEvents() {
    document.querySelectorAll(".excel-sort-btn").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.sortKey || "";
        const col = columns.find((item) => item.key === key);
        if (!col || col.type === "index" || col.type === "action") return;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDir = col.type === "number" ? "desc" : "asc";
        }
        renderTableHead();
        applyFilter();
      });
    });
    document.querySelectorAll("[data-filter-key]").forEach((control) => {
      control.addEventListener("input", () => {
        state.filters[control.dataset.filterKey] = control.value || "";
        applyFilter();
      });
      control.addEventListener("change", () => {
        state.filters[control.dataset.filterKey] = control.value || "";
        applyFilter();
      });
    });
    initColumnResize();
  }

  function initColumnResize() {
    document.querySelectorAll(".col-resizer").forEach((handle) => {
      handle.addEventListener("pointerdown", (event) => {
        const key = handle.dataset.resizeKey;
        const th = handle.closest("th");
        if (!key || !th) return;
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = th.getBoundingClientRect().width;
        const onMove = (moveEvent) => {
          const width = Math.max(72, Math.round(startWidth + moveEvent.clientX - startX));
          state.colWidths[key] = width;
          const col = Array.from(document.querySelectorAll("col[data-col-key]"))
            .find((item) => item.dataset.colKey === key);
          if (col) col.style.width = `${width}px`;
        };
        const onUp = () => {
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      });
    });
  }

  function initSearch() {
    const input = $("customerSearch");
    if (!input) return;
    input.placeholder = "全表搜索：客户 / 许可证号 / 市场部 / 营销线路 / 小组";
    input.addEventListener("input", () => {
      state.query = input.value || "";
      applyFilter();
    });
  }

  function init() {
    initSearch();
    buildCustomerGeoMap();
    renderTableHead();
    if (!day) {
      renderSummary([]);
      $("dayDetailTable").innerHTML = `<tr><td colspan="${columns.length}">暂无周期参数</td></tr>`;
      return;
    }
    loadDay(day, (rows) => {
      state.rows = rows.map(mergeCustomerGeo);
      state.filteredRows = state.rows.filter(rowPassesFilters).sort(compareRows);
      renderSummary(state.rows);
      renderTableHead();
      renderCustomerTable();
    });
  }

  init();
})();
