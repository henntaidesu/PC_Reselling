# -*- coding: utf-8 -*-
"""门户身份 → 本系统用户（即「校验双方用户名」）。

1. 按 (portal, sub) 找已绑定的用户——找到就用它。**本系统的用户名不跟着门户改**：
   这里的用户名同时是账号密码登录的登录名，由管理员在用户管理里定，悄悄改掉会让人
   下次用密码登录时登不进去。门户那边的新名字只记进绑定行的 portal_username。
2. 没绑定过：按门户用户名找本系统同名用户（列的排序规则是 _ci，本来就不分大小写），找到就绑上。
3. 都没有：配置允许就以门户用户名新建一个（没有本地密码、不是管理员），不允许就拒绝，
   让管理员先建同名账号。

第 2 步意味着**门户里叫 admin 的人登进来就是这里的 admin**。这正是「两边用户名对上就是同一个人」
的本意，前提是门户的账号由可信的人管——门户那边登记客户端本来就只许管理员。不想要这种自动
匹配的账号，在用户管理里给它换个名字即可（绑定只在首次建立，之后只认 sub）。

同名用户已经绑着**另一个**门户账号时拒绝，不替人改绑：门户里删号重建、或者两个人
先后用过同一个名字，自动改绑等于让后来的人顶替前一个人。管理员在「单点登录」页解绑即可。
删本系统用户时绑定随外键一起删掉，所以不会有「绑着一个不存在的用户」这种行。
"""

from __future__ import annotations

from typing import Any, Dict, List

from src import db
from src.auth import USER_COLUMNS
from src.portal_sso import settings
from src.portal_sso.flow import PROVIDER, SsoError
from src.security import NO_PASSWORD

_USERNAME_MAX = 64   # users.username 的列宽


def _user_by(where: str, params: tuple):
    return db.query_one(f"SELECT {USER_COLUMNS} FROM users WHERE {where} LIMIT 1", params)


def resolve(claims: Dict[str, Any]) -> Dict[str, Any]:
    """返回本系统的 users 行（列见 auth.USER_COLUMNS）。"""
    cfg = settings.get()
    subject = str(claims.get("sub") or "")
    portal_name = str(claims.get("preferred_username") or "").strip()
    display = str(claims.get("name") or "").strip() or portal_name
    if not subject:
        raise SsoError("id_token 里没有 sub")

    user = None
    bound = db.query_one(
        "SELECT user_id FROM sso_identities WHERE provider = %s AND subject = %s",
        (PROVIDER, subject))
    if bound:
        user = _user_by("id = %s", (bound["user_id"],))

    if user is None:
        if not portal_name:
            raise SsoError("门户没有给出用户名（preferred_username）")
        if len(portal_name) > _USERNAME_MAX:
            raise SsoError(f"门户用户名超过 {_USERNAME_MAX} 个字符，本系统存不下")
        user = _user_by("username = %s", (portal_name,))
        if user is not None:
            other = db.query_one(
                "SELECT subject FROM sso_identities WHERE provider = %s AND user_id = %s",
                (PROVIDER, user["id"]))
            if other and other["subject"] != subject:
                raise SsoError(f"本系统用户 {user['username']} 已绑定另一个门户账号。"
                               "如确是同一个人，请管理员在「系统配置 → 单点登录」里解绑后重新登录")
        elif cfg["auto_create"]:
            user_id = db.insert(
                "INSERT INTO users (username, password_hash, display_name, is_active, is_admin) "
                "VALUES (%s, %s, %s, 1, 0)",
                (portal_name, NO_PASSWORD, display[:_USERNAME_MAX] or None))
            user = _user_by("id = %s", (user_id,))
        else:
            raise SsoError(f"本系统里没有用户 {portal_name}，且未开启自动创建。请管理员先建一个同名账号")
        db.execute(
            "INSERT INTO sso_identities (provider, subject, user_id, portal_username) "
            "VALUES (%s, %s, %s, %s)",
            (PROVIDER, subject, user["id"], portal_name))

    if not user["is_active"]:
        raise SsoError("账号已被禁用")

    db.execute(
        "UPDATE sso_identities SET portal_username = %s, last_login_at = NOW() "
        "WHERE provider = %s AND subject = %s", (portal_name, PROVIDER, subject))
    return user


# ---------------------------------------------------------------- 管理页

def list_bindings() -> List[Dict[str, Any]]:
    rows = db.query(
        "SELECT i.id, i.portal_username, i.subject, i.user_id, u.username, u.display_name, "
        "i.created_at, i.last_login_at "
        "FROM sso_identities i JOIN users u ON u.id = i.user_id "
        "WHERE i.provider = %s ORDER BY i.id", (PROVIDER,))
    return [{
        "id": r["id"], "portal_username": r["portal_username"] or "", "portal_sub": r["subject"],
        "user_id": r["user_id"], "username": r["username"],
        "display_name": r["display_name"] or r["username"],
        "created_at": _ts(r["created_at"]), "last_login_at": _ts(r["last_login_at"]),
    } for r in rows]


def bound_users() -> Dict[int, str]:
    """{本系统用户 id: 门户用户名}，用户管理列表标「已绑定门户」用。"""
    rows = db.query("SELECT user_id, portal_username FROM sso_identities WHERE provider = %s",
                    (PROVIDER,))
    return {int(r["user_id"]): r["portal_username"] or "" for r in rows}


def unbind(binding_id: int) -> bool:
    """只删绑定，不动用户。下次从门户登录会重新按用户名匹配。"""
    return db.execute("DELETE FROM sso_identities WHERE id = %s", (binding_id,)) > 0


def _ts(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""
