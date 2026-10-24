# -*- coding: utf-8 -*-
"""门户单点登录的配置读写（系统配置 → 单点登录）。

存在 app_settings，与图床、汇率源同一套机制，网页上改完下一次登录就生效。这里**不加缓存**：
只有登录那一下才读，一次登录读几个键，不值得为它维护失效逻辑。

**本系统这边打开开关且配齐了才生效**（:func:`is_active`）。门户那边登记了本系统也没用——
单点登录要两边都同意：门户在卡片上登记客户端，本系统打开自己的配置项。
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from src import settings_store

K_ENABLED = "portal_sso_enabled"            # '1' 开 / 其它 关
K_PORTAL_URL = "portal_sso_portal_url"      # 浏览器访问门户的地址 = id_token 的 iss
K_INTERNAL_URL = "portal_sso_internal_url"  # 本机后端访问门户的地址（换 token 用），留空同上
K_CLIENT_ID = "portal_sso_client_id"
K_CLIENT_SECRET = "portal_sso_client_secret"
K_AUTO_CREATE = "portal_sso_auto_create"    # '0' 关：本系统没有同名用户时拒绝而不是新建
K_BUTTON_LABEL = "portal_sso_button_label"  # 登录页按钮文案，空 = 前端的默认译文

_KEYS = (K_ENABLED, K_PORTAL_URL, K_INTERNAL_URL, K_CLIENT_ID, K_CLIENT_SECRET,
         K_AUTO_CREATE, K_BUTTON_LABEL)


def normalize_url(raw: Optional[str]) -> str:
    """只接受 ``http(s)://host[:port][/path]``，去掉末尾的 /；非法一律返回空串（= 未配置）。

    末尾的 / 必须去掉：门户的 issuer 不带它，而 id_token 的 iss 是逐字比对的。
    """
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        return ""
    return value


def get() -> Dict[str, Any]:
    v = settings_store.get_many(_KEYS)
    return {
        "enabled": (v[K_ENABLED] or "") == "1",
        "portal_url": normalize_url(v[K_PORTAL_URL]),
        "internal_url": normalize_url(v[K_INTERNAL_URL]),
        "client_id": (v[K_CLIENT_ID] or "").strip(),
        "client_secret": v[K_CLIENT_SECRET] or "",
        "auto_create": (v[K_AUTO_CREATE] or "1") != "0",
        "button_label": (v[K_BUTTON_LABEL] or "").strip(),
    }


def is_configured(cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or get()
    return bool(cfg["portal_url"] and cfg["client_id"] and cfg["client_secret"])


def is_active(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """开着且配齐。只开不填等于没开——不然登录页会出现一个点了就报错的按钮。"""
    cfg = cfg or get()
    return cfg["enabled"] and is_configured(cfg)


def token_base(cfg: Dict[str, Any]) -> str:
    """后端换 token 用的门户地址。门户对外是域名、本机直连走内网 IP 时两者不同。"""
    return cfg["internal_url"] or cfg["portal_url"]


def save(*, enabled: Optional[bool] = None, portal_url: Optional[str] = None,
         internal_url: Optional[str] = None, client_id: Optional[str] = None,
         client_secret: Optional[str] = None, auto_create: Optional[bool] = None,
         button_label: Optional[str] = None) -> None:
    """None = 不改这一项。client_secret 留空 = 不改（前端拿不到明文，不能要求每次都重填）。"""
    s = settings_store.set
    if portal_url is not None:
        url = normalize_url(portal_url)
        if portal_url.strip() and not url:
            raise ValueError("门户地址格式不对，应为 http(s)://域名[:端口]")
        s(K_PORTAL_URL, url)
    if internal_url is not None:
        url = normalize_url(internal_url)
        if internal_url.strip() and not url:
            raise ValueError("内网地址格式不对，应为 http(s)://IP[:端口]")
        s(K_INTERNAL_URL, url)
    if client_id is not None:
        s(K_CLIENT_ID, client_id.strip())
    if client_secret:
        s(K_CLIENT_SECRET, client_secret.strip())
    if auto_create is not None:
        s(K_AUTO_CREATE, auto_create)
    if button_label is not None:
        s(K_BUTTON_LABEL, button_label.strip()[:20])
    if enabled is not None:
        # 最后写开关：配置不齐时拒绝打开，免得登录页挂一个注定失败的按钮
        if enabled and not is_configured():
            raise ValueError("请先填齐门户地址、Client ID 和 Client Secret 再开启")
        s(K_ENABLED, enabled)
