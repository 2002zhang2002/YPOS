(function () {
  const data = window.DIAGNOSIS_APP_DATA || {};
  const C = window.InventoryCharts;
  const state = {
    metric: "stock_sale_ratio_30d",
    dimension: "",
    dimensionValue: "",
    abnormal: "",
    search: "",
    markers: [],
    layer: null,
    trendCache: {}
  };

  const $ = (id) => document.getElementById(id);
  const rows = data.customerRows || [];

  renderSummary();
  initFilters();
  const map = initMap();
  renderMap();
  C.centered($("customerTrendChart"), "点击地图点位查看客户每日库存趋势", 110);

  $("mapMetricSelect").addEventListener("change", (e) => {
    state.metric = e.target.value;
    renderMap();
  });
  $("dimensionSelect").addEventListener("change", (e) => {
    state.dimension = e.target.value;
    state.dimensionValue = "";
    fillDimensionValues();
    renderMap();
  });
  $("dimensionValueSelect").addEventListener("change", (e) => {
    state.dimensionValue = e.target.value;
    renderMap();
  });
  $("abnormalSelect").addEventListener("change", (e) => {
    state.abnormal = e.target.value;
    renderMap();
  });
  $("searchInput").addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    renderMap();
  });
  $("resetBtn").addEventListener("click", () => {
    state.metric = "stock_sale_ratio_30d";
    state.dimension = "";
    state.dimensionValue = "";
    state.abnormal = "";
    state.search = "";
    $("mapMetricSelect").value = state.metric;
    $("dimensionSelect").value = "";
    $("abnormalSelect").value = "";
    $("searchInput").value = "";
    fillDimensionValues();
    renderMap();
  });
  $("closeDrawer").addEventListener("click", () => {
    $("customerDrawer").style.display = "none";
  });

  function renderSummary() {
    const s = data.summary || {};
    const cards = [
      ["客户数", C.fmt(s.customerCount, 0)],
      ["动销", C.fmt(s.activeCustomerCount, 0)],
      ["库存", C.fmt(s.stockQty, 0)],
      ["7天比", C.fmt(s.ratio7d, 2)],
      ["30天比", C.fmt(s.ratio30d, 2)],
      ["异常", C.fmt(s.abnormalCustomerCount, 0)]
    ];
    $("summaryCards").innerHTML = cards.map(([k, v]) => `<div class="card"><b>${v}</b><span>${k}</span></div>`).join("");
    $("mapMeta").textContent = `数据期：${data.trendStart || "-"} 至 ${data.periodEnd || "-"}；异常基准 ${data.baselineDays || 180} 天`;
  }

  function initFilters() {
    fillDimensionValues();
  }

  function fillDimensionValues() {
    const select = $("dimensionValueSelect");
    select.innerHTML = `<option value="">全部值</option>`;
    if (!state.dimension) return;
    const values = [...new Set(rows.map((row) => row[state.dimension]).filter(Boolean))].sort();
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
  }

  function initMap() {
    const map = L.map("map", { preferCanvas: true }).setView([36.58, 116.25], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }).addTo(map);
    state.layer = L.layerGroup().addTo(map);
    return map;
  }

  function filteredRows() {
    return rows.filter((row) => {
      if (!row.longitude || !row.latitude) return false;
      if (state.dimension && state.dimensionValue && row[state.dimension] !== state.dimensionValue) return false;
      if (state.abnormal && !String(row.abnormal_tag || "").includes(state.abnormal)) return false;
      if (state.search) {
        const text = [row.cust_name, row.group_name, row.slsman, row.ss_name, row.shop_id].join(" ").toLowerCase();
        if (!text.includes(state.search.toLowerCase())) return false;
      }
      return true;
    });
  }

  function renderMap() {
    state.layer.clearLayers();
    const list = filteredRows();
    const bounds = [];
    list.forEach((row) => {
      const lat = Number(row.latitude);
      const lng = Number(row.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      const marker = L.circleMarker([lat, lng], {
        radius: radius(row.stock_qty),
        color: "#1f2937",
        weight: 1,
        fillColor: color(row[state.metric]),
        fillOpacity: 0.75
      });
      marker.bindPopup(popup(row));
      marker.on("click", () => selectCustomer(row));
      marker.addTo(state.layer);
      bounds.push([lat, lng]);
    });
    if (bounds.length) map.fitBounds(bounds, { padding: [25, 25] });
    $("mapMeta").textContent = `当前显示 ${list.length} 户；点大小=库存，颜色=${metricName(state.metric)}`;
  }

  function radius(stock) {
    return Math.max(5, Math.min(24, 4 + Math.sqrt(C.n(stock)) * 0.8));
  }

  function color(value) {
    const v = C.n(value);
    if (state.metric === "stock_qty") {
      if (v < 200) return "#16a34a";
      if (v < 500) return "#eab308";
      if (v < 1000) return "#f97316";
      return "#dc2626";
    }
    if (v < 3) return "#16a34a";
    if (v < 8) return "#eab308";
    if (v < 15) return "#f97316";
    if (v < 25) return "#dc2626";
    return "#991b1b";
  }

  function metricName(metric) {
    return {
      stock_sale_ratio_30d: "30天存销比",
      stock_sale_ratio_7d: "7天存销比",
      stock_qty: "库存量",
      abnormal_score: "异常分"
    }[metric] || metric;
  }

  function popup(row) {
    return `<b>${row.cust_name || row.shop_id}</b><br>
      小组：${row.group_name || "-"}<br>
      档位：${row.cust_seg_name || "-"} ${row.market_type || ""}<br>
      库存：${C.fmt(row.stock_qty, 0)}<br>
      7天存销比：${C.fmt(row.stock_sale_ratio_7d, 2)}<br>
      30天存销比：${C.fmt(row.stock_sale_ratio_30d, 2)}<br>
      异常：${row.abnormal_tag || "正常"}`;
  }

  function selectCustomer(row) {
    $("customerDrawer").style.display = "block";
    $("selectedCustomerTitle").textContent = row.cust_name || row.shop_id;
    $("selectedCustomerSub").textContent = `${row.group_name || "-"} / ${row.market_type || "-"} / ${row.cust_seg_name || "-"}档 / ${row.base_type_name || "-"}`;
    $("selectedCustomerMetrics").innerHTML = [
      ["库存", C.fmt(row.stock_qty, 0)],
      ["7天销售", C.fmt(row.sale_qty_7d, 0)],
      ["30天销售", C.fmt(row.sale_qty_30d, 0)],
      ["7天比", C.fmt(row.stock_sale_ratio_7d, 2)],
      ["30天比", C.fmt(row.stock_sale_ratio_30d, 2)],
      ["异常分", C.fmt(row.abnormal_score, 0)]
    ].map(([k, v]) => `<div class="metric-pill"><b>${v}</b><span>${k}</span></div>`).join("");
    loadTrend(row.shop_id);
  }

  function loadTrend(shopId) {
    const key = String(shopId || "");
    if (state.trendCache[key]) {
      C.drawTrend($("customerTrendChart"), state.trendCache[key], { height: 260 });
      return;
    }
    const path = data.customerTrendIndex && data.customerTrendIndex[key];
    if (!path) {
      C.centered($("customerTrendChart"), "这个客户没有趋势文件", 110);
      return;
    }
    C.centered($("customerTrendChart"), "正在加载客户趋势...", 110);
    const old = document.getElementById("dynamicCustomerTrendScript");
    if (old) old.remove();
    window.CUSTOMER_TREND_DATA = null;
    const script = document.createElement("script");
    script.id = "dynamicCustomerTrendScript";
    script.src = path;
    script.onload = () => {
      if (window.CUSTOMER_TREND_DATA && String(window.CUSTOMER_TREND_DATA.shopId) === key) {
        state.trendCache[key] = window.CUSTOMER_TREND_DATA.rows || [];
        C.drawTrend($("customerTrendChart"), state.trendCache[key], { height: 260 });
      }
    };
    document.body.appendChild(script);
  }
})();
