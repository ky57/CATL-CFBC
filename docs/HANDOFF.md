# CATL-CFBC-CF-01 项目交接说明

> 交接时间：2026-11-13 23:15（Asia/Shanghai）
> 交接对象：接手继续开发 / 运维的 AI 或工程师
> 一句话结论：系统已在本机（192.168.1.8:46995）常驻运行，登记、修改、删除、每日 18:20 前自动汇总、浅色/深色适配均已可用；数据库当前为空（测试记录已删除）。

---

## 1. 项目概况

CATL-CFBC-CF-01 是一个内网故障信息登记系统：

- 登记项：拉线（Line，L1–L6）、维修物品（功率板 / ACDC / DCDC / 中位机）、故障原因
- 每条记录可修改、删除
- 每天 18:15 自动把当天多条记录合并成一条汇总，18:20 前可直接复制使用
- 数据存 SQLite，同时生成每日 Markdown / JSON / CSV / JSONL 归档
- 手机、电脑浏览器自适应；配色跟随系统（浅色 / 深色）
- 抬头：蓝色背景 + `CATL-CFBC-CF-01`
- 表单背景：半透明 PCBA 电路图（浅色、深色各一套矢量图）
- 零第三方依赖，仅 Python 标准库；前端为原生 HTML/CSS/JS，无构建步骤

### 路径

| 视角 | 路径 |
| --- | --- |
| Windows 共享盘 | `Z:\CATL\CATL-CFBC-InfoDB` |
| Linux 本机（共享源） | `/srv/sw-file/CATL/CATL-CFBC-InfoDB` |
| Samba 共享 | `\\192.168.2.10\sw-file\CATL\CATL-CFBC-InfoDB` |

> 早期临时项目 `/srv/sw-file/seven/catl-cfbc-db` 已删除，不要再引用。

---

## 2. 当前运行状态（接手先读）

| 项 | 当前值 |
| --- | --- |
| 正式访问地址 | `http://192.168.1.8:46995/` |
| 同机第二网段 | `http://192.168.2.10:46995/`（服务监听 0.0.0.0） |
| 进程 | PID `3105451`，用户 `cxw`，`python3 app.py --port 46995 --force` |
| 启动时间 | 2026-11-13 22:55:16 |
| 独立运行目录 | `/var/lib/catl-cfbc/runtime`（通过 `CFBC_RUNTIME` 指定） |
| 标准输出日志 | `/var/lib/catl-cfbc/stdout.log` |
| 数据库 | `data/cfbc_records.db`，`schema_version=2` |
| 当前记录数 | **0 条**（会话中唯一的测试记录已被删除） |
| 当前汇总数 | **0 条** |
| Windows 旧实例 | 已停止（`192.168.1.4:46995` 无响应） |
| 防火墙 | `46995/tcp` 已放行 `192.168.1.0/24`、`192.168.2.0/24` |
| 开机自启 | **未配置**（主机重启后需手动拉起） |

重要：**只允许一个 `app.py` 实例写库。** 数据库放在 SMB 共享盘上，SQLite 使用
DELETE 日志模式；两个实例同时写会有锁冲突、归档互相覆盖的风险。如果以后要在
Windows 上再启动 `启动.bat`，先停掉本机 Linux 实例，或反之。

---

## 3. 技术栈与目录

- Python 3.10+（本机运行 3.13，Windows 端曾用 3.14）
- 标准库：`http.server`、`sqlite3`、`threading`、`json`、`csv` 等
- 前端：原生 JS（IIFE）、CSS 变量、`<dialog>`、`:has()`、`prefers-color-scheme`
- 无 pip 依赖、无 npm、无构建产物

```
CATL-CFBC-InfoDB/
├─ app.py                      后端：HTTP + SQLite + 归档 + 汇总线程
├─ 启动.bat / 后台启动.bat / 停止服务.bat   Windows 启动脚本
├─ scripts/
│  ├─ daily_digest.py          日报取数脚本（复用 app.py 的归档函数）
│  ├─ start_background.ps1     Windows 后台启动
│  └─ stop_background.ps1      Windows 停止（读 runtime/server.json 的 PID）
├─ static/
│  ├─ index.html               页面结构
│  ├─ style.css                全部样式（含深色模式）
│  ├─ app.js                   全部前端逻辑
│  ├─ pcba-circuit.svg         浅色 PCBA 背景
│  ├─ pcba-circuit-dark.svg    深色 PCBA 背景（本次新增）
│  └─ favicon.svg
├─ data/cfbc_records.db        SQLite 主库
├─ logs/YYYY-MM-DD.jsonl       当天原始记录（编辑/删除后会重写）
├─ daily/YYYY-MM-DD.{md,json,csv}  每日归档
├─ docs/preview-*.png          旧版界面截图（已过时）
├─ runtime/                    Windows 端运行时信息（server.json / port.txt）
└─ README.md                   使用说明
```

### 环境变量

| 变量 | 作用 | 本项目用法 |
| --- | --- | --- |
| `CFBC_HOME` | 数据/日志/归档/运行目录根 | 测试时指向临时目录，避免污染正式库 |
| `CFBC_RUNTIME` | 仅覆盖 runtime 目录（本次新增） | Linux 实例用 `/var/lib/catl-cfbc/runtime`，避免覆盖 Windows 端 `runtime/server.json` |
| `CFBC_PORT` | 端口（默认随机） | 未使用，命令行 `--port` 优先 |

> `APP_CODE = "CATL-CFBC"` **不要改**。Windows 启动脚本通过
> `/api/health` 返回的 `app` 字段判断实例是否在运行；页面抬头
> `CATL-CFBC-CF-01` 是独立的展示文案。

---

## 4. 本次会话完成的工作

### 4.1 跟随系统的浅色 / 深色模式

- `static/style.css` 末尾新增 `@media (prefers-color-scheme: dark)`：
  - 页面背景、卡片、表单、选项、记录列表、每日汇总、归档、日期控件、页脚、Toast、编辑弹窗全部深色适配
  - 蓝色抬头保留品牌色，深色模式下略微加深
- 新增 `static/pcba-circuit-dark.svg`：深色版 PCBA 纹理（浅绿色走线）
- `static/index.html`：
  - `theme-color` 提供浅色 `#083d88` / 深色 `#04172e` 两个媒体查询版本
  - `color-scheme` 改为 `light dark`
- 原生日期控件、滚动条跟随系统深色
- 已用系统浅色 / 深色偏好分别截图验证

### 4.2 抬头标题

- 页面 H1：`CATL-CFBC` → **`CATL-CFBC-CF-01`**
- 浏览器标签页标题同步：`CATL-CFBC-CF-01 · 故障信息收集`
- 因标题变长，`@media (max-width: 420px)` 下字号改为
  `clamp(1.62rem, 7.6vw, 2rem)`，320px 宽手机仍单行显示

### 4.3 文案：拉线 → Line

用户明确要求把表单里的「拉线」改成 `Line`，并删除小字说明。

已改（仅 Web UI 文案）：

- 表单区块标题：`拉线` → `Line`
- 删除小字：`选择本次作业所在拉线`
- L1–L6 卡片下方说明：`拉线` → `Line`
- 右侧统计标题：`按拉线` → `按 Line`
- 修改弹窗字段名、选项说明、前端校验提示：改为 `Line`
- 无障碍 `legend`：改为 `Line`

**未改**（已知不一致，见第 10 节）：

- 每日汇总文本仍为 `拉线：...`、`【CATL-CFBC】...`
- Markdown 归档表头、CSV 表头仍为 `拉线`
- README、SQL 示例仍为 `拉线`

### 4.4 记录修改 / 删除

每条「最近记录」增加 **修改**、**删除** 按钮：

- 修改：`<dialog>` 弹窗，可改拉线（Line）、维修物品、故障原因；保存后调用后端更新
- 删除：`window.confirm` 二次确认后删除
- 修改/删除后：
  - 更新 `records`
  - 重写当天 `logs/YYYY-MM-DD.jsonl`
  - 重新生成当天 `daily/*.md/json/csv`
  - 若当天已有汇总，自动刷新；若删到 0 条，自动删除汇总

后端接口（POST，不是 PUT/DELETE）：

- `POST /api/records/<id>/update`
- `POST /api/records/<id>/delete`

### 4.5 每日汇总（18:20 前变成一条）

用户需求：一天 5–6 条记录，最后汇总成一条有用信息，18:20 前要用。

实现：

- 新表 `daily_summaries`
- 每天 **18:15**（服务器本地时间）自动生成当天汇总，18:20 前可用
  - 常量：`SUMMARY_DEADLINE_HOUR=18`、`SUMMARY_DEADLINE_MINUTE=15`
  - 后台线程 `summary_deadline_loop` 每 30 秒检查
  - 服务在 18:15 后启动时，`main()` 里的 `maybe_auto_summary()` 会补生成
  - 只有当天没有汇总且记录数 > 0 时才自动生成
- 手动生成：页面右侧「每日汇总」面板 → `立即汇总 / 重新汇总`
- 复制：`复制汇总` 按钮，优先 Clipboard API，HTTP 环境回退 `execCommand`
- 汇总不是破坏性的：原记录保留，汇总只是额外生成的一条信息
- 汇总内容：标题 + 总条数 + 拉线分布 + 物品分布 + 每条明细
- 当天新增/修改/删除记录后，若汇总已存在会自动刷新（保留 auto/manual 类型）
- 汇总写入 `daily_summaries`，并作为 `summary` 字段进入每日 JSON；
  Markdown 归档新增「三、每日汇总」区块（块引用形式）
- 自动刷新：页面原有 60 秒轮询会带出最新汇总

示例汇总文本（当前格式）：

```
【CATL-CFBC】2026-11-13 维修汇总：共 5 条
拉线：L1×1、L2×1、L3×1、L5×1、L6×1
物品：功率板×1、ACDC×1、DCDC×2、中位机×1
明细（5 条）：
1. [22:49] L1/功率板：更换电容 16pcs
2. [22:49] L3/DCDC：输出电压偏低，已更换 DCDC 模块
...
```

### 4.6 Linux 常驻运行与端口

- 在本机（共享所在服务器）以 `cxw` 用户常驻运行，地址 `192.168.1.8:46995`
- 新增 `CFBC_RUNTIME` 环境变量，Linux 端使用独立运行目录
  `/var/lib/catl-cfbc/runtime`，不覆盖 Windows 端 `runtime/server.json`
- 防火墙放行 `46995/tcp`（`192.168.1.0/24`、`192.168.2.0/24`）
- 当前未配置 systemd / 开机自启

### 4.7 文档

- `README.md` 已更新：深色模式、修改/删除、每日汇总、Linux 运行方式、新接口

---

## 5. 数据库结构

`data/cfbc_records.db`，`schema_version=2`，使用 DELETE 日志模式（SMB 上不要开 WAL）。

### records

| 字段 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `work_date` | 工作日 `YYYY-MM-DD` |
| `line` | `L1`–`L6` |
| `item` | `功率板` / `ACDC` / `DCDC` / `中位机` |
| `fault_reason` | 故障原因，必填，≤1000 字 |
| `created_at` | ISO 时间（带时区） |
| `created_ts` | Unix 时间戳，用于排序 |
| `source_ip` / `user_agent` | 排查用，不在页面展示 |

### daily_summaries

| 字段 | 说明 |
| --- | --- |
| `work_date` | 主键，一天一条 |
| `summary` | 汇总全文 |
| `total` | 汇总时记录条数 |
| `auto` | 1=自动（18:15 或启动补生成），0=手动 |
| `created_at` | 首次生成时间 |
| `updated_at` | 最近刷新时间 |

### 其他

- `meta`：`schema_version`
- `v_daily`：按日期看明细的视图
- 编辑/删除会重写 `logs/YYYY-MM-DD.jsonl`（不是追加）
- 归档文件在每次记录变更、汇总生成、跨日、启动预热时重新生成

---

## 6. HTTP API 清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 页面 |
| GET | `/api/health` | 健康检查、端口、今日/总条数 |
| GET | `/api/bootstrap` | 页面初始化：配置、日期、统计、记录、汇总 |
| GET | `/api/records?date=YYYY-MM-DD&limit=120` | 某天记录 + 统计 + `summary` |
| GET | `/api/stats?date=` | 某天统计 |
| GET | `/api/dates` | 有记录的日期（最近 90 天） |
| POST | `/api/records` | 新增记录 |
| POST | `/api/records/<id>/update` | 修改记录 |
| POST | `/api/records/<id>/delete` | 删除记录 |
| POST | `/api/summary` | 生成/刷新汇总，`{"date":"YYYY-MM-DD"}`，不传 date 为今天 |
| GET | `/api/daily/YYYY-MM-DD.md` | Markdown 归档 |
| GET | `/api/daily/YYYY-MM-DD.json` | JSON 归档 |
| GET | `/api/daily/YYYY-MM-DD.csv` | CSV 归档 |
| GET | `/api/export.csv?date=` | 强制重新生成并下载 CSV |

新增/修改/删除的 JSON 字段：

```json
{"line":"L4","item":"功率板","fault_reason":"更换电容 16pcs"}
```

新增响应包含 `record`、`stats`、`summary`、`today`；修改/删除响应包含
`record`/`deleted`、`stats`、`summary`、`today`。

curl 示例：

```bash
BASE=http://192.168.1.8:46995

# 新增
curl -X POST $BASE/api/records -H 'Content-Type: application/json' \
  -d '{"line":"L1","item":"功率板","fault_reason":"更换电容 16pcs"}'

# 修改 id=1
curl -X POST $BASE/api/records/1/update -H 'Content-Type: application/json' \
  -d '{"line":"L2","item":"ACDC","fault_reason":"保险丝熔断"}'

# 删除 id=1
curl -X POST $BASE/api/records/1/delete

# 手动汇总今天
curl -X POST $BASE/api/summary -H 'Content-Type: application/json' -d '{}'
```

---

## 7. 启动 / 停止 / 部署

### Linux（当前正式方式）

```bash
cd /srv/sw-file/CATL/CATL-CFBC-InfoDB
CFBC_RUNTIME=/var/lib/catl-cfbc/runtime \
  nohup python3 app.py --port 46995 --force \
  > /var/lib/catl-cfbc/stdout.log 2>&1 &
```

- 以 `cxw` 用户运行（项目文件属主是 `cxw`，Samba 映射也是 `cxw`）
- 重启：`kill <PID>` 后再执行上面的命令
- 查看 PID：`cat /var/lib/catl-cfbc/runtime/server.json`
- 日志：`/var/lib/catl-cfbc/stdout.log`
- 端口固定 46995；防火墙只放行内网网段

### Windows（备用，不要与 Linux 同时写库）

- `启动.bat`：前台启动，显示随机端口
- `后台启动.bat`：后台启动并打开浏览器
- `停止服务.bat`：读取 `runtime/server.json` 的 PID 停止
- Windows 端 `runtime/server.json` 目前仍是旧实例信息（PID 25676，已停止）；
  如需清理，运行一次 `停止服务.bat`，脚本发现进程不存在会删除运行时文件
- 如果以后改在 Windows 运行，Linux 端必须先停

---

## 8. 测试 / 回归清单

### 后端（用临时目录，不碰正式库）

```bash
cd /srv/sw-file/CATL/CATL-CFBC-InfoDB
CFBC_HOME=/tmp/cfbc-test python3 app.py --port 0 --force
# 从 /tmp/cfbc-test/runtime/port.txt 取端口
```

已验证过的场景：

- 6 条记录 → 手动汇总，明细/统计正确
- 修改记录 → 汇总自动刷新、JSONL 重写、归档更新
- 删除记录 → 汇总条数减少；删空 → 汇总被删除、归档恢复空状态
- 不存在的 id → 404；非法 line → 400；空日期汇总 → 400
- 18:15 后清空汇总，后台线程约 30 秒内自动重建（auto=1）
- 归档 Markdown 包含「三、每日汇总」，JSON 包含 `summary`
- 页面浅色 / 深色、电脑 / 手机、编辑弹窗均截图核验

### UI 回归

1. 电脑 + 手机各开一次页面，确认抬头 `CATL-CFBC-CF-01`、Line 区块无小字
2. 切系统深色模式，刷新，确认整体变暗、PCBA 纹理为浅绿色
3. 新增 2 条记录 → 修改其中一条 → 删除另一条
4. 点「立即汇总」→ 检查文本 → 点「复制汇总」
5. 切到历史日期，确认修改/删除/汇总只作用于该日期

---

## 9. 已知问题 / 注意事项

1. **单写实例**：SMB 上的 SQLite 同时被两个 `app.py` 写有风险；当前只有 Linux 实例在跑。
2. **术语不统一**：Web UI 已用 `Line`，但汇总文本、Markdown/CSV 表头、README 仍是「拉线」。
   如果用户要求统一，改 `app.py` 的 `build_summary_text()`、`generate_daily_archive()`、
   `README.md`；同时评估下游日报脚本是否按表头解析 CSV。
3. **汇总不是删除原记录**：用户说“汇总成一条”，当前实现是「保留明细 + 额外生成一条汇总」。
   如果实际要求是把当天多条记录合并替换为一条，需要改数据模型和删除逻辑，务必先确认。
4. **18:15 自动**：比用户说的 18:20 留了 5 分钟余量；只要服务在运行，18:15 后
   每 30 秒检查一次；18:15 之后新增记录也会在 30 秒内自动补汇总。
5. **服务无鉴权**：能访问内网端口的人都能新增/修改/删除；如需要，加口令或限制来源 IP。
6. **未配置开机自启**：主机重启后服务不会自动恢复。
7. **无自动化测试**：改动后按第 8 节手动回归。
8. **`<dialog>` / `:has()`**：需要较新的 Chrome / Edge / Safari / Firefox；
   老浏览器可能显示异常。
9. **HTTP 下复制**：非 HTTPS 环境 Clipboard API 不可用，走 `execCommand` 回退；
   iOS Safari 上可能仍被拦截，失败时提示手动复制。
10. **归档文件会被重写**：编辑/删除会重写 JSONL；如果外部有 tail/采集程序，需要知道这一点。
11. **`docs/preview-*.png` 已过时**：仍是旧抬头、无汇总/修改按钮的截图。
12. **版本号**：`VERSION` 仍为 `1.0.0`；`APP_CODE` 必须保持 `CATL-CFBC`。

---

## 10. 建议后续任务（按优先级）

1. **和用户确认汇总语义**：保留明细（当前）还是当天只留一条汇总记录。
2. **统一术语**：确认后把汇总/CSV/Markdown/README 的「拉线」统一为 `Line`。
3. **配置开机自启**：为 Linux 写 systemd unit（注意以 `cxw` 运行、设置
   `CFBC_RUNTIME=/var/lib/catl-cfbc/runtime`、固定 46995）。
4. **单实例保护**：在 Linux 上也可用 `--force` 之外的方式阻止第二实例；
   或让 Windows 启动脚本检测局域网实例。
5. **可选鉴权**：修改/删除接口目前无保护，内网共享环境下可接受，但可加简单口令。
6. **更新预览图**：重新生成 `docs/preview-desktop.png` / `preview-mobile.png`。
7. **补自动化测试**：至少覆盖记录增删改、汇总生成/刷新、归档一致性。
8. **汇总可编辑**（如果需要）：当前汇总只自动生成，不能手工改文字。

---

## 11. 关键代码位置（行号可能随改动漂移）

`app.py`：

| 内容 | 位置 |
| --- | --- |
| 汇总时间常量 | 第 41–42 行 |
| `CFBC_RUNTIME` | 第 50 行 |
| `daily_summaries` 建表 | 第 122 行附近 |
| 字段校验 `validate_record_fields` | 第 169 行 |
| 汇总：`fetch_summary` / `build_summary_text` / `save_summary` | 第 305–393 行 |
| `refresh_summary_if_exists` / `maybe_auto_summary` / `summary_deadline_loop` | 第 374–420 行 |
| `rebuild_jsonl` / `update_record` / `delete_record` | 第 488–580 行 |
| `read_payload` | 第 890 行 |
| `route_post`（新增/修改/删除/汇总路由） | 第 959 行 |
| `api_bootstrap` / `api_records`（返回 summary） | 第 1062–1100 行 |
| 启动补汇总 + 线程启动 | `main()` 内 |

`static/`：

| 内容 | 文件 |
| --- | --- |
| 抬头、Line 区块、汇总面板、修改弹窗 | `index.html` |
| 深色主题、记录操作按钮、汇总/弹窗样式 | `style.css`（末尾两段新样式） |
| `renderSummary`、`openEdit`、`submitEdit`、`removeRecord`、`generateSummary`、`copySummary` | `app.js` |
| 深色 PCBA 素材 | `pcba-circuit-dark.svg` |

---

## 12. 接手自检

- [ ] `curl http://192.168.1.8:46995/api/health` 返回 `ok:true`
- [ ] 确认没有第二个 `app.py` 在写同一个库
- [ ] 改后端前先用 `CFBC_HOME=/tmp/...` 起临时实例测试
- [ ] 不要修改 `APP_CODE` / `LINE` 字段名 / SQLite 日志模式
- [ ] 改表结构时补兼容迁移（`CREATE TABLE IF NOT EXISTS` 之外要考虑旧库）
- [ ] 每次涉及记录变更，检查 `records`、`logs/*.jsonl`、`daily/*`、`daily_summaries` 四处是否一致
- [ ] 修改前端后，浅色/深色、电脑/手机各看一遍
