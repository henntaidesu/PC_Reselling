# -*- coding: utf-8 -*-
"""资金池：注资批次、扣款、FIFO 分摊与人民币成本换算。

**为什么需要它**：先换一笔日元放在日本的账户里，再陆续用这笔钱买卡——这时一张卡的
真实人民币成本，取决于「买它的钱是哪一批换进来的、当时换汇价多少」，而不是买卡那天
的市场牌价。同一天买的两张卡，如果吃的是不同批次的钱，成本就不一样。

**模型**（三张表）：

- ``fund_injections`` 注资批次：一次换汇进池一条，带自己那天的汇率快照。
- ``fund_draws`` 扣款：卡片与整机侧的「购入价 / 国际运费」跟着各自的金额自动同步
  （一卡一类一条 / 一机一类一条），另有手工记的池内杂项支出。**设了归属人就扣**，
  扣款行上的 ``contributor_id`` 就是那件货的归属人（见 ``cards.uses_pool``）。
- ``fund_allocations`` 分摊明细：一笔扣款按 FIFO 拆到若干批次上，每段带该批次的汇率。

**按人分池**：注资上的 ``contributor_id`` 标记这笔钱是谁的，扣款上的 ``contributor_id``
（卡片 / 整机的扣款取自货的归属人）决定从谁的钱里扣——FIFO 只在那个人的注资批次里跑，
等价于每人一个池子。没指定人的手工支出在全池上跑。``pool_fx_rate`` 因此是这个人
那几批钱的加权汇率，而不是全池平均。「人」就是用户系统里的账号，两列都存 users.id
（为什么不存名字见 src.people）；对外输出时另带一个现查的显示名 ``contributor``。

**FIFO 与欠款**：

1. 先进先出：扣款按 ``draw_date``、注资按 ``inject_date`` 各自排好，前面的扣款先吃
   最早的批次。
2. **允许池子为负**：一个人的钱不够时照样扣，欠下的记为 ``shortfall``。这个人**之后**
   再注资，那笔钱会先顶上欠款（按 FIFO，较早的扣款先吃到），被顶上的那部分成本
   就按新注资的汇率算——这就是「先买、后补钱」的真实成本。还没补上的部分按扣款日的
   市场牌价暂估，并给出警告；补齐之后重算一遍，暂估自动消失。
   所以不再限制「只能吃扣款日之前进池的钱」：那条规则下，欠款永远补不上。

**专款**：注资上的 ``card_id`` / ``device_id`` 指定这笔钱只给那一件货扣。那件货的扣款
先吃自己的专款，再按普通 FIFO 吃归属人的其余批次；别的扣款一律碰不到专款。用于给
「当初没走池子、后来才补上归属人」的老货补录资金（见 schema._migrate_shares_to_owner）：
补的那笔按普通 FIFO 排的话，老货会先吃掉更早的批次，把后面的货挤成欠款。

**出售回流**：货以**日元**卖掉时，收到的日元就躺在日本的账户里——它就是池子里的钱，
下一件货可以直接拿它买。所以日元售价会自动变成归属人名下的一笔注资（``inject_type =
'sale'``），汇率取出售日的牌价快照（卡 / 部件上的 ``sale_fx_rate``）。用出售日汇率是和
收入口径对齐：这笔售价折人民币算收入用的就是它，日元按同一个价进池，之后花它买的货
成本也按这个价算，前后不凭空多出或少掉一笔汇差。
回流行与货上的售价自动同步（``sync_sale_returns``），和购入侧的扣款同一个思路；条件是
日元、填了出售日期（没有日期就没有汇率）、有归属人（没有归属人的货不进池，卖出的钱
也就无池可回）。部件的钱归部件自己的归属人，没填才跟随整机。人民币售价与池子无关。

谁出了多少、被用掉多少、还剩（或欠）多少，全部由分摊结果反算（``contributor_totals()``）。

**分摊是全量派生数据**：任何注资或扣款变动后都整体重算（``rebuild()``），而不是增量
维护。理由是「补录一笔上个月的注资」会改变它之后所有扣款的分摊结果，增量算法要处理
的回溯情形远比全量重算复杂，而这个系统的数据量（几百条）重算一次不到几十毫秒。

算完把分摊结果回写到 ``cards`` / ``devices`` 的 ``pool_purchase_cny / pool_intl_cny /
pool_fx_rate``，列表页和统计就不用为每一行再查一次明细（N+1）。两张表的这三列同名同义，
所以下面的同步与回写都写成「按归属方」的一套代码，而不是复制两份。
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from src import db, people
# uses_pool 的定义只有 cards.py 那一份（「有归属人」）。
# 在这里照抄一遍条件的下场是某天只改了其中一处，成本按池子算、扣款却没同步。
from src.cards import uses_pool
from src.fx import RATE_UNIT, FxError, get_rate
from src.schema import POOL_CURRENCY

log = logging.getLogger(__name__)

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
_RATE_UNIT = Decimal(str(RATE_UNIT))
_RATE_Q = Decimal("0.00000001")   # fund_injections.fx_rate 是 DECIMAL(18,8)

# 由系统自动同步的两类扣款 → 回写到归属行上的哪一列
_CARD_CATEGORIES = {
    "purchase": "pool_purchase_cny",
    "intl_shipping": "pool_intl_cny",
}

# 扣款的两种归属：卡片和整机。值是 (外键列, 目标表)。两张表的分摊快照列同名，
# 所以同步与回写共用一套代码，只有这两个名字不同。
_OWNERS = {
    "card": ("card_id", "cards"),
    "device": ("device_id", "devices"),
}


# ── 小工具 ──────────────────────────────────────────────────────────────── #

def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _round(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None:
        return None
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _float(value: Any) -> Optional[float]:
    value = _dec(value)
    return float(value) if value is not None else None


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def _to_cny(amount: Optional[Decimal], rate: Optional[Decimal]) -> Optional[Decimal]:
    """日元 → 人民币。rate 是「100 日元 = rate 人民币」，与 cards._to_cny 同一个算式。"""
    if amount is None or rate is None or rate <= 0:
        return None
    return _round(amount * rate / _RATE_UNIT)


# ── 注资的汇率 ──────────────────────────────────────────────────────────── #

def manual_rate(amount: Any, cny_cost: Any) -> Optional[float]:
    """由「换到多少日元」和「实际付了多少人民币」反推这批钱的汇率。

    换汇的人手上有的就是这两个数，汇率是它们的商。让人自己先除一遍再填，既多一步，
    又容易把 4.32 填成 0.0432 或 23.16——那种错算出来的成本差几百倍，页面上却看不出来。
    """
    jpy = _dec(amount)
    cny = _dec(cny_cost)
    if not jpy or not cny or jpy <= 0 or cny <= 0:
        return None
    return float((cny / jpy * _RATE_UNIT).quantize(_RATE_Q, rounding=ROUND_HALF_UP))


def resolve_injection_fx(
    inject_date: dt.date,
    amount: Any = None,
    cny_cost: Any = None,
) -> Dict[str, Any]:
    """定这批钱的汇率：填了实付人民币就由它算（外汇注资），否则按注资日取牌价（现金注资）。

    手工模式录的是实付人民币，汇率由 ``manual_rate`` 算出来。**存进去的仍然是汇率**：
    FIFO 要把一个批次拆成几段分给不同的扣款，只有按汇率折才拆得开。

    取不到不抛异常——先把注资记下来，汇率留空之后再补；只是在它被补上之前，吃到这批
    钱的卡片成本会显示成「缺汇率」，而不是一个猜出来的数字。
    """
    out: Dict[str, Any] = {"fx_rate": None, "fx_date": None, "fx_manual": 0, "warnings": []}
    rate = manual_rate(amount, cny_cost)
    if rate:
        out.update({"fx_rate": rate, "fx_date": inject_date, "fx_manual": 1})
        return out
    try:
        result = get_rate(inject_date)
    except FxError as exc:
        out["warnings"].append(f"注资日汇率获取失败：{exc}")
        return out
    out["fx_rate"] = result["rate"]
    out["fx_date"] = result["rate_date"]
    if result["stale"]:
        out["warnings"].append(f"{inject_date} 无牌价，已回退到 {result['rate_date']} 的汇率")
    elif result["rate_date"] != inject_date:
        out["warnings"].append(f"{inject_date} 是非交易日，采用 {result['rate_date']} 的牌价")
    return out


# ── FIFO 分摊（纯函数，不碰数据库，便于单独验算）──────────────────────────── #

def _earmark_of(row: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    """注资的专款对象，或扣款的归属对象：(card|device, id)。两边用同一个键配对。"""
    for kind, (col, _table) in _OWNERS.items():
        if row.get(col):
            return (kind, int(row[col]))
    return None


def allocate(
    injections: List[Dict[str, Any]],
    draws: List[Dict[str, Any]],
    market_rate: Any = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把每笔扣款按 FIFO 拆到注资批次上。

    ``injections`` 必须按 (inject_date, id) 升序，``draws`` 按 (draw_date, id) 升序——
    扣款也要按时间顺序处理，否则「谁先花掉了那批便宜的钱」会取决于录入顺序。

    ``draw["contributor_id"]`` 有值时只在那个人的批次里扣，没有就在全部批次上扣。
    专款批次（注资上带 card_id / device_id）只给对应那件货的扣款，而且排在最前面。
    批次的日期不设上限：比扣款晚进池的钱同样能被吃到，那就是「欠着、后来补上」
    （见模块文档）。全部批次都吃光了还不够的部分记为 shortfall。

    ``market_rate`` 是个 ``(date) -> Decimal | None`` 的函数，用于暂估还欠着的部分。

    返回 ``(分摊行, 每笔扣款的汇总)``。
    """
    remaining: Dict[int, Decimal] = {
        int(inj["id"]): (_dec(inj["amount"]) or _ZERO) for inj in injections
    }
    # 按出资人预先分好候选批次。每笔扣款现筛一遍的话是「几百笔 × 几十批」次比较，
    # 而且筛出来的顺序还得再保证一次；这里分一次，各桶天然继承了入参的日期升序。
    # 专款单独分桶，不进普通候选。
    by_contributor: Dict[Optional[int], List[Dict[str, Any]]] = {}
    general: List[Dict[str, Any]] = []
    earmarked: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for inj in injections:
        target = _earmark_of(inj)
        if target:
            earmarked.setdefault(target, []).append(inj)
            continue
        general.append(inj)
        by_contributor.setdefault(inj.get("contributor_id") or None, []).append(inj)

    allocations: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []

    for draw in draws:
        total = _dec(draw["amount"]) or _ZERO
        draw_date = draw["draw_date"]
        contributor = draw.get("contributor_id") or None

        seq = 0
        lines: List[Dict[str, Any]] = []
        cny_total: Optional[Decimal] = _ZERO
        jpy_converted = _ZERO
        shortfall = _ZERO

        need = total
        # 先吃给这件货的专款，再吃普通批次：指定了人就只在他的批次里扣（每人一个池子），
        # 没指定就是全池
        candidates = earmarked.get(_earmark_of(draw), []) + (
            by_contributor.get(contributor, []) if contributor else general)
        for inj in candidates:
            if need <= 0:
                break
            available = remaining.get(int(inj["id"]), _ZERO)
            if available <= 0:
                continue
            take = available if available < need else need
            rate = _dec(inj.get("fx_rate"))
            # 现金注资也按它自己的汇率（注资日牌价）折算，不当 0：那等于说这笔钱是
            # 白来的，吃到它的货成本归零、利润凭空多出一整份购入价。
            cny = _to_cny(take, rate)
            remaining[int(inj["id"])] = available - take
            need -= take
            lines.append({
                "draw_id": int(draw["id"]),
                "injection_id": int(inj["id"]),
                "seq": seq,
                "amount": take,
                "fx_rate": rate,
                "cny_amount": cny,
            })
            seq += 1
            # 任何一段折不出来（该批次还没汇率），整笔扣款的人民币成本就作废：
            # 拿「能算的那部分」当合计，会得到一个明显偏低却看不出问题的成本。
            if cny is None:
                cny_total = None
            elif cny_total is not None:
                cny_total += cny
                jpy_converted += take
        if need > 0:
            shortfall += need

        if shortfall > 0:
            # 还欠着的部分先按扣款日牌价暂估；之后补了注资，重算时就被新批次顶上
            fallback = market_rate(draw_date) if callable(market_rate) else _dec(market_rate)
            short_cny = _to_cny(shortfall, _dec(fallback))
            if short_cny is None:
                cny_total = None
            elif cny_total is not None:
                cny_total += short_cny
                jpy_converted += shortfall

        allocations.extend(lines)
        results.append({
            "draw": draw,
            "lines": lines,
            "cny_amount": _round(cny_total),
            "shortfall": shortfall,
            # 这笔钱实际吃到的加权汇率，与各批次的汇率同口径（100 日元 = ? 人民币）
            "effective_rate": (cny_total / jpy_converted * _RATE_UNIT)
            if (cny_total is not None and cny_total > 0 and jpy_converted > 0) else None,
        })

    return allocations, results


# ── 重算 ────────────────────────────────────────────────────────────────── #

def _market_rate_lookup():
    """按日期取市场牌价，只读本地缓存。

    重算会在每次存卡时触发，这里**不打网络**：几十笔扣款各打一次外部接口，会把一次
    保存拖成好几秒，而这个值只用于「池子不够」的兜底部分。取不到就留空（显示为不完整）。
    """
    memo: Dict[Any, Optional[Decimal]] = {}

    def lookup(date: Optional[dt.date]) -> Optional[Decimal]:
        if not date:
            return None
        if date not in memo:
            try:
                memo[date] = _dec(get_rate(date, allow_network=False)["rate"])
            except FxError:
                memo[date] = None
        return memo[date]

    return lookup


def rebuild() -> Dict[str, Any]:
    """整体重算全部分摊，并把结果回写到扣款行与它的归属行。可重复执行，结果幂等。"""
    injections = db.query(
        "SELECT id, inject_date, amount, fx_rate, contributor_id, inject_type, card_id, device_id "
        "FROM fund_injections ORDER BY inject_date, id"
    )
    # 扣款在谁的钱里扣就看它自己的 contributor_id：货的扣款由 sync_owner_draws 写成归属人，
    # 手工支出是录入时选的
    draws = db.query(
        "SELECT id, card_id, device_id, category, draw_date, amount, contributor_id "
        "FROM fund_draws ORDER BY draw_date, id"
    )
    allocations, results = allocate(injections, draws, _market_rate_lookup())

    # 每个归属方（一张卡 / 一台整机）把它的两类扣款汇总起来，一次性回写。
    # key 里带上归属类型：卡片和整机的 id 各自从 1 开始，只用 id 会把两者混在一起。
    owner_values: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for res in results:
        draw = res["draw"]
        if draw["category"] not in _CARD_CATEGORIES:
            continue
        owner = next(
            ((kind, int(draw[col])) for kind, (col, _t) in _OWNERS.items() if draw.get(col)),
            None,
        )
        if owner is None:
            continue  # 手工记的池内支出，不属于任何一行
        bucket = owner_values.setdefault(owner, {
            "pool_purchase_cny": None, "pool_intl_cny": None,
            "_jpy": _ZERO, "_cny": _ZERO, "_broken": False,
        })
        bucket[_CARD_CATEGORIES[draw["category"]]] = res["cny_amount"]
        if res["cny_amount"] is None:
            bucket["_broken"] = True
        else:
            bucket["_jpy"] += _dec(draw["amount"]) or _ZERO
            bucket["_cny"] += res["cny_amount"]

    with db.transaction() as cur:
        # 分摊行全删重插：它是纯派生数据，没有任何外部引用指向它
        cur.execute("DELETE FROM fund_allocations")
        if allocations:
            cur.executemany(
                "INSERT INTO fund_allocations (draw_id, injection_id, seq, amount, fx_rate, cny_amount) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [(a["draw_id"], a["injection_id"], a["seq"], a["amount"], a["fx_rate"], a["cny_amount"])
                 for a in allocations],
            )
        for res in results:
            cur.execute(
                "UPDATE fund_draws SET cny_amount = %s, shortfall = %s WHERE id = %s",
                (res["cny_amount"], res["shortfall"], res["draw"]["id"]),
            )
        # 先把两张表的分摊快照都清空，再写回有扣款的那些：漏清的话，一行改回「自有资金」
        # 之后仍留着上一次的池成本，成本就永远停在旧值上。
        for _col, table in _OWNERS.values():
            cur.execute(
                f"UPDATE {table} SET pool_purchase_cny = NULL, pool_intl_cny = NULL, "
                f"pool_fx_rate = NULL WHERE pool_purchase_cny IS NOT NULL "
                f"OR pool_intl_cny IS NOT NULL OR pool_fx_rate IS NOT NULL"
            )
        for (kind, owner_id), bucket in owner_values.items():
            rate = None
            if not bucket["_broken"] and bucket["_cny"] > 0 and bucket["_jpy"] > 0:
                rate = bucket["_cny"] / bucket["_jpy"] * _RATE_UNIT
            # 表名来自 _OWNERS 这张固定的表，不是外部输入，拼进 SQL 是安全的
            cur.execute(
                f"UPDATE {_OWNERS[kind][1]} SET pool_purchase_cny = %s, pool_intl_cny = %s, "
                f"pool_fx_rate = %s WHERE id = %s",
                (bucket["pool_purchase_cny"], bucket["pool_intl_cny"], rate, owner_id),
            )

    warnings: List[str] = []
    short = [r for r in results if r["shortfall"] > 0]
    if short:
        warnings.append(f"有 {len(short)} 笔扣款超出了池内余额（欠款），欠着的部分暂按当日市场牌价折算，补充注资后自动重算")
    missing = [r for r in results if r["cny_amount"] is None]
    if missing:
        warnings.append(f"有 {len(missing)} 笔扣款因缺少汇率算不出人民币成本")
    return {
        "draws": len(results),
        "allocations": len(allocations),
        "owners": len(owner_values),
        "warnings": warnings,
    }


# ── 归属方（卡片 / 整机）扣款的同步 ─────────────────────────────────────── #

def poolable_amounts(row: Dict[str, Any]) -> Dict[str, Decimal]:
    """这一行有哪几笔能从池里出，按扣款类别归好。

    只有**日元**进得了池子（池子装的是日元）；同一行上以人民币付的那项与池子无关，
    照旧按牌价折算。确认扣除前要拿它判断「有没有钱可扣」，同步扣款时要拿它算金额，
    两处必须是同一个判断——不然会出现「确认得下去、却一分钱都没扣」。
    """
    out: Dict[str, Decimal] = {}
    for category, amount_key, currency_key in (
        ("purchase", "purchase_amount", "purchase_currency"),
        ("intl_shipping", "intl_shipping_amount", "intl_shipping_currency"),
    ):
        amount = _dec(row.get(amount_key))
        currency = (row.get(currency_key) or "").upper()
        if amount and amount > 0 and currency == POOL_CURRENCY:
            out[category] = amount
    return out


def sync_owner_draws(kind: str, owner_id: int, row: Optional[Dict[str, Any]] = None) -> bool:
    """让一张卡 / 一台整机的池内扣款与它上面的金额保持一致，返回是否发生了改动。

    卡片和整机在这件事上完全同构：都有 fund_source、purchase_amount、
    intl_shipping_amount 和对应的币种，区别只是扣款行挂在哪一列上。所以这里写成
    一套，靠 ``_OWNERS`` 里的 (外键列, 表名) 分流——复制两份的下场是改了一边忘了
    另一边，而这种账目上的不一致要等到对不上数才会被发现。

    「一卡一类一条 / 一机一类一条」由唯一键保证，所以这里按 category 做 upsert 而不是
    先删后插——先删后插会让 id 每次保存都变，分摊明细也就没法追溯了。
    只有日元金额进池：池子装的是日元，人民币支出与它无关（照旧走牌价折算）。

    扣款的 ``contributor_id`` 就是货的归属人：换了归属人，钱就改从新那个人的池里扣；
    清空归属人，``uses_pool`` 为假、wanted 为空，扣款被删掉，钱还回池子。
    """
    col, table = _OWNERS[kind]
    row = row or db.query_one(f"SELECT * FROM {table} WHERE id = %s", (owner_id,))
    if not row:
        return False
    draw_date = row.get("purchase_date") or dt.date.today()
    wanted = poolable_amounts(row) if uses_pool(row) else {}
    owner = _owner_id(row)

    existing = {
        r["category"]: r for r in db.query(
            f"SELECT id, category, draw_date, amount, contributor_id FROM fund_draws WHERE {col} = %s",
            (owner_id,),
        )
    }
    changed = False

    for category in _CARD_CATEGORIES:
        want = wanted.get(category)
        have = existing.get(category)
        if want is None:
            if have:
                db.execute("DELETE FROM fund_draws WHERE id = %s", (have["id"],))
                changed = True
            continue
        if not have:
            db.insert(
                f"INSERT INTO fund_draws ({col}, category, draw_date, amount, currency, contributor_id) "
                f"VALUES (%s, %s, %s, %s, %s, %s)",
                (owner_id, category, draw_date, want, POOL_CURRENCY, owner),
            )
            changed = True
        elif (_dec(have["amount"]) != want or have["draw_date"] != draw_date
              or (have.get("contributor_id") or None) != owner):
            db.execute(
                "UPDATE fund_draws SET draw_date = %s, amount = %s, contributor_id = %s WHERE id = %s",
                (draw_date, want, owner, have["id"]),
            )
            changed = True

    return changed


def _owner_id(row: Dict[str, Any]) -> Optional[int]:
    return int(row["owner_id"]) if row.get("owner_id") else None


def _sale_return(row: Dict[str, Any], owner: Optional[int]) -> Optional[Dict[str, Any]]:
    """一张卡 / 一个部件的售价该回流成什么样，不该回流就是 None。

    出售日期必须有：回流的汇率就是出售日的牌价快照，没有日期就没有汇率，而注资的
    日期也是 FIFO 的排序依据，拿「今天」顶上会让它排错位置。汇率取不到（接口抽风）
    时照样回流、汇率留空——和注资缺汇率同一个处理，吃到它的货显示「缺汇率」，
    等「刷新汇率」补上。
    """
    amount = _dec(row.get("sale_amount"))
    if (not amount or amount <= 0
            or (row.get("sale_currency") or "").upper() != POOL_CURRENCY
            or not owner or not row.get("sale_date")):
        return None
    return {
        "inject_date": row["sale_date"],
        "amount": amount,
        "fx_rate": _dec(row.get("sale_fx_rate")),
        "fx_date": row.get("sale_fx_date"),
        "contributor_id": owner,
    }


_SALE_FIELDS = ("inject_date", "amount", "fx_rate", "fx_date", "contributor_id")


def sync_sale_returns(kind: str, owner_id: int, row: Optional[Dict[str, Any]] = None) -> bool:
    """让一张卡 / 一台整机各部件的出售回流与它们的售价保持一致，返回是否发生了改动。

    与 ``sync_owner_draws`` 同一个做法：按来源 upsert 而不是先删后插（注资的 id 被
    分摊明细引用着）。整机一个部件一笔，键是部件 id；部件被删时外键把 ``sale_part_id``
    置空，这里查的是整机名下的全部回流，置空的那行对不上任何部件，就在这一步删掉——
    只有经过这里，删部件才会被算作「池子变了」而触发重算。
    """
    col, table = _OWNERS[kind]
    row = row or db.query_one(f"SELECT * FROM {table} WHERE id = %s", (owner_id,))
    if not row:
        return False
    owner = _owner_id(row)
    wanted: Dict[int, Dict[str, Any]] = {}
    if kind == "card":
        want = _sale_return(row, owner)
        if want:
            wanted[owner_id] = want
        key_col, links = "sale_card_id", lambda key: {"sale_card_id": key}
    else:
        for part in db.query("SELECT * FROM device_parts WHERE device_id = %s", (owner_id,)):
            # 部件的钱归部件自己的归属人，没填才跟随整机
            want = _sale_return(part, _owner_id(part) or owner)
            if want:
                wanted[int(part["id"])] = want
        key_col = "sale_part_id"
        links = lambda key: {"sale_device_id": owner_id, "sale_part_id": key}

    # 列名都来自上面写死的常量（sale_card_id / sale_device_id / sale_part_id）
    existing = db.query(
        f"SELECT id, {key_col} AS source_id, {', '.join(_SALE_FIELDS)} "
        f"FROM fund_injections WHERE sale_{col} = %s",
        (owner_id,),
    )
    changed = False
    for inj in existing:
        want = wanted.pop(int(inj["source_id"]), None) if inj["source_id"] else None
        if want is None:
            db.execute("DELETE FROM fund_injections WHERE id = %s", (inj["id"],))
            changed = True
        elif any(inj[f] != want[f] for f in _SALE_FIELDS):
            db.execute(
                "UPDATE fund_injections SET inject_date = %s, amount = %s, fx_rate = %s, "
                "fx_date = %s, contributor_id = %s WHERE id = %s",
                [want[f] for f in _SALE_FIELDS] + [inj["id"]],
            )
            changed = True
    for key, want in wanted.items():
        values = {**want, **links(key)}
        db.insert(
            "INSERT INTO fund_injections ({cols}, currency, fx_manual, inject_type) "
            "VALUES ({ph}, %s, 0, 'sale')".format(
                cols=", ".join(values), ph=", ".join(["%s"] * len(values))),
            list(values.values()) + [POOL_CURRENCY],
        )
        changed = True
    return changed


def sync_all_sale_returns() -> bool:
    """全部卡片与整机的出售回流同步一遍，返回是否有改动（调用方据此决定要不要重算）。"""
    changed = False
    for kind, (_col, table) in _OWNERS.items():
        for row in db.query(f"SELECT * FROM {table} WHERE is_draft = 0"):
            changed = sync_sale_returns(kind, int(row["id"]), row) or changed
    return changed


def touches_pool(kind: str, owner_id: int) -> bool:
    """这件货在池子里有没有账（扣款、出售回流或给它的专款）。删货前问一句：删完它们就被
    外键级联带走了，那时再查已经不知道要不要重算。

    专款也得算上：它的外键是 SET NULL，货一删就变成归属人的普通注资，别的扣款从此
    吃得到它——不重算的话那批钱在分摊里仍是「谁都碰不到」，余额对、成本却停在旧值。"""
    col, _table = _OWNERS[kind]
    return bool(
        db.query_one(f"SELECT id FROM fund_draws WHERE {col} = %s LIMIT 1", (owner_id,))
        or db.query_one(f"SELECT id FROM fund_injections WHERE sale_{col} = %s LIMIT 1", (owner_id,))
        or db.query_one(f"SELECT id FROM fund_injections WHERE {col} = %s LIMIT 1", (owner_id,))
    )


def sync_and_rebuild(kind: str, owner_id: int, row: Optional[Dict[str, Any]] = None) -> None:
    """存卡 / 存整机后调用：同步扣款与出售回流，真的有变化时才重算。

    「有变化才重算」不只是省事——保存是防抖自动触发的（改一个字段就是一次 PUT），
    每次都全量重算会把大量无谓的写打到库上。换归属人也是「有变化」（扣款的
    contributor_id 变了），不需要另外强制重算。
    """
    try:
        _col, table = _OWNERS[kind]
        row = row or db.query_one(f"SELECT * FROM {table} WHERE id = %s", (owner_id,))
        # 两样都得同步，别写成 a or b：前一个有变化时后一个会被短路掉
        changed = sync_owner_draws(kind, owner_id, row)
        changed = sync_sale_returns(kind, owner_id, row) or changed
        if changed:
            rebuild()
    except Exception as exc:  # noqa: BLE001  资金池算不动不该让保存失败
        log.warning("同步%s %s 的资金池扣款失败：%s", kind, owner_id, exc)


def sync_card_draws(card_id: int, row: Optional[Dict[str, Any]] = None) -> bool:
    return sync_owner_draws("card", card_id, row)


def sync_card_and_rebuild(card_id: int, row: Optional[Dict[str, Any]] = None) -> None:
    sync_and_rebuild("card", card_id, row)


def sync_device_and_rebuild(device_id: int, row: Optional[Dict[str, Any]] = None) -> None:
    sync_and_rebuild("device", device_id, row)


def resync_all() -> Dict[str, Any]:
    """把全部卡片与整机的扣款按当前规则重新同步一遍，再整体重算。

    平时用不到（每次保存各自同步）。规则本身变了的时候才需要——比如资金池改成由归属人
    决定之后，那些早就设了归属人、却从没点过「确认扣除」的货，没有一次保存会替它们
    补上扣款。
    """
    for kind, (_col, table) in _OWNERS.items():
        for row in db.query(f"SELECT * FROM {table} WHERE is_draft = 0"):
            sync_owner_draws(kind, int(row["id"]), row)
    sync_all_sale_returns()
    return rebuild()


# ── 查询 ────────────────────────────────────────────────────────────────── #

def _sale_source(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """出售回流是哪件货卖的：{kind, id, mgmt_no, name, part_id, part_type}，普通注资为 None。
    整机的 id 是整机的（详情页按它打开），part_id 指明是其中哪一件。"""
    if row.get("sale_card_id"):
        return {
            "kind": "card", "id": row["sale_card_id"], "mgmt_no": row["sale_card_no"],
            "name": " ".join(x for x in (row["sale_card_brand"], row["sale_card_model"]) if x) or None,
            "part_id": None, "part_type": None,
        }
    if row.get("sale_device_id"):
        return {
            "kind": "device", "id": row["sale_device_id"], "mgmt_no": row["sale_device_no"],
            "name": " ".join(x for x in (row["sale_part_brand"], row["sale_part_model"]) if x) or None,
            "part_id": row.get("sale_part_id"), "part_type": row["sale_part_type"],
        }
    return None


def list_injections(sale_of: Optional[Tuple[str, int]] = None) -> List[Dict[str, Any]]:
    """注资列表，带每批的已用 / 剩余。已用量从分摊明细汇总，池子的账永远自洽。

    ``sale_of=(card|device, id)`` 只取那件货卖出去回流的几笔——详情页要看「卖的钱回到了
    谁的池里、按什么汇率、已经被用掉多少」，与资金池页同一个形状。
    """
    where, params = "", []
    if sale_of:
        # 列名由 _OWNERS 这张固定的表推出，不是外部输入
        where = f" WHERE i.sale_{_OWNERS[sale_of[0]][0]} = %s"
        params.append(sale_of[1])
    rows = db.query(
        "SELECT i.*, COALESCE(SUM(a.amount), 0) AS used_amount, "
        "       COALESCE(SUM(a.cny_amount), 0) AS used_cny, "
        # 专款对象与回流来源的编号。包一层 MAX：一批注资只对应一张卡 / 一台整机，但
        # GROUP BY 下 MySQL 推不出这一点，ONLY_FULL_GROUP_BY 会拒绝裸列
        "       MAX(c.mgmt_no) AS earmark_card_no, MAX(v.mgmt_no) AS earmark_device_no, "
        "       MAX(sc.mgmt_no) AS sale_card_no, MAX(sc.brand) AS sale_card_brand, "
        "       MAX(sc.model) AS sale_card_model, MAX(sv.mgmt_no) AS sale_device_no, "
        "       MAX(sp.part_type) AS sale_part_type, MAX(sp.brand) AS sale_part_brand, "
        "       MAX(sp.model) AS sale_part_model "
        "FROM fund_injections i LEFT JOIN fund_allocations a ON a.injection_id = i.id "
        "LEFT JOIN cards c ON c.id = i.card_id LEFT JOIN devices v ON v.id = i.device_id "
        "LEFT JOIN cards sc ON sc.id = i.sale_card_id "
        "LEFT JOIN devices sv ON sv.id = i.sale_device_id "
        "LEFT JOIN device_parts sp ON sp.id = i.sale_part_id"
        f"{where} GROUP BY i.id ORDER BY i.inject_date DESC, i.id DESC",
        params,
    )
    names = people.names()
    out = []
    for row in rows:
        amount = _dec(row["amount"]) or _ZERO
        used = _dec(row["used_amount"]) or _ZERO
        rate = _dec(row["fx_rate"])
        cny_cost = _to_cny(amount, rate)
        remaining_cny = _to_cny(amount - used, rate)
        out.append({
            "id": row["id"],
            "inject_date": _iso(row["inject_date"]),
            "amount": _float(amount),
            "currency": row["currency"],
            "inject_type": row.get("inject_type") or "forex",
            "fx_rate": _float(rate),
            "fx_date": _iso(row["fx_date"]),
            "fx_manual": bool(row["fx_manual"]),
            # 认人认 id，名字是现查的显示名，只给页面显示用（改了名这里跟着变）
            "contributor_id": row.get("contributor_id"),
            "contributor": people.name_of(row.get("contributor_id"), names),
            # 专款：只给这一件货扣的钱（见 allocate）。{kind, id, mgmt_no}，普通注资为 None
            "earmark": (
                {"kind": "card", "id": row["card_id"], "mgmt_no": row["earmark_card_no"]}
                if row.get("card_id") else
                {"kind": "device", "id": row["device_id"], "mgmt_no": row["earmark_device_no"]}
                if row.get("device_id") else None
            ),
            # 出售回流：这笔钱是哪件货卖出去收回来的（inject_type = 'sale'），只读
            "sale_source": _sale_source(row),
            "note": row["note"],
            "cny_cost": _float(cny_cost),
            "used_amount": _float(used),
            "used_cny": _float(row["used_cny"]),
            "remaining_amount": _float(amount - used),
            "remaining_cny": _float(remaining_cny),
            "created_at": _iso(row["created_at"]),
        })
    return out


def _bucket(buckets: Dict[Any, Dict[str, Any]], user_id: Optional[int],
            names: Dict[int, str]) -> Dict[str, Any]:
    """取（或新建）某个出资人的汇总档。按 id 分档，名字只是跟着显示的。"""
    return buckets.setdefault(user_id, {
        "id": user_id,
        "name": people.name_of(user_id, names),
        "injection_count": 0,
        "injected": 0.0, "injected_cny": 0.0,
        "used": 0.0, "used_cny": 0.0,
        "remaining": 0.0, "remaining_cny": 0.0,
        "shortfall": 0.0,
        "incomplete": False,
    })


def contributor_totals() -> List[Dict[str, Any]]:
    """按出资人汇总：谁投了多少、被花掉多少、还剩多少。

    全部由注资行反算，没有另一张「账户表」。理由和分摊一样——余额只要有第二个地方
    存着，就一定会有对不上的那天；这里的数据量（几十条注资）现算一遍不值一提。

    ``used_*`` 来自 ``list_injections()`` 里已经汇总好的分摊量，所以「谁的钱被花了多少」
    与扣款明细天然一致：FIFO 按日期吃钱，吃到谁头上就算在谁头上。

    没填出资人的注资归到 ``id = None`` 这一档（前端显示「未指定」），不合并进任何人——
    旧数据和自己出的钱都落在这里，硬塞给某个人等于凭空改账。

    人民币合计沿用 ``summary()`` 的口径：缺汇率的批次按 0 计入并置 ``incomplete``，
    由前端打标提示，而不是让整个人的合计变成「—」——那样一批缺汇率会把这个人
    另外十批已经算清楚的钱也一起藏掉。


    **欠款算进余额**：扣款超出这个人的钱时，超出部分（``fund_draws.shortfall``，扣款上
    的 contributor_id 就是他）从 ``remaining`` 里减掉，余额于是成了负数——「还差多少要补」。
    批次层面的剩余永远 ≥ 0（批次不可能被吃成负的），负数只出现在按人汇总上。欠款的
    人民币没有批次汇率可折，``remaining_cny`` 不扣它（暂估的成本已经按牌价记在货上了）。
    """
    rows = list_injections()
    names = people.names()
    total_in = sum(r["amount"] or 0 for r in rows)
    buckets: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        b = _bucket(buckets, row["contributor_id"], names)
        b["injection_count"] += 1
        b["injected"] += row["amount"] or 0
        b["injected_cny"] += row["cny_cost"] or 0
        b["used"] += row["used_amount"] or 0
        b["used_cny"] += row["used_cny"] or 0
        b["remaining"] += row["remaining_amount"] or 0
        b["remaining_cny"] += row["remaining_cny"] or 0
        if row["fx_rate"] is None:
            b["incomplete"] = True
    # 欠款按扣款的 contributor_id 记到人头上；没指定人的全池支出欠下的归「未指定」
    for row in db.query(
        "SELECT contributor_id, SUM(shortfall) AS s FROM fund_draws "
        "WHERE shortfall > 0 GROUP BY contributor_id"
    ):
        b = _bucket(buckets, row.get("contributor_id") or None, names)
        owed = _float(row["s"]) or 0.0
        b["shortfall"] += owed
        b["remaining"] -= owed

    out = []
    for b in buckets.values():
        for key in ("injected", "injected_cny", "used", "used_cny", "remaining", "remaining_cny", "shortfall"):
            b[key] = round(b[key], 2)
        b["avg_rate"] = (
            round(b["injected_cny"] / b["injected"] * RATE_UNIT, 4)
            if b["injected"] and b["injected_cny"] else None
        )
        # 占池子的份额按**日元**算：人民币口径下各人换汇价不同，份额会随汇率浮动，
        # 而「池子里有多少是我的钱」问的是日元。
        b["share"] = round(b["injected"] / total_in, 6) if total_in else None
        out.append(b)
    # 没指定出资人的那档永远排在最后：它不是一个人，是「还没归属」的一堆
    out.sort(key=lambda x: (x["id"] is None, -(x["injected"] or 0), x["name"] or ""))
    return out


def _draw_allocations(draw_ids: List[int], names: Dict[int, str]) -> Dict[int, List[Dict[str, Any]]]:
    if not draw_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(draw_ids))
    rows = db.query(
        f"SELECT a.*, i.inject_date, i.contributor_id FROM fund_allocations a "
        f"JOIN fund_injections i ON i.id = a.injection_id "
        f"WHERE a.draw_id IN ({placeholders}) ORDER BY a.draw_id, a.seq",
        draw_ids,
    )
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["draw_id"]), []).append({
            "injection_id": row["injection_id"],
            "inject_date": _iso(row["inject_date"]),
            "contributor_id": row.get("contributor_id"),
            "contributor": people.name_of(row.get("contributor_id"), names),
            "amount": _float(row["amount"]),
            "fx_rate": _float(row["fx_rate"]),
            "cny_amount": _float(row["cny_amount"]),
        })
    return grouped


def list_draws(
    card_id: Optional[int] = None,
    device_id: Optional[int] = None,
    limit: int = 300,
) -> List[Dict[str, Any]]:
    """扣款列表，每笔带它的分段明细（吃了哪几批钱、各按什么汇率折算）。

    每行都带上归属方：``owner_kind`` 是 card / device / None（手工记的池内支出），
    ``owner_name`` 与 ``mgmt_no`` 取自对应的那张表——前端只看这三个字段就能显示，
    不必自己判断该读 card 还是 device 的哪个字段。
    """
    where, params = "", []
    if card_id:
        where = " WHERE d.card_id = %s"
        params.append(card_id)
    elif device_id:
        where = " WHERE d.device_id = %s"
        params.append(device_id)
    rows = db.query(
        "SELECT d.*, c.mgmt_no AS card_mgmt_no, c.brand, c.model, "
        "       v.mgmt_no AS device_mgmt_no, v.title AS device_title "
        "FROM fund_draws d "
        "LEFT JOIN cards c ON c.id = d.card_id "
        "LEFT JOIN devices v ON v.id = d.device_id"
        f"{where} ORDER BY d.draw_date DESC, d.id DESC LIMIT %s",
        params + [limit],
    )
    names = people.names()
    alloc_map = _draw_allocations([int(r["id"]) for r in rows], names)
    out = []
    for row in rows:
        amount = _dec(row["amount"]) or _ZERO
        cny = _dec(row["cny_amount"])
        if row["card_id"]:
            owner_kind = "card"
            owner_name = " ".join(x for x in (row["brand"], row["model"]) if x) or None
            mgmt_no = row["card_mgmt_no"]
        elif row["device_id"]:
            owner_kind = "device"
            owner_name = row["device_title"]
            mgmt_no = row["device_mgmt_no"]
        else:
            owner_kind, owner_name, mgmt_no = None, None, None
        out.append({
            "id": row["id"],
            "card_id": row["card_id"],
            "device_id": row["device_id"],
            "owner_kind": owner_kind,
            "owner_name": owner_name,
            "mgmt_no": mgmt_no,
            "category": row["category"],
            "draw_date": _iso(row["draw_date"]),
            "amount": _float(amount),
            "currency": row["currency"],
            "contributor_id": row.get("contributor_id"),
            "contributor": people.name_of(row.get("contributor_id"), names),
            "note": row["note"],
            "cny_amount": _float(cny),
            "shortfall": _float(row["shortfall"]),
            "effective_rate": _float(cny / amount * _RATE_UNIT) if (cny and cny > 0 and amount > 0) else None,
            "allocations": alloc_map.get(int(row["id"]), []),
            "created_at": _iso(row["created_at"]),
        })
    return out


def card_draws(card_id: int) -> List[Dict[str, Any]]:
    return list_draws(card_id=card_id)


def device_draws(device_id: int) -> List[Dict[str, Any]]:
    return list_draws(device_id=device_id)


def summary() -> Dict[str, Any]:
    """池子的总账：进了多少、花了多少、还剩多少，以及剩余部分的人民币成本。

    「剩余的人民币成本」不是「剩余日元按今天的牌价折」，而是按各批次自己的汇率分别算
    再相加——池子里躺着的钱值多少，取决于它当初是用什么价换进来的。
    """
    injections = list_injections()
    total_in = sum(i["amount"] or 0 for i in injections)
    total_in_cny = sum(i["cny_cost"] or 0 for i in injections)
    # 平均换汇汇率只看真换过汇的批次：现金注资与出售回流用的都是当天牌价，算进来就
    # 不再是「换汇花了什么价」
    forex = [i for i in injections if i.get("inject_type") == "forex"]
    forex_in = sum(i["amount"] or 0 for i in forex)
    forex_in_cny = sum(i["cny_cost"] or 0 for i in forex)
    incomplete_injections = sum(
        1 for i in injections
        if i["fx_rate"] is None
    )
    remaining = sum(i["remaining_amount"] or 0 for i in injections)
    remaining_cny = sum(i["remaining_cny"] or 0 for i in injections)

    used_row = db.query_one(
        "SELECT COALESCE(SUM(amount), 0) AS jpy, COALESCE(SUM(cny_amount), 0) AS cny, "
        "COALESCE(SUM(shortfall), 0) AS shortfall, COUNT(*) AS n, "
        "SUM(CASE WHEN cny_amount IS NULL THEN 1 ELSE 0 END) AS broken FROM fund_draws"
    ) or {}
    used_jpy = _dec(used_row.get("jpy")) or _ZERO
    used_cny = _dec(used_row.get("cny")) or _ZERO
    # 欠款从余额里减掉：池子允许为负，负数就是「还差多少要补」（见 contributor_totals）
    owed = _float(used_row.get("shortfall")) or 0.0

    return {
        "currency": POOL_CURRENCY,
        "total_injected": round(total_in, 2),
        "total_injected_cny": round(total_in_cny, 2),
        "total_drawn": _float(used_jpy),
        "total_drawn_cny": _float(used_cny),
        "balance": round(remaining - owed, 2),
        "balance_cny": round(remaining_cny, 2),
        "shortfall": _float(used_row.get("shortfall")),
        "draw_count": int(used_row.get("n") or 0),
        "injection_count": len(injections),
        # 池子的平均换汇成本（只算外汇注资），与单批次同口径（100 日元 = ? 人民币）
        "avg_rate": round(forex_in_cny / forex_in * RATE_UNIT, 4) if forex_in else None,
        "used_rate": _float(used_cny / used_jpy * _RATE_UNIT) if (used_jpy > 0 and used_cny > 0) else None,
        "incomplete": bool(incomplete_injections or int(used_row.get("broken") or 0)),
        "incomplete_injections": incomplete_injections,
    }
