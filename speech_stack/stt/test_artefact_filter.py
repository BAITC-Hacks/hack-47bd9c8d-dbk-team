#!/usr/bin/env python3
"""Фильтр артефактов снимает СЕГМЕНТ, а не всю расшифровку.

Стерегущий тест к дефекту 21 сен: файл 01:38:26 декодировался 1199 с, вернул
0 символов и код 200, потому что `HALLUCINATION.search` шёл по всему тексту.
Тест обязан ПАДАТЬ на прежнем правиле — иначе он ничего не стережёт, и это
проверяется здесь же, отдельным прогоном старой реализации.
"""
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode import HALLUCINATION, drop_artefact_segments  # noqa: E402


def seg(text):
    return SimpleNamespace(text=text, start=0.0, end=1.0, words=None)


# Прежнее правило, дословно — оно тут ТОЛЬКО чтобы показать, что тест его ловит.
def old_rule(segments):
    full = " ".join(s.text for s in segments).strip()
    return ([], len(segments)) if full and HALLUCINATION.search(full) else (list(segments), 0)


LONG = [seg(t) for t in [
    " Всем мыло. Да, да.",
    " Ну, главное, чтобы подключился тот, кто будет докладывать.",
    " Подписывайтесь на канал!",            # галлюцинация в тишине
    " Показания по холодной воде — сто двадцать три.",
    " Хорошо, записал, спасибо.",
]]
SHORT = [seg(" ПОДПИШИСЬ!")]                # ровно тот случай, ради которого фильтр писался


class ArtefactFilter(unittest.TestCase):
    def test_длинная_запись_теряет_только_артефакт(self):
        kept, dropped = drop_artefact_segments(LONG)
        self.assertEqual(dropped, 1)
        self.assertEqual(len(kept), 4)
        text = " ".join(s.text for s in kept)
        self.assertIn("сто двадцать три", text, "настоящая речь обязана уцелеть")
        self.assertNotIn("Подписывайтесь", text)

    def test_короткая_реплика_артефакт_пропадает_целиком(self):
        kept, dropped = drop_artefact_segments(SHORT)
        self.assertEqual((kept, dropped), ([], 1))

    def test_чистая_расшифровка_не_трогается(self):
        clean = LONG[:2] + LONG[3:]
        kept, dropped = drop_artefact_segments(clean)
        self.assertEqual((len(kept), dropped), (len(clean), 0))

    def test_стенд_умеет_провалиться(self):
        """Прежнее правило теряет ВСЁ — значит первый тест не пустой."""
        kept, dropped = old_rule(LONG)
        self.assertEqual(kept, [], "старое правило обязано было терять всю запись")
        self.assertEqual(dropped, len(LONG))


if __name__ == "__main__":
    unittest.main(verbosity=2)
