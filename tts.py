import queue
import re
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from piper import PiperVoice
from piper.config import SynthesisConfig

# The .onnx and .onnx.json files must sit next to this script.
VOICE_PATH = Path(__file__).parent / "en_US-ryan-medium.onnx"

# 1.0 = normal speed. Higher = slower (1.15 is about 15% slower).
SPEED = 1.15

# Silence added around each phrase (seconds) so the speakers don't clip the edges.
PAD_START = 0.25
PAD_END = 0.30

# Words Piper says wrong -> how to spell them so it says them right.
PRONUNCIATIONS = {
    "Amogh": "Uh-mohg",
}


class Speaker:
    def __init__(self, voice_path=VOICE_PATH):
        self.voice = PiperVoice.load(str(voice_path))
        self.config = SynthesisConfig(length_scale=SPEED)
        self.q = queue.Queue()
        self.generation = 0  # bumps on stop() so stale speech gets dropped
        self.thread = threading.Thread(target=self._worker, name="tts", daemon=True)
        self.thread.start()
        self._synthesize("ready")  # warm-up so the first real reply is fast

    def say(self, text):
        if text:
            self.q.put((self.generation, text))

    def stop(self):
        """Cut off current speech and anything queued (e.g. when you start talking)."""
        self.generation += 1
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        sd.stop()

    def close(self):
        self.stop()
        self.q.put(None)
        self.thread.join(timeout=2)

    def _fix_pronunciation(self, text):
        for word, spoken in PRONUNCIATIONS.items():
            text = re.sub(rf"\b{re.escape(word)}\b", spoken, text, flags=re.IGNORECASE)
        return text

    def _synthesize(self, text):
        chunks = list(self.voice.synthesize(self._fix_pronunciation(text), syn_config=self.config))
        if not chunks:
            return None, None
        rate = chunks[0].sample_rate
        audio = np.concatenate([c.audio_float_array for c in chunks])
        audio = np.concatenate([
            np.zeros(int(PAD_START * rate), dtype=audio.dtype),
            audio,
            np.zeros(int(PAD_END * rate), dtype=audio.dtype),
        ])
        return audio, rate

    def _worker(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            gen, text = item
            try:
                audio, rate = self._synthesize(text)
            except Exception as e:
                print(f"[tts error] {e}")
                continue
            if audio is None or gen != self.generation:
                continue  # interrupted while synthesizing
            sd.play(audio, rate)
            sd.wait()
