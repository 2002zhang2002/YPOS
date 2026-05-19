-- Phase-2 dual-fact schema for POS customer analytics
-- Purpose:
-- 1) Daily shop/customer summary fact
-- 2) Daily item-level detail fact
-- 3) Customer profile dimension

CREATE DATABASE IF NOT EXISTS pos_ods
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

USE pos_ods;

-- Customer profile dimension
CREATE TABLE IF NOT EXISTS dim_customer_profile (
  cust_id VARCHAR(64) NOT NULL COMMENT '客户编码',
  license_code VARCHAR(64) NULL COMMENT '许可证号',
  cust_name VARCHAR(255) NULL COMMENT '客户名称',
  linkman VARCHAR(128) NULL COMMENT '联系人',
  order_phone VARCHAR(64) NULL COMMENT '联系电话',
  cust_seg_name VARCHAR(64) NULL COMMENT '客户档位',
  address VARCHAR(500) NULL COMMENT '经营地址',
  work_port_name VARCHAR(64) NULL COMMENT '城乡属性',
  base_type_name VARCHAR(128) NULL COMMENT '业态',
  sale_center VARCHAR(128) NULL COMMENT '营销中心',
  ss_name VARCHAR(128) NULL COMMENT '基层服务站',
  slsman VARCHAR(128) NULL COMMENT '客户经理',
  sale_dept VARCHAR(128) NULL COMMENT '所属单位',
  org_code VARCHAR(32) NULL COMMENT '组织编码',
  tenant_id VARCHAR(64) NULL COMMENT '租户/门店编码',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (cust_id),
  KEY idx_dim_license_code (license_code),
  KEY idx_dim_sale_center (sale_center, ss_name),
  KEY idx_dim_slsman (slsman),
  KEY idx_dim_updated_at (updated_at)
) ENGINE=InnoDB COMMENT='客户基础信息维表';

-- Daily shop-level summary fact
-- Source pattern:
-- getDataList + queryType=day + agg_item=shop
CREATE TABLE IF NOT EXISTS fact_customer_shop_daily (
  biz_date DATE NOT NULL COMMENT '业务日期',
  saleorg_id VARCHAR(32) NULL COMMENT '销售组织ID',
  shop_id VARCHAR(64) NOT NULL COMMENT '门店ID',
  shop_name VARCHAR(255) NULL COMMENT '门店名称',
  tenant_id VARCHAR(64) NULL COMMENT '租户/门店编码',
  cust_id VARCHAR(64) NOT NULL COMMENT '客户编码',
  license_code VARCHAR(64) NULL COMMENT '许可证号',
  sale_center VARCHAR(128) NULL COMMENT '营销中心',
  ss_name VARCHAR(128) NULL COMMENT '基层服务站',
  slsman VARCHAR(128) NULL COMMENT '客户经理',
  base_type_name VARCHAR(128) NULL COMMENT '业态',
  work_port_name VARCHAR(64) NULL COMMENT '城乡属性',
  cust_seg_name VARCHAR(64) NULL COMMENT '客户档位',
  t_big_stoamt DECIMAL(18,4) NULL COMMENT '累计入库条数/箱数口径',
  t_big_saleamt DECIMAL(18,4) NULL COMMENT '累计销售条数/箱数口径',
  t_big_stockamt DECIMAL(18,4) NULL COMMENT '累计库存条数/箱数口径',
  t_actual_saleamt DECIMAL(18,4) NULL COMMENT '实际销售量',
  t_actual_salemny DECIMAL(18,4) NULL COMMENT '实际销售额',
  t_salemny DECIMAL(18,4) NULL COMMENT '销售金额',
  t_stomny DECIMAL(18,4) NULL COMMENT '入库金额',
  t_stockmny DECIMAL(18,4) NULL COMMENT '库存金额',
  sto_sale DECIMAL(18,4) NULL COMMENT '存销比/入销指标',
  sale_stock DECIMAL(18,4) NULL COMMENT '销存比',
  stock_sale DECIMAL(18,4) NULL COMMENT '库存销量比',
  raw_json JSON NULL COMMENT '原始接口行',
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date, shop_id),
  KEY idx_shop_daily_cust_date (cust_id, biz_date),
  KEY idx_shop_daily_center_date (sale_center, ss_name, biz_date),
  KEY idx_shop_daily_slsman_date (slsman, biz_date),
  KEY idx_shop_daily_loaded_at (etl_loaded_at)
) ENGINE=InnoDB COMMENT='客户/门店日汇总事实表';

-- Daily item-level detail fact
-- Source pattern:
-- getDataList + queryType=day + agg_item=shop_barcode + tenantIds/shopIds specified
CREATE TABLE IF NOT EXISTS fact_customer_item_daily (
  biz_date DATE NOT NULL COMMENT '业务日期',
  saleorg_id VARCHAR(32) NULL COMMENT '销售组织ID',
  shop_id VARCHAR(64) NOT NULL COMMENT '门店ID',
  shop_name VARCHAR(255) NULL COMMENT '门店名称',
  tenant_id VARCHAR(64) NULL COMMENT '租户/门店编码',
  cust_id VARCHAR(64) NOT NULL COMMENT '客户编码',
  license_code VARCHAR(64) NULL COMMENT '许可证号',
  sale_center VARCHAR(128) NULL COMMENT '营销中心',
  ss_name VARCHAR(128) NULL COMMENT '基层服务站',
  slsman VARCHAR(128) NULL COMMENT '客户经理',
  base_type_name VARCHAR(128) NULL COMMENT '业态',
  work_port_name VARCHAR(64) NULL COMMENT '城乡属性',
  cust_seg_name VARCHAR(64) NULL COMMENT '客户档位',
  item_name VARCHAR(255) NULL COMMENT '商品名称',
  barcode VARCHAR(64) NULL COMMENT '条码',
  big_barcode VARCHAR(64) NULL COMMENT '大条码',
  item_key VARCHAR(128) NOT NULL COMMENT '商品唯一键',
  big_price DECIMAL(18,4) NULL COMMENT '条包单价',
  small_price DECIMAL(18,4) NULL COMMENT '小包单价',
  big_avg_price DECIMAL(18,4) NULL COMMENT '均价',
  small_big DECIMAL(18,4) NULL COMMENT '大小包换算',
  t_big_stoamt DECIMAL(18,4) NULL COMMENT '入库量',
  t_big_saleamt DECIMAL(18,4) NULL COMMENT '销售量',
  t_big_stockamt DECIMAL(18,4) NULL COMMENT '库存量',
  t_actual_saleamt DECIMAL(18,4) NULL COMMENT '实际销售量',
  t_actual_salemny DECIMAL(18,4) NULL COMMENT '实际销售额',
  t_salemny DECIMAL(18,4) NULL COMMENT '销售金额',
  t_stomny DECIMAL(18,4) NULL COMMENT '入库金额',
  t_stockmny DECIMAL(18,4) NULL COMMENT '库存金额',
  t_change_amt DECIMAL(18,4) NULL COMMENT '变动量',
  t_change_mny DECIMAL(18,4) NULL COMMENT '变动金额',
  t_org_stomny DECIMAL(18,4) NULL COMMENT '原始入库金额',
  t_big_org_stoamt DECIMAL(18,4) NULL COMMENT '原始入库量',
  t_big_actual_saleamt DECIMAL(18,4) NULL COMMENT '原始实际销售量',
  t_big_actual_salemny DECIMAL(18,4) NULL COMMENT '原始实际销售额',
  sto_sale DECIMAL(18,4) NULL COMMENT '存销指标',
  sale_stock DECIMAL(18,4) NULL COMMENT '销存指标',
  stock_sale DECIMAL(18,4) NULL COMMENT '库存销量指标',
  raw_json JSON NULL COMMENT '原始接口行',
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date, shop_id, item_key),
  KEY idx_item_daily_cust_date (cust_id, biz_date),
  KEY idx_item_daily_shop_date (shop_id, biz_date),
  KEY idx_item_daily_barcode_date (barcode, biz_date),
  KEY idx_item_daily_big_barcode_date (big_barcode, biz_date),
  KEY idx_item_daily_item_name_date (item_name(100), biz_date),
  KEY idx_item_daily_center_date (sale_center, ss_name, biz_date),
  KEY idx_item_daily_loaded_at (etl_loaded_at)
) ENGINE=InnoDB COMMENT='客户商品日明细事实表';

-- Suggested view for a simplified daily inventory drill-down
CREATE OR REPLACE VIEW vw_customer_item_daily_inventory AS
SELECT
  d.biz_date,
  d.shop_id,
  d.shop_name,
  d.cust_id,
  d.sale_center,
  d.ss_name,
  d.slsman,
  d.item_name,
  d.barcode,
  d.big_barcode,
  d.t_big_stoamt,
  d.t_big_saleamt,
  d.t_big_stockamt,
  d.t_stockmny
FROM fact_customer_item_daily d;

-- Suggested view for day-over-day item stock change analysis
CREATE OR REPLACE VIEW vw_customer_item_daily_delta AS
SELECT
  cur.biz_date,
  cur.shop_id,
  cur.shop_name,
  cur.cust_id,
  cur.item_key,
  cur.item_name,
  cur.barcode,
  cur.big_barcode,
  cur.t_big_stockamt AS cur_stockamt,
  prev.t_big_stockamt AS prev_stockamt,
  cur.t_big_stockamt - IFNULL(prev.t_big_stockamt, 0) AS stockamt_delta,
  cur.t_big_saleamt AS cur_saleamt,
  prev.t_big_saleamt AS prev_saleamt,
  cur.t_big_saleamt - IFNULL(prev.t_big_saleamt, 0) AS saleamt_delta
FROM fact_customer_item_daily cur
LEFT JOIN fact_customer_item_daily prev
  ON prev.shop_id = cur.shop_id
 AND prev.item_key = cur.item_key
 AND prev.biz_date = DATE_SUB(cur.biz_date, INTERVAL 1 DAY);
