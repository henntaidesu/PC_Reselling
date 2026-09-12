# -*- coding: utf-8 -*-
"""图片 / 视频的上传、排序、删除：显卡按五个分类，整机部件平铺一组。

文件本体一律走图床，本项目的库里只存指针（stored_name + public_url）。这样做的直接
好处是：这个程序打包成 exe 换机器运行、甚至同时开两份，图片都还在原地。

显卡和部件共用同一套上传流程（``_store_files``），只有「落哪张表」不同：显卡的图分
五类（外观 / PCB / 核心 / GPU-Z / mods），而一条内存、一块主板拍的就是它本身，没有
可分的类别，所以部件那边是平铺的一组。

平铺这一组有**两种归属**：整机部件（device_part_media）和整机本身（device_media，
拍的是整机外观 / 铭牌 / 开机测试）。两者表结构、上传、列出、删除完全同构，只有表名和
外键列不同，所以下面用 ``_FLAT_OWNERS`` 参数化成一套代码，路由则各自显式声明——
写成 ``/{owner}/{id}`` 会和 ``/card/{card_id}`` 撞上，靠注册顺序分胜负太脆。
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src import cards, db
from src.auth import require_auth
from src.media import ImageHostingClient, ImageHostingError
from src.schema import MEDIA_CATEGORIES

log = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"], dependencies=[Depends(require_auth)])

# 单次请求的文件数上限。图床侧也有自己的限制，这里先挡一道，免得一次拖 200 个文件
# 进来在内存里全部读完才发现超限。
MAX_FILES_PER_REQUEST = 20

VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "m4v", "mkv", "avi"}


def _kind_of(filename: str, content_type: str) -> str:
    if (content_type or "").lower().startswith("video/"):
        return "video"
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    return "video" if ext in VIDEO_EXTENSIONS else "image"


def _guess_content_type(filename: str, provided: Optional[str]) -> str:
    if provided and provided != "application/octet-stream":
        return provided
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


class ReorderPayload(BaseModel):
    """按前端拖拽后的顺序提交 media id 列表。显卡与平铺那两种归属共用这一个形状。"""
    media_ids: List[int]


async def _store_files(files, key_prefix: str, base_order: int, insert_row):
    """把一批文件传到图床，成功一个落库一个。显卡与部件共用。

    逐个文件独立成败：一个失败不影响其余，响应里分别列出成功和失败的项。批量传 10 张
    照片时最后一张格式不对就整批回滚，用户得重新选 10 个文件——这种设计是在惩罚用户。

    ``insert_row(kind, stored_name, public_url, filename, content_type, size, sort_order)``
    负责把这一条写进对应的表并返回给前端的那个 dict。
    """
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400, detail=f"一次最多上传 {MAX_FILES_PER_REQUEST} 个文件"
        )
    try:
        client = ImageHostingClient()
    except ImageHostingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    uploaded, errors = [], []
    for offset, upload_file in enumerate(files):
        filename = upload_file.filename or f"file_{offset}"
        try:
            content = await upload_file.read()
        finally:
            await upload_file.close()
        if not content:
            errors.append({"filename": filename, "error": "文件为空"})
            continue

        digest = hashlib.sha256(content).hexdigest()
        content_type = _guess_content_type(filename, upload_file.content_type)
        kind = _kind_of(filename, content_type)
        # external_key 让图床侧幂等：同一份内容重复上传不会产生第二个文件。
        # 用「归属 + 内容摘要」而不是文件名——手机相册里到处都是 IMG_0001.jpg。
        external_key = f"{key_prefix}-{digest[:32]}"

        try:
            result = client.upload(
                filename=filename,
                content=content,
                content_type=content_type,
                external_key=external_key,
                sha256=digest,
            )
        except ImageHostingError as exc:
            log.warning("上传 %s 到图床失败：%s", filename, exc)
            errors.append({"filename": filename, "error": exc.message})
            continue

        stored_name = result.get("stored_name") or result.get("filename") or ""
        public_url = result.get("url") or ""
        if not stored_name or not public_url:
            errors.append({"filename": filename, "error": "图床未返回存储名或访问地址"})
            continue

        uploaded.append(insert_row(
            kind, stored_name, public_url, filename, content_type,
            len(content), base_order + offset,
        ))

    return {"uploaded": uploaded, "errors": errors}


def _purge_from_hosting(stored_name: str) -> bool:
    """删图床上的本体。删不掉也要让调用方把本地记录删掉——否则界面上一直挂着一个点不开
    的坏链接，用户反复点删除反复失败；图床上留个孤儿文件是可接受的代价。"""
    try:
        ImageHostingClient().delete(stored_name)
        return True
    except ImageHostingError as exc:
        log.warning("删除图床文件 %s 失败，仅移除本地记录：%s", stored_name, exc)
        return False


@router.post("/upload")
async def upload(
    card_id: int = Form(...),
    category: str = Form(...),
    files: List[UploadFile] = File(...),
):
    """上传一批文件到某张卡的某个分类。"""
    if category not in MEDIA_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"未知分类：{category}")
    if not db.query_one("SELECT id FROM cards WHERE id = %s", (card_id,)):
        raise HTTPException(status_code=404, detail="显卡不存在")

    # 追加到分类末尾，不打乱已有顺序
    base_order = int(db.query_scalar(
        "SELECT COALESCE(MAX(sort_order), -1) AS m FROM card_media "
        "WHERE card_id = %s AND category = %s",
        (card_id, category), default=-1,
    ) or -1) + 1

    def insert_row(kind, stored_name, public_url, filename, content_type, size, sort_order):
        media_id = db.insert(
            "INSERT INTO card_media "
            "(card_id, category, kind, stored_name, public_url, filename, mime_type, "
            " size_bytes, sort_order) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (card_id, category, kind, stored_name, public_url, filename[:255],
             content_type[:128], size, sort_order),
        )
        return {
            "id": media_id, "card_id": card_id, "category": category, "kind": kind,
            "stored_name": stored_name, "public_url": public_url, "filename": filename,
            "mime_type": content_type, "size_bytes": size, "sort_order": sort_order,
        }

    return await _store_files(files, f"card{card_id}-{category}", base_order, insert_row)


# ── 平铺一组图：整机部件 / 整机本身 ────────────────────────────────────── #

# 归属 → (媒体表, 外键列, 归属表, 报错时的称呼, 图床 external_key 前缀)
_FLAT_OWNERS = {
    "parts": ("device_part_media", "part_id", "device_parts", "部件", "part"),
    "devices": ("device_media", "device_id", "devices", "设备", "device"),
}


def _flat_row(owner: str, row) -> dict:
    _table, fk, _owner_table, _label, _prefix = _FLAT_OWNERS[owner]
    return {
        "id": row["id"],
        # 前端只认 owner_id 这一个名字，两种归属的响应因此完全同形
        "owner_id": row[fk],
        fk: row[fk],
        "kind": row["kind"],
        "stored_name": row["stored_name"],
        "public_url": row["public_url"],
        "filename": row["filename"],
        "mime_type": row["mime_type"],
        "size_bytes": int(row["size_bytes"]) if row["size_bytes"] is not None else None,
        "sort_order": row["sort_order"],
    }


async def _upload_flat(owner: str, owner_id: int, files):
    """给一个部件 / 一台整机传图。

    归属必须先存在（有 id）才能挂文件：文件是挂在行上的，行还没有，文件就无处可去。
    部件那一行由前端在上传前先存一次建出来（详情页的 ensurePartId），所以界面上不再
    需要「先填点什么才能传图」这条规矩。
    """
    table, fk, owner_table, label, prefix = _FLAT_OWNERS[owner]
    if not db.query_one(f"SELECT id FROM {owner_table} WHERE id = %s", (owner_id,)):
        raise HTTPException(status_code=404, detail=f"{label}不存在")

    # 追加到末尾，不打乱已有顺序
    base_order = int(db.query_scalar(
        f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM {table} WHERE {fk} = %s",
        (owner_id,), default=-1,
    ) or -1) + 1

    def insert_row(kind, stored_name, public_url, filename, content_type, size, sort_order):
        media_id = db.insert(
            f"INSERT INTO {table} "
            f"({fk}, kind, stored_name, public_url, filename, mime_type, size_bytes, sort_order) "
            f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (owner_id, kind, stored_name, public_url, filename[:255],
             content_type[:128], size, sort_order),
        )
        return {
            "id": media_id, "owner_id": owner_id, fk: owner_id, "kind": kind,
            "stored_name": stored_name, "public_url": public_url, "filename": filename,
            "mime_type": content_type, "size_bytes": size, "sort_order": sort_order,
        }

    return await _store_files(files, f"{prefix}{owner_id}", base_order, insert_row)


def _list_flat(owner: str, owner_id: int) -> dict:
    table, fk, _owner_table, _label, _prefix = _FLAT_OWNERS[owner]
    rows = db.query(
        f"SELECT * FROM {table} WHERE {fk} = %s ORDER BY sort_order, id", (owner_id,))
    return {"items": [_flat_row(owner, r) for r in rows]}


def _reorder_flat(owner: str, owner_id: int, media_ids: List[int]) -> dict:
    """按传入顺序重排某个归属名下的图。一次事务写完，不会留下「排到一半」的中间态。

    WHERE 里带上归属列：请求里混进别的部件的 media id 时，它只会被忽略，而不是顺手把
    那一组的顺序也改了。
    """
    table, fk, _owner_table, _label, _prefix = _FLAT_OWNERS[owner]
    if not media_ids:
        return {"ok": True, "updated": 0}
    with db.transaction() as cur:
        for order, media_id in enumerate(media_ids):
            cur.execute(
                f"UPDATE {table} SET sort_order = %s WHERE id = %s AND {fk} = %s",
                (order, media_id, owner_id),
            )
    return {"ok": True, "updated": len(media_ids)}


def _delete_flat(owner: str, media_id: int, purge: bool) -> dict:
    table, _fk, _owner_table, _label, _prefix = _FLAT_OWNERS[owner]
    row = db.query_one(f"SELECT id, stored_name FROM {table} WHERE id = %s", (media_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    purged = _purge_from_hosting(row["stored_name"]) if purge else False
    db.execute(f"DELETE FROM {table} WHERE id = %s", (media_id,))
    return {"ok": True, "purged": purged}


# 路由各写各的：表名从上面那张固定的表里取，不进 SQL 的用户输入，也不会和
# /card/{card_id} 抢同一个形状的路径。

@router.post("/parts/{part_id}")
async def upload_part_media(part_id: int, files: List[UploadFile] = File(...)):
    return await _upload_flat("parts", part_id, files)


@router.get("/parts/{part_id}")
def list_part_media(part_id: int):
    return _list_flat("parts", part_id)


@router.put("/parts/{part_id}/reorder")
def reorder_part_media(part_id: int, payload: ReorderPayload):
    return _reorder_flat("parts", part_id, payload.media_ids)


@router.delete("/parts/items/{media_id}")
def delete_part_media(media_id: int, purge: bool = True):
    return _delete_flat("parts", media_id, purge)


@router.post("/devices/{device_id}")
async def upload_device_media(device_id: int, files: List[UploadFile] = File(...)):
    return await _upload_flat("devices", device_id, files)


@router.get("/devices/{device_id}")
def list_device_media(device_id: int):
    return _list_flat("devices", device_id)


@router.put("/devices/{device_id}/reorder")
def reorder_device_media(device_id: int, payload: ReorderPayload):
    return _reorder_flat("devices", device_id, payload.media_ids)


@router.delete("/devices/items/{media_id}")
def delete_device_media(media_id: int, purge: bool = True):
    return _delete_flat("devices", media_id, purge)


@router.get("/card/{card_id}")
def list_for_card(card_id: int):
    grouped = {c: [] for c in MEDIA_CATEGORIES}
    for item in cards.load_media([card_id]).get(card_id, []):
        grouped.setdefault(item["category"], []).append(item)
    return grouped


@router.put("/reorder")
def reorder(payload: ReorderPayload):
    """按传入顺序重排。一次事务写完，不会出现「排到一半」的中间态。"""
    if not payload.media_ids:
        return {"ok": True, "updated": 0}
    with db.transaction() as cur:
        for order, media_id in enumerate(payload.media_ids):
            cur.execute("UPDATE card_media SET sort_order = %s WHERE id = %s", (order, media_id))
    return {"ok": True, "updated": len(payload.media_ids)}


@router.delete("/{media_id}")
def delete_media(media_id: int, purge: bool = True):
    """删除一个文件。``purge=true``（默认）连图床上的本体一起删。

    这里默认删本体，和删整张卡时的默认相反：删单个文件是用户对着那张图点的删除，
    意图明确；删卡是一次波及几十个文件的操作，误删代价大得多。
    """
    row = db.query_one("SELECT id, stored_name FROM card_media WHERE id = %s", (media_id,))
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")

    purged = _purge_from_hosting(row["stored_name"]) if purge else False
    db.execute("DELETE FROM card_media WHERE id = %s", (media_id,))
    return {"ok": True, "purged": purged}
