window.InventoryCharts = (function () {
  function n(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  }

  function fmt(value, digits = 2) {
    if (value == null || value === "") return "-";
    return n(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
  }

  function pct(value) {
    if (value == null || value === "") return "-";
    return `${(n(value) * 100).toFixed(1)}%`;
  }

  function clear(svg) {
    svg.innerHTML = "";
  }

  function addText(svg, x, y, text, anchor = "start") {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("x", x);
    el.setAttribute("y", y);
    el.setAttribute("text-anchor", anchor);
    el.textContent = text;
    svg.appendChild(el);
  }

  function drawGrid(svg, width, height, pad) {
    for (let i = 0; i <= 5; i += 1) {
      const y = pad.top + ((height - pad.top - pad.bottom) * i) / 5;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", pad.left);
      line.setAttribute("x2", width - pad.right);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "#eadfce");
      svg.appendChild(line);
    }
  }

  function drawPath(svg, points, color, strokeWidth) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", points.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" "));
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", strokeWidth);
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
  }

  function drawPoint(svg, x, y, color) {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", 4);
    circle.setAttribute("fill", color);
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", 1.5);
    svg.appendChild(circle);
  }

  function centered(svg, text, y = 130) {
    clear(svg);
    addText(svg, 550, y, text, "middle");
  }

  function drawTrend(svg, rows, options = {}) {
    clear(svg);
    const data = [...(rows || [])].sort((a, b) => String(a.biz_date).localeCompare(String(b.biz_date)));
    if (!data.length) {
      centered(svg, "暂无趋势数据");
      return;
    }
    const width = options.width || 1100;
    const height = options.height || 360;
    const pad = { left: 58, right: 42, top: 24, bottom: 42 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    const stockMax = Math.max(...data.map((row) => n(row.stock_qty)), 1);
    const ratioMax = Math.max(...data.flatMap((row) => [n(row.stock_sale_ratio_7d), n(row.stock_sale_ratio_30d)]), 1);
    const x = (i) => pad.left + (data.length === 1 ? plotW / 2 : (i / (data.length - 1)) * plotW);
    const yStock = (v) => pad.top + plotH - (n(v) / stockMax) * plotH;
    const yRatio = (v) => pad.top + plotH - (n(v) / ratioMax) * plotH;
    const weekly = new Set((options.weeklyRows || []).map((row) => String(row.biz_date)));

    drawGrid(svg, width, height, pad);
    drawPath(svg, data.map((row, i) => [x(i), yStock(row.stock_qty)]), "#173f35", 3);
    drawPath(svg, data.map((row, i) => [x(i), yRatio(row.stock_sale_ratio_7d)]), "#d97706", 2.5);
    drawPath(svg, data.map((row, i) => [x(i), yRatio(row.stock_sale_ratio_30d)]), "#b91c1c", 2.5);

    data.forEach((row, i) => {
      if (weekly.has(String(row.biz_date))) drawPoint(svg, x(i), yRatio(row.stock_sale_ratio_7d), "#d97706");
      if (i !== 0 && i !== data.length - 1 && i % Math.ceil(data.length / 8) !== 0) return;
      addText(svg, x(i), height - 14, String(row.biz_date).slice(5), "middle");
    });
    addText(svg, 10, 20, `库存最大 ${fmt(stockMax, 0)}`);
    addText(svg, width - 10, 20, `存销比最大 ${fmt(ratioMax, 2)}`, "end");
  }

  return { n, fmt, pct, drawTrend, centered };
})();
