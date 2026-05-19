# Full Customer History Sync

This folder is isolated for historical backfill and scheduled daily sync for dual-fact POS analytics.

## Files

- full_customer_history_sync.py: main collector
- configurator_gui.py: local GUI configurator for token/cookie/MySQL settings
- config.json: runtime config
- run_once.bat: manual run entry
- run_backfill_once.bat: force historical backfill by configured date range
- run_increment_once.bat: one incremental run based on state file
- run_stock_pressure_once.bat: rebuild daily stock-pressure reports for 2-star/3-star customers
- open_configurator.bat: open the GUI configurator
- setup_daily_task.ps1: create/update daily scheduled task
- stock_pressure_app/index.html: frontend prototype for map + trend drill-down

## Data model

The script supports two storage backends:

- SQLite: local ODS file, configured by `sqlite_path`
- MySQL: dual-fact tables, configured by `mysql_*`

Default backend is `sqlite`, so you can still use the script before MySQL is installed.

In MySQL dual-fact mode:

- `fact_customer_shop_daily`: one row per `biz_date + shop_id`
- `fact_customer_item_daily`: one row per `biz_date + shop_id + item_key`

`item_key` is generated from `big_barcode -> barcode -> item_name` fallback.

## How it works

1. Fetch all shops using /soa/common/shophelper/getShopList
2. For each date, fetch shop-level daily summary using `agg_item=shop`
3. For each date and shop, fetch item-level daily detail using `agg_item=shop_barcode`
4. Upsert rows into SQLite ODS or MySQL dual-fact tables
5. Update state file (state/sync_state.json) after each completed date

## Run modes

- auto: continue from state last_completed_date; first run starts from history_start_date
- backfill: force run from history_start_date to history_end_date (or default end)
- daily: only run one day (today - daily_lag_days)

## Quick start

1. Fill token/cookie in config.json
2. Choose backend:
   - keep `storage_backend=sqlite` if you do not have MySQL yet
   - set `storage_backend=mysql` after MySQL is installed and `mysql_*` is filled
3. Historical backfill:
   - set `run_mode=backfill`
   - set `history_start_date` / `history_end_date`
   - use `run_backfill_once.bat`
4. Daily incremental after history is done:
   - set `run_mode=auto`
   - keep `state_path` unchanged
   - use `run_increment_once.bat`
5. Create daily task after history is complete (example 01:30):
   powershell -ExecutionPolicy Bypass -File .\setup_daily_task.ps1 -RunTime 01:30 -Mode auto

## Notes

- history_end_date empty means until (today - daily_lag_days)
- max_days_per_run controls batch size in one run; keep a safe value for long history catch-up
- shop_parallel_workers controls shop-level concurrency per date; typical value is 6-12 on intranet
- commit_every_n_shops controls commit frequency to reduce progress loss on interruption
- If token/cookie expires, update config.json and rerun
- If `storage_backend=mysql`, install `PyMySQL` first and import `mysql_phase1_schema.sql` into the target database
- Win7 installation notes are in `Win7_MySQL_Install.md`
- Recommended strategy:
  - history phase stores one snapshot per day per grain
  - daily phase only appends missing dates based on `state_path`
  - do not reset `state_path` after history catch-up, otherwise auto mode will replay old days
- Snapshot facts are normal here:
  - `fact_customer_shop_daily` and `fact_customer_item_daily` store daily status snapshots
  - later calculations such as day-over-day stock change should be done in derived SQL/views or downstream reports, not by mutating raw facts

## Detail mode and single-day validation

- `agg_item` in config now controls the shop summary chain only.
- Recommended value: `agg_item=shop`
- Item detail chain is fixed to `agg_item=shop_barcode + queryType=day + tenantIds/shopIds`
- Single-day validation command (check if each shop gets around 150 rows):
- `py -3 full_customer_history_sync.py --config config.json --mode auto --validate-single-day --validate-min-rows-per-shop 150 --validate-pass-ratio 0.9`
- Validate a specific date:
- `py -3 full_customer_history_sync.py --config config.json --validate-single-day --validate-date 20260110 --validate-min-rows-per-shop 150`
- Validation mode will not update `state/sync_state.json`, so incremental sync progress is not affected.
- Open `config_ui_dual_fact.html` if you want a visual explanation of token/cookie/MySQL config.

## Stock pressure app

This repo now includes a stock-pressure reporting layer and frontend prototype:

- Result table: `rpt_customer_stock_pressure_daily`
- Filter rule: only `terminal_level IN ('二星', '三星')`
- Main metrics:
  - `30-day stock-sale ratio = end stock / recent 30-day sales`
  - `7-day monthly stock-sale ratio = end stock / (recent 7-day sales / 7 * 30)`

Build or refresh it with:

```powershell
.\run_stock_pressure_once.bat
```

The script will:

1. Create the stock-pressure result table if needed
2. Rebuild daily results for the configured date range
3. Export the latest snapshot CSV / GeoJSON
4. Refresh `stock_pressure_app\data\stock_pressure_app_data.js`

Then open:

```text
customer_history_job\stock_pressure_app\index.html
```
