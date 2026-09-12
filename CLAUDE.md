# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PC Reselling Manager：管理从雅虎拍卖 / 煤炉购入、在中国出售的显卡与整机设备。显卡是一进一出
（一个买价、一个卖价），整机是一进多出（一笔总价买回来，拆成 CPU / 显卡 / 内存 / 硬盘等部件分别卖）。

**业务规则的权威说明在各领域模块的模块 docstring 里**，改逻辑前先读对应的那一份：
[cards.py](backend/src/cards.py)（汇率口径与金额换算）、[devices.py](backend/src/devices.py)（整机一进多出）、
[funds.py](backend/src/funds.py)（资金池 FIFO 分摊）、[fx/service.py](backend/src/fx/service.py)（三层取汇率）、
[api/inventory_api.py](backend/src/api/inventory_api.py)（合并列表）、[schema.py](backend/src/schema.py) 顶部（状态流转与全部枚举）。
本文件补充的是这些 docstring 之外的东西——命令、跨文件的结构约定、以及容易踩的坑。

代码与注释一律中文，docstring 解释**为什么这么做**而不是复述代码做了什么，新增代码保持同一风格。

## 常用命令

```powershell
start.bat                 # 开发启动：后端 + 前端 dev server 共用一个控制台，关窗即停

# 单独起后端（监听 9910）
conda activate PC_Reselling
cd backend; python main.py
$env:PC_RESELLING_RELOAD = "1"     # 开热重载（只监视 backend/*.py）
$env:PC_RESELLING_ENABLE_DOCS = "1" # 打开 /docs，默认关闭（局域网里那是一份免鉴权的路由清单）

# 单独起前端（监听 9911，/api 代理到 127.0.0.1:9910）
cd webside; npm install; npm run dev

pyinstaller.bat           # 打包成单 exe，产物在 Releases\v1.0.0\
```

- Python 在 conda 环境 `PC_Reselling`（3.12）里。`start.bat` / `pyinstaller.bat` 都先调
  `ensure_env.bat`：按全路径找环境的 `python.exe`（不依赖 `conda activate`——它需要 `conda init`
  做过 shell 集成，双击打开的终端里用不了），找不到就 `conda create` 建一个，依赖缺失就补装
  `requirements.txt`。环境名、Python 版本、依赖路径只写在 `ensure_env.bat` 一处，改这些改那里。
- 在 `pyinstaller.bat` 所在目录**不能**直接敲 `pyinstaller`——cmd 会解析到这个 bat 自身，要用 `python -m PyInstaller`。
- **项目里没有任何测试、linter 或 formatter 配置**，不要假装有；验证靠起服务点页面。
- 首次运行需要 `conf.ini`（gitignore，后端会生成一份默认的），建表在启动时自动跑。

端口：前端 dev 9911 / 后端 9910 / 图床（另一项目）9990。

## 架构

```
webside (Vue3 + Element Plus, hash 路由)
  └─ /api 代理 ──> FastAPI :9910
                      ├─ api/*_api.py   路由 + Pydantic 校验 + SQL
                      ├─ cards / devices / funds / fx / media   领域逻辑
                      └─ db.py          PyMySQL 连接池（无 ORM，手写 SQL）
                            ├──> MySQL（业务数据 + 全部非 MySQL 配置 + 汇率缓存）
                            ├──> Image_hosting 图床（图片/视频本体）
                            └──> Frankfurter / ECB（历史牌价）
```

打包后同一个进程既是 API 又托管前端 dist（`web_static.py`），开发时前端由 Vite 提供。

### 配置分两处，别搞混

- `conf.ini`：**只有** MySQL 连接与监听端口。每项都能被 `PC_RESELLING_*` 环境变量覆盖（见 `conf.py:_SPEC`）。
- `app_settings` 表（`settings_store.py`）：其余全部配置——图床地址/Token、汇率源、JWT 密钥。
  用户在网页上改、下一个请求就生效。**新增可配置项默认加到这里**，不要往 conf.ini 塞。

### 钱的算法：一份实现，两个模块共用

`devices.py` 直接 import `cards.py` 的 `_to_cny / _purchase_side / _dec / _iso / _round_rate`。
这是刻意的——抄一份的下场是某天只改了其中一处，显卡页和整机页的合计从此对不上。改换算口径时
只动 `cards.py`，并确认两边的调用方都还成立。

两条贯穿全系统的硬约定：

- **汇率方向**：`rate` = 「1 日元 = 多少人民币」（约 0.0421）。日元折人民币是**乘以** rate。
  方向只定义在 `fx/service.py` 的 `BASE` / `QUOTE` 两个常量上；再要换向，得同时改那两个常量、
  `cards._to_cny` / `funds._to_cny` 的乘除，以及库里全部存量汇率（照 `schema._migrate_fx_rate_direction`
  的样子写一个取倒数的迁移）。前端显示取 6 位小数——0.0421 留 4 位只剩两位有效数字。
- **缺汇率不当零**：任何一项该折算却折不出来时，含它的合计返回 `None`（前端显示「—」），
  绝不按 0 计入——那会算出一个看着正常、实际严重偏高的利润。

### 资金池是全量派生数据

`fund_allocations` 与回写到 `cards` / `devices` 的 `pool_purchase_cny / pool_intl_cny / pool_fx_rate`
都由 `funds.rebuild()` 整体重算得出，从不增量维护。**任何会影响池子的写路径都必须触发重算**——
新增/编辑/删除卡片或设备走 `funds.sync_card_and_rebuild()` / `sync_device_and_rebuild()`，
注资与扣款的增删改走 `funds.rebuild()`。忘了调用的症状是列表里的成本停在旧值。

`fund_draws` 上的 `card_id` / `device_id` 两列互斥，两张归属表的 `pool_*` 三列同名同义，
所以 `funds.py` 里的同步与回写是按 `_OWNERS` 参数化的一套代码，别为整机再复制一份。

### 枚举的单一事实来源在后端，文案在前端

`schema.py` 顶部的 `CARD_STATUSES` / `MEDIA_CATEGORIES` / `DEVICE_PART_TYPES` / `SOURCE_PLATFORMS` /
`CURRENCIES` / `FUND_SOURCES` / `FUND_DRAW_CATEGORIES` 是唯一定义，经 `/options/enums` 下发；
后端只发 key，中日英三套文案在 `webside/src/i18n/locales/{zh-CN,ja,en}.js`。

加一个状态要同时改：`schema.py` 的列表、三个 locale 文件、`webside/src/utils/format.js` 的
`STATUS_TAG_TYPE` 与 `STATUS_ORDER`。少改一处的表现是页面上出现裸 key 或排序错位。

### 库存合并列表在 Python 侧做

`api/inventory_api.py` 把 `cards` 和 `devices`（含展开的 `device_parts` 二级行）规范化成同一种行，
筛选、排序、分页全在内存里完成——成本与利润不是数据库列，是按汇率快照算出来的。
新增可排序列要同时加进 `_SORT_KEYS` 并在规范化函数里产出该字段。

### 建表与迁移：只加不改

`schema.py` 在每次启动时无条件跑一遍：`CREATE TABLE IF NOT EXISTS` + `_MIGRATIONS` 里逐条
`_ensure_column`。没有版本号表，新列往 `_MIGRATIONS` 里加即可，跑多少次都一样。

唯一会**改存量数据**的是 `_migrate_fx_rate_direction()`（汇率换向取倒数），它跑第二遍就会把
数据改回去，所以自己在 `app_settings` 里记了一个标记来保证只跑一次。再有这类迁移照它写，
别塞进 `_MIGRATIONS`。

## 写代码时的具体约束

- **SQL 一律用 `%s` 占位**，永不 f-string 拼用户输入。读走 `db.query/query_one`，写走
  `db.execute/insert`，跨多条语句的原子操作用 `db.transaction()`。
- **批量取关联数据**，别 N+1：`cards.load_media` / `devices.load_parts` / `devices.part_media_counts`
  都是「一次 IN 查询再分组」的现成范式。
- **序列化必须显式转 Decimal 与 date**（见各模块的 `serialize`），直接丢给 FastAPI 会在序列化阶段
  报一个指不到具体字段的错。
- `main.py` 里 `mount_spa(app)` **必须最后调用**，它的根路径兜底会吃掉所有未匹配路由；`/api` 下
  未匹配的路径必须 404，回 index.html 会让前端拿到 200 + 一整页 HTML 当数据读。
- 媒体表只存指针（`stored_name` / `public_url`），文件本体在图床；删除接口的 `purge` 参数决定是否
  连图床上的文件一起删。
- 鉴权：Bearer JWT，默认**永不过期**，靠 `users.token_version` 自增作废旧令牌（改密码 / 禁用账号）。
  新增受保护路由挂 `dependencies=[Depends(require_auth)]`（管理员用 `require_admin`）。

## 前端的三个非常规模式

- **详情页就是编辑页，没有编辑弹窗、没有保存按钮**：`views/CardDetail` 与 `views/DeviceDetail` 里
  每个值都是一个直接可改的控件（`InlineField.vue` 负责「平时长得像文本、悬浮才浮出边框」那层皮），
  改动经 `composables/useAutoSave.js` 防抖后自动 PUT。这份 composable 是唯一实现，两个详情页共用——
  它处理的三件事（存的过程中又改了要续存、离开页面前 flush、回填 id 不能反过来触发保存）每一件写错
  都表现为「数据莫名其妙丢了一次」。**别再引入第二套表单**：列表页只负责跳转，不再持有任何编辑状态。
  保存响应与 GET 是同一个形状（`cards_api._result` / `devices_api._result`，含 money、fund_draws、
  status_logs、warnings），所以存完直接刷新展示部分即可，不必补一发 GET；但**绝不能拿它回灌表单**，
  请求往返那几百毫秒里敲的字会被覆盖掉。
- **草稿行**：点「新增」就 `POST /cards/draft`（或 `/devices/draft`）建一行 `is_draft=1` 的空记录，
  然后直接跳进它的详情页——这样图片能立刻上传，新增与编辑也就是同一个界面。离开详情页时若它仍是
  草稿（一个字都没存过）就删掉；漏网的由启动时的 `_cleanup_stale_drafts()`（超过 2 小时）清理。
  只传了图没改字段的那种卡会在上传后立刻存一次转正，否则离开时会被当空草稿连图一起删掉。
  再加类似的「先建后填」实体请沿用这套，而不是在前端缓存文件。
- **整机的部件数组每次整体提交**，后端 `devices_api._write_parts` 按 **id 增量写**（带 id 更新 /
  无 id 插入 / 未提交的删除）——**绝不能改回「先全删再全插」**：行 id 一换，挂在部件上的图片会被
  外键级联删掉。前端对应地要在保存后把返回的 id 贴回行上（`mergePartIds`），并且「这一行算不算空」
  只有 `constants/parts.js` 的 `isBlankPart()` 一处判断：详情页据它决定提交不提交，部件卡据它画淡
  一档，两边不一致就会出现部件莫名多出来或消失。

其余：`@` 别名指向 `webside/src`；全站强制暗色主题（`main.js`）；`api/http.js` 统一处理 401
（清 token 跳 `#/login`）与断网（全屏遮罩 + 轮询 `/api/health` 恢复），所以各页面不用自己 catch 这两类错。
