import argparse
import csv
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor


ROOT = Path(__file__).resolve().parents[2]
SPACE_DIR = Path(__file__).resolve().parents[1]
SQL_PATH = SPACE_DIR / "sql" / "03_customer_activity_tables.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build customer period activity reports from shop summary facts.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="pos_ods")
    parser.add_argument("--charset", default="utf8mb4")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--output-dir", default=str(SPACE_DIR / "exports_activity"))
    return parser.parse_args()


def normalize_date(value: str) -> str:
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def split_sql(script: str):
    statements = []
    current = []
    in_single = False
    in_double = False
    prev = ""
    for ch in script:
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
        elif ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            text = "".join(current).strip()
            if text:
                statements.append(text)
            current = []
        else:
            current.append(ch)
        prev = ch
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def to_jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def get_connection(args: argparse.Namespace):
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


def execute_schema(conn):
    script = SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        for statement in split_sql(script):
            cur.execute(statement)
    conn.commit()


def table_columns(conn, table_name: str):
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
        return {row["Field"] for row in cur.fetchall()}


def customer_dim_exprs(conn):
    cols = table_columns(conn, "dim_customer_profile")

    def col(name: str, fallback: str = "NULL"):
        return f"d.`{name}`" if name in cols else fallback

    return {
        "cust_id": f"COALESCE(NULLIF({col('cust_id', 'NULL')}, ''), NULLIF({col('custId', 'NULL')}, ''), p.cust_id)",
        "license_code": (
            f"COALESCE(NULLIF({col('license_code', 'NULL')}, ''), NULLIF({col('licenseNo', 'NULL')}, ''), "
            "p.license_code, p.shop_id)"
        ),
        "cust_name": (
            f"COALESCE(NULLIF({col('cust_name', 'NULL')}, ''), NULLIF({col('custName', 'NULL')}, ''), "
            "p.shop_name)"
        ),
        "cust_seg_name": (
            f"COALESCE(NULLIF({col('cust_seg_name', 'NULL')}, ''), NULLIF({col('customerSegment', 'NULL')}, ''), "
            "p.cust_seg_name)"
        ),
        "base_type_name": (
            f"COALESCE(NULLIF({col('base_type_name', 'NULL')}, ''), NULLIF({col('businessType', 'NULL')}, ''), "
            "p.base_type_name)"
        ),
        "work_port_name": (
            f"COALESCE(NULLIF({col('work_port_name', 'NULL')}, ''), "
            f"NULLIF({col('urbanRuralCategory', 'NULL')}, ''), p.work_port_name)"
        ),
        "sale_dept": f"COALESCE(NULLIF({col('sale_dept', 'NULL')}, ''), NULLIF({col('marketDepartment', 'NULL')}, ''))",
        "longitude": col("longitude", "NULL"),
        "latitude": col("latitude", "NULL"),
        "join": (
            f"({col('license_code', 'NULL')} = p.shop_id OR {col('licenseNo', 'NULL')} = p.shop_id "
            f"OR {col('shop_id', 'NULL')} = p.shop_id OR {col('cust_id', 'NULL')} = p.cust_id "
            f"OR {col('custId', 'NULL')} = p.cust_id)"
        ),
    }


def build_reports(conn, start_date: str, end_date: str):
    dim = customer_dim_exprs(conn)
    delete_customer_sql = """
        DELETE FROM rpt_customer_period_activity
        WHERE period_start_date = %s AND period_end_date = %s
    """
    insert_customer_sql = f"""
        INSERT INTO rpt_customer_period_activity (
          period_start_date, period_end_date, shop_id, cust_id, license_code,
          shop_name, cust_name, cust_seg_name, base_type_name, work_port_name,
          sale_dept, ss_name, slsman, longitude, latitude,
          days_with_data, active_days, active_rate,
          period_sale_qty, period_purchase_qty, period_sale_amount, period_stock_amount,
          end_biz_date, end_stock_qty, end_stock_amount,
          stock_sale_ratio, avg_daily_sale_qty, stock_cover_days, purchase_sale_ratio
        )
        SELECT
          %s AS period_start_date,
          %s AS period_end_date,
          p.shop_id,
          {dim["cust_id"]} AS cust_id,
          {dim["license_code"]} AS license_code,
          {dim["cust_name"]} AS shop_name,
          {dim["cust_name"]} AS cust_name,
          {dim["cust_seg_name"]} AS cust_seg_name,
          {dim["base_type_name"]} AS base_type_name,
          {dim["work_port_name"]} AS work_port_name,
          {dim["sale_dept"]} AS sale_dept,
          p.ss_name AS ss_name,
          p.slsman AS slsman,
          {dim["longitude"]} AS longitude,
          {dim["latitude"]} AS latitude,
          p.days_with_data,
          p.active_days,
          CASE WHEN p.days_with_data > 0 THEN p.active_days / p.days_with_data ELSE NULL END AS active_rate,
          p.period_sale_qty,
          p.period_purchase_qty,
          p.period_sale_amount,
          p.period_stock_amount,
          p.end_biz_date,
          COALESCE(last_day.t_big_stoamt, 0) AS end_stock_qty,
          COALESCE(last_day.t_stomny, 0) AS end_stock_amount,
          CASE WHEN p.period_sale_qty > 0 THEN COALESCE(last_day.t_big_stoamt, 0) / p.period_sale_qty ELSE NULL END AS stock_sale_ratio,
          CASE WHEN p.days_with_data > 0 THEN p.period_sale_qty / p.days_with_data ELSE NULL END AS avg_daily_sale_qty,
          CASE
            WHEN p.period_sale_qty > 0 AND p.days_with_data > 0
            THEN COALESCE(last_day.t_big_stoamt, 0) / (p.period_sale_qty / p.days_with_data)
            ELSE NULL
          END AS stock_cover_days,
          CASE WHEN p.period_sale_qty > 0 THEN p.period_purchase_qty / p.period_sale_qty ELSE NULL END AS purchase_sale_ratio
        FROM (
          SELECT
            shop_id,
            MAX(biz_date) AS end_biz_date,
            MAX(cust_id) AS cust_id,
            MAX(license_code) AS license_code,
            MAX(shop_name) AS shop_name,
            MAX(cust_seg_name) AS cust_seg_name,
            MAX(base_type_name) AS base_type_name,
            MAX(work_port_name) AS work_port_name,
            MAX(ss_name) AS ss_name,
            MAX(slsman) AS slsman,
            COUNT(DISTINCT biz_date) AS days_with_data,
            SUM(CASE WHEN COALESCE(t_big_saleamt, 0) > 0 THEN 1 ELSE 0 END) AS active_days,
            SUM(COALESCE(t_big_saleamt, 0)) AS period_sale_qty,
            SUM(COALESCE(t_big_stockamt, 0)) AS period_purchase_qty,
            SUM(COALESCE(t_salemny, 0)) AS period_sale_amount,
            SUM(COALESCE(t_stomny, 0)) AS period_stock_amount
          FROM fact_customer_shop_daily
          WHERE biz_date BETWEEN %s AND %s
          GROUP BY shop_id
        ) p
        JOIN fact_customer_shop_daily last_day
          ON last_day.shop_id = p.shop_id
         AND last_day.biz_date = p.end_biz_date
        LEFT JOIN dim_customer_profile d
          ON {dim["join"]}
    """
    delete_seg_sql = """
        DELETE FROM rpt_cust_seg_period_activity
        WHERE period_start_date = %s AND period_end_date = %s
    """
    insert_seg_sql = """
        INSERT INTO rpt_cust_seg_period_activity (
          period_start_date, period_end_date, cust_seg_name, customer_count,
          active_customer_count, avg_active_rate, sale_qty, purchase_qty,
          end_stock_qty, stock_sale_ratio, purchase_sale_ratio
        )
        SELECT
          period_start_date,
          period_end_date,
          COALESCE(NULLIF(cust_seg_name, ''), 'UNSEGMENTED') AS cust_seg_name,
          COUNT(*) AS customer_count,
          SUM(CASE WHEN period_sale_qty > 0 THEN 1 ELSE 0 END) AS active_customer_count,
          AVG(active_rate) AS avg_active_rate,
          SUM(period_sale_qty) AS sale_qty,
          SUM(period_purchase_qty) AS purchase_qty,
          SUM(end_stock_qty) AS end_stock_qty,
          CASE WHEN SUM(period_sale_qty) > 0 THEN SUM(end_stock_qty) / SUM(period_sale_qty) ELSE NULL END AS stock_sale_ratio,
          CASE WHEN SUM(period_sale_qty) > 0 THEN SUM(period_purchase_qty) / SUM(period_sale_qty) ELSE NULL END AS purchase_sale_ratio
        FROM rpt_customer_period_activity
        WHERE period_start_date = %s AND period_end_date = %s
        GROUP BY period_start_date, period_end_date, COALESCE(NULLIF(cust_seg_name, ''), 'UNSEGMENTED')
    """
    with conn.cursor() as cur:
        cur.execute(delete_customer_sql, (start_date, end_date))
        cur.execute(insert_customer_sql, (start_date, end_date, start_date, end_date))
        customer_rows = cur.rowcount
        cur.execute(delete_seg_sql, (start_date, end_date))
        cur.execute(insert_seg_sql, (start_date, end_date))
        seg_rows = cur.rowcount
    conn.commit()
    return customer_rows, seg_rows


def fetch_rows(conn, sql: str, params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def write_csv(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: to_jsonable(v) for k, v in row.items()})


def write_geojson(rows, path: Path):
    features = []
    for row in rows:
        lng = row.get("longitude")
        lat = row.get("latitude")
        if lng in (None, "") or lat in (None, ""):
            continue
        props = {k: to_jsonable(v) for k, v in row.items() if k not in ("longitude", "latitude")}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
                "properties": props,
            }
        )
    data = {"type": "FeatureCollection", "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_reports(conn, start_date: str, end_date: str, output_dir: Path):
    customer_sql = """
        SELECT
          period_start_date,
          period_end_date,
          period_end_date AS biz_date,
          shop_id,
          cust_id,
          license_code,
          shop_name,
          cust_name,
          cust_seg_name,
          base_type_name,
          work_port_name,
          sale_dept,
          ss_name,
          slsman,
          longitude,
          latitude,
          days_with_data,
          active_days,
          active_rate,
          period_sale_qty AS sale_qty,
          period_purchase_qty AS order_qty,
          end_stock_qty AS stock_qty,
          stock_sale_ratio,
          avg_daily_sale_qty,
          stock_cover_days,
          purchase_sale_ratio
        FROM rpt_customer_period_activity
        WHERE period_start_date = %s AND period_end_date = %s
        ORDER BY end_stock_qty DESC, period_sale_qty DESC
    """
    seg_sql = """
        SELECT *
        FROM rpt_cust_seg_period_activity
        WHERE period_start_date = %s AND period_end_date = %s
        ORDER BY cust_seg_name
    """
    customers = fetch_rows(conn, customer_sql, (start_date, end_date))
    segs = fetch_rows(conn, seg_sql, (start_date, end_date))
    write_csv(customers, output_dir / "rpt_customer_period_activity.csv")
    write_csv(segs, output_dir / "rpt_cust_seg_period_activity.csv")
    write_geojson(customers, output_dir / "rpt_customer_period_activity.geojson")
    return len(customers), len(segs)


def main() -> int:
    args = parse_args()
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    output_dir = Path(args.output_dir)
    with get_connection(args) as conn:
        execute_schema(conn)
        customer_written, seg_written = build_reports(conn, start_date, end_date)
        customer_exported, seg_exported = export_reports(conn, start_date, end_date, output_dir)
    print(f"period={start_date}..{end_date}")
    print(f"mysql_customer_rows={customer_written} mysql_seg_rows={seg_written}")
    print(f"export_customer_rows={customer_exported} export_seg_rows={seg_exported}")
    print(f"output_dir={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
