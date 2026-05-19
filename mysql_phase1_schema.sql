-- Phase-1 MySQL schema for customer daily item details
-- MySQL 8.0+

CREATE DATABASE IF NOT EXISTS pos_ods
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

USE pos_ods;

-- Customer master profile table (one row per customer)
-- Field names follow lowerCamelCase converted from your Chinese header row.
CREATE TABLE IF NOT EXISTS dim_customer_profile (
  custId VARCHAR(64) NOT NULL COMMENT '客户编码',
  licenseNo VARCHAR(64) NULL COMMENT '许可证号',
  custName VARCHAR(255) NULL COMMENT '客户名称',
  principalName VARCHAR(128) NULL COMMENT '负责人',
  orderPhone VARCHAR(64) NULL COMMENT '订货电话',
  customerSegment VARCHAR(64) NULL COMMENT '客户档位',
  businessAddress VARCHAR(500) NULL COMMENT '经营地址',
  cigarSegment VARCHAR(64) NULL COMMENT '雪茄挡位',
  countyDistrict VARCHAR(128) NULL COMMENT '区县',
  marketDepartment VARCHAR(128) NULL COMMENT '市场部',
  marketingRoute VARCHAR(128) NULL COMMENT '营销线路',
  networkJoinDate DATE NULL COMMENT '入网日期',
  businessType VARCHAR(128) NULL COMMENT '经营业态',
  businessTypeDetail VARCHAR(128) NULL COMMENT '经营业态细分',
  marketType VARCHAR(64) NULL COMMENT '市场类型',
  urbanRuralCategory VARCHAR(64) NULL COMMENT '城乡分类',
  businessCircleType VARCHAR(128) NULL COMMENT '商圈类型',
  terminalType VARCHAR(128) NULL COMMENT '终端类型',
  modernTerminalDetail VARCHAR(128) NULL COMMENT '现代终端细分',
  terminalDetail VARCHAR(128) NULL COMMENT '终端细分',
  terminalLevel VARCHAR(64) NULL COMMENT '终端等级',
  scanDevice VARCHAR(128) NULL COMMENT '扫码设备',
  businessStatus VARCHAR(64) NULL COMMENT '经营状态',
  orderMethod VARCHAR(128) NULL COMMENT '订货方式',
  orderCycleType VARCHAR(64) NULL COMMENT '订货周期类型',
  orderWeek VARCHAR(64) NULL COMMENT '订货周次',
  orderDay VARCHAR(64) NULL COMMENT '订货日',
  bankName VARCHAR(128) NULL COMMENT '开户行',
  bankAccount VARCHAR(128) NULL COMMENT '银行帐号',
  accountHolderName VARCHAR(128) NULL COMMENT '开户姓名',
  shortName VARCHAR(128) NULL COMMENT '简称',
  mnemonicCode VARCHAR(64) NULL COMMENT '助记码',
  isRailwayCustomer VARCHAR(8) NULL COMMENT '是否铁路户(是/否)',
  isChainStore VARCHAR(8) NULL COMMENT '是否连锁(是/否)',
  isOrderSuspended VARCHAR(8) NULL COMMENT '是否暂停订货(是/否)',
  specialTag VARCHAR(255) NULL COMMENT '特殊标签',
  businessCircleTypeDetail VARCHAR(128) NULL COMMENT '商圈类型细分',
  structureCategory VARCHAR(128) NULL COMMENT '结构类别',
  paymentMethod VARCHAR(128) NULL COMMENT '支付方式',
  isOnlinePayment VARCHAR(8) NULL COMMENT '是否网上支付(是/否)',
  cloudPosStatus VARCHAR(128) NULL COMMENT '云pos状态',
  longitude DECIMAL(10,6) NULL COMMENT '经度',
  latitude DECIMAL(10,6) NULL COMMENT '纬度',
  invoiceType VARCHAR(64) NULL COMMENT '发票类型',
  belongingGroup VARCHAR(128) NULL COMMENT '所属小组',
  standardTerminalType VARCHAR(128) NULL COMMENT '标准终端类型',
  businessCircleTypeExt VARCHAR(128) NULL COMMENT '商圈类型(扩展)',
  specialPopulation VARCHAR(128) NULL COMMENT '特殊群体',
  cigarTerminalType VARCHAR(128) NULL COMMENT '雪茄终端类型',
  isSanQuanStore VARCHAR(8) NULL COMMENT '是否三全门店(是/否)',
  invoiceName VARCHAR(255) NULL COMMENT '发票名称',
  isPriceProcurementCustomer VARCHAR(8) NULL COMMENT '是否价采户(是/否)',
  businessScale VARCHAR(64) NULL COMMENT '经营规模',
  specialMarketType VARCHAR(128) NULL COMMENT '特类市场',
  specialMarketTypeDetail VARCHAR(128) NULL COMMENT '特类市场细分',
  sourceFileName VARCHAR(255) NULL COMMENT '来源文件名',
  etlLoadedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'ETL装载时间',
  updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (custId),
  UNIQUE KEY uq_dim_license_no (licenseNo),
  KEY idx_dim_market (marketDepartment, marketingRoute),
  KEY idx_dim_status (businessStatus),
  KEY idx_dim_terminal (terminalType, standardTerminalType),
  KEY idx_dim_group (belongingGroup),
  KEY idx_dim_updated_at (updatedAt)
) ENGINE=InnoDB COMMENT='客户基础信息维表';

-- Daily item detail fact table (one row per biz_date + shop + item)
CREATE TABLE IF NOT EXISTS fact_customer_item_daily (
  biz_date DATE NOT NULL,
  saleorg_id VARCHAR(32) NULL,
  shop_id VARCHAR(64) NOT NULL,
  shop_name VARCHAR(255) NULL,
  tenant_id VARCHAR(64) NULL,
  cust_id VARCHAR(64) NOT NULL,
  sale_center VARCHAR(128) NULL,
  ss_name VARCHAR(128) NULL,
  slsman VARCHAR(128) NULL,
  item_name VARCHAR(255) NULL,
  barcode VARCHAR(64) NULL,
  big_barcode VARCHAR(64) NULL,
  item_key VARCHAR(128) NOT NULL,
  t_big_stoamt DECIMAL(18,4) NULL,
  t_big_saleamt DECIMAL(18,4) NULL,
  t_big_stockamt DECIMAL(18,4) NULL,
  raw_json JSON NULL,
  etl_loaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (biz_date, shop_id, item_key),
  KEY idx_fact_cust_date (cust_id, biz_date),
  KEY idx_fact_shop_date (shop_id, biz_date),
  KEY idx_fact_item_date (item_key, biz_date),
  KEY idx_fact_barcode_date (barcode, biz_date),
  KEY idx_fact_center_date (sale_center, ss_name, biz_date),
  KEY idx_fact_loaded_at (etl_loaded_at)
) ENGINE=InnoDB;

-- Optional: when yearly data gets very large, add monthly partitions by biz_date.
-- Example (edit partition boundaries before running):
-- ALTER TABLE fact_customer_item_daily
-- PARTITION BY RANGE COLUMNS (biz_date) (
--   PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
--   PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
--   PARTITION pmax VALUES LESS THAN (MAXVALUE)
-- );
