# -*- coding: utf-8 -*-
"""归属人 / 出资人 = 用户系统里的人。

货的归属人（``cards`` / ``devices`` / ``device_parts`` 的 ``owner_id``）与资金池的出资人
（``fund_injections`` / ``fund_draws`` 的 ``contributor_id``）都指向 ``users.id``——
「货是谁的、钱从谁的池里扣、这笔钱是谁出的」说的是同一批人，就是能登进系统的这些账号。

**为什么存 id 而不是名字**：用户名和显示名都能在用户管理里改。存名字的话，改一次名就得
把五张表里的历史行全部跟着改一遍，漏一张（或者改名那一刻正好有一次自动保存带着旧名字
落库），那个人的池子就从中间断成两截，按人汇总也成了两个人，而页面上看不出任何异常。
存 id 之后改名是零成本的：显示时现查，所有地方同时换成新名字。

**显示名**：``display_name`` 有值就用它，否则用用户名（``shown_name``）。所以「甘」这种
称呼放在显示名里，登录用的用户名可以是 makuro——两者各管各的，谁改了都不影响账。
显示名在用户之间不许重复（users_api 里校验）：列表上的归属人标签、资金池的按人汇总
都只显示这个名字，两个同名的人在那些地方分不开。

**停用的人**：仍然是历史货与历史注资的归属人 / 出资人，名字照常显示，只是不再出现在
下拉候选里（前端 OwnerSelect 只列启用的，外加当前已选的那一个）。存量行每次自动保存
都会原样回传它的 owner_id，所以 ``check`` 不拦停用的人——拦了的话，停用一个人会让他名下
每一件货都存不进去。**删人**则在 users_api 里被挡住：名下还有货或钱的人删不掉
（外键也是 RESTRICT），停用即可。

老的 ``owner`` / ``contributor`` 名字列与 ``fund_contributors`` 字典只留不删，不再读写，
迁移见 schema._migrate_owner_to_users。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from src import db

# 「显示出来的那个名字」的 SQL 写法。唯一性校验要在库里比，和 shown_name 必须同一个口径
SHOWN_NAME_SQL = "COALESCE(NULLIF(TRIM(display_name), ''), username)"

# 引用了用户的列：(表, 列, 说明)。删人前数一遍，也是迁移时要回填的那几列
REFERENCES = (
    ("cards", "owner_id", "张显卡"),
    ("devices", "owner_id", "台整机"),
    ("device_parts", "owner_id", "个部件"),
    ("fund_injections", "contributor_id", "笔注资"),
    ("fund_draws", "contributor_id", "笔扣款"),
)


def shown_name(row: Dict[str, Any]) -> str:
    return (row.get("display_name") or "").strip() or row["username"]


def names() -> Dict[int, str]:
    """{用户 id: 显示名}。用户表只有几行，每次现查一遍，不做缓存——缓存就得记得在
    改名、新建、门户自动建号这几处各失效一次，漏一处就是一个显示旧名字的页面。"""
    return {int(r["id"]): shown_name(r)
            for r in db.query("SELECT id, username, display_name FROM users")}


def name_of(user_id: Any, table: Optional[Dict[int, str]] = None) -> Optional[str]:
    """把一个 id 换成显示名。批量序列化时传入 ``names()`` 的结果，免得逐行查库。"""
    if not user_id:
        return None
    table = names() if table is None else table
    return table.get(int(user_id))


def candidates() -> List[Dict[str, Any]]:
    """下拉候选：全部用户，含停用的（历史行要靠它显示名字），由前端只把启用的列出来。"""
    rows = db.query("SELECT id, username, display_name, is_active FROM users ORDER BY id")
    out = [{
        "id": int(r["id"]),
        "name": shown_name(r),
        "username": r["username"],
        "is_active": bool(r["is_active"]),
    } for r in rows]
    out.sort(key=lambda x: (not x["is_active"], x["name"]))
    return out


def check(user_id: Optional[int], label: str = "归属人") -> Optional[int]:
    """写入前确认这个人存在。空 = 未指定，原样放行；停用的人也放行（理由见模块文档）。"""
    if not user_id:
        return None
    if not db.query_one("SELECT id FROM users WHERE id = %s", (int(user_id),)):
        raise HTTPException(status_code=400, detail=f"{label}不存在，可能刚被删除，请刷新页面后重选")
    return int(user_id)


def reference_counts(user_id: int) -> List[str]:
    """这个人名下还挂着哪些东西，比如 ["20 张显卡", "36 笔注资"]。空列表 = 可以删。"""
    out = []
    for table, col, unit in REFERENCES:
        # 表名与列名只来自上面那张固定的表
        n = int(db.query_scalar(
            f"SELECT COUNT(*) AS c FROM {table} WHERE {col} = %s", (user_id,), default=0) or 0)
        if n:
            out.append(f"{n} {unit}")
    return out


def reject_legacy(data: Any, *fields: str) -> Any:
    """给请求体的 ``model_validator(mode="before")`` 用：见到老的名字字段就拒绝。

    归属人改成 id 之前的前端，每次保存都带着 ``owner`` / ``contributor`` 名字字段，却没有
    新的 id 字段——放过去的话 id 被当成「没填」，那件货的归属人在一次自动保存里就被清空，
    池子里的扣款跟着删掉。升级后还开着的旧标签页发的正是这种请求，所以直接拒绝，让人刷新。
    """
    if isinstance(data, dict) and any(f in data for f in fields):
        raise ValueError("页面版本过旧（归属人已改为从用户系统选择），请刷新页面后再保存")
    return data
