"""结构化记忆。

只存白名单槽位（名字、年龄、城市、生日、喜好、备注），不存聊天原文。
落盘到项目根目录的 ``memory.json``，删掉它就等于失忆。
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

__all__ = ["Memory"]

_DEFAULT_FILENAME = "memory.json"

_NAME_RE = re.compile(r"(?:我叫|我的名字是|我的名字叫|叫我)\s*([\u4e00-\u9fa5A-Za-z·]{1,10})")
_AGE_RE = re.compile(r"(?:今年|我[^我\d]{0,8})\s*(\d{1,3})\s*(?:周?岁)")
_CITY_RE = re.compile(r"(?:我[^我]{0,10})?(?:住在|家在|来自|老家在)\s*([\u4e00-\u9fa5A-Za-z]{2,10})")
_BIRTHDAY_RE = re.compile(r"生日(?:是|在)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
_LIKE_RE = re.compile(r"我(?:最)?(?:喜欢|爱)\s*([^，。！？,.!?\s]{1,12})")
_NOTE_RE = re.compile(r"记住[：:\s]*(.{1,60})")

_ASK_MARKERS = ("什么", "啥", "谁", "哪", "几", "吗", "呢", "?")

_RECALL_NAME = ("我叫什么", "我的名字", "你记得我叫", "我是谁", "还记得我")
_RECALL_AGE = ("我几岁", "我多大", "我的年龄", "我多少岁")
_RECALL_CITY = ("我住哪", "我住在哪", "我来自哪", "我的城市", "我家在哪")
_RECALL_BIRTHDAY = ("我的生日", "我生日", "生日是几号")
_RECALL_LIKE = ("我喜欢什么", "我爱什么", "我喜欢啥")
_RECALL_ALL = ("你记得什么", "你记得我什么", "我的信息", "你都知道我什么", "你记得哪些", "我的资料")


def _default_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, _DEFAULT_FILENAME)


def _empty() -> Dict[str, object]:
    return {
        "name": None,
        "age": None,
        "city": None,
        "birthday": None,
        "likes": [],
        "notes": [],
        "updated": None,
    }


class Memory:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or _default_path()
        self.data = _empty()
        self._load()

    # ---------------------------------------------------------------- 读写

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for key in ("name", "age", "city", "birthday"):
            value = raw.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                self.data[key] = str(value).strip()
        for key in ("likes", "notes"):
            value = raw.get(key)
            if isinstance(value, list):
                self.data[key] = [str(item)[:80] for item in value if str(item).strip()][:30]

    def _save(self) -> None:
        self.data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass

    # ---------------------------------------------------------------- 学习

    def learn(self, text: str) -> List[Tuple[str, str]]:
        """从一句话里抽槽位，返回 [(标签, 值)]。没抽到就是空列表。"""
        if not text:
            return []
        updates: List[Tuple[str, str]] = []
        asking = any(marker in text for marker in _ASK_MARKERS)

        if "叫" in text and not any(word in text for word in ("叫什么", "叫啥", "什么名字", "名字是什么")):
            match = _NAME_RE.search(text)
            if match:
                name = match.group(1).strip(" 的啊呀吧呢")
                if 1 <= len(name) <= 8 and name not in {"什么", "啥", "谁"} and not any(
                    bad in name for bad in ("你", "他", "她", "别", "不", "吗")
                ):
                    self.data["name"] = name
                    updates.append(("名字", name))

        match = _AGE_RE.search(text)
        if match and not asking and not any(word in text for word in ("他今年", "她今年", "孩子")):
            age = int(match.group(1))
            if 0 < age < 130:
                self.data["age"] = str(age)
                updates.append(("年龄", f"{age} 岁"))

        match = _CITY_RE.search(text)
        if (
            match
            and not any(word in match.group(1) for word in ("哪", "什么"))
            and not any(word in text for word in ("他住在", "她住在", "朋友住在"))
        ):
            city = match.group(1).strip(" 的，。")
            if 2 <= len(city) <= 10:
                self.data["city"] = city
                updates.append(("城市", city))

        match = _BIRTHDAY_RE.search(text)
        if match and not any(word in text for word in ("几号", "哪天", "什么时候")):
            month, day = int(match.group(1)), int(match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                value = f"{month} 月 {day} 日"
                self.data["birthday"] = value
                updates.append(("生日", value))

        match = _LIKE_RE.search(text)
        if match and not any(word in text for word in ("喜欢什么", "喜欢啥", "爱什么")):
            thing = match.group(1).strip(" 的，。！？")
            if thing and thing not in {"你", "他", "她", "它", "什么", "谁"} and len(thing) <= 14:
                likes = list(self.data.get("likes") or [])
                if thing not in likes:
                    likes.append(thing)
                    self.data["likes"] = likes[:10]
                    updates.append(("喜欢", thing))

        match = _NOTE_RE.search(text)
        if match:
            note = match.group(1).strip(" 的，。！？")
            if note and not any(word in note for word in ("什么", "啥")):
                notes = list(self.data.get("notes") or [])
                notes.append(note)
                self.data["notes"] = notes[-30:]
                updates.append(("备注", note))

        if updates:
            self._save()
        return updates

    # ---------------------------------------------------------------- 回忆

    def recall(self, text: str) -> Optional[str]:
        """如果是「你还记得我…吗」这类问题，就回答；否则返回 None。"""
        if not text:
            return None

        if any(pattern in text for pattern in _RECALL_ALL):
            return self.summary()

        if any(pattern in text for pattern in _RECALL_NAME):
            name = self.data.get("name")
            if name:
                return f"你叫{name}。（记在 memory.json 里，关掉窗口再开也还在。）"
            return "你还没告诉我你叫什么。你说一句「我叫什么什么」，我就记下来了。"

        if any(pattern in text for pattern in _RECALL_AGE):
            age = self.data.get("age")
            if age:
                return f"你今年 {age} 岁。"
            return "你没有告诉过我年龄，我也不会猜。"

        if any(pattern in text for pattern in _RECALL_CITY):
            city = self.data.get("city")
            if city:
                return f"你住在{city}。"
            return "你没说过你住哪。"

        if any(pattern in text for pattern in _RECALL_BIRTHDAY):
            birthday = self.data.get("birthday")
            if birthday:
                return f"你的生日是 {birthday}。"
            return "你没告诉过我生日。"

        if any(pattern in text for pattern in _RECALL_LIKE):
            likes = self.data.get("likes") or []
            if likes:
                return "你提到过喜欢：" + "、".join(likes) + "。"
            return "你没说过喜欢什么。"

        return None

    # ---------------------------------------------------------------- 展示

    def summary(self) -> str:
        parts: List[str] = []
        if self.data.get("name"):
            parts.append(f"名字是 {self.data['name']}")
        if self.data.get("age"):
            parts.append(f"{self.data['age']} 岁")
        if self.data.get("city"):
            parts.append(f"住在 {self.data['city']}")
        if self.data.get("birthday"):
            parts.append(f"生日 {self.data['birthday']}")
        likes = self.data.get("likes") or []
        if likes:
            parts.append("喜欢 " + "、".join(likes))
        notes = self.data.get("notes") or []
        if notes:
            parts.append("备注 " + "、".join(notes[-3:]))
        if not parts:
            return "目前什么都没记。你可以说「我叫…」「我今年…岁」「我喜欢…」，我只存这几个槽位，不存聊天原文。"
        return "我记着：" + "；".join(parts) + "。聊天原文不存。"

    def slot_count(self) -> int:
        count = 0
        for key in ("name", "age", "city", "birthday"):
            if self.data.get(key):
                count += 1
        count += len(self.data.get("likes") or [])
        count += len(self.data.get("notes") or [])
        return count
