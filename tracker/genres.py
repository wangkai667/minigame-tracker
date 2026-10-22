"""自定义品类口径。

优先级：genres.csv 人工标注 > 同名游戏的抖音品类 > 平台标签规则 > 名称关键词规则 > 未分类。
微信标签很粗（例如很多割草/塔防产品只标"休闲益智"），抖音（MomoRank）给的是单一细分品类，
所以同名游戏优先借用抖音品类。周报会列出仍靠规则或未分类的游戏，人工补进 genres.csv 后就一直沿用。
"""
from __future__ import annotations

import csv
from pathlib import Path

UNCLASSIFIED = "未分类"

# (平台标签里的关键字, 品类)，按顺序匹配
TAG_RULES = [
    ("割草", "割草"),
    ("修仙", "修仙"),
    ("经营", "模拟经营"),
    ("塔防", "塔防"),
    ("消除", "消除"),
    ("合成", "合成"),
    ("MMORPG", "MMO"),
    ("ARPG", "RPG"),
    ("角色扮演", "RPG"),
    ("策略", "SLG"),
    ("战争", "SLG"),
    ("卡牌", "卡牌"),
    ("放置", "放置"),
    ("射击", "射击"),
    ("棋牌", "棋牌"),
    ("纸牌", "棋牌"),
    ("扑克", "棋牌"),
    ("寻物", "益智解谜"),
    ("麻将", "棋牌"),
    ("战术竞技", "动作"),
    ("动作", "动作"),
    ("烧脑", "益智解谜"),
    ("益智", "益智解谜"),
]

# (名称里的关键字, 品类)，标签为空时兜底
NAME_RULES = [
    ("传奇", "传奇"),
    ("斗地主", "棋牌"),
    ("麻将", "棋牌"),
    ("象棋", "棋牌"),
    ("消除", "消除"),
    ("消消", "消除"),
    ("毛线", "消除"),
    ("塔防", "塔防"),
    ("开炮", "塔防"),
    ("模拟器", "模拟"),
    ("餐厅", "模拟经营"),
    ("农场", "模拟经营"),
    ("果园", "模拟经营"),
    ("仙", "修仙"),
    ("射击", "射击"),
    ("狙击", "射击"),
    ("甄嬛", "女性向"),
]


def load_overrides(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row["name"].strip(): row for row in csv.DictReader(f) if row.get("name", "").strip()}


def classify(name: str, tags: str, overrides: dict[str, dict], hints: dict[str, str] | None = None) -> tuple[str, str, str]:
    """返回 (品类, 题材, 来源)，来源为 manual / hint / tag / name / none。

    hints：游戏名 -> 更精确来源（抖音）的品类，优先于本条记录自己的标签，命中时来源记为 hint。
    """
    o = overrides.get(name)
    if o and o.get("genre", "").strip():
        return o["genre"].strip(), (o.get("theme") or "").strip(), "manual"
    hint = (hints or {}).get(name)
    tags = hint or tags or ""
    src = "hint" if hint else "tag"
    for kw, genre in TAG_RULES:
        if kw in tags:
            return genre, "", src
    for kw, genre in NAME_RULES:
        if kw in name:
            return genre, "", "name"
    if tags:
        # 没有命中规则的单一细分品类（如抖音的"竞速""冒险"）直接沿用
        return tags.split(",")[0].strip(), "", src
    return UNCLASSIFIED, "", "none"
