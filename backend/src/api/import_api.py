# -*- coding: utf-8 -*-
"""从商品页链接新建一张显卡 / 一台整机：标题、卖家、平台、链接直接填好，商品图传进图床。

取数怎么做见 ``src/item_import.py``；这里只管落库。

**导入出来的是正式行，不是草稿**：它已经有了真实内容（标题、链接、图），关掉详情时不该
被当成空草稿删掉。导错了就像别的行一样手动删除。

**先读、再建行、最后传图**：商品读不出来时一行都不建（没有要清理的半成品）；行建好之后
图片逐张独立成败，传失败几张不影响这一行，失败项随响应带回去提示。图床没配置也照样建行，
只是图一张都没有——标题和链接已经省掉了大半的手工。

**查重**：同一个规范链接已经录过（草稿除外）就拒绝，并告诉用户是哪一件。一个商品页只能
买一次，重复导入几乎都是手滑点了两次或忘了已经录过。

**显卡没有标题列**，标题写进备注：品牌 / 型号是字典下拉，从日文标题里硬猜只会往字典里
灌一堆脏条目，不如留给人挑。整机的 ``title`` 就是名称本身，直接填。

**购入价 = 现价 + 送料**（日元），组成写进备注留底（「595,100 円 + 送料 2,068 円（佐川急便）」），
日后对账单时知道这个数是怎么来的。购入日与汇率快照一并填上：只有金额没有日期的话，
折不出人民币，成本一栏就是「—」。送料不知道时只记现价，警告随响应带回去。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src import cards, db, devices, funds, item_import, settings_store
from src.api import media_api
from src.auth import require_admin, require_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/import", tags=["import"], dependencies=[Depends(require_auth)])

# devices.title 是 VARCHAR(128)，雅虎拍卖的标题最长 65 字、煤炉 80 字，一般放得下，
# 截断只是防呆
_DEVICE_TITLE_MAX = 128


# 雅虎拍卖算送料用的收货都道府县（JIS 编码 1–47），一般是转运仓库所在地
_SHIP_PREF_KEY = "import.ship_pref"
_SHIP_PREF_DEFAULT = 13  # 东京都


class ImportPayload(BaseModel):
    # 允许整段分享文字，不只是链接（见 item_import.parse_url）
    url: str = Field(..., min_length=1, max_length=4000)


class ImportSettingsPayload(BaseModel):
    ship_pref: int = Field(..., ge=1, le=47)


def _ship_pref() -> int:
    value = settings_store.get_int(_SHIP_PREF_KEY, _SHIP_PREF_DEFAULT)
    return value if 1 <= value <= 47 else _SHIP_PREF_DEFAULT


@router.get("/settings")
def get_settings():
    return {"ship_pref": _ship_pref()}


@router.put("/settings", dependencies=[Depends(require_admin)])
def save_settings(payload: ImportSettingsPayload):
    settings_store.set(_SHIP_PREF_KEY, str(payload.ship_pref))
    return {"ship_pref": payload.ship_pref}


def _fetch(text: str) -> item_import.ItemInfo:
    try:
        return item_import.fetch(text, _ship_pref())
    except item_import.ItemImportError as exc:
        raise HTTPException(status_code=400, detail=exc.message)


def _purchase(info: item_import.ItemInfo) -> Dict[str, Any]:
    """购入侧要写的列：金额、日期、汇率快照，以及留底用的价格组成。"""
    amount: Optional[int] = None
    breakdown = ""
    if info.price is not None:
        amount = info.price + (info.shipping or 0)
        if info.shipping:
            breakdown = f"{info.price:,} 円 + 送料 {info.shipping:,} 円"
        else:
            breakdown = f"{info.price:,} 円"
        if info.shipping_label:
            breakdown += f"（{info.shipping_label}）"
        if info.shipping is None:
            breakdown += "，送料未计入"
    else:
        info.warnings.append("没读到价格，请手动填写购入价")

    purchase_date = info.purchase_date or dt.date.today()
    fx = cards.resolve_fx(purchase_date, None)
    return {
        "purchase_amount": amount,
        "purchase_date": purchase_date,
        "purchase_fx_rate": fx["purchase_fx_rate"],
        "purchase_fx_date": fx["purchase_fx_date"],
        "breakdown": breakdown,
        "warnings": info.warnings + fx["warnings"],
    }


def _reject_duplicate(table: str, info: item_import.ItemInfo) -> None:
    # 两张表都查：同一个链接先录成整机、再录成显卡也算重复
    for tbl in ("cards", "devices"):
        row = db.query_one(
            f"SELECT mgmt_no FROM {tbl} WHERE item_url = %s AND is_draft = 0 LIMIT 1", (info.url,)
        )
        if row:
            raise HTTPException(status_code=409, detail=f"这件商品已经录入过了（{row['mgmt_no']}）")


def _ensure_platform(name: str) -> str:
    """平台字典里没有就补一条。

    内置的只有 yahoo / mercari / other，雅虎二手（paypay）是导入时才第一次出现的；
    不补的话这一行的平台在详情页下拉里选不中，看着像是没填。
    """
    if not db.query_one("SELECT id FROM source_platforms WHERE name = %s", (name,)):
        next_order = db.query_scalar(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM source_platforms", default=0
        ) or 0
        # INSERT IGNORE：两个导入同时补同一个平台时，唯一键挡住的那个不必报错
        db.execute("INSERT IGNORE INTO source_platforms (name, sort_order) VALUES (%s, %s)",
                   (name, next_order))
        log.info("导入时补入购买平台：%s", name)
    return name


def _store_photos(info: item_import.ItemInfo, store) -> Dict[str, Any]:
    """下载商品图并传进图床。``store(blobs)`` 决定落到哪张媒体表。"""
    blobs, errors = item_import.download_photos(info)
    uploaded: List[Dict[str, Any]] = []
    if blobs:
        try:
            result = store(blobs)
            uploaded, errors = result["uploaded"], errors + result["errors"]
        except HTTPException as exc:  # 图床没配置 / 连不上：行已经建好，只是没有图
            errors.append({"filename": "", "error": str(exc.detail)})
    return {"photos": len(uploaded), "photo_total": len(info.photos), "errors": errors}


def _summary(info: item_import.ItemInfo, buy: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": info.title, "platform": info.platform, "item_url": info.url,
        "purchase_amount": buy["purchase_amount"], "breakdown": buy["breakdown"],
        "warnings": buy["warnings"],
    }


@router.post("/card")
def import_card(payload: ImportPayload):
    info = _fetch(payload.url)
    _reject_duplicate("cards", info)
    buy = _purchase(info)
    note = "\n".join(x for x in (info.title, buy["breakdown"]) if x)
    mgmt_no = cards.next_mgmt_no()
    card_id = db.insert(
        "INSERT INTO cards (mgmt_no, source_platform, seller, item_url, note, "
        " purchase_date, purchase_amount, purchase_currency, purchase_fx_rate, purchase_fx_date, "
        " status, is_draft) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'JPY', %s, %s, 'purchased', 0)",
        (mgmt_no, _ensure_platform(info.platform), info.seller[:128] or None, info.url, note,
         buy["purchase_date"], buy["purchase_amount"], buy["purchase_fx_rate"], buy["purchase_fx_date"]),
    )
    cards.log_status(card_id, None, "purchased", "从商品页导入")
    funds.sync_card_and_rebuild(card_id)
    # 商品页上的图是卖家拍的外观照，进「显卡外观」分类
    photos = _store_photos(info, lambda blobs: media_api.store_card_blobs(card_id, "appearance", blobs))
    return {"id": card_id, "mgmt_no": mgmt_no, **_summary(info, buy), **photos}


@router.post("/device")
def import_device(payload: ImportPayload):
    info = _fetch(payload.url)
    _reject_duplicate("devices", info)
    buy = _purchase(info)
    mgmt_no = devices.next_mgmt_no()
    device_id = db.insert(
        "INSERT INTO devices (mgmt_no, title, source_platform, seller, item_url, note, "
        " purchase_date, purchase_amount, purchase_currency, purchase_fx_rate, purchase_fx_date, "
        " status, is_draft) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'JPY', %s, %s, 'purchased', 0)",
        (mgmt_no, info.title[:_DEVICE_TITLE_MAX], _ensure_platform(info.platform),
         info.seller[:128] or None, info.url, buy["breakdown"] or None,
         buy["purchase_date"], buy["purchase_amount"], buy["purchase_fx_rate"], buy["purchase_fx_date"]),
    )
    devices.log_status(device_id, None, "purchased", "从商品页导入")
    funds.sync_device_and_rebuild(device_id)
    # 整机的商品图是整机外观，进整机本身那一组，不分到某个部件上
    photos = _store_photos(info, lambda blobs: media_api.store_flat_blobs("devices", device_id, blobs))
    return {"id": device_id, "mgmt_no": mgmt_no, **_summary(info, buy), **photos}
