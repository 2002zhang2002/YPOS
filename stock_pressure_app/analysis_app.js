(function () {
  const data = window.DIAGNOSIS_APP_DATA || {};
  const C = window.InventoryCharts;
  const state = {
    tab: "dimension",
    dimension: "group_name",
    search: "",
    abnormal: "",
    selectedShopId: null,
    trendCache: {}
  };

  const labels = {
    group_name: "所属小组",
    cust_seg_name: "客户档位",
    market_type: "市场类型",
    work_port_name: "城乡分类",
    business_area_type: "商圈类型",
    base_type_name: "经营业态",
    terminal_level: "终端等级"
  };

  const $ = (id) => document.getElementById(id);

  $("periodText").textContent = `趋势期间：${data.trendStart || "-"} 至 ${data.periodEnd || "-"}`;
  $("baselineText").textContent = `异常基准：${data.baselineStart || "-"} 至 ${data.periodEnd || "-"}，约 ${data.baselineDays || 180} 天`;
  $("generatedText").textContent = `生成时间：${data.generatedAt || "-"}`;

  $("dimensionSelect").addEventListener("change", (e) => {
    state.dimension = e.target.value;
    render();
  });
  $("searchInput").addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    render();
  });
  $("abnormalSelect").addEventListener("change", (e) => {
    state.abnormal = e.target.value;
    render();
  });
  $("resetBtn").addEventListener("click", () => {
    state.dimension = "group_name";
    state.search = "";
    state.abnormal = "";
    $("dimensionSelect").value = state.dimension;
    $("searchInput").value = "";
    $("abnormalSelect").value = "";
    render();
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("is-active", item === btn));
      document.querySelectorAll(".tab-pane").forEach((pane) => pane.classList.remove("is-active"));
      $(`${state.tab}Tab`).classList.add("is-active");
      render();
    });
  });

  render();

  function render() {
    renderSummary();
    C.drawTrend($("trendChart"), data.areaTrendRows || [], { weeklyRows: data.weeklyRatioRows || [] });
    renderCustomerTrend();
    renderDimension();
    renderGroups();
    renderCustomers();
    renderAbnormal();
  }

  function renderSummary() {
    const s = data.summary || {};
    const cards = [
      ["客户数", C.fmt(s.customerCount, 0)],
      ["动销客户", C.fmt(s.activeCustomerCount, 0)],
      ["每日库存", C.fmt(s.stockQty, 0)],
      ["7天存销比", C.fmt(s.ratio7d, 2)],
      ["30天存销比", C.fmt(s.ratio30d, 2)],
      ["异常客户", C.fmt(s.abnormalCustomerCount, 0)]
    ];
    $("summaryCards").innerHTML = cards.map(([label, value]) => `<div class="card"><b>${value}</b><span>${label}</span></div>`).join("");
  }

  function includesSearch(row) {
    if (!state.search) return true;
    const text = [row.group_name, row.cust_name, row.shop_id, row.slsman, row.ss_name, row.dimension_value, row.abnormal_tag]
      .join(" ")
      .toLowerCase();
    return text.includes(state.search.toLowerCase());
  }

  function abnormalMatch(row) {
    if (!state.abnormal) return true;
    return String(row.abnormal_tag || "").includes(state.abnormal);
  }

  function renderCustomerTrend() {
    const svg = $("customerTrendChart");
    const customer = (data.customerRows || []).find((row) => String(row.shop_id) === String(state.selectedShopId));
    $("customerTrendTitle").textContent = customer ? `客户每日库存变化趋势：${customer.cust_name || customer.shop_id}` : "客户每日库存变化趋势";
    if (!state.selectedShopId) {
      C.centered(svg, "点击客户表或异常表中的一行查看客户趋势");
      return;
    }
    const rows = state.trendCache[String(state.selectedShopId)];
    if (rows) {
      C.drawTrend(svg, rows, { height: 260 });
      return;
    }
    loadCustomerTrend(state.selectedShopId);
  }

  function loadCustomerTrend(shopId) {
    const key = String(shopId || "");
    const path = data.customerTrendIndex && data.customerTrendIndex[key];
    if (!path) {
      C.centered($("customerTrendChart"), "这个客户没有趋势文件");
      return;
    }
    C.centered($("customerTrendChart"), "正在加载客户趋势...");
    const old = document.getElementById("dynamicCustomerTrendScript");
    if (old) old.remove();
    window.CUSTOMER_TREND_DATA = null;
    const script = document.createElement("script");
    script.id = "dynamicCustomerTrendScript";
    script.src = path;
    script.onload = () => {
      if (window.CUSTOMER_TREND_DATA && String(window.CUSTOMER_TREND_DATA.shopId) === key) {
        state.trendCache[key] = window.CUSTOMER_TREND_DATA.rows || [];
        renderCustomerTrend();
      }
    };
    document.body.appendChild(script);
  }

  function renderDimension() {
    $("dimensionTitle").textContent = `${labels[state.dimension] || state.dimension}对比`;
    const rows = (data.dimensionRows || [])
      .filter((row) => row.dimension_type === state.dimension)
      .filter(includesSearch)
      .sort((a, b) => C.n(b.abnormal_customer_pct) - C.n(a.abnormal_customer_pct) || C.n(b.stock_sale_ratio_30d) - C.n(a.stock_sale_ratio_30d))
      .slice(0, 300);
    renderTable("dimensionTable", rows, [
      ["dimension_value", labels[state.dimension] || "维度"],
      ["customer_count", "客户数", 0],
      ["active_customer_count", "动销客户", 0],
      ["stock_qty", "库存", 0],
      ["sale_qty_30d", "30天销售", 0],
      ["stock_sale_ratio_30d", "30天存销比", 2],
      ["abnormal_customer_count", "异常客户", 0],
      ["abnormal_customer_pct", "异常占比", "pct"]
    ]);
  }

  function renderGroups() {
    const rows = (data.groupRows || [])
      .filter(includesSearch)
      .sort((a, b) => C.n(a.group_score) - C.n(b.group_score))
      .slice(0, 500);
    renderTable("groupTable", rows, [
      ["group_name", "所属小组"],
      ["group_score", "评分", 1],
      ["customer_count", "客户数", 0],
      ["avg_cust_seg", "平均档位", 1],
      ["city_customer_pct", "城网占比", "pct"],
      ["rural_customer_pct", "农网占比", "pct"],
      ["stock_qty", "库存", 0],
      ["sale_qty_30d", "30天销售", 0],
      ["stock_sale_ratio_30d", "30天存销比", 2],
      ["expected_30d_sale_qty", "同类理论30天销售", 0],
      ["sale_achievement", "销售达成", "pct"],
      ["abnormal_customer_count", "异常客户", 0],
      ["abnormal_customer_pct", "异常占比", "pct"]
    ]);
  }

  function renderCustomers() {
    const rows = (data.customerRows || [])
      .filter(includesSearch)
      .filter(abnormalMatch)
      .sort((a, b) => C.n(b.abnormal_score) - C.n(a.abnormal_score) || C.n(b.stock_peer_multiple) - C.n(a.stock_peer_multiple))
      .slice(0, 1000);
    renderTable("customerTable", rows, customerColumns(), true);
  }

  function renderAbnormal() {
    const rows = (data.abnormalRows || [])
      .filter(includesSearch)
      .filter(abnormalMatch)
      .slice(0, 1000);
    renderTable("abnormalTable", rows, customerColumns(), true);
  }

  function customerColumns() {
    return [
      ["cust_name", "客户"],
      ["group_name", "所属小组"],
      ["terminal_level", "终端"],
      ["market_type", "市场"],
      ["cust_seg_name", "档位"],
      ["business_area_type", "商圈"],
      ["base_type_name", "业态"],
      ["stock_qty", "当前库存", 0],
      ["sale_qty_7d", "7天销售", 0],
      ["sale_qty_30d", "30天销售", 0],
      ["stock_sale_ratio_7d", "7天存销比", 2],
      ["stock_sale_ratio_30d", "30天存销比", 2],
      ["baseline_30d_sale_qty", "180天折算30天销售", 0],
      ["peer_avg_stock_qty", "同类均库存", 0],
      ["peer_avg_30d_sale_qty", "同类均30天销售", 0],
      ["stock_peer_multiple", "库存偏离", 2],
      ["sale_peer_multiple", "销售偏离", 2],
      ["abnormal_tag", "异常标签", "badge"]
    ];
  }

  function renderTable(id, rows, columns, clickable = false) {
    const table = $(id);
    const thead = `<thead><tr>${columns.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead>`;
    const tbody = rows.length
      ? `<tbody>${rows.map((row) => `<tr class="${clickable ? "is-clickable" : ""}" data-shop-id="${row.shop_id || ""}">${columns.map(([key,, mode]) => `<td>${cell(row[key], mode)}</td>`).join("")}</tr>`).join("")}</tbody>`
      : `<tbody><tr><td colspan="${columns.length}">没有符合条件的数据</td></tr></tbody>`;
    table.innerHTML = thead + tbody;
    if (clickable) {
      table.querySelectorAll("tr[data-shop-id]").forEach((tr) => {
        tr.addEventListener("click", () => {
          state.selectedShopId = tr.getAttribute("data-shop-id");
          renderCustomerTrend();
          $("customerTrendChart").scrollIntoView({ behavior: "smooth", block: "center" });
        });
      });
    }
  }

  function cell(value, mode) {
    if (mode === "pct") return C.pct(value);
    if (mode === "badge") {
      const text = value || "-";
      const cls = String(text).includes("正常") ? "badge" : String(text).includes("偏高") ? "badge warn" : "badge bad";
      return `<span class="${cls}">${text}</span>`;
    }
    if (typeof mode === "number") return C.fmt(value, mode);
    return value == null || value === "" ? "-" : String(value);
  }
})();
