(function () {
  const scenarios = {
    area: {
      eyebrow: "County View",
      title: "区县总览：先看整体库存压力",
      badge: "第一屏",
      panelTitle: "看板先给 4 个结论",
      bullets: [
        "二星 / 三星客户一共多少户。",
        "最新一天库存快照是多少。",
        "最近 7 天、30 天存销比是否偏高。",
        "异常客户有多少，主要集中在哪些小组。"
      ],
      usage: "先看全区总览，判断今天库存压力是否值得关注；如果压力偏高，再进入地图看集中区域。",
      table: "主要来自 rpt_area_terminal_daily_trend 和 rpt_customer_inventory_diagnosis。"
    },
    map: {
      eyebrow: "Spatial Diagnosis",
      title: "地图定位：看问题集中在哪些区域",
      badge: "地图主界面",
      panelTitle: "地图点位应该表达三件事",
      bullets: [
        "点大小表示最新库存，库存越高点越大。",
        "点颜色表示 30 天存销比或异常分，越红越需要关注。",
        "筛选小组、档位、城乡、商圈后，观察异常是否空间聚集。"
      ],
      usage: "地图不是为了好看，而是为了快速发现某个小组、乡镇、商圈是否出现集中压力。",
      table: "主要来自 rpt_customer_inventory_diagnosis，坐标来自 dim_customer_profile。"
    },
    peer: {
      eyebrow: "Peer Benchmark",
      title: "客户同类对比：判断这个客户是不是异常",
      badge: "钻取层",
      panelTitle: "同类对比建议看 5 个指标",
      bullets: [
        "客户最新库存 vs 同类平均库存。",
        "客户 30 天销售 vs 同类平均 30 天销售。",
        "客户 7 天、30 天存销比 vs 同类平均存销比。",
        "客户库存是否高，但销售是否低于同类。",
        "客户近期购进是否偏多，是否加重库存压力。"
      ],
      usage: "点击地图点或客户表行后，先看它和同类客户的差距，而不是只看绝对库存高低。",
      table: "主要来自 rpt_customer_inventory_diagnosis 和 rpt_customer_inventory_daily_trend。"
    },
    group: {
      eyebrow: "Group Deviation",
      title: "小组偏离：看客户结构和经营压力是否异常",
      badge: "管理层",
      panelTitle: "小组分析不要只排名，要解释结构",
      bullets: [
        "小组客户平均档位是多少，城网/农网比例如何。",
        "小组库存、销售、存销比与全区均值差多少。",
        "小组异常客户占比是否明显偏高。",
        "小组是否由少数高库存客户拉高压力。"
      ],
      usage: "小组分析适合做考核，但最好先解释客户结构差异，避免简单用总量排名误伤。",
      table: "主要来自 rpt_group_inventory_diagnosis 和 rpt_dimension_inventory_summary。"
    },
    action: {
      eyebrow: "Action List",
      title: "异常处置：把分析变成能执行的客户清单",
      badge: "落地层",
      panelTitle: "异常标签建议分 4 类",
      bullets: [
        "高库存低动销：库存高于同类，销售低于同类。",
        "有库存无销售：最新有库存，但近 7 天或 30 天销售很低。",
        "购进偏多且压力高：近期购进多，存销比仍偏高。",
        "长期压力客户：180 天基准下持续高于同类。"
      ],
      usage: "最后输出的不只是图，而是客户经理能拿去走访、核查、提醒、考核的名单。",
      table: "主要来自 rpt_customer_inventory_diagnosis，可导出 CSV 或后续做月报。"
    }
  };

  const $ = (id) => document.getElementById(id);

  function renderScenario(key) {
    const item = scenarios[key] || scenarios.area;
    $("scenarioEyebrow").textContent = item.eyebrow;
    $("scenarioTitle").textContent = item.title;
    $("scenarioBadge").textContent = item.badge;
    $("mockPanelTitle").textContent = item.panelTitle;
    $("mockBullets").innerHTML = item.bullets.map((text) => `<li>${text}</li>`).join("");
    $("usageText").textContent = item.usage;
    $("tableText").textContent = item.table;
    document.querySelectorAll(".scenario").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.scenario === key);
    });
  }

  document.querySelectorAll(".scenario").forEach((btn) => {
    btn.addEventListener("click", () => renderScenario(btn.dataset.scenario));
  });
})();
