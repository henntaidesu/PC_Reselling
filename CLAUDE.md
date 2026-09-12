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

### 开发机对外开放（内网 / 公网）

前后端本来就监听 `0.0.0.0`，Vite 也 `allowedHosts: true`，所以**代码侧不需要为外网改任何东西**。
实际挡住外部设备的是另外三样，症状都不像是它们自己：

- **Windows 防火墙**：入站默认丢弃，表现为连接超时且两个控制台一行日志都没有。以管理员身份
  跑一次 `open_firewall.bat` 放行 9910 / 9911（`open_firewall.bat off` 撤销）。规则名同时被
  `start.bat` 探测用来提示，改名两处一起改。
- **HMR 的 WebSocket 连错地址**：页面能开、改代码不生效、控制台刷连接失败。浏览器默认按
  「页面 host + 9911 + 页面协议」去连，公网 IP 直连时正好对；端口映射换了号、反代成 https、
  内网穿透给了别的域名时对不上，用 `vite.config.js` 顶部那三个 `PCR_HMR_*` 环境变量指定。
- **图片全裂**：`public_base`（系统配置 → 图床）是浏览器用的地址，填成内网 IP 的话外网打不开。

前端 `/api` 一律经 dev server 代理到 `127.0.0.1:9910`，所以只放行 9911 也能完整使用；
真要直连后端端口调接口再放行 9910。**对公网开放前把内置的 admin / admin 改掉**
（`schema.py` 首次建库时会灌这个账号）。

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

- **汇率口径**：`rate` = 「100 日元 = 多少人民币」（约 4.32），与银行牌价的写法一致。日元折
  人民币是 **× rate ÷ 100**。口径定义在 `fx/service.py` 的 `BASE` / `QUOTE` / `RATE_UNIT`，前端
  `format.js` 里另有一份 `RATE_UNIT`，两边必须一致。数据源给的是每 1 日元的价，只在
  `fx.service._scaled()` 里乘一次，此后库里、接口上、页面上流转的都是同一个口径。再要改口径，
  得改这两处常量、`cards._to_cny` / `funds._to_cny` 的算式，并在 `schema._FX_DIRECTION_FIXUPS`
  里按「旧标记 → 换算表达式」加一条，让存量数据跟着换过来。
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

`schema.py` 顶部的 `CARD_STATUSES` / `MEDIA_CATEGORIES` / `DEVICE_PART_TYPES` /
`CURRENCIES` / `FUND_SOURCES` / `FUND_DRAW_CATEGORIES` 是唯一定义，经 `/options/enums` 下发；
后端只发 key，中日英三套文案在 `webside/src/i18n/locales/{zh-CN,ja,en}.js`。

**购买平台不在其中**：它是字典表 `source_platforms`（用户在「系统配置 → 购买平台」里自己加减），
走 `/options/platforms`，与品牌 / 型号同一套路。内置的 `yahoo` / `mercari` / `other` 由
`schema.SOURCE_PLATFORM_SEEDS` 在建库时灌一次（库里存的就是这三个 key，前端对它们有译文），
用户后加的没有译文，原样显示。前端一律走 `composables/usePlatforms.js`，别自己写
`t('platform.' + v)`——自定义平台会被翻成一个裸 key。

加一个状态要同时改：`schema.py` 的列表、三个 locale 文件、`webside/src/utils/format.js` 的
`STATUS_COLOR` 与 `STATUS_ORDER`。少改一处的表现是页面上出现裸 key、排序错位，或标签退回默认色。
状态色只有 `format.js` 那一份，标签（`StatusTag.vue`）、时间轴圆点、概览页的图全从它取；
挑颜色的规则写在那份 map 的注释里（红绿是语义色、暖色表示等人动手、未购入的画描边）。

### 库存合并列表在 Python 侧做

`api/inventory_api.py` 把 `cards` 和 `devices`（含展开的 `device_parts` 二级行）规范化成同一种行，
筛选、排序、分页全在内存里完成——成本与利润不是数据库列，是按汇率快照算出来的。
新增可排序列要同时加进 `_SORT_KEYS` 并在规范化函数里产出该字段。

### 建表与迁移：只加不改

`schema.py` 在每次启动时无条件跑一遍：`CREATE TABLE IF NOT EXISTS` + `_MIGRATIONS` 里逐条
`_ensure_column`。没有版本号表，新列往 `_MIGRATIONS` 里加即可，跑多少次都一样。

唯一会**改存量数据**的是 `_migrate_fx_rate_direction()`（汇率换口径），它跑第二遍就会把数据
换错，所以 `app_settings` 里记着这个库当前是哪个口径，按标记决定要不要动、怎么动；标记不认识
就只记错误日志、一行都不动。再有这类迁移照它写，别塞进 `_MIGRATIONS`。

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
  连图床上的文件一起删。图分两种形态：显卡按五个分类（`card_media` + `MediaManager.vue`），整机
  部件与整机本身各是**平铺的一组**（`device_part_media` / `device_media` + `MediaGallery.vue`），
  后端那套增删查按 `media_api._FLAT_OWNERS` 参数化，两种归属共用一份实现。要给一个还没落盘的
  部件传图时，前端先 `useAutoSave.saveNow()` 把那一行建出来拿到 id（`ensurePartId`）——文件挂在
  行上，行不存在就无处可挂，但这不该变成「你得先填点什么才能拍照」。
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
  外键级联删掉。前端对应地要在保存后把返回的 id 贴回行上（`mergePartIds`）。「这一行提交不提交」
  只有 `constants/parts.js` 一处判断，而且它和「填没填」是两回事，别合并：
  `hasPartContent()` 只看内容，用来在界面上标「未填写」；`isBlankPart()` 决定提交，库里已经有的行
  （载入时打上 `_keep`）、手动添加的行、传过图的行一律提交，**只有摆出来的六个模板槽位会因为没填
  而被丢掉**。清空文字不再等于删除部件——那条老规矩会让人在改字段时把图片连带删掉。

整机详情页的版式：顶部一条摘要（成本 / 已收回 / 盈亏 / 回本率 / 已售件数）+ 一排二级标签
（整机 · CPU · 显卡 · …，标签上的角标是图片数），标签只当导航用，内容在下面单独渲染——挂进
`el-tab-pane` 会把十来个部件一次性全挂载，每个都去拉一遍图片。「整机」页里有一张部件一览表，
点一行跳到那个部件：分页之后总得有一个地方能一眼看完哪几件卖了、哪几件还空着。

其余：`@` 别名指向 `webside/src`；全站强制暗色主题（`main.js`）；`api/http.js` 统一处理 401
（清 token 跳 `#/login`）与断网（全屏遮罩 + 轮询 `/api/health` 恢复），所以各页面不用自己 catch 这两类错。
