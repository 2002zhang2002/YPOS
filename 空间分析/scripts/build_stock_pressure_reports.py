import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import pymysql


INSERT_SQL_TEMPLATE = """
INSERT INTO rpt_customer_stock_pressure_daily (
  biz_date, shop_id, cust_id, license_code, cust_name, shop_name, cust_seg_name,
  terminal_level, base_type_name, work_port_name, sale_dept, ss_name, slsman,
  longitude, latitude, window_7d_start, window_30d_start,
  stock_qty_end, stock_amount_end, sale_qty_7d, sale_qty_30d,
  sale_amount_7d, sale_amount_30d, sale_days_7d, sale_days_30d,
  stock_sale_ratio_7d_m, stock_sale_ratio_30d, ratio_valid_7d, ratio_valid_30d,
  pressure_level_7d, pressure_level_30d
)
SELECT
  stock.biz_date,
  stock.shop_id,
  COALESCE(d.cust_id, stock.cust_id) AS cust_id,
  COALESCE(d.license_code, stock.license_code, stock.shop_id) AS license_code,
  COALESCE(d.cust_name, stock.shop_name) AS cust_name,
  stock.shop_name,
  COALESCE(d.cust_seg_name, stock.cust_seg_name) AS cust_seg_name,
  d.terminal_level,
  COALESCE(d.base_type_name, stock.base_type_name) AS base_type_name,
  COALESCE(d.work_port_name, stock.work_port_name) AS work_port_name,
  d.sale_dept,
  COALESCE(d.ss_name, stock.ss_name) AS ss_name,
  COALESCE(d.slsman, stock.slsman) AS slsman,
  d.longitude,
  d.latitude,
  %s AS window_7d_start,
  %s AS window_30d_start,
  stock.stock_qty_end,
  stock.stock_amount_end,
  COALESCE(s7.sale_qty_7d, 0) AS sale_qty_7d,
  COALESCE(s30.sale_qty_30d, 0) AS sale_qty_30d,
  COALESCE(s7.sale_amount_7d, 0) AS sale_amount_7d,
  COALESCE(s30.sale_amount_30d, 0) AS sale_amount_30d,
  COALESCE(s7.sale_days_7d, 0) AS sale_days_7d,
  COALESCE(s30.sale_days_30d, 0) AS sale_days_30d,
  CASE
    WHEN COALESCE(s7.sale_days_7d, 0) < 7 OR COALESCE(s7.sale_qty_7d, 0) = 0 THEN NULL
    ELSE stock.stock_qty_end / NULLIF((COALESCE(s7.sale_qty_7d, 0) / 7.0 * 30.0), 0)
  END AS stock_sale_ratio_7d_m,
  CASE
    WHEN COALESCE(s30.sale_days_30d, 0) < 30 OR COALESCE(s30.sale_qty_30d, 0) = 0 THEN NULL
    ELSE stock.stock_qty_end / NULLIF(COALESCE(s30.sale_qty_30d, 0), 0)
  END AS stock_sale_ratio_30d,
  CASE WHEN COALESCE(s7.sale_days_7d, 0) >= 7 THEN 1 ELSE 0 END AS ratio_valid_7d,
  CASE WHEN COALESCE(s30.sale_days_30d, 0) >= 30 THEN 1 ELSE 0 END AS ratio_valid_30d,
  CASE
    WHEN COALESCE(s7.sale_days_7d, 0) < 7 THEN '未满7天'
    WHEN COALESCE(s7.sale_qty_7d, 0) = 0 THEN '无销量'
    WHEN stock.stock_qty_end / NULLIF((COALESCE(s7.sale_qty_7d, 0) / 7.0 * 30.0), 0) < 0.80 THEN '紧张'
    WHEN stock.stock_qty_end / NULLIF((COALESCE(s7.sale_qty_7d, 0) / 7.0 * 30.0), 0) < 1.50 THEN '平衡'
    WHEN stock.stock_qty_end / NULLIF((COALESCE(s7.sale_qty_7d, 0) / 7.0 * 30.0), 0) < 2.50 THEN '偏高'
    ELSE '积压'
  END AS pressure_level_7d,
  CASE
    WHEN COALESCE(s30.sale_days_30d, 0) < 30 THEN '未满30天'
    WHEN COALESCE(s30.sale_qty_30d, 0) = 0 THEN '无销量'
    WHEN stock.stock_qty_end / NULLIF(COALESCE(s30.sale_qty_30d, 0), 0) < 0.80 THEN '紧张'
    WHEN stock.stock_qty_end / NULLIF(COALESCE(s30.sale_qty_30d, 0), 0) < 1.50 THEN '平衡'
    WHEN stock.stock_qty_end / NULLIF(COALESCE(s30.sale_qty_30d, 0), 0) < 2.50 THEN '偏高'
    ELSE '积压'
  END AS pressure_level_30d
FROM (
  SELECT
    f.biz_date,
    f.shop_id,
    MAX(f.cust_id) AS cust_id,
    MAX(f.license_code) AS license_code,
    MAX(f.shop_name) AS shop_name,
    MAX(f.cust_seg_name) AS cust_seg_name,
    MAX(f.base_type_name) AS base_type_name,
    MAX(f.work_port_name) AS work_port_name,
    MAX(f.ss_name) AS ss_name,
    MAX(f.slsman) AS slsman,
    SUM(COALESCE(f.t_big_stoamt, 0)) AS stock_qty_end,
    SUM(COALESCE(f.t_stockmny, 0)) AS stock_amount_end
  FROM fact_customer_item_daily f
  WHERE f.biz_date = %s
  GROUP BY f.biz_date, f.shop_id
) stock
LEFT JOIN (
  SELECT
    f.shop_id,
    COUNT(DISTINCT f.biz_date) AS sale_days_7d,
    SUM(COALESCE(f.t_big_saleamt, 0)) AS sale_qty_7d,
    SUM(COALESCE(f.t_salemny, 0)) AS sale_amount_7d
  FROM fact_customer_item_daily f
  WHERE f.biz_date BETWEEN %s AND %s
  GROUP BY f.shop_id
) s7
  ON s7.shop_id = stock.shop_id
LEFT JOIN (
  SELECT
    f.shop_id,
    COUNT(DISTINCT f.biz_date) AS sale_days_30d,
    SUM(COALESCE(f.t_big_saleamt, 0)) AS sale_qty_30d,
    SUM(COALESCE(f.t_salemny, 0)) AS sale_amount_30d
  FROM fact_customer_item_daily f
  WHERE f.biz_date BETWEEN %s AND %s
  GROUP BY f.shop_id
) s30
  ON s30.shop_id = stock.shop_id
LEFT JOIN dim_customer_profile d
  ON d.license_code = stock.shop_id
WHERE d.terminal_level IN ('二星', '三星')
{sale_dept_filter}
ON DUPLICATE KEY UPDATE
  cust_id = VALUES(cust_id),
  license_code = VALUES(license_code),
  cust_name = VALUES(cust_name),
  shop_name = VALUES(shop_name),
  cust_seg_name = VALUES(cust_seg_name),
  terminal_level = VALUES(terminal_level),
  base_type_name = VALUES(base_type_name),
  work_port_name = VALUES(work_port_name),
  sale_dept = VALUES(sale_dept),
  ss_name = VALUES(ss_name),
  slsman = VALUES(slsman),
  longitude = VALUES(longitude),
  latitude = VALUES(latitude),
  window_7d_start = VALUES(window_7d_start),
  window_30d_start = VALUES(window_30d_start),
  stock_qty_end = VALUES(stock_qty_end),
  stock_amount_end = VALUES(stock_amount_end),
  sale_qty_7d = VALUES(sale_qty_7d),
  sale_qty_30d = VALUES(sale_qty_30d),
  sale_amount_7d = VALUES(sale_amount_7d),
  sale_amount_30d = VALUES(sale_amount_30d),
  sale_days_7d = VALUES(sale_days_7d),
  sale_days_30d = VALUES(sale_days_30d),
  stock_sale_ratio_7d_m = VALUES(stock_sale_ratio_7d_m),
  stock_sale_ratio_30d = VALUES(stock_sale_ratio_30d),
  ratio_valid_7d = VALUES(ratio_valid_7d),
  ratio_valid_30d = VALUES(ratio_valid_30d),
  pressure_level_7d = VALUES(pressure_level_7d),
  pressure_level_30d = VALUES(pressure_level_30d),
  etl_loaded_at = CURRENT_TIMESTAMP
"""


SNAPSHOT_SQL_TEMPLATE = """
SELECT
  biz_date,
  shop_id,
  cust_id,
  license_code,
  cust_name,
  shop_name,
  cust_seg_name,
  terminal_level,
  base_type_name,
  work_port_name,
  sale_dept,
  ss_name,
  slsman,
  longitude,
  latitude,
  stock_qty_end,
  stock_amount_end,
  sale_qty_7d,
  sale_qty_30d,
  sale_days_7d,
  sale_days_30d,
  stock_sale_ratio_7d_m,
  stock_sale_ratio_30d,
  ratio_valid_7d,
  ratio_valid_30d,
  pressure_level_7d,
  pressure_level_30d
FROM rpt_customer_stock_pressure_daily
WHERE biz_date = %s
{sale_dept_filter}
ORDER BY stock_sale_ratio_30d DESC, stock_sale_ratio_7d_m DESC, stock_qty_end DESC
"""


TREND_SQL_TEMPLATE = """
SELECT
  biz_date,
  shop_id,
  cust_id,
  cust_name,
  shop_name,
  cust_seg_name,
  terminal_level,
  sale_dept,
  stock_qty_end,
  stock_amount_end,
  sale_qty_7d,
  sale_qty_30d,
  sale_days_7d,
  sale_days_30d,
  stock_sale_ratio_7d_m,
  stock_sale_ratio_30d,
  ratio_valid_7d,
  ratio_valid_30d,
  pressure_level_7d,
  pressure_level_30d
FROM rpt_customer_stock_pressure_daily
WHERE biz_date BETWEEN %s AND %s
{sale_dept_filter}
ORDER BY cust_id, biz_date
"""


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Build daily stock-pressure report table for 2-star/3-star customers.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="pos_ods")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--sale-dept", default="")
    parser.add_argument("--export-date", default="")
    parser.add_argument("--trend-days", type=int, default=45)
    parser.add_argument("--output-dir", default=str(root / "exports_stock_pressure"))
    parser.add_argument("--app-output", default=str(root.parent / "stock_pressure_app" / "data" / "stock_pressure_app_data.js"))
    return parser.parse_args()


def parse_date(text: str) -> dt.date:
    return dt.datetime.strptime(text, "%Y-%m-%d").date()


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def load_sql_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def execute_multi_sql(conn: Any, sql_text: str) -> None:
    statements = [part.strip() for part in sql_text.split(";") if part.strip()]
    with conn.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    conn.commit()


def ensure_report_columns(conn: Any) -> None:
    column_defs = {
        "sale_days_7d": "INT NULL",
        "sale_days_30d": "INT NULL",
        "ratio_valid_7d": "TINYINT(1) NOT NULL DEFAULT 0",
        "ratio_valid_30d": "TINYINT(1) NOT NULL DEFAULT 0",
    }
    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM rpt_customer_stock_pressure_daily")
        existing = {row[0] for row in cursor.fetchall()}
        for name, definition in column_defs.items():
            if name not in existing:
                cursor.execute(f"ALTER TABLE rpt_customer_stock_pressure_daily ADD COLUMN {name} {definition}")
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


def write_app_js(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "window.STOCK_PRESSURE_APP_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2, default=str) + ";\n"
    path.write_text(text, encoding="utf-8")


def build_insert_sql(sale_dept: str) -> str:
    sale_dept_filter = "  AND d.sale_dept = %s\n" if sale_dept else ""
    return INSERT_SQL_TEMPLATE.format(sale_dept_filter=sale_dept_filter)


def build_snapshot_sql(sale_dept: str) -> str:
    sale_dept_filter = "  AND sale_dept = %s\n" if sale_dept else ""
    return SNAPSHOT_SQL_TEMPLATE.format(sale_dept_filter=sale_dept_filter)


def build_trend_sql(sale_dept: str) -> str:
    sale_dept_filter = "  AND sale_dept = %s\n" if sale_dept else ""
    return TREND_SQL_TEMPLATE.format(sale_dept_filter=sale_dept_filter)


def rebuild_range(conn: Any, start: dt.date, end: dt.date, sale_dept: str) -> None:
    delete_sql = "DELETE FROM rpt_customer_stock_pressure_daily WHERE biz_date BETWEEN %s AND %s"
    delete_params: List[Any] = [start, end]
    if sale_dept:
        delete_sql += " AND sale_dept = %s"
        delete_params.append(sale_dept)
    with conn.cursor() as cursor:
        cursor.execute(delete_sql, delete_params)
    conn.commit()

    insert_sql = build_insert_sql(sale_dept)
    for day in daterange(start, end):
        window_7d_start = day - dt.timedelta(days=6)
        window_30d_start = day - dt.timedelta(days=29)
        params: List[Any] = [
            window_7d_start,
            window_30d_start,
            day,
            window_7d_start,
            day,
            window_30d_start,
            day,
        ]
        if sale_dept:
            params.append(sale_dept)
        with conn.cursor() as cursor:
            cursor.execute(insert_sql, params)
        conn.commit()


def main() -> int:
    args = parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    export_date = parse_date(args.export_date) if args.export_date else end_date
    trend_start = export_date - dt.timedelta(days=max(args.trend_days - 1, 0))

    script_root = Path(__file__).resolve().parent.parent
    sql_path = script_root / "sql" / "02_stock_pressure_tables.sql"
    output_dir = Path(args.output_dir)

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
        ensure_report_columns(conn)
        rebuild_range(conn, start_date, end_date, args.sale_dept)

        snapshot_sql = build_snapshot_sql(args.sale_dept)
        trend_sql = build_trend_sql(args.sale_dept)

        snapshot_params: List[Any] = [export_date]
        trend_params: List[Any] = [trend_start, export_date]
        if args.sale_dept:
            snapshot_params.append(args.sale_dept)
            trend_params.append(args.sale_dept)

        snapshot_rows = fetch_all(conn, snapshot_sql, snapshot_params)
        trend_rows = fetch_all(conn, trend_sql, trend_params)

        output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(output_dir / "rpt_customer_stock_pressure_latest.csv", snapshot_rows)
        write_geojson(output_dir / "rpt_customer_stock_pressure_latest.geojson", snapshot_rows)

        payload = {
          "generatedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "snapshotDate": export_date.isoformat(),
          "saleDept": args.sale_dept,
          "tileUrl": "http://10.60.176.37:4201/datacenter/lcgis/rest/maptile?x={x}&y={y}&z={z}",
          "snapshotRows": snapshot_rows,
          "trendRows": trend_rows,
        }
        write_app_js(Path(args.app_output), payload)

        print(f"snapshot_rows={len(snapshot_rows)}")
        print(f"trend_rows={len(trend_rows)}")
        print(f"output_dir={output_dir}")
        print(f"app_output={args.app_output}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
