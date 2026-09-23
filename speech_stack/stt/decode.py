"""
Декодирование: обычный проход faster-whisper, длинная форма по VAD-чанкам,
второй проход ради word-таймингов и запасной путь через transformers.

Здесь живут измеренные решения о ДЕКОДЕРЕ — without_timestamps, ширина луча,
порог длинной формы. Какая модель отвечает, решено раньше, в asr_models.py:
сюда она приходит готовой, в model_obj.
"""

import os
import re

import torch

import asr_models
from audio import load_audio
from config import (DEFAULT_BEAM, DEFAULT_LANG, DEFAULT_PROMPT, DEVICE, LONGFORM_S,
                    VAD_MIN_SILENCE_MS, logger, norm_lang)


class _Seg:
    """Segment shaped like faster-whisper's, but with times we can shift."""

    __slots__ = ("text", "start", "end", "words")

    def __init__(self, text, start, end, words):
        self.text, self.start, self.end, self.words = text, start, end, words


class _Word:
    __slots__ = ("word", "start", "end", "probability")

    def __init__(self, word, start, end, probability):
        self.word, self.start, self.end, self.probability = word, start, end, probability


def _decode_longform(_m, audio, decode_kwargs):
    """Decode one VAD chunk at a time, restoring absolute timings."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    chunks = get_speech_timestamps(
        audio, VadOptions(min_silence_duration_ms=VAD_MIN_SILENCE_MS))
    kwargs = dict(decode_kwargs)
    kwargs["vad_filter"] = False          # we already did it, once, ourselves
    kwargs.pop("vad_parameters", None)

    out, info = [], None
    for c in chunks:
        off = c["start"] / 16000
        segs, chunk_info = _m.transcribe(audio[c["start"]:c["end"]], **kwargs)
        info = info or chunk_info
        for s in segs:
            words = [_Word(w.word, w.start + off, w.end + off, w.probability)
                     for w in (s.words or [])] if s.words else None
            out.append(_Seg(s.text, s.start + off, s.end + off, words))
    return out, info


def _cer(a: str, b: str) -> float:
    """Нормированное расстояние Левенштейна — насколько два прохода разошлись."""
    a, b = a.lower(), b.lower()
    if not a or not b:
        return 0.0 if a == b else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(len(a), len(b))


# Заученные артефакты: whisper выдаёт их вместо расшифровки на звуке, где речи
# почти нет. Список не выдуман — он уже жил в шести скриптах обучающего
# конвейера (export_asr_trainset, reconcile_labels, label_calls, name_density,
# probe_bfm, prepare_ehistory_tts), и это шесть копий одной правды, которые
# разойдутся. Дом у него здесь: служба фильтрует, и любой потребитель получает
# это не зная, что оно есть — ровно как `for_tts` внутри TTS.
#
# Риска потерять сказанное нет: «DimaTorzok», «Amara.org» и «Субтитры сделал»
# абонент водоканала не произносит, а на совещании их не диктуют.
HALLUCINATION = re.compile(
    r"[Сс]убтитр|[Пп]родолжение следует|DimaTorzok|Amara\.org|"
    r"[Сс]пасибо за просмотр|[Пп]одписывайтесь|ПОДПИШИСЬ|"
    r"[Рр]едактор субтитров|[Кк]орректор\s+А\.|ПОКОЙНАЯ МУЗЫКА",
    re.I)


def drop_artefact_segments(segments):
    """Снимает сегменты-артефакты, возвращает (оставленные, сколько снято).

    ПОСЕГМЕНТНО, а не по всей расшифровке: см. комментарий на месте вызова.
    Вынесено из цикла, чтобы правило проверялось тестом, а не пересказом.
    """
    kept, dropped = [], 0
    for seg in segments:
        if HALLUCINATION.search(seg.text):
            dropped += 1
            continue
        kept.append(seg)
    return kept, dropped

# Ниже этого — не слово, а обрывок. Порог взят ИЗ ЗАЗОРА, а не назначен:
# замерено 11 сен на 29 настоящих тихих паузах из звонков против 200 реплик с
# человеческой меткой. Речи в репликах: минимум 777 мс, p10 1313. В паузах:
# медиана 0, и ровно 20 из 29 дают чистый ноль. Корреляция полная — где VAD
# видит 0 мс, whisper не сочинил НИ РАЗУ (0 из 20); где видит обрывок, выдал
# текст во всех 9 случаях, включая «ПОДПИШИСЬ!» на 32 мс.
#
# 250 мс, а не 700 (где отсекалось бы 90 % пауз при нуле потерь на замере):
# в выборке нет односложных ответов, а «да» и «жоқ» — это 200-400 мс, и
# потерянное подтверждение дороже лишней «Мхм». Поднимать имеет смысл для
# расшифровки совещаний, где коротких подтверждений нет: WHISPER_MIN_SPEECH_MS.
MIN_SPEECH_MS = int(os.environ.get("WHISPER_MIN_SPEECH_MS", "250"))


def speech_ms(audio) -> float:
    """Сколько миллисекунд речи в клипе по Silero. 0 при любой поломке VAD."""
    try:
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        ts = get_speech_timestamps(
            audio, VadOptions(min_speech_duration_ms=0,
                              min_silence_duration_ms=VAD_MIN_SILENCE_MS,
                              speech_pad_ms=0))
        return sum(x["end"] - x["start"] for x in ts) / 16.0
    except Exception:
        # Ворота не имеют права уронить расшифровку: не смогли измерить —
        # пропускаем, как было до них.
        logger.exception("VAD-ворота: измерить не удалось, пропускаю")
        return float("inf")


def transcribe_whisper(audio_bytes: bytes, language: str | None = None, word_timestamps: bool = False,
                       prompt: str | None = None, model_obj=None, beam_size: int | None = None,
                       hotwords: str | None = None) -> dict:
    """Transcribe using Whisper. model_obj selects which loaded model (KSC2 or EN)."""
    # Load audio from bytes
    audio = load_audio(audio_bytes)

    if MIN_SPEECH_MS > 0:
        ms = speech_ms(audio)
        if ms < MIN_SPEECH_MS:
            logger.info("VAD-ворота: речи %.0f мс < %d — расшифровка не "
                        "запускается, возвращается пусто", ms, MIN_SPEECH_MS)
            return {"text": "", "segments": [], "language": language or "",
                    "duration": len(audio) / 16000.0}

    from faster_whisper import WhisperModel
    _m = model_obj if model_obj is not None else asr_models.whisper_model
    if isinstance(_m, WhisperModel):
        # "auto" (and only "auto") means: let Whisper detect. Anything else keeps
        # the old behaviour exactly, including bare None -> DEFAULT_LANG, so no
        # existing caller changes. Autodetect exists because a bilingual RU/KZ
        # call agent cannot know the language before the caller speaks — the
        # Yandex STT it replaces did this with a ru/kk whitelist.
        _lang = None if norm_lang(language) == "auto" else (language or DEFAULT_LANG)
        decode_kwargs = dict(
            language=_lang,
            # Beam 5 is the live default because latency is the product here.
            # Beam 10 (+patience 2) is measurably better but 2.2x slower: on 80
            # random clips CER 0.0017 -> 0.0011, and on the 52 clips the corpus
            # audit flagged as ASR failures it fixes 11 of them (5 -> 16 exact)
            # and cuts dropped words 34 -> 20.  So offline work — auditing labels,
            # re-checking a disagreement — should ask for the wide beam; a voice
            # agent waiting on a reply should not.
            beam_size=beam_size or DEFAULT_BEAM,
            patience=2.0 if (beam_size or DEFAULT_BEAM) >= 10 else 1.0,
            word_timestamps=word_timestamps,
            # Do not make the decoder emit timestamp tokens unless the caller
            # actually wants them.  Measured on 80 labelled KazakhTTS2 clips
            # (voice-agents/training/whisper_sweep.py): with timestamp tokens the
            # model mangles or drops the FIRST word of 40 % of utterances and
            # scores CER 0.0274; without them the first-word error is 0 % and CER
            # is 0.0017 — a 16x reduction — while running ~14 % faster.  Stock
            # large-v3 shows the same 41 % first-word failure, so this is Whisper
            # behaviour, not something the KSC2 fine-tune introduced.  Segment
            # start/end are unaffected: they come from the VAD, not the decoder,
            # and long-form (60 s / 158 s) was verified not to regress.
            without_timestamps=not word_timestamps,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=VAD_MIN_SILENCE_MS),
            # Anti-hallucination: stop the decoder looping garbage on trailing
            # silence (KSC2 model emits Kazakh-glyph runs otherwise).
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            initial_prompt=prompt or DEFAULT_PROMPT,
            # Hotwords are NOT a second, cleverer channel: faster-whisper's
            # get_prompt() puts them in the SAME `sot_prev` region as
            # initial_prompt, just ahead of it and truncated at
            # max_length//2 - 1 tokens. Exposed anyway because it is the
            # conventional API for "here is a list of proper nouns that may
            # occur", callers expect it, and it truncates by TOKENS where a
            # caller-built prompt truncates by guesswork. Expect the content
            # of the list to matter and the choice of field not to.
            # Ignored by faster-whisper when `prefix` is set; we never set it.
            hotwords=hotwords or None,
        )
        # Word alignment is measured to WRECK this fine-tune's output: on 40
        # labelled clips, word_timestamps=True scores CER 0.6788 against 0.0026
        # for the plain path, emitting hallucinated tails ("і қазақстан қазақстан")
        # at probability 0.00.  So the text is always produced by the accurate
        # path; a caller asking for word timings gets a SECOND, alignment-only
        # pass, and those timings are attached only if that pass agrees with the
        # accurate transcript.  Never trade the transcript for its timings.
        want_words = decode_kwargs.pop("word_timestamps", False)
        decode_kwargs["word_timestamps"] = False
        decode_kwargs["without_timestamps"] = True

        if len(audio) / 16000 > LONGFORM_S:
            segments, info = _decode_longform(_m, audio, decode_kwargs)
            # `info` остаётся None, если VAD не нашёл В ЗАПИСИ НИ ОДНОГО чанка
            # речи: тишина, гудки, музыка, обрыв линии. Раньше следом безусловно
            # читалось `info.language`, то есть на такой файл сервис отдавал 500
            # вместо пустой расшифровки. По этому пути пойдут 9 000 часов годовой
            # выгрузки и уже ходит нарезка источников (prepare_news_tts.sh), где
            # одна пятисотка роняет всю партию из 25 выпусков. Пустая запись —
            # нормальный ответ, а не отказ; поля заполняем честно, вероятность
            # языка 0.0 именно потому, что детекции не было.
            if info is None:
                logger.info("longform: VAD не нашёл речи в %.1f с — пустая расшифровка",
                            len(audio) / 16000)
                return {"text": "", "language": _lang or DEFAULT_LANG,
                        "language_probability": 0.0,
                        "duration": len(audio) / 16000, "segments": []}
        else:
            segments, info = _m.transcribe(audio, **decode_kwargs)

        if want_words:
            segments = list(segments)
            plain = " ".join(s.text for s in segments).strip()
            align_kwargs = dict(decode_kwargs, word_timestamps=True,
                                without_timestamps=False)
            aligned = list(_m.transcribe(audio, **align_kwargs)[0])
            got = " ".join(s.text for s in aligned).strip()
            # Побуквенное равенство недостижимо на длинной записи: проходы идут
            # с разными `without_timestamps`, и один знак препинания снимал
            # метки целиком. Измерено на минутных блоках ElevenLabs — метки не
            # возвращались НИ РАЗУ, и нарезка по ним была невозможна. Порог 5 %
            # оставляет исходный смысл («не менять расшифровку ради таймингов»):
            # при таком расхождении это та же расшифровка, а не другая.
            # 0.15 -> 0.40, 10 сен. Единственный потребитель словных меток —
            # `training/cut_el_*.py`; агент ходит с `response_format=json` и до
            # этой ветки не доходит. У резака свои ворота 0.25 НА КАЖДУЮ ФРАЗУ,
            # то есть качество проверяется там, где его видно. Здесь порог лишь
            # терял блоки целиком: партия B134-B179 читается числами, два
            # прохода расходятся на их ЗАПИСИ (CER 0.15-0.33) при исправном
            # звуке и верном прочтении.
            if _cer(got, plain) <= float(os.environ.get("WHISPER_WORD_ALIGN_CER", "0.40")):
                segments = aligned
            else:
                logger.warning("word alignment disagreed with the transcript "
                               "(CER %.3f); returning text without word timings",
                               _cer(got, plain))
                want_words = False
        word_timestamps = want_words

        text_parts = []
        seg_list = []
        word_list = []
        # Заученный артефакт, а не расшифровка. Замерено 11 сен: на паузах
        # из звонков whisper выдавал «ПОДПИШИСЬ!» на 32 мс речи и
        # «ПОКОЙНАЯ МУЗЫКА» на 1008 мс. Такой ответ хуже пустого: он
        # читается как сказанное и уходит в перевод или в протокол
        # совещания неотличимо от настоящей реплики.
        #
        # Снимается ПОСЕГМЕНТНО, и это не косметика. Поиск по всей
        # расшифровке убивал многочасовую запись из-за одной галлюцинации
        # в тишине: 21 сен файл 01:38:26 декодировался 1199 с, вернул
        # 0 символов и код 200, а отброшенный текст начинался настоящей
        # речью («Всем мыло. Да, да. Ну, главное, чтобы подключился тот,
        # кто б…»). Чем длиннее звук, тем вероятнее совпадение где-то
        # внутри, то есть прежнее правило отказывало тем чаще, чем дороже
        # был прогон. На короткой реплике, ради которой фильтр и писался,
        # сегмент один — там поведение прежнее, ответ пропадает целиком.
        segments, dropped = drop_artefact_segments(segments)
        for seg in segments:
            text_parts.append(seg.text)
            seg_list.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            })
            if word_timestamps and seg.words:
                for w in seg.words:
                    word_list.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "probability": round(w.probability, 3),
                    })
        full_text = " ".join(text_parts).strip()
        if dropped:
            logger.info("фильтр артефактов: снято %d сегмент(ов) из %d, "
                        "оставлено %d символов",
                        dropped, dropped + len(seg_list), len(full_text))
        result = {
            "text": full_text,
            "language": info.language,
            # The caller that asked for "auto" needs to know how sure the
            # detection was — a bilingual agent switches its TTS voice on this.
            "language_probability": round(getattr(info, "language_probability", 1.0) or 1.0, 3),
            "duration": info.duration,
            "segments": seg_list,
        }
        if word_timestamps:
            result["words"] = word_list
        return result
    else:
        # Transformers fallback (no word-level timestamps available)
        processor = _m["processor"]
        model = _m["model"]

        inputs = processor(audio, sampling_rate=16000, return_tensors="pt").input_features.to(DEVICE)
        forced_ids = processor.get_decoder_prompt_ids(
            language=language or "kazakh",
            task="transcribe",
        )
        with torch.no_grad():
            generated_ids = model.generate(
                inputs,
                forced_decoder_ids=forced_ids,
                max_length=448,
                num_beams=5,
            )
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return {"text": text.strip(), "language": language or "kk"}


def transcribe_turkic(audio_bytes: bytes) -> dict:
    """Transcribe using ISSAI TurkicASR."""
    if asr_models.turkic_asr_model is None:
        raise RuntimeError("TurkicASR model not loaded")

    audio = load_audio(audio_bytes)
    results = asr_models.turkic_asr_model(audio)
    text = results[0][0] if results else ""
    return {"text": text}
