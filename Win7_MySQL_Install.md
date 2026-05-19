# Win7 64位 MySQL 安装说明

适用场景：

- 操作系统：Windows 7 64位
- 目标：给 `customer_history_job` 脚本提供本地 MySQL 落库环境
- 推荐安装方式：ZIP 免安装包 + Windows 服务

## 先说结论

- 现在没有 MySQL，你的脚本也不是完全不能用。
- 当前配置默认是 `storage_backend=sqlite`，所以不装 MySQL 也可以先采集、先验证、先跑通接口。
- 只有当你想把数据直接写进 MySQL 时，才需要安装 MySQL 并把配置切到 `storage_backend=mysql`。

## Win7 推荐版本

推荐你优先使用：

- MySQL Community Server `5.7.37`
- 包名：`mysql-5.7.37-winx64.zip`

选择这个版本的原因：

- 官方归档页明确提供了 Windows 64 位 ZIP 包。
- MySQL 官方文档说明：`5.7.37` 及以下版本运行在 Windows 时需要的是 Visual C++ 2013 运行库；而 `5.7.40+` 改成依赖 Visual C++ 2019。
- 这对 Win7 更稳，因为较新的 VC++ v14 最新运行库官方页面已经只列出支持 Windows 10/11 和 Windows Server 2016+。

## 官方下载链接

MySQL 官方归档页：

- https://downloads.mysql.com/archives/community/?osva=Windows+%28x86%2C+64-bit%29&version=5.7.37

这个页面里对应的文件名是：

- `mysql-5.7.37-winx64.zip`

直接下载地址：

- https://downloads.mysql.com/archives/get/p/23/file/mysql-5.7.37-winx64.zip

校验值：

- MD5: `9a86ae49d0feacf75afb3361746eee4d`

VC++ 2013 x64 运行库：

- https://aka.ms/highdpimfc2013x64enu

如果上面的短链接打不开，也可以从微软说明页进入：

- https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170

## 安装前检查

1. 确认你的系统至少是 `Windows 7 SP1`。
2. 如果不是 SP1，MySQL 5.7 官方文档提示可能会反复重启并报 `0xc000001d`。
3. 如果不是 SP1，优先方案是先升级到 `Windows 7 SP1`；如果实在不能升级，再考虑使用更老的 MySQL 5.6 归档版本。

## 推荐安装目录

为了避免权限和空格路径问题，建议这样放：

- MySQL 主目录：`C:\mysql57`
- 数据目录：`C:\mysql57\data`
- 配置文件：`C:\mysql57\my.ini`

## 安装步骤

### 1. 安装 VC++ 2013 x64

先安装上面的微软运行库，安装完建议重启一次机器。

### 2. 解压 MySQL ZIP 包

把 `mysql-5.7.37-winx64.zip` 解压到：

- `C:\mysql57`

解压后你应该能看到：

- `C:\mysql57\bin\mysqld.exe`
- `C:\mysql57\bin\mysql.exe`

### 3. 建数据目录

手动创建：

- `C:\mysql57\data`

### 4. 新建配置文件

新建文件：

- `C:\mysql57\my.ini`

内容建议如下：

```ini
[mysqld]
basedir=C:/mysql57
datadir=C:/mysql57/data
port=3306
character-set-server=utf8mb4
default-storage-engine=INNODB
sql_mode=NO_ENGINE_SUBSTITUTION,STRICT_TRANS_TABLES
max_connections=200

[client]
default-character-set=utf8mb4
port=3306
```

### 5. 初始化数据目录

用管理员身份打开 `cmd`，执行：

```bat
cd /d C:\mysql57\bin
mysqld --initialize --console --defaults-file=C:\mysql57\my.ini
```

说明：

- 这一步会初始化系统库。
- 控制台会打印一个临时 `root` 密码，请先记下来。

### 6. 注册成 Windows 服务

还是在管理员 `cmd` 下执行：

```bat
cd /d C:\mysql57\bin
mysqld --install MySQL57 --defaults-file=C:\mysql57\my.ini
net start MySQL57
```

如果后面需要停止：

```bat
net stop MySQL57
```

如果后面需要卸载服务：

```bat
mysqld --remove MySQL57
```

### 7. 登录并改 root 密码

```bat
cd /d C:\mysql57\bin
mysql -u root -p
```

输入初始化时打印的临时密码，然后执行：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY '你的新密码';
```

### 8. 创建业务库并导入表结构

先创建数据库：

```bat
cd /d C:\mysql57\bin
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS pos_ods DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
```

再导入你项目里已经准备好的建表 SQL：

```bat
cd /d C:\mysql57\bin
mysql -u root -p pos_ods < E:\Get_Pos_Data\customer_history_job\mysql_phase1_schema.sql
```

## 脚本如何切到 MySQL

修改文件：

- `E:\Get_Pos_Data\customer_history_job\config.json`

把这些值改掉：

```json
{
  "storage_backend": "mysql",
  "mysql_host": "127.0.0.1",
  "mysql_port": 3306,
  "mysql_user": "root",
  "mysql_password": "你的新密码",
  "mysql_database": "pos_ods"
}
```

## Python 依赖

脚本切 MySQL 前，要先安装 Python 驱动：

```bat
cd /d E:\Get_Pos_Data
.\tools\python38\python.exe -m pip install PyMySQL
```

如果你是离线环境，需要把 `PyMySQL` 的 wheel 包提前下载到本机再安装。

## 验证命令

先单日验证接口，不改增量状态：

```bat
cd /d E:\Get_Pos_Data\customer_history_job
..\tools\python38\python.exe full_customer_history_sync.py --config config.json --validate-single-day --validate-min-rows-per-shop 150
```

如果要正式跑：

```bat
cd /d E:\Get_Pos_Data\customer_history_job
..\tools\python38\python.exe full_customer_history_sync.py --config config.json --mode auto
```

## 常见判断

### 现在没装 MySQL，能不能先用？

可以。

因为脚本现在默认还是：

```json
"storage_backend": "sqlite"
```

也就是说：

- 没装 MySQL：先写 SQLite，照样能采集
- 装好 MySQL：把配置切成 `mysql`，脚本就改写 MySQL

### 什么时候必须装 MySQL？

只有在你要：

- 把数据给别的系统直接查
- 做 MySQL 报表
- 给多人共享查询
- 后续接 BI 或数据平台

这些场景下，MySQL 才是必需的。

## 参考来源

- MySQL 5.7 Windows 安装总览：
  https://dev.mysql.com/doc/refman/5.7/en/windows-installation.html
- MySQL 5.7 ZIP 安装方式：
  https://dev.mysql.com/doc/refman/5.7/en/windows-install-archive.html
- MySQL 5.7 Windows 服务安装：
  https://dev.mysql.com/doc/refman/5.7/en/windows-start-service.html
- MySQL 5.7 Windows 平台限制：
  https://dev.mysql.com/doc/refman/5.7/en/windows-restrictions.html
- MySQL 5.7.37 Windows 64 位归档下载页：
  https://downloads.mysql.com/archives/community/?osva=Windows+%28x86%2C+64-bit%29&version=5.7.37
- Microsoft Visual C++ Redistributable 说明：
  https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170
