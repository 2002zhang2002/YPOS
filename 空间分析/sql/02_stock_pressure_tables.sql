CREATE DATABASE IF NOT EXISTS pos_ods
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

USE pos_ods;

CREATE TABLE IF NOT EXISTS rpt_customer_stock_pressure_daily (
  biz_date DATE NOT NULL,
  shop_id VARCHAR(64) NOT NULL,
  cust_id VARCHAR(64) NULL,
  license_code VARCHAR(64) NULL,
  cust_name VARCHAR(255) NULL,
  shop_name VARCHAR(255) NULL,
  cust_seg_name VARCHAR(64) NULL,
  terminal_level VARCHAR(64) NULL,
  base_type_name VARCHAR(128) NULL,
  work_port_name VARCHAR(64) NULL,
  sale_dept VARCHAR(128) NULL,
  ss_name VARCHAR(128) NULL,
  slsman VARCHAR(128) NULL,
  longitude DECIMAL(12,8) NULL,
  latitude DECIMAL(12,8) NULL,
  window_7d_start DATE NULL,
  window_30d_start DATE NULL,
  stock_qty_end DECIMAL(18,4) NULL,
  stock_amount_end DECIMAL(18,4) NULL,
  sale_qty_7d DECIMAL(18,4) NULL,
  sale_qty_30d DECIMAL(18,4) NULL,
  sale_amount_7d DECIMAL(18,4) NULL,
  sale_amount_30d DECIMAL(18,4) NULL,
  sale_days_7d INT NULL,
  sale_days_30d INT NULL,
  stock_sale_ratio_7d_m DECIMAL(18,6) NULL,
  stock_sale_ratio_30d DECIMAL(18,6) NULL,
  ratio_valid_7d TINYINT(1) NOT NULL DEFAULT 0,
  ratio_valid_30d TINYINT(1) NOT NULL DEFAULT 0,
  pressure_level_7d VARCHAR(32) NULL,
  pressure_level_30d VARCHAR(32) NULL,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date, shop_id),
  KEY idx_pressure_dept_date (sale_dept, biz_date),
  KEY idx_pressure_seg_date (cust_seg_name, biz_date),
  KEY idx_pressure_level_date (terminal_level, biz_date),
  KEY idx_pressure_cust_date (cust_id, biz_date),
  KEY idx_pressure_loaded (etl_loaded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
