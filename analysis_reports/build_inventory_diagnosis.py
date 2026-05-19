"""Build inventory and sell-through diagnosis reports for 2-star/3-star terminals.

Design:
- Area trend: every available day in the selected trend range.
- Area weekly ratio: one point every 7 days, based on rolling 7-day sales.
- Customer current status: latest day + rolling 7-day/30-day sales ratios.
- Abnormal diagnosis: uses a long baseline, default 180 days, for peer comparison.
- Customer daily trend: every customer's daily stock, sale, 7d/30d ratio.

The script writes MySQL tables, CSV files, and a static JS payload for
stock_pressure_app/index.html.
"""

import argparse
import csv
import datetime as dt
import json
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pymysql
from pymysql.cursors import DictCursor


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "analysis_exports" / "inventory_diagnosis"
APP_DATA_PATH = ROOT / "stock_pressure_app" / "data" / "diagnosis_app_data.js"
CUSTOMER_TREND_DIR = ROOT / "stock_pressure_app" / "data" / "customer_trends"
DAY_DETAIL_DIR = ROOT / "stock_pressure_app" / "data" / "day_details"
MISSING = "未填"
NORMAL = "正常"


CREATE_AREA_TREND_SQL = """
CREATE TABLE IF NOT EXISTS rpt_area_terminal_daily_trend (
  biz_date DATE NOT NULL,
  customer_count INT NOT NULL DEFAULT 0,
  active_customer_count INT NOT NULL DEFAULT 0,
  active_rate DECIMAL(18,6) NULL,
  stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  stock_sale_ratio_7d DECIMAL(18,6) NULL,
  stock_sale_ratio_7d_monthly DECIMAL(18,6) NULL,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  stock_ma_7 DECIMAL(18,4) NULL,
  stock_ma_30 DECIMAL(18,4) NULL,
  stock_ma_60 DECIMAL(18,4) NULL,
  stock_ma_120 DECIMAL(18,4) NULL,
  is_weekly_point TINYINT NOT NULL DEFAULT 0,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='茌平区二星三星终端每日库存与存销比趋势表'
"""


CREATE_CUSTOMER_TREND_SQL = """
CREATE TABLE IF NOT EXISTS rpt_customer_inventory_daily_trend (
  biz_date DATE NOT NULL,
  shop_id VARCHAR(64) NOT NULL,
  cust_id VARCHAR(64) NULL,
  cust_name VARCHAR(255) NULL,
  license_no VARCHAR(64) NULL,
  group_name VARCHAR(255) NULL,
  terminal_level VARCHAR(64) NULL,
  cust_seg_name VARCHAR(64) NULL,
  market_type VARCHAR(64) NULL,
  work_port_name VARCHAR(64) NULL,
  business_area_type VARCHAR(128) NULL,
  base_type_name VARCHAR(128) NULL,
  stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  stock_sale_ratio_7d DECIMAL(18,6) NULL,
  stock_sale_ratio_7d_monthly DECIMAL(18,6) NULL,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date, shop_id),
  KEY idx_customer_trend_shop (shop_id, biz_date),
  KEY idx_customer_trend_ratio (biz_date, stock_sale_ratio_30d)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户每日库存与7天30天存销比趋势表'
"""


CREATE_CUSTOMER_DIAG_SQL = """
CREATE TABLE IF NOT EXISTS rpt_customer_inventory_diagnosis (
  as_of_date DATE NOT NULL,
  baseline_start_date DATE NOT NULL,
  baseline_days INT NOT NULL,
  shop_id VARCHAR(64) NOT NULL,
  cust_id VARCHAR(64) NULL,
  cust_name VARCHAR(255) NULL,
  license_no VARCHAR(64) NULL,
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
  stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0,
  purchase_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  stock_sale_ratio_7d DECIMAL(18,6) NULL,
  stock_sale_ratio_7d_monthly DECIMAL(18,6) NULL,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  baseline_avg_stock_qty DECIMAL(18,4) NULL,
  baseline_30d_sale_qty DECIMAL(18,4) NULL,
  baseline_ratio_30d DECIMAL(18,6) NULL,
  peer_key VARCHAR(255) NOT NULL,
  peer_customer_count INT NOT NULL DEFAULT 0,
  peer_avg_stock_qty DECIMAL(18,4) NULL,
  peer_avg_30d_sale_qty DECIMAL(18,4) NULL,
  peer_avg_ratio_30d DECIMAL(18,6) NULL,
  stock_peer_multiple DECIMAL(18,6) NULL,
  sale_peer_multiple DECIMAL(18,6) NULL,
  ratio_peer_multiple DECIMAL(18,6) NULL,
  abnormal_tag VARCHAR(255) NULL,
  abnormal_score DECIMAL(18,4) NOT NULL DEFAULT 0,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (as_of_date, shop_id),
  KEY idx_inventory_diag_group (as_of_date, group_name, abnormal_score),
  KEY idx_inventory_diag_peer (as_of_date, peer_key),
  KEY idx_inventory_diag_ratio (as_of_date, stock_sale_ratio_30d)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户库存动销诊断表，异常基准默认180天'
"""


CREATE_GROUP_SQL = """
CREATE TABLE IF NOT EXISTS rpt_group_inventory_diagnosis (
  as_of_date DATE NOT NULL,
  group_name VARCHAR(255) NOT NULL,
  customer_count INT NOT NULL DEFAULT 0,
  active_customer_count INT NOT NULL DEFAULT 0,
  active_rate DECIMAL(18,6) NULL,
  avg_cust_seg DECIMAL(18,4) NULL,
  city_customer_pct DECIMAL(18,6) NULL,
  rural_customer_pct DECIMAL(18,6) NULL,
  stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  expected_30d_sale_qty DECIMAL(18,4) NULL,
  sale_achievement DECIMAL(18,6) NULL,
  abnormal_customer_count INT NOT NULL DEFAULT 0,
  abnormal_customer_pct DECIMAL(18,6) NULL,
  group_score DECIMAL(18,4) NULL,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (as_of_date, group_name),
  KEY idx_group_inventory_score (as_of_date, group_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='小组库存动销诊断表'
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build inventory diagnosis reports.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="pos_ods")
    parser.add_argument("--charset", default="utf8mb4")
    parser.add_argument("--end-date", default="", help="YYYY-MM-DD or YYYYMMDD. Defaults to latest fact date.")
    parser.add_argument("--trend-start-date", default="", help="Daily trend start. Defaults to earliest fact date.")
    parser.add_argument("--baseline-days", type=int, default=180, help="Minimum long baseline days for abnormal judgement.")
    parser.add_argument("--levels", default="二星,三星")
    parser.add_argument("--export-dir", default=str(EXPORT_DIR))
    parser.add_argument("--app-data", default=str(APP_DATA_PATH))
    parser.add_argument("--customer-trend-dir", default=str(CUSTOMER_TREND_DIR))
    parser.add_argument("--day-detail-dir", default=str(DAY_DETAIL_DIR))
    parser.add_argument("--app-customer-limit", type=int, default=5000)
    return parser.parse_args()


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def decimal_or_zero(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def safe_div(a: Decimal, b: Decimal) -> Optional[Decimal]:
    if b == 0:
        return None
    return a / b


def quant(value: Optional[Decimal], places: str = "0.000001") -> Optional[Decimal]:
    if value is None:
        return None
    return decimal_or_zero(value).quantize(Decimal(places))


def monthly_7d_ratio(stock: Decimal, sale_7d: Decimal) -> Optional[Decimal]:
    monthly_sale = safe_div(sale_7d, Decimal("7"))
    if monthly_sale is None:
        return None
    monthly_sale *= Decimal("30")
    return safe_div(stock, monthly_sale)


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def connect(args: argparse.Namespace):
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


def table_columns(conn, table_name: str) -> set:
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
        return {row["Field"] for row in cur.fetchall()}


def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_AREA_TREND_SQL)
        cur.execute(CREATE_CUSTOMER_TREND_SQL)
        cur.execute(CREATE_CUSTOMER_DIAG_SQL)
        cur.execute(CREATE_GROUP_SQL)
        ensure_columns(cur, "rpt_area_terminal_daily_trend", {
            "stock_sale_ratio_7d_monthly": "DECIMAL(18,6) NULL AFTER stock_sale_ratio_7d",
            "stock_ma_7": "DECIMAL(18,4) NULL AFTER stock_sale_ratio_30d",
            "stock_ma_30": "DECIMAL(18,4) NULL AFTER stock_ma_7",
            "stock_ma_60": "DECIMAL(18,4) NULL AFTER stock_ma_30",
            "stock_ma_120": "DECIMAL(18,4) NULL AFTER stock_ma_60",
        })
        ensure_columns(cur, "rpt_customer_inventory_daily_trend", {
            "license_no": "VARCHAR(64) NULL AFTER cust_name",
            "purchase_qty_7d": "DECIMAL(18,4) NOT NULL DEFAULT 0 AFTER purchase_qty",
            "stock_sale_ratio_7d_monthly": "DECIMAL(18,6) NULL AFTER stock_sale_ratio_7d",
        })
        ensure_columns(cur, "rpt_customer_inventory_diagnosis", {
            "license_no": "VARCHAR(64) NULL AFTER cust_name",
            "stock_sale_ratio_7d_monthly": "DECIMAL(18,6) NULL AFTER stock_sale_ratio_7d",
        })
    conn.commit()


def ensure_columns(cur, table_name: str, columns: Dict[str, str]):
    cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
    existing = {row["Field"] for row in cur.fetchall()}
    for column, definition in columns.items():
        if column not in existing:
            cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column}` {definition}")


def first_existing(row: Dict, names: List[str], default=MISSING):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return default


def load_customer_dim(conn) -> Dict[str, Dict]:
    cols = table_columns(conn, "dim_customer_profile")
    fields = [f"`{name}`" for name in cols]
    sql = f"SELECT {', '.join(fields)} FROM dim_customer_profile"
    maps = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            dim = {
                "cust_id": first_existing(row, ["cust_id", "custId"], ""),
                "license_code": first_existing(row, ["license_code", "licenseNo", "license_no"], ""),
                "license_no": first_existing(row, ["license_no", "license_code", "licenseNo"], ""),
                "shop_id": first_existing(row, ["shop_id"], ""),
                "cust_name": first_existing(row, ["cust_name", "custName"], ""),
                "group_name": first_existing(row, ["group_name", "belongingGroup"]),
                "terminal_level": first_existing(row, ["terminal_level", "terminalLevel"]),
                "cust_seg_name": first_existing(row, ["cust_seg_name", "customerSegment"]),
                "market_type": first_existing(row, ["market_type", "marketType"]),
                "work_port_name": first_existing(row, ["work_port_name", "urbanRuralCategory"]),
                "business_area_type": first_existing(row, ["business_area_type", "businessCircleType"]),
                "base_type_name": first_existing(row, ["base_type_name", "businessType"]),
                "longitude": first_existing(row, ["longitude"], None),
                "latitude": first_existing(row, ["latitude"], None),
            }
            for key in [dim["license_code"], dim["shop_id"], dim["cust_id"]]:
                if key:
                    maps[str(key)] = dim
    return maps


def fact_date_range(conn) -> Tuple[dt.date, dt.date]:
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(biz_date) AS min_date, MAX(biz_date) AS max_date FROM fact_customer_shop_daily")
        row = cur.fetchone()
    if not row or not row["max_date"]:
        raise RuntimeError("fact_customer_shop_daily has no rows.")
    return row["min_date"], row["max_date"]


def load_fact_rows(conn, start: dt.date, end: dt.date) -> List[Dict]:
    sql = """
        SELECT biz_date, shop_id, cust_id, shop_name, ss_name, slsman,
               base_type_name, work_port_name, cust_seg_name,
               COALESCE(t_big_stoamt, 0) AS stock_qty,
               COALESCE(t_big_saleamt, 0) AS sale_qty,
               COALESCE(t_big_stockamt, 0) AS purchase_qty
        FROM fact_customer_shop_daily
        WHERE biz_date BETWEEN %s AND %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (start, end))
        return cur.fetchall()


def enrich_and_filter_rows(fact_rows: List[Dict], dim_map: Dict[str, Dict], levels: List[str]) -> List[Dict]:
    output = []
    allowed = set(levels)
    for row in fact_rows:
        dim = dim_map.get(str(row.get("shop_id"))) or dim_map.get(str(row.get("cust_id"))) or {}
        terminal_level = dim.get("terminal_level") or MISSING
        if terminal_level not in allowed:
            continue
        item = dict(row)
        item.update(
            {
                "cust_name": dim.get("cust_name") or row.get("shop_name") or row.get("shop_id"),
                "license_no": dim.get("license_no") or row.get("license_no") or MISSING,
                "group_name": dim.get("group_name") or MISSING,
                "terminal_level": terminal_level,
                "cust_seg_name": dim.get("cust_seg_name") or row.get("cust_seg_name") or MISSING,
                "market_type": dim.get("market_type") or MISSING,
                "work_port_name": dim.get("work_port_name") or row.get("work_port_name") or MISSING,
                "business_area_type": dim.get("business_area_type") or MISSING,
                "base_type_name": dim.get("base_type_name") or row.get("base_type_name") or MISSING,
                "longitude": dim.get("longitude"),
                "latitude": dim.get("latitude"),
                "stock_qty": decimal_or_zero(row.get("stock_qty")),
                "sale_qty": decimal_or_zero(row.get("sale_qty")),
                "purchase_qty": decimal_or_zero(row.get("purchase_qty")),
            }
        )
        item["peer_key"] = "|".join(
            [
                str(item["market_type"]),
                str(item["cust_seg_name"]),
                str(item["business_area_type"]),
                str(item["base_type_name"]),
            ]
        )
        output.append(item)
    return output


def iter_dates(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def rolling(values_by_date: Dict[dt.date, Decimal], dates: List[dt.date], window_days: int) -> Dict[dt.date, Decimal]:
    queue = deque()
    total = Decimal("0")
    result = {}
    for day in dates:
        value = values_by_date.get(day, Decimal("0"))
        queue.append((day, value))
        total += value
        cutoff = day - dt.timedelta(days=window_days - 1)
        while queue and queue[0][0] < cutoff:
            _, old = queue.popleft()
            total -= old
        result[day] = total
    return result


def rolling_average(values_by_date: Dict[dt.date, Decimal], dates: List[dt.date], window_days: int) -> Dict[dt.date, Optional[Decimal]]:
    queue = deque()
    total = Decimal("0")
    result = {}
    for day in dates:
        value = values_by_date.get(day, Decimal("0"))
        queue.append((day, value))
        total += value
        cutoff = day - dt.timedelta(days=window_days - 1)
        while queue and queue[0][0] < cutoff:
            _, old = queue.popleft()
            total -= old
        result[day] = safe_div(total, Decimal(len(queue))) if queue else None
    return result


def yoy_fields(current: Optional[Decimal], previous: Optional[Decimal]) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    if current is None or previous is None:
        return None, None
    current_value = decimal_or_zero(current)
    previous_value = decimal_or_zero(previous)
    diff = current_value - previous_value
    pct = safe_div(diff, previous_value)
    return diff, pct


def build_area_trend(rows: List[Dict], trend_start: dt.date, end: dt.date) -> List[Dict]:
    by_date = defaultdict(lambda: {"shops": set(), "active": set(), "stock": Decimal("0"), "sale": Decimal("0"), "purchase": Decimal("0")})
    for row in rows:
        day = row["biz_date"]
        shop_id = str(row["shop_id"])
        by_date[day]["shops"].add(shop_id)
        if row["sale_qty"] > 0:
            by_date[day]["active"].add(shop_id)
        by_date[day]["stock"] += row["stock_qty"]
        by_date[day]["sale"] += row["sale_qty"]
        by_date[day]["purchase"] += row["purchase_qty"]

    all_dates = list(iter_dates(trend_start - dt.timedelta(days=119), end))
    sale_series = {day: by_date[day]["sale"] for day in all_dates}
    stock_series = {day: by_date[day]["stock"] for day in all_dates}
    sale_7 = rolling(sale_series, all_dates, 7)
    sale_30 = rolling(sale_series, all_dates, 30)
    stock_ma_7 = rolling_average(stock_series, all_dates, 7)
    stock_ma_30 = rolling_average(stock_series, all_dates, 30)
    stock_ma_60 = rolling_average(stock_series, all_dates, 60)
    stock_ma_120 = rolling_average(stock_series, all_dates, 120)
    trend = []
    for day in iter_dates(trend_start, end):
        bucket = by_date[day]
        customer_count = len(bucket["shops"])
        active_count = len(bucket["active"])
        stock = bucket["stock"]
        trend.append(
            {
                "biz_date": day,
                "customer_count": customer_count,
                "active_customer_count": active_count,
                "active_rate": quant(safe_div(Decimal(active_count), Decimal(customer_count))) if customer_count else None,
                "stock_qty": stock,
                "sale_qty": bucket["sale"],
                "purchase_qty": bucket["purchase"],
                "sale_qty_7d": sale_7.get(day, Decimal("0")),
                "sale_qty_30d": sale_30.get(day, Decimal("0")),
                "stock_sale_ratio_7d": quant(safe_div(stock, sale_7.get(day, Decimal("0")))),
                "stock_sale_ratio_7d_monthly": quant(monthly_7d_ratio(stock, sale_7.get(day, Decimal("0")))),
                "stock_sale_ratio_30d": quant(safe_div(stock, sale_30.get(day, Decimal("0")))),
                "stock_ma_7": quant(stock_ma_7.get(day), "0.0001"),
                "stock_ma_30": quant(stock_ma_30.get(day), "0.0001"),
                "stock_ma_60": quant(stock_ma_60.get(day), "0.0001"),
                "stock_ma_120": quant(stock_ma_120.get(day), "0.0001"),
                "is_weekly_point": 1 if day.weekday() == 5 else 0,
            }
        )
    return trend


def build_all_daily_sale_rows(fact_rows: List[Dict], trend_start: dt.date, end: dt.date) -> List[Dict]:
    by_date = defaultdict(Decimal)
    for row in fact_rows:
        day = row["biz_date"]
        if trend_start <= day <= end:
            by_date[day] += decimal_or_zero(row.get("sale_qty"))
    return [
        {
            "biz_date": day,
            "sale_qty": by_date[day],
        }
        for day in iter_dates(trend_start, end)
    ]


def build_weekly_compare(area_trend: List[Dict], compare_source: List[Dict]) -> List[Dict]:
    by_date = {row["biz_date"]: row for row in compare_source}
    output = []
    for row in area_trend:
        if not row.get("is_weekly_point"):
            continue
        last_year_date = row["biz_date"] - dt.timedelta(days=364)
        previous = by_date.get(last_year_date)
        if previous and int(previous.get("customer_count") or 0) <= 0:
            previous = None
        stock_diff, stock_pct = yoy_fields(row.get("stock_qty"), previous.get("stock_qty") if previous else None)
        ratio_diff, ratio_pct = yoy_fields(
            row.get("stock_sale_ratio_7d_monthly"),
            previous.get("stock_sale_ratio_7d_monthly") if previous else None,
        )
        sale_diff, sale_pct = yoy_fields(row.get("sale_qty_7d"), previous.get("sale_qty_7d") if previous else None)
        output.append(
            {
                "biz_date": row["biz_date"],
                "customer_count": row.get("customer_count"),
                "active_customer_count": row.get("active_customer_count"),
                "stock_qty": row.get("stock_qty"),
                "sale_qty_7d": row.get("sale_qty_7d"),
                "purchase_qty": row.get("purchase_qty"),
                "stock_sale_ratio_7d_monthly": row.get("stock_sale_ratio_7d_monthly"),
                "last_year_date": last_year_date,
                "last_year_customer_count": previous.get("customer_count") if previous else None,
                "last_year_stock_qty": previous.get("stock_qty") if previous else None,
                "last_year_sale_qty_7d": previous.get("sale_qty_7d") if previous else None,
                "last_year_stock_sale_ratio_7d_monthly": previous.get("stock_sale_ratio_7d_monthly") if previous else None,
                "stock_yoy_diff": quant(stock_diff, "0.0001"),
                "stock_yoy_pct": quant(stock_pct),
                "sale_yoy_diff": quant(sale_diff, "0.0001"),
                "sale_yoy_pct": quant(sale_pct),
                "ratio_yoy_diff": quant(ratio_diff),
                "ratio_yoy_pct": quant(ratio_pct),
            }
        )
    return output


def build_customer_trend(rows: List[Dict], trend_start: dt.date, end: dt.date) -> List[Dict]:
    by_shop = defaultdict(list)
    for row in rows:
        by_shop[str(row["shop_id"])].append(row)
    trend_rows = []
    all_dates = list(iter_dates(trend_start - dt.timedelta(days=29), end))
    for shop_id, items in by_shop.items():
        items.sort(key=lambda x: x["biz_date"])
        latest = items[-1]
        by_date = {item["biz_date"]: item for item in items}
        sale_series = {day: by_date[day]["sale_qty"] if day in by_date else Decimal("0") for day in all_dates}
        purchase_series = {day: by_date[day]["purchase_qty"] if day in by_date else Decimal("0") for day in all_dates}
        sale_7 = rolling(sale_series, all_dates, 7)
        sale_30 = rolling(sale_series, all_dates, 30)
        purchase_7 = rolling(purchase_series, all_dates, 7)
        for day in iter_dates(trend_start, end):
            item = by_date.get(day)
            if not item:
                continue
            stock = item["stock_qty"]
            trend_rows.append(
                {
                    "biz_date": day,
                    "shop_id": shop_id,
                    "cust_id": item.get("cust_id"),
                    "cust_name": item.get("cust_name"),
                    "license_no": item.get("license_no"),
                    "group_name": item.get("group_name"),
                    "terminal_level": item.get("terminal_level"),
                    "cust_seg_name": item.get("cust_seg_name"),
                    "market_type": item.get("market_type"),
                    "work_port_name": item.get("work_port_name"),
                    "business_area_type": item.get("business_area_type"),
                    "base_type_name": item.get("base_type_name"),
                    "stock_qty": stock,
                    "sale_qty": item["sale_qty"],
                    "purchase_qty": item["purchase_qty"],
                    "purchase_qty_7d": purchase_7.get(day, Decimal("0")),
                    "sale_qty_7d": sale_7.get(day, Decimal("0")),
                    "sale_qty_30d": sale_30.get(day, Decimal("0")),
                    "stock_sale_ratio_7d": quant(safe_div(stock, sale_7.get(day, Decimal("0")))),
                    "stock_sale_ratio_7d_monthly": quant(monthly_7d_ratio(stock, sale_7.get(day, Decimal("0")))),
                    "stock_sale_ratio_30d": quant(safe_div(stock, sale_30.get(day, Decimal("0")))),
                }
            )
    return trend_rows


def average(values: List[Decimal]) -> Optional[Decimal]:
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def build_customer_diagnosis(rows: List[Dict], end: dt.date, baseline_start: dt.date, baseline_days: int) -> List[Dict]:
    by_shop = defaultdict(list)
    for row in rows:
        by_shop[str(row["shop_id"])].append(row)

    diagnosis = []
    sale_7_start = end - dt.timedelta(days=6)
    sale_30_start = end - dt.timedelta(days=29)
    for shop_id, items in by_shop.items():
        items.sort(key=lambda x: x["biz_date"])
        latest_candidates = [item for item in items if item["biz_date"] <= end]
        if not latest_candidates:
            continue
        latest = latest_candidates[-1]
        baseline_items = [item for item in items if baseline_start <= item["biz_date"] <= end]
        sale_7 = sum(item["sale_qty"] for item in items if sale_7_start <= item["biz_date"] <= end)
        sale_30 = sum(item["sale_qty"] for item in items if sale_30_start <= item["biz_date"] <= end)
        purchase_7 = sum(item["purchase_qty"] for item in items if sale_7_start <= item["biz_date"] <= end)
        purchase_30 = sum(item["purchase_qty"] for item in items if sale_30_start <= item["biz_date"] <= end)
        baseline_stock_avg = average([item["stock_qty"] for item in baseline_items])
        baseline_sale = sum(item["sale_qty"] for item in baseline_items)
        baseline_observed_days = len({item["biz_date"] for item in baseline_items}) or baseline_days
        baseline_30d_sale = baseline_sale / Decimal(baseline_observed_days) * Decimal("30")
        stock = latest["stock_qty"]
        row = {
            "as_of_date": end,
            "baseline_start_date": baseline_start,
            "baseline_days": baseline_observed_days,
            "shop_id": shop_id,
            "cust_id": latest.get("cust_id"),
            "cust_name": latest.get("cust_name"),
            "license_no": latest.get("license_no"),
            "group_name": latest.get("group_name"),
            "terminal_level": latest.get("terminal_level"),
            "cust_seg_name": latest.get("cust_seg_name"),
            "market_type": latest.get("market_type"),
            "work_port_name": latest.get("work_port_name"),
            "business_area_type": latest.get("business_area_type"),
            "base_type_name": latest.get("base_type_name"),
            "ss_name": latest.get("ss_name"),
            "slsman": latest.get("slsman"),
            "longitude": latest.get("longitude"),
            "latitude": latest.get("latitude"),
            "stock_qty": stock,
            "sale_qty_7d": sale_7,
            "sale_qty_30d": sale_30,
            "purchase_qty_7d": purchase_7,
            "purchase_qty_30d": purchase_30,
            "stock_sale_ratio_7d": quant(safe_div(stock, sale_7)),
            "stock_sale_ratio_7d_monthly": quant(monthly_7d_ratio(stock, sale_7)),
            "stock_sale_ratio_30d": quant(safe_div(stock, sale_30)),
            "baseline_avg_stock_qty": quant(baseline_stock_avg, "0.0001"),
            "baseline_30d_sale_qty": quant(baseline_30d_sale, "0.0001"),
            "baseline_ratio_30d": quant(safe_div(stock, baseline_30d_sale)),
            "peer_key": latest.get("peer_key") or "",
        }
        diagnosis.append(row)

    peers = defaultdict(list)
    for row in diagnosis:
        peers[row["peer_key"]].append(row)

    for row in diagnosis:
        peer_rows = peers[row["peer_key"]]
        peer_avg_stock = average([decimal_or_zero(item["baseline_avg_stock_qty"]) for item in peer_rows])
        peer_avg_sale = average([decimal_or_zero(item["baseline_30d_sale_qty"]) for item in peer_rows])
        peer_avg_ratio = average([decimal_or_zero(item["baseline_ratio_30d"]) for item in peer_rows if item["baseline_ratio_30d"] is not None])
        row["peer_customer_count"] = len(peer_rows)
        row["peer_avg_stock_qty"] = quant(peer_avg_stock, "0.0001")
        row["peer_avg_30d_sale_qty"] = quant(peer_avg_sale, "0.0001")
        row["peer_avg_ratio_30d"] = quant(peer_avg_ratio)
        row["stock_peer_multiple"] = quant(safe_div(row["stock_qty"], peer_avg_stock or Decimal("0")))
        row["sale_peer_multiple"] = quant(safe_div(row["sale_qty_30d"], peer_avg_sale or Decimal("0")))
        row["ratio_peer_multiple"] = quant(safe_div(decimal_or_zero(row["stock_sale_ratio_30d"]), peer_avg_ratio or Decimal("0")))
        tags = []
        score = Decimal("0")
        if row["sale_qty_30d"] == 0 and row["stock_qty"] > 0:
            tags.append("有库存无销售")
            score += Decimal("40")
        if (row["stock_peer_multiple"] or Decimal("0")) >= Decimal("1.5") and (row["sale_peer_multiple"] or Decimal("0")) <= Decimal("0.6"):
            tags.append("180天同类基准下高库存低动销")
            score += Decimal("35")
        if (row["stock_sale_ratio_30d"] or Decimal("0")) >= Decimal("25"):
            tags.append("30天存销比偏高")
            score += Decimal("20")
        if row["purchase_qty_30d"] > 0 and row["sale_qty_30d"] > 0:
            purchase_sale = row["purchase_qty_30d"] / row["sale_qty_30d"]
            if purchase_sale >= Decimal("1.5") and (row["stock_sale_ratio_30d"] or Decimal("0")) >= Decimal("15"):
                tags.append("购进偏多且库存压力高")
                score += Decimal("10")
        row["abnormal_tag"] = "、".join(tags) if tags else NORMAL
        row["abnormal_score"] = score
    return diagnosis


def parse_seg(value) -> Optional[Decimal]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return Decimal(digits) if digits else None


def build_group_summary(customers: List[Dict], end: dt.date) -> List[Dict]:
    groups = defaultdict(list)
    for row in customers:
        groups[row.get("group_name") or MISSING].append(row)
    output = []
    for group_name, rows in groups.items():
        customer_count = len(rows)
        active_count = sum(1 for row in rows if row["sale_qty_30d"] > 0)
        stock = sum(row["stock_qty"] for row in rows)
        sale = sum(row["sale_qty_30d"] for row in rows)
        abnormal_count = sum(1 for row in rows if row["abnormal_tag"] != NORMAL)
        expected_sale = sum(decimal_or_zero(row["peer_avg_30d_sale_qty"]) for row in rows)
        seg_values = [parse_seg(row.get("cust_seg_name")) for row in rows]
        seg_values = [value for value in seg_values if value is not None]
        sale_achievement = safe_div(sale, expected_sale)
        score = Decimal("100")
        if sale_achievement is not None:
            score -= max(Decimal("0"), Decimal("1") - sale_achievement) * Decimal("35")
        score -= (safe_div(Decimal(abnormal_count), Decimal(customer_count)) or Decimal("0")) * Decimal("30")
        output.append(
            {
                "as_of_date": end,
                "group_name": group_name,
                "customer_count": customer_count,
                "active_customer_count": active_count,
                "active_rate": quant(safe_div(Decimal(active_count), Decimal(customer_count))),
                "avg_cust_seg": quant(average(seg_values), "0.0001") if seg_values else None,
                "city_customer_pct": quant(safe_div(Decimal(sum(1 for row in rows if row.get("market_type") == "城网")), Decimal(customer_count))),
                "rural_customer_pct": quant(safe_div(Decimal(sum(1 for row in rows if row.get("market_type") == "农网")), Decimal(customer_count))),
                "stock_qty": stock,
                "sale_qty_30d": sale,
                "stock_sale_ratio_30d": quant(safe_div(stock, sale)),
                "expected_30d_sale_qty": quant(expected_sale, "0.0001"),
                "sale_achievement": quant(sale_achievement),
                "abnormal_customer_count": abnormal_count,
                "abnormal_customer_pct": quant(safe_div(Decimal(abnormal_count), Decimal(customer_count))),
                "group_score": max(Decimal("0"), quant(score, "0.0001") or Decimal("0")),
            }
        )
    return sorted(output, key=lambda row: (row["group_score"] or Decimal("0"), -row["abnormal_customer_count"]))


def build_dimension_summary(customers: List[Dict]) -> List[Dict]:
    dimensions = ["cust_seg_name", "market_type", "work_port_name", "business_area_type", "group_name", "base_type_name", "terminal_level"]
    output = []
    for dim in dimensions:
        buckets = defaultdict(list)
        for row in customers:
            buckets[row.get(dim) or MISSING].append(row)
        for value, rows in buckets.items():
            customer_count = len(rows)
            stock = sum(row["stock_qty"] for row in rows)
            sale = sum(row["sale_qty_30d"] for row in rows)
            abnormal_count = sum(1 for row in rows if row["abnormal_tag"] != NORMAL)
            output.append(
                {
                    "dimension_type": dim,
                    "dimension_value": value,
                    "customer_count": customer_count,
                    "active_customer_count": sum(1 for row in rows if row["sale_qty_30d"] > 0),
                    "stock_qty": stock,
                    "sale_qty_30d": sale,
                    "stock_sale_ratio_30d": quant(safe_div(stock, sale)),
                    "abnormal_customer_count": abnormal_count,
                    "abnormal_customer_pct": quant(safe_div(Decimal(abnormal_count), Decimal(customer_count))),
                }
            )
    return output


def write_mysql(conn, table: str, rows: List[Dict], delete_sql: str, delete_params: Tuple):
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_sql = ", ".join(f"`{col}`" for col in columns)
    insert_sql = f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})"
    with conn.cursor() as cur:
        cur.execute(delete_sql, delete_params)
        chunk = 1000
        for idx in range(0, len(rows), chunk):
            cur.executemany(insert_sql, [tuple(row[col] for col in columns) for row in rows[idx : idx + chunk]])
    conn.commit()
    return len(rows)


def write_csv(path: Path, rows: List[Dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: jsonable(value) for key, value in row.items()})


def slim(rows: List[Dict], limit: int) -> List[Dict]:
    return [{key: jsonable(value) for key, value in row.items()} for row in rows[:limit]]


def select_app_customers(customer_rows: List[Dict], abnormal_rows: List[Dict], limit: int) -> set:
    selected = []
    seen = set()
    for source in [abnormal_rows, customer_rows]:
        for row in source:
            shop_id = str(row["shop_id"])
            if shop_id in seen:
                continue
            seen.add(shop_id)
            selected.append(shop_id)
            if len(selected) >= limit:
                return set(selected)
    return set(selected)


def write_app_data(path: Path, payload: Dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "window.DIAGNOSIS_APP_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def safe_filename(value: str) -> str:
    keep = []
    for ch in str(value):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep) or "unknown"


def write_customer_trend_files(output_dir: Path, rows: List[Dict]) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("*.js"):
        old.unlink()
    by_shop = defaultdict(list)
    for row in rows:
        by_shop[str(row["shop_id"])].append(row)
    index = {}
    for shop_id, items in by_shop.items():
        items.sort(key=lambda row: row["biz_date"])
        filename = f"{safe_filename(shop_id)}.js"
        path = output_dir / filename
        payload = slim(items, len(items))
        var_name = "window.CUSTOMER_TREND_DATA"
        path.write_text(
            f"{var_name} = {json.dumps({'shopId': shop_id, 'rows': payload}, ensure_ascii=False, separators=(',', ':'))};\n",
            encoding="utf-8",
        )
        index[shop_id] = f"data/customer_trends/{filename}"
    return index


def write_day_detail_files(output_dir: Path, rows: List[Dict]) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.glob("*.js"):
        old.unlink()
    by_day = defaultdict(list)
    for row in rows:
        by_day[row["biz_date"]].append(row)
    index = {}
    fields = [
        "biz_date",
        "shop_id",
        "cust_id",
        "cust_name",
        "license_no",
        "group_name",
        "terminal_level",
        "cust_seg_name",
        "market_type",
        "work_port_name",
        "business_area_type",
        "base_type_name",
        "stock_qty",
        "sale_qty",
        "purchase_qty",
        "purchase_qty_7d",
        "sale_qty_7d",
        "sale_qty_30d",
        "stock_sale_ratio_7d_monthly",
        "stock_sale_ratio_30d",
    ]
    for day, items in by_day.items():
        items.sort(key=lambda row: (-row["stock_qty"], str(row.get("cust_name") or "")))
        filename = f"day_{day.isoformat()}.js"
        payload = [{field: jsonable(row.get(field)) for field in fields} for row in items]
        path = output_dir / filename
        path.write_text(
            "window.INVENTORY_DAY_DETAILS = window.INVENTORY_DAY_DETAILS || {};\n"
            f"window.INVENTORY_DAY_DETAILS[{json.dumps(day.isoformat())}] = {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))};\n",
            encoding="utf-8",
        )
        index[day.isoformat()] = f"data/day_details/{filename}"
    return index


def main() -> int:
    args = parse_args()
    levels = [item.strip() for item in args.levels.split(",") if item.strip()]
    if not levels:
        raise ValueError("--levels cannot be empty")
    end_text = normalize_date(args.end_date)
    trend_start_text = normalize_date(args.trend_start_date)
    export_dir = Path(args.export_dir)
    app_data_path = Path(args.app_data)
    customer_trend_dir = Path(args.customer_trend_dir)
    day_detail_dir = Path(args.day_detail_dir)

    with connect(args) as conn:
        ensure_tables(conn)
        min_date, max_date = fact_date_range(conn)
        end = dt.date.fromisoformat(end_text) if end_text else max_date
        trend_start = dt.date.fromisoformat(trend_start_text) if trend_start_text else min_date
        baseline_start = max(min_date, end - dt.timedelta(days=args.baseline_days - 1))
        compare_trend_start = trend_start - dt.timedelta(days=364)
        fetch_start = min(trend_start - dt.timedelta(days=119), compare_trend_start - dt.timedelta(days=119), baseline_start, end - dt.timedelta(days=29))

        dim_map = load_customer_dim(conn)
        fact_rows = load_fact_rows(conn, fetch_start, end)
        rows = enrich_and_filter_rows(fact_rows, dim_map, levels)
        area_trend = build_area_trend(rows, trend_start, end)
        all_daily_sale_rows = build_all_daily_sale_rows(fact_rows, trend_start, end)
        compare_area_trend = build_area_trend(rows, compare_trend_start, end)
        customer_trend = build_customer_trend(rows, trend_start, end)
        detail_trend = build_customer_trend(rows, compare_trend_start, end)
        customer_diag = build_customer_diagnosis(rows, end, baseline_start, args.baseline_days)
        group_summary = build_group_summary(customer_diag, end)
        dimension_summary = build_dimension_summary(customer_diag)

        write_mysql(
            conn,
            "rpt_area_terminal_daily_trend",
            area_trend,
            "DELETE FROM rpt_area_terminal_daily_trend WHERE biz_date BETWEEN %s AND %s",
            (trend_start, end),
        )
        write_mysql(
            conn,
            "rpt_customer_inventory_daily_trend",
            customer_trend,
            "DELETE FROM rpt_customer_inventory_daily_trend WHERE biz_date BETWEEN %s AND %s",
            (trend_start, end),
        )
        write_mysql(
            conn,
            "rpt_customer_inventory_diagnosis",
            customer_diag,
            "DELETE FROM rpt_customer_inventory_diagnosis WHERE as_of_date=%s",
            (end,),
        )
        write_mysql(
            conn,
            "rpt_group_inventory_diagnosis",
            group_summary,
            "DELETE FROM rpt_group_inventory_diagnosis WHERE as_of_date=%s",
            (end,),
        )

    weekly_points = [row for row in area_trend if row["is_weekly_point"]]
    weekly_compare_rows = build_weekly_compare(area_trend, compare_area_trend)
    abnormal_rows = sorted(customer_diag, key=lambda row: (-row["abnormal_score"], -(row["stock_sale_ratio_30d"] or Decimal("0")), -row["stock_qty"]))
    customer_rows = sorted(customer_diag, key=lambda row: (-row["stock_qty"], str(row["cust_name"] or "")))
    customer_trend_index = write_customer_trend_files(customer_trend_dir, customer_trend)
    day_detail_index = write_day_detail_files(day_detail_dir, detail_trend)

    write_csv(export_dir / "rpt_area_terminal_daily_trend.csv", area_trend)
    write_csv(export_dir / "rpt_area_terminal_weekly_ratio.csv", weekly_points)
    write_csv(export_dir / "rpt_customer_inventory_daily_trend.csv", customer_trend)
    write_csv(export_dir / "rpt_customer_inventory_diagnosis.csv", customer_diag)
    write_csv(export_dir / "rpt_group_inventory_diagnosis.csv", group_summary)
    write_csv(export_dir / "rpt_dimension_inventory_summary.csv", dimension_summary)

    latest_area = area_trend[-1] if area_trend else {}
    payload = {
        "generatedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trendStart": trend_start.isoformat(),
        "periodEnd": end.isoformat(),
        "baselineStart": baseline_start.isoformat(),
        "baselineDays": args.baseline_days,
        "levels": levels,
        "summary": {
            "customerCount": latest_area.get("customer_count", len(customer_diag)),
            "activeCustomerCount": latest_area.get("active_customer_count", 0),
            "stockQty": jsonable(latest_area.get("stock_qty")),
            "saleQty7d": jsonable(latest_area.get("sale_qty_7d")),
            "saleQty30d": jsonable(latest_area.get("sale_qty_30d")),
            "ratio7d": jsonable(latest_area.get("stock_sale_ratio_7d")),
            "ratio7dMonthly": jsonable(latest_area.get("stock_sale_ratio_7d_monthly")),
            "ratio30d": jsonable(latest_area.get("stock_sale_ratio_30d")),
            "abnormalCustomerCount": sum(1 for row in customer_diag if row["abnormal_tag"] != NORMAL),
        },
        "areaTrendRows": slim(area_trend, 10000),
        "allDailySaleRows": slim(all_daily_sale_rows, 10000),
        "weeklyRatioRows": slim(weekly_points, 2000),
        "weeklyStockCompareRows": slim(weekly_compare_rows, 2000),
        "customerTrendIndex": customer_trend_index,
        "dayDetailIndex": day_detail_index,
        "customerTrendRows": [],
        "customerRows": slim(customer_rows, args.app_customer_limit),
        "abnormalRows": slim(abnormal_rows, 3000),
        "groupRows": slim(group_summary, 3000),
        "dimensionRows": slim(dimension_summary, 5000),
    }
    # Backward compatible names used by the current page.
    payload["trendRows"] = payload["areaTrendRows"]
    write_app_data(app_data_path, payload)

    print(f"end_date={end}")
    print(f"trend_range={trend_start}..{end} days={(end - trend_start).days + 1}")
    print(f"baseline_range={baseline_start}..{end} days={(end - baseline_start).days + 1}")
    print(f"fact_rows_loaded={len(fact_rows)} filtered_rows={len(rows)}")
    print(f"area_trend_rows={len(area_trend)} weekly_points={len(weekly_points)}")
    print(f"customer_trend_rows={len(customer_trend)} customer_diag_rows={len(customer_diag)}")
    print(f"exports={export_dir}")
    print(f"app_data={app_data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
