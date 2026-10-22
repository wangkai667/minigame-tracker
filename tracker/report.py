"""日报 / 周报：从快照库计算变化并生成 Markdown。"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

from . import db
from .genres import classify
from .sources import LISTS

# 品类份额只看真实排名榜（新游榜按上线时间波动，不计入）
SHARE_LISTS = ["wx_bestsell", "wx_popular", "dy_bestsell", "dy_popular"]


def _label(key: str) -> str:
    platform, name = LISTS[key][:2]
    return f"{platform}{name}"


def _days_before(date: str, n: int) -> str:
    return (dt.date.fromisoformat(date) - dt.timedelta(days=n)).isoformat()


class Reporter:
    def __init__(self, conn: sqlite3.Connection, overrides: dict, lists: list[str], rise_threshold: int = 3):
        self.conn = conn
        self.overrides = overrides
        self.lists = lists
        self.share_lists = [k for k in SHARE_LISTS if k in lists]
        self.rise_threshold = rise_threshold
        # 同名游戏借用抖音的细分品类
        self.hints = {
            r["name"]: r["tags"]
            for r in conn.execute("SELECT name, tags FROM games WHERE game_id LIKE 'dy:%' AND tags<>''")
        }

    def classify(self, row) -> tuple[str, str, str]:
        return classify(row["name"], row["tags"], self.overrides, self.hints)

    def genre(self, row) -> str:
        return self.classify(row)[0]

    def _tagged(self, row) -> str:
        return f"{row['name']}（{self.genre(row)}）"

    # ---------- 日报 ----------
    def daily(self, date: str) -> tuple[str, str]:
        parts = []
        for key in self.lists:
            today = db.ranking(self.conn, key, date)
            if not today:
                parts.append(f"### {_label(key)}\n今日抓取失败或无数据\n")
                continue
            prev = db.prev_date(self.conn, key, date)
            parts.append(self._daily_list(key, today, prev))
        for key in self.share_lists:
            if key.endswith("_bestsell"):
                parts.append(self._share_section(key, date, None))
        return f"小游戏日报 {date[5:]}", "\n".join(parts)

    def _daily_list(self, key: str, today, prev: str | None) -> str:
        lines = [f"### {_label(key)}"]
        if not prev:
            lines.append("首次建库，明天起显示变化。今日前 10：")
            lines += [f"{r['rank']}. {self._tagged(r)}" for r in today[:10]]
            return "\n".join(lines) + "\n"
        before = {r["game_id"]: r for r in db.ranking(self.conn, key, prev)}
        now_ids = {r["game_id"] for r in today}
        new = [r for r in today if r["game_id"] not in before]
        dropped = [r for gid, r in before.items() if gid not in now_ids]
        moves = [
            (before[r["game_id"]]["rank"] - r["rank"], r)
            for r in today if r["game_id"] in before
        ]
        up = sorted([m for m in moves if m[0] >= self.rise_threshold], key=lambda m: -m[0])[:5]
        down = sorted([m for m in moves if m[0] <= -self.rise_threshold], key=lambda m: m[0])[:3]

        if new:
            lines.append("**新进榜**：" + "、".join(f"{self._tagged(r)} #{r['rank']}" for r in new))
        if up:
            lines.append("**上升**：" + "、".join(f"{r['name']} ↑{d}→#{r['rank']}" for d, r in up))
        if down:
            lines.append("**下降**：" + "、".join(f"{r['name']} ↓{-d}→#{r['rank']}" for d, r in down))
        if dropped:
            lines.append("**跌出**：" + "、".join(r["name"] for r in dropped))
        if len(lines) == 1:
            lines.append(f"较 {prev[5:]} 无明显变化")
        return "\n".join(lines) + "\n"

    # ---------- 品类份额 ----------
    def share(self, key: str, date: str) -> dict[str, tuple[int, int]]:
        """品类 -> (款数, 加权分)。加权分：第 1 名 N 分 ... 第 N 名 1 分。"""
        rows = db.ranking(self.conn, key, date)
        n = len(rows)
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in rows:
            g = out[self.genre(r)]
            g[0] += 1
            g[1] += n + 1 - r["rank"]
        return {k: (v[0], v[1]) for k, v in out.items()}

    def _share_section(self, key: str, date: str, base_date: str | None) -> str:
        now = self.share(key, date)
        if not now:
            return ""
        base = self.share(key, base_date) if base_date else {}
        total = sum(v[1] for v in now.values()) or 1
        base_total = sum(v[1] for v in base.values()) or 1
        rows = []
        for g in set(now) | set(base):
            c, s = now.get(g, (0, 0))
            bc, bs = base.get(g, (0, 0))
            rows.append((g, c, s / total * 100, bc, bs / base_total * 100))
        title = f"### {_label(key)} 品类份额"
        if base_date:
            title += f"（对比 {base_date[5:]}）"
            rows.sort(key=lambda x: -(x[2] - x[4]))
            body = [
                f"- {g}：{c} 款，{p:.0f}%（{'+' if p - bp >= 0 else ''}{p - bp:.0f}pt，上期 {bc} 款）"
                for g, c, p, bc, bp in rows
            ]
        else:
            rows.sort(key=lambda x: -x[2])
            body = [f"- {g}：{c} 款，{p:.0f}%" for g, c, p, _, _ in rows if c]
        return "\n".join([title, *body]) + "\n"

    # ---------- 周报 ----------
    def weekly(self, date: str) -> tuple[str, str]:
        week_ago = _days_before(date, 7)
        parts = [f"统计区间：{week_ago} ~ {date}。份额 = 名次加权（第 1 名权重最高），按份额变化从高到低排列。\n"]
        for key in self.share_lists:
            base = db.date_on_or_before(self.conn, key, week_ago)
            if base is None:
                base = self._earliest(key)
                if base == date:
                    base = None
            parts.append(self._share_section(key, date, base))
            parts.append(self._weekly_movers(key, date, base))
        parts.append(self._weekly_new_games(date, week_ago))
        parts.append(self._needs_review(date, week_ago))
        return f"小游戏周报 {date[5:]}", "\n".join(p for p in parts if p)

    def _earliest(self, key: str) -> str | None:
        return self.conn.execute("SELECT MIN(date) FROM snapshots WHERE list=?", (key,)).fetchone()[0]

    def _weekly_movers(self, key: str, date: str, base: str | None) -> str:
        if not base:
            return ""
        before = {r["game_id"]: r["rank"] for r in db.ranking(self.conn, key, base)}
        moves = []
        for r in db.ranking(self.conn, key, date):
            if r["game_id"] in before:
                d = before[r["game_id"]] - r["rank"]
                if d >= self.rise_threshold:
                    moves.append((d, f"{self._tagged(r)} ↑{d}→#{r['rank']}"))
            else:
                moves.append((100, f"{self._tagged(r)} 新进→#{r['rank']}"))
        if not moves:
            return ""
        moves.sort(key=lambda m: -m[0])
        return f"**{_label(key)} 本周上升**：\n" + "\n".join(f"- {m[1]}" for m in moves[:8]) + "\n"

    def _weekly_new_games(self, date: str, since: str) -> str:
        rows = self.conn.execute(
            "SELECT * FROM games WHERE first_seen>? AND first_seen<=? ORDER BY first_seen", (since, date)
        ).fetchall()
        if not rows:
            return ""
        by_genre: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            by_genre[self.genre(r)].append(r["name"])
        lines = [f"### 本周首次出现的游戏（{len(rows)} 款，按品类）"]
        for g, names in sorted(by_genre.items(), key=lambda x: -len(x[1])):
            lines.append(f"- {g}（{len(names)}）：{'、'.join(names)}")
        return "\n".join(lines) + "\n"

    def _needs_review(self, date: str, since: str, limit: int = 30) -> str:
        """列出未分类的游戏和本周新出现但只靠粗规则分类的游戏；抖音细分品类视为可靠，不列出。"""
        seen, todo, rule_only = set(), [], 0
        for key in self.lists:
            for r in db.ranking(self.conn, key, date):
                if r["name"] in seen:
                    continue
                seen.add(r["name"])
                genre, _, src = self.classify(r)
                if src == "none":
                    todo.append(f"{r['name']}（未分类）")
                elif src in ("tag", "name") and not r["game_id"].startswith("dy:"):
                    if r["first_seen"] > since:
                        todo.append(f"{r['name']}（规则判为{genre}）")
                    else:
                        rule_only += 1
        if not todo and not rule_only:
            return ""
        lines = ["### 品类待标注（补进 genres.csv 后份额更准）"]
        if todo:
            more = f" 等 {len(todo)} 款" if len(todo) > limit else ""
            lines.append("、".join(todo[:limit]) + more)
        if rule_only:
            lines.append(f"另有 {rule_only} 款按微信标签或名称规则分类，未人工确认")
        return "\n".join(lines) + "\n"
