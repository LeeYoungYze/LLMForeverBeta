"""离线单位换算。

没有网络、没有第三方库，所以单位表是手写的。
支持长度、质量、时间、面积、体积、数据、温度七个家族。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

__all__ = ["convert"]

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# 基准单位：长度=米，质量=千克，时间=秒，面积=平方米，体积=升，数据=字节
_FAMILIES: Dict[str, Dict[str, float]] = {
    "长度": {
        "毫米": 1e-3,
        "厘米": 1e-2,
        "分米": 1e-1,
        "米": 1.0,
        "千米": 1000.0,
        "公里": 1000.0,
        "英里": 1609.344,
        "英尺": 0.3048,
        "英寸": 0.0254,
        "码": 0.9144,
        "海里": 1852.0,
        "mm": 1e-3,
        "cm": 1e-2,
        "km": 1000.0,
    },
    "质量": {
        "毫克": 1e-6,
        "克": 1e-3,
        "千克": 1.0,
        "公斤": 1.0,
        "吨": 1000.0,
        "斤": 0.5,
        "两": 0.05,
        "磅": 0.45359237,
        "盎司": 0.028349523125,
        "kg": 1.0,
    },
    "时间": {
        "毫秒": 1e-3,
        "秒": 1.0,
        "分钟": 60.0,
        "分": 60.0,
        "小时": 3600.0,
        "天": 86400.0,
        "日": 86400.0,
        "周": 604800.0,
        "星期": 604800.0,
    },
    "面积": {
        "平方厘米": 1e-4,
        "平方分米": 1e-2,
        "平方米": 1.0,
        "公顷": 1e4,
        "平方千米": 1e6,
        "平方公里": 1e6,
        "亩": 2000.0 / 3.0,
    },
    "体积": {
        "毫升": 1e-3,
        "升": 1.0,
        "立方米": 1000.0,
        "立方厘米": 1e-3,
    },
    "数据": {
        "字节": 1.0,
        "千字节": 1024.0,
        "兆字节": 1024.0**2,
        "吉字节": 1024.0**3,
        "kb": 1024.0,
        "mb": 1024.0**2,
        "gb": 1024.0**3,
        "tb": 1024.0**4,
    },
}

_TEMP_NAMES = {
    "摄氏度": "C",
    "摄氏": "C",
    "℃": "C",
    "°c": "C",
    "华氏度": "F",
    "华氏": "F",
    "℉": "F",
    "°f": "F",
    "开尔文": "K",
    "开氏度": "K",
}

# 长名字优先，保证「平方千米」不会被「千米」抢先匹配
_UNIT_LIST: List[Tuple[str, str, float]] = sorted(
    [(name, family, factor) for family, table in _FAMILIES.items() for name, factor in table.items()]
    + [(name, "温度", 0.0) for name in _TEMP_NAMES],
    key=lambda item: len(item[0]),
    reverse=True,
)


def _is_ascii(name: str) -> bool:
    return name.isascii()


def _touches_letter(text: str, start: int, length: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[start + length] if start + length < len(text) else ""
    return (before.isalpha() and before.isascii()) or (after.isalpha() and after.isascii())


_SHORT_UNIT_LEADS = ("多少", "几", "是", "为", "成", "换")


def _short_unit_ok(text: str, start: int) -> bool:
    """单个汉字的单位（天/日/分/斤/两/亩/米/克/升）要防误伤。

    「今天」「周日」「十分」里的天/日/分不是单位，所以要求：
    前面是数字或约数符号，或者前面两个字是「多少/几/是/为/成/换」。
    """
    if start == 0:
        return True
    prev = text[start - 1]
    if prev.isdigit() or prev in ". 约～~":
        return True
    return text[max(0, start - 2) : start] in _SHORT_UNIT_LEADS


def _find_units(text: str) -> List[Tuple[int, int, str, str, float]]:
    low = text.lower()
    found: List[Tuple[int, int, str, str, float]] = []
    for name, family, factor in _UNIT_LIST:
        key = name.lower()
        start = 0
        while True:
            idx = low.find(key, start)
            if idx < 0:
                break
            end = idx + len(key)
            ok = True
            if _is_ascii(key) and _touches_letter(low, idx, len(key)):
                ok = False
            if ok and len(name) == 1 and not _short_unit_ok(low, idx):
                ok = False
            if ok:
                found.append((idx, end, name, family, factor))
                start = end
            else:
                start = idx + 1
    found.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: List[Tuple[int, int, str, str, float]] = []
    for item in found:
        if kept and item[0] < kept[-1][1]:
            continue
        kept.append(item)
    return kept


def _to_celsius(value: float, scale: str) -> float:
    if scale == "C":
        return value
    if scale == "F":
        return (value - 32.0) * 5.0 / 9.0
    return value - 273.15


def _from_celsius(value: float, scale: str) -> float:
    if scale == "C":
        return value
    if scale == "F":
        return value * 9.0 / 5.0 + 32.0
    return value + 273.15


def convert(text: str) -> Optional[dict]:
    """从一句话里识别「数值 + 源单位 + 目标单位」，做换算。

    识别不出两份不同的同类单位就返回 None（交给上层去说不会或繁忙）。
    """
    if not text:
        return None

    number = _NUMBER_RE.search(text)
    if number is None:
        return None
    value = float(number.group())

    units = [item for item in _find_units(text) if item[0] >= number.end()]
    if not units:
        return None

    temps = [item for item in units if item[3] == "温度"]
    if len(temps) >= 2 and temps[0][2] != temps[1][2]:
        src = _TEMP_NAMES[temps[0][2].lower()] if temps[0][2].lower() in _TEMP_NAMES else _TEMP_NAMES[temps[0][2]]
        dst = _TEMP_NAMES[temps[1][2]] if temps[1][2] in _TEMP_NAMES else _TEMP_NAMES[temps[1][2].lower()]
        result = _from_celsius(_to_celsius(value, src), dst)
        return {
            "family": "温度",
            "value": value,
            "src": temps[0][2],
            "dst": temps[1][2],
            "result": result,
        }

    grouped: Dict[str, list] = {}
    for item in units:
        if item[3] == "温度":
            continue
        grouped.setdefault(item[3], []).append(item)

    for family, items in grouped.items():
        if len(items) >= 2 and items[0][2] != items[1][2]:
            src_item, dst_item = items[0], items[1]
            if src_item[4] == 0 or dst_item[4] == 0:
                continue
            result = value * src_item[4] / dst_item[4]
            return {
                "family": family,
                "value": value,
                "src": src_item[2],
                "dst": dst_item[2],
                "result": result,
            }
    return None
