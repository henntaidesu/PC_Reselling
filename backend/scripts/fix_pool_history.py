# -*- coding: utf-8 -*-
"""修历史数据：让走资金池的货按池子的真实换汇价算成本。

**为什么会有历史数据要修**：出资比例（``fund_shares``）是后加的功能。在那之前确认扣除的
货没有比例，FIFO 就在全池上跑，按日期吃掉最早的批次——不管那批钱是谁的。等后来一件货
写明「由某某 100% 出资」，那个人名下的钱可能早被那笔旧扣款吃光了，于是整笔记成
shortfall，按购入日的**市场牌价**折算。页面上看到的就是「明明从池里扣的，成本却和牌价
一模一样」。这正是 funds.allocate 的 docstring 里说的「那笔旧扣款也该补上出资人」。

这个脚本做四件事：

1. **体检**：列出所有已确认扣除的货、它的出资比例、扣款的 shortfall，以及池子里
   「没写出资人、却在吃别人钱」的旧扣款。
2. **补比例**（``--share 管理编号=出资人[:比例],...``）：给没写比例的旧货补上。
3. **补现金注资的汇率**：现金注资原先记作零成本、汇率为空，现在按注资日牌价记，
   存量的那几笔在 ``--apply`` 时补上。
4. **重算**：``funds.rebuild()`` 全量重算，前后对比每件货的池成本与加权汇率。

默认只预览：在内存里拿补好的比例跑一遍 ``funds.allocate``，打印前后对比，**不写库**。
确认无误后加 ``--apply`` 才落盘。比例是按「件」写的，同一件货的购入价与国际运费共用。

用法（在 backend 目录下，PC_Reselling 环境里）::

    python scripts/fix_pool_history.py                              # 只体检
    python scripts/fix_pool_history.py --share DEV-2026-0004=甘      # 预览补比例后的结果
    python scripts/fix_pool_history.py --share DEV-2026-0004=甘 --apply
    python scripts/fix_pool_history.py --share GPU-2026-0001=甘:60,宁:40 --apply
    python scripts/fix_pool_history.py --rebuild --apply            # 不补比例，只全量重算一次
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# Windows 控制台默认 GBK，出资人名字是中文，直接 print 会变成乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
os.chdir(_BACKEND)  # conf.ini 按工作目录找

from src import db, funds  # noqa: E402

_KINDS = {"card": "cards", "device": "devices"}


def _owner_rows() -> Dict[Tuple[str, int], Dict[str, Any]]:
    """全部「选了资金池」的卡与整机，按 (kind, id) 索引。"""
    out: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for kind, table in _KINDS.items():
        for row in db.query(
            f"SELECT id, mgmt_no, purchase_date, purchase_amount, purchase_currency, "
            f"purchase_fx_rate, fund_source, pool_confirmed_at, pool_purchase_cny, "
            f"pool_intl_cny, pool_fx_rate FROM {table} WHERE fund_source = 'pool'"
        ):
            out[(kind, int(row["id"]))] = row
    return out


def _find_owner(mgmt_no: str) -> Tuple[str, int]:
    for kind, table in _KINDS.items():
        row = db.query_one(f"SELECT id FROM {table} WHERE mgmt_no = %s", (mgmt_no,))
        if row:
            return kind, int(row["id"])
    raise SystemExit(f"找不到管理编号 {mgmt_no}")


def _parse_shares(specs: List[str]) -> Dict[Tuple[str, int], List[Dict[str, Any]]]:
    """``DEV-2026-0004=甘`` / ``GPU-2026-0001=甘:60,宁:40`` → {(kind, id): [比例]}。"""
    known = set(funds.contributor_names())
    out: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"--share 格式不对：{spec}（应为 管理编号=出资人[:比例],...）")
        mgmt_no, rhs = spec.split("=", 1)
        items = [p.strip() for p in rhs.split(",") if p.strip()]
        shares = []
        for item in items:
            name, _, pct = item.partition(":")
            name = name.strip()
            if name not in known:
                raise SystemExit(f"出资人「{name}」不在字典里（现有：{'、'.join(sorted(known))}）")
            shares.append({"contributor": name,
                           "share_pct": Decimal(pct) if pct else Decimal(100) / len(items)})
        total = sum(s["share_pct"] for s in shares)
        if abs(total - 100) > Decimal("0.01"):
            raise SystemExit(f"{mgmt_no} 的比例合计是 {total}，不是 100")
        out[_find_owner(mgmt_no.strip())] = shares
    return out


def _simulate(overrides: Dict[Tuple[str, int], List[Dict[str, Any]]]) -> Dict[Tuple[str, int], Dict[str, Any]]:
    """用补好的比例在内存里跑一遍 FIFO，算出每件货的池成本 / 加权汇率 / 缺口。

    与 funds.rebuild() 走同一个 allocate，只是不写库——预览和落盘的结果必须一致。
    """
    injections = db.query(
        "SELECT id, inject_date, amount, fx_rate, contributor FROM fund_injections "
        "ORDER BY inject_date, id")
    draws = db.query(
        "SELECT id, card_id, device_id, category, draw_date, amount, contributor "
        "FROM fund_draws ORDER BY draw_date, id")
    funds._draw_share_lookup(draws)
    for draw in draws:
        for kind, (col, _t) in funds._OWNERS.items():
            if draw.get(col) and (kind, int(draw[col])) in overrides:
                draw["shares"] = overrides[(kind, int(draw[col]))]
    _allocs, results = funds.allocate(injections, draws, funds._market_rate_lookup())

    out: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for res in results:
        draw = res["draw"]
        owner = next(((k, int(draw[c])) for k, (c, _t) in funds._OWNERS.items() if draw.get(c)), None)
        if owner is None or draw["category"] not in funds._CARD_CATEGORIES:
            continue
        b = out.setdefault(owner, {"cny": Decimal(0), "jpy": Decimal(0), "short": Decimal(0), "broken": False})
        b["short"] += res["shortfall"]
        if res["cny_amount"] is None:
            b["broken"] = True
        else:
            b["cny"] += res["cny_amount"]
            b["jpy"] += Decimal(str(draw["amount"]))
    for b in out.values():
        b["rate"] = (b["cny"] / b["jpy"] * funds._RATE_UNIT) if not b["broken"] and b["jpy"] else None
    return out


def _cash_without_rate() -> List[Dict[str, Any]]:
    """现金注资原先按「无人民币成本」记，fx_rate 是空的。现在改成按注资日牌价记，
    存量的这些要补上一个汇率，否则吃到它们的货会显示成「缺汇率」。"""
    return db.query("SELECT id, inject_date, amount, contributor FROM fund_injections "
                    "WHERE inject_type = 'cash' AND fx_rate IS NULL ORDER BY inject_date, id")


def _fill_cash_rates(rows: List[Dict[str, Any]]) -> None:
    for inj in rows:
        fx = funds.resolve_injection_fx(inj["inject_date"])
        if fx["fx_rate"] is None:
            print(f"  ⚠ 现金注资 #{inj['id']} 取不到牌价：{'；'.join(fx['warnings'])}")
            continue
        db.execute("UPDATE fund_injections SET fx_rate = %s, fx_date = %s, fx_manual = 0 WHERE id = %s",
                   (fx["fx_rate"], fx["fx_date"], inj["id"]))
        print(f"  现金注资 #{inj['id']} {inj['inject_date']} 补汇率 {_fmt(fx['fx_rate'], 4)}"
              f"（{fx['fx_date']}）")


def _fmt(value: Any, nd: int = 2) -> str:
    return "—" if value is None else f"{Decimal(str(value)):,.{nd}f}"


def _report(owners, shares, draws_short, sim) -> None:
    print("\n已确认扣除的货（池成本 / 加权汇率 —— 预览值，当日牌价供对照）")
    print(f"{'编号':<15}{'出资比例':<14}{'当前成本':>12}{'当前汇率':>10}  →  "
          f"{'预览成本':>12}{'预览汇率':>10}{'牌价':>9}  缺口(日元)")
    for key, row in sorted(owners.items(), key=lambda kv: (kv[1]["purchase_date"] or "", kv[1]["mgmt_no"])):
        if row["pool_confirmed_at"] is None:
            continue
        cur_cny = (row["pool_purchase_cny"] or 0) + (row["pool_intl_cny"] or 0)
        s = sim.get(key, {})
        share_txt = "、".join(f"{x['contributor']}{float(x['share_pct']):g}%" for x in shares.get(key, [])) or "（未写）"
        flag = "  ⚠ 吃别人的钱" if not shares.get(key) else ""
        short = s.get("short") or 0
        print(f"{row['mgmt_no']:<15}{share_txt:<14}{_fmt(cur_cny):>12}{_fmt(row['pool_fx_rate'], 4):>10}  →  "
              f"{_fmt(s.get('cny')):>12}{_fmt(s.get('rate'), 4):>10}{_fmt(row['purchase_fx_rate'], 4):>9}  "
              f"{_fmt(short, 0) if short else ''}{' ⚠ 余额不足按牌价' if short else ''}{flag}")
    if draws_short:
        print("\n当前库里有 shortfall 的扣款（这部分按市场牌价折算，没用上池子的汇率）：")
        for d in draws_short:
            print(f"  扣款 #{d['id']}  {d['draw_date']}  {_fmt(d['amount'], 0)} 日元，缺口 {_fmt(d['shortfall'], 0)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="修资金池历史数据（默认只预览）")
    ap.add_argument("--share", action="append", default=[],
                    help="给旧货补出资比例：管理编号=出资人[:比例],...，可写多次")
    ap.add_argument("--rebuild", action="store_true", help="不补比例也全量重算一次")
    ap.add_argument("--apply", action="store_true", help="真的写库（否则只预览）")
    args = ap.parse_args()

    overrides = _parse_shares(args.share)
    owners = _owner_rows()
    current = {}
    for kind in _KINDS:
        ids = [oid for (k, oid) in owners if k == kind]
        for oid, rows in funds.load_shares(kind, ids).items():
            if rows:
                current[(kind, oid)] = rows
    for key, sh in overrides.items():
        if key not in owners:
            print(f"注意：{key} 不是「从资金池扣除」的货，补比例不会影响池子")
        elif current.get(key):
            print(f"注意：{owners[key]['mgmt_no']} 已有比例，将被覆盖")
    shares = {**current, **overrides}

    print("出资人批次：")
    for inj in db.query("SELECT id, inject_date, amount, fx_rate, fx_manual, contributor "
                        "FROM fund_injections ORDER BY inject_date, id"):
        print(f"  #{inj['id']:<3} {inj['inject_date']}  {inj['contributor'] or '（无）':<4}"
              f"{_fmt(inj['amount'], 0):>12} 日元 @ {_fmt(inj['fx_rate'], 4)}"
              f"{'' if inj['fx_manual'] else '  ← 按注资日牌价取的，不是实付'}")

    draws_short = db.query("SELECT id, draw_date, amount, shortfall FROM fund_draws "
                           "WHERE shortfall > 0 ORDER BY draw_date, id")
    _report(owners, shares, draws_short, _simulate(overrides))

    cash = _cash_without_rate()
    if cash:
        print(f"\n有 {len(cash)} 笔现金注资还没有汇率（旧规则下按 0 成本记），--apply 时按注资日牌价补上：")
        for inj in cash:
            print(f"  #{inj['id']}  {inj['inject_date']}  {inj['contributor'] or '（无）'}  {_fmt(inj['amount'], 0)} 日元")
        print("  （上面的预览成本里，吃到这几笔的货还是按缺汇率算的）")

    if not args.apply:
        print("\n以上是预览，没有写库。确认无误后加 --apply。")
        return
    if not overrides and not args.rebuild and not cash:
        print("\n没有 --share、--rebuild，也没有要补汇率的现金注资，无事可做。")
        return

    _fill_cash_rates(cash)
    # 与 *_api 的写路径一致：写比例 → 强制重算（比例只改「扣谁的钱」，金额没动，
    # sync_owner_draws 察觉不到，必须 force）
    for (kind, oid), sh in overrides.items():
        funds.write_shares(kind, oid, sh)
    result = funds.rebuild()
    print(f"\n已写库并重算：{result['draws']} 笔扣款、{result['allocations']} 段分摊、"
          f"{result['owners']} 件货。")
    for w in result["warnings"]:
        print("  ⚠", w)


if __name__ == "__main__":
    main()
