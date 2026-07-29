# PostgreSQL 连接说明

## 本地连接

当前项目已接入本地 PostgreSQL 健康检查，默认配置如下：

```text
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=historical_agent
POSTGRES_USER=postgres
POSTGRES_PASSWORD=admin
```

配置来源：

- 默认值：`apps/api/settings.py`
- 环境变量示例：`.env.example`

## 当前状态

已验证本机连接可用：

```text
database=historical_agent
user=postgres
server=PostgreSQL 17.9
```

当前已在 `historical_agent` 数据库正式建表：

```text
core_tables=19
current_app_tables=23+
regions=6
categories=10
modern_countries=5
polities=5
tools=7
pgvector=enabled
historical_events.embedding=vector
```

当前后端默认使用 PostgreSQL。完整管理后台还依赖事件审计、知识库、事件向量列和向量重建任务表。

完整初始化入口：

```text
infrastructure/database/init.sql
```

它会按顺序执行：

```text
schema.sql
schema_event_management.sql
schema_knowledge.sql
schema_vector_optional.sql
schema_vector_jobs.sql
seed_reference_data.sql
```

其中 `schema_knowledge.sql` 和 `schema_vector_optional.sql` 要求本机 PostgreSQL 已安装 pgvector。

基础表结构和基础字典种子数据：

```text
infrastructure/database/schema.sql
infrastructure/database/seed_reference_data.sql
```

pgvector 已在本机 PostgreSQL 17.9 中安装并启用：

```text
extension=vector
version=0.8.2
database=historical_agent
```

本机 Visual Studio Build Tools 的实际路径为：

```text
C:\Program
```

后续如需重新编译 pgvector，可使用：

```bat
call C:\Program\VC\Auxiliary\Build\vcvars64.bat
set "PGROOT=D:\software\pgsql"
nmake /F Makefile.win
nmake /F Makefile.win install
```

向量检索扩展脚本：

```text
infrastructure/database/schema_vector_optional.sql
```

已验证 `schema.sql + schema_vector_optional.sql` 可以在事务中成功执行。

## API 健康检查

安装 API 依赖并启动服务后，可以访问：

```text
GET /health/db
```

未安装 `psycopg` 时，健康检查会使用本机 `psql` 命令行回退验证连接；安装 `psycopg[binary]` 后会自动优先使用 Python 驱动。

## 建表命令

如果要初始化当前完整应用所需表结构，推荐执行：

```bash
psql -h localhost -p 5432 -U postgres -d historical_agent -f infrastructure/database/init.sql
```

如果只需要不依赖 pgvector 的基础历史事件和 Agent 运行表，可以执行：

```bash
psql -h localhost -p 5432 -U postgres -d historical_agent -f infrastructure/database/schema.sql
psql -h localhost -p 5432 -U postgres -d historical_agent -f infrastructure/database/seed_reference_data.sql
```

样例事件关系种子依赖样例事件已存在，不放入完整初始化入口。需要补样例关系时再单独执行：

```bash
psql -h localhost -p 5432 -U postgres -d historical_agent -f infrastructure/database/seed_sample_relations.sql
```
