"""客户历史明细采集脚本。

脚本职责：
1. 从 POS 接口拉取门店列表。
2. 按日期、按门店抓取 getDataList，支持店铺汇总和商品明细两种粒度。
3. 将结果按主键幂等写入本地 ODS（SQLite）或 MySQL。
4. 可选执行单日验证，检查每个门店明细条数是否达到预期阈值。
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

try:
    import pymysql
except ImportError:
    pymysql = None


THREAD_LOCAL = threading.local()


SQLITE_DDL_SQL = """
CREATE TABLE IF NOT EXISTS ods_customer_item_daily (
    biz_date TEXT NOT NULL,
    saleorg_id TEXT,
    shop_id TEXT NOT NULL,
    shop_name TEXT,
    tenant_id TEXT,
    cust_id TEXT,
    sale_center TEXT,
    ss_name TEXT,
    slsman TEXT,
    item_name TEXT,
    barcode TEXT,
    big_barcode TEXT,
    item_key TEXT NOT NULL,
    t_big_stoamt REAL,
    t_big_saleamt REAL,
    t_big_stockamt REAL,
    raw_json TEXT NOT NULL,
    etl_loaded_at TEXT NOT NULL,
    PRIMARY KEY (biz_date, shop_id, item_key)
);

CREATE INDEX IF NOT EXISTS idx_ods_biz_date ON ods_customer_item_daily (biz_date);
CREATE INDEX IF NOT EXISTS idx_ods_shop_id ON ods_customer_item_daily (shop_id);
CREATE INDEX IF NOT EXISTS idx_ods_cust_id ON ods_customer_item_daily (cust_id);
"""


SQLITE_UPSERT_SQL = """
INSERT INTO ods_customer_item_daily (
    biz_date,
    saleorg_id,
    shop_id,
    shop_name,
    tenant_id,
    cust_id,
    sale_center,
    ss_name,
    slsman,
    item_name,
    barcode,
    big_barcode,
    item_key,
    t_big_stoamt,
    t_big_saleamt,
    t_big_stockamt,
    raw_json,
    etl_loaded_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(biz_date, shop_id, item_key)
DO UPDATE SET
    saleorg_id = excluded.saleorg_id,
    shop_name = excluded.shop_name,
    tenant_id = excluded.tenant_id,
    cust_id = excluded.cust_id,
    sale_center = excluded.sale_center,
    ss_name = excluded.ss_name,
    slsman = excluded.slsman,
    item_name = excluded.item_name,
    barcode = excluded.barcode,
    big_barcode = excluded.big_barcode,
    t_big_stoamt = excluded.t_big_stoamt,
    t_big_saleamt = excluded.t_big_saleamt,
    t_big_stockamt = excluded.t_big_stockamt,
    raw_json = excluded.raw_json,
    etl_loaded_at = excluded.etl_loaded_at
"""


MYSQL_DDL_SQL = """
CREATE TABLE IF NOT EXISTS fact_customer_shop_daily (
    biz_date DATE NOT NULL,
    saleorg_id VARCHAR(32) NULL,
    shop_id VARCHAR(64) NOT NULL,
    shop_name VARCHAR(255) NULL,
    tenant_id VARCHAR(64) NULL,
    cust_id VARCHAR(64) NOT NULL,
    license_code VARCHAR(64) NULL,
    sale_center VARCHAR(128) NULL,
    ss_name VARCHAR(128) NULL,
    slsman VARCHAR(128) NULL,
    base_type_name VARCHAR(128) NULL,
    work_port_name VARCHAR(64) NULL,
    cust_seg_name VARCHAR(64) NULL,
    t_big_stoamt DECIMAL(18,4) NULL,
    t_big_saleamt DECIMAL(18,4) NULL,
    t_big_stockamt DECIMAL(18,4) NULL,
    t_actual_saleamt DECIMAL(18,4) NULL,
    t_actual_salemny DECIMAL(18,4) NULL,
    t_salemny DECIMAL(18,4) NULL,
    t_stomny DECIMAL(18,4) NULL,
    t_stockmny DECIMAL(18,4) NULL,
    sto_sale DECIMAL(18,4) NULL,
    sale_stock DECIMAL(18,4) NULL,
    stock_sale DECIMAL(18,4) NULL,
    raw_json JSON NULL,
    etl_loaded_at DATETIME NOT NULL,
    PRIMARY KEY (biz_date, shop_id),
    KEY idx_shop_daily_cust_date (cust_id, biz_date),
    KEY idx_shop_daily_center_date (sale_center, ss_name, biz_date),
    KEY idx_shop_daily_loaded_at (etl_loaded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS fact_customer_item_daily (
    biz_date DATE NOT NULL,
    saleorg_id VARCHAR(32) NULL,
    shop_id VARCHAR(64) NOT NULL,
    shop_name VARCHAR(255) NULL,
    tenant_id VARCHAR(64) NULL,
    cust_id VARCHAR(64) NOT NULL,
    license_code VARCHAR(64) NULL,
    sale_center VARCHAR(128) NULL,
    ss_name VARCHAR(128) NULL,
    slsman VARCHAR(128) NULL,
    base_type_name VARCHAR(128) NULL,
    work_port_name VARCHAR(64) NULL,
    cust_seg_name VARCHAR(64) NULL,
    item_name VARCHAR(255) NULL,
    barcode VARCHAR(64) NULL,
    big_barcode VARCHAR(64) NULL,
    item_key VARCHAR(128) NOT NULL,
    big_price DECIMAL(18,4) NULL,
    small_price DECIMAL(18,4) NULL,
    big_avg_price DECIMAL(18,4) NULL,
    small_big DECIMAL(18,4) NULL,
    t_big_stoamt DECIMAL(18,4) NULL,
    t_big_saleamt DECIMAL(18,4) NULL,
    t_big_stockamt DECIMAL(18,4) NULL,
    t_actual_saleamt DECIMAL(18,4) NULL,
    t_actual_salemny DECIMAL(18,4) NULL,
    t_salemny DECIMAL(18,4) NULL,
    t_stomny DECIMAL(18,4) NULL,
    t_stockmny DECIMAL(18,4) NULL,
    t_change_amt DECIMAL(18,4) NULL,
    t_change_mny DECIMAL(18,4) NULL,
    t_org_stomny DECIMAL(18,4) NULL,
    t_big_org_stoamt DECIMAL(18,4) NULL,
    t_big_actual_saleamt DECIMAL(18,4) NULL,
    t_big_actual_salemny DECIMAL(18,4) NULL,
    sto_sale DECIMAL(18,4) NULL,
    sale_stock DECIMAL(18,4) NULL,
    stock_sale DECIMAL(18,4) NULL,
    raw_json JSON NULL,
    etl_loaded_at DATETIME NOT NULL,
    PRIMARY KEY (biz_date, shop_id, item_key),
    KEY idx_fact_cust_date (cust_id, biz_date),
    KEY idx_fact_shop_date (shop_id, biz_date),
    KEY idx_fact_item_date (item_key, biz_date),
    KEY idx_fact_barcode_date (barcode, biz_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


MYSQL_ITEM_TABLE_EXTRA_COLUMNS = {
    "license_code": "VARCHAR(64) NULL",
    "base_type_name": "VARCHAR(128) NULL",
    "work_port_name": "VARCHAR(64) NULL",
    "cust_seg_name": "VARCHAR(64) NULL",
    "big_price": "DECIMAL(18,4) NULL",
    "small_price": "DECIMAL(18,4) NULL",
    "big_avg_price": "DECIMAL(18,4) NULL",
    "small_big": "DECIMAL(18,4) NULL",
    "t_actual_saleamt": "DECIMAL(18,4) NULL",
    "t_actual_salemny": "DECIMAL(18,4) NULL",
    "t_salemny": "DECIMAL(18,4) NULL",
    "t_stomny": "DECIMAL(18,4) NULL",
    "t_stockmny": "DECIMAL(18,4) NULL",
    "t_change_amt": "DECIMAL(18,4) NULL",
    "t_change_mny": "DECIMAL(18,4) NULL",
    "t_org_stomny": "DECIMAL(18,4) NULL",
    "t_big_org_stoamt": "DECIMAL(18,4) NULL",
    "t_big_actual_saleamt": "DECIMAL(18,4) NULL",
    "t_big_actual_salemny": "DECIMAL(18,4) NULL",
    "sto_sale": "DECIMAL(18,4) NULL",
    "sale_stock": "DECIMAL(18,4) NULL",
    "stock_sale": "DECIMAL(18,4) NULL",
}


MYSQL_UPSERT_SQL_SHOP_DAILY = """
INSERT INTO fact_customer_shop_daily (
    biz_date,
    saleorg_id,
    shop_id,
    shop_name,
    tenant_id,
    cust_id,
    license_code,
    sale_center,
    ss_name,
    slsman,
    base_type_name,
    work_port_name,
    cust_seg_name,
    t_big_stoamt,
    t_big_saleamt,
    t_big_stockamt,
    t_actual_saleamt,
    t_actual_salemny,
    t_salemny,
    t_stomny,
    t_stockmny,
    sto_sale,
    sale_stock,
    stock_sale,
    raw_json,
    etl_loaded_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    saleorg_id = VALUES(saleorg_id),
    shop_name = VALUES(shop_name),
    tenant_id = VALUES(tenant_id),
    cust_id = VALUES(cust_id),
    license_code = VALUES(license_code),
    sale_center = VALUES(sale_center),
    ss_name = VALUES(ss_name),
    slsman = VALUES(slsman),
    base_type_name = VALUES(base_type_name),
    work_port_name = VALUES(work_port_name),
    cust_seg_name = VALUES(cust_seg_name),
    t_big_stoamt = VALUES(t_big_stoamt),
    t_big_saleamt = VALUES(t_big_saleamt),
    t_big_stockamt = VALUES(t_big_stockamt),
    t_actual_saleamt = VALUES(t_actual_saleamt),
    t_actual_salemny = VALUES(t_actual_salemny),
    t_salemny = VALUES(t_salemny),
    t_stomny = VALUES(t_stomny),
    t_stockmny = VALUES(t_stockmny),
    sto_sale = VALUES(sto_sale),
    sale_stock = VALUES(sale_stock),
    stock_sale = VALUES(stock_sale),
    raw_json = VALUES(raw_json),
    etl_loaded_at = VALUES(etl_loaded_at)
"""


MYSQL_UPSERT_SQL = """
INSERT INTO fact_customer_item_daily (
    biz_date,
    saleorg_id,
    shop_id,
    shop_name,
    tenant_id,
    cust_id,
    license_code,
    sale_center,
    ss_name,
    slsman,
    base_type_name,
    work_port_name,
    cust_seg_name,
    item_name,
    barcode,
    big_barcode,
    item_key,
    big_price,
    small_price,
    big_avg_price,
    small_big,
    t_big_stoamt,
    t_big_saleamt,
    t_big_stockamt,
    t_actual_saleamt,
    t_actual_salemny,
    t_salemny,
    t_stomny,
    t_stockmny,
    t_change_amt,
    t_change_mny,
    t_org_stomny,
    t_big_org_stoamt,
    t_big_actual_saleamt,
    t_big_actual_salemny,
    sto_sale,
    sale_stock,
    stock_sale,
    raw_json,
    etl_loaded_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    saleorg_id = VALUES(saleorg_id),
    shop_name = VALUES(shop_name),
    tenant_id = VALUES(tenant_id),
    cust_id = VALUES(cust_id),
    license_code = VALUES(license_code),
    sale_center = VALUES(sale_center),
    ss_name = VALUES(ss_name),
    slsman = VALUES(slsman),
    base_type_name = VALUES(base_type_name),
    work_port_name = VALUES(work_port_name),
    cust_seg_name = VALUES(cust_seg_name),
    item_name = VALUES(item_name),
    barcode = VALUES(barcode),
    big_barcode = VALUES(big_barcode),
    big_price = VALUES(big_price),
    small_price = VALUES(small_price),
    big_avg_price = VALUES(big_avg_price),
    small_big = VALUES(small_big),
    t_big_stoamt = VALUES(t_big_stoamt),
    t_big_saleamt = VALUES(t_big_saleamt),
    t_big_stockamt = VALUES(t_big_stockamt),
    t_actual_saleamt = VALUES(t_actual_saleamt),
    t_actual_salemny = VALUES(t_actual_salemny),
    t_salemny = VALUES(t_salemny),
    t_stomny = VALUES(t_stomny),
    t_stockmny = VALUES(t_stockmny),
    t_change_amt = VALUES(t_change_amt),
    t_change_mny = VALUES(t_change_mny),
    t_org_stomny = VALUES(t_org_stomny),
    t_big_org_stoamt = VALUES(t_big_org_stoamt),
    t_big_actual_saleamt = VALUES(t_big_actual_saleamt),
    t_big_actual_salemny = VALUES(t_big_actual_salemny),
    sto_sale = VALUES(sto_sale),
    sale_stock = VALUES(sale_stock),
    stock_sale = VALUES(stock_sale),
    raw_json = VALUES(raw_json),
    etl_loaded_at = VALUES(etl_loaded_at)
"""


def current_yyyymmdd() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def current_ts_ms() -> str:
    return str(int(time.time() * 1000))


def parse_yyyymmdd(text: str) -> dt.date:
    value = str(text or "").strip()
    if not re.fullmatch(r"\d{8}", value):
        raise ValueError(f"expected YYYYMMDD 8 digits, got {value!r}")
    return dt.datetime.strptime(value, "%Y%m%d").date()


def validate_date_config(name: str, value: str, required: bool = True) -> bool:
    text = str(value or "").strip()
    if not text and not required:
        return True
    try:
        parse_yyyymmdd(text)
        return True
    except ValueError as exc:
        print(f"config date invalid: {name}={text!r}; {exc}")
        return False


def to_yyyymmdd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def to_mysql_date(text: str) -> str:
    return parse_yyyymmdd(text).strftime("%Y-%m-%d")


def normalize_base_url(raw_base_url: str) -> str:
    raw = (raw_base_url or "").strip()
    if not raw:
        return ""

    parsed = urlsplit(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"

    cleaned = raw.split("/")[0]
    return f"http://{cleaned}"


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    if not cookie_header:
        return cookies

    parts = [p.strip() for p in cookie_header.split(";") if p.strip()]
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def load_json(path: Path, default_value: Any) -> Any:
    if not path.exists():
        return default_value
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_value(cli_value: Any, cfg: Dict[str, Any], key: str, default_value: Any) -> Any:
    if cli_value not in (None, ""):
        return cli_value
    if key in cfg and cfg[key] not in (None, ""):
        return cfg[key]
    return default_value


def parse_bool(value: Any, default_value: bool = False) -> bool:
    """Parse JSON/config booleans safely, including string values from GUI edits."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default_value
    text = str(value).strip().lower()
    if not text:
        return default_value
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default_value


def contains_placeholder(text: str) -> bool:
    """Return True when a config value still looks like a placeholder."""
    value = (text or "").strip()
    if not value:
        return False
    markers = ("TODO", "REPLACE_ME", "example")
    return any(marker.lower() in value.lower() for marker in markers)


def is_latin1_encodable(text: str) -> bool:
    """HTTP headers must be encodable as latin-1."""
    try:
        (text or "").encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    headers: Dict[str, str],
    timeout: int,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        resp = session.request(method=method, url=url, headers=headers, params=params, data=data, timeout=timeout)
    except UnicodeEncodeError as exc:
        raise RuntimeError("request header or cookie contains non-latin-1 characters") from exc
    resp.raise_for_status()

    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid payload type: {type(payload)}")
    return payload


def build_common_headers(base_url: str, token: str) -> Dict[str, str]:
    host = base_url.rstrip("/")
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": host,
        "Referer": host + "/foa/analysis/cigaretteshopJXCday",
        "token": token,
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }


def create_session(cookie_dict: Dict[str, str]) -> requests.Session:
    session = requests.Session()
    if cookie_dict:
        session.cookies.update(cookie_dict)
    return session


def get_thread_session(cookie_dict: Dict[str, str]) -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = create_session(cookie_dict)
        THREAD_LOCAL.session = session
    return session


def normalize_shop_row(row: Dict[str, Any]) -> Dict[str, str]:
    return {
        "shop_id": str(row.get("SHOP_ID") or row.get("shop_id") or "").strip(),
        "shop_name": str(row.get("SHOP_NAME") or row.get("shop_name") or "").strip(),
        "tenant_id": str(row.get("TENANT_ID") or row.get("tenant_id") or "").strip(),
        "org_code": str(row.get("ORG_CODE") or row.get("org_code") or "").strip(),
    }


def fetch_shop_list_all(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    timeout: int,
    saleorg_id: str,
    limit: int,
    query_type: str,
) -> List[Dict[str, str]]:
    """Fetch all shops with pagination and de-duplication."""
    url = base_url.rstrip("/") + "/soa/common/shophelper/getShopList"
    offset = 0
    shops: List[Dict[str, str]] = []
    seen_shop_ids = set()

    while True:
        params = {
            "t": current_ts_ms(),
            "offset": str(offset),
            "limit": str(limit),
            "dpId": "",
            "orgCode": "",
            "nameBarSearch": "",
            "queryType": query_type,
            "isShopIn": "",
            "isFrontPage": "false",
            "saleCenterSearch": "",
            "saleorgIdSearch": saleorg_id,
            "slsmanIdSearch": "",
        }
        payload = request_json(session, "GET", url, headers, timeout, params=params)
        if payload.get("code") != 200:
            raise RuntimeError(f"getShopList failed: {payload}")

        data = payload.get("data") or {}
        rows = data.get("rows") or []
        if not isinstance(rows, list):
            raise RuntimeError(f"getShopList rows invalid: {data}")
        if not rows:
            break

        for row in rows:
            if not isinstance(row, dict):
                continue
            item = normalize_shop_row(row)
            shop_id = item["shop_id"]
            if not shop_id or shop_id in seen_shop_ids:
                continue
            seen_shop_ids.add(shop_id)
            shops.append(item)

        print(f"[getShopList] page rows={len(rows)} offset={offset} total_shops={len(shops)}")
        if len(rows) < limit:
            break
        offset += limit

    return shops


def build_data_list_form(
    offset: int,
    limit: int,
    biz_date: str,
    saleorg_id: str,
    shop_id: str,
    agg_item: str,
) -> Dict[str, str]:
    """Build getDataList form parameters for a shop/day request."""
    return {
        "offset": str(offset),
        "limit": str(limit),
        "agg_item": agg_item,
        "queryType": "day",
        "beginDate": biz_date,
        "endDate": biz_date,
        "weekMonth": "",
        "saleCenterSearch": "",
        "saleorgIdSearch": saleorg_id,
        "serviceIdSearch": "",
        "slsmanIdSearch": "",
        "custSearch": "",
        "custSeg": "",
        "isMicCustSearch": "",
        "workPort": "",
        "custSampleType": "",
        "areaType": "",
        "baseType": "",
        "kindSearch": "",
        "priceSegmentSearch": "",
        "yieldlyTypeSearch": "",
        "tenantIds": "",
        "shopIds": shop_id,
        "searchValue": "",
        "barcodeSearch": "",
        "creditGrade": "",
        "cust_seg_ext": "",
    }


def fetch_data_list_rows_for_shop_day(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    timeout: int,
    saleorg_id: str,
    shop_id: str,
    biz_date: str,
    limit: int,
    agg_item: str,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch all rows for one shop/day with automatic pagination."""
    url = base_url.rstrip("/") + "/soa/analysis/cigaretteshopJXCmth/getDataList"
    offset = 0
    rows_all: List[Dict[str, Any]] = []
    server_total = 0

    while True:
        form = build_data_list_form(
            offset=offset,
            limit=limit,
            biz_date=biz_date,
            saleorg_id=saleorg_id,
            shop_id=shop_id,
            agg_item=agg_item,
        )
        payload = request_json(session, "POST", url, headers, timeout, data=form)
        if payload.get("code") != 200:
            raise RuntimeError(f"getDataList failed: {payload}")

        data = payload.get("data") or {}
        rows = data.get("rows") or []
        server_total = int(data.get("total") or 0)
        if not isinstance(rows, list):
            raise RuntimeError(f"getDataList rows invalid: {data}")

        rows_all.extend(rows)
        if not rows:
            break
        if server_total > 0 and len(rows_all) >= server_total:
            break
        if server_total <= 0 and len(rows) < limit:
            break
        offset += limit

    return rows_all, server_total


def fetch_rows_for_single_shop_day(
    base_url: str,
    headers: Dict[str, str],
    timeout: int,
    saleorg_id: str,
    shop: Dict[str, str],
    biz_date: str,
    limit: int,
    agg_item: str,
    cookie_dict: Dict[str, str],
) -> Tuple[Dict[str, str], List[Dict[str, Any]], int]:
    """Fetch summary rows for a single shop/day."""
    session = get_thread_session(cookie_dict)
    shop_id = shop.get("shop_id", "")
    rows, server_total = fetch_data_list_rows_for_shop_day(
        session=session,
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        saleorg_id=saleorg_id,
        shop_id=shop_id,
        biz_date=biz_date,
        limit=limit,
        agg_item=agg_item,
    )
    return shop, rows, server_total


def fetch_dual_rows_for_single_shop_day(
    base_url: str,
    headers: Dict[str, str],
    timeout: int,
    saleorg_id: str,
    shop: Dict[str, str],
    biz_date: str,
    limit: int,
    agg_item: str,
    cookie_dict: Dict[str, str],
    fetch_shop_summary: bool,
    fetch_item_detail: bool,
) -> Tuple[Dict[str, str], List[Dict[str, Any]], int, List[Dict[str, Any]], int]:
    """Fetch shop summary and item detail in the same worker for real parallelism."""
    shop_rows: List[Dict[str, Any]] = []
    item_rows: List[Dict[str, Any]] = []
    shop_total = 0
    item_total = 0
    if fetch_shop_summary:
        _, shop_rows, shop_total = fetch_rows_for_single_shop_day(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            saleorg_id=saleorg_id,
            shop=shop,
            biz_date=biz_date,
            limit=limit,
            agg_item=agg_item,
            cookie_dict=cookie_dict,
        )
    if fetch_item_detail:
        _, item_rows, item_total = fetch_item_detail_rows_for_single_shop_day(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            saleorg_id=saleorg_id,
            shop=shop,
            biz_date=biz_date,
            limit=limit,
            cookie_dict=cookie_dict,
        )
    return shop, shop_rows, shop_total, item_rows, item_total


def fetch_item_detail_rows_for_single_shop_day(
    base_url: str,
    headers: Dict[str, str],
    timeout: int,
    saleorg_id: str,
    shop: Dict[str, str],
    biz_date: str,
    limit: int,
    cookie_dict: Dict[str, str],
) -> Tuple[Dict[str, str], List[Dict[str, Any]], int]:
    """Fetch item-level daily detail using the specifications daily page parameter pattern."""
    session = get_thread_session(cookie_dict)
    shop_id = shop.get("shop_id", "")
    tenant_id = shop.get("tenant_id", "") or shop_id
    url = base_url.rstrip("/") + "/soa/analysis/cigaretteshopJXCmth/getDataList"
    offset = 0
    rows_all: List[Dict[str, Any]] = []
    server_total = 0

    while True:
        form = {
            "offset": str(offset),
            "limit": str(limit),
            "agg_item": "shop_barcode",
            "queryType": "day",
            "beginDate": biz_date,
            "endDate": biz_date,
            "weekMonth": "",
            "saleCenterSearch": "",
            "saleorgIdSearch": saleorg_id,
            "serviceIdSearch": "",
            "slsmanIdSearch": "",
            "custSearch": "",
            "custSeg": "",
            "isMicCustSearch": "",
            "workPort": "",
            "baseType": "",
            "kindSearch": "",
            "priceSegmentSearch": "",
            "yieldlyTypeSearch": "",
            "tenantIds": tenant_id,
            "shopIds": shop_id,
            "barcodeSearch": "",
            "begin_date_Week": "",
            "end_date_Week": "",
            "custSampleType": "",
            "areaType": "",
            "creditGrade": "",
            "cust_seg_ext": "",
        }
        payload = request_json(session, "POST", url, headers, timeout, data=form)
        if payload.get("code") != 200:
            raise RuntimeError(f"item detail getDataList failed: {payload}")

        data = payload.get("data") or {}
        rows = data.get("rows") or []
        server_total = int(data.get("total") or 0)
        if not isinstance(rows, list):
            raise RuntimeError(f"item detail rows invalid: {data}")

        rows_all.extend(rows)
        if not rows:
            break
        if server_total > 0 and len(rows_all) >= server_total:
            break
        if server_total <= 0 and len(rows) < limit:
            break
        offset += limit

    return shop, rows_all, server_total

def pick_row_value(row: Dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    upper_key = key.upper()
    if upper_key in row:
        return row.get(upper_key)
    return None


def to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def build_item_key(row: Dict[str, Any]) -> str:
    for key in ("big_barcode", "barcode", "item_name"):
        value = str(pick_row_value(row, key) or "").strip()
        if value:
            return value
    return "_UNKNOWN_ITEM_"


def build_upsert_payload(
    storage_backend: str,
    rows: List[Dict[str, Any]],
    biz_date: str,
    saleorg_id: str,
    fallback_shop_id: str,
    fallback_shop_name: str,
    fallback_tenant_id: str,
) -> List[Tuple[Any, ...]]:
    """Build backend-specific payload rows for SQLite or MySQL."""
    if not rows:
        return []

    now_text = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_biz_date = to_mysql_date(biz_date) if storage_backend == "mysql" else biz_date
    payload: List[Tuple[Any, ...]] = []

    for row in rows:
        shop_id = str(pick_row_value(row, "shop_id") or fallback_shop_id or "").strip()
        shop_name = str(pick_row_value(row, "shop_name") or fallback_shop_name or "").strip()
        tenant_id = str(pick_row_value(row, "tenant_id") or fallback_tenant_id or "").strip()
        cust_id = str(pick_row_value(row, "cust_id") or "").strip()
        sale_center = str(pick_row_value(row, "sale_center") or "").strip()
        ss_name = str(pick_row_value(row, "ss_name") or "").strip()
        slsman = str(pick_row_value(row, "slsman") or "").strip()
        item_name = str(pick_row_value(row, "item_name") or "").strip()
        barcode = str(pick_row_value(row, "barcode") or "").strip()
        big_barcode = str(pick_row_value(row, "big_barcode") or "").strip()
        item_key = build_item_key(row)

        payload.append(
            (
                db_biz_date,
                saleorg_id,
                shop_id,
                shop_name,
                tenant_id,
                cust_id,
                str(pick_row_value(row, "license_code") or "").strip(),
                sale_center,
                ss_name,
                slsman,
                str(pick_row_value(row, "base_type_name") or "").strip(),
                str(pick_row_value(row, "work_port_name") or "").strip(),
                str(pick_row_value(row, "cust_seg_name") or "").strip(),
                item_name,
                barcode,
                big_barcode,
                item_key,
                to_float(pick_row_value(row, "big_price")),
                to_float(pick_row_value(row, "small_price")),
                to_float(pick_row_value(row, "big_avg_price")),
                to_float(pick_row_value(row, "small_big")),
                to_float(pick_row_value(row, "t_big_stoamt")),
                to_float(pick_row_value(row, "t_big_saleamt")),
                to_float(pick_row_value(row, "t_big_stockamt")),
                to_float(pick_row_value(row, "t_actual_saleamt")),
                to_float(pick_row_value(row, "t_actual_salemny")),
                to_float(pick_row_value(row, "t_salemny")),
                to_float(pick_row_value(row, "t_stomny")),
                to_float(pick_row_value(row, "t_stockmny")),
                to_float(pick_row_value(row, "t_change_amt")),
                to_float(pick_row_value(row, "t_change_mny")),
                to_float(pick_row_value(row, "t_org_stomny")),
                to_float(pick_row_value(row, "t_big_org_stoamt")),
                to_float(pick_row_value(row, "t_big_actual_saleamt")),
                to_float(pick_row_value(row, "t_big_actual_salemny")),
                to_float(pick_row_value(row, "sto_sale")),
                to_float(pick_row_value(row, "sale_stock")),
                to_float(pick_row_value(row, "stock_sale")),
                json.dumps(row, ensure_ascii=False),
                now_text,
            )
        )

    return payload


def build_shop_daily_upsert_payload(
    storage_backend: str,
    rows: List[Dict[str, Any]],
    biz_date: str,
    saleorg_id: str,
    fallback_shop_id: str,
    fallback_shop_name: str,
    fallback_tenant_id: str,
) -> List[Tuple[Any, ...]]:
    """Build shop-level daily summary payload for MySQL."""
    if not rows:
        return []

    now_text = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_biz_date = to_mysql_date(biz_date) if storage_backend == "mysql" else biz_date
    payload: List[Tuple[Any, ...]] = []

    for row in rows:
        shop_id = str(pick_row_value(row, "shop_id") or fallback_shop_id or "").strip()
        shop_name = str(pick_row_value(row, "shop_name") or fallback_shop_name or "").strip()
        tenant_id = str(pick_row_value(row, "tenant_id") or fallback_tenant_id or "").strip()
        payload.append(
            (
                db_biz_date,
                saleorg_id,
                shop_id,
                shop_name,
                tenant_id,
                str(pick_row_value(row, "cust_id") or "").strip(),
                str(pick_row_value(row, "license_code") or "").strip(),
                str(pick_row_value(row, "sale_center") or "").strip(),
                str(pick_row_value(row, "ss_name") or "").strip(),
                str(pick_row_value(row, "slsman") or "").strip(),
                str(pick_row_value(row, "base_type_name") or "").strip(),
                str(pick_row_value(row, "work_port_name") or "").strip(),
                str(pick_row_value(row, "cust_seg_name") or "").strip(),
                to_float(pick_row_value(row, "t_big_stoamt")),
                to_float(pick_row_value(row, "t_big_saleamt")),
                to_float(pick_row_value(row, "t_big_stockamt")),
                to_float(pick_row_value(row, "t_actual_saleamt")),
                to_float(pick_row_value(row, "t_actual_salemny")),
                to_float(pick_row_value(row, "t_salemny")),
                to_float(pick_row_value(row, "t_stomny")),
                to_float(pick_row_value(row, "t_stockmny")),
                to_float(pick_row_value(row, "sto_sale")),
                to_float(pick_row_value(row, "sale_stock")),
                to_float(pick_row_value(row, "stock_sale")),
                json.dumps(row, ensure_ascii=False),
                now_text,
            )
        )
    return payload


def upsert_shop_daily_rows(
    conn: Any,
    storage_backend: str,
    rows: List[Dict[str, Any]],
    biz_date: str,
    saleorg_id: str,
    fallback_shop_id: str,
    fallback_shop_name: str,
    fallback_tenant_id: str,
) -> int:
    """Upsert shop-level daily rows into MySQL."""
    payload = build_shop_daily_upsert_payload(
        storage_backend=storage_backend,
        rows=rows,
        biz_date=biz_date,
        saleorg_id=saleorg_id,
        fallback_shop_id=fallback_shop_id,
        fallback_shop_name=fallback_shop_name,
        fallback_tenant_id=fallback_tenant_id,
    )
    if not payload:
        return 0

    if storage_backend == "mysql":
        with conn.cursor() as cursor:
            cursor.executemany(MYSQL_UPSERT_SQL_SHOP_DAILY, payload)
        return len(payload)

    return 0


def upsert_rows(
    conn: Any,
    storage_backend: str,
    rows: List[Dict[str, Any]],
    biz_date: str,
    saleorg_id: str,
    fallback_shop_id: str,
    fallback_shop_name: str,
    fallback_tenant_id: str,
) -> int:
    """Upsert fetched rows into the configured backend."""
    payload = build_upsert_payload(
        storage_backend=storage_backend,
        rows=rows,
        biz_date=biz_date,
        saleorg_id=saleorg_id,
        fallback_shop_id=fallback_shop_id,
        fallback_shop_name=fallback_shop_name,
        fallback_tenant_id=fallback_tenant_id,
    )
    if not payload:
        return 0

    if storage_backend == "mysql":
        with conn.cursor() as cursor:
            cursor.executemany(MYSQL_UPSERT_SQL, payload)
    else:
        conn.executemany(SQLITE_UPSERT_SQL, payload)
    return len(payload)


def init_sqlite_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the local SQLite ODS file."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SQLITE_DDL_SQL)
    return conn


def init_mysql_db(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    charset: str,
    connect_timeout: int,
) -> Any:
    """Initialize MySQL connection and ensure dual fact tables exist."""
    if pymysql is None:
        raise RuntimeError("storage_backend=mysql but PyMySQL is not installed")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset=charset,
        connect_timeout=connect_timeout,
        autocommit=False,
    )
    with conn.cursor() as cursor:
        for statement in split_mysql_statements(MYSQL_DDL_SQL):
            cursor.execute(statement)
        ensure_mysql_item_table_columns(cursor)
    return conn


def ensure_mysql_item_table_columns(cursor: Any) -> None:
    cursor.execute("SHOW COLUMNS FROM fact_customer_item_daily")
    existing_columns = {str(row[0]).lower() for row in cursor.fetchall()}
    for column_name, column_type in MYSQL_ITEM_TABLE_EXTRA_COLUMNS.items():
        if column_name.lower() not in existing_columns:
            cursor.execute(f"ALTER TABLE fact_customer_item_daily ADD COLUMN {column_name} {column_type}")


def split_mysql_statements(sql_text: str) -> List[str]:
    """Split simple semicolon-terminated DDL text for PyMySQL execution."""
    statements: List[str] = []
    current: List[str] = []
    in_single_quote = False
    in_double_quote = False
    previous = ""
    for char in sql_text:
        if char == "'" and not in_double_quote and previous != "\\":
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and previous != "\\":
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        previous = char

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def init_storage(
    storage_backend: str,
    sqlite_path: Path,
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_password: str,
    mysql_database: str,
    mysql_charset: str,
    mysql_connect_timeout: int,
) -> Tuple[Any, str]:
    """Initialize the selected storage backend and return a display name."""
    if storage_backend == "mysql":
        conn = init_mysql_db(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            database=mysql_database,
            charset=mysql_charset,
            connect_timeout=mysql_connect_timeout,
        )
        return conn, f"mysql://{mysql_user}@{mysql_host}:{mysql_port}/{mysql_database}.fact_customer_item_daily"

    conn = init_sqlite_db(sqlite_path)
    return conn, str(sqlite_path)


def compute_date_range(
    mode: str,
    history_start_date: str,
    history_end_date: str,
    daily_lag_days: int,
    max_days_per_run: int,
    state: Dict[str, Any],
) -> List[str]:
    """Compute pending dates for the selected run mode."""
    today = dt.date.today()
    default_end = today - dt.timedelta(days=daily_lag_days)

    if mode == "daily":
        return [to_yyyymmdd(default_end)]

    start = parse_yyyymmdd(history_start_date)
    end = parse_yyyymmdd(history_end_date) if history_end_date else default_end
    if end < start:
        return []

    if mode == "auto":
        last_completed = str(state.get("last_completed_date") or "").strip()
        if last_completed:
            try:
                next_start = parse_yyyymmdd(last_completed) + dt.timedelta(days=1)
                if next_start > start:
                    start = next_start
            except ValueError:
                pass

    dates: List[str] = []
    current = start
    while current <= end and len(dates) < max_days_per_run:
        dates.append(to_yyyymmdd(current))
        current += dt.timedelta(days=1)
    return dates


def pick_percentile(sorted_values: List[int], percentile: float) -> int:
    """Pick a simple nearest-rank percentile from an already sorted list."""
    if not sorted_values:
        return 0
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 1:
        return sorted_values[-1]
    idx = int(round((len(sorted_values) - 1) * percentile))
    return sorted_values[idx]


def print_single_day_validation_summary(
    biz_date: str,
    shop_row_stats: List[Tuple[str, str, int]],
    min_rows_per_shop: int,
    min_pass_ratio: float,
) -> bool:
    """Print one-day validation stats and return True when validation fails."""
    if not shop_row_stats:
        print(f"[validate] date={biz_date} no shop stats collected")
        return True

    counts = [row_count for _, _, row_count in shop_row_stats]
    sorted_counts = sorted(counts)
    shop_count = len(counts)
    pass_count = sum(1 for count in counts if count >= min_rows_per_shop)
    pass_ratio = pass_count / shop_count
    avg_rows = sum(counts) / shop_count

    p50 = pick_percentile(sorted_counts, 0.50)
    p90 = pick_percentile(sorted_counts, 0.90)

    print(
        f"[validate] date={biz_date} shops={shop_count} "
        f"min_rows={sorted_counts[0]} p50={p50} p90={p90} max_rows={sorted_counts[-1]} avg_rows={avg_rows:.1f}"
    )
    print(
        f"[validate] threshold_rows={min_rows_per_shop} "
        f"pass_shops={pass_count}/{shop_count} pass_ratio={pass_ratio:.1%}"
    )

    low_shops = [(shop_id, shop_name, row_count) for shop_id, shop_name, row_count in shop_row_stats if row_count < min_rows_per_shop]
    low_shops.sort(key=lambda x: x[2])
    if low_shops:
        print(f"[validate] low-row shops (top {min(20, len(low_shops))}):")
        for shop_id, shop_name, row_count in low_shops[:20]:
            print(f"  - shop_id={shop_id} shop_name={shop_name} rows={row_count}")

    failed = pass_ratio < min_pass_ratio
    status = "FAILED" if failed else "PASSED"
    print(f"[validate-{status}] target_pass_ratio={min_pass_ratio:.1%} actual={pass_ratio:.1%}")
    return failed


def describe_date_plan(
    mode: str,
    history_start_date: str,
    history_end_date: str,
    daily_lag_days: int,
    max_days_per_run: int,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """Explain how the next date range is determined."""
    today = dt.date.today()
    default_end = today - dt.timedelta(days=daily_lag_days)
    configured_start = parse_yyyymmdd(history_start_date)
    configured_end = parse_yyyymmdd(history_end_date) if history_end_date else default_end
    start = configured_start
    end = configured_end
    last_completed = str(state.get("last_completed_date") or "").strip()
    state_reason = "history_range"

    if mode == "daily":
        start = default_end
        end = default_end
        state_reason = "daily_mode"
    elif mode == "auto" and last_completed:
        try:
            next_start = parse_yyyymmdd(last_completed) + dt.timedelta(days=1)
            if next_start > start:
                start = next_start
                state_reason = "advanced_from_state"
        except ValueError:
            state_reason = "state_invalid_ignored"

    return {
        "mode": mode,
        "today": to_yyyymmdd(today),
        "daily_lag_days": daily_lag_days,
        "default_end": to_yyyymmdd(default_end),
        "configured_start": to_yyyymmdd(configured_start),
        "configured_end": to_yyyymmdd(configured_end),
        "effective_start": to_yyyymmdd(start),
        "effective_end": to_yyyymmdd(end),
        "last_completed_date": last_completed,
        "max_days_per_run": max_days_per_run,
        "state_reason": state_reason,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Sync POS customer history to SQLite/MySQL.")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--mode", choices=("auto", "backfill", "daily"), default="auto", help="Run mode override")
    parser.add_argument("--history-start-date", default="", help="Backfill start date, YYYYMMDD")
    parser.add_argument("--history-end-date", default="", help="Backfill end date, YYYYMMDD")
    parser.add_argument("--max-days", type=int, default=0, help="Max dates to process in this run")
    parser.add_argument("--agg-item", default=None, help="Shop summary agg_item override")
    parser.add_argument("--storage-backend", default=None, choices=("sqlite", "mysql"), help="Storage backend override")
    parser.add_argument("--dry-run", action="store_true", help="Fetch data but skip DB writes")
    parser.add_argument("--validate-single-day", action="store_true", help="Run one-day validation without advancing state")
    parser.add_argument("--validate-date", default="", help="Validation date, YYYYMMDD")
    parser.add_argument("--validate-min-rows-per-shop", type=int, default=0, help="Validation threshold rows per shop")
    parser.add_argument("--validate-pass-ratio", type=float, default=-1.0, help="Validation pass ratio, e.g. 0.9")
    return parser.parse_args()


def main() -> int:
    """Program entrypoint."""
    try:
        # Keep console/log output line-buffered so progress appears immediately.
        import sys

        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    args = parse_args()
    job_root = Path(__file__).resolve().parent

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = job_root / config_path

    cfg = load_json(config_path, {})
    if not isinstance(cfg, dict):
        print("config file must be a JSON object")
        return 2

    run_mode = str(pick_value(args.mode if args.mode != "auto" else None, cfg, "run_mode", args.mode)).strip() or "auto"
    if run_mode not in {"auto", "backfill", "daily"}:
        print(f"unsupported run_mode: {run_mode}")
        return 2

    # 1) 读取配置与运行参数。
    raw_base_url = str(pick_value(None, cfg, "base_url", "http://sdycpos.sd.yc"))
    base_url = normalize_base_url(raw_base_url)
    token = str(pick_value(None, cfg, "token", ""))
    cookie = str(pick_value(None, cfg, "cookie", ""))
    saleorg_id = str(pick_value(None, cfg, "saleorg_id", "11371502"))

    shop_page_limit = int(pick_value(None, cfg, "shop_page_limit", 200))
    data_page_limit = int(pick_value(None, cfg, "data_page_limit", 500))
    shop_parallel_workers = int(pick_value(None, cfg, "shop_parallel_workers", 8))
    commit_every_n_shops = int(pick_value(None, cfg, "commit_every_n_shops", 50))
    progress_every_n_shops = int(pick_value(None, cfg, "progress_every_n_shops", 20))
    progress_heartbeat_seconds = int(pick_value(None, cfg, "progress_heartbeat_seconds", 20))
    timeout = int(pick_value(None, cfg, "timeout", 30))
    query_type = str(pick_value(None, cfg, "shop_query_type", "02"))
    agg_item = str(pick_value(args.agg_item, cfg, "agg_item", "shop")).strip() or "shop"
    storage_backend = str(pick_value(args.storage_backend, cfg, "storage_backend", "sqlite")).strip().lower() or "sqlite"
    fetch_shop_summary = parse_bool(pick_value(None, cfg, "fetch_shop_summary", True), True)
    fetch_item_detail = parse_bool(pick_value(None, cfg, "fetch_item_detail", True), True)

    validate_single_day = bool(args.validate_single_day)
    validate_date = str(args.validate_date or "").strip()

    min_rows_cli = args.validate_min_rows_per_shop if args.validate_min_rows_per_shop > 0 else None
    validate_min_rows_per_shop = int(pick_value(min_rows_cli, cfg, "validate_min_rows_per_shop", 150))
    if validate_min_rows_per_shop < 1:
        validate_min_rows_per_shop = 1

    pass_ratio_cli = args.validate_pass_ratio if args.validate_pass_ratio >= 0 else None
    validate_pass_ratio = float(pick_value(pass_ratio_cli, cfg, "validate_pass_ratio", 0.9))
    validate_pass_ratio = max(0.0, min(1.0, validate_pass_ratio))

    if shop_parallel_workers < 1:
        shop_parallel_workers = 1
    if commit_every_n_shops < 1:
        commit_every_n_shops = 1
    if progress_every_n_shops < 1:
        progress_every_n_shops = 1
    if progress_heartbeat_seconds < 5:
        progress_heartbeat_seconds = 5

    history_start_date = str(pick_value(args.history_start_date, cfg, "history_start_date", "20220101"))
    history_end_date = str(pick_value(args.history_end_date, cfg, "history_end_date", ""))
    daily_lag_days = int(pick_value(None, cfg, "daily_lag_days", 1))
    max_days_per_run = int(pick_value(args.max_days if args.max_days else None, cfg, "max_days_per_run", 7))

    sqlite_rel = str(pick_value(None, cfg, "sqlite_path", "data/ods_customer_item_daily.sqlite"))
    mysql_host = str(pick_value(None, cfg, "mysql_host", "127.0.0.1")).strip()
    mysql_port = int(pick_value(None, cfg, "mysql_port", 3306))
    mysql_user = str(pick_value(None, cfg, "mysql_user", "root")).strip()
    mysql_password = str(pick_value(None, cfg, "mysql_password", "")).strip()
    mysql_database = str(pick_value(None, cfg, "mysql_database", "pos_ods")).strip()
    mysql_charset = str(pick_value(None, cfg, "mysql_charset", "utf8mb4")).strip() or "utf8mb4"
    mysql_connect_timeout = int(pick_value(None, cfg, "mysql_connect_timeout", 10))
    state_rel = str(pick_value(None, cfg, "state_path", "state/sync_state.json"))

    sqlite_path = Path(sqlite_rel)
    if not sqlite_path.is_absolute():
        sqlite_path = job_root / sqlite_path

    state_path = Path(state_rel)
    if not state_path.is_absolute():
        state_path = job_root / state_path

    if not validate_date_config("history_start_date", history_start_date, required=True):
        return 2
    if not validate_date_config("history_end_date", history_end_date, required=False):
        return 2

    if storage_backend not in {"sqlite", "mysql"}:
        print(f"unsupported storage_backend: {storage_backend}")
        return 2

    if storage_backend == "mysql" and (not mysql_host or not mysql_user or not mysql_database):
        print("storage_backend=mysql requires mysql_host/mysql_user/mysql_database")
        return 2

    cookies = parse_cookie_header(cookie)
    cookie_token = str(cookies.get("token") or "").strip()

    if contains_placeholder(cookie):
        print(f"cookie still contains a placeholder. Please update config: {config_path}")
        return 2

    if cookie and not is_latin1_encodable(cookie):
        print("cookie contains characters that cannot be sent in HTTP headers. Please check config.")
        return 2

    if (not token) or contains_placeholder(token):
        if cookie_token and (not contains_placeholder(cookie_token)):
            token = cookie_token
            print("token is empty or placeholder; using token from cookie.")
        else:
            print(f"token is empty or placeholder. Please update config: {config_path}")
            return 2

    if not is_latin1_encodable(token):
        print("token contains characters that cannot be sent in HTTP headers. Please check config.")
        return 2

    # 2) 计算日期计划，支持 auto/backfill/daily。
    state = load_json(state_path, {})
    if not isinstance(state, dict):
        state = {}

    run_dates = compute_date_range(
        mode=run_mode,
        history_start_date=history_start_date,
        history_end_date=history_end_date,
        daily_lag_days=daily_lag_days,
        max_days_per_run=max_days_per_run,
        state=state,
    )

    if validate_single_day and validate_date:
        try:
            parse_yyyymmdd(validate_date)
        except ValueError:
            print(f"validate_date format is invalid: {validate_date}; expected YYYYMMDD")
            return 2
        run_dates = [validate_date]
    elif validate_single_day and run_dates:
        run_dates = [run_dates[0]]

    if not run_dates:
        print("no pending date to process")
        plan = describe_date_plan(
            mode=run_mode,
            history_start_date=history_start_date,
            history_end_date=history_end_date,
            daily_lag_days=daily_lag_days,
            max_days_per_run=max_days_per_run,
            state=state,
        )
        print(
            "[date-plan] "
            f"mode={plan['mode']} today={plan['today']} daily_lag_days={plan['daily_lag_days']} "
            f"default_end={plan['default_end']} configured_start={plan['configured_start']} "
            f"configured_end={plan['configured_end']} effective_start={plan['effective_start']} "
            f"last_completed_date={plan['last_completed_date']} max_days_per_run={plan['max_days_per_run']}"
        )
        print(f"[date-plan] reason={plan['state_reason']}")
        print(
            "[date-plan] tip=Use run_mode=backfill for a fixed history range, "
            "or clear/lower last_completed_date in state file for auto mode."
        )
        return 0

    print(f"base_url={base_url}")
    print(f"mode={run_mode} pending_dates={run_dates[0]}..{run_dates[-1]} count={len(run_dates)}")
    print(f"storage_backend={storage_backend}")
    print(f"shop_summary_agg_item={agg_item}")
    print("item_detail_agg_item=shop_barcode")
    print(f"fetch_shop_summary={int(fetch_shop_summary)} fetch_item_detail={int(fetch_item_detail)}")
    print(f"shop_parallel_workers={shop_parallel_workers} commit_every_n_shops={commit_every_n_shops}")
    print(
        f"progress_every_n_shops={progress_every_n_shops} "
        f"progress_heartbeat_seconds={progress_heartbeat_seconds}"
    )
    if validate_single_day:
        print(
            f"validate_single_day=1 validate_date={run_dates[0]} "
            f"validate_min_rows_per_shop={validate_min_rows_per_shop} "
            f"validate_pass_ratio={validate_pass_ratio:.1%}"
        )

    session = create_session(cookies)
    headers = build_common_headers(base_url, token)

    # 3) 拉取全量门店，后续按门店并发采集。
    shops = fetch_shop_list_all(
        session=session,
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        saleorg_id=saleorg_id,
        limit=shop_page_limit,
        query_type=query_type,
    )

    if not shops:
        print("no shop found from getShopList")
        return 3

    print(f"total shops={len(shops)}")

    if args.dry_run and not validate_single_day:
        print("dry-run enabled, stop before writing DB")
        return 0

    if args.dry_run and validate_single_day:
        print("dry-run enabled: validation will fetch rows but skip DB writes")

    conn: Optional[Any] = None
    db_display = "(dry-run no write)"
    if not args.dry_run:
        conn, db_display = init_storage(
            storage_backend=storage_backend,
            sqlite_path=sqlite_path,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_password=mysql_password,
            mysql_database=mysql_database,
            mysql_charset=mysql_charset,
            mysql_connect_timeout=mysql_connect_timeout,
        )

    total_rows_fetched = 0
    total_rows_written = 0
    total_shop_rows_fetched = 0
    total_shop_rows_written = 0
    total_item_rows_fetched = 0
    total_item_rows_written = 0
    validation_failed = False
    try:
        # 4) 主循环：逐日处理，每日再按门店并发抓取。
        for date_idx, biz_date in enumerate(run_dates, start=1):
            date_rows_fetched = 0
            date_rows_written = 0
            date_shop_rows_fetched = 0
            date_shop_rows_written = 0
            date_item_rows_fetched = 0
            date_item_rows_written = 0
            date_start_ts = time.time()
            shop_row_stats: List[Tuple[str, str, int]] = []
            print(f"\n[date] {biz_date} ({date_idx}/{len(run_dates)})")

            worker_count = max(1, min(shop_parallel_workers, len(shops)))

            if worker_count == 1:
                last_progress_ts = time.time()
                for shop_idx, shop in enumerate(shops, start=1):
                    shop_id = shop.get("shop_id", "")
                    shop_name = shop.get("shop_name", "")
                    tenant_id = shop.get("tenant_id", "")

                    rows: List[Dict[str, Any]] = []
                    server_total = 0
                    if fetch_shop_summary:
                        try:
                            rows, server_total = fetch_data_list_rows_for_shop_day(
                                session=session,
                                base_url=base_url,
                                headers=headers,
                                timeout=timeout,
                                saleorg_id=saleorg_id,
                                shop_id=shop_id,
                                biz_date=biz_date,
                                limit=data_page_limit,
                                agg_item=agg_item,
                            )
                        except Exception as exc:
                            print(f"[warn] date={biz_date} shop={shop_id} fetch failed: {exc}")
                            continue

                    row_count = len(rows)
                    shop_row_stats.append((shop_id, shop_name, row_count))
                    date_shop_rows_fetched += row_count
                    total_shop_rows_fetched += row_count

                    written = 0
                    if conn is not None:
                        written = upsert_shop_daily_rows(
                            conn=conn,
                            storage_backend=storage_backend,
                            rows=rows,
                            biz_date=biz_date,
                            saleorg_id=saleorg_id,
                            fallback_shop_id=shop_id,
                            fallback_shop_name=shop_name,
                            fallback_tenant_id=tenant_id,
                        )
                    date_shop_rows_written += written
                    total_shop_rows_written += written

                    item_rows: List[Dict[str, Any]] = []
                    item_server_total = 0
                    if fetch_item_detail:
                        try:
                            item_rows, item_server_total = fetch_item_detail_rows_for_single_shop_day(
                                base_url=base_url,
                                headers=headers,
                                timeout=timeout,
                                saleorg_id=saleorg_id,
                                shop=shop,
                                biz_date=biz_date,
                                limit=data_page_limit,
                                cookie_dict=cookies,
                            )
                        except Exception as exc:
                            print(f"[warn] date={biz_date} shop={shop_id} item detail fetch failed: {exc}")

                    item_row_count = len(item_rows)
                    date_item_rows_fetched += item_row_count
                    total_item_rows_fetched += item_row_count
                    written_item = 0
                    if conn is not None and item_rows:
                        written_item = upsert_rows(
                            conn=conn,
                            storage_backend=storage_backend,
                            rows=item_rows,
                            biz_date=biz_date,
                            saleorg_id=saleorg_id,
                            fallback_shop_id=shop_id,
                            fallback_shop_name=shop_name,
                            fallback_tenant_id=tenant_id,
                        )
                    date_item_rows_written += written_item
                    total_item_rows_written += written_item
                    date_rows_fetched = date_shop_rows_fetched + date_item_rows_fetched
                    total_rows_fetched = total_shop_rows_fetched + total_item_rows_fetched
                    date_rows_written = date_shop_rows_written + date_item_rows_written
                    total_rows_written = total_shop_rows_written + total_item_rows_written

                    if conn is not None and shop_idx % commit_every_n_shops == 0:
                        conn.commit()

                    now_ts = time.time()
                    need_progress = (
                        shop_idx % progress_every_n_shops == 0
                        or shop_idx == len(shops)
                        or (now_ts - last_progress_ts) >= progress_heartbeat_seconds
                    )
                    if need_progress:
                        elapsed = max(1.0, now_ts - date_start_ts)
                        speed = shop_idx / elapsed
                        pct = shop_idx * 100.0 / len(shops)
                        print(
                            f"[progress] date={biz_date} shop={shop_idx}/{len(shops)} "
                            f"pct={pct:.1f}% elapsed_s={int(elapsed)} speed_shop_s={speed:.2f} "
                            f"shop_rows={len(rows)} shop_total={server_total} "
                            f"item_rows={item_row_count} item_total={item_server_total}"
                        )
                        last_progress_ts = now_ts
            else:
                print(f"[shop-parallel] date={biz_date} shops={len(shops)} workers={worker_count}")
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    future_map = {
                        executor.submit(
                            fetch_dual_rows_for_single_shop_day,
                            base_url,
                            headers,
                            timeout,
                            saleorg_id,
                            shop,
                            biz_date,
                            data_page_limit,
                            agg_item,
                            cookies,
                            fetch_shop_summary,
                            fetch_item_detail,
                        ): shop
                        for shop in shops
                    }

                    completed = 0
                    pending_futures = set(future_map.keys())
                    last_progress_ts = time.time()
                    while pending_futures:
                        done_futures, pending_futures = wait(
                            pending_futures,
                            timeout=progress_heartbeat_seconds,
                            return_when=FIRST_COMPLETED,
                        )

                        if not done_futures:
                            now_ts = time.time()
                            elapsed = max(1.0, now_ts - date_start_ts)
                            speed = completed / elapsed
                            pct = completed * 100.0 / len(shops)
                            print(
                                f"[heartbeat] date={biz_date} shop={completed}/{len(shops)} "
                                f"pending={len(pending_futures)} pct={pct:.1f}% "
                                f"elapsed_s={int(elapsed)} speed_shop_s={speed:.2f}"
                            )
                            last_progress_ts = now_ts
                            continue

                        for future in done_futures:
                            completed += 1
                            fallback_shop = future_map[future]
                            fallback_shop_id = fallback_shop.get("shop_id", "")

                            try:
                                done_shop, rows, server_total, item_rows, item_server_total = future.result()
                            except Exception as exc:
                                print(f"[warn] date={biz_date} shop={fallback_shop_id} fetch failed: {exc}")
                                continue

                            done_shop_id = done_shop.get("shop_id", "")
                            done_shop_name = done_shop.get("shop_name", "")
                            row_count = len(rows)
                            shop_row_stats.append((done_shop_id, done_shop_name, row_count))
                            date_shop_rows_fetched += row_count
                            total_shop_rows_fetched += row_count

                            written = 0
                            if conn is not None:
                                written = upsert_shop_daily_rows(
                                    conn=conn,
                                    storage_backend=storage_backend,
                                    rows=rows,
                                    biz_date=biz_date,
                                    saleorg_id=saleorg_id,
                                    fallback_shop_id=done_shop_id,
                                    fallback_shop_name=done_shop_name,
                                    fallback_tenant_id=done_shop.get("tenant_id", ""),
                                )
                            date_shop_rows_written += written
                            total_shop_rows_written += written

                            item_row_count = len(item_rows)
                            date_item_rows_fetched += item_row_count
                            total_item_rows_fetched += item_row_count
                            written_item = 0
                            if conn is not None and item_rows:
                                written_item = upsert_rows(
                                    conn=conn,
                                    storage_backend=storage_backend,
                                    rows=item_rows,
                                    biz_date=biz_date,
                                    saleorg_id=saleorg_id,
                                    fallback_shop_id=done_shop_id,
                                    fallback_shop_name=done_shop_name,
                                    fallback_tenant_id=done_shop.get("tenant_id", ""),
                                )
                            date_item_rows_written += written_item
                            total_item_rows_written += written_item
                            date_rows_fetched = date_shop_rows_fetched + date_item_rows_fetched
                            total_rows_fetched = total_shop_rows_fetched + total_item_rows_fetched
                            date_rows_written = date_shop_rows_written + date_item_rows_written
                            total_rows_written = total_shop_rows_written + total_item_rows_written

                            if conn is not None and completed % commit_every_n_shops == 0:
                                conn.commit()

                            now_ts = time.time()
                            need_progress = (
                                completed % progress_every_n_shops == 0
                                or completed == len(shops)
                                or (now_ts - last_progress_ts) >= progress_heartbeat_seconds
                            )
                            if need_progress:
                                elapsed = max(1.0, now_ts - date_start_ts)
                                speed = completed / elapsed
                                pct = completed * 100.0 / len(shops)
                                print(
                                    f"[progress] date={biz_date} shop={completed}/{len(shops)} "
                                    f"pct={pct:.1f}% elapsed_s={int(elapsed)} speed_shop_s={speed:.2f} "
                                    f"shop_rows={len(rows)} shop_total={server_total} "
                                    f"item_rows={item_row_count} item_total={item_server_total}"
                                )
                                last_progress_ts = now_ts

            if conn is not None:
                conn.commit()

            if validate_single_day:
                # 验证模式：只输出统计，不推进增量状态。
                validation_failed = print_single_day_validation_summary(
                    biz_date=biz_date,
                    shop_row_stats=shop_row_stats,
                    min_rows_per_shop=validate_min_rows_per_shop,
                    min_pass_ratio=validate_pass_ratio,
                )
            else:
                # 正式模式：日期完成后推进状态文件，保障断点续跑。
                state["last_completed_date"] = biz_date
                state["last_run_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                state["last_mode"] = run_mode
                save_json(state_path, state)

            print(
                f"[date-done] {biz_date} "
                f"shop_fetched={date_shop_rows_fetched} shop_written={date_shop_rows_written} "
                f"item_fetched={date_item_rows_fetched} item_written={date_item_rows_written} "
                f"total_fetched={date_rows_fetched} total_written={date_rows_written}"
            )

    except KeyboardInterrupt:
        if conn is not None:
            conn.commit()
        if not validate_single_day:
            state["last_run_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state["last_mode"] = run_mode
            save_json(state_path, state)
        print("\n[interrupt] stopped by user; committed rows already written.")
        print(f"state_file={state_path}")
        return 130

    finally:
        if conn is not None:
            conn.close()

    print(
        f"\nfinished: "
        f"shop_fetched_rows={total_shop_rows_fetched} shop_written_rows={total_shop_rows_written} "
        f"item_fetched_rows={total_item_rows_fetched} item_written_rows={total_item_rows_written} "
        f"total_fetched_rows={total_rows_fetched} total_written_rows={total_rows_written} db={db_display}"
    )
    print(f"state_file={state_path}")
    if validate_single_day and validation_failed:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



