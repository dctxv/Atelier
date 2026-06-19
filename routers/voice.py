"""Local speech-to-text (Stage 3 upgrade).

Browser-native SpeechRecognition only works in real Google Chrome / Edge — other
Chromium forks (Comet, Brave, …) expose the API but ship no speech backend, so it
silently returns nothing. To make voice input browser-independent, transcription
runs server-side via faster-whisper: the client records a clip and uploads it here.

The model is loaded once (lazily, on first request) and kept in memory. The first
request also downloads the weights (~140 MB for "base") — subsequent calls are fast.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api")

# "base" is the latency/accuracy sweet spot for CPU int8 — near-realtime on a
# sentence while still accurate for clear dictation. Override with env if a
# machine wants more accuracy ("small"/"medium") or has a GPU.
_MODEL_SIZE   = os.getenv("ATELIER_WHISPER_MODEL", "base")
_MODEL_DEVICE = os.getenv("ATELIER_WHISPER_DEVICE", "cpu")
# int8 on CPU is robust everywhere; float16 suits CUDA.
_COMPUTE_TYPE = os.getenv("ATELIER_WHISPER_COMPUTE", "int8")

_model = None
_model_lock = asyncio.Lock()


async def _get_model():
    global _model
    if _model is None:
        async with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel
                _model = await asyncio.to_thread(
                    WhisperModel, _MODEL_SIZE, device=_MODEL_DEVICE, compute_type=_COMPUTE_TYPE,
                )
    return _model


@router.post("/voice/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    data = await audio.read()
    if not data:
        raise HTTPException(400, "empty audio")

    model = await _get_model()

    # faster-whisper reads from a path; PyAV (bundled) decodes the webm/opus that
    # MediaRecorder produces. Use the uploaded extension so the decoder is happy.
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()

        def _run() -> str:
            # beam_size=1 (greedy) keeps latency low; dictation is usually clean
            # enough that beam search buys little. language pinned to English.
            segments, _info = model.transcribe(tmp.name, language="en", beam_size=1)
            return " ".join(seg.text.strip() for seg in segments).strip()

        text = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    return {"text": text}
