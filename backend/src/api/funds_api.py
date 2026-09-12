# -*- coding: utf-8 -*-
"""资金池：注资、扣款与分摊明细。

写操作（注资/扣款的增删改）之后一律 ``funds.rebuild()`` 再返回，让响应里的
summary 就是重算后的结果——否则前端刚存完看到的还是旧的余额，得再刷一次才对得上。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from src import db, funds
from src.auth import require_auth
from src.schema import POOL_CURRENCY, SHARE_UNIT

log = logging.getLogger(__name__)

router = APIRouter(prefix="/funds", tags=["funds"], dependencies=[Depends(require_auth)])

# 由实付人民币折算出的汇率的合理区间（100 日元 = ? 人民币）。真实牌价这些年在 4~9 之间，
# 这个区间留得很宽，够挡住「把日元金额填进了人民币格子」「小数点点错位」这类错——那种
# 错存进去只是个大一点的数字，页面上看不出来，成本却差几百倍。
_RATE_MIN, _RATE_MAX = 0.5, 20.0


class InjectionPayload(BaseModel):
    """一笔注资。金额恒为日元；实付人民币留空则按注资日自动取牌价。"""

    inject_date: dt.date
    amount: float = Field(gt=0)
    currency: str = POOL_CURRENCY
    # 这次换汇**实际付出去的人民币**。汇率不收——由它和 amount 自动算出来
    # （funds.manual_rate）：换汇的人手上有的就是这两个数，汇率是它们的商，
    # 让人自己先除一遍再填只会多一个填错的机会。留空则按注资日取牌价。
    cny_cost: Optional[float] = Field(default=None, gt=0)
    # 这批钱是谁出的。收名字而不是字典 id：下拉允许现敲一个新名字，见 funds.ensure_contributor。
    contributor: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _check_manual_rate(self) -> "InjectionPayload":
        rate = funds.manual_rate(self.amount, self.cny_cost)
        if rate is not None and not _RATE_MIN < rate < _RATE_MAX:
            raise ValueError(
                f"实付人民币与日元金额对不上：折合 {rate:.4f}（100 日元 = ? 人民币），"
                f"正常在 {_RATE_MIN}~{_RATE_MAX} 之间，检查一下金额是不是填错了"
            )
        return self

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, v: str) -> str:
        v = (v or POOL_CURRENCY).upper().strip()
        if v != POOL_CURRENCY:
            raise ValueError(f"资金池只接受 {POOL_CURRENCY}")
        return v


class DrawPayload(BaseModel):
    """手工记的池内支出（手续费、代购费…）。

    卡片与整机的购入价、国际运费**不走这里**——那两类由各自表单上的「从资金池扣除」
    开关自动同步，手工再记一笔就会重复扣钱。
    """

    draw_date: dt.date
    amount: float = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=500)


class SharePayload(BaseModel):
    """一件货（显卡 / 整机）上某个出资人占的比例。

    定义在这里、由 cards_api 和 devices_api 共同 import：两边是同一件事，各写一份的
    下场是某天只给其中一边加了校验，另一边能存进一组加起来 97% 的比例。
    """

    contributor: str = Field(min_length=1, max_length=64)
    # 百分数（60 = 60%），见 schema.SHARE_UNIT
    share_pct: float = Field(gt=0, le=SHARE_UNIT)


def validate_shares(shares: Optional[List[SharePayload]]) -> Optional[List[SharePayload]]:
    """校验一组出资比例：不能重名，加起来必须正好是 100。

    ``None`` = 这次请求没提交这一项，保持原样；``[]`` = 明确清空（不指定出资人，
    回到全池 FIFO）。两者必须分开：详情页是逐字段自动保存的，把「没提交」当成「清空」
    会让改一次备注就把出资比例抹掉。

    合计必须是 100 而不是「按填的归一化」：填了 60 和 30 的人，想的多半是还有一个人
    没填完，而不是「那就按 2:1 分」。当场拦住，比事后发现分红少算一个人强。
    """
    if shares is None:
        return None
    names = [sh.contributor.strip() for sh in shares]
    if any(not n for n in names):
        raise ValueError("出资人不能为空")
    if len(set(names)) != len(names):
        raise ValueError("同一个出资人只能出现一次")
    if not shares:
        return []
    total = round(sum(sh.share_pct for sh in shares), 4)
    if abs(total - SHARE_UNIT) > 0.01:
        raise ValueError(f"出资比例加起来要等于 {SHARE_UNIT}%，现在是 {total:g}%")
    return shares


def apply_shares(kind: str, owner_id: int, shares: Optional[List[SharePayload]]) -> bool:
    """把出资比例写到一件货上，返回是否真的变了（变了要重算池子）。

    顺带把名字落进出资人字典（与注资那头同一个 upsert），所以在显卡详情页现敲一个
    新出资人也能用，不必先跑一趟资金池页面。
    """
    if shares is None:
        return False
    rows = [
        {"contributor": funds.ensure_contributor(sh.contributor), "share_pct": sh.share_pct}
        for sh in shares
    ]
    return funds.write_shares(kind, owner_id, [r for r in rows if r["contributor"]])


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _state(warnings=None):
    """所有写操作的统一响应：重算后的总账 + 两张明细表 + 警告。"""
    result = funds.rebuild()
    return {
        "summary": funds.summary(),
        "injections": funds.list_injections(),
        "draws": funds.list_draws(),
        "contributors": funds.contributor_totals(),
        "contributor_names": funds.contributor_names(),
        "warnings": list(warnings or []) + result["warnings"],
    }


@router.get("/summary")
def summary():
    return funds.summary()


@router.get("")
def overview():
    """页面首屏一次拿全：总账 + 注资列表 + 扣款列表 + 出资人。

    出资人给两份：``contributors`` 是按人汇总的结果（派生自注资与分摊），
    ``contributor_names`` 是字典里的候选清单——一个刚建好还没注过资的人只在后者里，
    只发汇总的话他在下拉里就不见了。
    """
    return {
        "summary": funds.summary(),
        "injections": funds.list_injections(),
        "draws": funds.list_draws(),
        "contributors": funds.contributor_totals(),
        "contributor_names": funds.contributor_names(),
    }


@router.get("/injections")
def list_injections():
    return {"items": funds.list_injections()}


@router.post("/injections")
def create_injection(payload: InjectionPayload):
    fx = funds.resolve_injection_fx(payload.inject_date, payload.amount, payload.cny_cost)
    db.insert(
        "INSERT INTO fund_injections (inject_date, amount, currency, fx_rate, fx_date, "
        "fx_manual, contributor, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (payload.inject_date, payload.amount, payload.currency, fx["fx_rate"], fx["fx_date"],
         fx["fx_manual"], funds.ensure_contributor(payload.contributor), _clean(payload.note)),
    )
    return _state(fx["warnings"])


@router.put("/injections/{injection_id}")
def update_injection(injection_id: int, payload: InjectionPayload):
    existing = db.query_one("SELECT id FROM fund_injections WHERE id = %s", (injection_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="注资记录不存在")
    fx = funds.resolve_injection_fx(payload.inject_date, payload.amount, payload.cny_cost)
    db.execute(
        "UPDATE fund_injections SET inject_date = %s, amount = %s, currency = %s, fx_rate = %s, "
        "fx_date = %s, fx_manual = %s, contributor = %s, note = %s WHERE id = %s",
        (payload.inject_date, payload.amount, payload.currency, fx["fx_rate"], fx["fx_date"],
         fx["fx_manual"], funds.ensure_contributor(payload.contributor), _clean(payload.note),
         injection_id),
    )
    return _state(fx["warnings"])


@router.delete("/injections/{injection_id}")
def delete_injection(injection_id: int):
    """删掉一批注资。

    已经被花掉的那部分不会阻止删除——分摊是派生数据，删完重算即可；只是原本吃这批钱
    的扣款会转而去吃别的批次，吃不到的部分变成「余额不足」并给出警告。这比禁止删除
    更实用：录错一笔注资是常事，而它往往已经被后面的扣款「用掉」了。
    """
    existing = db.query_one("SELECT id FROM fund_injections WHERE id = %s", (injection_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="注资记录不存在")
    db.execute("DELETE FROM fund_injections WHERE id = %s", (injection_id,))
    return _state()


@router.get("/draws")
def list_draws(
    card_id: Optional[int] = Query(default=None),
    device_id: Optional[int] = Query(default=None),
    limit: int = Query(default=300, ge=1, le=1000),
):
    return {"items": funds.list_draws(card_id=card_id, device_id=device_id, limit=limit)}


@router.post("/draws")
def create_draw(payload: DrawPayload):
    db.insert(
        "INSERT INTO fund_draws (card_id, device_id, category, draw_date, amount, currency, note) "
        "VALUES (NULL, NULL, 'other', %s, %s, %s, %s)",
        (payload.draw_date, payload.amount, POOL_CURRENCY, _clean(payload.note)),
    )
    return _state()


@router.put("/draws/{draw_id}")
def update_draw(draw_id: int, payload: DrawPayload):
    existing = db.query_one(
        "SELECT id, category, card_id, device_id FROM fund_draws WHERE id = %s", (draw_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="扣款记录不存在")
    if existing["card_id"] or existing["device_id"]:
        raise HTTPException(
            status_code=400,
            detail="这笔扣款跟着显卡 / 整机走，请到对应的那条记录上修改金额或关闭「从资金池扣除」。",
        )
    db.execute(
        "UPDATE fund_draws SET draw_date = %s, amount = %s, note = %s WHERE id = %s",
        (payload.draw_date, payload.amount, _clean(payload.note), draw_id),
    )
    return _state()


@router.delete("/draws/{draw_id}")
def delete_draw(draw_id: int):
    existing = db.query_one(
        "SELECT id, card_id, device_id FROM fund_draws WHERE id = %s", (draw_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="扣款记录不存在")
    if existing["card_id"] or existing["device_id"]:
        raise HTTPException(
            status_code=400,
            detail="这笔扣款跟着显卡 / 整机走，请到对应的那条记录上关闭「从资金池扣除」。",
        )
    db.execute("DELETE FROM fund_draws WHERE id = %s", (draw_id,))
    return _state()


@router.post("/rebuild")
def rebuild():
    """手工触发全量重算。补录了历史注资、或改过汇率后用它把成本刷一遍。"""
    return _state()
