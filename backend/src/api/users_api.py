# -*- coding: utf-8 -*-
"""用户管理（系统配置 → 用户，仅管理员）。

本系统的权限只有两档：管理员（系统配置里那些会改全局的东西）和普通用户（其余全部）。
货、资金池不按用户隔离——归属人（owner）是出资人名单，不是登录账号，两者刻意不挂钩：
出资人可以从来不登录，一个人也可以既用密码又从门户登进来。

三条护栏，少一条都会把人锁在门外：

- **不能对自己做「停用 / 取消管理员 / 删除」**：点下去的那一刻自己的令牌就作废了，
  而能把它改回来的页面正是刚刚失去权限的这个。
- **至少留一个启用中的管理员**：否则再没有人进得了系统配置，只能去库里手改。
- **凡是「从此不该再让旧令牌进来」的改动都让 token_version +1**：重置密码、停用、
  强制下线。令牌默认永不过期（auth.py），不 +1 的话停用之前签出去的那张照样能用。

门户单点登录建的号没有本地密码（security.NO_PASSWORD），这里重置一次密码它就能两种方式登录。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src import db
from src.auth import USER_COLUMNS, public_user, require_admin
from src.portal_sso import identity
from src.security import NO_PASSWORD, hash_password

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


class UserCreatePayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    # 不给 = 没有本地密码，只能从门户登录（先建好同名账号再让他从门户进来就是这种）
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    display_name: Optional[str] = Field(default=None, max_length=64)
    is_admin: bool = False


class UserUpdatePayload(BaseModel):
    username: Optional[str] = Field(default=None, min_length=1, max_length=64)
    display_name: Optional[str] = Field(default=None, max_length=64)
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class PasswordPayload(BaseModel):
    password: str = Field(min_length=8, max_length=128)


def _ts(value) -> Optional[str]:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _serialize(row: dict, bound: dict) -> dict:
    return {
        **public_user(row),
        "is_active": bool(row["is_active"]),
        "portal_username": bound.get(int(row["id"])),   # None = 没绑门户
        "last_login_at": _ts(row["last_login_at"]),
        "last_active_at": _ts(row["last_active_at"]),
        "created_at": _ts(row["created_at"]),
    }


def _get(user_id: int) -> dict:
    row = db.query_one(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,))
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return row


def _one(user_id: int) -> dict:
    return _serialize(_get(user_id), identity.bound_users())


def _clean_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    return name


def _name_taken(name: str, exclude_id: int = 0) -> bool:
    # username 列是 _ci 排序规则，Admin 与 admin 算重名——这里的判断与唯一索引同一口径
    return db.query_one("SELECT id FROM users WHERE username = %s AND id <> %s",
                        (name, exclude_id)) is not None


def _other_admins(user_id: int) -> int:
    return int(db.query_scalar(
        "SELECT COUNT(*) AS c FROM users WHERE is_admin = 1 AND is_active = 1 AND id <> %s",
        (user_id,), default=0) or 0)


def _guard_admin_loss(row: dict, me: int, action: str) -> None:
    """row 这个人即将失去「启用中的管理员」身份时调。"""
    if int(row["id"]) == me:
        raise HTTPException(status_code=400, detail=f"不能{action}自己的账号")
    if row["is_admin"] and row["is_active"] and _other_admins(row["id"]) == 0:
        raise HTTPException(status_code=400, detail=f"这是最后一个启用中的管理员，不能{action}")


@router.get("")
def list_users():
    rows = db.query(f"SELECT {USER_COLUMNS} FROM users ORDER BY id")
    bound = identity.bound_users()
    return [_serialize(r, bound) for r in rows]


@router.post("")
def create_user(payload: UserCreatePayload):
    name = _clean_name(payload.username)
    if _name_taken(name):
        raise HTTPException(status_code=400, detail=f"用户名 {name} 已存在")
    user_id = db.insert(
        "INSERT INTO users (username, password_hash, display_name, is_active, is_admin) "
        "VALUES (%s, %s, %s, 1, %s)",
        (name, hash_password(payload.password) if payload.password else NO_PASSWORD,
         (payload.display_name or "").strip() or None, 1 if payload.is_admin else 0),
    )
    return _one(user_id)


@router.put("/{user_id}")
def update_user(user_id: int, payload: UserUpdatePayload, claims: dict = Depends(require_admin)):
    row = _get(user_id)
    me = int(claims["user_id"])
    sets, params = [], []

    if payload.username is not None:
        name = _clean_name(payload.username)
        if name != row["username"]:
            if _name_taken(name, user_id):
                raise HTTPException(status_code=400, detail=f"用户名 {name} 已存在")
            # 改名不作废令牌：令牌里的 username 只是展示用，认人认的是 sub（用户 id）
            sets.append("username = %s")
            params.append(name)
    if payload.display_name is not None:
        sets.append("display_name = %s")
        params.append(payload.display_name.strip() or None)
    if payload.is_admin is not None and bool(payload.is_admin) != bool(row["is_admin"]):
        if not payload.is_admin:
            _guard_admin_loss(row, me, "取消管理员")
        sets.append("is_admin = %s")
        params.append(1 if payload.is_admin else 0)
    if payload.is_active is not None and bool(payload.is_active) != bool(row["is_active"]):
        if not payload.is_active:
            _guard_admin_loss(row, me, "停用")
            # 停用必须作废已签发的令牌，否则那张永不过期的票还能一直用下去
            sets.append("token_version = token_version + 1")
        sets.append("is_active = %s")
        params.append(1 if payload.is_active else 0)

    if sets:
        db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", (*params, user_id))
    return _one(user_id)


@router.post("/{user_id}/password")
def reset_password(user_id: int, payload: PasswordPayload):
    _get(user_id)
    # 与「改自己的密码」同一个道理：只换哈希不动版本号，泄露出去的令牌照样能用
    db.execute(
        "UPDATE users SET password_hash = %s, token_version = token_version + 1 WHERE id = %s",
        (hash_password(payload.password), user_id),
    )
    return _one(user_id)


@router.post("/{user_id}/revoke")
def revoke_sessions(user_id: int):
    """强制下线：这个人所有设备上的登录全部作废，下一个请求就 401。"""
    _get(user_id)
    db.execute("UPDATE users SET token_version = token_version + 1 WHERE id = %s", (user_id,))
    return _one(user_id)


@router.delete("/{user_id}")
def delete_user(user_id: int, claims: dict = Depends(require_admin)):
    row = _get(user_id)
    _guard_admin_loss(row, int(claims["user_id"]), "删除")
    # 门户绑定随外键级联删掉；业务数据不挂用户，删账号不动任何货和账
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    return {"ok": True}
