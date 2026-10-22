"""推送到个人微信：Server酱（默认）或 PushPlus。"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)


class NotifyError(RuntimeError):
    pass


def _post(url: str, data: bytes, content_type: str) -> dict:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def serverchan(key: str, title: str, body: str) -> None:
    # Server酱³ 的 key 形如 sctp123tXXXX，走独立域名；Turbo 版走 sctapi
    m = re.match(r"^sctp(\d+)t", key)
    url = f"https://{m.group(1)}.push.ft07.com/send/{key}.send" if m else f"https://sctapi.ftqq.com/{key}.send"
    data = urllib.parse.urlencode({"title": title[:32], "desp": body}).encode()
    res = _post(url, data, "application/x-www-form-urlencoded")
    if res.get("code") != 0:
        raise NotifyError(f"Server酱返回 {res}")


def pushplus(token: str, title: str, body: str) -> None:
    data = json.dumps({"token": token, "title": title, "content": body, "template": "markdown"}).encode()
    res = _post("https://www.pushplus.plus/send", data, "application/json")
    if res.get("code") != 200:
        raise NotifyError(f"PushPlus返回 {res}")


PROVIDERS = {"serverchan": serverchan, "pushplus": pushplus}


def send(cfg: dict, title: str, body: str) -> None:
    provider = cfg.get("provider", "serverchan")
    key = cfg.get("key", "")
    if not key:
        raise NotifyError("config.json 里没有配置 notify.key")
    if provider not in PROVIDERS:
        raise NotifyError(f"未知推送渠道 {provider}，可选 {list(PROVIDERS)}")
    PROVIDERS[provider](key, title, body)
    log.info("pushed via %s: %s", provider, title)
