param(
  [string]$StartDate = "2024-08-02",
  [string]$EndDate = "2025-01-01",
  [string]$MysqlDump = "mysqldump",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 3306,
  [string]$User = "root",
  [string]$Password = "",
  [string]$Database = "pos_ods",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Dump {
  param(
    [string]$Table,
    [string]$OutFile,
    [string]$Where = ""
  )
  $args = @(
    "--host=$HostName",
    "--port=$Port",
    "--user=$User",
    "--password=$Password",
    "--default-character-set=utf8mb4",
    "--single-transaction",
    "--quick",
    "--skip-triggers",
    "--no-create-info",
    "--replace",
    "--hex-blob",
    "--result-file=$OutFile"
  )
  if ($Where) {
    $args += "--where=$Where"
  }
  $args += @($Database, $Table)

  & $MysqlDump @args
  if ($LASTEXITCODE -ne 0) {
    throw "mysqldump failed for table $Table with exit code $LASTEXITCODE"
  }
}

function Invoke-SchemaDump {
  param(
    [string]$OutFile
  )
  $args = @(
    "--host=$HostName",
    "--port=$Port",
    "--user=$User",
    "--password=$Password",
    "--default-character-set=utf8mb4",
    "--single-transaction",
    "--skip-triggers",
    "--no-data",
    "--result-file=$OutFile",
    $Database,
    "dim_customer_profile",
    "fact_customer_shop_daily",
    "fact_customer_item_daily"
  )

  & $MysqlDump @args
  if ($LASTEXITCODE -ne 0) {
    throw "mysqldump schema dump failed with exit code $LASTEXITCODE"
  }
}

if (-not $OutDir) {
  $safeStart = $StartDate.Replace("-", "")
  $safeEnd = $EndDate.Replace("-", "")
  $OutDir = Join-Path (Join-Path $PSScriptRoot "transfer_exports") "pos_ods_${safeStart}_${safeEnd}"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$schemaSource = Join-Path $PSScriptRoot "mysql_phase2_dual_fact_schema.sql"
$schemaTarget = Join-Path $OutDir "00_schema.sql"
if (Test-Path -LiteralPath $schemaSource) {
  Copy-Item -LiteralPath $schemaSource -Destination $schemaTarget -Force
} else {
  Write-Host "Schema file not found, dumping table structure from source database..."
  Invoke-SchemaDump -OutFile $schemaTarget
}

$where = "biz_date >= '$StartDate' AND biz_date <= '$EndDate'"

Invoke-Dump -Table "dim_customer_profile" -OutFile (Join-Path $OutDir "01_dim_customer_profile.sql")
Invoke-Dump -Table "fact_customer_shop_daily" -Where $where -OutFile (Join-Path $OutDir "02_fact_customer_shop_daily_${StartDate}_to_${EndDate}.sql")
Invoke-Dump -Table "fact_customer_item_daily" -Where $where -OutFile (Join-Path $OutDir "03_fact_customer_item_daily_${StartDate}_to_${EndDate}.sql")

@"
Export range: $StartDate to $EndDate
Source: $User@$HostName`:$Port/$Database

Import order:
1. 00_schema.sql
2. 01_dim_customer_profile.sql
3. 02_fact_customer_shop_daily_${StartDate}_to_${EndDate}.sql
4. 03_fact_customer_item_daily_${StartDate}_to_${EndDate}.sql
"@ | Out-File -LiteralPath (Join-Path $OutDir "README_IMPORT_ORDER.txt") -Encoding utf8

Write-Host "Export completed:"
Write-Host $OutDir
