"""Build terminal-level daily trend reports for 2-star and 3-star customers.

The report uses shop-level daily facts, not item-level details, so it is fast
enough for scheduled reporting. Stock is treated as a daily snapshot, while
sales and purchase quantities are accumulated inside rolling windows.
"""

import argparse
import csv
import datetime as dt
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pymysql
from pymysql.cursors import DictCursor


REPORT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rpt_terminal_level_daily_trend (
  biz_date DATE NOT NULL COMMENT '统计日期',
  dimension_type VARCHAR(64) NOT NULL COMMENT '维度类型',
  dimension_value VARCHAR(255) NOT NULL COMMENT '维度值',
  customer_count INT NOT NULL DEFAULT 0 COMMENT '当日客户数',
  active_customer_count INT NOT NULL DEFAULT 0 COMMENT '当日有销售客户数',
  active_rate DECIMAL(18,6) NULL COMMENT '当日动销率=有销售客户数/客户数',
  stock_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '当日库存快照合计 SUM(t_big_stoamt)',
  sale_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '当日销售合计 SUM(t_big_saleamt)',
  purchase_qty DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '当日购进合计 SUM(t_big_stockamt)',
  sale_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '最近7天销售累计，含当天',
  sale_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '最近30天销售累计，含当天',
  purchase_qty_7d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '最近7天购进累计，含当天',
  purchase_qty_30d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT '最近30天购进累计，含当天',
  stock_sale_ratio_7d DECIMAL(18,6) NULL COMMENT '7天存销比=当日库存/最近7天销售',
  stock_sale_ratio_30d DECIMAL(18,6) NULL COMMENT '30天存销比=当日库存/最近30天销售',
  stock_cover_days_7d DECIMAL(18,6) NULL COMMENT '按最近7天日均销售测算的库存可销天数',
  stock_cover_days_30d DECIMAL(18,6) NULL COMMENT '按最近30天日均销售测算的库存可销天数',
  purchase_sale_ratio_7d DECIMAL(18,6) NULL COMMENT '7天购销比=最近7天购进/最近7天销售',
  purchase_sale_ratio_30d DECIMAL(18,6) NULL COMMENT '30天购销比=最近30天购进/最近30天销售',
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date, dimension_type, dimension_value),
  KEY idx_rpt_terminal_dim (dimension_type, dimension_value, biz_date),
  KEY idx_rpt_terminal_ratio7 (biz_date, stock_sale_ratio_7d),
  KEY idx_rpt_terminal_ratio30 (biz_date, stock_sale_ratio_30d)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='二星三星终端每日动销与存销比趋势表'
"""


DIMENSIONS = [
    ("ALL", "二星三星合计"),
    ("terminal_level", None),
    ("cust_seg_name", None),
    ("market_type", None),
    ("work_port_name", None),
    ("business_area_type", None),
    ("group_name", None),
    ("base_type_name", None),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 2-star/3-star terminal daily trend report.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="pos_ods")
    parser.add_argument("--charset", default="utf8mb4")
    parser.add_argument("--start-date", default="", help="YYYY-MM-DD or YYYYMMDD. Empty means earliest fact date.")
    parser.add_argument("--end-date", default="", help="YYYY-MM-DD or YYYYMMDD. Empty means latest fact date.")
    parser.add_argument("--levels", default="二星,三星", help="Terminal levels to include, comma-separated.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "analysis_exports" / "terminal_level_daily_trend.csv"),
        help="CSV output path.",
    )
    return parser.parse_args()


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def to_output(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.0001")))
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


def table_columns(conn, table_name: str):
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
        return {row["Field"] for row in cur.fetchall()}


def dim_expr(conn, standard: str, legacy: str = "", fallback: str = "NULL") -> str:
    cols = table_columns(conn, "dim_customer_profile")
    pieces = []
    if standard and standard in cols:
        pieces.append(f"NULLIF(d.`{standard}`, '')")
    if legacy and legacy in cols:
        pieces.append(f"NULLIF(d.`{legacy}`, '')")
    pieces.append(fallback)
    return "COALESCE(" + ", ".join(pieces) + ")"


def build_fact_query(conn, levels: List[str]) -> str:
    dim_cols = table_columns(conn, "dim_customer_profile")

    def c(name: str) -> str:
        return f"d.`{name}`" if name in dim_cols else "NULL"

    terminal_level = dim_expr(conn, "terminal_level", "terminalLevel")
    join_condition = (
        f"{c('license_code')} = f.shop_id OR {c('licenseNo')} = f.shop_id "
        f"OR {c('shop_id')} = f.shop_id OR {c('cust_id')} = f.cust_id "
        f"OR {c('custId')} = f.cust_id"
    )
    level_placeholders = ", ".join(["%s"] * len(levels))
    return f"""
        SELECT
          f.biz_date,
          f.shop_id,
          {terminal_level} AS terminal_level,
          {dim_expr(conn, "cust_seg_name", "customerSegment", "f.cust_seg_name")} AS cust_seg_name,
          {dim_expr(conn, "market_type", "marketType")} AS market_type,
          {dim_expr(conn, "work_port_name", "urbanRuralCategory", "f.work_port_name")} AS work_port_name,
          {dim_expr(conn, "business_area_type", "businessCircleType")} AS business_area_type,
          {dim_expr(conn, "group_name", "belongingGroup")} AS group_name,
          {dim_expr(conn, "base_type_name", "businessType", "f.base_type_name")} AS base_type_name,
          COALESCE(f.t_big_stoamt, 0) AS stock_qty,
          COALESCE(f.t_big_saleamt, 0) AS sale_qty,
          COALESCE(f.t_big_stockamt, 0) AS purchase_qty
        FROM fact_customer_shop_daily f
        JOIN dim_customer_profile d
          ON {join_condition}
        WHERE f.biz_date BETWEEN %s AND %s
          AND {terminal_level} IN ({level_placeholders})
    """


def resolve_date_range(conn, start_date: str, end_date: str) -> Tuple[dt.date, dt.date]:
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(biz_date) AS min_date, MAX(biz_date) AS max_date FROM fact_customer_shop_daily")
        row = cur.fetchone()
    if not row or not row["max_date"]:
        raise RuntimeError("fact_customer_shop_daily has no data.")
    start = dt.date.fromisoformat(start_date) if start_date else row["min_date"]
    end = dt.date.fromisoformat(end_date) if end_date else row["max_date"]
    if start > end:
        raise ValueError("start-date cannot be later than end-date.")
    return start, end


def iter_dates(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def add_daily_metrics(bucket, shop_id: str, stock: Decimal, sale: Decimal, purchase: Decimal):
    bucket["customer_ids"].add(shop_id)
    if sale > 0:
        bucket["active_customer_ids"].add(shop_id)
    bucket["stock_qty"] += stock
    bucket["sale_qty"] += sale
    bucket["purchase_qty"] += purchase


def aggregate_daily(rows) -> Dict[Tuple[dt.date, str, str], Dict]:
    daily = defaultdict(
        lambda: {
            "customer_ids": set(),
            "active_customer_ids": set(),
            "stock_qty": Decimal("0"),
            "sale_qty": Decimal("0"),
            "purchase_qty": Decimal("0"),
        }
    )
    for row in rows:
        biz_date = row["biz_date"]
        shop_id = str(row["shop_id"])
        stock = to_decimal(row["stock_qty"])
        sale = to_decimal(row["sale_qty"])
        purchase = to_decimal(row["purchase_qty"])
        for dim_type, fixed_value in DIMENSIONS:
            dim_value = fixed_value if fixed_value is not None else row.get(dim_type)
            dim_value = str(dim_value or "未填")
            add_daily_metrics(daily[(biz_date, dim_type, dim_value)], shop_id, stock, sale, purchase)
    return daily


def rolling_sum(series: Dict[dt.date, Decimal], dates: Iterable[dt.date], window_days: int) -> Dict[dt.date, Decimal]:
    result = {}
    q = deque()
    total = Decimal("0")
    for day in dates:
        value = series.get(day, Decimal("0"))
        q.append((day, value))
        total += value
        cutoff = day - dt.timedelta(days=window_days - 1)
        while q and q[0][0] < cutoff:
            _, old_value = q.popleft()
            total -= old_value
        result[day] = total
    return result


def safe_div(numerator: Decimal, denominator: Decimal):
    if denominator == 0:
        return None
    return numerator / denominator


def quant(value):
    if value is None:
        return None
    return value.quantize(Decimal("0.000001"))


def build_trend_rows(daily, start: dt.date, end: dt.date, pre_start: dt.date) -> List[Dict]:
    all_dim_keys = sorted({(dim_type, dim_value) for _, dim_type, dim_value in daily.keys()})
    all_dates = list(iter_dates(pre_start, end))
    output_rows = []
    for dim_type, dim_value in all_dim_keys:
        sale_series = {}
        purchase_series = {}
        for day in all_dates:
            bucket = daily.get((day, dim_type, dim_value))
            sale_series[day] = bucket["sale_qty"] if bucket else Decimal("0")
            purchase_series[day] = bucket["purchase_qty"] if bucket else Decimal("0")
        sale_7d = rolling_sum(sale_series, all_dates, 7)
        sale_30d = rolling_sum(sale_series, all_dates, 30)
        purchase_7d = rolling_sum(purchase_series, all_dates, 7)
        purchase_30d = rolling_sum(purchase_series, all_dates, 30)
        for day in iter_dates(start, end):
            bucket = daily.get((day, dim_type, dim_value))
            if not bucket:
                continue
            customer_count = len(bucket["customer_ids"])
            active_customer_count = len(bucket["active_customer_ids"])
            stock_qty = bucket["stock_qty"]
            sale_qty = bucket["sale_qty"]
            purchase_qty = bucket["purchase_qty"]
            row = {
                "biz_date": day,
                "dimension_type": dim_type,
                "dimension_value": dim_value,
                "customer_count": customer_count,
                "active_customer_count": active_customer_count,
                "active_rate": quant(safe_div(Decimal(active_customer_count), Decimal(customer_count))),
                "stock_qty": stock_qty,
                "sale_qty": sale_qty,
                "purchase_qty": purchase_qty,
                "sale_qty_7d": sale_7d[day],
                "sale_qty_30d": sale_30d[day],
                "purchase_qty_7d": purchase_7d[day],
                "purchase_qty_30d": purchase_30d[day],
                "stock_sale_ratio_7d": quant(safe_div(stock_qty, sale_7d[day])),
                "stock_sale_ratio_30d": quant(safe_div(stock_qty, sale_30d[day])),
                "stock_cover_days_7d": quant(safe_div(stock_qty, sale_7d[day] / Decimal("7")) if sale_7d[day] else None),
                "stock_cover_days_30d": quant(safe_div(stock_qty, sale_30d[day] / Decimal("30")) if sale_30d[day] else None),
                "purchase_sale_ratio_7d": quant(safe_div(purchase_7d[day], sale_7d[day])),
                "purchase_sale_ratio_30d": quant(safe_div(purchase_30d[day], sale_30d[day])),
            }
            output_rows.append(row)
    return output_rows


def fetch_fact_rows(conn, start: dt.date, end: dt.date, levels: List[str]):
    pre_start = start - dt.timedelta(days=29)
    sql = build_fact_query(conn, levels)
    params = [pre_start, end] + levels
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall(), pre_start


def ensure_report_table(conn):
    with conn.cursor() as cur:
        cur.execute(REPORT_TABLE_SQL)
    conn.commit()


def write_report_table(conn, rows: List[Dict], start: dt.date, end: dt.date):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM rpt_terminal_level_daily_trend WHERE biz_date BETWEEN %s AND %s",
            (start, end),
        )
        if not rows:
            conn.commit()
            return 0
        columns = [
            "biz_date",
            "dimension_type",
            "dimension_value",
            "customer_count",
            "active_customer_count",
            "active_rate",
            "stock_qty",
            "sale_qty",
            "purchase_qty",
            "sale_qty_7d",
            "sale_qty_30d",
            "purchase_qty_7d",
            "purchase_qty_30d",
            "stock_sale_ratio_7d",
            "stock_sale_ratio_30d",
            "stock_cover_days_7d",
            "stock_cover_days_30d",
            "purchase_sale_ratio_7d",
            "purchase_sale_ratio_30d",
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        updates = ", ".join([f"`{col}`=VALUES(`{col}`)" for col in columns[3:]])
        sql = (
            f"INSERT INTO rpt_terminal_level_daily_trend ({', '.join('`' + c + '`' for c in columns)}) "
            f"VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}, etl_loaded_at=NOW()"
        )
        values = [tuple(row[col] for col in columns) for row in rows]
        cur.executemany(sql, values)
    conn.commit()
    return len(rows)


def write_csv(rows: List[Dict], output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "biz_date",
        "dimension_type",
        "dimension_value",
        "customer_count",
        "active_customer_count",
        "active_rate",
        "stock_qty",
        "sale_qty",
        "purchase_qty",
        "sale_qty_7d",
        "sale_qty_30d",
        "purchase_qty_7d",
        "purchase_qty_30d",
        "stock_sale_ratio_7d",
        "stock_sale_ratio_30d",
        "stock_cover_days_7d",
        "stock_cover_days_30d",
        "purchase_sale_ratio_7d",
        "purchase_sale_ratio_30d",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: to_output(row[col]) for col in columns})


def main() -> int:
    args = parse_args()
    levels = [item.strip() for item in args.levels.split(",") if item.strip()]
    if not levels:
        raise ValueError("--levels cannot be empty.")
    start_text = normalize_date(args.start_date)
    end_text = normalize_date(args.end_date)
    output_path = Path(args.output)

    with connect(args) as conn:
        ensure_report_table(conn)
        start, end = resolve_date_range(conn, start_text, end_text)
        fact_rows, pre_start = fetch_fact_rows(conn, start, end, levels)
        daily = aggregate_daily(fact_rows)
        trend_rows = build_trend_rows(daily, start, end, pre_start)
        written = write_report_table(conn, trend_rows, start, end)
        write_csv(trend_rows, output_path)

    print(f"levels={','.join(levels)}")
    print(f"date_range={start}..{end}")
    print(f"fact_rows_loaded={len(fact_rows)}")
    print(f"trend_rows_written={written}")
    print(f"csv={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
