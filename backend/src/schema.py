# -*- coding: utf-8 -*-
"""建表与轻量迁移。

启动时无条件跑一遍：``CREATE TABLE IF NOT EXISTS`` 保证新库能自建，``_ensure_column``
保证老库能补上后加的字段。没有版本号表——这个系统的演进方式是「只加不改」，
把每次新增的列写进 _MIGRATIONS 即可，跑多少次都一样。

**唯一的例外是 ``_migrate_fx_rate_direction``**：它要改动存量数据（汇率换口径），
跑第二遍就会把数据改回去，所以它自己在 app_settings 里记了一个标记来保证只跑一次。
再有这类「改数据」的迁移，照它的样子写，别塞进 _MIGRATIONS。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from src import db, settings_store

log = logging.getLogger(__name__)


# ── 枚举取值（后端唯一事实来源，前端通过 /options 端点拿）────────────────── #

# 状态是**一条单线**：已购入 → 待测试 → 测试通过 / 测试不通过 → 回国中 → 转寄中
# → 已签收 → 已打款。「已签收」「已打款」是中国买家的动作，走到「已打款」这笔生意才算完。
# 「测试不通过」是分叉终点，通常不会再往后走（卡有问题，退货或另行处理）。
CARD_STATUSES: List[str] = [
    "purchased",      # 已购入
    "pending_test",   # 待测试
    "test_passed",    # 测试通过
    "test_failed",    # 测试不通过
    "returning",      # 回国中
    "returned",       # 已回国
    "forwarding",     # 转寄中
    "received",       # 已签收（买家）
    "paid",           # 已打款（买家）
]

# 图片/视频分类。顺序即前端标签页顺序。
MEDIA_CATEGORIES: List[str] = [
    "appearance",  # 显卡外观
    "pcb",         # PCB 外观
    "gpu_core",    # GPU 核心
    "gpuz",        # GPU-Z
    "mods",        # mods 测试
]

# 整机设备里的部件类型。顺序即录入表单里「快捷添加」按钮的顺序。
# 内存 / 硬盘一台机器里往往有好几条，所以部件是**一台设备下的多行**，而不是设备上的字段。
DEVICE_PART_TYPES: List[str] = [
    "cpu",          # CPU
    "gpu",          # 显卡
    "ram",          # 内存
    "disk",         # 硬盘
    "motherboard",  # 主板
    "psu",          # 电源
    "cooler",       # 散热
    "case",         # 机箱
    "other",        # 其他
]

# 购买平台**不是枚举**，是 source_platforms 字典表（用户在系统配置里自己加）。这份清单
# 只是首次建库时的初始内容：库里存的就是这三个 key，前端对它们有中日英三套文案；
# 用户后加的平台没有文案，原样显示名字即可（见 webside 的 usePlatforms）。
SOURCE_PLATFORM_SEEDS: List[str] = ["yahoo", "mercari", "other"]

CURRENCIES: List[str] = ["JPY", "CNY"]

# 资金池只装日元：它模拟的是「先把人民币换成日元放在日本的账户里，再用这笔日元买卡」，
# 人民币不需要进池（rate 恒等于 1，进了池只会让 FIFO 里多一堆无意义的批次）。
POOL_CURRENCY: str = "JPY"

# 一张卡的采购资金从哪来。own = 自有资金（按交易日牌价折算，老逻辑）；
# pool = 从资金池扣，成本按被消耗的那几笔注资各自的汇率分段折算。
FUND_SOURCES: List[str] = ["own", "pool"]

# 资金池扣款的用途。purchase / intl_shipping 两类由卡片自动同步（跟着卡上的金额走），
# other 是手工记的池内杂项支出（手续费、代购费…），不计入任何一张卡的成本。
FUND_DRAW_CATEGORIES: List[str] = ["purchase", "intl_shipping", "other"]


# ── 表定义 ──────────────────────────────────────────────────────────────── #

_TABLES: List[Tuple[str, str]] = [
    (
        "app_settings",
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            `key`        VARCHAR(128) NOT NULL,
            `value`      TEXT NULL,
            updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`key`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='除 MySQL 连接以外的全部配置：图床连接、汇率来源、系统参数'
        """,
    ),
    (
        "users",
        """
        CREATE TABLE IF NOT EXISTS users (
            id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
            username       VARCHAR(64) NOT NULL,
            password_hash  VARCHAR(255) NOT NULL,
            is_active      TINYINT(1) NOT NULL DEFAULT 1,
            is_admin       TINYINT(1) NOT NULL DEFAULT 0,
            token_version  INT UNSIGNED NOT NULL DEFAULT 0,
            last_active_at DATETIME NULL,
            created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_users_username (username)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        "gpu_brands",
        """
        CREATE TABLE IF NOT EXISTS gpu_brands (
            id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
            name       VARCHAR(64) NOT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_gpu_brands_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='品牌字典（华硕/微星/技嘉…），录卡时下拉选，可现场新增'
        """,
    ),
    (
        "gpu_models",
        """
        CREATE TABLE IF NOT EXISTS gpu_models (
            id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
            name         VARCHAR(128) NOT NULL,
            -- 已停用：显存那一栏改成了「核心编号」，而核心编号是一张卡一个，
            -- 没有「按型号给默认值」的意义。列按惯例只留不删。
            default_vram VARCHAR(32) NULL,
            sort_order   INT NOT NULL DEFAULT 0,
            created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_gpu_models_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='型号字典，独立于品牌。型号即芯片名，如 RTX 4090 / RTX 5090。'
        """,
    ),
    (
        "source_platforms",
        """
        CREATE TABLE IF NOT EXISTS source_platforms (
            id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
            name       VARCHAR(32) NOT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_source_platforms_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='购买平台字典。原来是写死的三个枚举，改成表是因为买的渠道会变
                   （多一个駿河屋、少一个某某），那不该是一次改代码重新打包'
        """,
    ),
    (
        "cards",
        """
        CREATE TABLE IF NOT EXISTS cards (
            id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
            mgmt_no       VARCHAR(32) NOT NULL COMMENT '系统管理编号 GPU-2026-0001',
            brand         VARCHAR(64) NULL,
            model         VARCHAR(128) NULL,
            core_no       VARCHAR(32) NULL COMMENT 'GPU 核心上的丝印编号，用来证明核心没被换过',
            serial_no     VARCHAR(128) NULL COMMENT '显卡实体序列号',

            source_platform VARCHAR(32) NULL COMMENT 'source_platforms 字典里的 name',
            seller          VARCHAR(128) NULL,
            item_url        VARCHAR(1024) NULL,
            order_no        VARCHAR(128) NULL,

            purchase_date            DATE NULL,
            purchase_amount          DECIMAL(14,2) NULL,
            purchase_currency        VARCHAR(3) NOT NULL DEFAULT 'JPY',
            intl_shipping_amount     DECIMAL(14,2) NULL,
            intl_shipping_currency   VARCHAR(3) NOT NULL DEFAULT 'JPY',
            domestic_shipping_amount DECIMAL(14,2) NULL,
            domestic_shipping_currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
            sale_date                DATE NULL,
            sale_amount              DECIMAL(14,2) NULL,
            sale_currency            VARCHAR(3) NOT NULL DEFAULT 'CNY',

            -- 汇率快照。取到就写死在行里，之后再也不重算：
            -- 汇率每天在动，不快照的话昨天算出来的利润今天会自己变。
            purchase_fx_rate DECIMAL(18,8) NULL COMMENT '100 JPY = ? CNY，按 purchase_date',
            purchase_fx_date DATE NULL COMMENT '实际取到的牌价日（周末/节假日会回退到前一工作日）',
            sale_fx_rate     DECIMAL(18,8) NULL COMMENT '100 JPY = ? CNY，按 sale_date',
            sale_fx_date     DATE NULL,
            fx_manual        TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=汇率被手工改过，自动刷新时跳过',

            -- 采购资金从哪来。'own' 走 purchase_fx_rate（老逻辑）；'pool' 则由
            -- fund_draws / fund_allocations 按注资批次的汇率分段算出成本。
            fund_source VARCHAR(8) NOT NULL DEFAULT 'own',
            -- 选了 'pool' 只是意向，池子要等这里有时间戳才真的少钱：详情页是边填边自动
            -- 保存的，没有这道闸门，购入价刚敲了两位数就已经从池里扣走了。
            -- 改回 'own' 时置回 NULL，否则下次切回资金池会无声无息地又扣一笔。
            pool_confirmed_at DATETIME NULL COMMENT '点「确认扣除」的时间；NULL = 池子未动',
            -- 下面三列是资金池分摊的**结果快照**，由 funds.rebuild() 统一回写。
            -- 冗余在卡片行上是为了让列表/统计不必为每一行再查一次分摊明细（N+1）。
            pool_purchase_cny DECIMAL(14,2) NULL COMMENT '购入价按各注资批次汇率折算后的人民币合计',
            pool_intl_cny     DECIMAL(14,2) NULL COMMENT '国际运费按各注资批次汇率折算后的人民币合计',
            pool_fx_rate      DECIMAL(18,8) NULL COMMENT '这张卡实际吃到的加权汇率，仅供展示',

            status     VARCHAR(24) NOT NULL DEFAULT 'purchased',
            note       TEXT NULL,
            -- 草稿卡：点「新增」就先建一张（好让图片能立刻挂上去），存下第一笔改动即转 0。
            -- 列表、统计一律只算 is_draft=0；未保存就关掉的草稿会被清理掉。
            is_draft   TINYINT(1) NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_cards_mgmt_no (mgmt_no),
            KEY idx_cards_status (status),
            KEY idx_cards_is_draft (is_draft),
            KEY idx_cards_purchase_date (purchase_date),
            KEY idx_cards_sale_date (sale_date),
            KEY idx_cards_serial (serial_no)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        "card_media",
        """
        CREATE TABLE IF NOT EXISTS card_media (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            card_id     INT UNSIGNED NOT NULL,
            category    VARCHAR(24) NOT NULL COMMENT 'appearance/pcb/gpu_core/gpuz/mods',
            kind        VARCHAR(8) NOT NULL DEFAULT 'image' COMMENT 'image / video',
            -- 图床侧的存储名，删除和查详情都靠它
            stored_name VARCHAR(255) NOT NULL,
            public_url  VARCHAR(1024) NOT NULL,
            filename    VARCHAR(255) NULL COMMENT '上传时的原始文件名，仅供展示',
            mime_type   VARCHAR(128) NULL,
            size_bytes  BIGINT UNSIGNED NULL,
            sort_order  INT NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_card_media_card (card_id, category, sort_order),
            CONSTRAINT fk_card_media_card FOREIGN KEY (card_id)
                REFERENCES cards (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='文件本体在图床，这里只存指针'
        """,
    ),
    (
        "card_status_logs",
        """
        CREATE TABLE IF NOT EXISTS card_status_logs (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            card_id     INT UNSIGNED NOT NULL,
            from_status VARCHAR(24) NULL,
            to_status   VARCHAR(24) NOT NULL,
            note        VARCHAR(500) NULL,
            occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_card_status_logs_card (card_id, occurred_at),
            CONSTRAINT fk_card_status_logs_card FOREIGN KEY (card_id)
                REFERENCES cards (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='状态流转history，用于「这张卡在海关卡了多久」这类追溯'
        """,
    ),
    (
        "devices",
        """
        CREATE TABLE IF NOT EXISTS devices (
            id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
            mgmt_no  VARCHAR(32) NOT NULL COMMENT '系统管理编号 DEV-2026-0001',
            title    VARCHAR(128) NULL COMMENT '整机名称，如「戴尔 T7920 工作站」',

            source_platform VARCHAR(32) NULL COMMENT 'source_platforms 字典里的 name',
            seller          VARCHAR(128) NULL,
            item_url        VARCHAR(1024) NULL,
            order_no        VARCHAR(128) NULL,

            -- 采购只有**一笔总价**：整机是一口价买进来的，拆开来卖才产生多笔收入。
            -- 所以购入金额挂在设备上，出售金额挂在 device_parts 的每一行上。
            purchase_date          DATE NULL,
            purchase_amount        DECIMAL(14,2) NULL COMMENT '整机购入总价',
            purchase_currency      VARCHAR(3) NOT NULL DEFAULT 'JPY',
            intl_shipping_amount   DECIMAL(14,2) NULL,
            intl_shipping_currency VARCHAR(3) NOT NULL DEFAULT 'JPY',

            -- 汇率快照，口径与 cards 完全一致：取到就写死，之后不重算。
            purchase_fx_rate DECIMAL(18,8) NULL COMMENT '100 JPY = ? CNY，按 purchase_date',
            purchase_fx_date DATE NULL COMMENT '实际取到的牌价日（非交易日会回退）',

            -- 采购资金从哪来，与 cards 同一套语义：'own' 走 purchase_fx_rate；
            -- 'pool' 则由 fund_draws / fund_allocations 按注资批次的汇率分段算出成本。
            fund_source VARCHAR(8) NOT NULL DEFAULT 'own',
            -- 与 cards 同义：池子要等这里有时间戳才真的少钱（见 cards.pool_confirmed_at）
            pool_confirmed_at DATETIME NULL COMMENT '点「确认扣除」的时间；NULL = 池子未动',
            pool_purchase_cny DECIMAL(14,2) NULL COMMENT '购入总价按各注资批次汇率折算后的人民币合计',
            pool_intl_cny     DECIMAL(14,2) NULL COMMENT '国际运费按各注资批次汇率折算后的人民币合计',
            pool_fx_rate      DECIMAL(18,8) NULL COMMENT '这台设备实际吃到的加权汇率，仅供展示',

            status     VARCHAR(24) NOT NULL DEFAULT 'purchased',
            note       TEXT NULL,
            -- 与卡片同一套草稿机制：点「新增」就先建一台，存下第一笔改动即转 0。
            is_draft   TINYINT(1) NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_devices_mgmt_no (mgmt_no),
            KEY idx_devices_status (status),
            KEY idx_devices_is_draft (is_draft),
            KEY idx_devices_purchase_date (purchase_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='整机设备：一次购入（一笔总价），拆成多个部件分别出售'
        """,
    ),
    (
        "device_parts",
        """
        CREATE TABLE IF NOT EXISTS device_parts (
            id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
            device_id INT UNSIGNED NOT NULL,
            -- cpu / gpu / ram / disk / motherboard / psu / cooler / case / other。
            -- 一台机器里内存、硬盘常常有好几条，所以它们是这张表里的**多行**，
            -- 而不是设备表上的多个字段——字段数写死了就装不下第三条内存。
            part_type VARCHAR(24) NOT NULL DEFAULT 'other',
            brand     VARCHAR(64) NULL,
            model     VARCHAR(128) NULL COMMENT '型号，如 i9-13900K / RTX 4090',
            spec      VARCHAR(128) NULL COMMENT '规格，如 32GB DDR5-6000 / 2TB NVMe',
            serial_no VARCHAR(128) NULL,
            quantity  INT NOT NULL DEFAULT 1 COMMENT '同规格几件合成一行（如 2 条 16G）',

            -- 出售侧：每个部件各卖各的价，一台设备因此有多个出售价格。
            sale_date                  DATE NULL,
            sale_amount                DECIMAL(14,2) NULL COMMENT '这一行的出售总价（含 quantity 件）',
            sale_currency              VARCHAR(3) NOT NULL DEFAULT 'CNY',
            domestic_shipping_amount   DECIMAL(14,2) NULL,
            domestic_shipping_currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
            sale_fx_rate DECIMAL(18,8) NULL COMMENT '按本行 sale_date 取的牌价快照',
            sale_fx_date DATE NULL,

            buyer      VARCHAR(128) NULL,
            status     VARCHAR(24) NOT NULL DEFAULT 'purchased',
            note       VARCHAR(500) NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_device_parts_device (device_id, sort_order, id),
            KEY idx_device_parts_type (part_type),
            KEY idx_device_parts_sale_date (sale_date),
            CONSTRAINT fk_device_parts_device FOREIGN KEY (device_id)
                REFERENCES devices (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='设备部件明细。一台设备多行，内存/硬盘可重复出现；出售价格在这里'
        """,
    ),
    (
        "device_part_media",
        """
        CREATE TABLE IF NOT EXISTS device_part_media (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            part_id     INT UNSIGNED NOT NULL,
            kind        VARCHAR(8) NOT NULL DEFAULT 'image' COMMENT 'image / video',
            stored_name VARCHAR(255) NOT NULL COMMENT '图床侧的存储名，删除靠它',
            public_url  VARCHAR(1024) NOT NULL,
            filename    VARCHAR(255) NULL COMMENT '上传时的原始文件名，仅供展示',
            mime_type   VARCHAR(128) NULL,
            size_bytes  BIGINT UNSIGNED NULL,
            sort_order  INT NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_device_part_media_part (part_id, sort_order, id),
            CONSTRAINT fk_device_part_media_part FOREIGN KEY (part_id)
                REFERENCES device_parts (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='部件图片/视频。不像 card_media 那样分五类——「显卡外观 / PCB / GPU 核心」
                   这套分类只对显卡成立，一条内存、一块主板拍的就是它本身，平铺即可。
                   外键指着 device_parts，所以部件行的 id 必须稳定（见 devices_api._write_parts）'
        """,
    ),
    (
        "device_media",
        """
        CREATE TABLE IF NOT EXISTS device_media (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            device_id   INT UNSIGNED NOT NULL,
            kind        VARCHAR(8) NOT NULL DEFAULT 'image' COMMENT 'image / video',
            stored_name VARCHAR(255) NOT NULL COMMENT '图床侧的存储名，删除靠它',
            public_url  VARCHAR(1024) NOT NULL,
            filename    VARCHAR(255) NULL COMMENT '上传时的原始文件名，仅供展示',
            mime_type   VARCHAR(128) NULL,
            size_bytes  BIGINT UNSIGNED NULL,
            sort_order  INT NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_device_media_device (device_id, sort_order, id),
            CONSTRAINT fk_device_media_device FOREIGN KEY (device_id)
                REFERENCES devices (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='整机本身的图片/视频：整机外观、铭牌、开机测试这类拍的是「这台机器」
                   而不是某个部件的照片。与 device_part_media 同构（平铺一组，不分类），
                   列表页的封面也取这里的第一张'
        """,
    ),
    (
        "device_status_logs",
        """
        CREATE TABLE IF NOT EXISTS device_status_logs (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            device_id   INT UNSIGNED NOT NULL,
            from_status VARCHAR(24) NULL,
            to_status   VARCHAR(24) NOT NULL,
            note        VARCHAR(500) NULL,
            occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_device_status_logs_device (device_id, occurred_at),
            CONSTRAINT fk_device_status_logs_device FOREIGN KEY (device_id)
                REFERENCES devices (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='整机的状态流转history，与 card_status_logs 同构。整机详情页要和显卡详情页
                   显示同一条时间线，没有这张表就只剩一个当前状态，看不出它是什么时候到的'
        """,
    ),
    (
        "fx_rates",
        """
        CREATE TABLE IF NOT EXISTS fx_rates (
            rate_date  DATE NOT NULL,
            base       VARCHAR(3) NOT NULL,
            quote      VARCHAR(3) NOT NULL,
            rate       DECIMAL(18,8) NOT NULL COMMENT '100 JPY = ? CNY（口径见 fx.service.RATE_UNIT）',
            source     VARCHAR(32) NOT NULL DEFAULT 'ecb',
            fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (rate_date, base, quote, source)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='汇率本地缓存。历史牌价一经公布就不再变，缓存下来永久有效，
                   既省接口调用，也保证断网时历史数据照样算得出来'
        """,
    ),
    (
        "fund_injections",
        """
        CREATE TABLE IF NOT EXISTS fund_injections (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            inject_date DATE NOT NULL COMMENT '这笔钱进池的日期，也是 FIFO 的排序依据',
            amount      DECIMAL(16,2) NOT NULL COMMENT '注入的日元金额',
            currency    VARCHAR(3) NOT NULL DEFAULT 'JPY',
            -- 换汇当时的汇率快照：100 日元 = fx_rate 人民币。这笔钱之后被谁用掉，
            -- 都按这个汇率折人民币成本 —— 池子里的钱是「已经用这个价换进来的」，
            -- 用它的那天市场价是多少与真实成本无关。
            fx_rate     DECIMAL(18,8) NULL,
            fx_date     DATE NULL COMMENT '实际取到的牌价日（非交易日会回退）',
            fx_manual   TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1=汇率手工填写（真实换汇价），不自动覆盖',
            -- 换汇渠道。界面上已经不录了（渠道对算账没有任何影响），列留着不删：
            -- 老数据里还有值，而这个库的迁移规矩是只加不改。
            channel     VARCHAR(64) NULL COMMENT '换汇渠道，已停用，不再写入',
            note        VARCHAR(500) NULL,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_fund_injections_date (inject_date, id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='资金池注资批次。每次换汇进池一条，各自带自己那天的汇率'
        """,
    ),
    (
        "fund_draws",
        """
        CREATE TABLE IF NOT EXISTS fund_draws (
            id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
            -- 一笔扣款要么挂在一张卡上，要么挂在一台整机上，要么谁也不挂（手工记的
            -- 池内杂项支出）。两列互斥，永远最多只有一个非 NULL。
            card_id    INT UNSIGNED NULL COMMENT '归属卡片',
            device_id  INT UNSIGNED NULL COMMENT '归属整机设备',
            category   VARCHAR(24) NOT NULL DEFAULT 'purchase'
                           COMMENT 'purchase / intl_shipping 由卡片/整机自动同步；other 为手工记账',
            draw_date  DATE NOT NULL COMMENT '花钱的日期，决定它能吃到哪些批次（只能用已经进池的钱）',
            amount     DECIMAL(16,2) NOT NULL COMMENT '扣掉的日元金额',
            currency   VARCHAR(3) NOT NULL DEFAULT 'JPY',
            note       VARCHAR(500) NULL,
            -- 下面三列是 FIFO 分摊的结果，由 funds.rebuild() 回写：
            cny_amount DECIMAL(14,2) NULL COMMENT '折算后的人民币成本合计；NULL=有分段折不出来',
            shortfall  DECIMAL(16,2) NOT NULL DEFAULT 0 COMMENT '池子不够、没吃到注资的日元部分',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_fund_draws_date (draw_date, id),
            -- 一卡一类一条 / 一机一类一条。MySQL 的唯一键不约束含 NULL 的行，所以
            -- 手工支出（两列都为 NULL）以及另一种归属的行都不会被这两个键挡住。
            UNIQUE KEY uk_fund_draws_card_cat (card_id, category),
            UNIQUE KEY uk_fund_draws_device_cat (device_id, category),
            CONSTRAINT fk_fund_draws_card FOREIGN KEY (card_id)
                REFERENCES cards (id) ON DELETE CASCADE,
            CONSTRAINT fk_fund_draws_device FOREIGN KEY (device_id)
                REFERENCES devices (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='从资金池扣款。卡片/整机侧的两类跟着各自的金额自动同步，删除时级联清掉'
        """,
    ),
    (
        "fund_allocations",
        """
        CREATE TABLE IF NOT EXISTS fund_allocations (
            id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
            draw_id      INT UNSIGNED NOT NULL,
            injection_id INT UNSIGNED NOT NULL,
            seq          INT NOT NULL DEFAULT 0 COMMENT '同一笔扣款内的分段顺序',
            amount       DECIMAL(16,2) NOT NULL COMMENT '这一段从该批次吃掉的日元',
            fx_rate      DECIMAL(18,8) NULL COMMENT '该批次的汇率快照（冗余，便于直接展示）',
            cny_amount   DECIMAL(14,2) NULL COMMENT 'amount * fx_rate / 100；批次缺汇率时为 NULL',
            PRIMARY KEY (id),
            KEY idx_fund_alloc_draw (draw_id, seq),
            KEY idx_fund_alloc_injection (injection_id),
            CONSTRAINT fk_fund_alloc_draw FOREIGN KEY (draw_id)
                REFERENCES fund_draws (id) ON DELETE CASCADE,
            CONSTRAINT fk_fund_alloc_injection FOREIGN KEY (injection_id)
                REFERENCES fund_injections (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='一笔扣款按 FIFO 拆到各注资批次上的明细。全量派生数据，
                   任何注资/扣款变动后由 funds.rebuild() 整体重算'
        """,
    ),
]


# 后加的列写在这里：(表名, 列名, 完整的 ADD COLUMN 定义)
#
# CREATE TABLE IF NOT EXISTS 对已存在的表是空操作，所以当目标库里事先就有一张
# 同名旧表（比如上一版本建的、或别处留下的 users）时，新加的列不会自动补上，运行时会撞
# "Unknown column"。凡是后来才加进表定义的列，都必须在这里登记一条，让 _ensure_column
# 在启动时按需补齐。已存在的列会被跳过，重复执行安全。
_MIGRATIONS: List[Tuple[str, str, str]] = [
    ("users", "is_active", "is_active TINYINT(1) NOT NULL DEFAULT 1"),
    ("users", "is_admin", "is_admin TINYINT(1) NOT NULL DEFAULT 0"),
    ("users", "token_version", "token_version INT UNSIGNED NOT NULL DEFAULT 0"),
    ("users", "last_active_at", "last_active_at DATETIME NULL"),
    ("cards", "is_draft", "is_draft TINYINT(1) NOT NULL DEFAULT 0"),
    ("cards", "fund_source", "fund_source VARCHAR(8) NOT NULL DEFAULT 'own'"),
    ("cards", "pool_purchase_cny", "pool_purchase_cny DECIMAL(14,2) NULL"),
    ("cards", "pool_intl_cny", "pool_intl_cny DECIMAL(14,2) NULL"),
    ("cards", "pool_fx_rate", "pool_fx_rate DECIMAL(18,8) NULL"),
    ("cards", "pool_confirmed_at", "pool_confirmed_at DATETIME NULL"),
    ("devices", "fund_source", "fund_source VARCHAR(8) NOT NULL DEFAULT 'own'"),
    ("devices", "pool_purchase_cny", "pool_purchase_cny DECIMAL(14,2) NULL"),
    ("devices", "pool_intl_cny", "pool_intl_cny DECIMAL(14,2) NULL"),
    ("devices", "pool_fx_rate", "pool_fx_rate DECIMAL(18,8) NULL"),
    ("devices", "pool_confirmed_at", "pool_confirmed_at DATETIME NULL"),
    ("fund_draws", "device_id", "device_id INT UNSIGNED NULL"),
]


def _ensure_column(table: str, column: str, ddl: str) -> None:
    exists = db.query_scalar(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
        default=0,
    )
    if int(exists or 0) > 0:
        return
    log.info("迁移：为 %s 添加列 %s", table, column)
    db.execute("ALTER TABLE `{t}` ADD COLUMN {ddl}".format(t=table.replace("`", ""), ddl=ddl))


def _has_column(table: str, column: str) -> bool:
    return int(db.query_scalar(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column), default=0) or 0) > 0


def _has_index(table: str, index: str) -> bool:
    return int(db.query_scalar(
        "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s",
        (table, index), default=0) or 0) > 0


def _migrate_gpu_models_standalone() -> None:
    """把 gpu_models 从「依附品牌」迁成独立型号表：去掉 brand_id 及其相关索引，
    唯一键改到 name 上。CREATE TABLE IF NOT EXISTS 动不了已存在的旧表，只能在这里 ALTER。"""
    if not _has_column("gpu_models", "brand_id"):
        return  # 已是新结构，无需迁移
    log.info("迁移：gpu_models 解除与品牌的关联，改为独立型号表")
    # 先删掉引用 brand_id 的旧索引，之后才能删列
    if _has_index("gpu_models", "uk_gpu_models_brand_name"):
        db.execute("ALTER TABLE gpu_models DROP INDEX uk_gpu_models_brand_name")
    if _has_index("gpu_models", "idx_gpu_models_brand"):
        db.execute("ALTER TABLE gpu_models DROP INDEX idx_gpu_models_brand")
    # 旧结构允许跨品牌同名，去 brand 后同名会撞新唯一键：同名只保留 id 最小的一条
    db.execute("DELETE m1 FROM gpu_models m1 JOIN gpu_models m2 ON m1.name = m2.name AND m1.id > m2.id")
    db.execute("ALTER TABLE gpu_models DROP COLUMN brand_id")
    if not _has_index("gpu_models", "uk_gpu_models_name"):
        db.execute("ALTER TABLE gpu_models ADD UNIQUE KEY uk_gpu_models_name (name)")


def _migrate_fund_draws_devices() -> None:
    """给已存在的 fund_draws 补上整机归属所需的唯一键与外键。

    device_id 这一列由 _MIGRATIONS 补上，但唯一键和外键 ALTER 不了已建好的表
    （CREATE TABLE IF NOT EXISTS 对老表是空操作），只能在这里按需加。
    """
    if not _has_column("fund_draws", "device_id"):
        return  # 列还没补上（建表刚失败？），索引无从谈起
    if not _has_index("fund_draws", "uk_fund_draws_device_cat"):
        log.info("迁移：fund_draws 增加整机侧唯一键")
        db.execute("ALTER TABLE fund_draws ADD UNIQUE KEY uk_fund_draws_device_cat (device_id, category)")
    has_fk = int(db.query_scalar(
        "SELECT COUNT(*) AS c FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'fund_draws' "
        "AND CONSTRAINT_NAME = 'fk_fund_draws_device'", default=0) or 0)
    if not has_fk:
        log.info("迁移：fund_draws 增加指向 devices 的外键")
        db.execute(
            "ALTER TABLE fund_draws ADD CONSTRAINT fk_fund_draws_device "
            "FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE"
        )


# 汇率口径前后改过两次，每改一次都要把库里的存量汇率整体换算一遍：最早是
# 「1 人民币 = ? 日元」（23.76），中间是「1 日元 = ? 人民币」（0.0432），现在是
# 「100 日元 = ? 人民币」（4.32）。换算两遍等于没换，所以 app_settings 里记着这个库
# 当前是哪个口径，按标记决定要不要动、怎么动——全库唯一一处改存量数据的迁移。
_FX_DIRECTION_KEY = "fx_rate_direction"
_FX_DIRECTION = "cny_per_100jpy"

# 旧标记 → 把该口径的存量值换成当前口径的 SQL 表达式（{c} 是列名）。
# 被除数写成 100.000000000000 而不是 100：MySQL 除法结果的小数位 = 被除数小数位 +
# div_precision_increment（默认 4），拿整数去除只留 4 位小数，DECIMAL(18,8) 也补不回来。
_FX_DIRECTION_FIXUPS: Dict[Optional[str], str] = {
    None: "100.000000000000 / `{c}`",   # 「1 人民币 = ? 日元」：取倒数再换单位
    "jpy_cny": "`{c}` * 100",           # 「1 日元 = ? 人民币」：只差一个单位
}

# 所有存着汇率快照的列。派生出来的金额列（cny_amount / pool_*_cny）存的已经是人民币，
# 与口径无关，不用动。
_FX_RATE_COLUMNS: List[Tuple[str, str]] = [
    ("cards", "purchase_fx_rate"),
    ("cards", "sale_fx_rate"),
    ("cards", "pool_fx_rate"),
    ("devices", "purchase_fx_rate"),
    ("devices", "pool_fx_rate"),
    ("device_parts", "sale_fx_rate"),
    ("fund_injections", "fx_rate"),
    ("fund_allocations", "fx_rate"),
]


def _migrate_fx_rate_direction() -> None:
    """把存量汇率换算成当前口径（100 日元 = ? 人民币）。做过一次就跳过。

    整段必须在一个事务里，标记也由同一个游标写：中途失败却留下一半已换算的数据，
    下次启动会把那一半再换一次——那时已经没法从数值上分辨谁是新口径谁是旧口径了。
    """
    current = settings_store.get(_FX_DIRECTION_KEY)
    if current == _FX_DIRECTION:
        return
    if current not in _FX_DIRECTION_FIXUPS:
        # 标记是本版本不认识的口径。宁可不动数据也不要按错的算式换算一遍——
        # 换完就再也分不清原值是多少了。留个错误日志，等人工核对。
        log.error("app_settings.%s = %r 不认识，存量汇率未做换算", _FX_DIRECTION_KEY, current)
        return
    expr = _FX_DIRECTION_FIXUPS[current]
    log.info("迁移：汇率口径改为「100 日元 = ? 人民币」（原口径 %r）", current)
    with db.transaction() as cur:
        # 表名与列名都来自上面那张固定的表，不是外部输入，拼进 SQL 是安全的
        for table, column in _FX_RATE_COLUMNS:
            if not _has_column(table, column):
                continue
            cur.execute(
                "UPDATE `{t}` SET `{c}` = {e} WHERE `{c}` IS NOT NULL AND `{c}` > 0".format(
                    t=table, c=column, e=expr.format(c=column)
                )
            )
        if current is None:
            # 最早那版连缓存表的 base/quote 都是反的。那时留下的 JPY→CNY 行是另一套数值，
            # 换向后混在一起没法分辨，直接删——fx_rates 是纯缓存，删了下次自动重取。
            cur.execute("DELETE FROM fx_rates WHERE base = 'JPY' AND quote = 'CNY'")
            cur.execute(
                "UPDATE fx_rates SET base = 'JPY', quote = 'CNY', rate = {e} "
                "WHERE base = 'CNY' AND quote = 'JPY' AND rate > 0".format(e=expr.format(c="rate"))
            )
        else:
            cur.execute(
                "UPDATE fx_rates SET rate = {e} "
                "WHERE base = 'JPY' AND quote = 'CNY' AND rate > 0".format(e=expr.format(c="rate"))
            )
        # 与 settings_store.set 同一条语句，只是必须走本事务的游标
        cur.execute(
            "INSERT INTO app_settings (`key`, `value`) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)",
            (_FX_DIRECTION_KEY, _FX_DIRECTION),
        )


def _migrate_card_vram_to_core_no() -> None:
    """把 cards.vram 改名成 core_no：显卡不再记显存，改记核心上的丝印编号。

    用 CHANGE 而不是「加新列 + 留着旧列」，是因为这一栏换的是含义不是用途——留着一个
    永远为空的 vram 列，以后每次看表结构都要想一遍它还算不算数。
    """
    if not _has_column("cards", "vram") or _has_column("cards", "core_no"):
        return  # 已经改过，或本来就是新结构
    log.info("迁移：cards.vram 改名为 core_no（显存 → 核心编号）")
    db.execute(
        "ALTER TABLE cards CHANGE COLUMN vram core_no VARCHAR(32) NULL "
        "COMMENT 'GPU 核心上的丝印编号，用来证明核心没被换过'"
    )


def _migrate_platform_column_width() -> None:
    """把 cards / devices 的 source_platform 从 VARCHAR(16) 放宽到 32。

    原来只存 yahoo / mercari / other 三个 key，16 够用；改成字典表之后名字由用户自己起，
    16 个字符会把「Yahoo! Auction Japan」这种截断。加宽是无损的，跑多少遍都一样
    （已经 >= 32 就跳过），所以不用像换汇率口径那样记标记。
    """
    for table in ("cards", "devices"):
        width = db.query_scalar(
            "SELECT CHARACTER_MAXIMUM_LENGTH AS n FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'source_platform'",
            (table,),
            default=0,
        )
        if not width or int(width) >= 32:
            continue
        log.info("迁移：%s.source_platform 放宽到 VARCHAR(32)", table)
        # 表名来自上面这个固定的元组，不是外部输入
        db.execute(
            "ALTER TABLE `{t}` MODIFY COLUMN source_platform VARCHAR(32) NULL "
            "COMMENT 'source_platforms 字典里的 name'".format(t=table)
        )


# pool_confirmed_at 是后加的闸门列：在它之前，只要 fund_source='pool' 池子就已经扣了钱。
# 补上这列后那些行会变成「未确认」，下一次保存就把扣款删掉——池内余额凭空涨回来，
# 成本也从注资汇率退回市场牌价。所以建完列要把存量的 pool 行一次性标成已确认。
# 这是改存量数据的迁移，跑第二遍会把用户后来主动撤销的行又标回已确认，
# 所以照 _migrate_fx_rate_direction 的办法在 app_settings 里记一个做过的标记。
_POOL_CONFIRM_KEY = "pool_confirm_backfilled"


def _migrate_backfill_pool_confirmed() -> None:
    """把补列之前就在走资金池的卡片 / 整机标成「已确认扣除」。做过一次就跳过。

    时间取 purchase_date（那天的钱就该那天出池），没有购入日的退回 created_at——
    确认时间只用于展示与「有没有确认过」，FIFO 分摊吃的是 fund_draws.draw_date。
    """
    if settings_store.get(_POOL_CONFIRM_KEY):
        return
    for table in ("cards", "devices"):
        if not _has_column(table, "pool_confirmed_at"):
            return  # 列还没补上，等下次启动
    log.info("迁移：把存量的资金池卡片 / 整机标为已确认扣除")
    with db.transaction() as cur:
        # 表名来自上面这个固定的元组，不是外部输入
        for table in ("cards", "devices"):
            cur.execute(
                "UPDATE `{t}` SET pool_confirmed_at = COALESCE(purchase_date, created_at, NOW()) "
                "WHERE fund_source = 'pool' AND pool_confirmed_at IS NULL".format(t=table)
            )
        # 与 settings_store.set 同一条语句，只是必须走本事务的游标
        cur.execute(
            "INSERT INTO app_settings (`key`, `value`) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)",
            (_POOL_CONFIRM_KEY, "1"),
        )


def init() -> None:
    """建库 → 建表 → 补列 → 结构迁移 → 数据迁移 → 灌入首次运行的种子数据。可重复执行。"""
    db.ensure_database()
    for name, ddl in _TABLES:
        db.execute(ddl)
        log.debug("表就绪：%s", name)
    for table, column, ddl in _MIGRATIONS:
        _ensure_column(table, column, ddl)
    _migrate_gpu_models_standalone()
    _migrate_fund_draws_devices()
    _migrate_card_vram_to_core_no()
    _migrate_platform_column_width()
    _migrate_fx_rate_direction()
    _migrate_backfill_pool_confirmed()
    _cleanup_stale_drafts()
    _seed()


def _cleanup_stale_drafts() -> None:
    """清掉超过 2 小时没定稿的草稿（卡片与整机都算）。

    正常流程里草稿要么存下改动（转正）、要么离开详情页时被删；只有「点了新增又直接关掉浏览器」
    才会残留。2 小时的阈值保证正在编辑中的草稿（刚建几秒）不会被误删，即使期间热重载了。
    连带 card_media / device_parts 由外键级联删除；图床上的文件成孤儿（可接受，仅占空间）。
    """
    try:
        removed_devices = db.execute(
            "DELETE FROM devices WHERE is_draft = 1 AND created_at < (NOW() - INTERVAL 2 HOUR)"
        )
        if removed_devices:
            log.info("清理了 %d 台过期草稿设备", removed_devices)
        removed_cards = db.execute(
            "DELETE FROM cards WHERE is_draft = 1 AND created_at < (NOW() - INTERVAL 2 HOUR)"
        )
        if removed_cards:
            log.info("清理了 %d 张过期草稿卡", removed_cards)
        if removed_cards or removed_devices:
            # 草稿上若开过「从资金池扣除」，它的扣款刚被外键连带删掉了：重算一次，
            # 把那笔钱还给池子，后面的扣款也才吃得到。在函数里 import 是为了避开
            # funds → schema 的循环依赖。
            from src import funds

            funds.rebuild()
    except Exception as exc:  # noqa: BLE001  清理失败不该拖垮启动
        log.warning("清理草稿失败：%s", exc)


def _seed() -> None:
    """首次运行的种子数据：默认管理员 + 购买平台字典。品牌与型号一律由用户手动添加，不预置。"""
    from src.security import hash_password

    # 平台和品牌不一样，必须预置：库里已有的卡片存的就是 yahoo / mercari / other，
    # 字典空着的话那些行在下拉里选不中，看着像数据丢了。只在表为空时灌一次，
    # 用户后来删掉哪个都不会被重新塞回来。
    if not db.query_scalar("SELECT COUNT(*) AS c FROM source_platforms", default=0):
        db.execute(
            "INSERT INTO source_platforms (name, sort_order) VALUES " +
            ", ".join(["(%s, %s)"] * len(SOURCE_PLATFORM_SEEDS)),
            [x for i, name in enumerate(SOURCE_PLATFORM_SEEDS) for x in (name, i)],
        )
        log.info("已灌入默认购买平台：%s", " / ".join(SOURCE_PLATFORM_SEEDS))

    # 按用户名判断而不是 COUNT==0：库里若已有一张旧的 users 表（有其他行、但没有 admin），
    # 用 COUNT 判断会以为「已初始化」而跳过，导致没有可登录的账号。
    admin = db.query_one("SELECT id, is_admin FROM users WHERE username = %s", ("admin",))
    if not admin:
        db.insert(
            "INSERT INTO users (username, password_hash, is_active, is_admin) VALUES (%s, %s, 1, 1)",
            ("admin", hash_password("admin")),
        )
        log.warning("已创建默认管理员 admin / admin —— 请登录后立即在「系统配置」中改密码")
    elif not admin["is_admin"]:
        # 旧表迁移后 is_admin 默认补成了 0：把内置的 admin 账号提回管理员，
        # 否则它进不了「系统配置」里的数据库/账号等管理员专属页面。
        db.execute("UPDATE users SET is_admin = 1 WHERE id = %s", (admin["id"],))
        log.info("已将已存在的 admin 账号提升为管理员")
