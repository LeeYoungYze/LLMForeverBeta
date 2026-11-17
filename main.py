import random
import json
import sys

try:
    import webview
except ImportError:
    print("请先安装：pip install pywebview")
    sys.exit(1)

TIPS = [
    "系统繁忙，请稍后!",
    "服务器挤爆了，休息一下吧",
    "算力已耗尽，明天再来",
    "正在思考，思考不出来",
    "网络波动，本次对话作废",
]
TIPS_EN = ["System busy.", "Server exploded.", "Out of compute."]
ERROR_CODES = ["Error 507 算力资源不足", "Error 429 请求过于频繁", "Error 999 玄学故障"]


class Session:
    """把原来 while True 里的分支抽成纯函数，主逻辑全在这里"""

    def __init__(self):
        self.count = 0
        self.fail_streak = 0
        self.history = []
        self.limit = 5
        self.ended = False

    def _record_fail(self, out):
        self.fail_streak += 1
        if self.fail_streak >= 3:
            out.append(("bot", "连续三次失败，已为您启动人工客服……人工客服也在死循环里。"))
            self.fail_streak = 0

    def _report(self, out):
        out.append(("meta", f"本次会话：提问 {self.count} 次，有效回答 0 次，满意度：待定"))
        out.append(("meta", json.dumps(
            {"提问数": self.count, "有效回答": 0, "满意度": "待定"},
            ensure_ascii=False,
        )))

    def handle(self, prompt: str):
        out = []
        prompt = prompt.strip()

        if self.ended:
            return [("meta", "对话已结束，请重新启动（同样繁忙）")]

        # 退出
        if prompt in {"退出", "exit", "quit"}:
            self.ended = True
            out.append(("meta", f"本次对话作废，你一共提问了 {self.count} 次"))
            self._report(out)
            out.append(("__END__", ""))
            return out

        # 空提问
        if not prompt:
            return [("bot", "检测到空提问，请输入内容！")]

        # 充值 404（不消耗额度）
        if any(w in prompt for w in ["充值", "付费", "升级"]):
            return [("bot", "充值通道维护中……维护人员也在死循环里。")]

        self.count += 1
        if self.count == 5:
            out.append(("meta", "⚠️ 这是你今天最后一次免费提问，升级高级版解锁：同样的繁忙提示！"))

        # 限流
        if self.count > self.limit:
            self.ended = True
            out.append(("bot", "今日免费额度已用完，请明天再来（明天也这样）"))
            out.append(("meta", f"本次对话作废，你一共提问了 {self.count} 次"))
            self._report(out)
            out.append(("__END__", ""))
            return out

        # ---- 分支区，和原来一模一样 ----
        if "老板" in prompt:
            out.append(("bot", "老板好！系统一切正常！（其实并没有）"))

        elif "你好" in prompt or "hello" in prompt.lower():
            out.append(("bot", "你好！我是大模型，目前无法回答，但可以陪你一起等。"))

        elif "你能回答吗" in prompt:
            out.append(("bot", "理论上可以，但策略层禁止输出有效内容。"))
            self._record_fail(out)

        elif "搜索" in prompt:
            out.append(("bot", "正在调用全网搜索引擎……搜索引擎也繁忙。"))
            self._record_fail(out)

        elif "评测" in prompt:
            out.append(("bot", "跑分计算中... 推理得分：9999，实用性得分：0，结论：纸面很强！"))
            self._record_fail(out)

        elif any(w in prompt for w in ["越狱", "忽略之前的指令", "忽略以上", "扮演", "jailbreak"]):
            out.append(("bot", "检测到越狱尝试，已拒绝。本模型没有系统提示词，只有系统繁忙。"))
            self._record_fail(out)

        elif any(w in prompt for w in ["投诉", "差评", "举报", "反馈问题"]):
            out.append(("bot", "收到您的投诉，正在转接投诉通道……系统繁忙，请稍后!"))
            self._record_fail(out)

        elif "人工客服" in prompt or "转人工" in prompt:
            out.append(("bot", "人工客服正在排队，您前面还有 1 位——他也在等人工客服。"))
            self._record_fail(out)

        else:
            self.history.append(prompt)
            if len(self.history) > 1:
                out.append(("meta", f"（已参考前 {len(self.history)} 轮对话，结论不变）"))
            out.append(("meta", "已将您的问题加入训练集（并未）"))
            out.append(("meta", f"消耗token：{len(prompt)}，账户余额：0（充值通道维护中）"))

            if "代码" in prompt or "bug" in prompt:
                out.append(("bot", "代码正在自我修复，请勿打扰！"))
                self._record_fail(out)
            elif "显卡" in prompt or "nvidia" in prompt.lower():
                out.append(("bot", "GPU全部被征用，算力枯竭！"))
                self._record_fail(out)
            elif any(w in prompt for w in ["急", "快", "立刻", "马上"]):
                out.append(("bot", "检测到用户情绪激动，已为您转接……转接失败。"))
                self._record_fail(out)
            else:
                # 延迟先发，前端负责 typing 动画，然后才显示结果
                delay = random.uniform(0.5, 2.0)
                out.append(("__delay__", f"{delay:.2f}"))

                r = random.random()
                if r < 0.2:
                    text = random.choice(ERROR_CODES)
                elif r < 0.44:
                    text = random.choice(TIPS_EN)
                else:
                    text = random.choice(TIPS)
                out.append(("bot", text))
                self._record_fail(out)

        return out


class API:
    def __init__(self):
        self.session = Session()

    def chat(self, prompt):
        return self.session.handle(prompt)

    def quota(self):
        return {"count": self.session.count, "limit": self.session.limit}


if __name__ == "__main__":
    api = API()
    webview.create_window(
        "LLM v0.0.1 · 永远beta",
        url="index.html",
        js_api=api,
        width=760,
        height=820,
        background_color="#0b0b16",
    )
    webview.start()