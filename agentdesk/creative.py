"""Stable, curated visual identities for children's projects."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


PALETTES = [
    {"name": "汽水星球", "background": "#081A2B", "surface": "#12324A", "primary": "#38D6C7", "accent": "#FFD166", "text": "#F4FBFF"},
    {"name": "草莓晚霞", "background": "#27152F", "surface": "#4A2448", "primary": "#FF718D", "accent": "#FFC857", "text": "#FFF7F2"},
    {"name": "青柠实验室", "background": "#10251F", "surface": "#193D32", "primary": "#A8E063", "accent": "#56CCF2", "text": "#F6FFF2"},
    {"name": "蓝莓太空", "background": "#11152F", "surface": "#252958", "primary": "#8F8CFF", "accent": "#FF7EC7", "text": "#F8F7FF"},
    {"name": "橘子海岸", "background": "#192636", "surface": "#27435A", "primary": "#FF9F43", "accent": "#4DD4AC", "text": "#FFF9EF"},
    {"name": "云朵乐园", "background": "#EAF5FF", "surface": "#FFFFFF", "primary": "#3977E6", "accent": "#FF7A59", "text": "#18324A"},
]

WORLDS = ["漂浮岛屿", "积木城市", "深海基地", "纸片宇宙", "糖果工厂", "机械森林"]
SHAPES = ["圆润气泡", "像素积木", "剪纸层次", "太空舷窗", "漫画分镜", "卡片拼图"]
MOTIONS = ["轻快弹跳", "柔和漂浮", "有力推进", "像素闪烁", "卡片翻转", "涟漪扩散"]
LAYOUTS = ["中央舞台", "左右对战", "纵向闯关", "环形仪表", "漫画分区", "自由探索"]


def creative_fingerprint(seed: str, recent_signatures: set[str] | None = None) -> dict:
    """Return a repeatable identity, nudged away from recent combinations."""
    recent = recent_signatures or set()
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    for offset in range(64):
        values = [(digest[(i + offset) % len(digest)] + offset * (i + 3)) for i in range(5)]
        result = {
            "palette": PALETTES[values[0] % len(PALETTES)],
            "world": WORLDS[values[1] % len(WORLDS)],
            "shape": SHAPES[values[2] % len(SHAPES)],
            "motion": MOTIONS[values[3] % len(MOTIONS)],
            "layout": LAYOUTS[values[4] % len(LAYOUTS)],
        }
        result["signature"] = "|".join((result["palette"]["name"], result["world"], result["shape"], result["layout"]))
        if result["signature"] not in recent:
            return result
    return result


def friendly_project_name(idea: str) -> str:
    """Make a short folder/title without asking a child to name files."""
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", idea).strip()
    value = re.sub(r"\s+", "", value)
    for prefix in ("我想要做一个", "我想做一个", "我要做一个", "我想要做", "我想做", "我要做", "帮我做一个", "做一个"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = re.split(r"[，。！!？?；;]", value)[0][:18]
    return value or "我的新作品"


def unique_project_path(root: Path, idea: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = friendly_project_name(idea)
    target = root / base
    number = 2
    while target.exists():
        target = root / f"{base}-{number}"
        number += 1
    return target
