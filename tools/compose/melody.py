"""Write vocal melodies for lyrics, scored for catchiness.

For each section, many candidate melodies are generated over the section's chords and the
best-scoring one is kept. The score follows research_notes/Reggae afrobeat style guide/
catchiness_and_learning.md:

  melodic repetition       strongest hook predictor (Van Balen et al. 2015: +12% faster
                           recognition); choruses repeat their title line's melody
  melodic conventionality  arch-shaped contour, mostly stepwise motion (+7.8%)
  range conventionality    chorus spans about an octave, verses less (+6.8%)
  salient detail           one or two leaps or repeated-note figures (Jakubowski et al. 2017)
  chord tones              about 70-80% of notes, as in classic reggae choruses (Hooktheory)
  syncopation              medium, not none and not maximal (Witek et al. 2014)
Target ranges beyond those directions are engineering defaults, to be tuned by learning.
"""
import re

import numpy as np

SCALES = {"minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10],
          "major": [0, 2, 4, 5, 7, 9, 11], "mixolydian": [0, 2, 4, 5, 7, 9, 10]}
WEIGHTS = {"repetition": 12, "contour": 7.8, "steps": 5, "range": 6.8, "salient": 4, "chord_tones": 6,
           "syncopation": 4, "repeats": 2, "cadence": 5}

_pyphen = None


def syllable_count(word):
    global _pyphen
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    if w.endswith("le") and len(w) > 2 and w[-3] not in "aeiouy":
        n = max(n, 2)
    if _pyphen is None:
        import pyphen
        _pyphen = pyphen.Pyphen(lang="en_US")
    return max(1, n, len(_pyphen.positions(w)) + 1)


def syllable_tokens(line):
    """'Mixed roots, one tree' -> ['Mixed', 'roots', 'one', 'tree']; multi-syllable words become
    'Mel-' 'o-' 'dy' style tokens (the text split is approximate; only the count matters)."""
    out = []
    for word in re.findall(r"[A-Za-z']+", line):
        n = syllable_count(word)
        if n == 1:
            out.append(word)
            continue
        size = max(1, len(word) // n)
        parts = [word[i * size:(i + 1) * size] for i in range(n - 1)] + [word[(n - 1) * size:]]
        out += [p + "-" for p in parts[:-1]] + [parts[-1]]
    return out


# ---------------------------------------------------------------- rhythm

def rhythm(n, rng, steps=32, sync=0.3):
    """n onsets in a 2-bar phrase on a 16th grid -> [(step, length)]; leaves a breath at the end."""
    start = int(rng.choice([0, 1, 2, 2, 4], p=[0.25, 0.1, 0.35, 0.2, 0.1]))
    breath = int(rng.integers(3, 7))
    avail = steps - start - breath
    if n > avail:
        start, breath = 0, 2
        avail = steps - 2
    n = min(n, avail)
    lengths = [2] * n
    total = sum(lengths)
    guard = 0
    while total != avail and guard < 500:
        guard += 1
        i = int(rng.integers(0, n))
        if total > avail and lengths[i] > 1:
            lengths[i] -= 1
            total -= 1
        elif total < avail and lengths[i] < 6:
            lengths[i] += 1 if rng.random() < 0.7 else 2
            total = sum(lengths)
    if total > avail:
        lengths[-1] -= total - avail
    lengths[-1] = max(lengths[-1], 2)
    out, t = [], start
    for L in lengths:
        out.append((t, max(1, L)))
        t += max(1, L)
    # syncopate: occasionally push a note a 16th early (anticipation)
    for k in range(1, len(out)):
        s, L = out[k]
        if s % 4 == 0 and rng.random() < sync and out[k - 1][1] > 1:
            ps, pl = out[k - 1]
            out[k - 1] = (ps, pl - 1)
            out[k] = (s - 1, L + 1)
    return out


# ---------------------------------------------------------------- pitch

def chord_pcs(root, quality):
    third = 3 if quality == "minor" else 4
    return {root % 12, (root + third) % 12, (root + 7) % 12}


def pitches(rhy, chords, tonic, scale, lo, hi, rng, end_degree=None, contour="arch"):
    """chords: [(root_pc, quality)] per bar of the phrase."""
    pool = sorted(p for p in range(lo, hi + 1) if (p - tonic) % 12 in scale)
    idx_of = {p: i for i, p in enumerate(pool)}
    out, prev = [], None
    n = len(rhy)
    for k, (s, L) in enumerate(rhy):
        bar = min(len(chords) - 1, s // 16)
        ct = chord_pcs(*chords[bar])
        strong = s % 4 == 0
        frac = k / max(1, n - 1)
        lift = (0.5 - abs(frac - 0.45)) if contour == "arch" else (0.5 - frac)
        if prev is None:
            cands = [p for p in pool if p % 12 in ct and lo + 2 <= p <= (lo + hi) // 2 + 2]
            p = int(rng.choice(cands)) if cands else pool[len(pool) // 3]
        else:
            i = idx_of[prev]
            r = rng.random()
            if r < 0.22:
                step = 0
            elif r < 0.85:
                step = 1 if rng.random() < 0.5 + lift * 0.6 else -1
            else:
                step = int(rng.choice([2, 3, 4])) * (1 if rng.random() < 0.5 + lift * 0.6 else -1)
            j = int(np.clip(i + step, 0, len(pool) - 1))
            p = pool[j]
            if strong and p % 12 not in ct:            # strong beats land on chord tones
                near = sorted((q for q in pool if q % 12 in ct), key=lambda q: abs(q - p))
                p = near[0] if near else p
        out.append(p)
        prev = p
    if end_degree is not None and out:
        target = (tonic + end_degree) % 12
        near = sorted((q for q in pool if q % 12 == target), key=lambda q: abs(q - out[-1]))
        out[-1] = near[0]
    return out


# ---------------------------------------------------------------- scoring

def gauss(x, mu, sigma):
    return float(np.exp(-((x - mu) ** 2) / (2 * sigma ** 2)))


def features(lines, chords_per_line, kind):
    """lines: [[(step, len, pitch)]] per 2-bar line."""
    allp = [p for ln in lines for _, _, p in ln]
    iv = np.diff(allp) if len(allp) > 1 else np.array([0])
    f = {}
    shapes = [tuple(np.sign(np.diff([p for _, _, p in ln]))) + tuple(s % 16 for s, _, _ in ln) for ln in lines]
    reps = sum(1 for i in range(len(shapes)) for j in range(i) if shapes[i][:6] == shapes[j][:6])
    f["repetition"] = min(1.0, reps / max(1, len(lines) - 1))
    if kind == "verse":
        f["repetition"] = gauss(f["repetition"], 0.4, 0.3)
    rng_semis = max(allp) - min(allp)
    f["range"] = gauss(rng_semis, 11 if kind == "chorus" else 7, 2.5)
    steps = np.mean(np.abs(iv) <= 2)
    f["steps"] = gauss(steps, 0.68, 0.12)
    f["repeats"] = gauss(np.mean(iv == 0), 0.22, 0.1)
    leaps = int(np.sum(np.abs(iv) >= 5))
    f["salient"] = gauss(leaps / max(1, len(lines) / 2), 1.5, 1.0)
    peak = int(np.argmax(allp)) / max(1, len(allp) - 1)
    f["contour"] = gauss(peak, 0.45, 0.22)
    ct = 0
    for ln, chords in zip(lines, chords_per_line):
        for s, _, p in ln:
            ct += p % 12 in chord_pcs(*chords[min(len(chords) - 1, s // 16)])
    f["chord_tones"] = gauss(ct / max(1, len(allp)), 0.75, 0.1)
    onsets = [s for ln in lines for s, _, _ in ln]
    sync = np.mean([s % 2 == 1 for s in onsets])
    f["syncopation"] = gauss(sync, 0.22, 0.12)
    return f


def score(f):
    return sum(WEIGHTS[k] * v for k, v in f.items() if k in WEIGHTS) / sum(WEIGHTS.values())


# ---------------------------------------------------------------- sections

def write_section(lyric_lines, chords, kind, tonic, mode, lo, hi, rng, candidates=400, sync=0.3):
    """lyric_lines: 2-bar lines; chords: [(root_pc, quality)] per bar for the whole section.
    Returns (vocals token string, syllables string, score, features)."""
    scale = SCALES[mode]
    per_line = [chords[2 * i:2 * i + 2] or chords[-2:] for i in range(len(lyric_lines))]
    toks = [syllable_tokens(l) for l in lyric_lines]
    best = None
    for _ in range(candidates):
        lines = []
        for i, t in enumerate(toks):
            reuse = kind == "chorus" and i >= 2 and len(toks[i]) == len(toks[i - 2])
            if reuse:                                   # the hook comes back: same melody
                prev = lines[i - 2]
                end = 0 if i == len(toks) - 1 else None
                ps = [p for _, _, p in prev]
                if end is not None:
                    ps = pitches([(s, L) for s, L, _ in prev], per_line[i], tonic, scale, lo, hi, rng,
                                 end_degree=0)[:-1] + [ps[-1]]
                    ps[-1] = sorted((q for q in range(lo, hi + 1) if (q - tonic) % 12 == 0),
                                    key=lambda q: abs(q - ps[-2]))[0]
                lines.append([(s, L, p) for (s, L, _), p in zip(prev, ps)])
                continue
            rhy = rhythm(len(t), rng, sync=sync)
            end = 0 if i == len(toks) - 1 else (7 if i % 2 == 1 else None)
            ps = pitches(rhy, per_line[i], tonic, scale, lo, hi, rng, end_degree=end,
                         contour="arch" if i % 2 == 0 else "fall")
            lines.append([(s, L, p) for (s, L), p in zip(rhy, ps)])
        f = features(lines, per_line, kind)
        f["cadence"] = 1.0 if (lines[-1][-1][2] - tonic) % 12 == 0 else 0.0
        sc = score(f)
        if best is None or sc > best[0]:
            best = (sc, lines, f)
    sc, lines, f = best
    return to_tokens(lines), " ".join(" ".join(t) for t in toks), sc, f


NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def to_tokens(lines):
    """[[(step, len, pitch)]] per 2-bar line -> 'D4/0.5 r/0.25 ...' covering every bar."""
    out = []
    for ln in lines:
        t = 0
        for s, L, p in ln:
            if s > t:
                out.append(f"r/{(s - t) / 4:g}")
            out.append(f"{NAMES[p % 12]}{p // 12 - 1}/{L / 4:g}")
            t = s + L
        if t < 32:
            out.append(f"r/{(32 - t) / 4:g}")
    return " ".join(out)
