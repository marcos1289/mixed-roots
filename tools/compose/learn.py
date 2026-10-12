#!/usr/bin/env python3
"""Turn the band's A/B picks from the studio page into what evolve.py samples next.

    tools/stems/.venv/bin/python tools/compose/learn.py

The studio page saves each pick encrypted (same key as the studio) to feedback/*.bin in the
repo. This pulls them, decrypts with .studio-password, and for every setting where the two
compared variants differed, credits the winner's option with a win and the loser's with a
loss ("both good" = half each, "both bad" = a loss for both). The records go to learned.json;
evolve.py turns them into Thompson-sampling odds. Also prints a per-variant Bradley-Terry
ranking and the written notes, so a person can read what the band is saying.
"""
import base64
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LEARNED = HERE / "learned.json"


def key():
    cfg = json.loads((REPO / "tools/stems/private_studio.json").read_text())
    pw = (REPO / ".studio-password").read_text().strip().encode()
    return PBKDF2HMAC(hashes.SHA256(), 32, base64.b64decode(cfg["salt"]), 600_000).derive(pw)


def ratings():
    aes = AESGCM(key())
    out = []
    for f in sorted((REPO / "feedback").glob("*.bin")):
        raw = f.read_bytes()
        try:
            out.append(json.loads(aes.decrypt(raw[:12], raw[12:], None)))
        except Exception:
            print(f"skipping {f.name}: can't decrypt (password changed?)")
    return out


def bradley_terry(items, games, iters=200):
    """games: [(winner, loser, weight)] -> strength per item (MM algorithm, light prior)."""
    s = {i: 1.0 for i in items}
    for _ in range(iters):
        wins = defaultdict(lambda: 0.5)
        denom = defaultdict(lambda: 1.0 / 2)
        for w, l, wt in games:
            wins[w] += wt
            for a, b in ((w, l), (l, w)):
                denom[a] += wt / (s[a] + s[b])
        s = {i: wins[i] / denom[i] for i in items}
        m = np.exp(np.mean(np.log(list(s.values()))))
        s = {i: v / m for i, v in s.items()}
    return s


def main():
    subprocess.run(["git", "-C", str(REPO), "pull", "-q", "--rebase", "origin", "main"], check=False)
    rs = ratings()
    batches = {}
    for f in (HERE / "songs" / "batches").glob("*/batch.json"):
        b = json.loads(f.read_text())
        batches[b["id"]] = {v["id"]: v for v in b["variants"]}
    stats = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    games, notes = [], []
    for r in rs:
        vs = batches.get(r["batch"])
        if not vs or r["a"] not in vs or r["b"] not in vs:
            continue
        a, b = vs[r["a"]], vs[r["b"]]
        if r.get("note"):
            notes.append(f'{r.get("who", "?")} on {r["batch"]} {r["a"]} vs {r["b"]} ({r["choice"]}): {r["note"]}')
        res = {"a": (1, 0), "b": (0, 1), "tie": (0.5, 0.5), "both_bad": (0, 0)}[r["choice"]]
        ida, idb = f'{r["batch"]}/{r["a"]}', f'{r["batch"]}/{r["b"]}'
        if r["choice"] == "a":
            games.append((ida, idb, 1))
        elif r["choice"] == "b":
            games.append((idb, ida, 1))
        elif r["choice"] == "tie":
            games += [(ida, idb, 0.5), (idb, ida, 0.5)]
        for p in a["params"]:
            oa, ob = str(a["params"][p]), str(b["params"][p])
            if oa == ob and r["choice"] != "both_bad":
                continue
            stats[p][oa][0] += res[0]
            stats[p][oa][1] += 1 - res[0] if r["choice"] != "both_bad" else 1
            if oa != ob:
                stats[p][ob][0] += res[1]
                stats[p][ob][1] += 1 - res[1] if r["choice"] != "both_bad" else 1
    LEARNED.write_text(json.dumps({"ratings": len(rs), "stats": {p: dict(d) for p, d in stats.items()}},
                                  indent=2) + "\n")
    print(f"{len(rs)} ratings")
    for p, d in stats.items():
        ranked = sorted(d.items(), key=lambda kv: -(kv[1][0] + 1) / (sum(kv[1]) + 2))
        print(f"  {p:12} " + "  ".join(f"{o}: {w:g}-{l:g}" for o, (w, l) in ranked))
    if games:
        items = sorted({g[0] for g in games} | {g[1] for g in games})
        st = bradley_terry(items, games)
        print("variant strength (Bradley-Terry):",
              ", ".join(f"{k} {v:.2f}" for k, v in sorted(st.items(), key=lambda kv: -kv[1])))
    for n in notes:
        print("  note:", n)


if __name__ == "__main__":
    main()
