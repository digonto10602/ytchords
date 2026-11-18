"""Local word transcription and time-aligned chord sheets."""
from bisect import bisect_left
from collections import defaultdict
import json
import sys
from tempfile import NamedTemporaryFile

from .chart import OPEN, timestamp
from .media import CACHE


def transcribe(wav):
    import torch
    import whisper

    cache = CACHE / "lyrics"
    cache.mkdir(parents=True, exist_ok=True)
    transcript = cache / f"{wav.stem}.whisper-small.json"
    audio_version = [wav.stat().st_size, wav.stat().st_mtime_ns]
    try:
        saved = json.loads(transcript.read_text(encoding="utf-8"))
        if saved["audio"] == audio_version:
            return saved["lines"]
    except (OSError, ValueError, KeyError):
        pass

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        torch.set_num_threads(min(4, torch.get_num_threads()))
    print(f"Transcribing vocals locally with Whisper small on {device.upper()}…", file=sys.stderr)
    try:
        model = whisper.load_model("small", device=device)
        result = model.transcribe(str(wav), word_timestamps=True, fp16=device == "cuda",
                                  condition_on_previous_text=False, verbose=None)
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"Local lyric transcription failed: {error}") from error

    lines = []
    for segment in result["segments"]:
        line = []
        length = 0
        for word in segment.get("words", []):
            text = " ".join(word["word"].split())
            if not text:
                continue
            if line and length + len(text) + 1 > 68:
                lines.append(line)
                line, length = [], 0
            line.append([word["start"], word["end"], text])
            length += len(text) + 1
        if line:
            lines.append(line)

    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache, delete=False) as file:
        temporary = cache / file.name
        try:
            json.dump({"audio": audio_version, "lines": lines}, file, ensure_ascii=False)
            file.close()
            temporary.replace(transcript)
        finally:
            temporary.unlink(missing_ok=True)
    return lines


def render_lyrics(header, segments, lines, easy):
    changes = [(start, chord) for start, _, chord in segments if chord not in ("N", "X")]
    sheet = [header, "", "Lyrics and chord placement estimated from the recording."]
    if easy and changes:
        names = dict.fromkeys(chord for _, chord in changes)
        sheet.extend(["", "Fingerings (low E to high E)"])
        fingerings = [f"{name} {OPEN[name]}" for name in names]
        sheet.extend("   ".join(fingerings[i:i + 5]) for i in range(0, len(fingerings), 5))
    if not lines:
        sheet.extend(["", "No timed words detected."])

    index = 0
    for line in lines:
        if not line:
            continue
        first, last = line[0][0], line[-1][1]
        before = index
        while index < len(changes) and changes[index][0] < first - 0.35:
            index += 1
        if index > before:
            sheet.extend(["", *[f"{timestamp(t)}  {chord}" for t, chord in changes[before:index]]])

        starts = [word[0] for word in line]
        labels = defaultdict(list)
        while index < len(changes) and changes[index][0] <= last:
            onset, chord = changes[index]
            word = bisect_left(starts, onset)
            if word > 0 and (word == len(line) or
                             onset != starts[word] and
                             onset - line[word - 1][1] <= starts[word] - onset):
                word -= 1
            labels[word].append(chord)
            index += 1

        prefix = f"{timestamp(first)}  "
        words = prefix
        chord_rows = [" " * len(prefix) for _ in range(max(map(len, labels.values()), default=0))]
        for word, (_, _, text) in enumerate(line):
            column = len(words)
            chord_names = labels[word]
            for row, name in enumerate(chord_names):
                chord_rows[row] = chord_rows[row].ljust(column) + name
            width = max(len(text), max(map(len, chord_names), default=0))
            words += text.ljust(width) + " "
        sheet.extend(["", *chord_rows, words.rstrip()])

    if index < len(changes):
        sheet.extend(["", *[f"{timestamp(t)}  {chord}" for t, chord in changes[index:]]])
    return "\n".join(sheet) + "\n"
