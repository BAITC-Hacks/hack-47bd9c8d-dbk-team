"""
Звук: единственная точка, где загруженный файл превращается в массив.

16 кГц моно — форма, которую принимают и faster-whisper, и ESPnet, и детектор
языка, поэтому конверсия одна на всех и живёт отдельно от них.
"""

import io

import librosa


def load_audio(audio_bytes: bytes):
    """Load audio from bytes: float32 mono at 16 kHz (контейнер и кодек — на librosa)."""
    audio, _sr = librosa.load(io.BytesIO(audio_bytes), sr=16000)
    return audio
