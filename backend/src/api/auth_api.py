# -*- coding: utf-8 -*-
"""登录、改密、当前用户。门户单点登录在 sso_api.py，两条路的登录响应都出自 auth.issue_login。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src import db
from src.auth import USER_COLUMNS, issue_login, public_user, require_auth
from src.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class ChangePasswordPayload(BaseModel):
    # 不收原密码：改密码的入口本身已经在 Bearer JWT 后面，再验一遍原密码挡不住「令牌已经泄露」
    # 之外的任何情形，只是每次改密多敲一遍。门户建的号本来就没有原密码，这里也是他设密码的入口。
    new_password: str = Field(min_length=8, max_length=128)


class ProfilePayload(BaseModel):
    display_name: str = Field(default="", max_length=64)


@router.post("/login")
def login(payload: LoginPayload):
    user = db.query_one(
        f"SELECT {USER_COLUMNS} FROM users WHERE username = %s LIMIT 1",
        (payload.username.strip(),),
    )
    # 用户不存在和密码错误回同一句话：分开提示等于送给攻击者一个用户名枚举接口。
    # 门户建的号没有本地密码（security.NO_PASSWORD），verify_password 对它恒为 False，也落在这里
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return issue_login(user)


def _me_row(claims: dict) -> dict:
    row = db.query_one(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (claims["user_id"],))
    if not row:
        raise HTTPException(status_code=401, detail="用户不存在或登录已失效")
    return row


@router.get("/me")
def me(claims: dict = Depends(require_auth)):
    # 从库里读而不是回令牌里的声明：管理员可能刚改过他的用户名 / 显示名 / 密码，
    # 令牌永不过期，里面那份可能是很久以前的
    return public_user(_me_row(claims))


@router.put("/profile")
def update_profile(payload: ProfilePayload, claims: dict = Depends(require_auth)):
    """只许改显示名。用户名是登录名，由管理员在用户管理里改，自己改了容易登不进来。"""
    db.execute("UPDATE users SET display_name = %s WHERE id = %s",
               (payload.display_name.strip() or None, claims["user_id"]))
    return public_user(_me_row(claims))


@router.post("/change-password")
def change_password(payload: ChangePasswordPayload, claims: dict = Depends(require_auth)):
    user = db.query_one(
        "SELECT id, password_hash, token_version FROM users WHERE id = %s",
        (claims["user_id"],),
    )
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    # token_version 自增 → 所有已签发的旧令牌立刻失效。改密码的意义就在这里：
    # 只改哈希不动版本号的话，泄露出去的那个令牌照样能继续用。
    db.execute(
        "UPDATE users SET password_hash = %s, token_version = token_version + 1 WHERE id = %s",
        (hash_password(payload.new_password), user["id"]),
    )
    return {"ok": True, "message": "密码已修改，请重新登录"}
