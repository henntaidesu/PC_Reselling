# -*- coding: utf-8 -*-
"""实物置换：单卡 ↔ 整机显卡部件（规则见 src.swaps 的模块文档）。

置换记录本身不单独列表展示，跟着两头的详情响应走（cards_api / devices_api 的
``_result`` 里的 ``swaps``），所以这里只有「挑对象」和「执行」两个端点。
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src import swaps
from src.auth import require_auth

router = APIRouter(prefix="/swaps", tags=["swaps"], dependencies=[Depends(require_auth)])


class SwapPayload(BaseModel):
    card_id: int
    part_id: int
    swap_date: Optional[dt.date] = None
    note: Optional[str] = Field(default=None, max_length=500)


@router.get("/candidates")
def candidates(
    card_id: Optional[int] = Query(default=None, description="从显卡发起：列出可换的整机显卡部件"),
    part_id: Optional[int] = Query(default=None, description="从部件发起：列出可换的单卡"),
):
    """两种发起方向各给一份对方的候选。只传一个参数，两个都传按显卡侧算。"""
    try:
        if card_id is not None:
            return {"items": swaps.candidates_for_card(card_id)}
        if part_id is not None:
            return {"items": swaps.candidates_for_part(part_id)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    raise HTTPException(status_code=400, detail="缺少 card_id 或 part_id")


@router.post("")
def create_swap(payload: SwapPayload):
    """执行置换。响应只带记录 id：两头的详情各自重新 GET 一次即可，这里不替哪一边
    拼完整响应——发起方可能是显卡详情，也可能是整机详情。"""
    try:
        swap_id = swaps.perform(payload.card_id, payload.part_id, payload.swap_date, payload.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except swaps.SwapError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "id": swap_id}
