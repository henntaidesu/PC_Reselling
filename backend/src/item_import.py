# -*- coding: utf-8 -*-
"""从商品页链接自动导入：读出标题、卖家和全部商品图。

支持四种页面，各走各的取数路径，**全部是免登录的纯 HTTP**，不开浏览器：

| 页面                                   | 取法                                          |
|----------------------------------------|-----------------------------------------------|
| 煤炉 ``jp.mercari.com/item/m…``        | ``api.mercari.jp/items/get``，带 DPoP 签名     |
| 煤炉 Shops ``…/shops/product/…``       | ``api.mercari.jp/v1/marketplaces/shops/products`` |
| 雅虎拍卖 ``auctions.yahoo.co.jp/jp/auction/…`` | 公开页的 ``__NEXT_DATA__``            |
| 雅虎二手 ``paypayfleamarket.yahoo.co.jp/item/…`` | 公开页的 ``__NEXT_DATA__``          |

**煤炉为什么不读页面**：商品页是前端渲染的，HTML 里只有 og 标签——标题带着「 by
メルカリ」的后缀，图只有第一张。它自己的前端调的是 ``api.mercari.jp``，要求每个请求带
一个 DPoP 证明（RFC 9449：用一把临时 EC 密钥签的 JWT，公钥放在头里）。那把密钥不需要
在任何地方登记，进程里现造一把即可，所以这里照做，不需要任何账号。

**雅虎只认 ``__NEXT_DATA__`` 里那一个商品节点**：页面上推荐商品、缩放代理到处都是
yimg 的图，全文扫 URL 会把别人的商品图一起导进来。节点读不到时退回 og 标签，至少能
拿到标题和首图——页面改版时宁可少几张图，也不要整个导入报错。

**价格 = 现价 + 送料**，落进购入价（日元）：

* 煤炉 / 煤炉 Shops / 雅虎二手几乎都是「送料込み」（卖家出），送料记 0；煤炉上少数到付的，
  送料要到货才知道，这时只取现价并带一条警告，不瞎填。
* 雅虎拍卖的送料多半是买家出，而且**按收货地的都道府县算**，页面数据里没有，是前端另请求
  ``/web/api/itempage/v1/shipments/…`` 拿的（个人卖家与商店各一个接口）。这里照着请求，
  收货地取「系统配置 → 购买平台」里设的那个都道府县（转运仓库所在地）。现价优先取含税价——
  商店出品页面上显示、实际要付的就是含税价。
* 拍卖已结束时购入日取结束日，其余取导入当天。

**下载图片只放行这几个平台自己的图片域名**，而且不跟随重定向：图片地址来自外部页面，
不设限的话一个指向内网的地址就会让服务端替它去拉（SSRF）。

这里只负责「读」，不碰数据库；落库与传图床在 ``api/import_api.py``。
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

log = logging.getLogger(__name__)

TIMEOUT = 15
# 一件商品最多导多少张图。煤炉上限 20 张，雅虎 10 张；与 media_api 的单次上限一致。
MAX_PHOTOS = 20
MAX_IMAGE_BYTES = 20 * 1024 * 1024

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_HTML_HEADERS = {"User-Agent": _UA, "Accept-Language": "ja,en;q=0.8"}

# 图片只从这些域名下载（后缀匹配）。见模块 docstring 的 SSRF 一段。
_IMAGE_HOST_SUFFIXES = (
    ".mercdn.net",                  # 煤炉 static.mercdn.net
    ".mercari-shops-static.com",    # 煤炉 Shops
    ".yimg.jp",                     # 雅虎拍卖 / 雅虎二手 auctions.c.yimg.jp
)

_EXT_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


class ItemImportError(RuntimeError):
    """导入失败，``message`` 直接给用户看。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class ItemInfo:
    # source 是页面种类（决定怎么取），platform 是落进 source_platform 的字典 key。
    # 煤炉 Shops 与煤炉是同一个平台、同一个 App 里买的，所以 platform 相同。
    source: str
    platform: str
    item_id: str
    url: str
    title: str = ""
    seller: str = ""
    photos: List[str] = field(default_factory=list)
    # 日元。price 是现价（拍卖为当前价 / 落札价，含税优先）；shipping 为 0 表示卖家出，
    # None 表示不知道（到付 / 送料接口没取到），此时购入价只含现价，warnings 里说明
    price: Optional[int] = None
    shipping: Optional[int] = None
    shipping_label: str = ""     # 「送料込み」或运输方式名，写进备注留底
    purchase_date: Optional[dt.date] = None
    warnings: List[str] = field(default_factory=list)


# ── 链接识别 ────────────────────────────────────────────────────────── #

# (正则, source, platform, 规范链接模板)。规范链接是落进 item_url 的那一份，
# 也是查重的依据：同一件商品从 App 分享出来的链接常带一串跟踪参数，原样存下来就查不出重。
_PATTERNS: List[Tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"mercari\.com/(?:[a-z]{2}/)?item/(m\d+)", re.I),
     "mercari", "mercari", "https://jp.mercari.com/item/{}"),
    (re.compile(r"mercari\.com/(?:[a-z]{2}/)?shops/product/([A-Za-z0-9]+)", re.I),
     "mercari_shops", "mercari", "https://jp.mercari.com/shops/product/{}"),
    (re.compile(r"mercari-shops\.com/products/([A-Za-z0-9]+)", re.I),
     "mercari_shops", "mercari", "https://jp.mercari.com/shops/product/{}"),
    (re.compile(r"auctions\.yahoo\.co\.jp/jp/auction/([a-z]?\d+)", re.I),
     "yahoo_auction", "yahoo", "https://auctions.yahoo.co.jp/jp/auction/{}"),
    (re.compile(r"paypayfleamarket\.yahoo\.co\.jp/item/(z\d+)", re.I),
     "yahoo_flea", "paypay", "https://paypayfleamarket.yahoo.co.jp/item/{}"),
]


def parse_url(text: str) -> ItemInfo:
    """从用户粘贴的内容里认出是哪个平台的哪件商品。

    粘贴的常常不是干净的链接，而是 App 分享出来的一段话（「〇〇を出品中！ https://…」），
    所以在整段文字里找，而不是要求整串就是一个 URL。
    """
    raw = (text or "").strip()
    for pattern, source, platform, template in _PATTERNS:
        m = pattern.search(raw)
        if m:
            item_id = m.group(1)
            return ItemInfo(source=source, platform=platform, item_id=item_id,
                            url=template.format(item_id))
    raise ItemImportError("认不出这个链接。支持煤炉（含 Shops）、雅虎拍卖、雅虎二手的商品页。")


# ── 煤炉 ───────────────────────────────────────────────────────────── #

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class _Dpop:
    """DPoP 证明生成器。密钥在进程内现造，每个请求签一个新的 JWT（jti / iat 不同）。"""

    def __init__(self):
        self._key = ec.generate_private_key(ec.SECP256R1())
        nums = self._key.public_key().public_numbers()
        self._jwk = {
            "crv": "P-256", "kty": "EC",
            "x": _b64(nums.x.to_bytes(32, "big")),
            "y": _b64(nums.y.to_bytes(32, "big")),
        }

    def proof(self, method: str, url: str) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self._jwk}
        payload = {"iat": int(time.time()), "jti": str(uuid.uuid4()),
                   "htu": url, "htm": method, "uuid": str(uuid.uuid4())}
        signing_input = ".".join(
            _b64(json.dumps(part, separators=(",", ":")).encode()) for part in (header, payload)
        )
        der = self._key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        # JWS 要的是 r||s 定长拼接，cryptography 给的是 DER，得拆开重拼
        r, s = decode_dss_signature(der)
        return signing_input + "." + _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


_dpop: Optional[_Dpop] = None


def _mercari_get(url: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    global _dpop
    if _dpop is None:
        _dpop = _Dpop()
    headers = {
        # htu 不含查询串（RFC 9449 §4.2），所以签的是不带参数的 url
        "DPoP": _dpop.proof("GET", url),
        "X-Platform": "web",
        "User-Agent": _UA,
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ItemImportError(f"连不上煤炉：{exc}") from exc
    if resp.status_code == 404:
        raise ItemImportError("煤炉上找不到这件商品（可能已被删除）")
    if not resp.ok:
        raise ItemImportError(f"煤炉返回 HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise ItemImportError("煤炉返回的不是 JSON，接口可能改版了")


def _fetch_mercari(info: ItemInfo) -> None:
    data = _mercari_get("https://api.mercari.jp/items/get", {"id": info.item_id}).get("data") or {}
    info.title = str(data.get("name") or "")
    info.seller = str((data.get("seller") or {}).get("name") or "")
    info.photos = [str(p) for p in (data.get("photos") or []) if p]
    info.price = _to_int(data.get("price"))
    payer = data.get("shipping_payer") or {}
    _set_seller_paid(info, str(payer.get("code") or "").lower() == "seller")


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _set_seller_paid(info: ItemInfo, seller_paid: bool) -> None:
    """送料込み → 送料 0；到付 → 送料未知，只记现价。"""
    if seller_paid:
        info.shipping, info.shipping_label = 0, "送料込み"
    else:
        info.shipping_label = "着払い"
        info.warnings.append("这件是到付（着払い），送料未计入购入价，到货后请手动加上")


def _fetch_mercari_shops(info: ItemInfo) -> None:
    data = _mercari_get(
        f"https://api.mercari.jp/v1/marketplaces/shops/products/{info.item_id}", {"view": "FULL"}
    )
    detail = data.get("productDetail") or {}
    info.title = str(data.get("displayName") or "")
    info.seller = str((detail.get("shop") or {}).get("displayName") or "")
    # Shops 的图默认给 webp（「…@webp」），换成 jpg：图床和各处缩略图对 jpg 最稳
    info.photos = [re.sub(r"@webp$", "@jpg", str(p)) for p in (detail.get("photos") or []) if p]
    info.price = _to_int(data.get("price"))
    payer = detail.get("shippingPayer") or {}
    _set_seller_paid(info, str(payer.get("code") or "").upper() == "SELLER")


# ── 雅虎 ───────────────────────────────────────────────────────────── #

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_OG_RE = re.compile(r'<meta[^>]+property="og:(title|image)"[^>]+content="([^"]*)"', re.I)


def _get_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HTML_HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ItemImportError(f"打不开商品页：{exc}") from exc
    if resp.status_code == 404:
        raise ItemImportError("商品页不存在（可能已删除或已过公开期）")
    if not resp.ok:
        raise ItemImportError(f"商品页返回 HTTP {resp.status_code}")
    resp.encoding = "utf-8"
    return resp.text


def _next_data(html: str) -> Dict[str, Any]:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except ValueError:
        return {}


def _dig(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _og_fallback(info: ItemInfo, html: str, title_suffix: str) -> None:
    """``__NEXT_DATA__`` 读不出来时的退路：og 标签里的标题与首图。"""
    import html as html_lib

    og = {k.lower(): html_lib.unescape(v) for k, v in _OG_RE.findall(html)}
    title = og.get("title", "")
    if title_suffix and title.endswith(title_suffix):
        title = title[: -len(title_suffix)]
    info.title = info.title or title.strip()
    if not info.photos and og.get("image"):
        info.photos = [og["image"]]


_YAHOO_SHIPMENTS = "https://auctions.yahoo.co.jp/web/api/itempage/v1/shipments"


def _auction_id(item: Dict[str, Any]) -> str:
    return str(item.get("auctionId") or "")


def _yahoo_shipping(item: Dict[str, Any], price: int, pref_code: int) -> Tuple[Optional[int], str]:
    """问雅虎「寄到 pref_code 要多少送料」，返回 ``(最低送料, 运输方式名)``；取不到返回 (None, "")。

    参数照着商品页前端的写法拼：商店出品走 ``/shopping``（按商店的送料设定 + 重量 + 价格算，
    满额包邮就是在这里体现的），个人卖家走 ``/auction/items/{aid}``。
    """
    shop = item.get("aucShoppingItemInfo") or {}
    shop_info = shop.get("shoppingItemInfo") or {}
    if shop.get("shoppingSellerId") and shop_info:
        differed = bool(shop.get("isShoppingDifferedPaymentEnabled"))
        url = f"{_YAHOO_SHIPMENTS}/shopping"
        params = {
            "prefCode": pref_code,
            "sellerId": shop["shoppingSellerId"],
            "itemCode": (shop.get("shoppingItemCode") if not differed and shop.get("shoppingItemCode")
                         else _auction_id(item)),
            "price": price,
            "postageSet": (shop.get("postageSetId") if differed and shop.get("postageSetId")
                           else shop_info.get("postageSet")),
            "weight": (shop.get("weight") if differed and shop.get("weight")
                       else shop_info.get("weight")),
        }
        params = {k: v for k, v in params.items() if v is not None}
    else:
        url = f"{_YAHOO_SHIPMENTS}/auction/items/{_auction_id(item)}"
        params = {"prefCode": pref_code, "aid": _auction_id(item)}
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT, headers={
            **_HTML_HEADERS, "Accept": "application/json",
            "Referer": f"https://auctions.yahoo.co.jp/jp/auction/{_auction_id(item)}",
        })
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("雅虎拍卖 %s 送料查询失败：%s", _auction_id(item), exc)
        return None, ""
    return _to_int(data.get("lowestPrice")), str(data.get("mainMethodName") or "")


def _fetch_yahoo_auction(info: ItemInfo, pref_code: int) -> None:
    html = _get_html(info.url)
    data = _next_data(html)
    # 拍卖页的数据在 pageProps 底下，老一点的页面直接挂在 props 上，两处都看
    item = (_dig(data, "props", "pageProps", "initialState", "item", "detail", "item")
            or _dig(data, "props", "initialState", "item", "detail", "item"))
    if not (isinstance(item, dict) and _auction_id(item) == info.item_id):
        log.info("雅虎拍卖 %s 没读到 __NEXT_DATA__ 商品节点，退回 og 标签", info.item_id)
        _og_fallback(info, html, " - Yahoo!オークション")
        info.warnings.append("页面结构没认出来，价格与送料未能读取")
        return

    info.title = str(item.get("title") or "")
    info.seller = str(_dig(item, "seller", "displayName") or "")
    info.photos = [str(i.get("image")) for i in (item.get("img") or [])
                   if isinstance(i, dict) and i.get("image")]
    # 商店出品的 price 是税抜，页面上大字显示、实际要付的是 taxinPrice
    info.price = _to_int(item.get("taxinPrice")) or _to_int(item.get("price"))
    if item.get("status") == "closed" and item.get("endTime"):
        try:
            info.purchase_date = dt.datetime.fromisoformat(str(item["endTime"])).date()
        except ValueError:
            pass

    if item.get("chargeForShipping") == "seller":
        info.shipping, info.shipping_label = 0, "送料無料"
    elif info.price is not None:
        info.shipping, info.shipping_label = _yahoo_shipping(item, info.price, pref_code)
        if info.shipping is None:
            info.warnings.append("送料没查到（可能是着払い或需要询价），未计入购入价")


def _fetch_yahoo_flea(info: ItemInfo) -> None:
    html = _get_html(info.url)
    item = _dig(_next_data(html), "props", "initialState", "itemsState", "items", "item")
    if isinstance(item, dict) and str(item.get("id") or "") == info.item_id:
        info.title = str(item.get("title") or "")
        info.seller = str(_dig(item, "seller", "nickname") or "")
        info.photos = [str(i.get("url")) for i in (item.get("images") or [])
                       if isinstance(i, dict) and i.get("url")]
        info.price = _to_int(item.get("price"))
        # 雅虎二手规定一律送料込み（出品者負担），没有到付这个选项
        info.shipping, info.shipping_label = 0, "送料込み"
    else:
        log.info("雅虎二手 %s 没读到 __NEXT_DATA__ 商品节点，退回 og 标签", info.item_id)
        _og_fallback(info, html, "")


_FETCHERS = {
    "mercari": _fetch_mercari,
    "mercari_shops": _fetch_mercari_shops,
    "yahoo_flea": _fetch_yahoo_flea,
}


def fetch(text: str, pref_code: int = 13) -> ItemInfo:
    """认链接 + 读商品。标题读不到算失败——那多半是页面结构变了，导一行空壳进来没有意义。

    ``pref_code`` 是雅虎拍卖算送料用的收货都道府县（1–47，13 = 东京都），别的平台用不到。
    """
    info = parse_url(text)
    if info.source == "yahoo_auction":
        _fetch_yahoo_auction(info, pref_code)
    else:
        _FETCHERS[info.source](info)
    info.title = info.title.strip()
    if not info.title:
        raise ItemImportError("读不到商品标题，页面结构可能变了，请改用手动录入")
    seen, photos = set(), []
    for url in info.photos:
        if url not in seen:
            seen.add(url)
            photos.append(url)
    info.photos = photos[:MAX_PHOTOS]
    return info


# ── 下载图片 ──────────────────────────────────────────────────────── #

def _image_host_allowed(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host.endswith(s) for s in _IMAGE_HOST_SUFFIXES)


def download_photos(info: ItemInfo) -> Tuple[List[Tuple[str, bytes, str]], List[Dict[str, str]]]:
    """把商品图下载成 ``(文件名, 内容, content_type)``，逐张独立成败。

    返回 ``(成功的, 失败的)``，失败项与 media_api 的上传结果同形（filename + error），
    前端可以合在一起提示。
    """
    blobs: List[Tuple[str, bytes, str]] = []
    errors: List[Dict[str, str]] = []
    referer = f"{urlsplit(info.url).scheme}://{urlsplit(info.url).hostname}/"
    for n, url in enumerate(info.photos, start=1):
        label = f"{info.item_id}_{n}"
        if not _image_host_allowed(url):
            errors.append({"filename": label, "error": "图片地址不在允许的域名内"})
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": _UA, "Referer": referer},
                                timeout=TIMEOUT, stream=True, allow_redirects=False)
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            # 雅虎二手的图床回的是不标准的 image/jpg，不纠正的话图床按扩展名白名单可能不认
            if content_type == "image/jpg":
                content_type = "image/jpeg"
            if not content_type.startswith("image/"):
                raise ItemImportError(f"不是图片（{content_type or '无类型'}）")
            content = resp.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
            if len(content) > MAX_IMAGE_BYTES:
                raise ItemImportError("图片超过 20MB")
        except (requests.RequestException, ItemImportError) as exc:
            msg = exc.message if isinstance(exc, ItemImportError) else str(exc)
            log.warning("下载商品图 %s 失败：%s", url, msg)
            errors.append({"filename": label, "error": msg})
            continue
        ext = _EXT_BY_TYPE.get(content_type, "jpg")
        blobs.append((f"{label}.{ext}", content, content_type))
    return blobs, errors
