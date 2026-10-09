import queue
import sys
import threading

import keyboard
import numpy as np
import sounddevice as sd
import soxr
from faster_whisper import WhisperModel

import commands
import tts

# ---------------- settings ----------------
MIC_NAME = "ME6S"
CHANNELS = 1
WHISPER_RATE = 16000
MODEL_SIZE = "base.en"
BLOCK = 1024

# Helps Whisper spell names and app names correctly.
HINT = "Amogh Prashanth. Chrome, Google, Roblox, Spotify, Fortnite."

START_KEY = "ctrl+alt+up"
STOP_KEY = "ctrl+alt+down"
QUIT_KEY = "ctrl+alt+q"

# ---------------- state ----------------
DEVICE = None
DEVICE_RATE = None
model = None
speaker = None

listening = False
audio_q = queue.Queue()
lock = threading.Lock()
capture_thread = None
capture_stop = threading.Event()


def resolve_input_device(name_hint=None):
    wasapi = next(
        i for i, api in enumerate(sd.query_hostapis()) if api["name"] == "Windows WASAPI"
    )
    candidates = [
        (i, d)
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0 and d["hostapi"] == wasapi
    ]
    if not candidates:
        raise RuntimeError("No WASAPI input devices found.")

    if name_hint:
        for i, d in candidates:
            if name_hint.lower() in d["name"].lower():
                return i
        print(f"[warn] '{name_hint}' not found, falling back")

    return candidates[0][0]


def drain_queue():
    chunks = []
    while not audio_q.empty():
        chunks.append(audio_q.get())
    return chunks


def capture_loop():
    # Blocking reads on our own thread. The ME6S does not support callback mode.
    try:
        with sd.InputStream(
            device=DEVICE,
            channels=CHANNELS,
            samplerate=DEVICE_RATE,
            dtype="float32",
        ) as s:
            while not capture_stop.is_set():
                try:
                    data, overflowed = s.read(BLOCK)
                except sd.PortAudioError:
                    break
                if overflowed:
                    print("[audio] overflow", file=sys.stderr)
                audio_q.put(data.copy())
    except sd.PortAudioError as e:
        print(f"[audio error] {e}", file=sys.stderr)


def stop_capture():
    global capture_thread
    capture_stop.set()
    if capture_thread is not None:
        capture_thread.join(timeout=2)
        capture_thread = None


def start_listening():
    global capture_thread
    drain_queue()
    capture_stop.clear()
    capture_thread = threading.Thread(target=capture_loop, name="capture_loop", daemon=True)
    capture_thread.start()
    print(f"\n[LISTENING] speak now, {STOP_KEY} to stop")


def stop_listening():
    stop_capture()

    chunks = drain_queue()
    if not chunks:
        print("[nothing captured]")
        speaker.say("I didn't hear anything.")
        return

    audio = np.concatenate(chunks, axis=0).flatten()
    duration = len(audio) / DEVICE_RATE
    print(f"[STOPPED] {duration:.1f}s captured, transcribing...")

    if duration < 0.3:
        print("[too short]")
        speaker.say("That was too short, try again.")
        return

    audio16 = soxr.resample(audio, DEVICE_RATE, WHISPER_RATE)

    segments, _ = model.transcribe(
        audio16, beam_size=5, vad_filter=True, initial_prompt=HINT
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()

    if text:
        print(f'\n>>> "{text}"')
        reply = commands.handle(text)
        print(f"[jarvis] {reply}\n")
        speaker.say(reply)
    else:
        print("[no speech detected]\n")
        speaker.say("Sorry, I didn't catch that.")


def on_start():
    global listening
    with lock:
        if listening:
            return
        listening = True
        speaker.stop()  # stop talking when you start talking
        start_listening()


def on_stop():
    global listening
    with lock:
        if not listening:
            return
        listening = False
        stop_listening()


def shutdown():
    global listening
    with lock:
        if listening:
            listening = False
            stop_capture()


if __name__ == "__main__":
    DEVICE = resolve_input_device(MIC_NAME)
    info = sd.query_devices(DEVICE, "input")
    DEVICE_RATE = int(info["default_samplerate"])
    print(f"Mic  : {info['name']} @ {DEVICE_RATE} Hz  (index {DEVICE})")

    print(f"Model: {MODEL_SIZE} loading...")
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    print("Voice: loading...")
    speaker = tts.Speaker()
    print("Ready.\n")
    print(f"  {START_KEY}  start listening")
    print(f"  {STOP_KEY}  stop and transcribe")
    print(f"  {QUIT_KEY}  quit\n")

    keyboard.add_hotkey(START_KEY, on_start)
    keyboard.add_hotkey(STOP_KEY, on_stop)
    speaker.say("Hello Amogh, I'm online.")
    keyboard.wait(QUIT_KEY)
    shutdown()
    speaker.close()
    print("Bye.")
