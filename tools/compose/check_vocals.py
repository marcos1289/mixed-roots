#!/usr/bin/env python3
"""Score how understandable the sung lyrics are: sing each line alone, transcribe it with
Whisper, and count the lyric words recognised in order.

    tools/stems/.venv/bin/python tools/compose/check_vocals.py [song.json] [--voice Daniel] [--rate 150]
"""
import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose  # noqa: E402
import sing  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def words(text):
    return re.sub(r"[^a-z' ]", " ", re.sub(r"\(.*?\)", "", text.lower())).split()


def lines_of(song):
    """[(expected words, syllables, [(t_s, d_s, midi)])] per sung phrase (split at breaths)."""
    beat = 60 / song["bpm"]
    out, seen = [], set()
    for sec in compose.resolve(song["sections"]):
        if not sec.get("vocals") or sec["name"] in seen:
            continue
        seen.add(sec["name"])
        notes = [(t * beat, d * 0.95 * beat, n + song.get("vocal_transpose", 0))
                 for t, n, d in compose.parse_line(sec["vocals"])]
        tokens = sec["syllables"].split()
        phrase, syl = [], []
        for k, (note, tok) in enumerate(zip(notes, tokens)):
            phrase.append(note)
            syl.append(tok)
            nxt = notes[k + 1] if k + 1 < len(notes) else None
            breath = nxt is None or nxt[0] - (note[0] + note[1] / 0.95) >= 0.9 * beat
            if breath and not tok.endswith("-"):
                text = " ".join(w for w, _ in sing.words_from_syllables(" ".join(syl)))
                out.append((text, " ".join(syl), phrase))
                phrase, syl = [], []
    return out


def main():
    args = sys.argv[1:]
    song_path = Path(next((a for a in args if a.endswith(".json")), REPO / "tools/compose/songs/common-ground.json"))
    voice = args[args.index("--voice") + 1] if "--voice" in args else None
    if "--rate" in args:
        sing.RATE = int(args[args.index("--rate") + 1])
    song = json.loads(song_path.read_text())
    voice = voice or song.get("voice", "Daniel")
    import whisper
    model = whisper.load_model("base.en")
    cache, total, hit = {}, 0, 0
    for line, syl, notes in lines_of(song):
        t0 = notes[0][0]
        rel = [(t - t0, d, m) for t, d, m in notes]
        L = int((rel[-1][0] + rel[-1][1] + 1.5) * sing.SR)
        y = np.zeros(L)
        for s, a in sing.sing_line(syl, rel, voice, cache):
            a0 = int(s * sing.SR)
            y[a0:a0 + len(a)] += a[:L - a0]
        path = "/tmp/_line.wav"
        sf.write(path, y / (np.abs(y).max() + 1e-9) * 0.8, sing.SR)
        heard = model.transcribe(path, language="en", fp16=False)["text"].strip()
        T, H = words(line), words(heard)
        m = sum(b.size for b in difflib.SequenceMatcher(None, T, H).get_matching_blocks())
        total += len(T)
        hit += m
        print(f"{m:2}/{len(T):2}  {line}\n        heard: {heard}")
    print(f"\n{voice} @ rate {sing.RATE}: {hit}/{total} lyric words recognised ({100 * hit / total:.0f}%)")


if __name__ == "__main__":
    main()
