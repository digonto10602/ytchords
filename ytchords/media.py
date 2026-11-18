"""Read ytamp's queue and keep a separate audio cache for ytchords."""
import fcntl
import json
from dataclasses import asdict
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from ytamp.playlist import Track
from ytamp.search import Searcher
from ytamp.util import clean_env

CACHE = Path.home() / ".cache" / "ytchords"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
         "youtu.be", "www.youtu.be"}


def video_id(url):
    parsed = urlsplit("https://" + url if "://" not in url else url)
    if parsed.hostname not in HOSTS or parsed.scheme not in ("http", "https"):
        raise ValueError("Enter a YouTube video URL.")
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname in ("youtu.be", "www.youtu.be"):
        candidate = parts[0]
    elif parts[0] in ("shorts", "live", "embed") and len(parts) == 2:
        candidate = parts[1]
    else:
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    if not VIDEO_ID.fullmatch(candidate):
        raise ValueError("The URL must identify a single YouTube video.")
    return candidate


def cached_track(identifier):
    metadata = CACHE / f"{identifier}.json"
    try:
        track = Track(**json.loads(metadata.read_text()))
    except (OSError, ValueError, TypeError):
        return None
    return track if track.id == identifier else None


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, env=clean_env())
    if result.returncode:
        message = result.stderr.strip()
        if command[0] == "yt-dlp":
            hint = Searcher._explain(message)
            if hint and "press L" in hint:
                message = hint.split(" - press L")[0] + ". Configure sign-in in ytamp and retry."
        raise RuntimeError(message or f"{command[0]} exited with status {result.returncode}.")
    return result.stdout


def download(track, config):
    if not VIDEO_ID.fullmatch(track.id):
        raise ValueError("The selected entry has no valid YouTube video ID.")
    if track.live:
        raise ValueError("Choose a finished recording.")
    CACHE.mkdir(parents=True, exist_ok=True)
    wav = CACHE / f"{track.id}.mono.wav"
    with (CACHE / f"{track.id}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if wav.is_file() and wav.stat().st_size > 44:
            return wav
        source = next((p for p in CACHE.glob(f"{track.id}.*")
                       if p.suffix not in {".lock", ".json"} and p != wav and p.is_file()), None)
        with TemporaryDirectory(dir=CACHE) as directory:
            staging = Path(directory)
            if source is None:
                run(["yt-dlp", "--ignore-config", "--no-playlist", "--no-progress",
                     "--socket-timeout", "20", "-f", "bestaudio",
                     "-o", str(staging / f"{track.id}.%(ext)s"),
                     *config.ytdlp_auth_args(), "--", track.watch_url])
                files = list(staging.glob(f"{track.id}.*"))
                if len(files) != 1:
                    raise RuntimeError("yt-dlp did not produce one audio file.")
                source = files[0].replace(CACHE / files[0].name)
            metadata = staging / "track.json"
            metadata.write_text(json.dumps(asdict(track)), encoding="utf-8")
            metadata.replace(CACHE / f"{track.id}.json")
            converted = staging / "audio.wav"
            run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-vn",
                 "-map_metadata", "-1", "-ac", "1", "-ar", "22050", str(converted)])
            converted.replace(wav)
    return wav
