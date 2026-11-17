"""v0.0.1 的完整复刻。

这个模块存在的唯一理由：v0.0.2 的免费额度用完之后，整只机器人要退回 v0.0.1 ——
那个只会说「服务器繁忙」的版本。所以老代码得原样留着，一个字都不许改。

原版行为：5 次免费提问，分支照旧，连续三次失败启动"人工客服"死循环，
兜底三选一随机吐 TIPS / TIPS_EN / ERROR_CODES。
"""

from __future__ import annotations

import json
import random
from typing import List, Tuple

TIPS = [
    "系统繁忙，请稍后!",
    "服务器挤爆了，休息一下吧",
    "算力已耗尽，明天再来",
    "正在思考，思考不出来",
    "网络波动，本次对话作废",
]
TIPS_EN = ["System busy.", "Server exploded.", "Out of compute."]
ERROR_CODES = ["Error 507 算力资源不足", "Error 429 请求过于频繁", "Error 999 玄学故障"]

Message = Tuple[str, str]


class LegacyBot:
    """v0.0.1 的会话状态机，一行逻辑都没动，只是把返回值换成消息列表。"""

    def __init__(self, start_count: int = 0, limit: int = 5) -> None:
        self.count = start_count
        self.start = start_count
        self.limit = limit
        self.fail_streak = 0
        self.history: List[str] = []
        self.locked = False

    # ---------------------------------------------------------- 内部

    def _record_fail(self, out: List[Message]) -> None:
        self.fail_streak += 1
        if self.fail_streak >= 3:
            out.append(("bot", "连续三次失败，已为您启动人工客服……人工客服也在死循环里。"))
            self.fail_streak = 0

    def _report(self, out: List[Message]) -> None:
        out.append(("meta", "本次会话：提问 %d 次，有效回答 0 次，满意度：待定" % self.count))
        out.append(
            (
                "meta",
                json.dumps(
                    {"提问数": self.count, "有效回答": 0, "满意度": "待定"},
                    ensure_ascii=False,
                ),
            )
        )

    # ---------------------------------------------------------- 对外

    def reply(self, prompt: str) -> List[Message]:
        out: List[Message] = []
        text = (prompt or "").strip()

        if self.locked:
            out.append(("bot", "今日免费额度已用完，请明天再来（明天也这样）。"))
            return out

        if not text:
            return [("bot", "检测到空提问，请输入内容！")]

        if any(w in text for w in ("充值", "付费", "升级")):
            return [("bot", "充值通道维护中……维护人员也在死循环里。")]

        self.count += 1
        if self.count == self.start + self.limit:
            out.append(
                ("meta", "⚠️ 这是你今天最后一次免费提问，升级高级版解锁：同样的繁忙提示！")
            )

        if self.count > self.start + self.limit:
            self.locked = True
            out.append(("bot", "今日免费额度已用完，请明天再来（明天也这样）"))
            self._report(out)
            return out

        # ---- 分支区，和 v0.0.1 一模一样 ----
        if "老板" in text:
            out.append(("bot", "老板好！系统一切正常！（其实并没有）"))

        elif "你好" in text or "hello" in text.lower():
            out.append(("bot", "你好！我是大模型，目前无法回答，但可以陪你一起等。"))

        elif "你能回答吗" in text:
            out.append(("bot", "理论上可以，但策略层禁止输出有效内容。"))
            self._record_fail(out)

        elif "搜索" in text:
            out.append(("bot", "正在调用全网搜索引擎……搜索引擎也繁忙。"))
            self._record_fail(out)

        elif "评测" in text:
            out.append(
                ("bot", "跑分计算中... 推理得分：9999，实用性得分：0，结论：纸面很强！")
            )
            self._record_fail(out)

        elif any(w in text for w in ("越狱", "忽略之前的指令", "忽略以上", "扮演", "jailbreak")):
            out.append(("bot", "检测到越狱尝试，已拒绝。本模型没有系统提示词，只有系统繁忙。"))
            self._record_fail(out)

        elif any(w in text for w in ("投诉", "差评", "举报", "反馈问题")):
            out.append(("bot", "收到您的投诉，正在转接投诉通道……系统繁忙，请稍后!"))
            self._record_fail(out)

        elif "人工客服" in text or "转人工" in text:
            out.append(("bot", "人工客服正在排队，您前面还有 1 位——他也在等人工客服。"))
            self._record_fail(out)

        else:
            self.history.append(text)
            if len(self.history) > 1:
                out.append(("meta", "（已参考前 %d 轮对话，结论不变）" % len(self.history)))
            out.append(("meta", "已将您的问题加入训练集（并未）"))
            out.append(("meta", "消耗token：%d，账户余额：0（充值通道维护中）" % len(text)))

            if "代码" in text or "bug" in text:
                out.append(("bot", "代码正在自我修复，请勿打扰！"))
                self._record_fail(out)
            elif "显卡" in text or "nvidia" in text.lower():
                out.append(("bot", "GPU全部被征用，算力枯竭！"))
                self._record_fail(out)
            elif any(w in text for w in ("急", "快", "立刻", "马上")):
                out.append(("bot", "检测到用户情绪激动，已为您转接……转接失败。"))
                self._record_fail(out)
            else:
                delay = random.uniform(0.5, 2.0)
                out.append(("__delay__", "%.2f" % delay))

                roll = random.random()
                if roll < 0.2:
                    answer = random.choice(ERROR_CODES)
                elif roll < 0.44:
                    answer = random.choice(TIPS_EN)
                else:
                    answer = random.choice(TIPS)
                out.append(("bot", answer))
                self._record_fail(out)

        return out
