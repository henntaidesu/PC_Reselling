# -*- coding: utf-8 -*-
"""库存合并列表：显卡与整机设备放在同一张表里，用 ``kind`` 区分。

**为什么要有这个模块**：两种货的数据结构差得远——显卡是一进一出（买价卖价在同一行），
整机是一进多出（一笔总价，拆件分售，出售价在 device_parts 上）。硬塞进一张表会让两边
都别扭。但**看库存的人不关心这个**：他要的是「我手上一共有什么、花了多少、回来多少」，
按类型分成两个页面等于每次都要看两遍再自己加一次。

所以底层仍是 cards / devices 两套表与两套 CRUD，只在这里把它们**规范化成同一种行**
（编号、名称、状态、日期、成本、收入、盈亏），再统一筛选、排序、分页。

**为什么在 Python 里排序分页而不是 SQL**：两张表结构不同，UNION 要先把列一一对齐，
而成本 / 利润根本不是列——它们是按汇率快照算出来的（见 cards.compute_money）。想在
SQL 里按利润排序就得把整套换算逻辑再用 SQL 写一遍，两份实现迟早对不上。这个系统的
量级是几百行，全取回来在内存里排完再切页，快得多也稳得多。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src import cards, db, devices, funds
from src.auth import require_auth
from src.schema import CARD_STATUSES

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
    "mgmt_no", "title", "status", "cost_total_cny", "sale_cny", "profit_cny",
}


# ── 规范化：两种货 → 同一种行 ───────────────────────────────────────────── #

def _involved(drawn: List[Optional[str]], shares: List[Dict[str, Any]]) -> List[str]:
    """这件货**牵涉到**哪些出资人：出资比例里写了的，加上扣款实际吃到了钱的。

    按出资人筛选用的是这一份，两个来源缺一不可：只看比例的话，没写比例、在全池上
    FIFO 扣到了老李那批钱的货筛不出来；只看扣款的话，写了比例但还没点「确认扣除」的
    货也筛不出来——而那正是「老李出钱、还没扣」最该被找到的时候。
    """
    names: List[str] = []
    for name in [sh.get("contributor") for sh in shares] + list(drawn):
        if name and name not in names:
            names.append(name)
    return names


def _card_item(row: Dict[str, Any], media: List[Dict[str, Any]],
               contributors: List[Optional[str]], shares: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        "from_pool": money["from_pool"],
        # 这笔钱从哪儿出的。from_pool 只在**确认扣除之后**才为真，所以两者不是互为反面：
        # 选了池子但还没点确认的行，fund_source 是 pool 而 from_pool 是 false，列表里
        # 不该给它贴任何一个标（成本这会儿还是按购入日牌价折的）。
        "fund_source": row.get("fund_source") or "own",
        # 扣款实际吃到了谁的钱（见 funds.load_draw_contributors），列表在金额后面标名字
        "pool_contributors": contributors if money["from_pool"] else [],
        "fund_contributors": _involved(contributors, shares),
        "media": data["media"],
    }


def _part_row(part: Dict[str, Any], device_id: int) -> Dict[str, Any]:
    """把一个部件规范化成**和顶层行同样的形状**，作为整机的二级行。

    不适用的列一律给 None，前端统一显示成「—」：部件没有购入日（整机是一口价买的），
    也没有单件成本——总价不往部件上摊（理由见 src.devices 的模块文档），所以「总成本」
    和「利润」这两列在部件行上是空的，只有出售侧的数字。
    """
    money = part["money"]
    title = " ".join(x for x in (part.get("brand"), part.get("model"), part.get("spec")) if x)
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
        "from_pool": False,
        # 部件不单独出钱：整机是一口价买的，资金来源在整机那一行上
        "fund_source": None,
        "pool_contributors": [],
        "fund_contributors": [],
        "media": [],
    }


def _device_item(row: Dict[str, Any], parts: List[Dict[str, Any]],
                 media: List[Dict[str, Any]], contributors: List[Optional[str]],
                 shares: List[Dict[str, Any]]) -> Dict[str, Any]:
    data = devices.serialize(row, parts)
    money = data["money"]
    # 整机没有单一的「出售日期」——部件是分批卖的，这里取最后成交的那天。
    # **列表的顶层行不显示它**（逐件的出售日期在展开的二级行上，那才是实情），
    # 这个值留着是给按出售日期排序用的：整机得有个可比的位置，不然排序时全落到末尾。
    sale_dates = [p["sale_date"] for p in data["parts"] if p["sale_date"]]
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
        "fund_source": row.get("fund_source") or "own",
        "pool_contributors": contributors if money["from_pool"] else [],
        "fund_contributors": _involved(contributors, shares),
        # 整机自己的图（外观 / 铭牌…），列表里取第一张当封面，与显卡同一套
        "media": media,
    }
    # 二级行。没有部件时**不带 children 这个键**——给个空数组的话 el-table 仍会画出
    # 一个点开是空的展开箭头。
    if data["parts"]:
        item["children"] = [_part_row(p, row["id"]) for p in data["parts"]]
    return item


# ── 筛选 ────────────────────────────────────────────────────────────────── #

def _statuses(status: Optional[str]) -> List[str]:
    if not status:
        return []
    return [s.strip() for s in status.split(",") if s.strip() in CARD_STATUSES]


def _fetch_cards(
    keyword: Optional[str],
    statuses: List[str],
    brand: Optional[str],
    source_platform: Optional[str],
    purchase_from: Optional[dt.date],
    purchase_to: Optional[dt.date],
) -> List[Dict[str, Any]]:
    where: List[str] = ["is_draft = 0"]
    params: List[Any] = []
    if keyword:
        like = f"%{keyword.strip()}%"
        where.append(
            "(mgmt_no LIKE %s OR brand LIKE %s OR model LIKE %s "
            "OR serial_no LIKE %s OR seller LIKE %s OR order_no LIKE %s)"
        )
        params.extend([like] * 6)
    if statuses:
        where.append("status IN ({ph})".format(ph=", ".join(["%s"] * len(statuses))))
        params.extend(statuses)
    if brand:
        where.append("brand = %s")
        params.append(brand.strip())
    if source_platform:
        where.append("source_platform = %s")
        params.append(source_platform.strip())
    if purchase_from:
        where.append("purchase_date >= %s")
        params.append(purchase_from)
    if purchase_to:
        where.append("purchase_date <= %s")
        params.append(purchase_to)

    rows = db.query("SELECT * FROM cards WHERE " + " AND ".join(where), params)
    ids = [r["id"] for r in rows]
    media_map = cards.load_media(ids)
    contrib_map = funds.load_draw_contributors("card", ids)
    shares_map = funds.load_shares("card", ids)
    return [_card_item(r, media_map.get(r["id"], []), contrib_map.get(r["id"], []),
                       shares_map.get(r["id"], [])) for r in rows]


def _fetch_devices(
    keyword: Optional[str],
    statuses: List[str],
    brand: Optional[str],
    source_platform: Optional[str],
    purchase_from: Optional[dt.date],
    purchase_to: Optional[dt.date],
) -> List[Dict[str, Any]]:
    where: List[str] = ["is_draft = 0"]
    params: List[Any] = []
    if keyword:
        like = f"%{keyword.strip()}%"
        # 部件里的品牌 / 型号 / 序列号也要能搜到：找一台机器往往是从「哪台里有那块 4090」
        # 反推的，只搜设备自己的字段等于搜不到。
        where.append(
            "(mgmt_no LIKE %s OR title LIKE %s OR seller LIKE %s OR order_no LIKE %s "
            " OR EXISTS (SELECT 1 FROM device_parts p WHERE p.device_id = devices.id "
            "            AND (p.brand LIKE %s OR p.model LIKE %s OR p.spec LIKE %s "
            "                 OR p.serial_no LIKE %s)))"
        )
        params.extend([like] * 8)
    if statuses:
        where.append("status IN ({ph})".format(ph=", ".join(["%s"] * len(statuses))))
        params.extend(statuses)
    if brand:
        # 整机本身没有品牌，按「里面有这个品牌的部件」来匹配
        where.append(
            "EXISTS (SELECT 1 FROM device_parts p WHERE p.device_id = devices.id AND p.brand = %s)"
        )
        params.append(brand.strip())
    if source_platform:
        where.append("source_platform = %s")
        params.append(source_platform.strip())
    if purchase_from:
        where.append("purchase_date >= %s")
        params.append(purchase_from)
    if purchase_to:
        where.append("purchase_date <= %s")
        params.append(purchase_to)

    rows = db.query("SELECT * FROM devices WHERE " + " AND ".join(where), params)
    ids = [r["id"] for r in rows]
    parts_map = devices.load_parts(ids)
    media_map = devices.load_media(ids)
    contrib_map = funds.load_draw_contributors("device", ids)
    shares_map = funds.load_shares("device", ids)
    return [_device_item(r, parts_map.get(r["id"], []), media_map.get(r["id"], []),
                         contrib_map.get(r["id"], []), shares_map.get(r["id"], [])) for r in rows]


# 出资人筛选里「未指定」的取值：比例没写、扣款也没吃到任何有名字的批次的那些货。
# 用一个不可能是人名的记号，而不是空串——空串在查询串里会被当成「没传」。
CONTRIBUTOR_NONE = "__none__"

_STOCK_STATES = {"in_stock", "settled"}
_PROFIT_STATES = {"gain", "loss", "incomplete"}
_POOL_STATES = {"drawn", "undrawn"}


def _inventory_filters(
    kind: Optional[str] = Query(default=None, description="card / device，留空为全部"),
    keyword: Optional[str] = Query(default=None, description="编号/型号/序列号/卖家/部件 模糊匹配"),
    status: Optional[str] = Query(default=None, description="逗号分隔的多个状态"),
    brand: Optional[str] = Query(default=None),
    source_platform: Optional[str] = Query(default=None),
    purchase_from: Optional[dt.date] = Query(default=None),
    purchase_to: Optional[dt.date] = Query(default=None),
    contributor: Optional[str] = Query(default=None, description=f"逗号分隔的出资人，{CONTRIBUTOR_NONE} 表示未指定"),
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
        kind=kind, keyword=keyword, status=status, brand=brand, source_platform=source_platform,
        purchase_from=purchase_from, purchase_to=purchase_to,
        contributors=[c.strip() for c in (contributor or "").split(",") if c.strip()],
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
    """按**算出来的**字段筛：出资人、结清、盈亏、池内扣除、成本。

    这些都不是数据库列（成本 / 利润按汇率快照现算，出资人来自分摊结果），所以和排序
    一样放在规范化之后、在内存里做，口径与列表上显示的那个数天然一致。
    """
    if f["contributors"]:
        names = item["fund_contributors"]
        want_none = CONTRIBUTOR_NONE in f["contributors"]
        if not (any(n in names for n in f["contributors"]) or (want_none and not names)):
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


def _collect(f: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按筛选条件取出两类库存，合成一个列表。列表与统计共用它，口径永远一致。

    分两步：能落到 SQL 的（关键词、状态、品牌、平台、购入日期）先在库里筛掉，
    剩下的派生条件在规范化之后由 _match_derived 过一遍。
    """
    status = f["status"]
    statuses = _statuses(status)
    # 指定了状态却一个合法值都没有：说明筛的是不存在的状态，直接返回空，
    # 而不是把条件丢掉当「不筛」——那会让人以为筛选没生效。
    if status and not statuses:
        return []
    items: List[Dict[str, Any]] = []
    args = (f["keyword"], statuses, f["brand"], f["source_platform"],
            f["purchase_from"], f["purchase_to"])
    if f["kind"] != KIND_DEVICE:
        items.extend(_fetch_cards(*args))
    if f["kind"] != KIND_CARD:
        items.extend(_fetch_devices(*args))
    return [i for i in items if _match_derived(i, f)]


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


@router.get("/stats")
def stats(f: Dict[str, Any] = Depends(_inventory_filters)):
    """顶部统计：对**当前筛选下的全部库存**（不只当前页）汇总，显卡与整机合在一起。

    金额一律用各自领域模块算好的结果，缺汇率的项不当 0 计入（见 compute_money）。
    """
    items = _collect(f)

    # 缺汇率的行（incomplete）三项合计里一个都不参与。逐项跳过 None 的话，一行的收入
    # 会在它的成本被丢掉的情况下照样计入合计，「总利润」就凭空多出这一整笔成本——
    # 宁可整行不算，也不能算出一个偏高的净利润。行数在 incomplete 里另外报。
    countable = [i for i in items if not i["incomplete"]]

    def _sum(key: str, digits: int = 2) -> float:
        return round(sum(i[key] for i in countable if i[key] is not None), digits)

    card_count = sum(1 for i in items if i["kind"] == KIND_CARD)
    settled = sum(1 for i in items if i["settled"])
    total_cost = _sum("cost_total_cny")
    total_revenue = _sum("sale_cny")
    return {
        "total": len(items),
        "cards": card_count,
        "devices": len(items) - card_count,
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
        "incomplete": sum(1 for i in items if i["incomplete"]),
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
    return {
        "items": items[start:start + page_size],
        "total": len(items),
        "page": page,
        "page_size": page_size,
    }
