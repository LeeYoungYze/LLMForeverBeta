"""一键盘点：把依赖装进 .vendor/，把模型下到 models/。

    python install.py            # 装依赖 + 下模型
    python install.py --deps     # 只装依赖
    python install.py --model    # 只下模型

装到 .vendor/ 而不是系统 site-packages，好处是删掉文件夹就干净了，
也不需要虚拟环境权限。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(ROOT, ".vendor")
MODEL_ROOT = os.path.join(ROOT, "models", "Qwen2.5-0.5B-Instruct")

MIRROR = "https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct/resolve/master/"
FILES = [
    "config.json",
    "generation_config.json",
    "merges.txt",
    "vocab.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "model.safetensors",
]

PACKAGES = ["torch", "transformers", "accelerate"]
CHUNK = 256 * 1024

# pip 内部全程用 tempfile.mkdtemp()，而有些受限环境（比如被 ACL 限制的沙箱）
# 给 mkdtemp 建出来的目录没有写权限，pip 会直接崩。这里换成 os.mkdir 版本。
_PIP_SHIM = """import sys, os, tempfile

def mkdtemp(suffix=None, prefix=None, dir=None):
    base = dir or tempfile.gettempdir()
    path = os.path.join(base, (prefix or 'tmp') + os.urandom(6).hex())
    os.makedirs(path, exist_ok=True)
    return path

tempfile.mkdtemp = mkdtemp
from pip._internal.cli.main import main
sys.exit(main(%r))
"""


def install_deps() -> bool:
    os.makedirs(VENDOR, exist_ok=True)
    args = ["install", "--target", ".vendor", "--upgrade", "--no-cache-dir"] + PACKAGES
    cmd = [sys.executable, "-c", _PIP_SHIM % (args,)]
    print("[1/2] 安装依赖 -> .vendor/")
    print("      " + " ".join(PACKAGES))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("依赖安装失败。可以在正常网络下手工执行：")
        print("      pip install --target .vendor " + " ".join(PACKAGES))
        return False
    return True


def download(name: str) -> bool:
    target = os.path.join(MODEL_ROOT, name)
    tmp = target + ".part"
    if os.path.exists(target) and os.path.getsize(target) > 0:
        print("      跳过 %-24s 已存在 %.1f MB" % (name, os.path.getsize(target) / 1024**2))
        return True

    have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    headers = {"User-Agent": "Mozilla/5.0"}
    if have:
        headers["Range"] = "bytes=%d-" % have
    try:
        req = urllib.request.Request(MIRROR + name, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = resp.headers.get("Content-Length")
            total = int(total) + have if total else None
            mode = "ab" if have and resp.status == 206 else "wb"
            written = have if mode == "ab" else 0
            started = time.time()
            with open(tmp, mode) as handle:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
        if os.path.exists(target):
            os.remove(target)
        os.replace(tmp, target)
        speed = written / max(time.time() - started, 0.001) / 1024 / 1024
        print("      %-24s %.1f MB  (%.2f MB/s)" % (name, written / 1024**2, speed))
        return True
    except Exception as exc:
        print("      下载 %s 失败：%s: %s" % (name, type(exc).__name__, str(exc)[:80]))
        return False


def fetch_model() -> bool:
    os.makedirs(MODEL_ROOT, exist_ok=True)
    print("[2/2] 下载模型 -> models/Qwen2.5-0.5B-Instruct/  (约 1 GB)")
    for name in FILES:
        ok = False
        for attempt in range(1, 4):
            if download(name):
                ok = True
                break
            time.sleep(2 * attempt)
        if not ok:
            return False
    return True


def main() -> int:
    args = sys.argv[1:]
    want_deps = "--model" not in args
    want_model = "--deps" not in args

    if want_deps and not install_deps():
        return 1
    if want_model and not fetch_model():
        return 1
    print("\n完成。运行：python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
