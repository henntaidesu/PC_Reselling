# -*- coding: utf-8 -*-
"""整机设备的增删改查、部件明细、状态流转、汇率刷新。

一台设备 = 一笔购入总价 + 若干个各自带出售价格的部件（见 src.devices 的模块文档）。
部件随设备整体提交：表单是自动保存的，每次 PUT 都带上完整的部件数组。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src import db, devices, funds
from src.auth import require_auth
from src.cards import uses_pool
from src.schema import (
    CARD_STATUSES,
    CURRENCIES,
    DEVICE_PART_TYPES,
    FUND_SOURCES,
    SOURCE_PLATFORMS,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(require_auth)])

# 允许写入 devices 的列。汇率两列由 _apply_fx 另行补上，不在这里。
_WRITABLE = [
    "title",
    "source_platform", "seller", "item_url", "order_no",
    "purchase_date", "purchase_amount", "purchase_currency",
    "intl_shipping_amount", "intl_shipping_currency",
    "fund_source",
    "status", "note",
]

# 允许写入 device_parts 的列，顺序即 INSERT / UPDATE 里的顺序。
# quantity 与 buyer 不在其中：数量恒为 1（同规格的两条内存就是两行，合成一行之后
# 序列号、成色、卖价都只能记一份），买家一栏则没人填。两列仍留在表里，不动老数据。
_PART_COLUMNS = [
    "part_type", "brand", "model", "spec", "serial_no",
    "sale_date", "sale_amount", "sale_currency",
    "domestic_shipping_amount", "domestic_shipping_currency",
    "status", "note", "sort_order",
]


class PartPayload(BaseModel):
    """一个部件。内存 / 硬盘这类一台机器里有好几条的，就提交好几条，条数不限。"""

    # 已存在的部件带上自己的 id，后端据此原地更新而不是删了重建——部件上挂着图片，
    # 换一次 id 就等于把图片连同旧行一起级联删掉。新加的行不带 id。
    id: Optional[int] = None
    part_type: str = "other"
    brand: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=128)
    spec: Optional[str] = Field(default=None, max_length=128)
    serial_no: Optional[str] = Field(default=None, max_length=128)

    sale_date: Optional[dt.date] = None
    sale_amount: Optional[float] = Field(default=None, ge=0)
    sale_currency: str = "CNY"
    domestic_shipping_amount: Optional[float] = Field(default=None, ge=0)
    domestic_shipping_currency: str = "CNY"

    status: str = "purchased"
    note: Optional[str] = Field(default=None, max_length=500)
    sort_order: int = 0

    @field_validator("part_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        v = (v or "other").strip().lower()
        if v not in DEVICE_PART_TYPES:
            raise ValueError(f"未知部件类型：{v}")
        return v

    @field_validator("sale_currency", "domestic_shipping_currency")
    @classmethod
    def _check_currency(cls, v: str) -> str:
        v = (v or "").upper().strip()
        if v not in CURRENCIES:
            raise ValueError(f"币种只能是 {' / '.join(CURRENCIES)}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        v = (v or "purchased").strip()
        if v not in CARD_STATUSES:
            raise ValueError(f"未知状态：{v}")
        return v


class DevicePayload(BaseModel):
    """新增 / 编辑整机。字段全部可选——录入是渐进的：买的时候只有总价，
    拆机后才知道有几条内存，卖掉才有售价，不该强制一次填全。"""

    title: Optional[str] = Field(default=None, max_length=128)

    source_platform: Optional[str] = Field(default=None, max_length=16)
    seller: Optional[str] = Field(default=None, max_length=128)
    item_url: Optional[str] = Field(default=None, max_length=1024)
    order_no: Optional[str] = Field(default=None, max_length=128)

    purchase_date: Optional[dt.date] = None
    purchase_amount: Optional[float] = Field(default=None, ge=0)
    purchase_currency: str = "JPY"
    intl_shipping_amount: Optional[float] = Field(default=None, ge=0)
    intl_shipping_currency: str = "JPY"

    # 采购资金来源：own = 自有资金；pool = 从资金池扣。选 pool 后这台机器的日元支出会
    # 在资金池里生成对应扣款，成本改由被消耗的注资批次的汇率分段折算。
    fund_source: str = "own"

    status: str = "purchased"
    note: Optional[str] = None

    # 部件明细。提交即是这台设备**当前的全部部件**（见 _write_parts 的说明）。
    parts: List[PartPayload] = Field(default_factory=list, max_length=200)

    @field_validator("purchase_currency", "intl_shipping_currency")
    @classmethod
    def _check_currency(cls, v: str) -> str:
        v = (v or "").upper().strip()
        if v not in CURRENCIES:
            raise ValueError(f"币种只能是 {' / '.join(CURRENCIES)}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        v = (v or "purchased").strip()
        if v not in CARD_STATUSES:
            raise ValueError(f"未知状态：{v}")
        return v

    @field_validator("fund_source")
    @classmethod
    def _check_fund_source(cls, v: str) -> str:
        v = (v or "own").strip().lower()
        if v not in FUND_SOURCES:
            raise ValueError(f"资金来源只能是 {' / '.join(FUND_SOURCES)}")
        return v

    @field_validator("source_platform")
    @classmethod
    def _check_platform(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip().lower()
        if v not in SOURCE_PLATFORMS:
            raise ValueError(f"购买平台只能是 {' / '.join(SOURCE_PLATFORMS)}")
        return v


class StatusPayload(BaseModel):
    status: str
    note: Optional[str] = Field(default=None, max_length=500)


def _clean(value: Any) -> Any:
    """空字符串统一存成 NULL，理由同 cards_api._clean：别让「没填」有两种形态。"""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _apply_fx(payload: DevicePayload) -> Dict[str, Any]:
    """一次取齐这台设备用到的全部汇率：购入日一个，每个部件的出售日各一个。

    返回设备行要写的两列 + 每个部件对应的 (rate, rate_date)，顺序与 payload.parts 一致。
    """
    resolved = devices.resolve_rates(
        [payload.purchase_date] + [p.sale_date for p in payload.parts]
    )
    p_rate, p_date = devices.rate_for(resolved, payload.purchase_date)
    return {
        "purchase_fx_rate": p_rate,
        "purchase_fx_date": p_date,
        "part_rates": [devices.rate_for(resolved, p.sale_date) for p in payload.parts],
        "warnings": resolved["warnings"],
    }


def _write_parts(device_id: int, payload: DevicePayload, fx: Dict[str, Any]) -> None:
    """按 id 增量写入这台设备的部件：带 id 的原地更新，没 id 的新插，这次没提交的删掉。

    原先是「先全删再全插」——写起来简单，代价是部件行的 id 每存一次就换一批。部件能
    传图之后这条路就走不通了：device_part_media 的外键指着 device_parts，行一删，刚传
    的图片就跟着级联没了，而表单是每改一个字段就自动保存一次的。所以 id 必须稳定。

    提交里没出现的行按「用户删掉了这个部件」处理，连同它的图片记录一并删除；图床上的
    文件不动（与删卡时的默认一致：留个孤儿文件只占空间，误删则找不回来）。
    """
    existing = {int(r["id"]) for r in db.query(
        "SELECT id FROM device_parts WHERE device_id = %s", (device_id,))}
    kept = set()

    insert_sql = "INSERT INTO device_parts ({cols}, device_id, sale_fx_rate, sale_fx_date) VALUES ({ph})".format(
        cols=", ".join(f"`{c}`" for c in _PART_COLUMNS),
        ph=", ".join(["%s"] * (len(_PART_COLUMNS) + 3)),
    )
    update_sql = "UPDATE device_parts SET {sets}, sale_fx_rate = %s, sale_fx_date = %s WHERE id = %s".format(
        sets=", ".join(f"`{c}` = %s" for c in _PART_COLUMNS),
    )

    with db.transaction() as cur:
        for index, part in enumerate(payload.parts):
            values = {name: _clean(getattr(part, name)) for name in _PART_COLUMNS}
            # 排序按提交顺序重排，前端拖动 / 插入后不必自己维护 sort_order
            values["sort_order"] = index
            rate, rate_date = fx["part_rates"][index]
            row = [values[c] for c in _PART_COLUMNS]
            # id 必须确认属于这台设备才认：否则一个伪造的 id 就能改到别人的部件上
            part_id = int(part.id) if part.id and int(part.id) in existing else None
            if part_id:
                cur.execute(update_sql, row + [rate, rate_date, part_id])
                kept.add(part_id)
            else:
                cur.execute(insert_sql, row + [device_id, rate, rate_date])

        stale = existing - kept
        if stale:
            cur.execute(
                "DELETE FROM device_parts WHERE id IN ({ph})".format(
                    ph=", ".join(["%s"] * len(stale))),
                list(stale),
            )


def _load(device_id: int) -> Optional[Dict[str, Any]]:
    return db.query_one("SELECT * FROM devices WHERE id = %s", (device_id,))


def _result(device_id: int, warnings: List[str]) -> Dict[str, Any]:
    """一台设备的完整响应：设备 + 部件 + 池内扣款明细 + 状态流转 + 本次操作的警告。

    增删改查一律回这同一个形状。详情页既是展示页也是编辑页（改一个字段就 PUT 一次），
    而一次编辑能同时改动金额、资金池分摊和状态时间线——响应里全带上，前端拿到就能整页
    刷新，不必在每次保存后再补一发 GET。
    """
    row = _load(device_id)
    parts = devices.load_parts([device_id]).get(device_id, [])
    out = devices.serialize(row, parts)
    # 部件的图片本身按需拉（打开那一栏才请求），这里只带个数量，好在折叠状态下也能
    # 看出哪些部件已经有图
    counts = devices.part_media_counts([p["id"] for p in parts])
    for item in out["parts"]:
        item["media_count"] = counts.get(item["id"], 0)
    out["fund_draws"] = funds.device_draws(device_id) if uses_pool(row) else []
    out["status_logs"] = [
        {
            "from_status": log_row["from_status"],
            "to_status": log_row["to_status"],
            "note": log_row["note"],
            "occurred_at": log_row["occurred_at"].isoformat() if log_row["occurred_at"] else None,
        }
        for log_row in db.query(
            "SELECT from_status, to_status, note, occurred_at FROM device_status_logs "
            "WHERE device_id = %s ORDER BY occurred_at, id",
            (device_id,),
        )
    ]
    out["warnings"] = warnings
    return out


@router.get("/next-mgmt-no")
def next_mgmt_no():
    """新建表单打开时预填一个编号。真正的编号在保存那一刻才生成。"""
    return {"mgmt_no": devices.next_mgmt_no()}


@router.get("/{device_id}")
def get_device(device_id: int):
    if not _load(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    return _result(device_id, [])


@router.post("/draft")
def create_draft():
    """建一台空草稿设备，只为拿到 id 与管理编号——列表页点「新增整机」就调它，拿到 id
    后直接跳进这台设备的详情页填写（与显卡同一套流程）。

    草稿不进列表也不进统计（is_draft=1）。详情页上存下第一笔改动就会走 update 转正；
    什么都没填就离开则由前端删掉，残留的（关浏览器等）由启动时的 _cleanup_stale_drafts
    兜底清理。
    """
    mgmt_no = devices.next_mgmt_no()
    device_id = db.insert(
        "INSERT INTO devices (mgmt_no, status, is_draft) VALUES (%s, 'purchased', 1)",
        (mgmt_no,),
    )
    return {"id": device_id, "mgmt_no": mgmt_no}


@router.post("")
def create_device(payload: DevicePayload):
    fx = _apply_fx(payload)
    values = {name: _clean(getattr(payload, name)) for name in _WRITABLE}
    values["mgmt_no"] = devices.next_mgmt_no()
    values["purchase_fx_rate"] = fx["purchase_fx_rate"]
    values["purchase_fx_date"] = fx["purchase_fx_date"]

    columns = list(values.keys())
    device_id = db.insert(
        "INSERT INTO devices ({cols}) VALUES ({ph})".format(
            cols=", ".join(f"`{c}`" for c in columns),
            ph=", ".join(["%s"] * len(columns)),
        ),
        [values[c] for c in columns],
    )
    _write_parts(device_id, payload, fx)
    devices.log_status(device_id, None, values["status"], "创建")
    # 先同步资金池扣款再读回：分摊结果是写在设备行上的，读早了成本还是空的
    funds.sync_device_and_rebuild(device_id)
    return _result(device_id, fx["warnings"])


@router.put("/{device_id}")
def update_device(device_id: int, payload: DevicePayload):
    existing = _load(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="设备不存在")

    fx = _apply_fx(payload)
    values = {name: _clean(getattr(payload, name)) for name in _WRITABLE}
    values["purchase_fx_rate"] = fx["purchase_fx_rate"]
    values["purchase_fx_date"] = fx["purchase_fx_date"]
    # 一旦保存就转正：草稿变正式设备，从此进列表与统计
    values["is_draft"] = 0

    db.execute(
        "UPDATE devices SET {sets} WHERE id = %s".format(
            sets=", ".join(f"`{c}` = %s" for c in values)
        ),
        list(values.values()) + [device_id],
    )
    _write_parts(device_id, payload, fx)
    devices.log_status(device_id, existing["status"], values["status"], "编辑")
    funds.sync_device_and_rebuild(device_id)
    return _result(device_id, fx["warnings"])


@router.patch("/{device_id}/status")
def change_status(device_id: int, payload: StatusPayload):
    """只改状态。列表页的快捷操作走这里，不必提交整个表单。"""
    try:
        status = devices.validate_status(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    existing = _load(device_id)
    if not existing:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.execute("UPDATE devices SET status = %s WHERE id = %s", (status, device_id))
    devices.log_status(device_id, existing["status"], status, payload.note or "")
    return {"ok": True, "status": status}


@router.post("/{device_id}/refresh-fx")
def refresh_fx(device_id: int):
    """按购入日与各部件的出售日重新取一遍汇率。

    录入时汇率接口不可用会留空，金额就算不出来；补上网络后点一次这里即可，
    不必逐个字段重新编辑。
    """
    row = _load(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")
    parts = devices.load_parts([device_id]).get(device_id, [])
    resolved = devices.resolve_rates([row["purchase_date"]] + [p["sale_date"] for p in parts])

    p_rate, p_date = devices.rate_for(resolved, row["purchase_date"])
    db.execute(
        "UPDATE devices SET purchase_fx_rate = %s, purchase_fx_date = %s WHERE id = %s",
        (p_rate, p_date, device_id),
    )
    for part in parts:
        rate, rate_date = devices.rate_for(resolved, part["sale_date"])
        db.execute(
            "UPDATE device_parts SET sale_fx_rate = %s, sale_fx_date = %s WHERE id = %s",
            (rate, rate_date, part["id"]),
        )
    return _result(device_id, resolved["warnings"])


@router.delete("/{device_id}")
def delete_device(device_id: int):
    """删设备。部件行与它的池内扣款都由外键 ON DELETE CASCADE 一起清掉。"""
    if not _load(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    had_draws = bool(db.query_one("SELECT id FROM fund_draws WHERE device_id = %s", (device_id,)))
    db.execute("DELETE FROM devices WHERE id = %s", (device_id,))
    # 扣款刚被级联删掉了：池子余额和后面那些扣款的分摊都得跟着重算
    if had_draws:
        try:
            funds.rebuild()
        except Exception as exc:  # noqa: BLE001  重算失败不该让删除本身失败
            log.warning("删设备后重算资金池失败：%s", exc)
    return {"ok": True}
