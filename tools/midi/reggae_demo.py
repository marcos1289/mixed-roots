#!/usr/bin/env python3
"""Write an 8-bar reggae one-drop groove as MIDI files for Reason (or any DAW).

    python3 tools/midi/reggae_demo.py [out_dir] [--groove band-stems/<song>/groove.json]

--groove applies the push/pull and accents measured from a real recording by
tools/stems (per 16th position: kick timing drives the bass, snare the skank and horns,
hats the hats), so the parts sit the way the band plays instead of on a rigid grid.

No dependencies. Writes one type-1 file with every part plus one file per part.
Drums use General MIDI note numbers (kick 36, side stick 37, hats 42/46).
"""
import json
import random
import struct
import sys
from pathlib import Path

PPQ = 480
SIX = PPQ // 4  # one 16th note
BPM = 76
random.seed(7)

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def midi_note(name, octave):
    return 12 * (octave + 1) + NOTE[name]


# One chord per bar: (root, quality)
PROGRESSION = [("A", "m"), ("A", "m"), ("D", "m"), ("D", "m"), ("A", "m"), ("A", "m"), ("G", ""), ("E", "m")]


def triad(root, quality, octave=4):
    r = midi_note(root, octave)
    third = 3 if quality == "m" else 4
    return [r, r + third, r + 7]


def hum(v, spread=8):
    return max(1, min(127, v + random.randint(-spread, spread)))


def drums():
    notes = []
    for bar in range(8):
        t0 = bar * 16 * SIX
        notes.append((t0 + 8 * SIX, 36, hum(110), SIX))       # the "one drop": kick on beat 3
        notes.append((t0 + 8 * SIX, 37, hum(100), SIX))       # side stick with it
        for step in range(0, 16, 2):                           # 8th-note hats, swung slightly
            swing = 20 if step % 4 == 2 else 0
            open_hat = bar % 2 == 1 and step == 14
            notes.append((t0 + step * SIX + swing, 46 if open_hat else 42, hum(80 if step % 4 else 95), SIX))
        if bar == 7:                                            # small fill into the loop
            for step, n in ((12, 38), (13, 38), (14, 45), (15, 41)):
                notes.append((t0 + step * SIX, n, hum(90), SIX))
    return notes


def bass():
    notes = []
    pattern = [(2, 0, 2), (6, 0, 1), (8, 7, 2), (11, 10, 1), (14, 0, 2)]  # (16th step, interval, length)
    for bar, (root, quality) in enumerate(PROGRESSION):
        r = midi_note(root, 1) if NOTE[root] >= NOTE["E"] else midi_note(root, 2)
        for step, interval, length in pattern:
            notes.append((bar * 16 * SIX + step * SIX, r + interval, hum(100, 6), length * SIX - 20))
    return notes


def skank():
    notes = []
    for bar, (root, quality) in enumerate(PROGRESSION):
        for beat in (1, 3):                                    # chord stabs on 2 and 4
            t = bar * 16 * SIX + beat * 4 * SIX
            for n in triad(root, quality):
                notes.append((t, n, hum(85, 5), SIX))
    return notes


def horns():
    # Call (bars 5-6) and response (bars 7-8), A minor pentatonic
    line = [
        (4, 0, "E", 5, 2), (4, 4, "G", 5, 2), (4, 8, "A", 5, 6),
        (5, 4, "G", 5, 2), (5, 6, "E", 5, 2), (5, 8, "D", 5, 4),
        (6, 0, "C", 5, 2), (6, 2, "D", 5, 2), (6, 4, "E", 5, 4), (6, 10, "D", 5, 2), (6, 12, "C", 5, 2),
        (7, 0, "A", 4, 8),
    ]
    notes = []
    for bar, step, name, octv, length in line:
        n = midi_note(name, octv)
        t = bar * 16 * SIX + step * SIX
        notes.append((t, n, hum(96, 5), length * SIX - 30))
        notes.append((t, n - 12, hum(88, 5), length * SIX - 30))  # trombone an octave down
    return notes


PARTS = [  # (name, channel, General MIDI program or None, notes)
    ("Drums", 9, None, drums()),
    ("Bass", 0, 33, bass()),
    ("Skank", 1, 4, skank()),
    ("Horns", 2, 61, horns()),
]


def vlq(n):
    out = [n & 0x7F]
    while n > 0x7F:
        n >>= 7
        out.insert(0, (n & 0x7F) | 0x80)
    return bytes(out)


def track_chunk(name, channel, program, notes, tempo=False):
    events = [(0, 0, b"\xff\x03" + vlq(len(name)) + name.encode())]
    if tempo:
        us = 60_000_000 // BPM
        events.append((0, 0, b"\xff\x51\x03" + us.to_bytes(3, "big")))
        events.append((0, 0, b"\xff\x58\x04\x04\x02\x18\x08"))
    if program is not None:
        events.append((0, 0, bytes([0xC0 | channel, program])))
    for t, n, v, length in notes:
        events.append((t, 2, bytes([0x90 | channel, n, v])))
        events.append((t + max(10, length), 1, bytes([0x80 | channel, n, 0])))
    events.sort(key=lambda e: (e[0], e[1]))
    data, last = b"", 0
    for t, _, msg in events:
        data += vlq(t - last) + msg
        last = t
    data += vlq(0) + b"\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + data


def write(path, parts):
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(parts), PPQ)
    chunks = [track_chunk(*p, tempo=(i == 0)) for i, p in enumerate(parts)]
    path.write_bytes(header + b"".join(chunks))


POSITION_NAMES = ["on the beat", "1st 16th (e)", "8th offbeat (&)", "3rd 16th (a)"]
FEEL_SOURCE = {"Drums": None, "Bass": "kick", "Skank": "snare", "Horns": "snare"}
DRUM_KIND = {36: "kick", 37: "snare", 38: "snare", 42: "hat", 46: "hat"}


def apply_groove(parts, groove):
    """Shift notes by the measured offset for their 16th position; scale velocity by the accent."""
    table = groove["positions"]
    ms_to_ticks = BPM / 60 * PPQ / 1000
    out = []
    for name, channel, program, notes in parts:
        moved = []
        for t, n, v, length in notes:
            kind = DRUM_KIND.get(n, "snare") if name == "Drums" else FEEL_SOURCE[name]
            pos = POSITION_NAMES[(round(t / SIX)) % 4]
            cell = table.get(kind, {}).get(pos)
            if cell:
                ref = max(c["avg_velocity"] for c in table[kind].values())
                t = max(0, t + round(cell["median_offset_ms"] * ms_to_ticks))
                v = max(1, min(127, round(v * (0.75 + 0.25 * cell["avg_velocity"] / ref))))
            moved.append((t, n, v, length))
        out.append((name, channel, program, moved))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    parts, suffix = PARTS, ""
    if "--groove" in sys.argv:
        gpath = Path(sys.argv[sys.argv.index("--groove") + 1])
        args = [a for a in args if a != str(gpath) and a != sys.argv[sys.argv.index("--groove") + 1]]
        parts = apply_groove(PARTS, json.loads(gpath.read_text()))
        suffix = f" (groove from {gpath.parent.name})"
    out = Path(args[0] if args else Path.home() / "Desktop" / "Mixed Roots MIDI")
    out.mkdir(parents=True, exist_ok=True)
    write(out / f"reggae-one-drop-Am-76bpm{suffix} (all parts).mid", parts)
    for part in parts:
        write(out / f"reggae-one-drop-Am-76bpm{suffix} {part[0]}.mid", [part])
    print(f"Wrote {len(parts) + 1} MIDI files to {out}")


if __name__ == "__main__":
    main()
