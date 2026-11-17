"""Narration with Kokoro-82M on the CPU, one line at a time so each length is known."""

import os
import subprocess
import urllib.request

import numpy as np

SAMPLE_RATE = 24000
RELEASE = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
)
FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")
VOICES = {"en": ("af_heart", "en-us"), "es": ("ef_dora", "es")}
SPEED = 1.0
MP3_BITRATE = "64k"  # speech; plenty for one voice


def model_dir():
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.environ.get("KOKORO_DIR", os.path.join(app_dir, "checkpoints", "kokoro"))


def download():
    """Fetch the model files once (325 MB + 28 MB); they are not in git."""
    folder = model_dir()
    os.makedirs(folder, exist_ok=True)
    for name in FILES:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            print(f"Downloading {name} ...", flush=True)
            urllib.request.urlretrieve(f"{RELEASE}/{name}", path + ".part")
            os.replace(path + ".part", path)
    return folder


_kokoro = None


def voice():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro

        folder = download()
        _kokoro = Kokoro(os.path.join(folder, FILES[0]), os.path.join(folder, FILES[1]))
    return _kokoro


def speak(text, language="en"):
    """One line -> float32 samples at 24 kHz. Empty text -> empty array."""
    if not text.strip():
        return np.zeros(0, dtype=np.float32)
    name, lang = VOICES.get(language, VOICES["en"])
    samples, rate = voice().create(text, voice=name, speed=SPEED, lang=lang)
    assert rate == SAMPLE_RATE, rate
    return trim(np.asarray(samples, dtype=np.float32))


def trim(samples, threshold=0.003):
    """Cut the silence Kokoro leaves at both ends, so the timing is the voice itself."""
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if len(loud) == 0:
        return samples[:0]
    margin = int(0.03 * SAMPLE_RATE)
    return samples[max(0, loud[0] - margin) : loud[-1] + margin]


def mix(lines, duration):
    track = np.zeros(int(round(duration * SAMPLE_RATE)), dtype=np.float32)
    for start, samples in lines:
        i = int(round(start * SAMPLE_RATE))
        end = min(len(track), i + len(samples))
        track[i:end] += samples[: end - i]
    return np.clip(track, -1.0, 1.0)


def to_mp3(samples, path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "f32le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            MP3_BITRATE,
            path,
        ],
        input=samples.astype(np.float32).tobytes(),
        check=True,
    )
    return path
