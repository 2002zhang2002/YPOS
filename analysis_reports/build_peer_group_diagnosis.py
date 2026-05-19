"""Build peer/group sell-through diagnosis data and static app payload.

The output is designed for file:// usage:
- MySQL report tables for reuse.
- CSV files for audit/export.
- stock_pressure_app/data/diagnosis_app_data.js for the local HTML app.
"""

import argparse
import csv
import datetime as dt
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pymysql
from pymysql.cursors import DictCursor


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "analysis_exports" / "peer_group"
APP_DATA_PATH = ROOT / "stock_pressure_app" / "data" / "diagnosis_app_data.js"


CUSTOMER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rpt_customer_peer_diagnosis (
  period_start_date DATE NOT NULL,
  period_end_date DATE NOT NULL,
  shop_id VARCHAR(64) NOT NULL,
  cust_id VARCHAR(64) NULL,
  cust_name VARCHAR(255) NULL,
  group_name VARCHAR(255) NULL,
  terminal_level VARCHAR(64) NULL,
  cust_seg_name VARCHAR(64) NULL,
  market_type VARCHAR(64) NULL,
  work_port_name VARCHAR(64) NULL,
  business_area_type VARCHAR(128) NULL,
  base_type_name VARCHAR(128) NULL,
  ss_name VARCHAR(128) NULL,
  slsman VARCHAR(128) NULL,
  longitude DECIMAL(12,8) NULL,
  latitude DECIMAL(12,8) NULL,
  days_with_data INT NOT NULL DEFAULT 0,
  active_days INT NOT NULL DEFAULT 0,
  active_rate DECIMAL(18,6) NULL,
  end_stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  stock_sale_ratio_7d DECIMAL(18,6) NULL,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  peer_key VARCHAR(255) NOT NULL,
  peer_customer_count INT NOT NULL DEFAULT 0,
  peer_avg_stock_qty DECIMAL(18,4) NULL,
  peer_avg_sale_qty_30d DECIMAL(18,4) NULL,
  peer_avg_ratio_30d DECIMAL(18,6) NULL,
  stock_peer_multiple DECIMAL(18,6) NULL,
  sale_peer_multiple DECIMAL(18,6) NULL,
  ratio_peer_multiple DECIMAL(18,6) NULL,
  abnormal_tag VARCHAR(255) NULL,
  abnormal_score DECIMAL(18,4) NOT NULL DEFAULT 0,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (period_start_date, period_end_date, shop_id),
  KEY idx_peer_diag_group (period_end_date, group_name, abnormal_score),
  KEY idx_peer_diag_peer (period_end_date, peer_key),
  KEY idx_peer_diag_ratio (period_end_date, stock_sale_ratio_30d)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户同类对比动销诊断表'
"""


GROUP_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rpt_group_expected_actual (
  period_start_date DATE NOT NULL,
  period_end_date DATE NOT NULL,
  group_name VARCHAR(255) NOT NULL,
  customer_count INT NOT NULL DEFAULT 0,
  active_customer_count INT NOT NULL DEFAULT 0,
  active_rate DECIMAL(18,6) NULL,
  avg_cust_seg DECIMAL(18,4) NULL,
  city_customer_pct DECIMAL(18,6) NULL,
  rural_customer_pct DECIMAL(18,6) NULL,
  terminal_2star_pct DECIMAL(18,6) NULL,
  terminal_3star_pct DECIMAL(18,6) NULL,
  actual_stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  expected_stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  actual_sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  expected_sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  actual_ratio_30d DECIMAL(18,6) NULL,
  expected_ratio_30d DECIMAL(18,6) NULL,
  sale_achievement DECIMAL(18,6) NULL,
  stock_deviation DECIMAL(18,6) NULL,
  ratio_deviation DECIMAL(18,6) NULL,
  abnormal_customer_count INT NOT NULL DEFAULT 0,
  abnormal_customer_pct DECIMAL(18,6) NULL,
  group_score DECIMAL(18,4) NULL,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (period_start_date, period_end_date, group_name),
  KEY idx_group_score (period_end_date, group_score),
  KEY idx_group_abnormal (period_end_date, abnormal_customer_pct)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='小组结构与实际理论表现对比表'
"""


TREND_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rpt_area_terminal_trend (
  biz_date DATE NOT NULL,
  stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  stock_sale_ratio_7d DECIMAL(18,6) NULL,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  active_customer_count INT NOT NULL DEFAULT 0,
  customer_count INT NOT NULL DEFAULT 0,
  active_rate DECIMAL(18,6) NULL,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='茌平区二星三星累计库存与存销比趋势表'
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build customer peer/group diagnosis reports.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="pos_ods")
    parser.add_argument("--charset", default="utf8mb4")
    parser.add_argument("--start-date", default="", help="YYYY-MM-DD or YYYYMMDD. Defaults to latest-29 days.")
    parser.add_argument("--end-date", default="", help="YYYY-MM-DD or YYYYMMDD. Defaults to latest fact date.")
    parser.add_argument("--levels", default="二星,三星")
    parser.add_argument("--export-dir", default=str(EXPORT_DIR))
    parser.add_argument("--app-data", default=str(APP_DATA_PATH))
    return parser.parse_args()


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def safe_div(a: Decimal, b: Decimal):
    if b == 0:
        return None
    return a / b


def q(value, places="0.000001"):
    if value is None:
        return None
    return dec(value).quantize(Decimal(places))


def to_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def connect(args):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset=args.charset,
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10,
    )


def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute(CUSTOMER_TABLE_SQL)
        cur.execute(GROUP_TABLE_SQL)
        cur.execute(TREND_TABLE_SQL)
    conn.commit()


def table_columns(conn, table: str):
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        return {row["Field"] for row in cur.fetchall()}


def dim_expr(cols, standard: str, legacy: str = "", fallback: str = "NULL") -> str:
    parts = []
    if standard in cols:
        parts.append(f"NULLIF(d.`{standard}`, '')")
    if legacy and legacy in cols:
        parts.append(f"NULLIF(d.`{legacy}`, '')")
    parts.append(fallback)
    return "COALESCE(" + ", ".join(parts) + ")"


def resolve_date_range(conn, start_text: str, end_text: str):
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(biz_date) AS min_date, MAX(biz_date) AS max_date FROM fact_customer_shop_daily")
        row = cur.fetchone()
    if not row or not row["max_date"]:
        raise RuntimeError("fact_customer_shop_daily has no data")
    end = dt.date.fromisoformat(end_text) if end_text else row["max_date"]
    start = dt.date.fromisoformat(start_text) if start_text else max(row["min_date"], end - dt.timedelta(days=29))
    return start, end


def build_fact_query(conn, levels: List[str]) -> str:
    cols = table_columns(conn, "dim_customer_profile")

    def c(name: str):
        return f"d.`{name}`" if name in cols else "NULL"

    terminal_level = dim_expr(cols, "terminal_level", "terminalLevel")
    join_condition = (
        f"{c('license_code')} = f.shop_id OR {c('licenseNo')} = f.shop_id "
        f"OR {c('shop_id')} = f.shop_id OR {c('cust_id')} = f.cust_id OR {c('custId')} = f.cust_id"
    )
    level_placeholders = ", ".join(["%s"] * len(levels))
    missing_text = "'未填'"
    cust_id_expr = dim_expr(cols, "cust_id", "custId")
    cust_name_expr = dim_expr(cols, "cust_name", "custName", "f.shop_name")
    cust_seg_expr = dim_expr(cols, "cust_seg_name", "customerSegment", "f.cust_seg_name")
    market_expr = dim_expr(cols, "market_type", "marketType", missing_text)
    work_port_expr = dim_expr(cols, "work_port_name", "urbanRuralCategory", "f.work_port_name")
    business_area_expr = dim_expr(cols, "business_area_type", "businessCircleType", missing_text)
    group_expr = dim_expr(cols, "group_name", "belongingGroup", missing_text)
    base_type_expr = dim_expr(cols, "base_type_name", "businessType", "f.base_type_name")
    return f"""
      SELECT
        f.biz_date,
        f.shop_id,
        COALESCE(NULLIF(f.cust_id, ''), {cust_id_expr}) AS cust_id,
        {cust_name_expr} AS cust_name,
        {terminal_level} AS terminal_level,
        {cust_seg_expr} AS cust_seg_name,
        {market_expr} AS market_type,
        {work_port_expr} AS work_port_name,
        {business_area_expr} AS business_area_type,
        {group_expr} AS group_name,
        {base_type_expr} AS base_type_name,
        f.ss_name,
        f.slsman,
        {c('longitude')} AS longitude,
        {c('latitude')} AS latitude,
        COALESCE(f.t_big_stoamt, 0) AS stock_qty,
        COALESCE(f.t_big_saleamt, 0) AS sale_qty,
        COALESCE(f.t_big_stockamt, 0) AS purchase_qty
      FROM fact_customer_shop_daily f
      JOIN dim_customer_profile d
        ON {join_condition}
      WHERE f.biz_date BETWEEN %s AND %s
        AND {terminal_level} IN ({level_placeholders})
    """


def fetch_rows(conn, start: dt.date, end: dt.date, levels: List[str]):
    pre_start = start - dt.timedelta(days=29)
    sql = build_fact_query(conn, levels)
    with conn.cursor() as cur:
        cur.execute(sql, [pre_start, end] + levels)
        rows = cur.fetchall()
    return rows, pre_start


def date_iter(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def seg_number(value: str):
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return Decimal(digits) if digits else None


def build_customer_latest(rows, start: dt.date, end: dt.date):
    by_shop = defaultdict(list)
    for row in rows:
        by_shop[str(row["shop_id"])].append(row)
    customers = []
    for shop_id, items in by_shop.items():
        items.sort(key=lambda r: r["biz_date"])
        in_period = [r for r in items if start <= r["biz_date"] <= end]
        if not in_period:
            continue
        latest = in_period[-1]
        sale_7_start = end - dt.timedelta(days=6)
        sale_30_start = end - dt.timedelta(days=29)
        sale_7 = sum(dec(r["sale_qty"]) for r in items if sale_7_start <= r["biz_date"] <= end)
        sale_30 = sum(dec(r["sale_qty"]) for r in items if sale_30_start <= r["biz_date"] <= end)
        purchase_7 = sum(dec(r["purchase_qty"]) for r in items if sale_7_start <= r["biz_date"] <= end)
        purchase_30 = sum(dec(r["purchase_qty"]) for r in items if sale_30_start <= r["biz_date"] <= end)
        active_days = sum(1 for r in in_period if dec(r["sale_qty"]) > 0)
        days_with_data = len({r["biz_date"] for r in in_period})
        stock = dec(latest["stock_qty"])
        customer = {
            "period_start_date": start,
            "period_end_date": end,
            "shop_id": shop_id,
            "cust_id": latest.get("cust_id"),
            "cust_name": latest.get("cust_name") or latest.get("shop_name") or shop_id,
            "group_name": latest.get("group_name") or "未填",
            "terminal_level": latest.get("terminal_level") or "未填",
            "cust_seg_name": latest.get("cust_seg_name") or "未填",
            "market_type": latest.get("market_type") or "未填",
            "work_port_name": latest.get("work_port_name") or "未填",
            "business_area_type": latest.get("business_area_type") or "未填",
            "base_type_name": latest.get("base_type_name") or "未填",
            "ss_name": latest.get("ss_name") or "未填",
            "slsman": latest.get("slsman") or "未填",
            "longitude": latest.get("longitude"),
            "latitude": latest.get("latitude"),
            "days_with_data": days_with_data,
            "active_days": active_days,
            "active_rate": q(safe_div(Decimal(active_days), Decimal(days_with_data))),
            "end_stock_qty": stock,
            "sale_qty_7d": sale_7,
            "sale_qty_30d": sale_30,
            "purchase_qty_7d": purchase_7,
            "purchase_qty_30d": purchase_30,
            "stock_sale_ratio_7d": q(safe_div(stock, sale_7)),
            "stock_sale_ratio_30d": q(safe_div(stock, sale_30)),
        }
        customer["peer_key"] = "|".join(
            [
                str(customer["market_type"]),
                str(customer["cust_seg_name"]),
                str(customer["business_area_type"]),
                str(customer["base_type_name"]),
            ]
        )
        customers.append(customer)
    return customers


def avg(values: List[Decimal]):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals, Decimal("0")) / Decimal(len(vals))


def enrich_peer_metrics(customers: List[Dict]):
    peers = defaultdict(list)
    for c in customers:
        peers[c["peer_key"]].append(c)
    for c in customers:
        group = peers[c["peer_key"]]
        peer_avg_stock = avg([dec(x["end_stock_qty"]) for x in group])
        peer_avg_sale = avg([dec(x["sale_qty_30d"]) for x in group])
        peer_ratios = [x["stock_sale_ratio_30d"] for x in group if x["stock_sale_ratio_30d"] is not None]
        peer_avg_ratio = avg([dec(x) for x in peer_ratios])
        c["peer_customer_count"] = len(group)
        c["peer_avg_stock_qty"] = q(peer_avg_stock, "0.0001")
        c["peer_avg_sale_qty_30d"] = q(peer_avg_sale, "0.0001")
        c["peer_avg_ratio_30d"] = q(peer_avg_ratio)
        c["stock_peer_multiple"] = q(safe_div(dec(c["end_stock_qty"]), peer_avg_stock or Decimal("0")))
        c["sale_peer_multiple"] = q(safe_div(dec(c["sale_qty_30d"]), peer_avg_sale or Decimal("0")))
        c["ratio_peer_multiple"] = q(safe_div(dec(c["stock_sale_ratio_30d"] or 0), peer_avg_ratio or Decimal("0")))
        tags = []
        score = Decimal("0")
        if c["sale_qty_30d"] == 0 and c["end_stock_qty"] > 0:
            tags.append("有库存无销售")
            score += Decimal("40")
        if (c["stock_peer_multiple"] or 0) >= Decimal("1.5") and (c["sale_peer_multiple"] or 0) <= Decimal("0.6"):
            tags.append("同类中高库存低动销")
            score += Decimal("30")
        if (c["stock_sale_ratio_30d"] or 0) >= Decimal("25"):
            tags.append("30天存销比偏高")
            score += Decimal("20")
        if c["purchase_qty_30d"] > 0 and c["sale_qty_30d"] > 0:
            ps = c["purchase_qty_30d"] / c["sale_qty_30d"]
            if ps >= Decimal("1.5") and (c["stock_sale_ratio_30d"] or 0) >= Decimal("15"):
                tags.append("购进偏多且库存压力高")
                score += Decimal("10")
        c["abnormal_tag"] = "、".join(tags) if tags else "正常"
        c["abnormal_score"] = score


def build_group_reports(customers: List[Dict]):
    peer_expected = defaultdict(lambda: {"stock": [], "sale": [], "ratio": []})
    for c in customers:
        peer_expected[c["peer_key"]]["stock"].append(dec(c["end_stock_qty"]))
        peer_expected[c["peer_key"]]["sale"].append(dec(c["sale_qty_30d"]))
        if c["stock_sale_ratio_30d"] is not None:
            peer_expected[c["peer_key"]]["ratio"].append(dec(c["stock_sale_ratio_30d"]))
    peer_avg = {
        key: {
            "stock": avg(value["stock"]) or Decimal("0"),
            "sale": avg(value["sale"]) or Decimal("0"),
            "ratio": avg(value["ratio"]) or Decimal("0"),
        }
        for key, value in peer_expected.items()
    }
    groups = defaultdict(list)
    for c in customers:
        groups[c["group_name"] or "未填"].append(c)
    reports = []
    for group_name, items in groups.items():
        customer_count = len(items)
        active_count = sum(1 for c in items if c["sale_qty_30d"] > 0)
        stock = sum(dec(c["end_stock_qty"]) for c in items)
        sale = sum(dec(c["sale_qty_30d"]) for c in items)
        expected_stock = sum(peer_avg[c["peer_key"]]["stock"] for c in items)
        expected_sale = sum(peer_avg[c["peer_key"]]["sale"] for c in items)
        ratio = safe_div(stock, sale)
        expected_ratio = safe_div(expected_stock, expected_sale)
        seg_values = [seg_number(c["cust_seg_name"]) for c in items]
        seg_values = [v for v in seg_values if v is not None]
        abnormal_count = sum(1 for c in items if c["abnormal_tag"] != "正常")
        sale_achievement = safe_div(sale, expected_sale)
        stock_deviation = safe_div(stock, expected_stock)
        ratio_deviation = safe_div(ratio or Decimal("0"), expected_ratio or Decimal("0"))
        score = Decimal("100")
        if sale_achievement is not None:
            score -= max(Decimal("0"), Decimal("1") - sale_achievement) * Decimal("35")
        if ratio_deviation is not None:
            score -= max(Decimal("0"), ratio_deviation - Decimal("1")) * Decimal("20")
        score -= safe_div(Decimal(abnormal_count), Decimal(customer_count)) * Decimal("25")
        report = {
            "period_start_date": items[0]["period_start_date"],
            "period_end_date": items[0]["period_end_date"],
            "group_name": group_name,
            "customer_count": customer_count,
            "active_customer_count": active_count,
            "active_rate": q(safe_div(Decimal(active_count), Decimal(customer_count))),
            "avg_cust_seg": q(avg(seg_values), "0.0001") if seg_values else None,
            "city_customer_pct": q(safe_div(Decimal(sum(1 for c in items if c["market_type"] == "城网")), Decimal(customer_count))),
            "rural_customer_pct": q(safe_div(Decimal(sum(1 for c in items if c["market_type"] == "农网")), Decimal(customer_count))),
            "terminal_2star_pct": q(safe_div(Decimal(sum(1 for c in items if c["terminal_level"] == "二星")), Decimal(customer_count))),
            "terminal_3star_pct": q(safe_div(Decimal(sum(1 for c in items if c["terminal_level"] == "三星")), Decimal(customer_count))),
            "actual_stock_qty": stock,
            "expected_stock_qty": expected_stock,
            "actual_sale_qty_30d": sale,
            "expected_sale_qty_30d": expected_sale,
            "actual_ratio_30d": q(ratio),
            "expected_ratio_30d": q(expected_ratio),
            "sale_achievement": q(sale_achievement),
            "stock_deviation": q(stock_deviation),
            "ratio_deviation": q(ratio_deviation),
            "abnormal_customer_count": abnormal_count,
            "abnormal_customer_pct": q(safe_div(Decimal(abnormal_count), Decimal(customer_count))),
            "group_score": max(Decimal("0"), q(score, "0.0001") or Decimal("0")),
        }
        reports.append(report)
    return sorted(reports, key=lambda r: (r["group_score"] or Decimal("0"), -r["abnormal_customer_count"]))


def build_dimension_summary(customers: List[Dict]):
    rows = []
    for dim in ["cust_seg_name", "market_type", "work_port_name", "business_area_type", "group_name", "base_type_name", "terminal_level"]:
        buckets = defaultdict(list)
        for c in customers:
            buckets[c.get(dim) or "未填"].append(c)
        for value, items in buckets.items():
            stock = sum(dec(c["end_stock_qty"]) for c in items)
            sale = sum(dec(c["sale_qty_30d"]) for c in items)
            abnormal = sum(1 for c in items if c["abnormal_tag"] != "正常")
            rows.append(
                {
                    "dimension_type": dim,
                    "dimension_value": value,
                    "customer_count": len(items),
                    "active_customer_count": sum(1 for c in items if c["sale_qty_30d"] > 0),
                    "stock_qty": stock,
                    "sale_qty_30d": sale,
                    "stock_sale_ratio_30d": q(safe_div(stock, sale)),
                    "abnormal_customer_count": abnormal,
                    "abnormal_customer_pct": q(safe_div(Decimal(abnormal), Decimal(len(items)))),
                }
            )
    return rows


def build_area_trend(rows: List[Dict], start: dt.date, end: dt.date):
    by_date = defaultdict(lambda: {"shops": set(), "active": set(), "stock": Decimal("0"), "sale": Decimal("0"), "purchase": Decimal("0")})
    for row in rows:
        if not (start - dt.timedelta(days=29) <= row["biz_date"] <= end):
            continue
        d = row["biz_date"]
        shop_id = str(row["shop_id"])
        by_date[d]["shops"].add(shop_id)
        if dec(row["sale_qty"]) > 0:
            by_date[d]["active"].add(shop_id)
        by_date[d]["stock"] += dec(row["stock_qty"])
        by_date[d]["sale"] += dec(row["sale_qty"])
        by_date[d]["purchase"] += dec(row["purchase_qty"])
    trend = []
    all_dates = list(date_iter(start - dt.timedelta(days=29), end))
    for d in date_iter(start, end):
        last_7 = [x for x in all_dates if d - dt.timedelta(days=6) <= x <= d]
        last_30 = [x for x in all_dates if d - dt.timedelta(days=29) <= x <= d]
        sale_7 = sum(by_date[x]["sale"] for x in last_7)
        sale_30 = sum(by_date[x]["sale"] for x in last_30)
        item = by_date[d]
        customer_count = len(item["shops"])
        active_count = len(item["active"])
        trend.append(
            {
                "biz_date": d,
                "stock_qty": item["stock"],
                "sale_qty": item["sale"],
                "purchase_qty": item["purchase"],
                "sale_qty_7d": sale_7,
                "sale_qty_30d": sale_30,
                "stock_sale_ratio_7d": q(safe_div(item["stock"], sale_7)),
                "stock_sale_ratio_30d": q(safe_div(item["stock"], sale_30)),
                "active_customer_count": active_count,
                "customer_count": customer_count,
                "active_rate": q(safe_div(Decimal(active_count), Decimal(customer_count))) if customer_count else None,
            }
        )
    return trend


def write_mysql(conn, table: str, rows: List[Dict], start: dt.date, end: dt.date):
    if not rows:
        return 0
    columns = list(rows[0].keys())
    with conn.cursor() as cur:
        if "period_start_date" in columns:
            cur.execute(f"DELETE FROM `{table}` WHERE period_start_date=%s AND period_end_date=%s", (start, end))
        else:
            cur.execute(f"DELETE FROM `{table}` WHERE biz_date BETWEEN %s AND %s", (start, end))
        placeholders = ", ".join(["%s"] * len(columns))
        col_sql = ", ".join(f"`{c}`" for c in columns)
        sql = f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})"
        cur.executemany(sql, [tuple(r[c] for c in columns) for r in rows])
    conn.commit()
    return len(rows)


def write_csv(path: Path, rows: List[Dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: to_float(v) for k, v in row.items()})


def small_rows(rows: List[Dict], limit: int):
    return [{k: to_float(v) for k, v in row.items()} for row in rows[:limit]]


def write_app_data(path: Path, payload: Dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "window.DIAGNOSIS_APP_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    levels = [x.strip() for x in args.levels.split(",") if x.strip()]
    start_text = normalize_date(args.start_date)
    end_text = normalize_date(args.end_date)
    export_dir = Path(args.export_dir)
    app_data_path = Path(args.app_data)

    with connect(args) as conn:
        ensure_tables(conn)
        start, end = resolve_date_range(conn, start_text, end_text)
        rows, _ = fetch_rows(conn, start, end, levels)
        customers = build_customer_latest(rows, start, end)
        enrich_peer_metrics(customers)
        groups = build_group_reports(customers)
        dimensions = build_dimension_summary(customers)
        trend = build_area_trend(rows, start, end)

        write_mysql(conn, "rpt_customer_peer_diagnosis", customers, start, end)
        write_mysql(conn, "rpt_group_expected_actual", groups, start, end)
        write_mysql(conn, "rpt_area_terminal_trend", trend, start, end)

    write_csv(export_dir / "rpt_customer_peer_diagnosis.csv", customers)
    write_csv(export_dir / "rpt_group_expected_actual.csv", groups)
    write_csv(export_dir / "rpt_dimension_activity_summary.csv", dimensions)
    write_csv(export_dir / "rpt_area_terminal_trend.csv", trend)

    abnormal_customers = sorted(customers, key=lambda x: (-dec(x["abnormal_score"]), -(x["stock_sale_ratio_30d"] or 0), -dec(x["end_stock_qty"])))
    payload = {
        "generatedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "periodStart": start.isoformat(),
        "periodEnd": end.isoformat(),
        "levels": levels,
        "summary": {
            "customerCount": len(customers),
            "stockQty": to_float(sum(dec(c["end_stock_qty"]) for c in customers)),
            "saleQty30d": to_float(sum(dec(c["sale_qty_30d"]) for c in customers)),
            "ratio30d": to_float(safe_div(sum(dec(c["end_stock_qty"]) for c in customers), sum(dec(c["sale_qty_30d"]) for c in customers))),
            "abnormalCustomerCount": sum(1 for c in customers if c["abnormal_tag"] != "正常"),
        },
        "trendRows": small_rows(trend, 5000),
        "groupRows": small_rows(groups, 2000),
        "dimensionRows": small_rows(dimensions, 5000),
        "customerRows": small_rows(sorted(customers, key=lambda x: (-dec(x["end_stock_qty"]), str(x["cust_name"]))), 5000),
        "abnormalRows": small_rows(abnormal_customers, 2000),
    }
    write_app_data(app_data_path, payload)

    print(f"period={start}..{end}")
    print(f"fact_rows_loaded={len(rows)}")
    print(f"customers={len(customers)} groups={len(groups)} dimensions={len(dimensions)} trend_days={len(trend)}")
    print(f"exports={export_dir}")
    print(f"app_data={app_data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
