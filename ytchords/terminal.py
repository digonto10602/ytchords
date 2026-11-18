"""Theme-inheriting curses tools for selection and playback."""
from bisect import bisect_right
import curses
import json
from pathlib import Path
from select import select
import socket
import subprocess
from tempfile import TemporaryDirectory
import time

from ytamp.util import clean_env, runtime_dir

from .chart import chord_text, timestamp


def draw(screen, row, text, style=0):
    height, width = screen.getmaxyx()
    if row < height and width > 1:
        screen.addnstr(row, 0, "".join(char if char.isprintable() else " " for char in text),
                       width - 1, style)


def pick(tracks):
    def interact(screen):
        selected = 0
        first = 0
        while True:
            screen.erase()
            draw(screen, 0, "Choose a song   ↑/↓ move   Enter select   Esc cancel", curses.A_BOLD)
            visible = max(1, screen.getmaxyx()[0] - 1)
            first = min(max(first, selected - visible + 1), selected)
            for index, track in enumerate(tracks[first:first + visible], first):
                duration = timestamp(track.duration) if track.duration is not None else "–:––"
                line = f"{duration:>6}  {track.uploader or 'Unknown channel'}  ·  {track.title}"
                draw(screen, index - first + 1, line, curses.A_REVERSE if index == selected else 0)
            screen.refresh()
            key = screen.getch()
            if key in (10, 13, curses.KEY_ENTER):
                return tracks[selected]
            if key in (27, ord("q")):
                return None
            if key == curses.KEY_UP:
                selected = max(0, selected - 1)
            if key == curses.KEY_DOWN:
                selected = min(len(tracks) - 1, selected + 1)

    return curses.wrapper(interact)


def play(wav, header, segments, easy):
    def interact(screen):
        screen.timeout(30)
        starts = [start for start, _, _ in segments]
        with TemporaryDirectory(dir=runtime_dir(), prefix="ytchords-") as directory:
            endpoint = str(Path(directory) / "mpv")
            with subprocess.Popen(
                ["mpv", "--no-config", "--no-terminal", "--no-video", "--pause",
                 f"--input-ipc-server={endpoint}", "--", str(wav)],
                env=clean_env(),
            ) as process, socket.socket(socket.AF_UNIX) as ipc:
                try:
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            ipc.connect(endpoint)
                            break
                        except (FileNotFoundError, ConnectionRefusedError):
                            if process.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError("mpv IPC did not start.")
                            time.sleep(0.03)

                    def send(*command):
                        ipc.sendall((json.dumps({"command": command}) + "\n").encode())

                    send("observe_property", 1, "time-pos")
                    send("set_property", "pause", False)
                    position = None
                    buffer = b""
                    while process.poll() is None:
                        if select([ipc], [], [], 0)[0]:
                            received = ipc.recv(65536)
                            if not received:
                                break
                            *lines, buffer = (buffer + received).split(b"\n")
                            for line in lines:
                                event = json.loads(line)
                                if event.get("event") == "end-file" and event.get("reason") == "error":
                                    raise RuntimeError(event.get("file_error", "mpv could not play the audio."))
                                if event.get("name") == "time-pos":
                                    position = event.get("data")

                        current = bisect_right(starts, position) - 1 if position is not None else -1
                        screen.erase()
                        for row, line in enumerate(header.splitlines()):
                            draw(screen, row, line, curses.A_BOLD)
                        time_label = timestamp(position) if position is not None else "–:––"
                        draw(screen, 3, f"{time_label}   Space pause   ←/→ seek   Q quit")
                        count = max(1, screen.getmaxyx()[0] - 4)
                        first = max(0, min(current - count // 2, len(segments) - count))
                        for index, (start, end, chord) in enumerate(segments[first:first + count], first):
                            active = index == current and position < end
                            draw(screen, 4 + index - first, f"{timestamp(start)}  {chord_text(chord, easy)}",
                                 curses.A_REVERSE if active else 0)
                        screen.refresh()
                        key = screen.getch()
                        if key in (ord("q"), 27):
                            return
                        if key == ord(" "):
                            send("cycle", "pause")
                        if key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                            send("seek", -5 if key == curses.KEY_LEFT else 5, "relative")
                    if process.wait(timeout=2):
                        raise RuntimeError("mpv exited with an error.")
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()

    curses.wrapper(interact)
