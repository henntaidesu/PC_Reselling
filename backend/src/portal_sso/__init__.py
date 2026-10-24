# -*- coding: utf-8 -*-
"""门户（D:\\Project\\Portal）单点登录：门户当 OIDC 提供方，本系统当客户端。

与 FreeMarket_Manager 的 ``portal_sso`` 同一套做法，拆法也一样：

- settings.py  配置（系统配置 → 单点登录），存在 app_settings
- flow.py      授权码 + PKCE 流程、id_token 校验、一次性票
- identity.py  门户身份 → 本系统用户（按 sub 认人，首次按用户名匹配，没有就新建）

HTTP 端点在 api/sso_api.py：登录用的那几条公开，配置与绑定管理挂 require_admin。
"""
