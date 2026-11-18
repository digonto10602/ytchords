"""Inference adapter for the vendored BTC-ISMIR19 large-vocabulary model."""
from itertools import groupby
from pathlib import Path
import sys

ROOTS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
QUALITIES = ("m", "", "dim", "aug", "m6", "6", "m7", "m(maj7)", "maj7",
             "7", "dim7", "m7b5", "sus2", "sus4")
LABELS = tuple(root + quality for root in ROOTS for quality in QUALITIES) + ("X", "N")
SAMPLE_RATE = 22050
MODEL_DIR = Path(__file__).with_name("_btc")


def analyse(wav):
    import librosa
    import numpy as np
    import torch

    from ._btc.btc_model import BTC_model
    from ._btc.utils.hparams import HParams

    config = HParams.load(MODEL_DIR / "run_config.yaml")
    config.model["num_chords"] = len(LABELS)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        torch.set_num_threads(min(4, torch.get_num_threads()))
    print(f"Running BTC large vocabulary on {device.upper()}…", file=sys.stderr)
    model = BTC_model(config.model).to(device).eval()
    # The legacy checkpoint stores the standard deviation as a NumPy scalar.
    allowed = [(np._core.multiarray.scalar, "numpy.core.multiarray.scalar"),
               np.dtype, np.dtypes.Float64DType]
    with torch.serialization.safe_globals(allowed):
        checkpoint = torch.load(MODEL_DIR / "btc_model_large_voca.pt",
                                map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"])

    audio, sr = librosa.load(wav, sr=SAMPLE_RATE, mono=True)
    if not len(audio):
        raise ValueError("The audio file is empty.")
    hop = config.feature["hop_length"]
    n_bins = config.feature["n_bins"]
    bins_per_octave = config.feature["bins_per_octave"]
    frames = config.model["timestep"]
    chunk_samples = round(config.mp3["inst_len"] * sr)
    duration = len(audio) / sr
    segments = []
    with torch.inference_mode():
        for offset in range(0, len(audio), chunk_samples):
            chunk = audio[offset:offset + chunk_samples]
            count = min(frames, (len(chunk) + hop - 1) // hop)
            padded = np.pad(chunk, (0, max(0, 8192 - len(chunk))))
            cqt = librosa.cqt(padded, sr=sr, hop_length=hop, n_bins=n_bins,
                              bins_per_octave=bins_per_octave)
            features = np.log(np.abs(cqt[:, :count].T) + 1e-6)
            features = (features - checkpoint["mean"]) / checkpoint["std"]
            features = np.pad(features, ((0, frames - count), (0, 0)))
            tensor = torch.as_tensor(features, dtype=torch.float32, device=device)[None]
            output, _ = model.self_attn_layers(tensor)
            predictions, _ = model.output_layer(output)
            index = 0
            for label, run in groupby(predictions.flatten()[:count].tolist()):
                start = (offset + index * hop) / sr
                index += sum(1 for _ in run)
                end = min((offset + index * hop) / sr, (offset + chunk_samples) / sr, duration)
                name = LABELS[label]
                if segments and segments[-1][2] == name:
                    start = segments.pop()[0]
                segments.append((start, end, name))

    chroma = librosa.feature.chroma_stft(y=audio, sr=sr).mean(axis=1)
    profiles = ([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
                [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    key = "Unknown"
    if np.std(chroma) > 1e-8:
        _, root, mode = max(
            (np.corrcoef(chroma, np.roll(profile, root))[0, 1], root, mode)
            for mode, profile in zip(("major", "minor"), profiles)
            for root in range(12)
        )
        key = f"{ROOTS[root]} {mode}"
    bpm, _ = librosa.beat.beat_track(y=audio, sr=sr)
    return segments, key, float(np.asarray(bpm).item())
