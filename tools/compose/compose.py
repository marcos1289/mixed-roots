#!/usr/bin/env python3
"""Turn a song file (tools/compose/songs/*.json) into MIDI for Reason and a rendered demo.

    tools/stems/.venv/bin/python tools/compose/compose.py tools/compose/songs/common-ground.json

The song file holds the composition: chords per bar, horn and vocal melodies written as
"NOTE/beats" tokens ("r" = rest, "|" = bar line, "@Section" reuses an earlier section),
lyrics, and which grooves play where. This script supplies the playing:

  drums    one-drop or steppers patterns, played with the band's own drum hits
  bass     a reggae line built from each bar's chord, played with the band's real bass notes
  guitar   the skank on 2 and 4, played with the band's real guitar chord stabs
  keys     the organ bubble on the offbeat 8ths, played with the band's real keys stabs
  horns    the written line plus a harmony a third below, played with their real horn notes
  vocals   the lyrics sung on the melody (sing.py: a Mac voice re-pitched with WORLD)
  other    shaker or afrobeat congas (synthesized)

Band sounds come from every recording tools/stems has processed (samplers.py); a part
falls back to a synthesized sound if no usable notes were found. --synth forces synth
sounds everywhere, --no-vocals skips the singing (faster).

Timing and accents come from a groove captured by tools/stems from a real recording, so
the parts sit the way the band plays. Output goes to band-stems/<song>/ in the same layout
the stem studio uses, so tools/stems/publish_private.py puts it on the private studio page.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf
from scipy.signal import oaconvolve, butter, sosfilt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "stems"))
import studio  # noqa: E402  (waveform images, stem levels, library page)
sys.path.insert(0, str(Path(__file__).resolve().parent))

SR = 44100
rng = np.random.default_rng(11)
NOTE_NAMES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
              "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
PARTS = ["vocals", "drums", "bass", "guitar", "keys", "horns", "other"]
GM_PROGRAM = {"bass": 33, "guitar": 28, "keys": 16, "horns": 61, "vocals": 54}
DRUM_NOTE = {"kick": 36, "snare": 37, "hat": 42, "open": 46, "tom_hi": 48, "tom_lo": 45, "crash": 49,
             "shaker": 70, "conga_hi": 63, "conga_lo": 64}
POSITIONS = ["on the beat", "1st 16th (e)", "8th offbeat (&)", "3rd 16th (a)"]
FEEL = {"drums": None, "bass": "kick", "guitar": "snare", "keys": "hat", "horns": "snare", "vocals": None,
        "other": "hat"}


def midi_of(name):
    m = re.fullmatch(r"([A-G][#b]?)(-?\d)", name)
    return 12 * (int(m.group(2)) + 1) + NOTE_NAMES[m.group(1)]


def chord_tones(symbol):
    m = re.fullmatch(r"([A-G][#b]?)(m?)(7?)", symbol)
    root = NOTE_NAMES[m.group(1)]
    third = 3 if m.group(2) else 4
    tones = [root, (root + third) % 12, (root + 7) % 12]
    if m.group(3):
        tones.append((root + 10) % 12)
    return root, tones


def parse_line(text):
    """'A4/0.5 r/1 | ...' -> [(beat offset, midi note or None, beats)]"""
    out, t = [], 0.0
    for tok in text.replace("|", " ").split():
        name, dur = tok.split("/")
        dur = float(dur)
        if name != "r":
            out.append((t, midi_of(name), dur))
        t += dur
    return out


def resolve(sections):
    """Expand '@Name' references to the first earlier section with that name."""
    seen = {}
    for s in sections:
        for k, v in list(s.items()):
            if isinstance(v, str) and v.startswith("@"):
                s[k] = seen[v[1:]][k]
        seen.setdefault(s["name"], s)
    return sections


# ---------------------------------------------------------------- arrangement -> notes

def arrange(song):
    """Return {part: [(beat, pitch, beats, velocity)]} plus section start beats."""
    notes = {p: [] for p in PARTS}
    scale = {NOTE_NAMES[n] for n in song["harmony_scale"]}
    starts, beat = [], 0.0
    chord_map, vocal_phrases = [], []
    horns_tr, vocal_tr = song.get("horns_transpose", 0), song.get("vocal_transpose", 0)
    for sec in resolve(song["sections"]):
        starts.append((sec["name"], beat))
        bars = sec["chords"]
        for i, ch in enumerate(bars):
            b0 = beat + 4 * i
            root, tones = chord_tones(ch)
            chord_map.append((b0, root, "minor" if (tones[1] - root) % 12 == 3 else "major"))
            last = i == len(bars) - 1
            end_bar = sec.get("end") and last
            fill_bar = sec.get("fill") and last
            drums(notes["drums"], b0, sec.get("drums"), fill_bar, end_bar, i)
            if i + 1 >= sec.get("bass_from_bar", 1):
                bass(notes["bass"], b0, root, tones, i, end_bar)
            if sec.get("skank"):
                skank(notes["guitar"], b0, tones, end_bar)
            if sec.get("bubble") and not end_bar:
                bubble(notes["keys"], b0, root, tones)
            if sec.get("perc") and not end_bar:
                perc(notes["other"], b0, sec["perc"])
        for t, n, d in parse_line(sec.get("horns", "")):
            v = 100 if d >= 1 else 92
            notes["horns"].append((beat + t, n + horns_tr, d * 0.92, v))
            notes["horns"].append((beat + t, harmony(n, scale) + horns_tr, d * 0.92, v - 12))
        sung = parse_line(sec.get("vocals", ""))
        for t, n, d in sung:
            notes["vocals"].append((beat + t, n + vocal_tr, d * 0.95, 96))
        if sung:
            vocal_phrases.append((sec["syllables"], len(sung)))
        beat += 4 * len(bars)
    return notes, starts, beat, chord_map, vocal_phrases


def harmony(n, scale):
    """A third below that stays in the scale (minor third preferred)."""
    for step in (3, 4):
        if (n - step) % 12 in scale:
            return n - step
    return n - 3


def drums(out, b0, style, fill, end, bar):
    if not style:
        return
    add = lambda t, k, v: out.append((b0 + t, DRUM_NOTE[k], 0.1, v))
    if end:
        add(0, "kick", 115); add(0, "crash", 110); add(0, "snare", 100)
        return
    if bar == 0:
        add(0, "crash", 92)
    if style == "onedrop":
        add(2, "kick", 112); add(2, "snare", 104)
        for k in range(8):
            t = k * 0.5
            if fill and t >= 3:
                break
            open_hat = k == 7 and bar % 4 == 3
            add(t, "open" if open_hat else "hat", 96 if k % 2 else 70)
    elif style == "steppers":
        for q in range(4):
            add(q, "kick", 108 if q in (0, 2) else 96)
        add(2, "snare", 104)
        for k in range(16):
            t = k * 0.25
            if fill and t >= 3:
                break
            add(t, "hat", (90, 50, 78, 50)[k % 4])
    if fill:
        for t, k in ((3, "snare"), (3.25, "snare"), (3.5, "tom_hi"), (3.75, "tom_lo")):
            add(t, k, 96)


BASS_RHYTHMS = [
    [(0.0, 0, 0.9), (1.0, 0, 0.4), (1.5, 7, 0.4), (2.5, 0, 0.4), (3.0, 3, 0.45), (3.5, 7, 0.4)],
    [(0.0, 0, 1.4), (1.5, 7, 0.4), (2.0, 12, 0.4), (2.5, 10, 0.4), (3.0, 7, 0.9)],
]


def bass(out, b0, root, tones, bar, end):
    base = 36 + (root - 0) % 12          # C2..B2
    if base > 43:                         # keep the line between E1 and G2
        base -= 12
    if end:
        out.append((b0, base, 3.5, 108))
        return
    third = (tones[1] - root) % 12
    for t, iv, d in BASS_RHYTHMS[bar % 2]:
        if iv == 3:
            iv = third
        if iv == 10 and len(tones) < 4 and third == 4:
            iv = 7
        out.append((b0 + t, base + iv, d, 100 if t in (0.0, 2.0) else 88))


def voicing(tones, low=62):
    """Close triad voicing starting at or above `low` (D4)."""
    vs = []
    for pc in tones[:3]:
        n = low + (pc - low) % 12
        vs.append(n)
    return sorted(vs)


def skank(out, b0, tones, end):
    hits = [0] if end else [1, 3]
    for q in hits:
        for n in voicing(tones):
            out.append((b0 + q, n, 1.5 if end else 0.18, 84))


def bubble(out, b0, root, tones):
    v = voicing(tones, 55)
    for k in range(4):
        t = k + 0.5
        chord = v if k % 2 == 0 else [x + 12 for x in v[1:]]
        for n in chord:
            out.append((b0 + t, n, 0.22, 64 if k % 2 else 74))


def perc(out, b0, style):
    if style == "shaker":
        for k in range(16):
            out.append((b0 + k * 0.25, DRUM_NOTE["shaker"], 0.1, (70, 40, 60, 40)[k % 4]))
    elif style == "afro":
        for t, k, v in ((0.75, "conga_lo", 90), (1.5, "conga_hi", 84), (2.0, "conga_hi", 70),
                        (2.75, "conga_lo", 92), (3.5, "conga_hi", 88), (3.75, "conga_hi", 64)):
            out.append((b0 + t, DRUM_NOTE[k], 0.2, v))
        for k in range(16):
            out.append((b0 + k * 0.25, DRUM_NOTE["shaker"], 0.1, (64, 36, 54, 36)[k % 4]))


# ---------------------------------------------------------------- groove

def apply_groove(notes, groove, bpm):
    """Offset each note by the captured push/pull for its 16th position, and humanize a little."""
    table = groove.get("positions", {})
    beat_ms = 60000 / bpm
    out = {}
    kind_of = {36: "kick", 37: "snare", 38: "snare", 42: "hat", 46: "hat", 70: "hat"}
    for part, ns in notes.items():
        moved = []
        shared = {}   # notes struck together (chords, horn harmony) move together
        for t, n, d, v in ns:
            kind = kind_of.get(n, "snare") if part in ("drums", "other") else FEEL[part]
            off_ms = 0.0
            pos = POSITIONS[round(t * 4) % 4]
            cell = table.get(kind or "", {}).get(pos) if kind else None
            if cell:
                off_ms = max(-25.0, min(25.0, cell["median_offset_ms"]))
            if part in ("drums", "other"):
                off_ms += rng.normal(0, 4)
            else:
                off_ms += shared.setdefault(t, rng.normal(0, 6))
            v = int(np.clip(v + rng.normal(0, 5), 20, 127))
            moved.append((max(0.0, t + off_ms / beat_ms), n, d, v))
        out[part] = moved
    return out


# ---------------------------------------------------------------- synthesis

def hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, d, s, r, sr=SR):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    body = max(n - a - d, 0)
    e = np.concatenate([np.linspace(0, 1, max(a, 1)), np.linspace(1, s, max(d, 1)), np.full(body, s)])[:n]
    if len(e) < n:
        e = np.pad(e, (0, n - len(e)), constant_values=s)
    tail = s * np.linspace(1, 0, max(r, 1))
    return np.concatenate([e, tail])


def synth_bass(n, dur, vel):
    f = hz(n)
    t = np.arange(int((dur + 0.08) * SR)) / SR
    e = env_adsr(int(dur * SR), 0.006, 0.25, 0.55, 0.08)[:len(t)]
    e = np.pad(e, (0, max(0, len(t) - len(e))))
    y = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    y = np.tanh(1.6 * y) * e
    return y * (vel / 127) * 0.55


def karplus(n, dur, vel, damp=0.996, bright=0.5):
    f = hz(n)
    period = int(SR / f)
    length = int((dur + 0.05) * SR)
    buf = rng.uniform(-1, 1, period) * bright + (1 - bright) * np.sin(np.linspace(0, 2 * np.pi, period))
    out = np.empty(length)
    for i in range(length):                # short notes, so the loop is cheap
        out[i] = buf[i % period]
        buf[i % period] = damp * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    mute = np.ones(length)
    cut = int(dur * SR)
    if cut < length:
        mute[cut:] = np.linspace(1, 0, length - cut)
    return out * mute * (vel / 127) * 0.5


def synth_skank(chord, dur, vel):
    parts = []
    for k, n in enumerate(chord):
        y = karplus(n, dur, vel, damp=0.992, bright=0.75)
        parts.append(np.pad(y, (int(k * 0.006 * SR), 0)))   # small down-strum
    L = max(len(p) for p in parts)
    y = sum(np.pad(p, (0, L - len(p))) for p in parts)
    sos = butter(2, [250, 5000], btype="band", fs=SR, output="sos")
    return sosfilt(sos, y) * 1.4


def synth_organ(n, dur, vel):
    f = hz(n)
    t = np.arange(int((dur + 0.04) * SR)) / SR
    vib = 1 + 0.003 * np.sin(2 * np.pi * 6.2 * t)
    y = sum(a * np.sin(2 * np.pi * f * m * np.cumsum(vib) / SR) for m, a in
            ((1, 1), (2, 0.6), (3, 0.45), (4, 0.25), (6, 0.12), (8, 0.08)))
    e = env_adsr(int(dur * SR), 0.004, 0.05, 0.8, 0.04)[:len(t)]
    e = np.pad(e, (0, max(0, len(t) - len(e))))
    return y * e * (vel / 127) * 0.16


def synth_horn(n, dur, vel, trombone=False):
    f = hz(n)
    L = int((dur + 0.12) * SR)
    t = np.arange(L) / SR
    vib_amt = np.clip((t - 0.18) / 0.25, 0, 1) * 0.0045
    phase = 2 * np.pi * f * np.cumsum(1 + vib_amt * np.sin(2 * np.pi * 5.3 * t)) / SR
    bright = 2.5 + 7.0 * np.clip(t / 0.07, 0, 1) - 2.0 * np.clip((t - 0.1) / 0.4, 0, 1)
    nmax = int(min(28, (SR / 2.2) / f))
    y = np.zeros(L)
    for h in range(1, nmax + 1):
        y += np.sin(h * phase) / h * np.exp(-(h - 1) / bright)
    e = env_adsr(int(dur * SR), 0.035, 0.12, 0.8, 0.09)[:L]
    e = np.pad(e, (0, max(0, L - len(e))))
    breath = sosfilt(butter(2, [1500, 6000], btype="band", fs=SR, output="sos"), rng.normal(0, 1, L)) * 0.02
    out = (y * 0.55 + breath) * e * (vel / 127)
    return out * (0.32 if trombone else 0.26)


def synth_voice(n, dur, vel):
    f = hz(n)
    t = np.arange(int((dur + 0.1) * SR)) / SR
    vib = 1 + np.clip((t - 0.15) / 0.2, 0, 1) * 0.006 * np.sin(2 * np.pi * 5.6 * t)
    ph = 2 * np.pi * f * np.cumsum(vib) / SR
    y = np.sin(ph) + 0.25 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)
    e = env_adsr(int(dur * SR), 0.05, 0.1, 0.85, 0.1)[:len(t)]
    e = np.pad(e, (0, max(0, len(t) - len(e))))
    return y * e * (vel / 127) * 0.22


def noise_hit(dur, lo, hi, decay, amp):
    t = np.arange(int(dur * SR)) / SR
    y = sosfilt(butter(2, [lo, hi], btype="band", fs=SR, output="sos"), rng.normal(0, 1, len(t)))
    return y * np.exp(-t * decay) * amp


def tom(f0, amp=0.6):
    t = np.arange(int(0.35 * SR)) / SR
    return np.sin(2 * np.pi * f0 * (1 + 0.6 * np.exp(-t * 25)) * t) * np.exp(-t * 9) * amp


def conga(f0, amp):
    t = np.arange(int(0.3 * SR)) / SR
    y = np.sin(2 * np.pi * f0 * (1 + 0.25 * np.exp(-t * 40)) * t) * np.exp(-t * 14)
    return (y + noise_hit(0.3, 800, 4000, 60, 0.15)) * amp


def load_hit(path):
    y, sr = sf.read(path)
    y = y.mean(axis=1) if y.ndim > 1 else y
    return y / max(np.abs(y).max(), 1e-9)


def drum_bank(kit):
    kick = load_hit(REPO / kit["kick"])
    t = np.arange(int(0.42 * SR)) / SR
    sub = np.sin(2 * np.pi * 52 * (1 + 1.2 * np.exp(-t * 35)) * t) * np.exp(-t * 7)
    L = max(len(kick), len(sub))
    # The phone-recorded kick has little below 100 Hz; a sub layer puts the low end back.
    kick = np.pad(kick, (0, L - len(kick))) * 0.55 + np.pad(sub, (0, L - len(sub))) * 0.8
    hat = load_hit(REPO / kit["hat"])
    open_hat = np.concatenate([hat, np.zeros(int(0.1 * SR))]) * 0.7 + np.pad(
        noise_hit(0.35, 7000, 15000, 9, 0.5), (0, max(0, len(hat) + int(0.1 * SR) - int(0.35 * SR))))[:len(hat) + int(0.1 * SR)]
    return {
        36: kick * 0.9, 37: load_hit(REPO / kit["snare"]) * 0.7, 38: load_hit(REPO / kit["snare"]) * 0.7,
        42: hat * 0.35, 46: open_hat * 0.35, 48: tom(160), 45: tom(110),
        49: noise_hit(1.6, 3000, 16000, 2.6, 0.35),
        70: noise_hit(0.07, 5000, 14000, 55, 0.25), 63: conga(330, 0.5), 64: conga(220, 0.55),
    }


def place(buf, y, start_s, pan=0.0):
    a = int(start_s * SR)
    if a >= buf.shape[1]:
        return
    y = y[: buf.shape[1] - a]
    left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, a:a + len(y)] += y * left
    buf[1, a:a + len(y)] += y * right


def reverb_ir(seconds=1.8):
    t = np.arange(int(seconds * SR)) / SR
    ir = np.stack([rng.normal(0, 1, len(t)), rng.normal(0, 1, len(t))]) * np.exp(-t * 3.2)
    ir = sosfilt(butter(1, 6000, fs=SR, output="sos"), ir)
    return ir / np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))


def chord_at(chord_map, beat):
    current = chord_map[0]
    for c in chord_map:
        if c[0] <= beat + 0.05:
            current = c
    return current


def render(notes, bpm, kit, length_beats, chord_map, vocal_phrases, bank_samplers, voice):
    sec = 60 / bpm
    L = int((length_beats * sec + 3) * SR)
    bank = drum_bank(kit)
    bufs = {p: np.zeros((2, L)) for p in PARTS}
    pans = {36: 0, 37: 0.05, 38: 0.05, 42: 0.3, 46: 0.3, 48: -0.25, 45: 0.25, 49: -0.3, 70: 0.45,
            63: -0.4, 64: -0.2}
    used = {}
    for part, ns in notes.items():
        sampler = bank_samplers.get(part)
        if part in ("guitar", "keys"):
            by_time = {}
            for t, n, d, v in ns:
                by_time.setdefault(round(t, 3), []).append((n, d, v))
            for k, (t, chord) in enumerate(sorted(by_time.items())):
                y = None
                if sampler is not None:
                    _, root, quality = chord_at(chord_map, t)
                    y = sampler.play(root, quality, chord[0][1] * sec + 0.05, chord[0][2], variant=k)
                    used[part] = "band"
                if y is None:
                    y = synth_skank([c[0] for c in chord], chord[0][1] * sec, chord[0][2]) if part == "guitar" else \
                        sum(np.pad(synth_organ(c[0], c[1] * sec, c[2]), (0, 0)) for c in chord[:1])
                    used.setdefault(part, "synth")
                place(bufs[part], y * (0.9 if part == "guitar" else 0.55), t * sec, -0.35 if part == "guitar" else 0.35)
            continue
        if part == "vocals" and voice:
            import sing
            cache, i = {}, 0
            for syllables, count in vocal_phrases:
                group = [(t * sec, d * sec, n) for t, n, d, v in ns[i:i + count]]
                i += count
                for t0, y in sing.sing_line(syllables, group, voice, cache):
                    place(bufs[part], y * 1.6, t0)
            used[part] = f"sung ({voice})"
            continue
        for t, n, d, v in ns:
            s = t * sec
            if part in ("drums", "other"):
                y = bank[n] * (v / 127) ** 1.3
                place(bufs[part], y, s, pans.get(n, 0))
            elif part == "bass":
                y = sampler.play(n, d * sec, v) if sampler is not None else None
                used[part] = "band" if y is not None else "synth"
                place(bufs[part], y * 0.6 if y is not None else synth_bass(n, d * sec, v), s)
            elif part == "keys":
                place(bufs[part], synth_organ(n, d * sec, v), s, 0.35)
            elif part == "horns":
                y = sampler.play(n, d * sec, v, sustain=True) if sampler is not None else None
                used[part] = "band" if y is not None else "synth"
                if y is None:
                    y = synth_horn(n, d * sec, v, trombone=n < 64)
                else:
                    y = y * 0.45
                place(bufs[part], y, s, -0.2 if n >= 55 else 0.2)
            elif part == "vocals":
                place(bufs[part], synth_voice(n, d * sec, v), s)
    ir = reverb_ir()
    wet = {"drums": 0.08, "guitar": 0.22, "keys": 0.15, "horns": 0.25, "vocals": 0.2, "other": 0.12}
    gain = {"vocals": 0.9, "drums": 1.0, "bass": 1.0, "guitar": 0.55, "keys": 0.55, "horns": 0.8, "other": 0.6}
    for p, b in bufs.items():
        if wet.get(p):
            verb = np.stack([oaconvolve(b[0], ir[0])[:L], oaconvolve(b[1], ir[1])[:L]])
            b = b + wet[p] * verb
        bufs[p] = b * gain[p]
    mix = sum(bufs.values())
    peak = np.abs(mix).max()
    scale = 0.89 / peak if peak > 0 else 1
    return {p: b * scale for p, b in bufs.items()}, mix * scale, used


# ---------------------------------------------------------------- output

def write_midi(path, bpm, tracks):
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    sec = 60 / bpm
    for name, ns in tracks:
        drum = name in ("drums", "other")
        inst = pretty_midi.Instrument(program=0 if drum else GM_PROGRAM[name], is_drum=drum,
                                      name="percussion" if name == "other" else
                                      ("guitar (skank)" if name == "guitar" else
                                       "keys (organ bubble)" if name == "keys" else
                                       "vocal guide melody" if name == "vocals" else name))
        for t, n, d, v in ns:
            inst.notes.append(pretty_midi.Note(velocity=int(v), pitch=int(n), start=t * sec, end=(t + d) * sec))
        pm.instruments.append(inst)
    pm.write(str(path))


def song_sheet(song, starts, bpm):
    lines = [f"# {song['title']}", "", f"{song['key']}, {bpm} BPM, one-drop. {song['subtitle']}.", ""]
    for (name, beat), sec in zip(starts, song["sections"]):
        bar = int(beat // 4) + 1
        sec_time = beat * 60 / bpm
        lines.append(f"## {name}  (bar {bar}, {int(sec_time // 60)}:{int(sec_time % 60):02d})")
        lines.append("Chords: " + " | ".join(sec["chords"]))
        for l in sec.get("lyrics", []) or []:
            lines.append(f"    {l}")
        lines.append("")
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    song_path = Path(args[0] if args else REPO / "tools/compose/songs/common-ground.json")
    song = json.loads(song_path.read_text())
    bpm = song["bpm"]
    groove = json.loads((REPO / song["groove"]).read_text())
    straight, starts, total_beats, chord_map, vocal_phrases = arrange(song)
    notes = apply_groove(straight, groove, bpm)
    slug = "Test song - " + song["title"]
    out = REPO / "band-stems" / slug
    for sub in ("stems", "midi", "wave", "sheet"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    print(f"{song['title']}: {total_beats / 4:.0f} bars, {total_beats * 60 / bpm:.0f}s; rendering…")
    import samplers
    recordings = [d.name for d in sorted((REPO / "band-stems").iterdir())
                  if (d / "info.json").exists() and not d.name.startswith("Test song")]
    plan = {"bass": [(r, "bass", "note") for r in recordings],
            "horns": [(r, "horns", "note") for r in recordings],
            "guitar": [(r, "guitar", "stab") for r in recordings],
            "keys": [(r, "keys", "stab") for r in recordings]}
    print("harvesting the band's notes and chords…")
    bank_samplers = {} if "--synth" in sys.argv else samplers.build(REPO, plan)
    stems, mix, used = render(notes, bpm, song["kit"], total_beats, chord_map, vocal_phrases, bank_samplers,
                              None if "--no-vocals" in sys.argv else song.get("voice"))
    print("sounds used:", used)
    sf.write(out / "mix.wav", mix.T, SR, subtype="PCM_24")
    for p, b in stems.items():
        sf.write(out / "stems" / f"{p}.wav", b.T, SR, subtype="PCM_24")
        studio.waveform_png(b, out / "wave" / f"{p}.png", studio.COLORS[p])
    studio.waveform_png(mix, out / "wave" / "mix.png", studio.COLORS["mix"])
    base = f"{song['title']} - {bpm}bpm"
    write_midi(out / "midi" / f"{base} - all parts.mid", bpm, [(p, notes[p]) for p in PARTS if notes[p]])
    write_midi(out / "midi" / f"{base} - all parts (straight, no groove).mid", bpm,
               [(p, straight[p]) for p in PARTS if straight[p]])
    for p in PARTS:
        if notes[p]:
            label = {"other": "percussion", "vocals": "vocal guide melody", "guitar": "skank guitar",
                     "keys": "organ bubble"}.get(p, p)
            write_midi(out / "midi" / f"{base} - {label}.mid", bpm, [(p, notes[p])])
    (out / "sheet" / f"{song['title']} - lyrics and chords.md").write_text(song_sheet(song, starts, bpm))
    (out / "groove.json").write_text(json.dumps(groove, indent=2))
    info = {
        "title": slug, "source": str(song_path.relative_to(REPO)), "mode": "composed",
        "duration": round(mix.shape[1] / SR, 1), "tempo": bpm, "key": song["key"], "key_confidence": 1.0,
        "reconstruction_percent": 100.0,
        "stem_levels_db": {p: studio.stem_level(b) for p, b in stems.items()},
        "drum_hits": {}, "midi": sorted(f.name for f in (out / "midi").glob("*.mid")), "kit": {},
        "phrases": [], "groove": groove, "sounds": used,
    }
    (out / "info.json").write_text(json.dumps(info, indent=2))
    studio.report_page(out, slug, info, stems, mix)
    studio.library_page(REPO / "band-stems")
    print(f"Done -> {out}")


if __name__ == "__main__":
    main()
