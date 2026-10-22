"""榜单抓取。

- 微信：应用宝网页版（sj.qq.com），Next.js 页面内嵌 __NEXT_DATA__，每榜前 20。
- 抖音：MomoRank（momorank.com，数据每日更新），App Router 的 RSC 数据流，
  免费公开每榜前 10（完整 200 名需付费，这里只取公开部分）。
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# key -> (平台, 中文名, URL, 解析器名)
# 微信热门榜目前与人气榜内容相同，默认不抓（见 cli.DEFAULT_CONFIG）。
LISTS = {
    "wx_bestsell": ("微信", "畅销榜", "https://sj.qq.com/wechat-game/best-sell-game-rank", "yyb"),
    "wx_popular": ("微信", "人气榜", "https://sj.qq.com/wechat-game/popular-game-rank", "yyb"),
    "wx_new": ("微信", "新游榜", "https://sj.qq.com/wechat-game/new-game-rank", "yyb"),
    "wx_hot": ("微信", "热门榜", "https://sj.qq.com/wechat-game/hot-game-list", "yyb"),
    "dy_bestsell": ("抖音", "畅销榜", "https://www.momorank.com/douyin/rankings/bestseller", "momorank"),
    "dy_popular": ("抖音", "热门榜", "https://www.momorank.com/douyin/rankings/popular", "momorank"),
    "dy_new": ("抖音", "新游榜", "https://www.momorank.com/douyin/rankings/new_game", "momorank"),
}

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class FetchError(RuntimeError):
    pass


def _get(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:  # 网络抖动时退避重试
            last = e
            log.warning("fetch %s failed (%d/%d): %s", url, attempt + 1, retries, e)
            time.sleep(3 * (attempt + 1))
    raise FetchError(f"{url}: {last}")


def parse_yyb(html: str) -> list[dict]:
    m = _NEXT_DATA.search(html)
    if not m:
        raise FetchError("页面里没有 __NEXT_DATA__，页面结构可能变了")
    data = json.loads(m.group(1))
    components = data["props"]["pageProps"]["dynamicCardResponse"]["data"]["components"]
    items = next((c["data"]["itemData"] for c in components if c.get("data", {}).get("itemData")), None)
    if not items:
        raise FetchError("没有找到 itemData，页面结构可能变了")
    out = []
    for rank, it in enumerate(items, 1):
        out.append({
            "rank": rank,
            "game_id": it.get("pkg_name") or it.get("app_id"),
            "name": (it.get("name") or "").strip(),
            "developer": (it.get("developer") or "").strip(),
            "tags": (it.get("tags") or "").strip(),
        })
    return out


_RSC_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)


def parse_momorank(html: str) -> list[dict]:
    # RSC 数据以 JS 字符串分片下发：先拼回原文，再定位排行组件的 items 数组
    stream = "".join(json.loads('"' + c + '"') for c in _RSC_CHUNK.findall(html))
    anchor = stream.find('"detailQuery"')
    start = stream.find('"items":', anchor)
    if anchor < 0 or start < 0:
        raise FetchError("没有找到排行数据，MomoRank 页面结构可能变了")
    items, _ = json.JSONDecoder().raw_decode(stream, start + len('"items":'))
    if not items:
        raise FetchError("MomoRank 排行为空")
    return [
        {
            "rank": it["rank"],
            "game_id": it.get("appId") or f"momorank:{it['gameId']}",
            "name": (it.get("name") or "").strip(),
            "developer": (it.get("publisher") or "").strip(),
            "tags": (it.get("category") or "").strip(),
        }
        for it in items
    ]


PARSERS = {"yyb": parse_yyb, "momorank": parse_momorank}


def fetch(key: str) -> list[dict]:
    _, _, url, parser = LISTS[key]
    return PARSERS[parser](_get(url))
