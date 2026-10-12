"""Sing lyrics on a melody using the Mac's speech voices and the WORLD vocoder.

Each word is spoken by `say`, then WORLD splits it into pitch, spectral envelope (the
voice's tone and vowel shape) and breathiness. The envelope is stretched to the length of
the word's notes, keeping the consonants at their spoken length, and the pitch is
replaced by the melody, with a short glide between notes and vibrato on held notes.
The result sings the actual words; it sounds processed, like hard pitch correction.

Syllables come from the song file: "Hud- son" is one word over two notes, and "_" holds
the previous syllable over another note (a melisma).
"""
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np
import pyworld as pw
import soundfile as sf

SR = 44100
VOICE_SR = 22050
FRAME_MS = 5.0
RATE = 120          # speaking rate for `say` (wpm); 120 scored best in check_vocals.py (84% vs 68% at 150)


def words_from_syllables(text):
    """'From Ac- cra _ to' -> [('From', 1), ('Accra', 3), ('to', 1)]  (word, notes it spans)"""
    words, cur, count = [], "", 0
    for tok in text.split():
        if tok == "_":
            words[-1] = (words[-1][0], words[-1][1] + 1) if not cur else words[-1]
            if cur:
                count += 1
            continue
        if tok.endswith("-"):
            cur += tok[:-1]
            count += 1
            continue
        cur += tok
        count += 1
        words.append((cur, count))
        cur, count = "", 0
    return words


def speak(word, voice, cache):
    key = (word.lower(), voice, RATE)
    if key not in cache:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.wav"
            subprocess.run(["say", "-v", voice, "-r", str(RATE), "-o", str(p), "--file-format=WAVE",
                            f"--data-format=LEI16@{VOICE_SR}", word], check=True)
            y, _ = sf.read(p)
        y, _ = librosa.effects.trim(y.astype(np.float64), top_db=38)
        cache[key] = y
    return cache[key]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def sing_word(y, notes, glide_s=0.035, vib_depth=0.18, vib_rate=5.0):
    """notes: [(start_s, dur_s, midi)] relative to the word's first note. Returns audio at SR."""
    f0, t = pw.harvest(y, VOICE_SR, frame_period=FRAME_MS, f0_floor=60, f0_ceil=600)
    sp = pw.cheaptrick(y, f0, t, VOICE_SR)
    ap = pw.d4c(y, f0, t, VOICE_SR)
    n = len(f0)
    total = notes[-1][0] + notes[-1][1]
    m = max(4, int(total * 1000 / FRAME_MS))
    voiced = np.where(f0 > 0)[0]
    if len(voiced) == 0:
        pre, suf = 0, n
    else:
        pre, suf = voiced[0], voiced[-1] + 1
    head, tail = pre, n - suf
    mid_src = max(1, suf - pre)
    mid_dst = m - head - tail
    if mid_dst < mid_src // 3:                     # word longer than its notes: squeeze everything
        idx = np.linspace(0, n - 1, m)
    else:
        idx = np.concatenate([np.arange(head), pre + np.linspace(0, mid_src - 1, mid_dst), suf + np.arange(tail)])
    idx = np.clip(idx, 0, n - 1)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, n - 1)
    w = (idx - lo)[:, None]
    sp2 = np.exp((1 - w) * np.log(sp[lo] + 1e-12) + w * np.log(sp[hi] + 1e-12))
    ap2 = (1 - w) * ap[lo] + w * ap[hi]
    src_voiced = f0[np.round(idx).astype(int)] > 0
    times = np.arange(len(idx)) * FRAME_MS / 1000
    target = np.zeros(len(idx))
    for k, (s, d, midi) in enumerate(notes):
        sel = (times >= s) & (times < s + d + (1 if k == len(notes) - 1 else 0))
        target[sel] = midi
    target[target == 0] = notes[0][2]
    # glide into each new note
    g = max(1, int(glide_s * 1000 / FRAME_MS))
    smooth = np.convolve(np.pad(target, (g, g), mode="edge"), np.ones(g) / g, mode="same")[g:-g]
    # vibrato on notes held longer than 0.3 s, fading in
    vib = np.zeros(len(idx))
    for s, d, _ in notes:
        if d > 0.3:
            sel = (times >= s + 0.15) & (times < s + d)
            ramp = np.clip((times[sel] - s - 0.15) / 0.2, 0, 1)
            vib[sel] = vib_depth * ramp * np.sin(2 * np.pi * vib_rate * (times[sel] - s))
    f0_new = np.where(src_voiced, hz(smooth + vib), 0.0)
    # sustained vowels must stay voiced even where the stretched source flickered
    if len(voiced):
        core = (np.arange(len(idx)) >= head) & (np.arange(len(idx)) < len(idx) - tail)
        f0_new[core] = hz(smooth + vib)[core]
    out = pw.synthesize(np.ascontiguousarray(f0_new), np.ascontiguousarray(sp2), np.ascontiguousarray(ap2),
                        VOICE_SR, FRAME_MS)
    out = librosa.resample(out, orig_sr=VOICE_SR, target_sr=SR)
    fade = int(0.012 * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out


def sing_line(syllables, notes, voice, cache, transpose=0):
    """notes: [(start_s, dur_s, midi)] in order, one per syllable or '_' token. Returns
    [(start_s, audio)] one entry per word."""
    words = words_from_syllables(syllables)
    want = sum(c for _, c in words)
    if want != len(notes):
        raise ValueError(f"{want} syllable slots for {len(notes)} notes in: {syllables!r}")
    out, i = [], 0
    for word, count in words:
        group = notes[i:i + count]
        i += count
        t0 = group[0][0]
        rel = [(s - t0, d, m + transpose) for s, d, m in group]
        out.append((t0, sing_word(speak(word, voice, cache), rel)))
    return out
