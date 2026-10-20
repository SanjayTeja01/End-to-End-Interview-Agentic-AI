"""Speech infrastructure (NOT agents): STT via faster-whisper, TTS via Piper. Both behind provider interfaces."""
from __future__ import annotations

import io
import logging
import os
import tempfile
import wave
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable

log = logging.getLogger(__name__)


class SpeechError(ServiceUnavailable):
    code = "speech_error"


@dataclass
class Transcript:
    text: str
    language: str | None
    duration_seconds: float | None
    avg_logprob: float | None


def call_with_timeout(fn, seconds: float, what: str):  # noqa: ANN001, ANN201
    """Run a native speech call (model load, transcription, synthesis) with a hard wait limit.

    These run inside C extensions where Celery's soft time limit cannot interrupt them, so a hang used to freeze
    the turn for the rest of the interview. Here the caller stops waiting after `seconds` and gets a SpeechError
    (the stuck thread is abandoned; the worker process is recycled after a few tasks)."""
    import concurrent.futures

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"speech-{what}")
    fut = pool.submit(fn)
    try:
        return fut.result(timeout=seconds)
    except concurrent.futures.TimeoutError as exc:
        raise SpeechError(f"{what} did not finish within {seconds:.0f}s") from exc
    finally:
        pool.shutdown(wait=False)


class STTProvider(Protocol):
    def transcribe(self, audio: bytes, ext: str) -> Transcript: ...


class TTSProvider(Protocol):
    available: bool

    def synthesize(self, text: str) -> bytes | None: ...  # WAV bytes


class FasterWhisperSTT:
    def __init__(self) -> None:
        s = get_settings()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechError("faster-whisper is not installed") from exc
        self._beam = s.stt_beam_size
        self._model = WhisperModel(s.stt_model, device=s.stt_device, compute_type=s.stt_compute_type,
                                   cpu_threads=s.stt_cpu_threads)

    def transcribe(self, audio: bytes, ext: str) -> Transcript:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(audio)
            path = tmp.name
        try:
            segments, info = self._model.transcribe(path, vad_filter=True, beam_size=self._beam)
            segs = list(segments)
        except Exception as exc:  # noqa: BLE001
            raise SpeechError("Transcription failed") from exc
        finally:
            os.unlink(path)
        text = " ".join(s.text.strip() for s in segs).strip()
        avg = sum(s.avg_logprob for s in segs) / len(segs) if segs else None
        return Transcript(text=text, language=getattr(info, "language", None),
                          duration_seconds=getattr(info, "duration", None), avg_logprob=avg)


class PiperTTS:
    def __init__(self) -> None:
        s = get_settings()
        self.available = False
        try:
            from piper.voice import PiperVoice
        except ImportError:
            log.warning("tts_unavailable", extra={"data": {"reason": "piper-tts not installed"}})
            return
        if not os.path.exists(s.piper_voice_path):
            log.warning("tts_unavailable", extra={"data": {"reason": "voice model missing", "path": s.piper_voice_path}})
            return
        self._voice = PiperVoice.load(s.piper_voice_path)
        self.available = True

    def synthesize(self, text: str) -> bytes | None:
        if not self.available:
            return None
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            if hasattr(self._voice, "synthesize_wav"):  # piper-tts >= 1.3
                self._voice.synthesize_wav(text, wf)
            else:  # piper-tts 1.2
                self._voice.synthesize(text, wf)
        return buf.getvalue()


class NullTTS:
    available = False

    def synthesize(self, text: str) -> bytes | None:
        return None


class StaticSTT:
    """Test double: returns a fixed transcript."""

    def __init__(self, text: str = "") -> None:
        self.text = text

    def transcribe(self, audio: bytes, ext: str) -> Transcript:
        return Transcript(text=self.text, language="en", duration_seconds=None, avg_logprob=None)


_stt_override: STTProvider | None = None
_tts_override: TTSProvider | None = None


def set_speech(stt: STTProvider | None = None, tts: TTSProvider | None = None) -> None:
    global _stt_override, _tts_override
    _stt_override, _tts_override = stt, tts


@lru_cache
def _stt() -> STTProvider:
    p = get_settings().stt_provider
    if p == "faster_whisper":
        return FasterWhisperSTT()
    raise SpeechError(f"Unknown STT_PROVIDER '{p}'")


@lru_cache
def _tts() -> TTSProvider:
    p = get_settings().tts_provider
    if p == "piper":
        return PiperTTS()
    if p == "none":
        return NullTTS()
    raise SpeechError(f"Unknown TTS_PROVIDER '{p}'")


def get_stt() -> STTProvider:
    return _stt_override or _stt()


def get_tts() -> TTSProvider:
    return _tts_override or _tts()
