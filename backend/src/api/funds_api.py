# -*- coding: utf-8 -*-
"""资金池：注资、扣款与分摊明细。

写操作（注资/扣款的增删改）之后一律 ``funds.rebuild()`` 再返回，让响应里的
summary 就是重算后的结果——否则前端刚存完看到的还是旧的余额，得再刷一次才对得上。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from src import db, funds
from src.auth import require_auth
from src.schema import POOL_CURRENCY

log = logging.getLogger(__name__)

router = APIRouter(prefix="/funds", tags=["funds"], dependencies=[Depends(require_auth)])

# 由实付人民币折算出的汇率的合理区间（100 日元 = ? 人民币）。真实牌价这些年在 4~9 之间，
# 这个区间留得很宽，够挡住「把日元金额填进了人民币格子」「小数点点错位」这类错——那种
# 错存进去只是个大一点的数字，页面上看不出来，成本却差几百倍。
_RATE_MIN, _RATE_MAX = 0.5, 20.0


_INJECT_TYPES = ("forex", "cash")


class InjectionPayload(BaseModel):
    """一笔注资。金额恒为日元，两种方式定汇率的办法不同：

    - forex（外汇注资）：拿人民币换来的日元。**必须填实付人民币**，汇率由它和日元金额
      算出来——换汇的人手上就有这两个数，按注资日牌价取的只是个近似，拿它当成本会让
      吃到这批钱的每件货都偏一点。
    - cash（现金注资）：手上本来就是日元现金，没有一笔真实的换汇价可填，按注资日的
      牌价记人民币成本。不记成 0：那等于说这笔钱是白来的，吃到它的货会凭空多出利润。
    """

    inject_date: dt.date
    amount: float = Field(gt=0)
    currency: str = POOL_CURRENCY
    inject_type: str = "forex"
    # 外汇注资**实际付出去的人民币**。汇率不收——由它和 amount 自动算出来
    # （funds.manual_rate），让人自己先除一遍再填只会多一个填错的机会。现金注资忽略它。
    cny_cost: Optional[float] = Field(default=None, gt=0)
    # 注资必须写明是谁的钱：没有出资人的批次只能被全池 FIFO 吃掉，指定了出资人的货
    # 永远扣不到它，按人汇总时也只能归进「未指定」——等于这笔钱在账上找不到主人。
    contributor: str = Field(max_length=64)
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("contributor")
    @classmethod
    def _check_contributor(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("注资要选出资人")
        return v

    @field_validator("inject_type")
    @classmethod
    def _check_inject_type(cls, v: str) -> str:
        v = (v or "forex").strip().lower()
        if v not in _INJECT_TYPES:
            raise ValueError(f"注资类型只能是 {' / '.join(_INJECT_TYPES)}")
        return v

    @model_validator(mode="after")
    def _check_manual_rate(self) -> "InjectionPayload":
        if self.inject_type == "cash":
            self.cny_cost = None
            return self
        if self.cny_cost is None:
            raise ValueError("外汇注资要填这次换汇实际付出的人民币")
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

    卡片与整机的购入价、国际运费**不走这里**——那两类跟着各自的归属人自动同步，
    手工再记一笔就会重复扣钱。

    ``contributor`` 指定这笔支出从谁的钱里扣：FIFO 只在那个人的注资批次里跑，
    不影响别人的余额，不够时同样记成欠款。留空则按全池 FIFO。
    """

    draw_date: dt.date
    amount: float = Field(gt=0)
    contributor: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=500)


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
    # 现金注资的 cny_cost 已在校验里置空，这里自然落到「按注资日取牌价」那条路
    fx = funds.resolve_injection_fx(payload.inject_date, payload.amount, payload.cny_cost)
    db.insert(
        "INSERT INTO fund_injections (inject_date, amount, currency, inject_type, fx_rate, "
        "fx_date, fx_manual, contributor, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (payload.inject_date, payload.amount, payload.currency, payload.inject_type,
         fx["fx_rate"], fx["fx_date"], fx["fx_manual"],
         funds.ensure_contributor(payload.contributor), _clean(payload.note)),
    )
    return _state(fx["warnings"])


@router.put("/injections/{injection_id}")
def update_injection(injection_id: int, payload: InjectionPayload):
    existing = db.query_one("SELECT id FROM fund_injections WHERE id = %s", (injection_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="注资记录不存在")
    # 现金注资的 cny_cost 已在校验里置空，这里自然落到「按注资日取牌价」那条路
    fx = funds.resolve_injection_fx(payload.inject_date, payload.amount, payload.cny_cost)
    db.execute(
        "UPDATE fund_injections SET inject_date = %s, amount = %s, currency = %s, "
        "inject_type = %s, fx_rate = %s, fx_date = %s, fx_manual = %s, contributor = %s, "
        "note = %s WHERE id = %s",
        (payload.inject_date, payload.amount, payload.currency, payload.inject_type,
         fx["fx_rate"], fx["fx_date"], fx["fx_manual"],
         funds.ensure_contributor(payload.contributor), _clean(payload.note), injection_id),
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
    contributor = funds.ensure_contributor(payload.contributor) if payload.contributor else None
    db.insert(
        "INSERT INTO fund_draws (card_id, device_id, category, draw_date, amount, currency, "
        "contributor, note) VALUES (NULL, NULL, 'other', %s, %s, %s, %s, %s)",
        (payload.draw_date, payload.amount, POOL_CURRENCY, contributor, _clean(payload.note)),
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
    contributor = funds.ensure_contributor(payload.contributor) if payload.contributor else None
    db.execute(
        "UPDATE fund_draws SET draw_date = %s, amount = %s, contributor = %s, note = %s "
        "WHERE id = %s",
        (payload.draw_date, payload.amount, contributor, _clean(payload.note), draw_id),
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
