"""
AURA — Train Custom "Hey Aura" Wake Word
=========================================
Records your voice saying "Hey Aura" and trains a custom OpenWakeWord
model. Run this on the Pi after initial setup.

Completely free. No cloud. No subscription. Runs locally.

Usage:
    cd /config/aura/voice-agent
    python train_wake_word.py

The script will:
  1. Prompt you to say "Hey Aura" 16 times
  2. Record each sample (1.5 seconds each)
  3. Train a custom .onnx model
  4. Save it to models/hey_aura.onnx
  5. AURA automatically uses it on next restart

Takes about 2-3 minutes total.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("aura.train_wake_word")

SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_DIR = SCRIPT_DIR / "models"
OUTPUT_MODEL = MODELS_DIR / "hey_aura.onnx"
SAMPLES_DIR = MODELS_DIR / "training_samples"

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_DURATION = 1.5  # seconds per recording
PAUSE_BETWEEN = 1.5  # seconds between prompts

# Train on multiple natural phrases so AURA responds to how you actually talk.
# Each phrase gets recorded multiple times by each person.
PHRASES = [
    ("Hey Aura", 6),
    ("Aura", 4),
    ("Yo Aura", 4),
    ("Aye Aura", 2),
]


def record_sample(pa: "pyaudio.PyAudio", duration: float) -> np.ndarray:
    """Record a single audio sample from the microphone."""
    import pyaudio

    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=1024,
    )

    frames = []
    num_chunks = int(SAMPLE_RATE * duration / 1024)
    for _ in range(num_chunks):
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(np.frombuffer(data, dtype=np.int16))

    stream.stop_stream()
    stream.close()

    return np.concatenate(frames)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        import pyaudio
    except ImportError:
        print("ERROR: PyAudio not installed. Run: pip install pyaudio")
        sys.exit(1)

    # Create directories
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    total_samples = sum(count for _, count in PHRASES)

    print()
    print("=" * 50)
    print("  AURA — Wake Word Training")
    print("  Train custom 'Aura' detection")
    print("=" * 50)
    print()
    print("  AURA will respond to how you naturally talk:")
    for phrase, count in PHRASES:
        print(f"    '{phrase}' — {count} times")
    print()
    print(f"  {total_samples} total samples, {SAMPLE_DURATION}s each.")
    print(f"  Total time: ~{int(total_samples * (SAMPLE_DURATION + PAUSE_BETWEEN))} seconds.")
    print()
    print("  Both CC and Adon should each run this script so")
    print("  AURA recognizes both voices.")
    print()
    input("  Press Enter when ready… ")
    print()

    pa = pyaudio.PyAudio()
    samples = []
    sample_num = 0

    for phrase, count in PHRASES:
        print(f"\n  --- Say '{phrase}' ({count} times) ---\n")
        for i in range(count):
            sample_num += 1
            print(f"  [{sample_num}/{total_samples}] Say '{phrase}' now…", end="", flush=True)
            time.sleep(0.3)

            audio = record_sample(pa, SAMPLE_DURATION)
            samples.append(audio)

            safe_phrase = phrase.lower().replace(" ", "_")
            sample_path = SAMPLES_DIR / f"{safe_phrase}_{i + 1:02d}.npy"
            np.save(sample_path, audio)

            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
            print(f" recorded (RMS: {rms:.0f})")

            if sample_num < total_samples:
                time.sleep(PAUSE_BETWEEN)

    pa.terminate()

    print()
    print(f"  {total_samples} samples recorded across {len(PHRASES)} phrases.")
    print()

    # Train the model using OpenWakeWord's training utilities
    print("  Training custom wake word model…")
    print("  (This may take 1-2 minutes on Pi 5)")
    print()

    try:
        # OpenWakeWord supports training from positive examples
        from openwakeword import train  # type: ignore[import-untyped]

        # Combine samples into training data
        positive_samples = [s.astype(np.float32) / 32768.0 for s in samples]

        # Train and export the model
        train.train_custom_model(
            positive_examples=positive_samples,
            model_name="hey_aura",
            output_dir=str(MODELS_DIR),
            sample_rate=SAMPLE_RATE,
        )

        if OUTPUT_MODEL.exists():
            print(f"  Model saved to: {OUTPUT_MODEL}")
            print()
            print("  Training complete!")
            print("  Restart the voice agent to use the new wake word:")
            print("    systemctl restart aura_voice")
        else:
            print("  WARNING: Model file not found after training.")
            print("  The training may have used a different output name.")
            print(f"  Check {MODELS_DIR} for .onnx files.")

    except ImportError:
        # If openwakeword.train is not available, save samples for manual training
        print("  NOTE: OpenWakeWord training module not available in this version.")
        print(f"  Your {NUM_SAMPLES} voice samples are saved at:")
        print(f"    {SAMPLES_DIR}")
        print()
        print("  To train manually, use the OpenWakeWord training notebook:")
        print("  https://github.com/dscripka/openWakeWord#training-custom-models")
        print()
        print("  Or use the online training tool:")
        print("  https://github.com/dscripka/openWakeWord/tree/main/notebooks")
        print()
        print("  After training, place the .onnx file at:")
        print(f"    {OUTPUT_MODEL}")
        print("  Then restart: systemctl restart aura_voice")

    except Exception as exc:
        print(f"  Training failed: {exc}")
        print(f"  Your voice samples are saved at: {SAMPLES_DIR}")
        print("  You can retry training later.")

    print()


if __name__ == "__main__":
    main()
