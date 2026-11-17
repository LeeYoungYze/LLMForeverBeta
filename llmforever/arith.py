"""手写四则运算引擎。

不依赖任何第三方库：词法切分 + 递归下降求值。
支持整数、小数、``+ - * /``、括号、一元正负号、后缀百分号。

对外三个入口：

* :func:`evaluate`         传入干净的表达式字符串，返回 float
* :func:`extract_expression` 从中文问句里抠出表达式，抠不出返回 None
* :func:`format_number`    把 float 格式化成人类想看的字符串
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

__all__ = [
    "ArithError",
    "evaluate",
    "extract_expression",
    "format_number",
]

_MAX_LENGTH = 120
_MAX_ABS_RESULT = 1e18

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# 单个二元运算符存在的证据：数字或右括号，跟着运算符，再跟着数字或左括号。
# 这样 "-5" 这种纯负数不会被误判成"要算算术"。
_BINARY_OP_RE = re.compile(r"[\d)]\s*[+\-*/]\s*[\d(]")


class ArithError(Exception):
    """表达式本身有问题（写错、除零等），消息可以直接说给用户听。"""


# --------------------------------------------------------------------------
# 词法
# --------------------------------------------------------------------------


def _tokenize(source: str) -> List[Tuple[str, object]]:
    tokens: List[Tuple[str, object]] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            match = _NUMBER_RE.match(source, i)
            if match is None:  # pragma: no cover - isdigit 已保证能匹配
                raise ArithError("这里有一串数字我没读出来")
            tokens.append(("num", float(match.group())))
            i = match.end()
            continue
        if ch in "+-*/()%":
            tokens.append(("op", ch))
            i += 1
            continue
        raise ArithError(f"表达式里有个我看不懂的符号「{ch}」")
    if not tokens:
        raise ArithError("没有可以计算的表达式")
    return tokens


# --------------------------------------------------------------------------
# 语法（递归下降）
#   expr   := term (('+' | '-') term)*
#   term   := factor (('*' | '/') factor)*
#   factor := ('+' | '-') factor | primary '%'*
#   primary:= number | '(' expr ')'
# --------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: List[Tuple[str, object]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _take(self):
        token = self._peek()
        self.pos += 1
        return token

    def parse(self) -> float:
        value = self._expr()
        leftover = self._peek()
        if leftover is not None:
            raise ArithError(f"末尾多出来一个「{leftover[1]}」，我接不上")
        return value

    def _expr(self) -> float:
        value = self._term()
        while True:
            token = self._peek()
            if token and token[0] == "op" and token[1] in "+-":
                op = self._take()[1]
                rhs = self._term()
                value = value + rhs if op == "+" else value - rhs
            else:
                return value

    def _term(self) -> float:
        value = self._factor()
        while True:
            token = self._peek()
            if token and token[0] == "op" and token[1] in "*/":
                op = self._take()[1]
                rhs = self._factor()
                if op == "*":
                    value *= rhs
                else:
                    if rhs == 0:
                        raise ArithError("除数是 0，这个式子没有值")
                    value /= rhs
            else:
                return value

    def _factor(self) -> float:
        token = self._peek()
        if token and token[0] == "op" and token[1] in "+-":
            op = self._take()[1]
            value = self._factor()
            return -value if op == "-" else value
        value = self._primary()
        while True:
            token = self._peek()
            if token and token[0] == "op" and token[1] == "%":
                self._take()
                value /= 100.0
            else:
                return value

    def _primary(self) -> float:
        token = self._take()
        if token is None:
            raise ArithError("表达式在中间就结束了")
        kind, value = token
        if kind == "num":
            return float(value)
        if value == "(":
            inner = self._expr()
            closing = self._take()
            if closing is None or closing[1] != ")":
                raise ArithError("括号没有配对，右括号不见了")
            return inner
        if value == ")":
            raise ArithError("括号没有配对，多了一个右括号")
        raise ArithError(f"「{value}」出现在不该出现的位置")


def evaluate(source: str) -> float:
    """求值一个干净表达式。失败抛 :class:`ArithError`。"""
    source = source.strip()
    if not source:
        raise ArithError("没有可以计算的表达式")
    if len(source) > _MAX_LENGTH:
        raise ArithError("表达式太长，我这个解析器会喘不过气")
    value = _Parser(_tokenize(source)).parse()
    if math.isnan(value) or math.isinf(value):
        raise ArithError("结果溢出了，我算不了这么大的数")
    if abs(value) > _MAX_ABS_RESULT:
        raise ArithError("结果太大了，超出我能表示的精度")
    return value


# --------------------------------------------------------------------------
# 从中文问句里抠表达式
# --------------------------------------------------------------------------

# 顺序重要：先换多字的，再换单字的，否则「乘以」会被拆成「乘」「以」。
_OPERATOR_MAP = (
    ("乘以", "*"),
    ("除以", "/"),
    ("加上", "+"),
    ("减去", "-"),
    ("×", "*"),
    ("x", "*"),
    ("X", "*"),
    ("÷", "/"),
    ("＊", "*"),
    ("／", "/"),
    ("＋", "+"),
    ("－", "-"),
    ("—", "-"),
    ("–", "-"),
    ("（", "("),
    ("）", ")"),
    ("加", "+"),
    ("减", "-"),
    ("乘", "*"),
    ("除", "/"),
)

# 长的写前面，避免「等于」先被「等于多少」以外的规则吃掉。
_FILLERS = (
    "帮我计算一下",
    "帮我算一下",
    "帮算一下",
    "帮忙算一下",
    "帮我算算",
    "请帮我算",
    "计算一下",
    "算一下",
    "请问",
    "告诉我",
    "等于多少",
    "结果是",
    "结果",
    "算算",
    "是多少",
    "等于几",
    "等于",
    "是多少呢",
    "多少",
    "一共",
    "加起来",
    "帮我",
    "请",
    "呢",
    "吗",
    "？",
    "?",
    "。",
    "，",
    ",",
    "＝",
    "=",
)

_ALLOWED_CHARS = set("0123456789.+-*/()% ")


def extract_expression(text: str) -> Optional[str]:
    """从一句话里提取算术表达式；看着不像算术题就返回 None。"""
    if not text:
        return None
    if not any(ch.isdigit() for ch in text):
        return None

    cleaned = text
    for source, target in _OPERATOR_MAP:
        cleaned = cleaned.replace(source, target)
    for filler in _FILLERS:
        cleaned = cleaned.replace(filler, "")
    cleaned = "".join(ch for ch in cleaned if ch in _ALLOWED_CHARS).strip()

    if not cleaned:
        return None
    if not _BINARY_OP_RE.search(cleaned):
        return None
    # 光有括号没有运算符的，交给后面去说"不会"
    if not any(ch in cleaned for ch in "+-*/"):
        return None
    return cleaned


# --------------------------------------------------------------------------
# 输出格式化
# --------------------------------------------------------------------------


def format_number(value: float) -> str:
    """3.0 -> "3"，0.30000000000000004 -> "0.3"，大数用科学计数法兜底。"""
    if value != value:  # NaN
        return "不是一个数"
    if abs(value) < 1e-12:
        return "0"
    rounded = round(value, 10)
    if abs(rounded - round(rounded)) < 1e-9 and abs(rounded) < 1e15:
        return str(int(round(rounded)))
    if abs(rounded) >= 1e15:
        return f"{rounded:.6e}"
    text = f"{rounded:.10f}".rstrip("0").rstrip(".")
    return text or "0"
