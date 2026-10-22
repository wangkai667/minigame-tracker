from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from . import db, notify, sources
from .genres import load_overrides
from .report import Reporter

ROOT = Path(__file__).resolve().parent.parent
CST = dt.timezone(dt.timedelta(hours=8))  # 榜单按北京时间记日期，与机器时区无关

DEFAULT_CONFIG = {
    "notify": {"provider": "serverchan", "key": ""},
    "lists": ["wx_bestsell", "wx_popular", "wx_new", "dy_bestsell", "dy_popular", "dy_new"],
    "weekly_weekday": 1,  # 1=周一 ... 7=周日
    "rise_threshold": 3,
    "db_path": "data/tracker.db",
}

log = logging.getLogger("tracker")


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    path = ROOT / "config.json"
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in user.items() if k != "notify"})
        cfg["notify"].update(user.get("notify", {}))
    # 环境变量优先，方便不落盘密钥
    if os.environ.get("TRACKER_PUSH_KEY"):
        cfg["notify"]["key"] = os.environ["TRACKER_PUSH_KEY"]
    return cfg


def setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        ROOT / "logs" / "tracker.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[fh, sh])


def today() -> str:
    return dt.datetime.now(CST).date().isoformat()


def do_fetch(conn, cfg, date: str) -> list[str]:
    errors = []
    for key in cfg["lists"]:
        try:
            items = sources.fetch(key)
            db.save_snapshot(conn, date, key, items)
            log.info("saved %s %s: %d items", date, key, len(items))
        except Exception as e:
            log.exception("fetch %s failed", key)
            errors.append(f"{key}: {e}")
    return errors


def emit(cfg, title: str, body: str, dry_run: bool) -> None:
    if dry_run:
        print(f"# {title}\n\n{body}")
        return
    notify.send(cfg["notify"], title, body)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="tracker", description="小游戏榜单追踪与微信推送")
    p.add_argument("--date", help="指定日期 YYYY-MM-DD，默认北京时间今天")
    p.add_argument("--dry-run", action="store_true", help="只打印，不推送")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="定时任务入口：抓取 → 日报；到周报日再发周报")
    sub.add_parser("fetch", help="只抓取入库")
    sub.add_parser("daily", help="生成并推送日报")
    sub.add_parser("weekly", help="生成并推送周报")
    sub.add_parser("test-push", help="发一条测试消息，检查推送配置")
    args = p.parse_args(argv)

    setup_logging()
    cfg = load_config()
    date = args.date or today()
    conn = db.connect(ROOT / cfg["db_path"])
    reporter = Reporter(conn, load_overrides(ROOT / "genres.csv"), cfg["lists"], cfg["rise_threshold"])

    try:
        if args.cmd == "test-push":
            emit(cfg, "小游戏追踪：推送测试", f"配置正常，{date}", args.dry_run)
        elif args.cmd == "fetch":
            errors = do_fetch(conn, cfg, date)
            return 1 if errors else 0
        elif args.cmd == "daily":
            emit(cfg, *reporter.daily(date), args.dry_run)
        elif args.cmd == "weekly":
            emit(cfg, *reporter.weekly(date), args.dry_run)
        elif args.cmd == "run":
            errors = do_fetch(conn, cfg, date)
            title, body = reporter.daily(date)
            if errors:
                title += "（部分抓取失败）"
                body = "**抓取失败**：\n" + "\n".join(f"- {e}" for e in errors) + "\n\n" + body
            emit(cfg, title, body, args.dry_run)
            if dt.date.fromisoformat(date).isoweekday() == cfg["weekly_weekday"]:
                emit(cfg, *reporter.weekly(date), args.dry_run)
            return 1 if errors else 0
    except notify.NotifyError as e:
        log.error("%s", e)
        return 2
    return 0
