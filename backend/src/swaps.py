# -*- coding: utf-8 -*-
"""实物置换：一张单卡 ↔ 某台整机里的一个显卡部件。

典型场景：甘的整机里有一块 5090，单手上有一张 5090 单卡，两人把卡换了。换完之后
**整机里装的是原来单的那张卡，单手上的是原来整机里那张**。

**换的是实物，不是账**。两条记录各自的购入价、售价、资金池扣款、出资比例、归属人、
状态全部原地不动——整机仍是那一笔总价买回来的整机，单卡仍是那一笔价买回来的单卡，
只是「这一行指的是哪一张物理的卡」变了。所以跟着走的只有描述那张卡本身的东西：

| 显卡（cards） | 部件（device_parts） | 说明                                   |
|---------------|----------------------|----------------------------------------|
| brand         | brand                |                                        |
| model         | model                |                                        |
| core_no       | spec                 | 显卡部件的「规格」一栏就是核心编号      |
| serial_no     | serial_no            |                                        |
| card_media    | device_part_media    | 照片拍的是那张卡，卡走了照片也得跟着走 |

为什么不做成「部件移出整机变成一张新单卡、单卡塞进整机变成部件」：那等于改账——
整机的总价里有一部分凭什么跟着部件走、走多少，没有一个不拍脑袋的答案（理由同
devices 模块文档里「成本不往部件上分摊」）。互换实物信息则一分钱都不用重新算，
资金池也就不必重算。

图片的两种形态不对称：显卡分五类，部件平铺一组。显卡的图搬到部件上时把原分类记在
``device_part_media.category`` 上，再换回显卡时归位；部件自己传的图没有分类，
搬到显卡上一律落进「外观」。

置换前两边的实物信息快照进 ``item_swaps``，互换之后行上的值已经是对方的了，
不留快照就说不清「原来那张是什么」。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Dict, List, Optional

from src import cards, db
from src.cards import _iso
from src.schema import MEDIA_CATEGORIES

log = logging.getLogger(__name__)

# 互换的字段：(cards 列, device_parts 列)。顺序即快照里的顺序。
SWAP_FIELDS = [
    ("brand", "brand"),
    ("model", "model"),
    ("core_no", "spec"),
    ("serial_no", "serial_no"),
]

# 只有显卡部件能和单卡互换：一条内存和一张显卡之间没有「换了一下」这回事。
SWAPPABLE_PART_TYPE = "gpu"

# 部件自己传的图没有分类，搬到显卡上落进这一类
_DEFAULT_CATEGORY = MEDIA_CATEGORIES[0]
_CATEGORY_ORDER = {name: i for i, name in enumerate(MEDIA_CATEGORIES)}

_MEDIA_COLS = "kind, stored_name, public_url, filename, mime_type, size_bytes, created_at"


class SwapError(ValueError):
    """不能置换（已卖出、不是显卡部件、草稿……）。消息直接给用户看。"""


# ── 资格 ────────────────────────────────────────────────────────────────── #

def _card_sold(row: Dict[str, Any]) -> bool:
    return row["status"] in cards.SOLD_STATUSES or row.get("sale_amount") is not None


def _part_sold(row: Dict[str, Any]) -> bool:
    return row["status"] in cards.SOLD_STATUSES or row.get("sale_amount") is not None


def _load_card(card_id: int) -> Dict[str, Any]:
    row = db.query_one("SELECT * FROM cards WHERE id = %s", (card_id,))
    if not row:
        raise LookupError("显卡不存在")
    return row


def _load_part(part_id: int) -> Dict[str, Any]:
    """部件连同它所属整机的几列一起取：资格判断与归属人回退都要用到整机。"""
    row = db.query_one(
        "SELECT p.*, d.mgmt_no AS device_mgmt_no, d.title AS device_title, "
        "d.owner AS device_owner, d.is_draft AS device_is_draft "
        "FROM device_parts p JOIN devices d ON d.id = p.device_id WHERE p.id = %s",
        (part_id,),
    )
    if not row:
        raise LookupError("部件不存在")
    return row


def _check_card(row: Dict[str, Any]) -> None:
    # 已经卖出去的卡在买家手里，不可能再拿来换；草稿则是还没录完的空卡
    if row.get("is_draft"):
        raise SwapError("这张显卡还是草稿，先录入信息再置换")
    if _card_sold(row):
        raise SwapError(f"显卡 {row['mgmt_no']} 已出售，不能置换")


def _check_part(row: Dict[str, Any]) -> None:
    if row["part_type"] != SWAPPABLE_PART_TYPE:
        raise SwapError("只有显卡部件能与单卡置换")
    if row.get("device_is_draft"):
        raise SwapError("这台整机还是草稿，先录入信息再置换")
    if _part_sold(row):
        raise SwapError("这个部件已出售，不能置换")


# ── 候选清单 ────────────────────────────────────────────────────────────── #

def _card_option(row: Dict[str, Any], media_count: int) -> Dict[str, Any]:
    return {
        "card_id": row["id"],
        "mgmt_no": row["mgmt_no"],
        "brand": row.get("brand"),
        "model": row.get("model"),
        "core_no": row.get("core_no"),
        "serial_no": row.get("serial_no"),
        "owner": row.get("owner"),
        "status": row["status"],
        "media_count": media_count,
    }


def _part_option(row: Dict[str, Any], media_count: int) -> Dict[str, Any]:
    return {
        "part_id": row["id"],
        "device_id": row["device_id"],
        "device_mgmt_no": row["device_mgmt_no"],
        "device_title": row.get("device_title"),
        "brand": row.get("brand"),
        "model": row.get("model"),
        "core_no": row.get("spec"),
        "serial_no": row.get("serial_no"),
        # 部件没单独指定归属人时就是整机的，候选里要显示「这块卡是谁的」
        "owner": row.get("owner") or row.get("device_owner"),
        "status": row["status"],
        "media_count": media_count,
    }


def _media_counts(table: str, fk: str, ids: List[int]) -> Dict[int, int]:
    """一次 IN 查询数完这批归属方各有几张图。表名与列名只来自本模块写死的常量。"""
    if not ids:
        return {}
    rows = db.query(
        f"SELECT {fk} AS oid, COUNT(*) AS n FROM {table} "
        f"WHERE {fk} IN ({', '.join(['%s'] * len(ids))}) GROUP BY {fk}",
        ids,
    )
    return {int(r["oid"]): int(r["n"]) for r in rows}


def candidates_for_card(card_id: int) -> List[Dict[str, Any]]:
    """这张卡能和哪些整机显卡部件换：未出售、整机不是草稿。同型号的排前面——
    置换几乎总是同型号之间（5090 换 5090），但不强制，型号录错了的也得找得到。"""
    card = _load_card(card_id)
    rows = db.query(
        "SELECT p.*, d.mgmt_no AS device_mgmt_no, d.title AS device_title, "
        "d.owner AS device_owner, d.is_draft AS device_is_draft "
        "FROM device_parts p JOIN devices d ON d.id = p.device_id "
        "WHERE p.part_type = %s AND d.is_draft = 0 "
        "AND p.sale_amount IS NULL AND p.status NOT IN ({ph}) "
        "ORDER BY d.purchase_date DESC, d.id DESC, p.sort_order, p.id".format(
            ph=", ".join(["%s"] * len(cards.SOLD_STATUSES))),
        [SWAPPABLE_PART_TYPE] + sorted(cards.SOLD_STATUSES),
    )
    counts = _media_counts("device_part_media", "part_id", [r["id"] for r in rows])
    out = [_part_option(r, counts.get(r["id"], 0)) for r in rows]
    model = card.get("model")
    out.sort(key=lambda x: 0 if model and x["model"] == model else 1)  # sort 是稳定的
    return out


def candidates_for_part(part_id: int) -> List[Dict[str, Any]]:
    """这个显卡部件能和哪些单卡换。口径与 candidates_for_card 对称。"""
    part = _load_part(part_id)
    rows = db.query(
        "SELECT * FROM cards WHERE is_draft = 0 AND sale_amount IS NULL "
        "AND status NOT IN ({ph}) ORDER BY purchase_date DESC, id DESC".format(
            ph=", ".join(["%s"] * len(cards.SOLD_STATUSES))),
        sorted(cards.SOLD_STATUSES),
    )
    counts = _media_counts("card_media", "card_id", [r["id"] for r in rows])
    out = [_card_option(r, counts.get(r["id"], 0)) for r in rows]
    model = part.get("model")
    out.sort(key=lambda x: 0 if model and x["model"] == model else 1)
    return out


# ── 执行 ────────────────────────────────────────────────────────────────── #

def _snapshot(values: Dict[str, Any], media_count: int, owner: Optional[str]) -> str:
    """快照统一用显卡这一侧的字段名（core_no 而不是 spec），两头读起来是同一个形状。"""
    data = dict(values)
    data["owner"] = owner
    data["media_count"] = media_count
    return json.dumps(data, ensure_ascii=False)


def perform(card_id: int, part_id: int, swap_date: Optional[dt.date] = None,
            note: Optional[str] = None) -> int:
    """互换一张单卡与一个显卡部件的实物信息和图片，记一条置换记录。返回记录 id。

    整段在一个事务里：字段换了一半、图片只搬了一边，那两张卡就再也对不上号了。
    资金池不用重算——一分钱都没动（见模块文档）。
    """
    card = _load_card(card_id)
    part = _load_part(part_id)
    _check_card(card)
    _check_part(part)

    card_vals = {c: card.get(c) for c, _ in SWAP_FIELDS}
    part_vals = {c: part.get(p) for c, p in SWAP_FIELDS}

    with db.transaction() as cur:
        # 锁住两头再读图，免得互换途中有人往其中一边又传了一张
        cur.execute("SELECT id FROM cards WHERE id = %s FOR UPDATE", (card_id,))
        cur.execute("SELECT id FROM device_parts WHERE id = %s FOR UPDATE", (part_id,))
        cur.execute(
            f"SELECT category, sort_order, {_MEDIA_COLS} FROM card_media "
            "WHERE card_id = %s ORDER BY sort_order, id", (card_id,))
        card_media = list(cur.fetchall())
        cur.execute(
            f"SELECT category, sort_order, {_MEDIA_COLS} FROM device_part_media "
            "WHERE part_id = %s ORDER BY sort_order, id", (part_id,))
        part_media = list(cur.fetchall())

        cur.execute(
            "UPDATE cards SET {sets} WHERE id = %s".format(
                sets=", ".join(f"`{c}` = %s" for c, _ in SWAP_FIELDS)),
            [part_vals[c] for c, _ in SWAP_FIELDS] + [card_id],
        )
        cur.execute(
            "UPDATE device_parts SET {sets} WHERE id = %s".format(
                sets=", ".join(f"`{p}` = %s" for _, p in SWAP_FIELDS)),
            [card_vals[c] for c, _ in SWAP_FIELDS] + [part_id],
        )

        # 图片：两边各自删掉再按对方的插回来。只动指针行，图床上的文件一个不碰。
        cur.execute("DELETE FROM card_media WHERE card_id = %s", (card_id,))
        cur.execute("DELETE FROM device_part_media WHERE part_id = %s", (part_id,))

        # 显卡 → 部件：部件那边是平铺一组，按「分类顺序、分类内顺序」排成一列，
        # 原分类记在 category 上留着换回来用
        card_media.sort(key=lambda m: (_CATEGORY_ORDER.get(m["category"], 99), m["sort_order"]))
        for order, m in enumerate(card_media):
            cur.execute(
                f"INSERT INTO device_part_media (part_id, category, sort_order, {_MEDIA_COLS}) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (part_id, m["category"], order, m["kind"], m["stored_name"], m["public_url"],
                 m["filename"], m["mime_type"], m["size_bytes"], m["created_at"]),
            )
        # 部件 → 显卡：记过分类的归位，其余落进默认分类；每个分类内重新从 0 编号
        next_order: Dict[str, int] = {}
        for m in part_media:
            category = m["category"] if m["category"] in _CATEGORY_ORDER else _DEFAULT_CATEGORY
            order = next_order.get(category, 0)
            next_order[category] = order + 1
            cur.execute(
                f"INSERT INTO card_media (card_id, category, sort_order, {_MEDIA_COLS}) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (card_id, category, order, m["kind"], m["stored_name"], m["public_url"],
                 m["filename"], m["mime_type"], m["size_bytes"], m["created_at"]),
            )

        cur.execute(
            "INSERT INTO item_swaps (swap_date, card_id, device_id, part_id, "
            "card_before, part_before, note) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (swap_date or dt.date.today(), card_id, part["device_id"], part_id,
             _snapshot(card_vals, len(card_media), card.get("owner")),
             _snapshot(part_vals, len(part_media), part.get("owner") or part.get("device_owner")),
             (note or "").strip()[:500] or None),
        )
        swap_id = cur.lastrowid

    log.info("置换：显卡 %s ↔ 整机 %s 的显卡部件 #%s",
             card["mgmt_no"], part["device_mgmt_no"], part_id)
    return int(swap_id)


# ── 记录 ────────────────────────────────────────────────────────────────── #

def _load_json(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return dict(value)


def _history(where: str, owner_id: int) -> List[Dict[str, Any]]:
    """where 只来自下面两个调用方写死的列名。"""
    rows = db.query(
        "SELECT s.*, c.mgmt_no AS card_mgmt_no, d.mgmt_no AS device_mgmt_no, "
        "d.title AS device_title FROM item_swaps s "
        "LEFT JOIN cards c ON c.id = s.card_id LEFT JOIN devices d ON d.id = s.device_id "
        f"WHERE s.{where} = %s ORDER BY s.swap_date DESC, s.id DESC",
        (owner_id,),
    )
    return [
        {
            "id": r["id"],
            "swap_date": _iso(r["swap_date"]),
            "card_id": r["card_id"],
            "card_mgmt_no": r.get("card_mgmt_no"),
            "device_id": r["device_id"],
            "device_mgmt_no": r.get("device_mgmt_no"),
            "device_title": r.get("device_title"),
            "part_id": r["part_id"],
            # 置换前单卡那一侧是什么、整机部件那一侧是什么（之后两边已经互换了）
            "card_before": _load_json(r.get("card_before")),
            "part_before": _load_json(r.get("part_before")),
            "note": r.get("note"),
            "created_at": _iso(r.get("created_at")),
        }
        for r in rows
    ]


def history_for_card(card_id: int) -> List[Dict[str, Any]]:
    return _history("card_id", card_id)


def history_for_device(device_id: int) -> List[Dict[str, Any]]:
    return _history("device_id", device_id)
