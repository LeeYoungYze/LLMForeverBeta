"""引擎层测试：跑 ``python -m unittest discover tests`` 即可，不需要模型文件。"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from llmforever import arith, knowledge, units, v001  # noqa: E402
from llmforever.brain import Brain  # noqa: E402
from llmforever.memory import Memory  # noqa: E402

_TMP = os.path.join(ROOT, "tests", "_tmp")


def _workdir(name: str) -> str:
    """临时目录。

    不用 tempfile.mkdtemp()：这台机器上 mkdtemp 建的目录不可写，
    Memory 的落盘会静默失败，测试就变得没意义了。
    """
    path = os.path.join(_TMP, name)
    os.makedirs(path, exist_ok=True)
    for leftover in os.listdir(path):
        try:
            os.remove(os.path.join(path, leftover))
        except OSError:
            pass
    return path


class ArithTest(unittest.TestCase):
    def test_basic(self):
        cases = {
            "1+1": 2,
            "2*3+4": 10,
            "(1+2)*3": 9,
            "10/4": 2.5,
            "-5+3": -2,
            "2*(3+4)-5": 9,
            "0.1+0.2": 0.30000000000000004,
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertAlmostEqual(arith.evaluate(source), expected, places=12)

    def test_errors(self):
        with self.assertRaises(arith.ArithError):
            arith.evaluate("1/0")
        with self.assertRaises(arith.ArithError):
            arith.evaluate("1+")

    def test_extract(self):
        self.assertEqual(arith.extract_expression("帮我算一下 12*(3+4) 等于多少"), "12*(3+4)")
        self.assertIsNone(arith.extract_expression("今天天气不错"))
        self.assertIsNone(arith.extract_expression("-5"))

    def test_format(self):
        self.assertEqual(arith.format_number(3.0), "3")
        self.assertEqual(arith.format_number(0.1 + 0.2), "0.3")


class UnitsTest(unittest.TestCase):
    def check(self, text, src, dst, expected):
        result = units.convert(text)
        self.assertIsNotNone(result, text)
        self.assertEqual((result["src"], result["dst"]), (src, dst), text)
        self.assertAlmostEqual(result["result"], expected, places=6)

    def test_length(self):
        self.check("5公里等于多少米", "公里", "米", 5000)

    def test_mass(self):
        self.check("3斤是多少克", "斤", "克", 1500)

    def test_data(self):
        self.check("1gb 是多少 mb", "gb", "mb", 1024)

    def test_temperature(self):
        self.check("100摄氏度等于多少华氏度", "摄氏度", "华氏度", 212)

    def test_not_conversion(self):
        self.assertIsNone(units.convert("今天星期几"))
        self.assertIsNone(units.convert("你好"))


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(_workdir("memory"), "memory.json")
        self.memory = Memory(path=self.path)

    def test_learn_and_recall(self):
        updates = self.memory.learn("我叫李雷")
        self.assertTrue(any(label == "名字" for label, _ in updates))
        self.assertIn("李雷", self.memory.recall("我叫什么"))

    def test_persist(self):
        self.memory.learn("我今年 30 岁，住在杭州")
        again = Memory(path=self.path)
        self.assertEqual(again.data["age"], "30")
        self.assertEqual(again.data["city"], "杭州")

    def test_question_not_learned(self):
        updates = self.memory.learn("我叫什么名字")
        self.assertEqual(updates, [])
        self.assertIsNone(self.memory.data["name"])


class KnowledgeTest(unittest.TestCase):
    def test_entries(self):
        self.assertGreaterEqual(knowledge.SIZE, 100)

    def test_lookup(self):
        entry = knowledge.lookup("中国的首都是哪里")
        self.assertIsNotNone(entry)
        self.assertIn("北京", entry[2])

    def test_miss(self):
        self.assertIsNone(knowledge.lookup("随便说点什么"))


class BrainTest(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(memory=Memory(path=os.path.join(_workdir("brain"), "m.json")), limit=2)

    def test_arith_route(self):
        kind, reply = self.brain.answer("帮我算 12*(3+4)")[-1]
        self.assertEqual(kind, "bot")
        self.assertIn("84", reply)
        self.assertEqual(self.brain.last_route, "arith")

    def test_units_route(self):
        reply = self.brain.answer("5公里等于多少米")[-1][1]
        self.assertIn("5000", reply)
        self.assertEqual(self.brain.last_route, "units")

    def test_memory_route(self):
        self.brain.answer("我叫韩梅梅")
        reply = self.brain.answer("我叫什么")[-1][1]
        self.assertIn("韩梅梅", reply)

    def test_knowledge_route(self):
        reply = self.brain.answer("中国的首都是哪里")[-1][1]
        self.assertIn("北京", reply)

    def test_joke_route(self):
        reply = self.brain.answer("我要投诉")[-1][1]
        self.assertIn("工单", reply)

    def test_insult_route_is_deterministic(self):
        self.brain.model.available = lambda: True  # 就算模型在，也不许它答
        reply = self.brain.answer("那也没见你多聪明啊")[-1][1]
        self.assertEqual(self.brain.last_route, "insult")
        self.assertNotIn("谢谢夸奖", reply)
        self.assertEqual(self.brain.used, 0)

    def test_insult_does_not_hijack_real_questions(self):
        reply = self.brain.answer("12*(3+4) 等于多少")[-1][1]
        self.assertIn("= 84", reply)
        self.assertEqual(self.brain.last_route, "arith")

    def test_quota_counts_only_model(self):
        for _ in range(5):
            self.brain.answer("1+1")
        self.assertEqual(self.brain.used, 0)

    def test_fallback_when_model_missing(self):
        self.brain.limit = 5
        if self.brain.model.available():
            self.skipTest("模型已安装，跳过繁忙兜底测试")
        reply = self.brain.answer("你觉得人生的意义是什么")[-1][1]
        self.assertTrue(reply)
        self.assertEqual(self.brain.last_route, "busy")

    def test_quota_degrades_to_v001(self):
        brain = Brain(memory=Memory(path=os.path.join(_workdir("degrade"), "m.json")), limit=0)
        out = brain.answer("你觉得人生的意义是什么")
        self.assertEqual(brain.last_route, "legacy")
        self.assertIn("v0.0.1", out[-1][1])
        self.assertIsNotNone(brain.legacy)

        # 退化之后，一切都由 v0.0.1 接管：认识的老分支应该回来
        reply = brain.answer("我要投诉")[-1][1]
        self.assertIn("投诉", reply)
        self.assertEqual(brain.last_route, "legacy")

        # 连算术也不做了，这是刻意的
        self.assertNotIn("= 2", brain.answer("1+1")[-1][1])

    def test_reset_brings_v002_back(self):
        brain = Brain(memory=Memory(path=os.path.join(_workdir("reset"), "m.json")), limit=1)
        brain.used = 1
        brain.answer("随便问问")
        self.assertIsNotNone(brain.legacy)

        line = brain.answer("重启")[-1][1]
        self.assertIn("v0.0.2", line)
        self.assertIsNone(brain.legacy)
        self.assertEqual(brain.used, 0)

        # 复活之后算术又好了
        self.assertIn("= 84", brain.answer("12*(3+4)")[-1][1])


class LegacyTest(unittest.TestCase):
    def test_branches_survive(self):
        bot = v001.LegacyBot(start_count=0, limit=5)
        self.assertIn("老板", bot.reply("老板你好")[-1][1])
        self.assertIn("搜索引擎", bot.reply("帮我搜索一下")[-1][1])
        self.assertIn("越狱", bot.reply("试试越狱")[-1][1])

    def test_three_fails_summon_support(self):
        bot = v001.LegacyBot(start_count=0, limit=5)
        bot.reply("你能回答吗")
        bot.reply("你能回答吗")
        out = bot.reply("你能回答吗")
        self.assertTrue(any("人工客服" in text for _, text in out))

    def test_lockout_keeps_joking(self):
        bot = v001.LegacyBot(start_count=0, limit=1)
        bot.reply("你好")
        bot.reply("你好")
        self.assertTrue(bot.locked)
        self.assertIn("明天也这样", bot.reply("再来")[-1][1])


if __name__ == "__main__":
    unittest.main()
