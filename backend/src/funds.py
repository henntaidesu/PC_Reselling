# -*- coding: utf-8 -*-
"""资金池：注资批次、扣款、FIFO 分摊与人民币成本换算。

**为什么需要它**：先换一笔日元放在日本的账户里，再陆续用这笔钱买卡——这时一张卡的
真实人民币成本，取决于「买它的钱是哪一批换进来的、当时换汇价多少」，而不是买卡那天
的市场牌价。同一天买的两张卡，如果吃的是不同批次的钱，成本就不一样。

**模型**（三张表）：

- ``fund_injections`` 注资批次：一次换汇进池一条，带自己那天的汇率快照。
- ``fund_draws`` 扣款：卡片与整机侧的「购入价 / 国际运费」跟着各自的金额自动同步
  （一卡一类一条 / 一机一类一条），另有手工记的池内杂项支出。**要先在详情页点过
  「确认扣除」**（``pool_confirmed_at`` 有值）才会生成——详情页边填边自动保存，
  没有这道闸门，购入价刚敲了两位数就已经从池里扣走一笔了。
- ``fund_allocations`` 分摊明细：一笔扣款按 FIFO 拆到若干批次上，每段带该批次的汇率。

**FIFO 与两条硬规则**：

1. 先进先出，按 ``inject_date`` 排序——最早换进来的钱先花掉。
2. 一笔扣款只能吃 ``inject_date <= draw_date`` 的批次：还没进池的钱花不出去。
   吃不满的部分记为 ``shortfall``（当时池内余额不够），按当日市场牌价折算并给出
   警告，而不是硬凑到后面的批次上——那会让成本凭空变好看。

**出资人（``fund_injections.contributor``）**：池子里的钱可能是几个人凑的。它只是注资上的
一个**归属标签**，不改变 FIFO——池子仍然是一个先进先出的队列，一笔扣款吃到谁的钱取决于
日期而不是人。这是刻意的：一张卡的人民币成本只取决于「吃掉的那几笔钱当初按什么价换的」，
按人分池会让同一天买的两张卡因为「记在谁头上」而成本不同，那是分账问题，不是成本问题。
谁出了多少、被用掉多少、还剩多少，全部由分摊结果反算（``contributor_totals()``）。

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

from src import db
# uses_pool 的定义只有 cards.py 那一份（「选了资金池 **且** 已确认扣除」）。
# 在这里照抄一遍条件的下场是某天只改了其中一处，成本按池子算、扣款却没同步。
from src.cards import compute_money as cards_compute_money
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
    """定这批钱的汇率：手填的实付人民币优先，否则按注资日取牌价。

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

def split_amount(total: Optional[Decimal], shares: List[Dict[str, Any]]) -> List[Tuple[str, Decimal]]:
    """按出资比例把一笔钱拆成几段。返回 ``[(出资人, 金额)]``。

    最后一段吃掉余数，而不是每段各自四舍五入——三个人各 1/3 分 100 日元，各自取整是
    33.33×3=99.99，池子里会凭空剩下一分钱，而且它会一直跟着后面每一笔扣款漂下去。

    比例之和不是 100 时按**实际之和**归一化。表单那头已经拦了（必须凑够 100），这里
    不重复报错：重算是个后台动作，为一条比例填错的旧数据整体算不下去，比按它本来的
    意思摊开更糟。
    """
    if total is None or not shares:
        return []
    weights = [(str(sh["contributor"]), _dec(sh.get("share_pct")) or _ZERO) for sh in shares]
    weight_sum = sum(w for _n, w in weights)
    if weight_sum <= 0:
        return []
    out: List[Tuple[str, Decimal]] = []
    taken = _ZERO
    for idx, (name, weight) in enumerate(weights):
        if idx == len(weights) - 1:
            part = total - taken
        else:
            part = _round(total * weight / weight_sum) or _ZERO
            taken += part
        out.append((name, part))
    return out


def allocate(
    injections: List[Dict[str, Any]],
    draws: List[Dict[str, Any]],
    market_rate: Any = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把每笔扣款按 FIFO 拆到注资批次上。

    ``injections`` 必须按 (inject_date, id) 升序，``draws`` 按 (draw_date, id) 升序——
    扣款也要按时间顺序处理，否则「谁先花掉了那批便宜的钱」会取决于录入顺序。

    **指定了出资人的扣款只在那几个人的批次里扣**：``draw["shares"]`` 里有比例时，先按
    比例把金额拆成几段，每段单独跑一遍 FIFO，候选批次只有该出资人的那些。没填 shares
    的扣款照旧在**全部**批次上跑一遍 FIFO——这是老数据的行为，也是「没说是谁的钱」的
    正确含义。两者混在一个池子里的后果要知道：一笔没指定出资人的旧扣款会按日期吃掉
    最早的批次，其中可能就有老李的钱；轮到一张指定老李的卡时，他名下可能已经不够了，
    那一段就记成余额不足。这不是算错——它恰好说明那笔旧扣款也该把出资人补上。

    ``market_rate`` 是个 ``(date) -> Decimal | None`` 的函数，用于折算池子不够的部分。

    返回 ``(分摊行, 每笔扣款的汇总)``。
    """
    remaining: Dict[int, Decimal] = {
        int(inj["id"]): (_dec(inj["amount"]) or _ZERO) for inj in injections
    }
    # 按出资人预先分好候选批次。每笔扣款现筛一遍的话是「几百笔 × 几十批」次比较，
    # 而且筛出来的顺序还得再保证一次；这里分一次，各桶天然继承了入参的日期升序。
    by_contributor: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for inj in injections:
        by_contributor.setdefault(inj.get("contributor") or None, []).append(inj)

    allocations: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []

    for draw in draws:
        total = _dec(draw["amount"]) or _ZERO
        draw_date = draw["draw_date"]
        shares = draw.get("shares") or []
        # 每段 = (在谁的批次里扣, 扣多少)。没指定出资人就是一段、候选是全池。
        parts = split_amount(total, shares) if shares else [(None, total)]

        seq = 0
        lines: List[Dict[str, Any]] = []
        cny_total: Optional[Decimal] = _ZERO
        jpy_converted = _ZERO
        shortfall = _ZERO

        for contributor, need in parts:
            candidates = by_contributor.get(contributor, []) if contributor else injections
            for inj in candidates:
                if need <= 0:
                    break
                # 候选已按日期升序：碰到晚于扣款日的批次，后面的只会更晚，直接收工
                if draw_date and inj["inject_date"] and inj["inject_date"] > draw_date:
                    break
                available = remaining.get(int(inj["id"]), _ZERO)
                if available <= 0:
                    continue
                take = available if available < need else need
                rate = _dec(inj.get("fx_rate"))
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
            # 各段的缺口都发生在同一天，市场牌价只需取一次
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


# ── 出资人字典 ──────────────────────────────────────────────────────────── #

def contributor_names() -> List[str]:
    """字典里的全部出资人。注资下拉、显卡 / 整机的出资比例下拉共用这一份候选。"""
    return [r["name"] for r in db.query(
        "SELECT name FROM fund_contributors ORDER BY sort_order, name")]


def ensure_contributor(name: Optional[str]) -> Optional[str]:
    """把填进来的出资人名字落进字典，返回字典里的那一份写法。

    下拉都是 allow-create 的——录注资、或在显卡详情页分比例时现敲一个新名字就该能存
    下去，而不是先跑一趟别处把人建好。所以这里做 upsert：字典里没有就加一条，有就用
    **字典里的那个写法**回填，让 "小王 " 和 "小王" 归到同一个人。按出资人汇总是按名字
    分组的，两种写法会被算成两个人，而页面上看起来一模一样。

    与品牌 / 购买平台一样，注资行和出资比例上存的都是名字不是外键：字典只是候选清单，
    日后从清单里拿掉某个人也不该动到历史账目。
    """
    name = (name or "").strip()
    if not name:
        return None
    existing = db.query_one("SELECT name FROM fund_contributors WHERE name = %s", (name,))
    if existing:
        return existing["name"]
    sort_order = int(db.query_scalar(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM fund_contributors", default=0) or 0)
    db.insert(
        "INSERT INTO fund_contributors (name, sort_order) VALUES (%s, %s)", (name, sort_order))
    return name


# ── 出资比例（一件货的钱由谁出）─────────────────────────────────────────── #

def load_shares(kind: str, owner_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """一次 IN 查询取回多件货的出资比例，按归属 id 分好组。

    列表页和重算都要按批取（一次 rebuild 会碰到全部扣款），一件一查就是 N+1。
    """
    if not owner_ids:
        return {}
    col, _table = _OWNERS[kind]
    placeholders = ", ".join(["%s"] * len(owner_ids))
    rows = db.query(
        f"SELECT {col} AS owner_id, contributor, share_pct FROM fund_shares "
        f"WHERE {col} IN ({placeholders}) ORDER BY id",
        list(owner_ids),
    )
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["owner_id"]), []).append({
            "contributor": row["contributor"],
            "share_pct": _float(row["share_pct"]),
        })
    return grouped


def owner_shares(kind: str, owner_id: int) -> List[Dict[str, Any]]:
    return load_shares(kind, [owner_id]).get(owner_id, [])


def write_shares(kind: str, owner_id: int, shares: Optional[List[Dict[str, Any]]]) -> bool:
    """整体替换一件货的出资比例，返回是否真的变了。

    这里**可以**先删后插——与整机部件相反：没有任何东西挂在一行 share 上（部件上挂着
    图片，行 id 一换图就被外键级联删了），比例本身就是一组数。

    「真的变了才写」不是省事：详情页改一个字段就 PUT 一次，每次都删掉重插会让
    ``updated_at`` 一直跳，更要紧的是每次都触发一遍全量重算。
    """
    col, _table = _OWNERS[kind]
    wanted = []
    for sh in (shares or []):
        name = (sh.get("contributor") or "").strip()
        pct = _dec(sh.get("share_pct"))
        if not name or pct is None or pct <= 0:
            continue
        wanted.append((name, pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)))

    existing = [
        (r["contributor"], (_dec(r["share_pct"]) or _ZERO).quantize(Decimal("0.0001")))
        for r in db.query(
            f"SELECT contributor, share_pct FROM fund_shares WHERE {col} = %s ORDER BY id",
            (owner_id,),
        )
    ]
    if existing == wanted:
        return False

    with db.transaction() as cur:
        cur.execute(f"DELETE FROM fund_shares WHERE {col} = %s", (owner_id,))
        if wanted:
            cur.executemany(
                f"INSERT INTO fund_shares ({col}, contributor, share_pct) VALUES (%s, %s, %s)",
                [(owner_id, name, pct) for name, pct in wanted],
            )
    return True


def _draw_share_lookup(draws: List[Dict[str, Any]]) -> None:
    """给每笔扣款挂上它那件货的出资比例（原地改 ``draw["shares"]``）。

    比例存在货上而不是扣款上，所以这里要绕一道：购入价和国际运费是同一件货的两笔扣款，
    自然共用同一个比例。手工记的池内支出两列都为空，永远没有 shares——它不属于任何
    一件货，也就谈不上由谁出。
    """
    for kind, (col, _table) in _OWNERS.items():
        ids = sorted({int(d[col]) for d in draws if d.get(col)})
        shares = load_shares(kind, ids)
        for draw in draws:
            if draw.get(col):
                draw["shares"] = shares.get(int(draw[col]), [])


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
        "SELECT id, inject_date, amount, fx_rate, contributor FROM fund_injections "
        "ORDER BY inject_date, id"
    )
    draws = db.query(
        "SELECT id, card_id, device_id, category, draw_date, amount FROM fund_draws "
        "ORDER BY draw_date, id"
    )
    # 扣款要在谁的钱里扣，取决于它那件货上的出资比例
    _draw_share_lookup(draws)
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
        warnings.append(f"有 {len(short)} 笔扣款超出了当时的池内余额，超出部分按当日市场牌价折算")
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

    ``uses_pool`` 里含「已确认扣除」这一条，所以确认之前 wanted 是空的，这里正好把
    可能残留的扣款删干净——撤销扣除也就不必另写一套删除逻辑，置回 NULL 再同步即可。
    """
    col, table = _OWNERS[kind]
    row = row or db.query_one(f"SELECT * FROM {table} WHERE id = %s", (owner_id,))
    if not row:
        return False
    draw_date = row.get("purchase_date") or dt.date.today()
    wanted = poolable_amounts(row) if uses_pool(row) else {}

    existing = {
        r["category"]: r for r in db.query(
            f"SELECT id, category, draw_date, amount FROM fund_draws WHERE {col} = %s",
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
                f"INSERT INTO fund_draws ({col}, category, draw_date, amount, currency) "
                f"VALUES (%s, %s, %s, %s, %s)",
                (owner_id, category, draw_date, want, POOL_CURRENCY),
            )
            changed = True
        elif _dec(have["amount"]) != want or have["draw_date"] != draw_date:
            db.execute(
                "UPDATE fund_draws SET draw_date = %s, amount = %s WHERE id = %s",
                (draw_date, want, have["id"]),
            )
            changed = True

    return changed


def set_confirmed(kind: str, owner_id: int, confirmed: bool) -> Dict[str, Any]:
    """点「确认扣除」/「撤销扣除」：只动确认标记，扣款行照旧由同步派生出来。

    这里**不吞异常**（与自动保存路径的 ``sync_and_rebuild`` 相反）：那边是防抖自动触发的，
    算不动池子不该让保存失败；这里是用户按了一个按钮，失败了必须说出来，
    否则表现成「点了没反应，钱也没动」。

    返回归属行最新的那一份，省得调用方再查一遍。
    """
    col, table = _OWNERS[kind]
    row = db.query_one(f"SELECT * FROM {table} WHERE id = %s", (owner_id,))
    if not row:
        raise LookupError("记录不存在")
    if confirmed:
        if (row.get("fund_source") or "own") != "pool":
            raise ValueError("资金来源不是「从资金池扣除」")
        if not poolable_amounts(row):
            # 选了池子却没有日元金额（金额空着、或填的是人民币）：确认下去也扣不出东西，
            # 与其静悄悄地记一个没有扣款的确认，不如当场说清楚
            raise ValueError("没有可从资金池扣除的日元金额")

    db.execute(
        f"UPDATE {table} SET pool_confirmed_at = %s WHERE id = %s",
        (dt.datetime.now() if confirmed else None, owner_id),
    )
    if sync_owner_draws(kind, owner_id):
        rebuild()
    return db.query_one(f"SELECT * FROM {table} WHERE id = %s", (owner_id,))


def sync_and_rebuild(
    kind: str, owner_id: int, row: Optional[Dict[str, Any]] = None, force: bool = False
) -> None:
    """存卡 / 存整机后调用：同步扣款，真的有变化时才重算。

    「有变化才重算」不只是省事——保存是防抖自动触发的（改一个字段就是一次 PUT），
    每次都全量重算会把大量无谓的写打到库上。

    ``force`` 给「扣款金额没动、但池子的账会变」的情形用，目前就是出资比例改了
    （``write_shares`` 返回 True）：钱数一分没变，但它该从谁的批次里扣变了。
    """
    try:
        if sync_owner_draws(kind, owner_id, row) or force:
            rebuild()
    except Exception as exc:  # noqa: BLE001  资金池算不动不该让保存失败
        log.warning("同步%s %s 的资金池扣款失败：%s", kind, owner_id, exc)


def sync_card_draws(card_id: int, row: Optional[Dict[str, Any]] = None) -> bool:
    return sync_owner_draws("card", card_id, row)


def sync_card_and_rebuild(
    card_id: int, row: Optional[Dict[str, Any]] = None, force: bool = False
) -> None:
    sync_and_rebuild("card", card_id, row, force)


def sync_device_and_rebuild(
    device_id: int, row: Optional[Dict[str, Any]] = None, force: bool = False
) -> None:
    sync_and_rebuild("device", device_id, row, force)


# ── 查询 ────────────────────────────────────────────────────────────────── #

def list_injections() -> List[Dict[str, Any]]:
    """注资列表，带每批的已用 / 剩余。已用量从分摊明细汇总，池子的账永远自洽。"""
    rows = db.query(
        "SELECT i.*, COALESCE(SUM(a.amount), 0) AS used_amount, "
        "       COALESCE(SUM(a.cny_amount), 0) AS used_cny "
        "FROM fund_injections i LEFT JOIN fund_allocations a ON a.injection_id = i.id "
        "GROUP BY i.id ORDER BY i.inject_date DESC, i.id DESC"
    )
    out = []
    for row in rows:
        amount = _dec(row["amount"]) or _ZERO
        used = _dec(row["used_amount"]) or _ZERO
        rate = _dec(row["fx_rate"])
        out.append({
            "id": row["id"],
            "inject_date": _iso(row["inject_date"]),
            "amount": _float(amount),
            "currency": row["currency"],
            "fx_rate": _float(rate),
            "fx_date": _iso(row["fx_date"]),
            "fx_manual": bool(row["fx_manual"]),
            "contributor": row.get("contributor") or None,
            "channel": row["channel"],
            "note": row["note"],
            "cny_cost": _float(_to_cny(amount, rate)),
            "used_amount": _float(used),
            "used_cny": _float(row["used_cny"]),
            "remaining_amount": _float(amount - used),
            "remaining_cny": _float(_to_cny(amount - used, rate)),
            "created_at": _iso(row["created_at"]),
        })
    return out


def split_dividends(
    shares: List[Dict[str, Any]], money: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """把一件货的成本与盈亏按出资比例分给各出资人。

    分红口径：**利润全额按出资比例分**，操作人不另外抽成。所以这里就是一次按比例的
    等分，没有第二条规则——真要加「运营分成」，加在这一个函数里，别在页面上各算各的。

    利润算不出来（缺汇率、还没卖）时每个人的分红都是 ``None``，不按 0 分：
    与全系统同一条规矩，把缺失当零会分出一笔看着正常、实际不存在的钱。
    """
    if not shares:
        return []
    profit = _dec(money.get("profit_cny"))
    cost = _dec(money.get("cost_total_cny"))
    # 还没有任何收入的货，利润栏是「-成本」或空，那不是亏损而是没卖——分红留空，
    # 占用的本金另算一档（见 contributor_totals 的 stock_cost_cny）
    has_revenue = money.get("sale_cny") is not None
    total_pct = sum(_dec(sh.get("share_pct")) or _ZERO for sh in shares) or _ZERO

    out = []
    for sh in shares:
        pct = _dec(sh.get("share_pct")) or _ZERO
        weight = (pct / total_pct) if total_pct > 0 else _ZERO
        out.append({
            "contributor": sh["contributor"],
            "share_pct": _float(pct),
            "cost_cny": _float(_round(cost * weight)) if cost is not None else None,
            "dividend_cny": (
                _float(_round(profit * weight))
                if (profit is not None and has_revenue) else None
            ),
        })
    return out


def _owner_money() -> List[Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
    """所有带出资比例的货，连同它各自那份钱的计算结果。

    利润用的就是显卡 / 整机详情页上那个数（``cards.compute_money`` /
    ``devices.compute_money``），不在这里另算一份——两份口径迟早会分叉，而分红对不上
    详情页的利润，没人会相信哪一个。
    """
    from src import devices  # 局部 import：devices 只在这一处用到，放模块顶端会多一条
                             # 「funds 依赖 devices」的关系，而它们在别处并不互相依赖
    out: List[Tuple[List[Dict[str, Any]], Dict[str, Any]]] = []

    card_shares = _all_shares("card")
    if card_shares:
        ids = list(card_shares)
        placeholders = ", ".join(["%s"] * len(ids))
        for row in db.query(f"SELECT * FROM cards WHERE id IN ({placeholders})", ids):
            out.append((card_shares[int(row["id"])], cards_compute_money(row)))

    device_shares = _all_shares("device")
    if device_shares:
        ids = list(device_shares)
        placeholders = ", ".join(["%s"] * len(ids))
        rows = db.query(f"SELECT * FROM devices WHERE id IN ({placeholders})", ids)
        parts = devices.load_parts(ids)
        for row in rows:
            money = devices.compute_money(row, parts.get(int(row["id"]), []))
            out.append((device_shares[int(row["id"])], money))
    return out


def _all_shares(kind: str) -> Dict[int, List[Dict[str, Any]]]:
    """某一类归属方上全部的出资比例，按 id 分组。

    只算**当前还走资金池**的那些货。比例行本身不会因为改回「自有资金」就被删掉
    （改回去再改回来不该丢掉填过的比例），但那时候这件货的钱不是从池里出的，
    再按比例分红就是凭空给人记一笔——所以在这里把它们滤掉，而不是删数据。
    """
    col, table = _OWNERS[kind]
    rows = db.query(
        f"SELECT s.{col} AS owner_id, s.contributor, s.share_pct FROM fund_shares s "
        f"JOIN {table} o ON o.id = s.{col} "
        f"WHERE s.{col} IS NOT NULL AND o.fund_source = 'pool' ORDER BY s.id"
    )
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["owner_id"]), []).append({
            "contributor": row["contributor"],
            "share_pct": _float(row["share_pct"]),
        })
    return grouped


def _bucket(buckets: Dict[Any, Dict[str, Any]], name: Optional[str]) -> Dict[str, Any]:
    """取（或新建）某个出资人的汇总档。

    出资人可能只出现在其中一头：注过资但还没买过货，或者货上写了他、名下却一笔注资
    都没有（那种情况下他那段扣款会全部记成余额不足）。两头都用这一个入口建档，
    就不会有人因为「只在另一张表里出现过」而从汇总里消失。
    """
    return buckets.setdefault(name, {
        "name": name,
        "injection_count": 0,
        "injected": 0.0, "injected_cny": 0.0,
        "used": 0.0, "used_cny": 0.0,
        "remaining": 0.0, "remaining_cny": 0.0,
        "dividend_cny": 0.0, "stock_cost_cny": 0.0,
        "incomplete": False, "pnl_incomplete": False,
    })


def contributor_totals() -> List[Dict[str, Any]]:
    """按出资人汇总：谁投了多少、被花掉多少、还剩多少。

    全部由注资行反算，没有另一张「账户表」。理由和分摊一样——余额只要有第二个地方
    存着，就一定会有对不上的那天；这里的数据量（几十条注资）现算一遍不值一提。

    ``used_*`` 来自 ``list_injections()`` 里已经汇总好的分摊量，所以「谁的钱被花了多少」
    与扣款明细天然一致：FIFO 按日期吃钱，吃到谁头上就算在谁头上。

    没填出资人的注资归到 ``name = None`` 这一档（前端显示「未指定」），不合并进任何人——
    旧数据和自己出的钱都落在这里，硬塞给某个人等于凭空改账。

    人民币合计沿用 ``summary()`` 的口径：缺汇率的批次按 0 计入并置 ``incomplete``，
    由前端打标提示，而不是让整个人的合计变成「—」——那样一批缺汇率会把这个人
    另外十批已经算清楚的钱也一起藏掉。

    另外两档来自货那边（见 ``_owner_money``）：``dividend_cny`` 是已经卖出去的那些货
    按比例分到的盈亏，``stock_cost_cny`` 是还压在没卖的货上的本金。**分开两档是必须的**：
    合成一个数的话，一台刚买回来还没拆卖的整机会以「亏了一整台的钱」的形式记进分红，
    而它其实只是还没卖。
    """
    rows = list_injections()
    total_in = sum(r["amount"] or 0 for r in rows)
    buckets: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        name = row["contributor"]
        b = _bucket(buckets, name)
        b["injection_count"] += 1
        b["injected"] += row["amount"] or 0
        b["injected_cny"] += row["cny_cost"] or 0
        b["used"] += row["used_amount"] or 0
        b["used_cny"] += row["used_cny"] or 0
        b["remaining"] += row["remaining_amount"] or 0
        b["remaining_cny"] += row["remaining_cny"] or 0
        if row["fx_rate"] is None:
            b["incomplete"] = True

    # 货那边：卖掉的按比例分盈亏，没卖的按比例记在库本金
    for shares, money in _owner_money():
        has_revenue = money.get("sale_cny") is not None
        for line in split_dividends(shares, money):
            b = _bucket(buckets, line["contributor"])
            if has_revenue:
                if line["dividend_cny"] is None:
                    b["pnl_incomplete"] = True
                else:
                    b["dividend_cny"] += line["dividend_cny"]
            elif line["cost_cny"] is None:
                b["pnl_incomplete"] = True
            else:
                b["stock_cost_cny"] += line["cost_cny"]

    out = []
    for b in buckets.values():
        for key in ("dividend_cny", "stock_cost_cny"):
            b[key] = round(b[key], 2)
        for key in ("injected", "injected_cny", "used", "used_cny", "remaining", "remaining_cny"):
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
    out.sort(key=lambda x: (x["name"] is None, -(x["injected"] or 0), x["name"] or ""))
    return out


def _draw_allocations(draw_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    if not draw_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(draw_ids))
    rows = db.query(
        f"SELECT a.*, i.inject_date, i.contributor FROM fund_allocations a "
        f"JOIN fund_injections i ON i.id = a.injection_id "
        f"WHERE a.draw_id IN ({placeholders}) ORDER BY a.draw_id, a.seq",
        draw_ids,
    )
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["draw_id"]), []).append({
            "injection_id": row["injection_id"],
            "inject_date": _iso(row["inject_date"]),
            "contributor": row.get("contributor") or None,
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
    alloc_map = _draw_allocations([int(r["id"]) for r in rows])
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
    incomplete_injections = sum(1 for i in injections if i["fx_rate"] is None)
    remaining = sum(i["remaining_amount"] or 0 for i in injections)
    remaining_cny = sum(i["remaining_cny"] or 0 for i in injections)

    used_row = db.query_one(
        "SELECT COALESCE(SUM(amount), 0) AS jpy, COALESCE(SUM(cny_amount), 0) AS cny, "
        "COALESCE(SUM(shortfall), 0) AS shortfall, COUNT(*) AS n, "
        "SUM(CASE WHEN cny_amount IS NULL THEN 1 ELSE 0 END) AS broken FROM fund_draws"
    ) or {}
    used_jpy = _dec(used_row.get("jpy")) or _ZERO
    used_cny = _dec(used_row.get("cny")) or _ZERO

    return {
        "currency": POOL_CURRENCY,
        "total_injected": round(total_in, 2),
        "total_injected_cny": round(total_in_cny, 2),
        "total_drawn": _float(used_jpy),
        "total_drawn_cny": _float(used_cny),
        "balance": round(remaining, 2),
        "balance_cny": round(remaining_cny, 2),
        "shortfall": _float(used_row.get("shortfall")),
        "draw_count": int(used_row.get("n") or 0),
        "injection_count": len(injections),
        # 池子的平均换汇成本，与单批次同口径（100 日元 = ? 人民币）。缺汇率的批次没算进
        # 人民币，所以只有全部批次都有汇率时这个数才准，前端用 incomplete 标记提示。
        "avg_rate": round(total_in_cny / total_in * RATE_UNIT, 4) if total_in else None,
        "used_rate": _float(used_cny / used_jpy * _RATE_UNIT) if (used_jpy > 0 and used_cny > 0) else None,
        "incomplete": bool(incomplete_injections or int(used_row.get("broken") or 0)),
        "incomplete_injections": incomplete_injections,
    }
