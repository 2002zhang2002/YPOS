# 库存动销诊断页面

当前入口：

```text
dashboard.html   库存经营驾驶舱
inventory.html   库存趋势与客户明细
index.html       地图主界面
analysis.html    旧版趋势与表格分析
strategy.html    分析设计思路展示
```

数据文件：

```text
data/diagnosis_app_data.js
data/customer_trends/*.js
data/day_details/*.js
```

口径说明：

- 7天月化存销比 = 库存 / (近7天销量 / 7 * 30)。
- 日库存趋势展示 7 / 30 / 60 / 120 天均线，可在页面里开关。
- 趋势主轴默认只展示 2025 年至今；2024 年数据只作为同比背景，不进入主轴展示。
- 周期视图每 7 天取一次库存快照，展示今年 vs 去年同期，并计算同比差值和同比幅度。
- 点击库存图上的日期，会跳转到客户明细页，并按需加载当天客户明细分片。
