# -*- coding: utf-8 -*-
"""库存合并列表：显卡与整机设备放在同一张表里，用 ``kind`` 区分。

**为什么要有这个模块**：两种货的数据结构差得远——显卡是一进一出（买价卖价在同一行），
整机是一进多出（一笔总价，拆件分售，出售价在 device_parts 上）。硬塞进一张表会让两边
都别扭。但**看库存的人不关心这个**：他要的是「我手上一共有什么、花了多少、回来多少」，
按类型分成两个页面等于每次都要看两遍再自己加一次。

所以底层仍是 cards / devices 两套表与两套 CRUD，只在这里把它们**规范化成同一种行**
（编号、名称、状态、日期、成本、收入、盈亏），再统一筛选、排序、分页。

**为什么在 Python 里筛选、排序、分页而不是 SQL**：两张表结构不同，UNION 要先把列一一对齐，
而成本 / 利润根本不是列——它们是按汇率快照算出来的（见 cards.compute_money）。想在
SQL 里按利润排序就得把整套换算逻辑再用 SQL 写一遍，两份实现迟早对不上。这个系统的
量级是几百行，全取回来在内存里排完再切页，快得多也稳得多。筛选也因此全在内存里：
下拉选项是联动的（facets），要按几十种条件组合各数一遍，落在 SQL 里就是几十次查库。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src import cards, db, devices, funds
from src.auth import require_auth
from src.schema import CARD_STATUSES, DEVICE_PART_TYPES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"], dependencies=[Depends(require_auth)])

# 列表行的类型。card / device 是顶层行，part 是整机展开后的二级行——它们共用同一套
# 列，所以在这里就规范化成同一种形状，前端不必为二级行另写一张表。
KIND_CARD = "card"
KIND_DEVICE = "device"
KIND_PART = "part"

# 允许的排序列。全部是**规范化之后**的字段名，两种类型共用同一套。
_SORT_KEYS = {
    "created_at", "updated_at", "purchase_date", "sale_date",
    "mgmt_no", "title", "status", "owner", "cost_total_cny", "sale_cny", "profit_cny",
}


# ── 规范化：两种货 → 同一种行 ───────────────────────────────────────────── #

def _card_item(row: Dict[str, Any], media: List[Dict[str, Any]],
               contributors: List[Optional[str]]) -> Dict[str, Any]:
    data = cards.serialize(row, media)
    money = data["money"]
    return {
        # 行标识。卡片与整机的 id 各自从 1 开始，二级行还要和它们混在一张表里，
        # 不带类型前缀会撞。el-table 的 row-key / 树形展开都靠它。
        "row_key": f"{KIND_CARD}-{row['id']}",
        "kind": KIND_CARD,
        "id": row["id"],
        "mgmt_no": row["mgmt_no"],
        "title": " ".join(x for x in (row.get("brand"), row.get("model")) if x) or None,
        "subtitle": row.get("core_no"),
        "status": row["status"],
        "source_platform": row.get("source_platform"),
        "purchase_date": data["purchase_date"],
        "sale_date": data["sale_date"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        # 显卡没有「部件」概念：一张卡就是一件，卖了就是 1/1
        "part_count": 1,
        "sold_count": 1 if row.get("sale_amount") is not None else 0,
        "sold": row["status"] in cards.SOLD_STATUSES or row.get("sale_amount") is not None,
        # 一张卡卖掉就没有后续了，所以「卖了 = 已结清」
        "settled": row.get("sale_amount") is not None,
        "cost_total_cny": money["cost_total_cny"],
        # 同一笔成本的日元口径。货是在日本买的，对着日站的成交价复核时看日元才顺手
        "cost_total_jpy": money["cost_total_jpy"],
        # 成本的三项拆开一起给：列表页要在「总成本」上悬浮出「购入 + 国际运费 + 国内运费」
        # 的明细。合计里本来就含着这两笔运费，但不摊开的话没人看得出利润是净的。
        "purchase_cny": money["purchase_cny"],
        "intl_shipping_cny": money["intl_shipping_cny"],
        "domestic_shipping_cny": money["domestic_shipping_cny"],
        "sale_cny": money["sale_cny"],
        "profit_cny": money["profit_cny"],
        "incomplete": money["incomplete"],
        # 成本按资金池算的（有归属人）。列表在金额后面标「扣款实际吃到了谁的钱」
        # （见 funds.load_draw_contributors），欠着还没补上的那部分不在其中
        "from_pool": money["from_pool"],
        "pool_contributors": contributors if money["from_pool"] else [],
        "owner": row.get("owner"),
        # 按归属人筛选看的是这一份（整机要把部件的也算上，见 _device_item）
        "owners": [row["owner"]] if row.get("owner") else [],
        "media": data["media"],
    }


def _part_row(part: Dict[str, Any], device_id: int, device_owner: Optional[str]) -> Dict[str, Any]:
    """把一个部件规范化成**和顶层行同样的形状**，作为整机的二级行。

    不适用的列一律给 None，前端统一显示成「—」：部件没有购入日（整机是一口价买的），
    也没有单件成本——总价不往部件上摊（理由见 src.devices 的模块文档），所以「总成本」
    和「利润」这两列在部件行上是空的，只有出售侧的数字。
    """
    money = part["money"]
    title = " ".join(x for x in (part.get("brand"), part.get("model"), part.get("spec")) if x)
    # 部件没单独指定归属人就是整机的
    owner = part.get("owner") or device_owner
    return {
        "row_key": f"{KIND_PART}-{part['id']}",
        "kind": KIND_PART,
        "id": part["id"],
        # 点二级行时要能打开它所属的那台设备
        "device_id": device_id,
        "part_type": part["part_type"],
        "quantity": part["quantity"],
        "mgmt_no": None,
        "title": title or None,
        "subtitle": None,
        "status": part["status"],
        "source_platform": None,
        "purchase_date": None,
        "sale_date": part["sale_date"],
        "created_at": part["created_at"],
        "updated_at": part["updated_at"],
        "part_count": None,
        "sold_count": None,
        "sold": money["sold"],
        "settled": money["sold"],
        "cost_total_cny": None,
        "cost_total_jpy": None,
        "purchase_cny": None,
        "intl_shipping_cny": None,
        "sale_cny": money["sale_cny"],
        "domestic_shipping_cny": money["domestic_shipping_cny"],
        "profit_cny": None,
        "incomplete": money["incomplete"],
        # 部件不单独出钱：整机是一口价买的，资金来源在整机那一行上
        "from_pool": False,
        "pool_contributors": [],
        "owner": owner,
        # 归属人是部件自己填的，而不是跟随整机——列表上据此区分显示
        "owner_own": bool(part.get("owner")),
        "owners": [owner] if owner else [],
        "media": [],
    }


def _device_item(row: Dict[str, Any], parts: List[Dict[str, Any]],
                 media: List[Dict[str, Any]], contributors: List[Optional[str]]) -> Dict[str, Any]:
    data = devices.serialize(row, parts)
    money = data["money"]
    # 整机没有单一的「出售日期」——部件是分批卖的，这里取最后成交的那天。
    # **列表的顶层行不显示它**（逐件的出售日期在展开的二级行上，那才是实情），
    # 这个值留着是给按出售日期排序用的：整机得有个可比的位置，不然排序时全落到末尾。
    sale_dates = [p["sale_date"] for p in data["parts"] if p["sale_date"]]
    children = [_part_row(p, row["id"], row.get("owner")) for p in data["parts"]]
    # 一台机器牵涉到的归属人：整机自己的，加上单独归别人的部件。按「单」筛选时，
    # 一台甘的整机里装着单的那块卡，这台机器也该出现
    owners: List[str] = []
    for name in [row.get("owner")] + [c["owner"] for c in children]:
        if name and name not in owners:
            owners.append(name)
    item = {
        "row_key": f"{KIND_DEVICE}-{row['id']}",
        "kind": KIND_DEVICE,
        "id": row["id"],
        "mgmt_no": row["mgmt_no"],
        "title": row.get("title"),
        "subtitle": None,
        "status": row["status"],
        "source_platform": row.get("source_platform"),
        "purchase_date": data["purchase_date"],
        "sale_date": max(sale_dates) if sale_dates else None,
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "part_count": money["part_count"],
        "sold_count": money["sold_count"],
        "sold": money["sold_count"] > 0,
        "settled": money["settled"],
        "cost_total_cny": money["cost_total_cny"],
        "cost_total_jpy": money["cost_total_jpy"],
        # 与显卡同一套明细。整机的国内运费是**各部件的合计**（部件分别发货，各按自己的
        # 出售汇率折算），已经计入 cost_total_cny，这里只是把它单独摆出来。
        "purchase_cny": money["purchase_cny"],
        "intl_shipping_cny": money["intl_shipping_cny"],
        "domestic_shipping_cny": money["domestic_shipping_cny"],
        "sale_cny": money["sale_cny"],
        "profit_cny": money["profit_cny"],
        "incomplete": money["incomplete"],
        "from_pool": money["from_pool"],
        "pool_contributors": contributors if money["from_pool"] else [],
        "owner": row.get("owner"),
        "owners": owners,
        # 整机自己的图（外观 / 铭牌…），列表里取第一张当封面，与显卡同一套
        "media": media,
    }
    # 二级行。没有部件时**不带 children 这个键**——给个空数组的话 el-table 仍会画出
    # 一个点开是空的展开箭头。
    if children:
        item["children"] = children
    return item


def _solo_part(part_item: Dict[str, Any], device_item: Dict[str, Any],
               media: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """把整机里的一个部件**单独列成一行**（按状态筛选时，整机本身没命中、部件命中）。

    为什么不干脆出整机那一行：筛「已回国」的人要的是「现在手上有哪几件回国了」，
    整机里已回国的是那块显卡，把整台机器（连同还在日本的其他部件）列出来等于答非所问。
    所以这一行只是部件本身，另带 ``parent`` 让前端能标出来自哪台、点开时进那台整机。

    购入日、池内扣除这几样部件自己没有，取整机的——它们本来就是整机这一笔买卖上的
    事实，部件跟着整机；不继承的话「按池内扣除筛」「按购入日排序」会把单列的部件
    全部漏掉或垫底。归属人部件自己有（没填时已经回退成整机的，见 _part_row）。成本 / 利润照旧空着（总价不往部件上摊）。
    """
    return {
        **part_item,
        "solo": True,
        "parent": {
            "id": device_item["id"],
            "mgmt_no": device_item["mgmt_no"],
            "title": device_item["title"],
        },
        "purchase_date": device_item["purchase_date"],
        "source_platform": device_item["source_platform"],
        "from_pool": device_item["from_pool"],
        # 部件的图由 _attach_part_media 只给当前页补
        "media": media or [],
    }


# ── 筛选 ────────────────────────────────────────────────────────────────── #

def _statuses(status: Optional[str]) -> List[str]:
    if not status:
        return []
    return [s.strip() for s in status.split(",") if s.strip() in CARD_STATUSES]


# ── 全量取数 ────────────────────────────────────────────────────────────── #

def _load_universe() -> Dict[str, List[tuple]]:
    """一次取回全部非草稿的显卡与整机，规范化好，连同原始行一起留着给筛选用。

    **为什么不再在 SQL 里筛**：筛选是联动的（见 facets()）——每个下拉的选项都要按
    「其余条件全部生效、只放开它自己」算一遍还剩几件，一个页面就是几十种组合。条件
    落在 SQL 里的话每种组合都得重新查一次库；全量取回来之后只是在内存里多过几遍，
    几百行的量级一遍不到一毫秒。顺带的好处是列表、统计、下拉选项三者走的是同一个
    _select()，口径不可能各算各的。
    """
    card_rows = db.query("SELECT * FROM cards WHERE is_draft = 0")
    cids = [r["id"] for r in card_rows]
    media_map = cards.load_media(cids)
    contrib_map = funds.load_draw_contributors("card", cids)
    card_list = [
        (_card_item(r, media_map.get(r["id"], []), contrib_map.get(r["id"], [])), r)
        for r in card_rows
    ]

    dev_rows = db.query("SELECT * FROM devices WHERE is_draft = 0")
    dids = [r["id"] for r in dev_rows]
    parts_map = devices.load_parts(dids)
    dmedia_map = devices.load_media(dids)
    dcontrib_map = funds.load_draw_contributors("device", dids)
    device_list = []
    for r in dev_rows:
        parts = parts_map.get(r["id"], [])
        item = _device_item(r, parts, dmedia_map.get(r["id"], []), dcontrib_map.get(r["id"], []))
        device_list.append((item, r, {p["id"]: p for p in parts}))
    return {"cards": card_list, "devices": device_list}


# ── 逐行判断 ────────────────────────────────────────────────────────────── #

def _kw_hit(keyword: Optional[str], values: List[Any]) -> bool:
    kw = (keyword or "").strip().lower()
    return not kw or any(kw in str(v).lower() for v in values if v)


def _in_purchase_range(row: Dict[str, Any], f: Dict[str, Any]) -> bool:
    d = row.get("purchase_date")
    if f["purchase_from"] and (d is None or d < f["purchase_from"]):
        return False
    if f["purchase_to"] and (d is None or d > f["purchase_to"]):
        return False
    return True


_CARD_KW_FIELDS = ("mgmt_no", "brand", "model", "serial_no", "seller", "order_no")
_PART_KW_FIELDS = ("brand", "model", "spec", "serial_no")
_DEVICE_KW_FIELDS = ("mgmt_no", "title", "seller", "order_no")


def _card_ok(row: Dict[str, Any], f: Dict[str, Any], statuses: List[str]) -> bool:
    if not _kw_hit(f["keyword"], [row.get(k) for k in _CARD_KW_FIELDS]):
        return False
    if statuses and row["status"] not in statuses:
        return False
    if f["brand"] and (row.get("brand") or "") != f["brand"]:
        return False
    if f["model"] and (row.get("model") or "") != f["model"]:
        return False
    if f["source_platform"] and row.get("source_platform") != f["source_platform"]:
        return False
    return _in_purchase_range(row, f)


def _device_ok(row: Dict[str, Any], parts: Dict[int, Dict[str, Any]], f: Dict[str, Any]) -> bool:
    """整机这一级的条件：平台、购入日期、关键词。

    关键词也要能命中部件：找一台机器往往是从「哪台里有那块 4090」反推的。
    """
    if f["source_platform"] and row.get("source_platform") != f["source_platform"]:
        return False
    if not _in_purchase_range(row, f):
        return False
    values = [row.get(k) for k in _DEVICE_KW_FIELDS]
    values += [p.get(k) for p in parts.values() for k in _PART_KW_FIELDS]
    return _kw_hit(f["keyword"], values)


def _part_ok(part: Dict[str, Any], device: Dict[str, Any], f: Dict[str, Any],
             statuses: List[str], part_type: Optional[str]) -> bool:
    """一个部件自己是否满足筛选（类型、状态、品牌、型号、关键词）。

    这些条件必须落在**同一个**部件上：「已回国的内存」不能被「有内存、另有个已回国的
    显卡」冒充。关键词既可以对上部件本身，也可以对上它所属整机的编号 / 名称——
    「DEV-2026-0009 里的内存」这种找法很常见。
    """
    if part_type and part.get("part_type") != part_type:
        return False
    if statuses and part.get("status") not in statuses:
        return False
    if f["brand"] and (part.get("brand") or "") != f["brand"]:
        return False
    if f["model"] and (part.get("model") or "") != f["model"]:
        return False
    values = [part.get(k) for k in _PART_KW_FIELDS] + [device.get(k) for k in _DEVICE_KW_FIELDS]
    return _kw_hit(f["keyword"], values)


# 归属人筛选里「未指定」的取值。用一个不可能是人名的记号，而不是空串——
# 空串在查询串里会被当成「没传」。
OWNER_NONE = "__none__"

_STOCK_STATES = {"in_stock", "settled"}
_PROFIT_STATES = {"gain", "loss", "incomplete"}
_POOL_STATES = {"drawn", "undrawn"}


def _inventory_filters(
    kind: Optional[str] = Query(default=None, description="card / device / part，留空为全部"),
    part_type: Optional[str] = Query(default=None, description="kind=part 时限定部件类型"),
    keyword: Optional[str] = Query(default=None, description="编号/型号/序列号/卖家/部件 模糊匹配"),
    status: Optional[str] = Query(default=None, description="逗号分隔的多个状态"),
    brand: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None, description="显卡单品或整机部件的型号，精确匹配"),
    source_platform: Optional[str] = Query(default=None),
    purchase_from: Optional[dt.date] = Query(default=None),
    purchase_to: Optional[dt.date] = Query(default=None),
    owner: Optional[str] = Query(default=None, description=f"逗号分隔的归属人，{OWNER_NONE} 表示未指定"),
    sale_from: Optional[dt.date] = Query(default=None),
    sale_to: Optional[dt.date] = Query(default=None),
    stock: Optional[str] = Query(default=None, description="in_stock / settled"),
    profit: Optional[str] = Query(default=None, description="gain / loss / incomplete"),
    pool: Optional[str] = Query(default=None, description="drawn / undrawn"),
    cost_min: Optional[float] = Query(default=None, description="总成本下限（人民币）"),
    cost_max: Optional[float] = Query(default=None, description="总成本上限（人民币）"),
) -> Dict[str, Any]:
    """列表与统计共用的筛选参数。写成依赖而不是在两个路由上各抄一遍签名：
    十几个参数抄两份，迟早有一个只加进了列表、没加进统计，顶部的合计就和下面的表对不上。
    """
    return dict(
        kind=kind,
        part_type=part_type if kind == KIND_PART and part_type in DEVICE_PART_TYPES else None,
        keyword=keyword, status=status,
        brand=(brand or "").strip() or None,
        model=(model or "").strip() or None,
        source_platform=(source_platform or "").strip() or None,
        purchase_from=purchase_from, purchase_to=purchase_to,
        owners=[c.strip() for c in (owner or "").split(",") if c.strip()],
        sale_from=sale_from, sale_to=sale_to,
        stock=stock if stock in _STOCK_STATES else None,
        profit=profit if profit in _PROFIT_STATES else None,
        pool=pool if pool in _POOL_STATES else None,
        cost_min=cost_min, cost_max=cost_max,
    )


def _sold_in_range(item: Dict[str, Any], start: Optional[dt.date], end: Optional[dt.date]) -> bool:
    """出售日期是否落在区间里。

    整机按**任一部件**在区间里成交来算，而不是看顶层那个「最后成交日」：筛「九月卖了
    什么」时，一台九月出了显卡、十月才出完 CPU 的机器应该在里面，按最后成交日就漏了。
    """
    if item["kind"] == KIND_DEVICE:
        dates = [c["sale_date"] for c in item.get("children", []) if c.get("sale_date")]
    else:
        dates = [item["sale_date"]] if item.get("sale_date") else []
    lo = start.isoformat() if start else None
    hi = end.isoformat() if end else None
    # 日期在规范化行里已经是 ISO 字符串，同格式的字符串比较就是日期比较
    return any((lo is None or d >= lo) and (hi is None or d <= hi) for d in dates)


def _match_derived(item: Dict[str, Any], f: Dict[str, Any]) -> bool:
    """按**算出来的**字段筛：归属人、结清、盈亏、池内扣除、成本。

    这些都不是数据库列（成本 / 利润按汇率快照现算，归属人要把整机的部件合起来看），所以和排序
    一样放在规范化之后、在内存里做，口径与列表上显示的那个数天然一致。
    """
    if f["owners"]:
        # 命中任一人即可，「未指定」= 这件货上一个归属人都没有
        names = item["owners"]
        want_none = OWNER_NONE in f["owners"]
        if not (any(n in names for n in f["owners"]) or (want_none and not names)):
            return False
    if (f["sale_from"] or f["sale_to"]) and not _sold_in_range(item, f["sale_from"], f["sale_to"]):
        return False
    if f["stock"] == "settled" and not item["settled"]:
        return False
    if f["stock"] == "in_stock" and item["settled"]:
        return False
    if f["profit"]:
        # 缺汇率的行利润是 None，它既不算赚也不算亏，只归「缺汇率」这一档——
        # 当 0 处理会让它混进某一边，筛出来的「亏损」里就夹着几件其实只是没算出来的货。
        value = item["profit_cny"]
        if f["profit"] == "incomplete":
            if not item["incomplete"]:
                return False
        elif item["incomplete"] or value is None:
            return False
        elif f["profit"] == "gain" and not value > 0:
            return False
        elif f["profit"] == "loss" and not value < 0:
            return False
    if f["pool"] == "drawn" and not item["from_pool"]:
        return False
    if f["pool"] == "undrawn" and item["from_pool"]:
        return False
    if f["cost_min"] is not None or f["cost_max"] is not None:
        # 成本算不出来的行在成本区间里无从判断，宁可不出现，也不当 0 落进「低成本」那头
        cost = item["cost_total_cny"]
        if cost is None:
            return False
        if f["cost_min"] is not None and cost < f["cost_min"]:
            return False
        if f["cost_max"] is not None and cost > f["cost_max"]:
            return False
    return True


def _select(universe: Dict[str, List[tuple]], f: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按筛选条件从全量里挑出列表行。列表、统计、下拉选项（facets）都只走这一个函数。

    整机的三种出法：

    - **部件模式**（类型选了「部件 / 某种部件」，或者按型号筛而类型没限定）：整机不出现，
      只把满足条件的部件逐个单列（_solo_part）。整机本身没有型号，按型号命中的只能是
      里面那个部件——「RTX 4090」筛出来的是 4090 单卡加整机里拆出来的那块 4090。
    - **按状态筛**：整机自己的状态命中就出整机那一行；没命中而部件命中，就只列那个部件
      （类型选了「整机」时不列部件——那是明说了只要整机）。
    - 其余：整机整台列出，品牌 / 型号按「里面有这样的部件」匹配。
    """
    status = f["status"]
    statuses = _statuses(status)
    # 指定了状态却一个合法值都没有：说明筛的是不存在的状态，直接返回空，
    # 而不是把条件丢掉当「不筛」——那会让人以为筛选没生效。
    if status and not statuses:
        return []
    kind = f["kind"]
    out: List[Dict[str, Any]] = []

    if kind in (None, KIND_CARD):
        out.extend(item for item, row in universe["cards"] if _card_ok(row, f, statuses))

    if kind != KIND_CARD:
        parts_only = kind == KIND_PART or (kind is None and bool(f["model"]))
        part_type = f["part_type"] if kind == KIND_PART else None
        for item, row, parts in universe["devices"]:
            if not _device_ok(row, parts, f):
                continue
            children = item.get("children", [])
            if parts_only:
                out.extend(_solo_part(c, item) for c in children
                           if _part_ok(parts[c["id"]], row, f, statuses, part_type))
                continue
            dev_ok = all(
                not f[key] or any((p.get(key) or "") == f[key] for p in parts.values())
                for key in ("brand", "model")
            )
            if dev_ok and (not statuses or item["status"] in statuses):
                out.append(item)
            elif statuses and kind is None:
                out.extend(_solo_part(c, item) for c in children
                           if _part_ok(parts[c["id"]], row, f, statuses, None))

    return [i for i in out if _match_derived(i, f)]


def _collect(f: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _select(_load_universe(), f)


def _attach_part_media(items: List[Dict[str, Any]]) -> None:
    """给单列的部件行补上部件自己的图。只对**当前页**做：全量筛选时每一行都去取图，
    一页 20 行却要把几十个部件的图全查一遍。"""
    solo = [i for i in items if i.get("solo")]
    media = devices.load_part_media([i["id"] for i in solo])
    for i in solo:
        i["media"] = media.get(i["id"], [])


# ── 联动的下拉选项 ──────────────────────────────────────────────────────── #

def _facet_candidates(universe: Dict[str, List[tuple]]) -> Dict[str, List[tuple]]:
    """每个下拉可能出现的取值，以及选它时要改写的筛选项。值是 (取值, 覆盖项)。"""
    def distinct(values) -> List[str]:
        return sorted({v for v in values if v})

    card_rows = [row for _, row in universe["cards"]]
    device_rows = [row for _, row, _ in universe["devices"]]
    all_parts = [p for _, _, parts in universe["devices"] for p in parts.values()]
    owners = distinct(
        n for entry in universe["cards"] + universe["devices"] for n in entry[0]["owners"])

    kinds = [(k, {"kind": k, "part_type": None}) for k in (KIND_CARD, KIND_DEVICE, KIND_PART)]
    kinds += [(f"{KIND_PART}:{t}", {"kind": KIND_PART, "part_type": t}) for t in DEVICE_PART_TYPES]
    return {
        "kind": kinds,
        "status": [(v, {"status": v}) for v in CARD_STATUSES],
        "brand": [(v, {"brand": v}) for v in distinct(
            [r.get("brand") for r in card_rows] + [p.get("brand") for p in all_parts])],
        "model": [(v, {"model": v}) for v in distinct(
            [r.get("model") for r in card_rows] + [p.get("model") for p in all_parts])],
        "source_platform": [(v, {"source_platform": v}) for v in distinct(
            r.get("source_platform") for r in card_rows + device_rows)],
        "owner": [(v, {"owners": [v]}) for v in owners + [OWNER_NONE]],
        "stock": [(v, {"stock": v}) for v in sorted(_STOCK_STATES)],
        "profit": [(v, {"profit": v}) for v in ("gain", "loss", "incomplete")],
        "pool": [(v, {"pool": v}) for v in ("drawn", "undrawn")],
    }


def facets(universe: Dict[str, List[tuple]], f: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """各下拉的联动选项：**其余筛选全部生效**时，选这个值能筛出几件。

    件数为 0 的取值不给——选了显卡，品牌 / 型号里就只剩显卡上出现过的那些。当前已选的
    值即使变成 0 也由前端保留着显示，否则下拉框里会冒出一个裸的取值。

    每个取值都是真的跑一遍 _select 数出来的，而不是从某个结果集里分组统计：部件单列、
    按状态拆整机这些规则让「选了它之后会出现哪些行」没法从别的结果里推出来，
    推算的数字迟早和点下去之后的条数对不上。
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key, options in _facet_candidates(universe).items():
        counted = ((value, len(_select(universe, {**f, **override}))) for value, override in options)
        out[key] = [{"value": v, "count": n} for v, n in counted if n]
    # 品牌 / 型号 / 平台这类自由文本按件数从多到少排，常用的在上面
    for key in ("brand", "model", "source_platform"):
        out[key].sort(key=lambda x: (-x["count"], x["value"]))
    return out


def _sort(items: List[Dict[str, Any]], sort_by: str, sort_dir: str) -> List[Dict[str, Any]]:
    """按规范化后的字段排序。

    缺失值（没卖出去所以没有出售日、缺汇率所以没有利润）一律排在最后，无论升序降序：
    把 NULL 当 0 排会让「算不出来的」混进「利润最低的」里，那是会看错的排序。
    """
    key = sort_by if sort_by in _SORT_KEYS else "purchase_date"
    reverse = str(sort_dir).lower() != "asc"

    def keyed(field: str):
        def sort_key(item: Dict[str, Any]):
            value = item.get(field)
            missing = value is None
            # 元组第一位专管「缺失值垫底」，并跟着 reverse 取反：升序时缺失取 True（排最大），
            # 降序时取 False（排最小、翻转后到末尾），两个方向下都落在最后。
            # 第二位只在第一位相同时才参与比较，也就是只在「都缺失」或「都不缺失」之间比，
            # 因此 0 与字符串永远不会撞上（每个排序列自己的类型是固定的）。
            return (missing != reverse, 0 if missing else value)
        return sort_key

    # 购入日期只精确到天，同一天买的好几件得有个确定的先后，否则翻页时会忽前忽后。
    # 先按录入时间排一遍，再按主键排——sorted 是稳定的，主键相同的就保留录入时间的顺序。
    items = sorted(items, key=keyed("created_at"), reverse=reverse)
    return sorted(items, key=keyed(key), reverse=reverse)


@router.get("/facets")
def list_facets(f: Dict[str, Any] = Depends(_inventory_filters)):
    """筛选下拉的联动选项，参数与列表完全相同（见 facets）。"""
    return facets(_load_universe(), f)


@router.get("/stats")
def stats(f: Dict[str, Any] = Depends(_inventory_filters)):
    """顶部统计：对**当前筛选下的全部库存**（不只当前页）汇总，显卡与整机合在一起。

    金额一律用各自领域模块算好的结果，缺汇率的项不当 0 计入（见 compute_money）。
    """
    items = _collect(f)

    # 缺汇率的行（incomplete）三项合计里一个都不参与。逐项跳过 None 的话，一行的收入
    # 会在它的成本被丢掉的情况下照样计入合计，「总利润」就凭空多出这一整笔成本——
    # 宁可整行不算，也不能算出一个偏高的净利润。行数在 incomplete 里另外报。
    # 单列出来的部件（见 _solo_part）只算件数、不进金额：它没有单件成本，售价却有，
    # 混进来的话「总收入」多出一截而「总成本」没变，总利润凭空变高。
    countable = [i for i in items if not i["incomplete"] and i["kind"] != KIND_PART]

    def _sum(key: str, digits: int = 2) -> float:
        return round(sum(i[key] for i in countable if i[key] is not None), digits)

    card_count = sum(1 for i in items if i["kind"] == KIND_CARD)
    device_count = sum(1 for i in items if i["kind"] == KIND_DEVICE)
    settled = sum(1 for i in items if i["settled"])
    total_cost = _sum("cost_total_cny")
    total_revenue = _sum("sale_cny")
    return {
        "total": len(items),
        "cards": card_count,
        "devices": device_count,
        # 按状态筛时从整机里单独列出来的部件
        "parts": len(items) - card_count - device_count,
        # 「在库」= 还没卖完的（显卡没卖出、整机部件没出完）
        "in_stock": len(items) - settled,
        "settled": settled,
        "total_cost_cny": total_cost,
        # 日元合计取的是**同一批行**（countable）。不这样的话两个数字统计的行数不一样，
        # 摆在一起看就是一笔对不上的账。日元侧自己折不出来的行按 0 计——它已经被上面
        # 那一句排除在外了，剩下的只有「人民币算得出、日元算不出」这种边角情况。
        "total_cost_jpy": _sum("cost_total_jpy", 0),
        "total_revenue_cny": total_revenue,
        # 已收回 − 已花出去。含未卖完的整机，所以是「到目前为止的盈亏」
        "total_profit_cny": round(total_revenue - total_cost, 2),
        "recovery": round(total_revenue / total_cost * 100, 2) if total_cost else None,
        "incomplete": sum(1 for i in items if i["incomplete"] and i["kind"] != KIND_PART),
    }


@router.get("")
def list_inventory(
    f: Dict[str, Any] = Depends(_inventory_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    # 默认按购入日期倒序：列表是按「哪天买的」来翻的，录入顺序（补录老货时）和它对不上
    sort_by: str = Query(default="purchase_date"),
    sort_dir: str = Query(default="desc"),
):
    items = _collect(f)
    items = _sort(items, sort_by, sort_dir)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    _attach_part_media(page_items)
    return {
        "items": page_items,
        "total": len(items),
        "page": page,
        "page_size": page_size,
    }
