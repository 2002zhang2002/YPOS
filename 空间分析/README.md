# 绌洪棿鍒嗘瀽

杩欎釜鐩綍鐢ㄤ簬鍋氬鎴风偣浣嶃€佸簱瀛樼儹鍔涖€侀攢閲忕儹鍔涖€佸簱瀛樺帇鍔涘垎甯冪瓑鍦扮悊鍒嗘瀽銆?
## 鐩綍璇存槑

- `sql/01_geo_tables.sql`
  鍒涘缓鍦扮悊鍒嗘瀽鎶ヨ〃琛細
  - `rpt_geo_customer_daily`
  - `rpt_geo_customer_item_daily`

- `scripts/build_geo_reports.py`
  鍒锋柊鎶ヨ〃琛ㄥ苟瀵煎嚭 CSV / GeoJSON銆?
- `exports/`
  鑴氭湰杩愯鍚庣殑瀵煎嚭缁撴灉鐩綍銆?
- `map_demo/`
  棰勭暀缁欏悗缁湴鍥炬紨绀洪〉闈€?
## 涓ゅ紶鏍稿績琛?
### 1. `rpt_geo_customer_daily`

涓€琛?= 鏌愬ぉ + 鏌愬鎴?搴楅摵

閫傚悎鍋氾細

- 瀹㈡埛搴撳瓨鐐逛綅鍥?- 瀹㈡埛閿€閲忕偣浣嶅浘
- 瀹㈡埛搴撳瓨鍘嬪姏鍥?- 鎸夋。浣?/ 鏈嶅姟绔?/ 瀹㈡埛缁忕悊绛涢€夊湴鍥?
鍏抽敭瀛楁锛?
- `biz_date`
- `shop_id`
- `cust_id`
- `cust_name`
- `cust_seg_name`
- `base_type_name`
- `ss_name`
- `slsman`
- `longitude`
- `latitude`
- `sale_qty`
- `stock_qty`
- `order_qty`
- `stock_amount`
- `stock_sale_ratio`

### 2. `rpt_geo_customer_item_daily`

涓€琛?= 鏌愬ぉ + 鏌愬鎴?搴楅摵 + 鏌愬晢鍝?
閫傚悎鍋氾細

- 鏌愬晢鍝佸簱瀛樺垎甯冨浘
- 鏌愬晢鍝佸姩閿€鍒嗗竷鍥?- 鏌愬晢鍝佸湪涓嶅悓鍖哄煙/妗ｄ綅鐨勫簱瀛樺帇鍔涘姣?
鍏抽敭瀛楁锛?
- `biz_date`
- `shop_id`
- `cust_id`
- `cust_seg_name`
- `item_key`
- `item_name`
- `barcode`
- `longitude`
- `latitude`
- `sale_qty`
- `stock_qty`
- `order_qty`
- `stock_amount`
- `stock_sale_ratio`

## 鎬庝箞杩愯

鍦?`E:\Get_Pos_Data` 涓嬫墽琛岋細

```powershell
.\tools\python38\python.exe customer_history_job\绌洪棿鍒嗘瀽\scripts\build_geo_reports.py `
  --host 127.0.0.1 `
  --port 3306 `
  --user root `
  --password <MYSQL_PASSWORD> `
  --database pos_ods `
  --start-date 2026-04-01 `
  --end-date 2026-04-07 `
  --level customer
```

## 杩愯鍚庝細鐢熸垚

鍦?`exports/` 涓嬶細

- `rpt_geo_customer_daily.csv`
- `rpt_geo_customer_daily.geojson`
- `rpt_geo_customer_item_daily_top5000.csv`
- `rpt_geo_customer_item_daily_top5000.geojson`

璇存槑锛?
- `rpt_geo_customer_daily.geojson`
  閫傚悎鐩存帴鍋氬鎴风偣浣嶅浘銆佺儹鍔涘浘銆?
- `rpt_geo_customer_item_daily_top5000.geojson`
  褰撳墠鍏堝鍑衡€滃簱瀛樺帇鍔涙渶楂樷€濈殑 5000 鏉″晢鍝佺偣浣嶏紝鏂逛究鍦板浘璇曢獙锛岄伩鍏嶄竴娆″鍑哄叏閲忓晢鍝佽繃澶с€?
`--level` 璇存槑锛?
- `customer`
  鍙敓鎴愬鎴锋棩鍦扮悊瀹借〃锛岄€熷害鏈€蹇紝寤鸿鍏堢敤杩欎釜鍋氱偣浣嶅拰鐑姏鍥俱€?
- `item`
  鍚屾椂鐢熸垚瀹㈡埛鍟嗗搧鏃ュ湴鐞嗗琛紝鏁版嵁鏇寸粏浣嗘洿鎱€?
- `all`
  褰撳墠绛夊悓浜庡悓鏃剁敓鎴愬鎴峰眰鍜屽晢鍝佸眰銆?
## 鎺ㄨ崘鍏堢湅浠€涔?
鍏堢湅瀹㈡埛鏃ュ眰锛?
1. 鐐瑰ぇ灏?= `stock_qty`
2. 鐐归鑹?= `stock_sale_ratio`
3. 绛涢€?= `cust_seg_name / ss_name / slsman / biz_date`

杩欐牱鏈€瀹规槗鐪嬪嚭锛?
- 鍝簺鍖哄煙搴撳瓨楂?- 鍝簺鍖哄煙閿€閲忎綆
- 鍝簺鍖哄煙搴撳瓨鍘嬪姏澶?
## 鎸囨爣浠庡摢閲屾潵

`rpt_geo_customer_daily` 鏄粠 `fact_customer_item_daily` 鎸夆€滄棩鏈?+ 瀹㈡埛/搴楅摵鈥濊仛鍚堝嚭鏉ョ殑銆?
鏍稿績鎸囨爣鍙ｅ緞锛?
- `sale_qty`
  鎵€閫夋椂闂存绱閿€鍞噺锛屾潵婧愭槸 `SUM(fact_customer_item_daily.t_big_saleamt)`銆?
- `stock_qty`
  鏈熸湯搴撳瓨閲忥紝鏉ユ簮鏄墍閫夋椂闂存鍐呮渶鍚庝竴澶╃殑 `SUM(fact_customer_item_daily.t_big_stoamt)`銆?
- `order_qty`
  鎵€閫夋椂闂存绱璐繘閲忥紝鏉ユ簮鏄?`SUM(fact_customer_item_daily.t_big_stockamt)`銆?
- `sale_amount`
  閿€鍞噾棰濓紝鏉ユ簮鏄?`SUM(fact_customer_item_daily.t_salemny)`銆?
- `stock_amount`
  搴撳瓨閲戦锛屾潵婧愭槸 `SUM(fact_customer_item_daily.t_stockmny)`銆?
- `stock_sale_ratio`
  搴撳瓨鍘嬪姏锛岃绠楁柟寮忔槸 `鏈熸湯搴撳瓨閲?/ 鏈熼棿绱閿€鍞噺`銆?
瀛楁鍙ｅ緞纭锛?
```text
t_big_stoamt    = 搴撳瓨閲?t_big_stockamt  = 璐繘閲?t_big_saleamt   = 閿€鍞噺
```

閲嶈璇存槑锛?
搴撳瓨鏄揩鐓ф寚鏍囷紝涓嶈兘璺ㄦ棩鏈熺疮璁°€傚洜姝ゅ鎴峰眰鍦板浘閲?`stock_qty` 鍙栨墍閫夋椂闂存鏈€鍚庝竴澶╁簱瀛橈紱閿€鍞拰璐繘鏄祦閲忔寚鏍囷紝鍙互鍦ㄦ椂闂存鍐呯疮璁°€?
瀹㈡埛妗ｄ綅銆佷笟鎬併€佹湇鍔＄珯銆佸鎴风粡鐞嗐€佺粡绾害鏉ヨ嚜 `dim_customer_profile`銆?
鍏宠仈鏂瑰紡锛?
```sql
fact_customer_item_daily.shop_id = dim_customer_profile.license_code
```

## 浜や簰鍦板浘鎬庝箞鐢?
鎵撳紑锛?
```text
map_demo/geo_customer_demo.html
```

鐒跺悗鍦ㄩ〉闈㈠乏渚ч€夋嫨锛?
```text
exports/rpt_geo_customer_daily.geojson
```

鍦板浘鏀寔锛?
- 榧犳爣鎷栨嫿
- 婊氳疆缂╂斁
- 鐐瑰嚮瀹㈡埛鐐逛綅鏌ョ湅寮圭獥
- 鍕鹃€夊涓鎴?搴楅摵鍚庣敓鎴愬贰搴楃嚎璺?- 鎸夌洿绾胯窛绂昏嚜鍔ㄤ紭鍖栨嫓璁块『搴?- 濉啓楂樺痉 Web鏈嶅姟 Key 鍚庤幏鍙栫湡瀹為┚杞﹁矾绾?- 涓€閿墦寮€楂樺痉/鐧惧害鍦板浘椤甸潰缁х画瀵艰埅
- 鎸夋棩鏈熺瓫閫?- 鎸夋。浣嶇瓫閫?- 鎸夋湇鍔＄珯绛涢€?- 鎸夊鎴风粡鐞嗙瓫閫?- 鎼滅储瀹㈡埛鍚嶇О鎴?shop_id

宸″簵瀵艰埅鐢ㄦ硶锛?
1. 宸︿晶鍏堢瓫閫夋棩鏈熴€佸鎴风粡鐞嗐€佹湇鍔＄珯绛夎寖鍥淬€?2. 鍦ㄢ€滄湡鏈簱瀛樻渶楂?Top 20鈥濋噷鍕鹃€夎鎷滆鐨勫簵閾猴紝鎴栬€呯偣鍑诲湴鍥剧偣浣嶏紝鍦ㄥ脊绐楅噷鐐光€滃姞鍏ョ嚎璺€濄€?3. 濉啓楂樺痉 Web鏈嶅姟 Key銆侹ey 浼氫繚瀛樺湪鏈満娴忚鍣紝涓嶄細鍐欏叆 HTML 鏂囦欢銆?4. 鍙墜鍔ㄥ～鍐欒捣鐐圭粡绾害锛屼篃鍙互鐐光€滃畾浣嶅綋鍓嶄綅缃€濇垨鈥滃湴鍥句腑蹇冧负璧风偣鈥濄€?5. 鐐瑰嚮鈥滀紭鍖栧苟瑙勫垝鈥濓紝椤甸潰浼氬厛鎸夊氨杩戝師鍒欐帓搴忥紝鍐嶈姹傞珮寰烽┚杞﹁鍒掞紱娴呰摑铏氱嚎鏄湰鍦扮洿绾块『搴忥紝娣辫摑瀹炵嚎鏄珮寰风湡瀹為┚杞﹁矾绾裤€?6. 鐐瑰嚮鈥滄墦寮€楂樺痉鍦板浘瀵艰埅鈥濇垨鈥滄墦寮€鐧惧害鍦板浘璺嚎鈥濓紝鍦ㄥ湴鍥鹃〉闈㈤噷缁х画瀹為檯瀵艰埅銆?
璇存槑锛?
杩欎釜 HTML 浣跨敤 Leaflet 鍜?OpenStreetMap 鍦ㄧ嚎搴曞浘銆傚鏋滅數鑴戜笉鑳借闂缃戯紝搴曞浘鍙兘鍔犺浇涓嶅嚭鏉ワ紝浣嗙偣浣嶆暟鎹拰绛涢€夐€昏緫浠嶇劧鍦ㄩ〉闈㈤噷銆傚悗缁彲浠ユ敼鎴愰珮寰枫€佸ぉ鍦板浘锛屾垨鑰呭唴缃戠绾跨摝鐗囥€?
褰撳墠绾胯矾浼樺寲鍒嗕袱灞傦細

- 娴忚鍣ㄦ湰鍦板厛鎸夆€滅粡绾害鐩寸嚎璺濈鈥濆仛杩戜技鎺掑簭锛岄€傚悎蹇€熷畨鎺掑贰搴楅『搴忋€?- 濉啓楂樺痉 Web鏈嶅姟 Key 鍚庯紝椤甸潰浼氳皟鐢ㄩ珮寰烽┚杞﹁矾寰勮鍒掓帴鍙ｏ紝璁＄畻鐪熷疄閬撹矾璺濈銆侀璁¤€楁椂锛屽苟鍦ㄥ湴鍥句笂鍙犲姞娣辫摑鑹茬湡瀹為┚杞﹁矾绾裤€?
娉ㄦ剰锛氶珮寰峰崟娆￠┚杞﹁矾寰勮鍒掓渶澶氭敮鎸?16 涓€旂粡鐐广€傞〉闈細淇濇寔鈥滄湰鍦版帓搴忓悗鐨勯『搴忊€濅紶缁欓珮寰凤紝楂樺痉璐熻矗鎸夐亾璺绠楄矾绾匡紝涓嶄細鑷姩鎵撲贡閫旂粡鐐归『搴忓仛鍏ㄥ眬鏈€浼?TSP銆?
## 鍚庣画鍙互缁х画鎵╁睍

鍚庨潰鍙互缁х画琛ワ細

- 琛屾斂鍖鸿仛鍚堢儹鍔?- 缃戞牸鑱氬悎
- 瀹㈡埛瀵嗗害鍒嗘瀽
- 鏌愬晢鍝佺殑绌洪棿鎵╂暎瓒嬪娍
- 缁忕含搴﹁仛绫诲垎鏋?
