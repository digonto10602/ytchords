"""ytchords command-line entry point."""
import argparse
import curses
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from threading import Event

from ytamp.config import Config
from ytamp.playlist import Playlist, Track
from ytamp.search import Searcher, looks_like_url

from .chart import clean, easy_chart, render
from .lyrics import render_lyrics, transcribe
from .media import cached_track, download, video_id
from .model import analyse
from .terminal import pick, play


def is_link(query):
    return looks_like_url(query) or query.lower().startswith(
        ("youtu.be/", "youtube.com/", "music.youtube.com/", "m.youtube.com/")
    )


def find(query, config):
    direct = is_link(query)
    if direct:
        identifier = video_id(query)
        cached = cached_track(identifier)
        if cached is not None:
            return cached
        query = Track(identifier, "").watch_url

    finished = Event()
    result = None

    def receive(tracks, error):
        nonlocal result
        result = tracks, error
        finished.set()

    searcher = Searcher(config)
    print("Resolving YouTube video…" if direct else "Searching YouTube…", file=sys.stderr)
    searcher.search_async(query, receive)
    try:
        finished.wait()
    except KeyboardInterrupt:
        searcher.cancel()
        raise
    tracks, error = result
    if error or not tracks:
        message = error or "No YouTube results."
        if "press L" in message:
            message = message.split(" - press L")[0] + ". Configure sign-in in ytamp and retry."
        raise RuntimeError(message)
    return tracks[0] if direct else choose(tracks)


def choose(tracks):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("The song picker needs a terminal. Pass a YouTube URL for unattended use.")
    return pick(tracks)


def save(title, identifier, chart, lyrics=False):
    directory = Path.home() / "Music" / "chords"
    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[/\\:*?"<>|\x00-\x1f\x7f]', "_", title).strip(" .")
    suffix = " - lyrics and chords" if lyrics else ""
    safe = safe.encode("utf-8")[:255 - len(suffix) - len(".txt")].decode("utf-8", errors="ignore")
    path = directory / f"{safe or identifier}{suffix}.txt"
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as temp:
        temporary = Path(temp.name)
        try:
            temp.write(chart)
            temp.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def make_chart(track, wav, easy):
    segments, key, tempo = analyse(wav)
    segments = clean(segments)
    capo, simplified = easy_chart(segments)
    tempo_label = f"{tempo:.0f} BPM" if tempo > 0 else "Unknown"
    capo_label = f"fret {capo}" if capo else "none"
    if not easy and capo:
        capo_label += " (for --easy)"
    title = "".join(char if char.isprintable() else " " for char in track.title)
    header = f"{title}\nKey: {key}   Tempo: {tempo_label}\nSuggested capo: {capo_label}"
    return header, simplified if easy else segments


def main():
    parser = argparse.ArgumentParser(
        prog="ytchords", description="Recognise guitar chords from YouTube audio locally."
    )
    parser.add_argument("song", nargs="?", help="YouTube video URL or search words")
    parser.add_argument("--from-ytamp", action="store_true", help="pick from ytamp's saved queue")
    parser.add_argument("--easy", action="store_true", help="show beginner shapes and guitar fingerings")
    parser.add_argument("--play", action="store_true", help="follow the chart during mpv playback")
    parser.add_argument("--save", action="store_true", help="save the chart in ~/Music/chords")
    layout = parser.add_mutually_exclusive_group()
    layout.add_argument("--lyrics", dest="lyrics", action="store_true", default=None,
                        help="save a lyrics-and-chords sheet with local word timing (default for URLs)")
    layout.add_argument("--chords-only", dest="lyrics", action="store_false",
                        help="show the chord timeline without transcribing vocals")
    parser.add_argument("--launcher", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.song and args.from_ytamp:
        parser.error("Choose a song or --from-ytamp.")
    try:
        song = args.song
        if not args.from_ytamp and not song:
            if not sys.stdin.isatty():
                parser.error("Pass a song or --from-ytamp.")
            song = input("YouTube URL or search words: ").strip()
            if not song:
                return 0
        config = Config.load()
        if args.from_ytamp:
            queue = Playlist()
            if not queue.load() or not queue.tracks:
                raise RuntimeError("ytamp has no saved songs in its queue.")
            track = choose(queue.tracks)
        else:
            track = find(song, config)
        if track is None:
            return 0
        wav = download(track, config)
        header, segments = make_chart(track, wav, args.easy)
        with_lyrics = args.lyrics if args.lyrics is not None else bool(song and is_link(song))
        if with_lyrics:
            chart = render_lyrics(header, segments, transcribe(wav), args.easy)
        else:
            chart = render(header, segments, args.easy)
        if args.save or with_lyrics:
            path = save(track.title, track.id, chart, lyrics=with_lyrics)
            print(f"Saved {path}", file=sys.stderr)
        if args.play:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError("--play needs an interactive terminal.")
            play(wav, header, segments, args.easy)
        if not with_lyrics:
            print(chart, end="")
        return 0
    except (RuntimeError, ValueError, OSError, curses.error) as error:
        print(f"ytchords: {error}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        return 130
    finally:
        if args.launcher and sys.stdin.isatty():
            try:
                input("\nPress Enter to close…")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
