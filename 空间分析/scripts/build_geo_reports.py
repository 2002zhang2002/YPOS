import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import pymysql


GEO_CUSTOMER_SQL = """
INSERT INTO rpt_geo_customer_daily (
  biz_date, shop_id, cust_id, license_code, cust_name, shop_name, cust_seg_name,
  base_type_name, work_port_name, sale_dept, ss_name, slsman, longitude, latitude,
  sale_qty, stock_qty, order_qty, sale_amount, stock_amount,
  active_item_count, stock_item_count, stock_sale_ratio, source_row_count
)
SELECT
  period.end_date AS biz_date,
  period.shop_id,
  COALESCE(d.cust_id, period.cust_id) AS cust_id,
  COALESCE(d.license_code, period.shop_id) AS license_code,
  COALESCE(d.cust_name, period.shop_name) AS cust_name,
  period.shop_name,
  COALESCE(d.cust_seg_name, period.cust_seg_name) AS cust_seg_name,
  COALESCE(d.base_type_name, period.base_type_name) AS base_type_name,
  COALESCE(d.work_port_name, period.work_port_name) AS work_port_name,
  d.sale_dept,
  COALESCE(d.ss_name, period.ss_name) AS ss_name,
  COALESCE(d.slsman, period.slsman) AS slsman,
  d.longitude,
  d.latitude,
  period.sale_qty,
  stock.stock_qty,
  period.order_qty,
  period.sale_amount,
  stock.stock_amount,
  period.active_item_count,
  stock.stock_item_count,
  CASE
    WHEN period.sale_qty = 0 THEN NULL
    ELSE stock.stock_qty / NULLIF(period.sale_qty, 0)
  END AS stock_sale_ratio,
  period.source_row_count
FROM (
  SELECT
    MAX(f.biz_date) AS end_date,
    f.shop_id,
    MAX(f.cust_id) AS cust_id,
    MAX(f.shop_name) AS shop_name,
    MAX(f.cust_seg_name) AS cust_seg_name,
    MAX(f.base_type_name) AS base_type_name,
    MAX(f.work_port_name) AS work_port_name,
    MAX(f.ss_name) AS ss_name,
    MAX(f.slsman) AS slsman,
    SUM(COALESCE(f.t_big_saleamt, 0)) AS sale_qty,
    SUM(COALESCE(f.t_big_stockamt, 0)) AS order_qty,
    SUM(COALESCE(f.t_salemny, 0)) AS sale_amount,
    SUM(CASE WHEN COALESCE(f.t_big_saleamt, 0) > 0 THEN 1 ELSE 0 END) AS active_item_count,
    COUNT(*) AS source_row_count
  FROM fact_customer_item_daily f
  WHERE f.biz_date BETWEEN %s AND %s
  GROUP BY f.shop_id
) period
JOIN (
  SELECT
    f.biz_date,
    f.shop_id,
    SUM(COALESCE(f.t_big_stoamt, 0)) AS stock_qty,
    SUM(COALESCE(f.t_stockmny, 0)) AS stock_amount,
    SUM(CASE WHEN COALESCE(f.t_big_stoamt, 0) > 0 THEN 1 ELSE 0 END) AS stock_item_count
  FROM fact_customer_item_daily f
  JOIN (
    SELECT shop_id, MAX(biz_date) AS end_date
    FROM fact_customer_item_daily
    WHERE biz_date BETWEEN %s AND %s
    GROUP BY shop_id
  ) last_day
    ON last_day.shop_id = f.shop_id
   AND last_day.end_date = f.biz_date
  GROUP BY f.biz_date, f.shop_id
) stock
  ON stock.shop_id = period.shop_id
 AND stock.biz_date = period.end_date
LEFT JOIN dim_customer_profile d
  ON d.license_code = period.shop_id
WHERE 1 = 1
  AND d.longitude IS NOT NULL
  AND d.latitude IS NOT NULL
ON DUPLICATE KEY UPDATE
  cust_id = VALUES(cust_id),
  license_code = VALUES(license_code),
  cust_name = VALUES(cust_name),
  shop_name = VALUES(shop_name),
  cust_seg_name = VALUES(cust_seg_name),
  base_type_name = VALUES(base_type_name),
  work_port_name = VALUES(work_port_name),
  sale_dept = VALUES(sale_dept),
  ss_name = VALUES(ss_name),
  slsman = VALUES(slsman),
  longitude = VALUES(longitude),
  latitude = VALUES(latitude),
  sale_qty = VALUES(sale_qty),
  stock_qty = VALUES(stock_qty),
  order_qty = VALUES(order_qty),
  sale_amount = VALUES(sale_amount),
  stock_amount = VALUES(stock_amount),
  active_item_count = VALUES(active_item_count),
  stock_item_count = VALUES(stock_item_count),
  stock_sale_ratio = VALUES(stock_sale_ratio),
  source_row_count = VALUES(source_row_count),
  etl_loaded_at = CURRENT_TIMESTAMP
"""


GEO_CUSTOMER_ITEM_SQL = """
INSERT INTO rpt_geo_customer_item_daily (
  biz_date, shop_id, cust_id, license_code, cust_name, shop_name, cust_seg_name,
  base_type_name, work_port_name, sale_dept, ss_name, slsman, longitude, latitude,
  item_key, item_name, barcode, big_barcode,
  sale_qty, stock_qty, order_qty, sale_amount, stock_amount, stock_sale_ratio
)
SELECT
  f.biz_date,
  f.shop_id,
  COALESCE(d.cust_id, f.cust_id) AS cust_id,
  COALESCE(d.license_code, f.shop_id) AS license_code,
  COALESCE(d.cust_name, f.shop_name) AS cust_name,
  f.shop_name,
  COALESCE(d.cust_seg_name, f.cust_seg_name) AS cust_seg_name,
  COALESCE(d.base_type_name, f.base_type_name) AS base_type_name,
  COALESCE(d.work_port_name, f.work_port_name) AS work_port_name,
  d.sale_dept,
  COALESCE(d.ss_name, f.ss_name) AS ss_name,
  COALESCE(d.slsman, f.slsman) AS slsman,
  d.longitude,
  d.latitude,
  f.item_key,
  f.item_name,
  f.barcode,
  f.big_barcode,
  SUM(COALESCE(f.t_big_saleamt, 0)) AS sale_qty,
  SUM(COALESCE(f.t_big_stoamt, 0)) AS stock_qty,
  SUM(COALESCE(f.t_big_stockamt, 0)) AS order_qty,
  SUM(COALESCE(f.t_salemny, 0)) AS sale_amount,
  SUM(COALESCE(f.t_stockmny, 0)) AS stock_amount,
  CASE
    WHEN SUM(COALESCE(f.t_big_saleamt, 0)) = 0 THEN NULL
    ELSE SUM(COALESCE(f.t_big_stoamt, 0)) / NULLIF(SUM(COALESCE(f.t_big_saleamt, 0)), 0)
  END AS stock_sale_ratio
FROM fact_customer_item_daily f
LEFT JOIN dim_customer_profile d
  ON d.license_code = f.shop_id
WHERE f.biz_date BETWEEN %s AND %s
  AND d.longitude IS NOT NULL
  AND d.latitude IS NOT NULL
GROUP BY
  f.biz_date, f.shop_id, COALESCE(d.cust_id, f.cust_id), COALESCE(d.license_code, f.shop_id),
  COALESCE(d.cust_name, f.shop_name), f.shop_name, COALESCE(d.cust_seg_name, f.cust_seg_name),
  COALESCE(d.base_type_name, f.base_type_name), COALESCE(d.work_port_name, f.work_port_name),
  d.sale_dept, COALESCE(d.ss_name, f.ss_name), COALESCE(d.slsman, f.slsman), d.longitude, d.latitude,
  f.item_key, f.item_name, f.barcode, f.big_barcode
ON DUPLICATE KEY UPDATE
  cust_id = VALUES(cust_id),
  license_code = VALUES(license_code),
  cust_name = VALUES(cust_name),
  shop_name = VALUES(shop_name),
  cust_seg_name = VALUES(cust_seg_name),
  base_type_name = VALUES(base_type_name),
  work_port_name = VALUES(work_port_name),
  sale_dept = VALUES(sale_dept),
  ss_name = VALUES(ss_name),
  slsman = VALUES(slsman),
  longitude = VALUES(longitude),
  latitude = VALUES(latitude),
  item_name = VALUES(item_name),
  barcode = VALUES(barcode),
  big_barcode = VALUES(big_barcode),
  sale_qty = VALUES(sale_qty),
  stock_qty = VALUES(stock_qty),
  order_qty = VALUES(order_qty),
  sale_amount = VALUES(sale_amount),
  stock_amount = VALUES(stock_amount),
  stock_sale_ratio = VALUES(stock_sale_ratio),
  etl_loaded_at = CURRENT_TIMESTAMP
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build geo analysis report tables and exports.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="pos_ods")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--level", choices=("customer", "item", "all"), default="customer")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent.parent / "exports"))
    return parser.parse_args()


def load_sql_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def execute_multi_sql(conn: Any, sql_text: str) -> None:
    statements = [part.strip() for part in sql_text.split(";") if part.strip()]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()


def fetch_all(conn: Any, sql: str, params: Sequence[Any]) -> List[Dict[str, Any]]:
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def to_feature(row: Dict[str, Any]) -> Dict[str, Any]:
    properties = dict(row)
    lon = properties.pop("longitude", None)
    lat = properties.pop("latitude", None)
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [float(lon), float(lat)],
        },
        "properties": properties,
    }


def write_geojson(path: Path, rows: List[Dict[str, Any]]) -> None:
    features = [to_feature(row) for row in rows if row.get("longitude") is not None and row.get("latitude") is not None]
    data = {"type": "FeatureCollection", "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    sql_path = root / "sql" / "01_geo_tables.sql"
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
    )
    try:
        execute_multi_sql(conn, load_sql_file(sql_path))

        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM rpt_geo_customer_daily WHERE biz_date BETWEEN %s AND %s", (args.start_date, args.end_date))
            cursor.execute(GEO_CUSTOMER_SQL, (args.start_date, args.end_date, args.start_date, args.end_date))
            if args.level in {"item", "all"}:
                cursor.execute("DELETE FROM rpt_geo_customer_item_daily WHERE biz_date BETWEEN %s AND %s", (args.start_date, args.end_date))
                cursor.execute(GEO_CUSTOMER_ITEM_SQL, (args.start_date, args.end_date))
        conn.commit()

        customer_rows = fetch_all(
            conn,
            """
            SELECT *
            FROM rpt_geo_customer_daily
            WHERE biz_date BETWEEN %s AND %s
            ORDER BY biz_date, shop_id
            """,
            (args.start_date, args.end_date),
        )
        hot_rows: List[Dict[str, Any]] = []
        if args.level in {"item", "all"}:
            hot_rows = fetch_all(
                conn,
                """
                SELECT *
                FROM rpt_geo_customer_item_daily
                WHERE biz_date BETWEEN %s AND %s
                  AND stock_sale_ratio IS NOT NULL
                ORDER BY stock_sale_ratio DESC, biz_date, shop_id
                LIMIT 5000
                """,
                (args.start_date, args.end_date),
            )

        write_csv(out_dir / "rpt_geo_customer_daily.csv", customer_rows)
        write_geojson(out_dir / "rpt_geo_customer_daily.geojson", customer_rows)
        if args.level in {"item", "all"}:
            write_csv(out_dir / "rpt_geo_customer_item_daily_top5000.csv", hot_rows)
            write_geojson(out_dir / "rpt_geo_customer_item_daily_top5000.geojson", hot_rows)

        print(f"date_range={args.start_date}..{args.end_date}")
        print(f"level={args.level}")
        print(f"customer_rows={len(customer_rows)}")
        print(f"hot_item_rows={len(hot_rows)}")
        print(f"output_dir={out_dir}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
