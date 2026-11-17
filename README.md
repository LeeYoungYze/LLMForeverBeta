# LLMForeverBeta

> 一个永远 beta 的"大语言模型"。上一版只会说「服务器繁忙」，这一版真的能答一点了。

## 它现在会什么

| 能力 | 谁负责 | 消耗额度 | 靠谱程度 |
|---|---|---|---|
| 四则运算、括号、负数、小数、百分号 | `llmforever/arith.py` | 否 | 确定，不会算错 |
| 单位换算（长度/质量/时间/面积/体积/数据/温度） | `llmforever/units.py` | 否 | 确定 |
| 记事儿（名字、年龄、城市、生日、喜好、备注） | `llmforever/memory.py` | 否 | 写盘，重启还在 |
| 小知识库（约 150 条手写常识） | `llmforever/knowledge.py` | 否 | 高分命中才用，宁可不说也不瞎说 |
| 开放问题、闲聊、常识 | Qwen2.5-0.5B-Instruct（本地 CPU） | 是 | 5 亿参数，别指望太多 |
| 繁忙、越狱、投诉、人工客服 | `llmforever/brain.py`（彩蛋） | 否 | 祖传艺能，保留 |

路由顺序就是上面这张表：先便宜后贵，先确定后生成。

## 安装

```bash
python install.py          # 装依赖到 .vendor/，下模型到 models/（约 1 GB）
python install.py --deps   # 只装依赖
python main.py             # 启动窗口
```

依赖装在项目内的 `.vendor/`，不碰系统 `site-packages`，删文件夹就干净了。
模型权重在 `models/Qwen2.5-0.5B-Instruct/`，走 [ModelScope](https://modelscope.cn/models/Qwen/Qwen2.5-0.5B-Instruct) 下载（有断点续传）。

## 运行

```bash
python main.py           # 桌面窗口（pywebview）
python main.py --web     # 浏览器模式，不需要 pywebview
python main.py --web --port=8765
```

桌面窗口走 pywebview；如果那台机器上装不了 pywebview（或是在受限环境里跑不起来），
`--web` 用标准库 `http.server` 起一个本地页面，自动打开默认浏览器，功能一模一样。

## 测试

```bash
python -m unittest discover -s tests -v
```

22 个用例，全部不需要模型文件——引擎层是纯标准库。

## 目录

```
main.py                 # pywebview 外壳 + 会话状态
install.py              # 装依赖 / 下模型
index.html              # 界面
llmforever/
  arith.py              # 四则运算（递归下降，纯标准库）
  units.py              # 单位换算
  memory.py             # 结构化记忆，落盘 memory.json
  knowledge.py          # 手写小知识库
  model.py              # Qwen2.5-0.5B 懒加载推理
  brain.py              # 路由：工具优先，模型兜底，繁忙收尾
tests/test_engine.py
```

## 彩蛋：额度用完之后

20 次模型额度用尽，机器人会**整只退回 v0.0.1** —— 就是那个只会说「服务器繁忙」的版本，
连算术都不做了，还带工单号、人工客服死循环、`Error 507 算力资源不足`。
老代码一个字没改，原样躺在 `llmforever/v001.py` 里。

想把它叫回来，输入「重启」：

```
> 重启
[meta] 重启完成，v0.0.2 回来了，额度重新算 20 次。
       注意：这次重启只发生在对话里，进度条也是假的。
```

## 说明

- 模型只跑 CPU（这台机器没有可用 CUDA），首次调用要加载几秒，之后每句几秒。
- 回答的「确定性」不来自模型：算术、换算、记忆都是代码算的，模型只负责它该负责的部分。
- 额度（默认 20 次）只对模型回答计数；算数、换算、记忆永远不占额度——这一版至少不会用「繁忙」糊弄算术题了。
- `.vendor/`、`models/`、`memory.json` 都在 `.gitignore` 里，不要提交。
