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

# 打包成单 exe：激活环境 → npm run build → PyInstaller，产物在 Releases\<VERSION>\
pyinstaller.bat           # 版本号改脚本顶部的 VERSION；只替换旧 exe，同目录的 conf.ini 保留
```

- Python 在 conda 环境 `PC_Reselling`（3.12）里。`start.bat` 通过 `conda activate` 激活环境
  （与 `D:\Project\FreeMarket_Manager` 同一套做法），激活失败时会回退到 `activate.bat` 的全路径。
  首次使用需先手动建环境：`conda create -y -n PC_Reselling python=3.12`，再
  `pip install -r requirements.txt`。
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

### 打包后的桌面外壳：运行窗口 + 托盘（只在冻结态存在）

exe 是 **windowed**（`pc_reselling.spec` 里 `console=False`）：双击后出现的是一个 Tk 运行窗口
（`log_window.py`），点 X 弹「收入任务栏 / 退出程序 / 取消」，托盘图标（`tray.py`）常驻右下角。
与 `D:\Project\FreeMarket_Manager` 同一套做法，窗口版式也刻意保持一致。开发态（`start.bat` /
`python main.py`）完全不装这一层——命令行里 Ctrl+C 就是退出。

为什么不直接在控制台窗口上做：**控制台窗口被关闭时 Windows 会强制结束进程，那次关闭拦不住也
取消不了**，所以控制台上根本没有「点 X 收起来」这回事。控制台仍然分配一个（`console_win.py`），
但隐藏、并摘掉它的关闭按钮，只当 stdout/stderr 的真实落点，内容由运行窗口转发显示。

三处顺序/依赖错了都不会报错，只会「窗口不出现」或「日志是空的」：

- `main.py` 里那段冻结态初始化必须在 `logging.basicConfig()` **之前**——basicConfig 会把当时的
  `sys.stderr` 绑进 StreamHandler，晚一步接管，日志就只进隐藏控制台、窗口里一行都没有。
- spec 的 `excludes` 里**不能**再有 `tkinter`（运行窗口就是 Tk 写的），`hiddenimports` 要留着
  `pystray` 的子模块（它的 Windows 后端是运行时按平台挑的，静态分析看不见）。
- 托盘走的是 `uvicorn.Server` 而不是 `uvicorn.run()`（`server.py:_serve`）：后者把 Server 藏在
  函数里，外面拿不到 `should_exit`，「退出程序」就没法做成优雅停机。

图标：`webside/public/static/` 下的 `logo.png`（托盘与窗口，pystray 和 Tk 都读不了 SVG）和
`favicon.ico`（exe 自身，PyInstaller 只收 .ico），两个都是照着 `logo.svg` 的图形转出来的；
改 logo 要一起重做，否则托盘上还是老图标。

### 打包时 conda 的 DLL 必须压过 PATH

`_ssl` / `_hashlib` / `_sqlite3` / `_lzma` / `_bz2` / `_ctypes` / `_tkinter` / `pyexpat` 依赖的那批
DLL 在 conda 里不跟 `python.exe` 放一起，而是单独住在 `<env>\Library\bin`。PyInstaller 解析依赖时
按 PATH 找，于是捞到的是 anaconda base（甚至 Git for Windows）里的同名 DLL——版本对不上，exe
一启动就弹 `DLL load failed while importing _ssl: 找不到指定的程序`（ERROR_PROC_NOT_FOUND：
DLL 找到了，但缺少 `_ssl.pyd` 要的导出符号）。

`pc_reselling.spec` 顶部因此把 `sys.prefix` 下的 `Library\bin` / `DLLs` / 环境根目录顶到 PATH 最前，
**别删**。这不是缺依赖，pip 装不出来，换台机器或装了别的软件就可能捞到另一份。

调试打包后的启动问题时注意：**onefile 的 exe 是父子两个进程**，引导进程只持有
`PyInstallerOnefileHiddenWindow`，真正跑 Python、持有运行窗口与托盘图标的是它的子进程。
按启动时拿到的那个 PID 去找窗口会一无所获，看着就像「窗口没起来」。

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
换归属人也是这样一条写路径，但不用另外处理：扣款的 `contributor` 就是归属人，
`sync_owner_draws()` 比对得出它变了。

`fund_draws` 上的 `card_id` / `device_id` 两列互斥，两张归属表的 `pool_*` 三列同名同义，
所以 `funds.py` 里的同步与回写是按 `_OWNERS` 参数化的一套代码，别为整机再复制一份。
注资上的专款两列（`fund_injections.card_id / device_id`）也走同一个键（`funds._earmark_of`）。

### 归属人：货是谁的，也是钱从谁的池里扣

`owner`（`cards` / `devices` / `device_parts` 三列）有两层含义：货是谁的，以及**买它的钱从谁的
池里扣**——`cards.uses_pool()` 就是「有没有归属人」，设了就扣，没有确认这一步。没设归属人的货
不进池，按购入日牌价折成本。候选就是注资的出资人名单（`fund_contributors`，写入走
`funds.ensure_contributor`）。部件的 `owner` 只是标签（NULL 表示跟随整机），扣款只认整机。
前端三处都用 `components/OwnerSelect.vue`。

每人一个池子：货的扣款只在归属人的注资批次里先进先出。**池子允许为负**：钱不够照扣，欠的
记在 `fund_draws.shortfall`，按扣款日牌价暂估；这个人之后的注资会先顶上欠款（所以 FIFO
不限制「只能吃扣款日之前进池的钱」）。按人汇总与总账的余额都减掉欠款，因此可以是负数。

专款注资（`card_id` / `device_id` 有值）只给那一件货扣、排在它的候选最前面，别的扣款碰不到。
它是给「当初没走池子、后来才补归属人」的老货补录资金用的（`schema._migrate_shares_to_owner`）：
按普通 FIFO 补，老货会先吃掉更早的批次，把后面的货挤成欠款。

已停用、只留不删：出资比例 `fund_shares`（迁移时读过一次）、`fund_source` / `pool_confirmed_at`
两列（原来的「确认扣除」闸门）。分红也随出资比例一起去掉了——一件货只有一个归属人，利润就是他的。

### 实物置换

置换（`swaps.py`，规则看它的 docstring）只在单卡 ↔ 整机显卡部件之间，**换实物不换账**：
品牌 / 型号 / 核心编号（部件上是 `spec`）/ 序列号和图片互换，价格、资金池、归属人、状态不动，
所以不触发 `funds.rebuild()`。显卡图搬到部件上时原分类记在 `device_part_media.category`，
换回来能归位。记录在 `item_swaps`（含置换前快照），跟着两头详情响应的 `swaps` 字段下发。

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
状态色只有 `format.js` 那一份，标签（`StatusTag.vue`）、下拉选项（`StatusSelect.vue`，四处状态
下拉共用它，别再在页面里手写 `v-for el-option`）、时间轴圆点、概览页的图全从它取；
挑颜色的规则写在那份 map 的注释里（红绿是语义色、暖色表示等人动手、未购入的画描边）。
部件类型另有一份 `PART_TYPE_COLOR`（同文件，走 `PartTypeTag.vue`，库存列表的二级行与整机
详情的部件表共用），与状态色刻意不共用——状态是流程、类型是分类。新增部件类型不配色也不会
出错，会落到 `other` 的灰色。

### 库存合并列表在 Python 侧做

`api/inventory_api.py` 把 `cards` 和 `devices`（含展开的 `device_parts` 二级行）规范化成同一种行，
筛选、排序、分页全在内存里完成——成本与利润不是数据库列，是按汇率快照算出来的。
新增可排序列要同时加进 `_SORT_KEYS` 并在规范化函数里产出该字段。
**筛选也全在内存里**：`_load_universe()` 一次取回全部非草稿行，`_select()` 是唯一的筛选实现，
列表、统计、联动下拉（`/inventory/facets`）都只走它。下拉是联动的——每个选项的件数是把它
代进当前其余条件真跑一遍 `_select` 数出来的，所以前端**不维护任何候选清单**，全从 facets 取。
新增筛选条件：参数只加在 `_inventory_filters` 这一个依赖上；原始列的判断进 `_card_ok` /
`_device_ok` / `_part_ok`，成本 / 利润 / 归属人这类算出来的值进 `_match_derived`；要做成下拉的
在 `_facet_candidates` 里登记取值。
按状态筛选时整机里状态命中的部件、以及类型筛选选了「部件 / 某种部件」（`kind=part` +
`part_type`，此时不出整机行）时满足条件的部件，都会**单独成为顶层行**（`_solo_part`，`kind=part` + `solo` +
`parent`），点击进所属整机并停在该部件的标签上；它只计件数、不进统计的金额合计（没有单件成本）。

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
- 鉴权：Bearer JWT，默认**永不过期**，靠 `users.token_version` 自增作废旧令牌（改密码 / 重置密码 /
  停用 / 强制下线）。新增受保护路由挂 `dependencies=[Depends(require_auth)]`（管理员用 `require_admin`）。
  登录响应只有 `auth.issue_login()` 一个出口（账号密码与门户单点登录共用，前端 `stores/auth.js` 的
  `enter()` 只认这一种形状）；用户行的列清单是 `auth.USER_COLUMNS`。用户管理（`users_api.py`）的
  护栏写在它的 docstring 里：不能对自己停用 / 降级 / 删除，至少留一个启用中的管理员。

### 门户单点登录（`src/portal_sso/` + `api/sso_api.py`）

门户（`D:\Project\Portal`）当 OIDC 提供方，PCR 当客户端，与 FreeMarket_Manager 的 `portal_sso` 同一套。
流程与理由在 `portal_sso/flow.py` 的 docstring；认人只认 `sso_identities` 里的 `(provider, sub)`，首次按用户名
匹配（`identity.py`）。门户建的号 `password_hash` 是 `security.NO_PASSWORD`（列是 NOT NULL，不改成可空）。

**PCR 是经门户的「整站」代理打开的**（`https://门户/api/proxy/<卡片 id>/__portal__/http/127.0.0.1:9910/`），
后端收到的路径已被剥掉前缀，门户也不发前缀头；整站模式还会改写 Location、正文里的完整地址和查询串里指回门户的地址。
所以（每一条的理由在 `sso_api.py` 模块头）：

- **`/sso/login` 是跳板页，不读 `base` 参数**：门户卡片按回调地址推出来的入口带的 `base` 只到门户根，被代理时是错的；
  由浏览器从自己的 `location` 剥掉 `api/v1/sso/login` 得到站点根，**base64url 编码**成 `root=` 再去 `/sso/start`
  （明文会被门户 `_clean_query` 换成 `http://127.0.0.1:9910/`）。
- **`/sso/start` 不发 303**，回一张页面 `location.replace(atob(...))` 去门户：303 指向门户的 Location 会被整站模式
  折成「经代理访问门户」，丢掉门户的登录态。
- **回调后跳 `/#/login` 这个根绝对地址**，别拼成 base + `#/login`：各种访问方式由各自那一层折回正确位置。
- 前端跳去登录时用**相对当前页面**的地址（`ssoApi.loginUrl`），别写成 `/api/...`——那会打到门户自己身上。
- 门户卡片上登记的回调地址是**被代理后的那个**；系统配置 → 单点登录 页按当前页面拼出来给你看，从哪个入口打开就显示哪个。
- 路由守卫在 `/login` 带着 `sso_ticket` 时不能因为「已登录」就跳走，否则票被吞掉、永远进的是上一个账号。

## 前端的三个非常规模式

- **详情就是编辑界面，没有保存按钮，以弹窗形式浮在库存列表上**：`views/CardDetail` 与 `views/DeviceDetail`
  里每个值都是一个直接可改的控件（标签在上、两列网格的 `.pcr-form`，定义在 App.vue），
  改动经 `composables/useAutoSave.js` 防抖后自动 PUT。这份 composable 是唯一实现，两个详情共用——
  它处理的三件事（存的过程中又改了要续存、关闭前 flush、回填 id 不能反过来触发保存）每一件写错
  都表现为「数据莫名其妙丢了一次」。**别再引入第二套表单**：列表只负责打开详情，不持有任何编辑状态
  （部件一览弹窗是只读的，点一行打开整机详情并停在那个部件的标签上）。
  保存响应与 GET 是同一个形状（`cards_api._result` / `devices_api._result`，含 money、fund_draws、
  status_logs、warnings），所以存完直接刷新展示部分即可，不必补一发 GET；但**绝不能拿它回灌表单**，
  请求往返那几百毫秒里敲的字会被覆盖掉。
  弹窗由 `views/Cards` 持有，**开着哪一件只记在路由里**（`/cards?open=card-12` / `device-5`，整机另可带
  `&tab=部件类型`）：后退键关的是弹窗，刷新还开着同一件。老地址 `/cards/:id`、`/devices/:id` 是重定向。
  详情组件只收 `id` / `tab` 两个 prop、发 `close`，并 `defineExpose({ beforeClose })`（flush + 删空草稿）；
  列表页在 `onBeforeRouteUpdate` / `onBeforeRouteLeave` 里 await 它——关闭按钮、点遮罩、后退、点侧栏
  去别的页都是路由变化，守卫是唯一的汇合点。**别在详情组件里自己用路由守卫**，它已经不是路由组件了。
  弹窗的样式（隐藏 Element 标题栏、顶栏吸顶）在 `App.vue` 的 `.pcr-detail-dialog`，因为 el-dialog 被
  teleport 到 body，scoped 样式够不着。
- **草稿行**：点「新增」就 `POST /cards/draft`（或 `/devices/draft`）建一行 `is_draft=1` 的空记录，
  然后直接打开它的详情——这样图片能立刻上传，新增与编辑也就是同一个界面。关闭详情时若它仍是
  草稿（一个字都没存过）就删掉；漏网的由启动时的 `_cleanup_stale_drafts()`（超过 2 小时）清理。
  只传了图没改字段的那种卡会在上传后立刻存一次转正，否则关闭时会被当空草稿连图一起删掉。
  再加类似的「先建后填」实体请沿用这套，而不是在前端缓存文件。
- **整机的部件数组每次整体提交**，后端 `devices_api._write_parts` 按 **id 增量写**（带 id 更新 /
  无 id 插入 / 未提交的删除）——**绝不能改回「先全删再全插」**：行 id 一换，挂在部件上的图片会被
  外键级联删掉。前端对应地要在保存后把返回的 id 贴回行上（`mergePartIds`）。「这一行提交不提交」
  只有 `constants/parts.js` 一处判断，而且它和「填没填」是两回事，别合并：
  `hasPartContent()` 只看内容，用来在界面上标「未填写」；`isBlankPart()` 决定提交，库里已经有的行
  （载入时打上 `_keep`）、手动添加的行、传过图的行一律提交，**只有摆出来的七个模板槽位会因为没填
  而被丢掉**。清空文字不再等于删除部件——那条老规矩会让人在改字段时把图片连带删掉。

详情弹窗的版式（两个详情共用 `components/DetailShell.vue`，照 `D:\Project\FreeMarket_Manager`
库存管理的商品表单）：**弹窗定高、自己不滚动，追求一屏看全**——顶栏（名称 / 状态 / 总账药丸 /
自动保存 / 关闭）+ 左边一摞分区卡片 + 右边 280px 的图片侧栏（侧栏自己滚）。**没有模块导航**：
字段能平铺就平铺，只有「偶尔才看」的内容收进左列最下面那张标签页卡（`.pd-tabs-card`，吃掉剩余
高度、在卡里滚）。
- 显卡：基本信息卡 + 购入 / 出售并排两张卡（`.pd-pair`，字段一一对应）常驻；标签页只有「资金与结算 /
  记录」；侧栏是五个分类的 `MediaManager compact`。
- 整机：基本信息卡 + 购入卡（四个值一行）常驻；标签页是「部件 / 资金与结算 / 记录」；侧栏默认是整机照片，在「部件」页选中
  一件时换成那一件的图（再点一下取消选中就回到整机照片），部件编辑区里不再有图片区。

卡片、紧凑表单、药丸、结算明细这些类是**全局的 `.pd-*`**（App.vue，有一段注释列全了）：它们写在页面
传给 DetailShell 的插槽里，scoped 够不着，两份页面各抄一遍又必然改漂。字段排法用 `.pd-row`（flex
折行，宽度由页面的 `.f-*` 给，别拉成等宽两列）或 `.pd-grid`（`--pd-cols` 改列数）；控件一律
`size="small"`（骨架里抬到 30px）。`.pd-form` 的 13px 字号只给桌面——手机输入框必须 16px，否则 iOS
聚焦会放大整页。`el-tabs` 只当标签条用，内容区按 `active` 用 `v-if` 渲染：图片组件一挂载就去拉图。
左右分栏（资金与结算）用容器查询看卡片宽，不看屏宽。手机上整块退回可滚动，顶栏 sticky。

新增字段先往常驻的卡片里放，**别把常驻区撑到把标签页卡挤没**——放不下再考虑收进标签页。
整机的「部件」页是左列表 + 右编辑区（`DevicePartPanel` 只编辑选中的那一件），选中记的是本地
`_uid`——模板槽位和刚加的部件还没有服务端 id。列表就是「哪几件卖了、哪几件还空着」的一览。

其余：`@` 别名指向 `webside/src`；全站强制暗色主题（`main.js`）；`api/http.js` 统一处理 401
（清 token 跳 `#/login`）与断网（全屏遮罩 + 轮询 `/api/health` 恢复），所以各页面不用自己 catch 这两类错。

### 手机浏览器访问

断点 **768px**，三处必须同源：`composables/useIsMobile.js`、`App.vue` 的 `@media`、各页面自己的
`@media`。不一致时正好 768px 宽的设备会一半按手机、一半按电脑渲染。

另有一档 **1200px 的「紧凑宽度」**（`useIsCompact`，同一个文件），专管「宽表格摆不摆得下」：
iPad 竖屏内容区只有 700 像素上下，宽表在这一档就换卡片列表（平板上两列网格），而排版
（筛选器、弹窗、单列化）仍按 768 走。页面里的平板专属规则写 `(min-width: 769px) and (max-width: 1200px)`。
这一档里侧栏收成 68px 的图标栏（`Layout.vue` 的 `isRail`，语言和退出收进底部按钮的下拉），
手机仍是抽屉、桌面仍是完整侧栏。

第三个判据 `useIsTouch()`（`(hover: none)`）给脚本用：日期选择器一律 `:editable="!isTouch"`——
Element 的日期框是个 `<input>`，iOS 上点一下会同时弹出面板和软键盘，键盘把面板顶出视口。
同类的 iOS 输入细节也都已按这个思路处理，新加字段照做：`el-input-number` 要显式给
`inputmode`（Element 不给默认值，iPhone 上弹的是全字母键盘）；网址 / 用户名 / Token 这类
输入框加 `autocapitalize="off" autocorrect="off" spellcheck="false"`（不加的话 `http://` 会被
改成 `Http://`、`admin` 变成 `Admin`）。当二级菜单用的 `el-tabs` 挂 `.pcr-touch-tabs`（App.vue），
触屏上换成原生横滑。

**「有没有悬浮」和「屏幕多宽」是两个判据，别混用。** 窄窗口的桌面浏览器仍然有鼠标，而平板
屏幕很宽却只有手指。所以「热区大小、悬浮才出现的东西」一律用 `@media (hover: none)`，
「排版怎么摆」才用宽度断点。最典型的是 `MediaGallery` / `MediaManager` 的缩略图排序只有 HTML5 拖放，触屏不触发它，所以触屏上
另给一个「设为封面」按钮（`useMediaSort.moveToFront`，与拖拽同一条写路径）——第一张图就是
列表里的封面（`format.firstImage`），没有它手机上换不了封面。

**宽表在窄屏换成卡片列表，而不是砍列或让它横滚。** 库存列表（11 列约 1400px）这么做：`v-if="isMobile"` 渲染一份卡片列表，`v-else` 保留原表格。
两边用的是**同一批数据、同一个点击处理**，卡片列表不持有任何自己的状态——它是同一个列表的
另一种排法，不是第二套列表（取数、筛选、分页仍然只有一份）。新增可显示字段时两边都要加，
漏掉的表现是「手机上看不到这一列」。

**打包后由后端托管时，压缩和缓存是必需的，不是优化。** `main.py` 挂了 `GZipMiddleware`，
`web_static._HashedStatic` 给 `/assets` 发一年期的 `immutable`。没有它们手机首次打开要下约
2.8MB（有压缩是 0.85MB），库存列表一页 39KB（压缩后 5KB）。`immutable` **只能**给 `/assets`：
那底下的文件名带内容哈希，而 `/static/logo.svg` 名字固定、`index.html` 更记着该加载哪几个
哈希文件名，缓存住了等于前端永远停在旧版本。

同样出于首屏体积，**ECharts 是按需引入的**（`components/EChart.vue` 里的 `echarts.use([...])`，
全量引入是 1.0MB / gzip 344KB，而概览页就是首页）。两条连带的规矩：加新图表类型要**同时**在那份
`use()` 里注册对应的 `XxxChart` / `XxxComponent`，漏了的表现是那张图不报错、就是画不出来；
以及**不能** `import 'echarts/theme/dark'`——那个主题文件是 UMD 的，会把全量 echarts 又拉回来。
所以每张图的文字色 / 轴色 / 提示框底色都得自己给全，一律从 `utils/chartTheme.js` 取，别手写颜色。

**Element 的弹层有自己写死的宽度，页面上的 `@media` 管不到。** 已经处理掉的两处：
日期**区间**选择器是并排两个月历、写死 646px（单月历 322px），窄屏上改成起 / 止两个单日期
选择器（`views/Cards/index.vue`）；确认框 `--el-messagebox-width` 写死 420px，在 `App.vue` 里
按窄屏压成 94vw。再引入新的弹层组件时先去 `element-plus` 的 CSS 里查一下它有没有固定宽度——
超过约 336px（360px 屏减去两侧内边距）的都会被裁掉，而被裁掉的通常正好是右下角的确认按钮。
