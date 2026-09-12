# -*- coding: utf-8 -*-
"""登录、改密、当前用户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src import db
from src.auth import create_access_token, require_auth
from src.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class ChangePasswordPayload(BaseModel):
    # 不收原密码：这是一个单人自用的库存工具，改密码的入口本身已经在 Bearer JWT 后面，
    # 再验一遍原密码挡不住「令牌已经泄露」之外的任何情形，只是每次改密多敲一遍。
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/login")
def login(payload: LoginPayload):
    user = db.query_one(
        "SELECT id, username, password_hash, is_active, is_admin, token_version "
        "FROM users WHERE username = %s LIMIT 1",
        (payload.username.strip(),),
    )
    # 用户不存在和密码错误回同一句话：分开提示等于送给攻击者一个用户名枚举接口。
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    token = create_access_token(user["id"], user["username"], user["token_version"] or 0)
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "is_admin": bool(user["is_admin"]),
        },
    }


@router.get("/me")
def me(claims: dict = Depends(require_auth)):
    return {
        "id": claims["user_id"],
        "username": claims.get("username"),
        "is_admin": bool(claims.get("is_admin")),
    }


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
