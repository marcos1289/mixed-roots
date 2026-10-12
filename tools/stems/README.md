# Stem studio

Splits the band's recordings into parts and turns them into material for Reason. Everything runs on Mark's Intel Mac, with no GPU and no paid services.

## Use

1. Put recordings in `band-audio/`. WAV, MP3, FLAC, M4A, AIFF, or even a phone video all work.
2. Run `tools/stems/run.sh`.
3. Open `band-stems/index.html`.

Each song gets its own folder in `band-stems/`:

| Output | What it is |
|---|---|
| `index.html` | A mixer: solo or mute each part to judge how clean the split is, and click a waveform to jump. |
| `stems/*.wav` | vocals, drums, bass, guitar, keys, horns, other. All the same length as the song, so they line up when dropped into Reason at bar 1. |
| `midi/*.mid` | One file per part plus `all parts`, at the song's detected tempo. Set Reason to that tempo (it's in the filename), then drag a file onto a track. **File → Import MIDI File** brings in every part at once. |
| `kit/` | The cleanest isolated kick, snare and hat hits, for Kong or Redrum. |
| `phrases/` | Horn and vocal phrases cut at the gaps, for a sampler. |
| `groove.json` | How the drummer sits against the grid: timing push/pull (ms) and accent strength for each 16th position. Also feeds `tools/midi/reggae_demo.py --groove`. |

Options:
- `--fast`: Demucs only, about 3x quicker, no horns stem.
- `--max-quality`: BS-Roformer for vocals. Noticeably cleaner, but hours per song on this Mac.
- `--only NAME`: process only files whose name contains NAME.
- `--redo`: re-separate songs already done.
- `--reanalyze`: keep the stems and redo only tempo, key, drums, MIDI, kit and groove. Takes seconds.

Speed on this Mac is about 11x real time, so a 4-minute song takes about 45 minutes. Run a batch overnight.

## How it works

Separation runs in three stages, so each model does what it's best at:
1. **Kim Vocal 2** takes the vocals off the full mix.
2. **Demucs v4 6-stem** splits what's left into drums, bass, guitar, piano and other. Its own leftover "vocals" output is bleed and gets folded into "other".
3. **UVR wind-instrument model** pulls brass and woodwind out of "other", giving the horns their own stem. Most separators leave horns buried in "other".

Stems are written without per-stem normalization, so their levels stay true to the mix. The mixer page shows how much of the mix the stems account for (about 99% is typical).

Drums are detected with a separate onset detector per frequency band: kick, snare and hat. A kick and hat that land together can look like a snare, so those are dropped when they are much weaker than the song's real snares. `test_drums.py` checks the detector against a synthetic one-drop groove with known hits. Last run: kicks 12/12, snares 8/8, hats 63/64, no false hits. Hand percussion (congas) lands in the drum stem too, and its hits get labelled kick or snare by pitch.

MIDI comes from Spotify's **basic-pitch** (ONNX backend). Stems more than 21 dB below the mix are skipped as mostly bleed.

## Setup notes (Intel Mac)

PyTorch stopped shipping Intel-Mac builds at 2.2.2, so the venv pins:
- `torch==2.2.2` and `numpy<2`
- `numba==0.61.2` and `llvmlite==0.44.0`
- `audio-separator[cpu]==0.24.1`. Newer versions need NumPy 2.
- `basic-pitch==0.4.0`, installed with `--no-deps`, plus `mir-eval`, `pretty-midi`, `resampy<0.4.3`, `scikit-learn` and `setuptools<70`. Without TensorFlow it uses its ONNX model.

Models download to `tools/stems/models/` on first use. They are gitignored, as are the venv, `band-audio/` and `band-stems/`.
