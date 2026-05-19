param(
  [string]$ImportDir = "",
  [string]$StartDate = "2024-08-02",
  [string]$EndDate = "2025-01-01",
  [string]$Mysql = "mysql",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 3306,
  [string]$User = "root",
  [string]$Password = "",
  [string]$Database = "pos_ods"
)

$ErrorActionPreference = "Stop"

if (-not $ImportDir) {
  $safeStart = $StartDate.Replace("-", "")
  $safeEnd = $EndDate.Replace("-", "")
  $ImportDir = Join-Path (Join-Path $PSScriptRoot "transfer_exports") "pos_ods_${safeStart}_${safeEnd}"
}

if (-not (Test-Path -LiteralPath $ImportDir)) {
  throw "ImportDir not found: $ImportDir"
}

function Invoke-MysqlFile {
  param([string]$File)
  Write-Host "Importing $File"
  & $Mysql "--host=$HostName" "--port=$Port" "--user=$User" "--password=$Password" "--default-character-set=utf8mb4" $Database --execute="source $File"
}

function Invoke-MysqlSql {
  param([string]$Sql)
  & $Mysql "--host=$HostName" "--port=$Port" "--user=$User" "--password=$Password" "--default-character-set=utf8mb4" $Database --execute=$Sql
}

$schema = Join-Path $ImportDir "00_schema.sql"
$dim = Join-Path $ImportDir "01_dim_customer_profile.sql"
$shop = Get-ChildItem -LiteralPath $ImportDir -Filter "02_fact_customer_shop_daily_*.sql" | Select-Object -First 1
$item = Get-ChildItem -LiteralPath $ImportDir -Filter "03_fact_customer_item_daily_*.sql" | Select-Object -First 1

Invoke-MysqlFile -File $schema

Invoke-MysqlSql -Sql "DELETE FROM fact_customer_shop_daily WHERE biz_date >= '$StartDate' AND biz_date <= '$EndDate';"
Invoke-MysqlSql -Sql "DELETE FROM fact_customer_item_daily WHERE biz_date >= '$StartDate' AND biz_date <= '$EndDate';"

Invoke-MysqlFile -File $dim
if ($shop) { Invoke-MysqlFile -File $shop.FullName }
if ($item) { Invoke-MysqlFile -File $item.FullName }

Invoke-MysqlSql -Sql "SELECT 'fact_customer_shop_daily' AS table_name, COUNT(*) AS rows_loaded, MIN(biz_date) AS min_date, MAX(biz_date) AS max_date FROM fact_customer_shop_daily WHERE biz_date >= '$StartDate' AND biz_date <= '$EndDate'; SELECT 'fact_customer_item_daily' AS table_name, COUNT(*) AS rows_loaded, MIN(biz_date) AS min_date, MAX(biz_date) AS max_date FROM fact_customer_item_daily WHERE biz_date >= '$StartDate' AND biz_date <= '$EndDate';"

Write-Host "Import completed."
