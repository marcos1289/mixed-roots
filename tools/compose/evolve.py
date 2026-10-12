#!/usr/bin/env python3
"""Generate a batch of song variants to compare, choosing their settings from what has been
learned so far.

    tools/stems/.venv/bin/python tools/compose/evolve.py [--n 4] [--lyrics tools/compose/songs/common-ground.json]

Each variant samples one option per setting (groove, tempo, key, chord loop, skank, horns,
percussion, bridge, melody syncopation) by Thompson sampling: every option keeps a win/loss
record from the band's A/B picks (learned.json, written by learn.py), and each batch draws
from those records, so winners come up more often while untried options still get tried.
Melodies are written fresh for every variant by melody.py and scored for catchiness.

Output: band-stems/Batch NN - X/ for every variant (full song + hook.wav, the first chorus)
and band-stems/_batches/batch-NN.json listing the variants and the pairs to compare.
publish_private.py puts them on the studio page's Compare tab.
"""
import json
import subprocess
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import melody  # noqa: E402
import styles  # noqa: E402

LEARNED = HERE / "learned.json"
BATCHES = REPO / "band-stems" / "_batches"
PY = str(REPO / "tools" / "stems" / ".venv" / "bin" / "python")

OPTIONS = {
    "groove": ["onedrop", "rockers", "stoopid", "marley_four", "steppers"],
    "tempo": [76, 82, 88, 94, 100],
    "key": ["D minor", "A minor", "E minor", "G major", "D major", "A major"],
    "progression": [0, 1, 2, 3, 4],
    "skank": ["single", "double"],
    "horns": ["call+answers", "answers", "stabs", "riff_everywhere"],
    "perc": ["none", "shekere", "afro"],
    "bridge": ["dub", "afro"],
    "melody_sync": [0.15, 0.3, 0.45],
    "keys": ["hammond+piano", "hammond", "band"],
}
# Starting beliefs, as (wins, losses) pseudo-counts, from feedback so far: the 80 BPM one-drop
# was "a little better, kinda slow"; Slightly Stoopid sits at 82-100 BPM (research notes).
PRIOR = {
    "tempo": {"76": [0, 1], "82": [1, 1], "88": [1, 0], "94": [1, 0], "100": [0.5, 0.5]},
    "groove": {"onedrop": [0, 1], "stoopid": [1, 0], "marley_four": [0.5, 0]},
    # "the keys need a more reggae feel" (batch 1 used the band's phone-recorded chord stabs)
    "keys": {"hammond+piano": [2, 0], "hammond": [1, 0], "band": [0, 2]},
}
SLOW_GROOVES = {"onedrop": 86, "steppers": 88}     # these grooves don't go above this tempo
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
PC = {n: i for i, n in enumerate(NAMES)} | {"Db": 1, "D#": 3, "Gb": 6, "G#": 8, "A#": 10}


def load_stats():
    stats = {p: {str(o): [1.0, 1.0] for o in opts} for p, opts in OPTIONS.items()}
    for p, d in PRIOR.items():
        for o, (w, l) in d.items():
            stats[p][o][0] += w
            stats[p][o][1] += l
    if LEARNED.exists():
        for p, d in json.loads(LEARNED.read_text()).get("stats", {}).items():
            for o, (w, l) in d.items():
                if p in stats and o in stats[p]:
                    stats[p][o][0] += w
                    stats[p][o][1] += l
    return stats


def sample(stats, rng):
    params = {}
    for p, opts in OPTIONS.items():
        draws = {str(o): rng.beta(*stats[p][str(o)]) for o in opts}
        params[p] = max(opts, key=lambda o: draws[str(o)])
    cap = SLOW_GROOVES.get(params["groove"])
    if cap and params["tempo"] > cap:
        params["tempo"] = max(t for t in OPTIONS["tempo"] if t <= cap)
    return params


def chord_name(tonic, numeral):
    off, q = styles.NUMERALS[numeral]
    return NAMES[(tonic + off) % 12] + ("m" if q == "m" else "")


def horn_tokens(riff, tonic, scale, bars):
    """Riff (2-bar steps, scale-degree index) -> unison line tokens spanning `bars` bars."""
    if not riff:
        return f"r/{4 * bars}"
    notes = styles.HORN_RIFFS[riff]
    base = 62 + (tonic - 2) % 12                         # tonic between D4 and C#5
    if base > 67:
        base -= 12
    out, t = [], 0
    for rep in range(bars // 2):
        for step, deg, length in notes:
            s = rep * 32 + step - 1
            if s > t:
                out.append(f"r/{(s - t) / 4:g}")
            octave, k = divmod(deg, len(scale))
            p = base + scale[k] + 12 * octave
            out.append(f"{NAMES[p % 12]}{p // 12 - 1}/{length / 4:g}")
            t = s + length
    if t < 16 * bars:
        out.append(f"r/{(16 * bars - t) / 4:g}")
    return " ".join(out)


HORN_PLAN = {   # section -> riff, per "horns" option
    "call+answers": {"Intro": "pent_call", "Chorus": "stab", "Bridge": "answer", "Outro": "pent_call"},
    "answers": {"Chorus": "stab", "Bridge": "answer", "Outro": "stab"},
    "stabs": {"Intro": "stab", "Chorus": "stab", "Outro": "stab"},
    "riff_everywhere": {"Intro": "pent_call", "Verse": "stab", "Chorus": "pent_call", "Bridge": "afro",
                        "Outro": "pent_call"},
}


def build_song(params, lyrics, rng, title):
    key_name, mode = params["key"].split()
    tonic = PC[key_name]
    prog = styles.PROGRESSIONS[mode][params["progression"]]
    chorus_prog = styles.PROGRESSIONS[mode][(params["progression"] + 2) % len(styles.PROGRESSIONS[mode])]
    scale_name = "dorian" if mode == "minor" and ("IV" in prog or "IV" in chorus_prog) else mode
    scale = melody.SCALES[scale_name]
    verse_chords = [chord_name(tonic, n) for n in prog] * 2
    chorus_chords = [chord_name(tonic, n) for n in chorus_prog] * 2

    def pairs(names):
        out = []
        for c in names:
            root = PC[c.rstrip("m")]
            out.append((root, "minor" if c.endswith("m") else "major"))
        return out

    lo, hi = 50, 67                                        # D3-G4: the guide voice's tenor range
    sync = params["melody_sync"]
    v1 = melody.write_section(lyrics["verse1"], pairs(verse_chords), "verse", tonic, scale_name, lo, hi, rng, sync=sync)
    v2 = melody.write_section(lyrics["verse2"], pairs(verse_chords), "verse", tonic, scale_name, lo, hi, rng, sync=sync)
    ch = melody.write_section(lyrics["chorus"], pairs(chorus_chords), "chorus", tonic, scale_name, lo, hi, rng, sync=sync)
    br_lines = ["Music is love, one love"] * 4
    br = melody.write_section(br_lines, [(tonic, "minor" if mode == "minor" else "major")] * 8, "chorus",
                              tonic, scale_name, lo, hi, rng, sync=sync)
    g = params["groove"]
    plan = HORN_PLAN[params["horns"]]
    common = {"skank": True, "double_chop": params["skank"] == "double", "bubble": True}
    perc = None if params["perc"] == "none" else ("shekere" if params["perc"] == "shekere" else "afro")

    def horns(section, bars):
        return horn_tokens(plan.get(section), tonic, scale, bars)

    sections = [
        {"name": "Intro", "chords": verse_chords[:4], "drums": g, "fill": True, "skank": True,
         "horns": horns("Intro", 4)},
        {"name": "Verse 1", "chords": verse_chords, "drums": g, **common, "perc": perc,
         "vocals": v1[0], "syllables": v1[1], "lyrics": lyrics["verse1"], "horns": horns("Verse", 8)},
        {"name": "Chorus", "chords": chorus_chords, "drums": g, **common, "double_chop": True,
         "perc": perc or "shekere", "fill": True, "vocals": ch[0], "syllables": ch[1],
         "lyrics": lyrics["chorus"], "horns": horns("Chorus", 8)},
        {"name": "Verse 2", "chords": verse_chords, "drums": g, **common, "perc": perc,
         "vocals": v2[0], "syllables": v2[1], "lyrics": lyrics["verse2"], "horns": horns("Verse", 8)},
        {"name": "Chorus", "chords": "@Chorus", "drums": g, **common, "double_chop": True,
         "perc": perc or "shekere", "fill": True, "vocals": "@Chorus", "syllables": "@Chorus",
         "lyrics": "@Chorus", "horns": "@Chorus"},
    ]
    if params["bridge"] == "dub":
        sections.append({"name": "Bridge", "chords": verse_chords[:4] * 2, "drums": g, "bass": "space",
                         "fill": True, "vocals": br[0], "syllables": br[1], "lyrics": br_lines,
                         "horns": horns("Bridge", 8),
                         "throws": [[2, "drums", 0.8], [10, "drums", 0.8], [18, "drums", 0.8]]})
    else:
        sections.append({"name": "Bridge", "chords": [chord_name(tonic, "i" if mode == "minor" else "I")] * 8,
                         "drums": "afro_rockers", "skank": True, "tenor_guitar": True, "perc": "afro",
                         "fill": True, "vocals": br[0], "syllables": br[1], "lyrics": br_lines,
                         "horns": horns("Bridge", 8)})
    sections += [
        {"name": "Chorus", "chords": "@Chorus", "drums": g, **common, "double_chop": True,
         "perc": perc or "shekere", "vocals": "@Chorus", "syllables": "@Chorus", "lyrics": "@Chorus",
         "horns": "@Chorus"},
        {"name": "Outro", "chords": verse_chords[:4], "drums": g, "end": True, "skank": True,
         "horns": horns("Outro", 4)},
    ]
    for s in sections:
        if s.get("perc") is None:
            s.pop("perc", None)
    base = json.loads((HERE / "songs" / "common-ground.json").read_text())
    return {
        "title": title, "subtitle": f"{g} groove, {params['tempo']} BPM, {params['key']}", "key": params["key"],
        "bpm": params["tempo"], "groove": base["groove"], "kit": base["kit"], "voice": "Daniel",
        "vocal_transpose": 0, "horns_transpose": 0, "sections": sections, "keys": params["keys"],
        "catchiness": {"verse": round(v1[2], 3), "chorus": round(ch[2], 3), "bridge": round(br[2], 3)},
    }


def lyrics_from(song_file):
    song = json.loads(Path(song_file).read_text())
    by = {}
    for s in song["sections"]:
        by.setdefault(s["name"], s)                       # first occurrence holds the real lyrics
    return {"verse1": by["Verse 1"]["lyrics"], "verse2": by["Verse 2"]["lyrics"], "chorus": by["Chorus"]["lyrics"]}


def hook_clip(folder, seconds=16.0):
    info = json.loads((folder / "info.json").read_text())
    start = next(s["start_s"] for s in info["sections"] if s["name"] == "Chorus")
    y, sr = sf.read(folder / "mix.wav")
    a = max(0, int((start - 0.3) * sr))
    clip = y[a:a + int(seconds * sr)].copy()
    fade = int(0.4 * sr)
    clip[-fade:] *= np.linspace(1, 0, fade)[:, None]
    sf.write(folder / "hook.wav", clip, sr, subtype="PCM_24")


def main():
    args = sys.argv[1:]
    n = int(args[args.index("--n") + 1]) if "--n" in args else 4
    lyr = args[args.index("--lyrics") + 1] if "--lyrics" in args else HERE / "songs" / "common-ground.json"
    BATCHES.mkdir(parents=True, exist_ok=True)
    num = len(list(BATCHES.glob("batch-*.json"))) + 1
    batch_id = f"batch-{num:02d}"
    rng = np.random.default_rng(int(time.time()))
    stats = load_stats()
    lyrics = lyrics_from(lyr)
    variants = []
    out_dir = HERE / "songs" / "batches" / batch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        letter = "ABCDEFGH"[i]
        params = sample(stats, rng)
        title = f"Batch {num:02d} - {letter}"
        song = build_song(params, lyrics, rng, "Common Ground")
        path = out_dir / f"{letter}.json"
        path.write_text(json.dumps(song, indent=2) + "\n")
        print(f"{title}: {params}  catchiness {song['catchiness']}", flush=True)
        subprocess.run([PY, str(HERE / "compose.py"), str(path), "--out", title], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        hook_clip(REPO / "band-stems" / title)
        variants.append({"id": letter, "folder": title, "params": params, "catchiness": song["catchiness"]})
    batch = {"id": batch_id, "created": time.strftime("%Y-%m-%d %H:%M"), "variants": variants,
             "pairs": [list(p) for p in combinations([v["id"] for v in variants], 2)]}
    (BATCHES / f"{batch_id}.json").write_text(json.dumps(batch, indent=2) + "\n")
    (out_dir / "batch.json").write_text(json.dumps(batch, indent=2) + "\n")   # committed copy for learn.py
    print(f"Wrote {batch_id} with {n} variants and {len(batch['pairs'])} pairs to compare")


if __name__ == "__main__":
    main()
