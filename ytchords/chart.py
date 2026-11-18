"""Chord cleanup, beginner voicings, and chart formatting."""
from collections import Counter

from .model import ROOTS

OPEN = {
    "A": "x02220", "Am": "x02210", "B7": "x21202", "C": "x32010",
    "D": "xx0232", "Dm": "xx0231", "E": "022100", "Em": "022000",
    "Fmaj7": "xx3210", "G": "320003", "A7": "x02020", "D7": "xx0212",
    "E7": "020100", "G7": "320001", "Asus2": "x02200", "Asus4": "x02230",
    "Dsus2": "xx0230", "Dsus4": "xx0233", "Esus4": "022200",
}
INTERVALS = {
    "m": (0, 3, 7), "": (0, 4, 7), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "7": (0, 4, 7, 10), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
    "maj7": (0, 4, 7, 11), "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9),
}


def timestamp(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"


def join(segments):
    merged = []
    for start, end, chord in segments:
        if merged and merged[-1][2] == chord:
            start = merged.pop()[0]
        merged.append((start, end, chord))
    return merged


def clean(segments):
    segments = join(segments)
    kept = []
    for start, end, chord in segments:
        if end - start >= 0.5:
            kept.append((start, end, chord))
        elif kept:
            previous, _, label = kept[-1]
            kept[-1] = previous, end, label
    if kept and segments:
        _, end, chord = kept[0]
        kept[0] = segments[0][0], end, chord
    return join(kept)


def split_chord(chord):
    length = 2 if chord[1:2] in ("#", "b") else 1
    quality = chord[length:]
    return ROOTS.index(chord[:length]), quality


def desired_shape(root, quality):
    if quality in ("m7b5", "dim", "dim7"):
        return ROOTS[(root + 3) % 12] + "m"
    if quality.startswith("m") and not quality.startswith("maj"):
        return ROOTS[root] + "m"
    if root == 5 and quality in ("", "maj7", "6"):
        return "Fmaj7"
    if ROOTS[root] + quality in OPEN:
        return ROOTS[root] + quality
    return ROOTS[root]


def notes(chord):
    root, quality = split_chord(chord)
    return {(root + interval) % 12 for interval in INTERVALS[quality]}


OPEN_NOTES = {shape: notes(shape) for shape in OPEN}


def easy_chart(segments):
    changes = Counter(chord for _, _, chord in segments if chord not in ("N", "X"))

    def for_capo(capo):
        return {
            chord: desired_shape((root - capo) % 12, quality)
            for chord in changes
            for root, quality in [split_chord(chord)]
        }

    capo = max(range(12), key=lambda fret: sum(
        changes[chord] for chord, shape in for_capo(fret).items() if shape in OPEN
    ))
    shapes = for_capo(capo)
    for chord, shape in shapes.items():
        if shape in OPEN:
            continue
        target = notes(shape)
        root, _ = split_chord(shape)
        shapes[chord] = max(OPEN, key=lambda candidate: (
            len(target & OPEN_NOTES[candidate]) / len(target | OPEN_NOTES[candidate]),
            split_chord(candidate)[0] == root,
        ))
    return capo, join((start, end, shapes.get(chord, chord)) for start, end, chord in segments)


def chord_text(chord, easy):
    if chord in ("N", "X"):
        return "No chord" if chord == "N" else "Unknown"
    return f"{chord} ({OPEN[chord]})" if easy else chord


def render(header, segments, easy):
    if not segments:
        return header + "\n\nNo sustained chords detected.\n"
    cells = [f"{timestamp(start)}  {chord_text(chord, easy)}" for start, _, chord in segments]
    width = max(map(len, cells))
    lines = ["   ".join(cell.ljust(width) for cell in cells[i:i + 4]).rstrip()
             for i in range(0, len(cells), 4)]
    return header + "\n\n" + "\n".join(lines) + "\n"
