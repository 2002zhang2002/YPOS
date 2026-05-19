import argparse
import json
from pathlib import Path


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>&#23458;&#25143;&#24211;&#23384;&#22320;&#29702;&#20998;&#26512;&#22320;&#22270;</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {
      --ink:#17211c;
      --muted:#66736b;
      --paper:#fffaf0;
      --panel:#ffffff;
      --line:#dfd4c2;
      --green:#173f35;
    }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Microsoft YaHei", "SimSun", sans-serif; background:#f6f1e8; color:var(--ink); }
    .layout { display:grid; grid-template-columns:390px 1fr; height:100vh; }
    aside { padding:16px; overflow:auto; background:var(--paper); border-right:1px solid var(--line); }
    #map { width:100%; height:100vh; }
    h1 { margin:0 0 8px; color:var(--green); font-size:24px; }
    h3 { margin:18px 0 8px; color:var(--green); }
    .hint { color:var(--muted); line-height:1.7; font-size:13px; margin-bottom:12px; }
    label { display:block; margin-top:10px; margin-bottom:5px; font-size:13px; font-weight:700; }
    select,input { width:100%; padding:8px; border:1px solid var(--line); border-radius:9px; background:#fff; }
    button { width:100%; margin-top:10px; padding:10px; border:0; border-radius:10px; background:var(--green); color:#fff; font-weight:700; cursor:pointer; }
    button.secondary { background:#6b5b43; }
    .metrics { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:12px 0; }
    .metric { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:10px; }
    .metric b { display:block; color:var(--green); font-size:20px; word-break:break-all; }
    .metric span { color:var(--muted); font-size:12px; }
    .legend,.row { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:10px; margin:8px 0; font-size:13px; line-height:1.6; }
    .row { cursor:pointer; }
    .row:hover { border-color:var(--green); }
    .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }
    .popup-title { font-weight:800; color:var(--green); margin-bottom:6px; }
    .popup-grid { display:grid; grid-template-columns:auto auto; gap:4px 12px; font-size:12px; }
    @media (max-width: 900px) {
      .layout { grid-template-columns:1fr; grid-template-rows:auto 65vh; height:auto; }
      aside { border-right:0; border-bottom:1px solid var(--line); }
      #map { height:65vh; }
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <h1>&#23458;&#25143;&#24211;&#23384;&#22320;&#29702;&#20998;&#26512;</h1>
      <div class="hint">
        &#22806;&#32593;&#22312;&#32447;&#24213;&#22270;&#29256;&#65306;&#22320;&#22270;&#29992; OpenStreetMap&#65292;&#19994;&#21153;&#25968;&#25454;&#24050;&#32463;&#20869;&#23884;&#21040;&#26412; HTML&#12290;<br>
        &#28857;&#22823;&#23567; = &#26399;&#26411;&#24211;&#23384;&#65307;&#39068;&#33394; = &#23384;&#38144;&#27604;&#12290;<br>
        &#24211;&#23384;&#21462;&#26399;&#38388;&#26368;&#21518;&#19968;&#22825;&#24555;&#29031;&#65307;&#38144;&#21806;&#21644;&#36141;&#36827;&#20026;&#26399;&#38388;&#32047;&#35745;&#12290;
      </div>
      <label>&#26085;&#26399;</label><select id="dateFilter"><option value="">&#20840;&#37096;</option></select>
      <label>&#26723;&#20301;</label><select id="segFilter"><option value="">&#20840;&#37096;</option></select>
      <label>&#26381;&#21153;&#31449;</label><select id="stationFilter"><option value="">&#20840;&#37096;</option></select>
      <label>&#23458;&#25143;&#32463;&#29702;</label><select id="managerFilter"><option value="">&#20840;&#37096;</option></select>
      <label>&#25628;&#32034;&#23458;&#25143;/&#24215;&#38138;/shop_id</label><input id="keyword" placeholder="&#20363;&#22914;&#65306;&#38271;&#22478;&#23486;&#39302;">
      <button id="apply">&#24212;&#29992;&#31579;&#36873;</button>
      <button id="reset" class="secondary">&#37325;&#32622;&#31579;&#36873;</button>
      <div class="metrics">
        <div class="metric"><b id="shopCount">0</b><span>&#23458;&#25143;&#25968;</span></div>
        <div class="metric"><b id="stockTotal">0</b><span>&#26399;&#26411;&#24211;&#23384;</span></div>
        <div class="metric"><b id="saleTotal">0</b><span>&#26399;&#38388;&#38144;&#21806;</span></div>
        <div class="metric"><b id="ratioAvg">0</b><span>&#24179;&#22343;&#23384;&#38144;&#27604;</span></div>
      </div>
      <div class="legend">
        <b>&#39068;&#33394;&#35828;&#26126;</b><br>
        <span class="dot" style="background:#16a34a"></span>&#23384;&#38144;&#27604; &lt; 3<br>
        <span class="dot" style="background:#eab308"></span>3 - 10<br>
        <span class="dot" style="background:#f97316"></span>10 - 20<br>
        <span class="dot" style="background:#dc2626"></span>20 - 50<br>
        <span class="dot" style="background:#991b1b"></span>&#8805; 50
      </div>
      <h3>&#26399;&#26411;&#24211;&#23384;&#26368;&#39640; Top 20</h3>
      <div id="topList"></div>
    </aside>
    <div id="map"></div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const GEO_DATA = __GEOJSON__;
    const allFeatures = GEO_DATA.features || [];
    const map = L.map('map', { preferCanvas:true }).setView([36.58, 116.25], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);
    const layer = L.layerGroup().addTo(map);
    const markerIndex = new Map();

    function num(v) {
      const n = Number(v);
      return Number.isFinite(n) ? n : 0;
    }
    function fmt(v, digits=2) {
      return num(v).toLocaleString('zh-CN', { maximumFractionDigits:digits });
    }
    function prop(f, name) {
      return (f.properties && f.properties[name] != null) ? f.properties[name] : '';
    }
    function colorByRatio(ratio) {
      if (!Number.isFinite(ratio)) return '#64748b';
      if (ratio < 3) return '#16a34a';
      if (ratio < 10) return '#eab308';
      if (ratio < 20) return '#f97316';
      if (ratio < 50) return '#dc2626';
      return '#991b1b';
    }
    function radiusByStock(stock) {
      const s = Math.max(num(stock), 0);
      return Math.max(5, Math.min(24, 4 + Math.sqrt(s) * 0.8));
    }
    function ratioOf(f) {
      const explicit = prop(f, 'stock_sale_ratio');
      if (explicit !== '' && explicit !== null && Number.isFinite(Number(explicit))) return Number(explicit);
      const sale = num(prop(f, 'sale_qty'));
      return sale > 0 ? num(prop(f, 'stock_qty')) / sale : null;
    }
    function uniqueValues(name) {
      return [...new Set(allFeatures.map(f => String(prop(f, name) || '').trim()).filter(Boolean))].sort();
    }
    function fillSelect(id, values) {
      const el = document.getElementById(id);
      for (const value of values) {
        const opt = document.createElement('option');
        opt.value = value;
        opt.textContent = value;
        el.appendChild(opt);
      }
    }
    function selected(id) { return document.getElementById(id).value.trim(); }
    function keyword() { return document.getElementById('keyword').value.trim().toLowerCase(); }
    function featureDate(f) { return String(prop(f, 'biz_date') || prop(f, 'period_end_date') || ''); }
    function filterFeatures() {
      const date = selected('dateFilter');
      const seg = selected('segFilter');
      const station = selected('stationFilter');
      const manager = selected('managerFilter');
      const kw = keyword();
      return allFeatures.filter(f => {
        const p = f.properties || {};
        if (date && featureDate(f) !== date) return false;
        if (seg && String(p.cust_seg_name || '') !== seg) return false;
        if (station && String(p.ss_name || '') !== station) return false;
        if (manager && String(p.slsman || '') !== manager) return false;
        if (kw) {
          const haystack = `${p.shop_id || ''} ${p.shop_name || ''} ${p.cust_name || ''} ${p.license_code || ''}`.toLowerCase();
          if (!haystack.includes(kw)) return false;
        }
        return true;
      });
    }
    function popupHtml(f) {
      const p = f.properties || {};
      const ratio = ratioOf(f);
      const ratioText = ratio == null ? '无销售' : fmt(ratio, 4);
      return `
        <div class="popup-title">${p.shop_name || p.cust_name || p.shop_id || '未知客户'}</div>
        <div class="popup-grid">
          <span>日期</span><b>${featureDate(f)}</b>
          <span>档位</span><b>${p.cust_seg_name || ''}</b>
          <span>服务站</span><b>${p.ss_name || ''}</b>
          <span>客户经理</span><b>${p.slsman || ''}</b>
          <span>期末库存</span><b>${fmt(p.stock_qty)}</b>
          <span>期间销售</span><b>${fmt(p.sale_qty)}</b>
          <span>期间购进</span><b>${fmt(p.order_qty)}</b>
          <span>存销比</span><b>${ratioText}</b>
        </div>`;
    }
    function render() {
      layer.clearLayers();
      markerIndex.clear();
      const features = filterFeatures();
      let stock = 0, sale = 0, ratioSum = 0, ratioN = 0;
      const bounds = [];
      for (const f of features) {
        const coords = f.geometry && f.geometry.coordinates;
        if (!coords || coords.length < 2) continue;
        const lng = Number(coords[0]);
        const lat = Number(coords[1]);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
        const p = f.properties || {};
        const ratio = ratioOf(f);
        const marker = L.circleMarker([lat, lng], {
          radius: radiusByStock(p.stock_qty),
          color: '#1f2937',
          weight: 1,
          fillColor: colorByRatio(ratio),
          fillOpacity: 0.72
        }).bindPopup(popupHtml(f));
        marker.addTo(layer);
        if (p.shop_id) markerIndex.set(String(p.shop_id), marker);
        bounds.push([lat, lng]);
        stock += num(p.stock_qty);
        sale += num(p.sale_qty);
        if (ratio != null && Number.isFinite(ratio)) {
          ratioSum += ratio;
          ratioN += 1;
        }
      }
      document.getElementById('shopCount').textContent = fmt(features.length, 0);
      document.getElementById('stockTotal').textContent = fmt(stock, 0);
      document.getElementById('saleTotal').textContent = fmt(sale, 0);
      document.getElementById('ratioAvg').textContent = ratioN ? fmt(ratioSum / ratioN, 2) : '0';
      renderTopList(features);
      if (bounds.length) map.fitBounds(bounds, { padding:[30, 30] });
    }
    function renderTopList(features) {
      const top = [...features].sort((a,b) => num(prop(b, 'stock_qty')) - num(prop(a, 'stock_qty'))).slice(0, 20);
      const box = document.getElementById('topList');
      box.innerHTML = '';
      for (const f of top) {
        const p = f.properties || {};
        const div = document.createElement('div');
        div.className = 'row';
        div.innerHTML = `<b>${p.shop_name || p.cust_name || p.shop_id || '未知客户'}</b><br>
          日期：${featureDate(f)} 档位：${p.cust_seg_name || ''}<br>
          库存：${fmt(p.stock_qty)} 销售：${fmt(p.sale_qty)} 存销比：${ratioOf(f) == null ? '无销售' : fmt(ratioOf(f), 3)}`;
        div.addEventListener('click', () => {
          const marker = markerIndex.get(String(p.shop_id || ''));
          if (marker) {
            map.setView(marker.getLatLng(), 15);
            marker.openPopup();
          }
        });
        box.appendChild(div);
      }
    }
    fillSelect('dateFilter', uniqueValues('biz_date').length ? uniqueValues('biz_date') : uniqueValues('period_end_date'));
    fillSelect('segFilter', uniqueValues('cust_seg_name'));
    fillSelect('stationFilter', uniqueValues('ss_name'));
    fillSelect('managerFilter', uniqueValues('slsman'));
    document.getElementById('apply').addEventListener('click', render);
    document.getElementById('reset').addEventListener('click', () => {
      for (const id of ['dateFilter', 'segFilter', 'stationFilter', 'managerFilter']) document.getElementById(id).value = '';
      document.getElementById('keyword').value = '';
      render();
    });
    render();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an online Leaflet HTML map with embedded GeoJSON.")
    parser.add_argument("--geojson", required=True, help="Input GeoJSON file.")
    parser.add_argument("--output", required=True, help="Output HTML file.")
    args = parser.parse_args()

    geojson_path = Path(args.geojson)
    output_path = Path(args.output)
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    html = HTML_TEMPLATE.replace("__GEOJSON__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
