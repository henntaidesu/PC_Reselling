# -*- coding: utf-8 -*-
"""门户单点登录的端点（流程与各步的理由见 src/portal_sso/flow.py）。

公开（正是没登录的人才用它们，不挂 require_auth）：

    GET  /sso/status     登录页问：本系统开没开单点登录、按钮写什么
    GET  /sso/login      跳板页，浏览器算出本系统地址后去 /start。门户卡片的「门户登录」入口就是它
    GET  /sso/start      303 去门户授权，顺手种下 state 临时 Cookie
    GET  /sso/callback   门户跳回来，303 回登录页并带上一次性票
    POST /sso/exchange   前端拿票换 JWT

管理员（系统配置 → 单点登录）：

    GET/PUT /sso/config   配置；Client Secret 不回传明文，只说配没配，和图床 Token 一个做法
    POST    /sso/test     用已保存的配置读门户发现文档
    GET     /sso/bindings
    DELETE  /sso/bindings/{id}

/start 与 /callback 是浏览器的顶层跳转，出错时 303 回登录页带 ``sso_error``，不回 JSON——
回一段 JSON 的话用户看到的是满屏大括号，而他只是点了个「门户登录」。
"""

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from src.auth import issue_login, require_admin
from src.portal_sso import flow, identity, settings

router = APIRouter(prefix="/sso", tags=["sso"])
_ADMIN = [Depends(require_admin)]


class ExchangePayload(BaseModel):
    ticket: str = Field(min_length=1, max_length=128)


class SsoConfigPayload(BaseModel):
    enabled: Optional[bool] = None
    portal_url: Optional[str] = Field(default=None, max_length=255)
    internal_url: Optional[str] = Field(default=None, max_length=255)
    client_id: Optional[str] = Field(default=None, max_length=64)
    # 留空 = 不修改已保存的 Secret
    client_secret: Optional[str] = Field(default=None, max_length=255)
    auto_create: Optional[bool] = None
    button_label: Optional[str] = Field(default=None, max_length=20)


def _to_login(base: str, **params: str) -> RedirectResponse:
    """回到前端登录页（hash 路由）。查询串放在 # 后面，不会发到服务端、也不进反代日志。"""
    query = "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items() if v)
    return RedirectResponse(f"{base}#/login?{query}", status_code=303,
                            headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- 登录流程（公开）

@router.get("/status")
def sso_status():
    cfg = settings.get()
    return {"enabled": settings.is_active(cfg), "label": cfg["button_label"]}


# 跳板页。base 不信任请求参数（门户推导的那个只到门户根），由浏览器从自己的地址里算：
# 被门户代理时 pathname 是 /api/proxy/<id>/api/v1/sso/login，剥掉 LOGIN_PATH 就是站点根
_TRAMPOLINE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta name="referrer" content="no-referrer"><title>门户登录</title>
<style>body{{background:#0b1220;color:#94a3b8;font:14px sans-serif;text-align:center;padding-top:30vh}}</style>
</head><body>正在跳转到门户……
<script>
(function () {{
  var p = location.pathname, tail = {tail};
  var i = p.lastIndexOf(tail);
  var root = location.origin + (i >= 0 ? p.slice(0, i) : '/');
  location.replace(root + {start} + '?base=' + encodeURIComponent(root));
}})();
</script>
<noscript>需要启用 JavaScript 才能使用门户登录。</noscript>
</body></html>"""


@router.get("/login", response_class=HTMLResponse)
def sso_login():
    html = _TRAMPOLINE.format(tail=json.dumps(flow.LOGIN_PATH),
                              start=json.dumps(flow.SSO_PREFIX[1:] + "/start"))
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/start")
def sso_start(request: Request, base: str = ""):
    origin = flow.normalize_base(base) or str(request.base_url)
    if not settings.is_active():
        return _to_login(origin, sso_error="本系统未开启门户单点登录（系统配置 → 单点登录）")
    url, packed = flow.begin(origin)
    resp = RedirectResponse(url, status_code=303, headers={"Cache-Control": "no-store"})
    resp.set_cookie(
        flow.STATE_COOKIE, packed, max_age=flow.STATE_TTL, httponly=True,
        secure=request.url.scheme == "https",
        # 必须是 lax：从门户跳回来那一下是顶层导航，直接访问时还是跨站的，strict 会让浏览器不带它
        samesite="lax",
        # 被门户代理时 Path 会被改写成 /api/proxy/<id>/，回调也在那底下，一样带得上
        path=flow.SSO_PREFIX,
    )
    return resp


@router.get("/callback")
def sso_callback(request: Request, code: str = "", state: str = "",
                 error: str = "", error_description: str = ""):
    raw = request.cookies.get(flow.STATE_COOKIE, "")
    base = str(request.base_url)
    try:
        saved = flow.unpack_state(raw)
        base = saved.get("base") or base
        if not settings.is_active():
            raise flow.SsoError("本系统未开启门户单点登录")
        if error:
            raise flow.SsoError(f"{error} {error_description}".strip())
        if not code:
            raise flow.SsoError("门户没有返回授权码")
        # state 对不上 = 这次回调不是我们发出去的那一次（CSRF，或两个标签页各点了一次）
        if not state or state != saved.get("state"):
            raise flow.SsoError("state 对不上，这次登录被丢弃")
        user = identity.resolve(flow.exchange(code, saved))
    except flow.SsoError as exc:
        resp = _to_login(base, sso_error=str(exc))
    else:
        resp = _to_login(base, sso_ticket=flow.issue_ticket(issue_login(user)))
    resp.delete_cookie(flow.STATE_COOKIE, path=flow.SSO_PREFIX)
    return resp


@router.post("/exchange")
def sso_exchange(payload: ExchangePayload):
    data = flow.redeem_ticket(payload.ticket)
    if data is None:
        raise HTTPException(status_code=401, detail="登录票无效或已过期，请重新点一次门户登录")
    return data


# ---------------------------------------------------------------- 配置（管理员）

def _config() -> dict:
    cfg = settings.get()
    return {
        "enabled": cfg["enabled"],
        "active": settings.is_active(cfg),
        "configured": settings.is_configured(cfg),
        "portal_url": cfg["portal_url"],
        "internal_url": cfg["internal_url"],
        "client_id": cfg["client_id"],
        "secret_set": bool(cfg["client_secret"]),
        "auto_create": cfg["auto_create"],
        "button_label": cfg["button_label"],
        # 门户里要登记的回调地址 = 浏览器看到的本系统地址 + 它。前端按 location 拼，
        # 被门户代理时拼出来的就是代理后的那个
        "callback_path": flow.CALLBACK_PATH,
        "login_path": flow.LOGIN_PATH,
    }


@router.get("/config", dependencies=_ADMIN)
def get_config():
    return _config()


@router.put("/config", dependencies=_ADMIN)
def save_config(payload: SsoConfigPayload):
    try:
        settings.save(**payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _config()


@router.post("/test", dependencies=_ADMIN)
def test_config():
    """用**已保存**的配置读门户的发现文档：先保存再测，测的才是真正会生效的那份。"""
    try:
        info = flow.probe()
    except flow.SsoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": f"门户可达，签发方 {info['issuer']} 与配置一致"}


@router.get("/bindings", dependencies=_ADMIN)
def list_bindings():
    return identity.list_bindings()


@router.delete("/bindings/{binding_id}", dependencies=_ADMIN)
def delete_binding(binding_id: int):
    if not identity.unbind(binding_id):
        raise HTTPException(status_code=404, detail="绑定不存在")
    return {"ok": True}
