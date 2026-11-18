# ytchords

Pick a YouTube recording and get a timed guitar chord chart. BTC-ISMIR19's pretrained large-vocabulary model recognises chords from the audio locally. PyTorch uses CUDA when available and otherwise runs on CPU. The key and tempo come from librosa and are estimates.

Pass a YouTube link to save a text sheet with chords above the lyrics. Whisper small transcribes the vocals locally and estimates word timestamps. The app places each chord above the word nearest its onset, and lists chord changes by timestamp during gaps in the vocals. Sung words and chord placement may need correction, especially with a dense mix.

## Install on Omarchy

From this directory, with Mamba available on PATH:

```sh
# Install any missing native tools through Omarchy
omarchy pkg add ffmpeg mpv deno git

mamba create -n ytchords -y python=3.11 pip
mamba run -n ytchords python -m pip install 'torch==2.11.0' \
  --index-url https://download.pytorch.org/whl/cu128
mamba run -n ytchords python -m pip install -r requirements.txt
./install.sh
```

Use the PyTorch index `https://download.pytorch.org/whl/cpu` for a CPU-only installation. The installer clones [ytamp](https://github.com/digonto10602/ytamp) into the sibling directory `../ytamp` if needed. Set `YTAMP_CHECKOUT` before running it to select another checkout. The installer adds `~/.local/bin/ytchords` and a user launcher entry, **ytchords**, which uses the Omarchy default terminal and its current theme. Keep the project and ytamp checkout in place or rerun the installer after moving them. Add `~/.local/bin` to PATH if your shell does not already include it.

## Use

```sh
ytchords "Monplaisir Everything is true"
ytchords 'https://youtu.be/UGnoFqjaeMg'
ytchords 'https://youtu.be/UGnoFqjaeMg' --easy
ytchords 'https://youtu.be/UGnoFqjaeMg' --chords-only --save
ytchords --from-ytamp --easy --play
```

Direct links save to `~/Music/chords/<title> - lyrics and chords.txt` by default. Add `--lyrics` when picking from search results or the ytamp queue to get the same format. The first lyrics run downloads about 461 MiB of Whisper weights and later runs reuse both the weights and the transcript. For chord timelines, use `--chords-only` and add `--save` to write the file. If you installed before lyrics support was added, rerun the requirements installation command above.

In the picker, use ↑ or ↓ and Enter. In playback, use Space to pause, ← or → to seek five seconds, and Q to close the playback view. The highlight follows the position reported by mpv.

ytchords reads ytamp's search settings, sign-in settings, and saved queue. If YouTube asks for sign-in, configure it in ytamp and retry. The first successful fetch caches the original audio as `~/.cache/ytchords/<video_id>.<ext>` and creates a mono analysis WAV alongside it. A cached video can be charted again without a YouTube request.

`--easy` chooses a capo from frets 0–11 based on how many chord changes map to open shapes. Ties favor the lower fret. Extended chords are simplified, and remaining shapes use an open chord with similar notes. For example, Bm7b5 can become Dm, and F can become Fmaj7. These are approximations. Six-character fingerings go from low E to high E, with `x` for mute and `0` for an open string. The standard chart uses chord names at sounding pitch and suggests a capo for the easy arrangement. `--save` writes the chart to `~/Music/chords/<title>.txt`.

## Worked example

The search above returned YouTube results for “Everything is true.” YouTube asked for sign-in when resolving the tested uploads on this machine, so the example chart was generated from the same recording supplied in the upstream BTC repository. The first eight entries of the saved easy chart are:

```text
Monplaisir - Everything is true
Key: Bb minor   Tempo: 123 BPM
Suggested capo: fret 6

0:00  No chord         0:02  C (x32010)       0:04  Fmaj7 (xx3210)   0:05  C (x32010)
0:06  Fmaj7 (xx3210)   0:08  C (x32010)       0:08  G (320003)       0:10  D (xx0232)
```

The displayed timestamps use whole seconds. Playback uses the unrounded analysis timestamps.

## Model source

The bundled [BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19/tree/2682317be668032e6e4b269ded36adaa2ad57df0) inference code and 170-class checkpoint come from revision `2682317be668032e6e4b269ded36adaa2ad57df0`. The adapter preserves BTC's CQT inputs and ten-second model windows. The vendored code uses package-relative imports, current NumPy types, and safe YAML parsing. The upstream MIT license is in `ytchords/_btc/LICENSE`.
