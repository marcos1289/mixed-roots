"""Accuracy check for classify_drum_hits: synthesize a groove with known hits, detect, score.

    tools/stems/.venv/bin/python tools/stems/test_drums.py
"""
import numpy as np
import studio

SR = studio.SR
rng = np.random.default_rng(1)


def kick():
    t = np.arange(int(0.35 * SR)) / SR
    return np.sin(2 * np.pi * (45 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 9)


def snare():
    t = np.arange(int(0.25 * SR)) / SR
    return (0.6 * rng.standard_normal(len(t)) * np.exp(-t * 22) + 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30))


def hat():
    t = np.arange(int(0.06 * SR)) / SR
    n = rng.standard_normal(len(t))
    n = np.diff(np.diff(n, prepend=0), prepend=0)   # crude high-pass
    return 0.35 * n * np.exp(-t * 70)


def main():
    bpm, bars = 76, 8
    six = 60 / bpm / 4
    truth = []
    for bar in range(bars):
        b0 = bar * 16 * six
        truth.append((b0 + 8 * six, "kick"))
        truth.append((b0 + 8 * six, "snare"))
        for st in range(0, 16, 2):
            truth.append((b0 + st * six + (0.012 if st % 4 == 2 else 0), "hat"))
        if bar % 2:
            truth.append((b0 + 14 * six, "kick"))
    n = int((bars * 16 * six + 1) * SR)
    y = np.zeros(n)
    for t, kind in truth:
        s = {"kick": kick, "snare": snare, "hat": hat}[kind]()
        a = int(t * SR)
        y[a:a + len(s)] += s * rng.uniform(0.8, 1.0)
    # bass bleed, as a separated drum stem from a real band would have
    tt = np.arange(n) / SR
    y += 0.08 * np.sin(2 * np.pi * 55 * tt) * (np.sin(2 * np.pi * bpm / 60 * tt) > 0)
    y += 0.003 * rng.standard_normal(n)
    hits = studio.classify_drum_hits(y.astype(np.float32))
    tol = 0.035
    print(f"{'part':6} {'true':>5} {'found':>6} {'hit':>5} {'missed':>7} {'extra':>6}")
    for kind in ("kick", "snare", "hat"):
        want = [t for t, k in truth if k == kind]
        got = [h["t"] for h in hits if h["kind"] == kind]
        matched = sum(any(abs(g - w) < tol for g in got) for w in want)
        extra = sum(not any(abs(g - w) < tol for w in want) for g in got)
        print(f"{kind:6} {len(want):5} {len(got):6} {matched:5} {len(want) - matched:7} {extra:6}")
        if "-v" in __import__("sys").argv:
            print("   extra at beats:", [round(g / (4 * six), 2) for g in got if not any(abs(g - w) < tol for w in want)])


if __name__ == "__main__":
    main()
