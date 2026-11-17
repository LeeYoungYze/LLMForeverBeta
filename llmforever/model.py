"""本地小模型：Qwen2.5-0.5B-Instruct，纯 CPU 推理。

模型文件在 models/Qwen2.5-0.5B-Instruct/，依赖装在 .vendor/。
两样缺一个，``available()`` 就返回 False，上层退回「繁忙」彩蛋。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import List, Optional

__all__ = ["LocalModel", "MODEL_DIR", "VENDOR_DIR"]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(_ROOT, "models", "Qwen2.5-0.5B-Instruct")
VENDOR_DIR = os.path.join(_ROOT, ".vendor")

_REQUIRED = ("config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors")

SYSTEM_PROMPT = (
    "你是 LLM v0.0.2，一个跑在本地 CPU 上的小模型，永远 beta。"
    "说话简短、直接、带一点自嘲式的吐槽，不要客套。"
    "能用一句话说清就用一句话，最多三句。"
    "不确定的事情就说不知道，绝对不要编造。"
    "你只有 5 亿参数，涉及精确计算、日期、人名时尤其要谨慎。"
)


def _ensure_vendor() -> None:
    if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
        sys.path.insert(0, VENDOR_DIR)


class LocalModel:
    """懒加载的单例包装：第一次真的要用时才吃内存。"""

    def __init__(self, threads: Optional[int] = None) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._torch = None
        self._load_error: Optional[str] = None
        self._threads = threads
        self._tokens = 0
        self._seconds = 0.0

    # ------------------------------------------------------------ 状态

    def available(self) -> bool:
        if not all(os.path.exists(os.path.join(MODEL_DIR, name)) for name in _REQUIRED):
            return False
        if not os.path.isdir(VENDOR_DIR):
            return False
        return self._load_error is None

    def loaded(self) -> bool:
        return self._model is not None

    def status(self) -> str:
        if self._load_error:
            return "模型加载失败：" + self._load_error
        if not self.available():
            return "模型文件或依赖不全"
        if self.loaded():
            return "已就绪"
        return "未加载"

    def stats(self) -> dict:
        speed = self._tokens / self._seconds if self._seconds else 0.0
        return {"tokens": self._tokens, "seconds": round(self._seconds, 1), "speed": round(speed, 1)}

    # ------------------------------------------------------------ 加载

    def load(self) -> bool:
        with self._lock:
            if self._model is not None:
                return True
            if self._load_error:
                return False
            if not self.available():
                self._load_error = "缺少模型文件或 .vendor 依赖"
                return False
            try:
                _ensure_vendor()
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                cores = os.cpu_count() or 4
                torch.set_num_threads(self._threads or max(1, min(cores, 16)))
                self._torch = torch
                self._tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
                try:
                    self._model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32)
                except TypeError:
                    self._model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, torch_dtype=torch.float32)
                self._model.eval()
            except Exception as exc:  # 依赖缺失、显存/内存不足、文件损坏都走这里
                self._load_error = "%s: %s" % (type(exc).__name__, str(exc)[:200])
                self._model = None
                return False
            return True

    # ------------------------------------------------------------ 推理

    def reply(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        max_new_tokens: int = 160,
        temperature: float = 0.7,
    ) -> Optional[str]:
        if not self.load():
            return None

        messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in (history or [])[-6:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:800]})
        messages.append({"role": "user", "content": prompt[:800]})

        torch = self._torch
        tokenizer = self._tokenizer
        model = self._model

        with self._lock:
            started = time.time()
            new_tokens = None
            try:
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = tokenizer(text, return_tensors="pt")
                with torch.inference_mode():
                    output = model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        do_sample=temperature > 0,
                        temperature=max(0.1, temperature),
                        top_p=0.9,
                        repetition_penalty=1.08,
                        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                    )
                new_tokens = output[0][inputs["input_ids"].shape[1] :]
                answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            except Exception as exc:
                self._load_error = "%s: %s" % (type(exc).__name__, str(exc)[:200])
                return None
            finally:
                elapsed = time.time() - started
                self._seconds += elapsed
                if new_tokens is not None:
                    self._tokens += int(new_tokens.nelement())

        return answer or None
