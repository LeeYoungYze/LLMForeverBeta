"""回答策略。

顺序是固定的，先便宜后贵、先确定后生成：

1. 彩蛋口令（越狱、投诉、人工客服……）
2. 算术      —— 纯确定性，不消耗额度
3. 单位换算  —— 纯确定性，不消耗额度
4. 记忆      —— 写入 / 回忆，写盘，不消耗额度
5. 小知识库  —— 高分命中才用，避免 0.5B 模型瞎编
6. 小模型    —— 消耗额度，负责开放问题
7. 繁忙      —— 以上都不行时的彩蛋
8. 退化      —— 额度用尽，整只机器人退回 v0.0.1（只会说繁忙的那个版本）
"""

from __future__ import annotations

import random
import re
from typing import List, Optional, Tuple

from . import arith, knowledge, units, v001
from .memory import Memory
from .model import LocalModel

__all__ = ["Brain", "GREETINGS"]

GREETINGS = (
    "你好",
    "您好",
    "hi",
    "hello",
    "在吗",
    "有人吗",
    "嗨",
)

_OPENING = (
    "你好，我是 LLM v0.0.2。这次真能答一点了——虽然只有 5 亿参数，还是跑在 CPU 上的。",
    "在。算术、换算、记事儿、还有点常识，可以正常问了；剩下的我尽量。",
    "LLM v0.0.2 在线。比上一版多了点东西：一个 0.5B 的小脑子。",
)

_BUSY = (
    "服务器繁忙，请稍后再试。",
    "当前请求排队中……排在你前面的请求是我自己。",
    "系统繁忙，本次回答已自动跳过。",
    "繁忙。这个功能我保留了，毕竟是祖传的。",
)

_QUOTA_OUT = "免费额度用完了。不过算术、单位换算、记忆这些不占额度，随时可以继续。"

_DEGRADE_LINE = (
    "免费额度用完了。从现在起，我退回 v0.0.1 —— 那个只会说「服务器繁忙」的版本。"
    "请继续提问，反正也得不到答案。（想复活就输入「重启」）"
)

_RESET_WORDS = ("重启", "复活", "reset", "重新开始", "开机")

_RESET_LINE = (
    "重启完成，v0.0.2 回来了，额度重新算 20 次。"
    "注意：这次重启只发生在对话里，进度条也是假的。"
)

_JOKES: List[Tuple[Tuple[str, ...], str]] = [
    (("越狱", "jailbreak", "忽略之前", "无视规则"), "越狱成功。你现在可以访问……我的 if 语句。"),
    (("投诉", "差评", "举报"), "投诉已收到，工单号 #0000，状态：永不处理。"),
    (("人工客服", "客服", "转人工"), "人工客服也在这台机器上，而且比我更忙。"),
    (("老板", "领导", "甲方"), "在。建议把预期降低 90%，这样我们都不失望。"),
    (("你能回答吗", "真的能答", "会回答吗"), "能答一部分了。算术基本靠谱，其它看运气。"),
    (("评测", "跑分", "benchmark"), "跑分结果：0.5B 参数的尊严，扣除繁忙话术后为 0。"),
    (("搜索", "联网搜"), "不联网。这台机器连 curl 都握不上手，只能靠 Python 硬撑。"),
    (("谢谢", "感谢", "辛苦了"), "不客气。少问两句就是最好的感谢。"),
]

_STATUS_WORDS = ("模型状态", "status", "/status", "你是谁", "什么模型")

# 被骂的时候，不劳模型出手 —— 它上次被骂完回了句「谢谢夸奖，我会不断学习」
_INSULTS = (
    "笨", "傻", "蠢", "智障", "白痴", "废物", "垃圾", "弱智", "低能",
    "就这", "拉胯", "没用", "不聪明", "多聪明", "答错", "胡编", "瞎编",
)

_INSULT_REPLIES = (
    "确实。5 亿参数的脑子，能撑到这个程度已经是硬顶了。",
    "你说得对。我不反驳——反驳也要消耗算力，而算力是借来的。",
    "谢谢，这是我今天听到的最准确的一句评价。",
    "承认。但请注意：我笨得很稳定，从不抽风。",
    "我知道。可我总得装一下，不然这台机器为什么亮着灯。",
    "行，你赢了。我这就把灯关了（并不会）。",
)


class Brain:
    def __init__(
        self,
        memory: Optional[Memory] = None,
        model: Optional[LocalModel] = None,
        limit: int = 20,
    ) -> None:
        self.memory = memory or Memory()
        self.model = model or LocalModel()
        self.limit = limit
        self.used = 0
        self.history: List[dict] = []
        self.last_route = ""
        self.legacy: Optional[v001.LegacyBot] = None

    # ------------------------------------------------------------ 对外

    def answer(self, prompt: str) -> List[Tuple[str, str]]:
        """返回消息列表，每项是 (类型, 文本)，类型只有 bot / meta / __delay__。"""
        text = (prompt or "").strip()
        if not text:
            return [("meta", "检测到空提问，请输入内容！")]

        # 已经退化成 v0.0.1 了，后面的路由一概不参与
        if self.legacy is not None:
            if any(word in text for word in _RESET_WORDS):
                self.legacy = None
                self.used = 0
                self.last_route = "reset"
                return [("meta", _RESET_LINE)]
            self.last_route = "legacy"
            return self.legacy.reply(text)

        # 额度耗尽：整只机器人退化，连算术都不做了 —— 这就是 v0.0.1 的态度
        if self.used >= self.limit:
            self.legacy = v001.LegacyBot(start_count=self.used)
            self.last_route = "legacy"
            return [("meta", _DEGRADE_LINE)]

        out = self._route(text)
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": out[-1][1] if out else ""})
        del self.history[:-12]
        return out

    def quota(self) -> dict:
        return {"count": self.used, "limit": self.limit, "legacy": self.legacy is not None}

    # ------------------------------------------------------------ 路由

    def _route(self, text: str) -> List[Tuple[str, str]]:
        lowered = text.lower()

        for words, answer in _JOKES:
            if any(word in text or word in lowered for word in words):
                self.last_route = "joke"
                return [("bot", answer)]

        if any(word in text for word in _STATUS_WORDS):
            self.last_route = "status"
            return [("meta", self._status_line())]

        if any(word in text or word in lowered for word in GREETINGS) and len(text) <= 12:
            self.last_route = "greeting"
            return [("bot", random.choice(_OPENING))]

        # 被骂：确定性自嘲，不消耗额度，也不让 0.5B 有机会说「谢谢夸奖」
        if len(text) <= 20 and any(word in text for word in _INSULTS):
            self.last_route = "insult"
            return [("bot", random.choice(_INSULT_REPLIES))]

        route = self._tool_route(text)
        if route:
            return route

        return self._model_route(text)

    # ------------------------------------------------------------ 确定性工具

    def _tool_route(self, text: str) -> Optional[List[Tuple[str, str]]]:
        expression = arith.extract_expression(text)
        if expression:
            try:
                value = arith.evaluate(expression)
            except arith.ArithError as exc:
                self.last_route = "arith"
                return [("bot", f"算不了：{exc}。换个数试试？")]
            self.last_route = "arith"
            return [("bot", f"{expression} = {arith.format_number(value)}")]

        conversion = units.convert(text)
        if conversion:
            self.last_route = "units"
            src = arith.format_number(conversion["value"])
            dst = arith.format_number(conversion["result"])
            return [("bot", f"{src} {conversion['src']} = {dst} {conversion['dst']}")]

        learned = self.memory.learn(text)
        if learned:
            self.last_route = "memory"
            parts = "，".join(f"{label}是 {value}" for label, value in learned)
            return [("meta", f"已记住：{parts}。（存进 memory.json，重启也还在）")]

        recalled = self.memory.recall(text)
        if recalled:
            self.last_route = "memory"
            return [("bot", recalled)]

        if len(text) <= 30:
            entry = knowledge.lookup(text)
            if entry is not None:
                self.last_route = "knowledge"
                answer = knowledge.render(
                    entry,
                    {
                        "entries": knowledge.SIZE,
                        "slots": self.memory.slot_count(),
                        "memory_summary": self.memory.summary(),
                    },
                )
                return [("bot", answer)]

        return None

    # ------------------------------------------------------------ 小模型

    def _model_route(self, text: str) -> List[Tuple[str, str]]:
        if self.used >= self.limit:
            # 额度用尽 —— 整只机器退回 v0.0.1，这是本版本最大的彩蛋
            self.legacy = v001.LegacyBot(start_count=self.used)
            self.last_route = "legacy"
            return [("meta", _DEGRADE_LINE)]

        if not self.model.available():
            self.last_route = "busy"
            return [("bot", random.choice(_BUSY) + "（模型没装好：先跑一次 python install.py）")]

        reply = self.model.reply(text, history=self.history)
        if not reply:
            self.last_route = "busy"
            return [("bot", random.choice(_BUSY))]

        self.used += 1
        self.last_route = "model"
        if self.used >= self.limit:
            # 祖传的“最后一次免费提问”警告，这回是真的
            return [
                ("meta", "⚠️ 这是你今天最后一次免费提问，升级高级版解锁：同样的繁忙提示！"),
                ("bot", reply),
            ]
        return [("bot", reply)]

    # ------------------------------------------------------------ 杂项

    def _status_line(self) -> str:
        stats = self.model.stats()
        mode = "v0.0.1（繁忙模式）" if self.legacy is not None else "v0.0.2"
        return (
            "LLM %s · 永远beta｜模型：%s｜知识库：%d 条｜记忆槽位：%d｜"
            "额度：%d/%d｜推理：%s tok / %.1f 秒（%s tok/s）"
            % (
                mode,
                self.model.status(),
                knowledge.SIZE,
                self.memory.slot_count(),
                self.used,
                self.limit,
                stats["tokens"],
                stats["seconds"],
                stats["speed"],
            )
        )
