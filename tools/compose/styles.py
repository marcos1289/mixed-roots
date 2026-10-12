"""Roots reggae / dub / afrobeat playing patterns for compose.py.

Encoded from research_notes/Reggae afrobeat style guide/ (roots_reggae_dub.md,
ska_rocksteady.md, afrobeat_fusion.md). Most grids there are practitioner conventions,
not transcriptions of specific records, so treat them as defaults to tune by ear.

Grids use 16 steps per bar: step 1 = beat 1, 5 = beat 2, 9 = beat 3, 13 = beat 4.
Times returned are in beats from the bar start (step s -> (s - 1) / 4).

Rules that keep it reggae rather than Latin (the "mariachi" test):
  - horns in unison/octaves, straight tone, short riffs; no parallel thirds
  - modal vamps (i-bVII, i-IV, bVI-bVII-i); no major V / leading tone
  - bass riffs with space that skip beat 1; no root-fifth on 1 and 3
  - swung/triplet hats in one-drop sections; snare/rim on 3, never a 2-and-4 backbeat
"""

DRUM = {"kick": 36, "rim": 37, "snare": 38, "hat": 42, "open": 46, "tom_hi": 48, "tom_lo": 45,
        "crash": 49, "shaker": 70, "conga_hi": 63, "conga_lo": 64, "slap": 62}


def at(step):
    return (step - 1) / 4


# kind -> list of (step, velocity)
DRUM_GRIDS = {
    "onedrop": {
        "kick": [(9, 110)], "rim": [(9, 104), (15, 38)],
        "hat": [(1, 78), (3, 62), (5, 80), (7, 62), (9, 84), (11, 62), (13, 80), (15, 62)],
    },
    "rockers": {
        "kick": [(1, 108), (8, 82), (9, 108)], "rim": [(9, 104)],
        "hat": [(s, 80 if s % 4 == 1 else 64) for s in range(1, 17, 2)],
    },
    "steppers": {
        "kick": [(1, 100), (5, 98), (9, 102), (13, 98)], "rim": [(9, 104)],
        "hat": [(s, 80 if s % 4 == 1 else 62) for s in range(1, 17, 2)],
    },
    # one drop with afrobeat hi-hat language (afrobeat_fusion.md F1)
    "afro_onedrop": {
        "kick": [(9, 110)], "rim": [(9, 104)],
        "hat": [(1, 80), (3, 60), (4, 52), (5, 78), (9, 82), (11, 60), (12, 52), (13, 78)],
        "open": [(7, 74), (15, 76)],
    },
    # rockers with Tony Allen-style hats and ghost snares (F2 / D2)
    "afro_rockers": {
        "kick": [(1, 106), (5, 92), (9, 106), (11, 84), (12, 80), (13, 92)],
        "snare": [(8, 40), (12, 40), (16, 36)], "rim": [(9, 100)],
        "hat": [(1, 82), (2, 50), (4, 54), (5, 80), (6, 50), (8, 54), (9, 82), (10, 50), (12, 54),
                (13, 80), (14, 50), (16, 54)],
        "open": [(3, 76), (7, 78), (11, 76), (15, 80)],
    },
}

# Swing for the 8th-note offbeat (50 = straight, 66 = triplet). The bubble sets the feel.
SWING = {"onedrop": 63, "rockers": 56, "steppers": 52, "afro_onedrop": 60, "afro_rockers": 52}


def drums(style, bar, phrase_end=False, end=False):
    """[(beat, drum note, velocity)] for one bar."""
    out = []
    if end:
        return [(0, DRUM["kick"], 112), (0, DRUM["rim"], 100), (0, DRUM["crash"], 96)]
    grid = DRUM_GRIDS[style]
    for kind, hits in grid.items():
        for step, vel in hits:
            if phrase_end and step >= 13 and kind in ("hat", "open"):
                continue
            out.append((at(step), DRUM[kind], vel))
    if style in ("onedrop", "afro_onedrop") and bar % 2 == 1 and not phrase_end:
        out = [h for h in out if not (h[1] == DRUM["hat"] and abs(h[0] - at(15)) < 1e-6)]
        out.append((at(15), DRUM["open"], 72))          # open hat on the & of 4 every other bar
    if phrase_end:                                        # short fill landing back on beat 3
        out += [(at(13), DRUM["rim"], 92), (at(14), DRUM["tom_hi"], 86), (at(15), DRUM["tom_hi"], 80),
                (at(16), DRUM["tom_lo"], 96)]
    return out


# Bass riffs: 2 bars, (step, scale degree in semitones above the chord root, length in 16ths,
# velocity). Degrees use 3 for the chord's third; it becomes 4 over a major chord.
# Register is set by the caller (root around D2/C2/Bb1).
BASS_RIFFS = {
    # one-drop, drop-one riff (roots_reggae_dub.md pattern 1)
    "onedrop": [
        [(3, 0, 2, 100), (5, 3, 2, 92), (7, 5, 1, 86), (9, 7, 3, 104), (13, -2, 2, 90), (15, 0, 1, 84)],
        [(3, 0, 2, 100), (6, 0, 1, 70), (7, 3, 2, 92), (9, 5, 2, 98), (11, 3, 2, 88), (13, 0, 4, 100)],
    ],
    # space-heavy meditative line (pattern 2) for intros and dub breaks
    "space": [
        [(9, 0, 4, 106), (15, -2, 1, 80), (16, 0, 1, 88)],
        [(5, -5, 2, 92), (9, 0, 3, 104), (12, 3, 1, 80), (13, 5, 3, 94)],
    ],
    # rockers (pattern 3): more notes, hits beat 1
    "rockers": [
        [(1, 0, 2, 104), (4, 0, 1, 80), (5, 3, 1, 88), (7, 7, 2, 94), (9, 0, 2, 102), (11, -2, 1, 84),
         (12, -5, 2, 90), (15, -2, 1, 82)],
        [(1, 0, 2, 104), (4, 12, 1, 82), (5, 10, 1, 84), (7, 7, 2, 92), (9, 5, 2, 96), (11, 3, 2, 88),
         (13, 0, 3, 100)],
    ],
    # afrobeat ostinato (afrobeat_fusion.md B1/B2): octave + dorian colour
    "afro": [
        [(1, 0, 2, 100), (4, 12, 1, 86), (7, 10, 1, 90), (8, 7, 1, 84), (11, 5, 2, 92), (13, 7, 2, 96)],
        [(3, 0, 2, 98), (4, 3, 1, 84), (7, 5, 1, 88), (9, 9, 2, 94), (11, 7, 2, 90), (15, 5, 1, 82),
         (16, 3, 1, 78)],
    ],
}
BASS_FOR_DRUMS = {"onedrop": "onedrop", "rockers": "rockers", "steppers": "rockers",
                  "afro_onedrop": "onedrop", "afro_rockers": "afro"}


def bass(riff, bar, root_midi, major):
    out = []
    for step, deg, length, vel in BASS_RIFFS[riff][bar % 2]:
        if deg == 3 and major:
            deg = 4
        if deg == 9 and not major and riff != "afro":
            deg = 8
        out.append((at(step), root_midi + deg, length / 4 * 0.75, vel))   # short, "thuddy" notes
    return out


def skank(voicing, double=False):
    """Chop on beats 2 and 4 (steps 5 and 13), one 16th long."""
    out = []
    for step, vel in ((5, 90), (13, 92)):
        for n in voicing:
            out.append((at(step), n, 0.22, vel))
        if double:
            for n in voicing:
                out.append((at(step + 1), n, 0.18, 62))
    return out


def bubble(low_voicing, high_voicing):
    """Organ bubble: left hand on every upbeat with a softer second note after it ('bub-ble');
    right hand doubles the skank on 2 and 4."""
    out = []
    for step in (3, 7, 11, 15):
        for n in low_voicing:
            out.append((at(step), n, 0.2, 66))
        out.append((at(step + 1), low_voicing[0] - 12, 0.15, 50))
    for step in (5, 13):
        for n in high_voicing:
            out.append((at(step), n, 0.2, 70))
    return out


def tenor_guitar(root_midi):
    """Afrobeat muted single-note tenor guitar line (G1), interlocking with the chank."""
    line = [(1, 7, 90), (3, 7, 60), (4, 10, 95), (6, 12, 90), (8, 7, 70), (10, 7, 60), (11, 10, 95),
            (13, 5, 85), (15, 7, 70)]
    return [(at(s), root_midi + d, 0.12, v) for s, d, v in line]


def percussion(style):
    out = []
    if style in ("shekere", "afro"):
        for s in range(1, 17):
            out.append((at(s), DRUM["shaker"], 86 if s in (3, 7, 11, 15) else (60 if s % 2 else 34)))
    if style == "afro":
        conga = [(1, "conga_hi", 70), (3, "slap", 88), (5, "conga_hi", 70), (7, "conga_hi", 84),
                 (8, "conga_hi", 80), (9, "conga_hi", 70), (11, "slap", 88), (12, "conga_lo", 90),
                 (13, "conga_hi", 70), (15, "conga_hi", 82)]
        out += [(at(s), DRUM[k], v) for s, k, v in conga]
    return out


# ---------------------------------------------------------------- SoCal / Slightly Stoopid
# socal_slightly_stoopid.md grid B: kick 1, &2, 3, &4; snare backbeat on 2 and 4; straight 16th
# hats with ghosts. Their records sit at 82-100 BPM (2am 82, Collie Man 85, Officer 95).
DRUM_GRIDS["stoopid"] = {
    "kick": [(1, 108), (7, 88), (9, 104), (15, 86)],
    "snare": [(5, 104), (13, 106)], "rim": [(9, 36)],
    "hat": [(s, 84 if s % 4 == 1 else (70 if s % 2 else 40)) for s in range(1, 17)],
}
# Marley-hit style: kick on every beat with the rim on 3 and busy 16th hats ("Is This Love",
# "Jamming", "Buffalo Soldier" feel)
DRUM_GRIDS["marley_four"] = {
    "kick": [(1, 100), (5, 96), (9, 102), (13, 96)], "rim": [(9, 100), (16, 36)],
    "hat": [(s, 80 if s % 4 == 1 else (64 if s % 2 else 42)) for s in range(1, 17)],
}
SWING.update({"stoopid": 50, "marley_four": 54})
BASS_FOR_DRUMS.update({"stoopid": "stoopid", "marley_four": "rockers"})
# busier melodic riff that lands on beat 1 with the kick
BASS_RIFFS["stoopid"] = [
    [(1, 0, 2, 106), (4, 0, 1, 80), (5, 7, 1, 88), (7, 0, 2, 96), (9, 12, 1, 92), (10, 10, 1, 82),
     (11, 7, 2, 90), (13, 5, 1, 86), (15, 3, 2, 90)],
    [(1, 0, 2, 106), (4, 0, 1, 80), (5, 7, 1, 88), (7, 0, 2, 96), (9, 5, 2, 96), (11, 7, 1, 88),
     (12, 10, 1, 84), (13, 12, 2, 98), (15, 7, 1, 84)],
]

# Chord loops by scale degree (roman numerals resolved in evolve.py against the key).
PROGRESSIONS = {
    "minor": [["i", "i", "bVII", "bVII"], ["i", "iv", "i", "iv"], ["bVI", "bVII", "i", "i"],
              ["i", "IV", "i", "IV"], ["i", "bVII", "bVI", "bVII"]],
    "major": [["I", "IV", "I", "IV"], ["I", "bVII", "IV", "I"], ["I", "V", "vi", "IV"],
              ["I", "I", "IV", "IV"], ["IV", "V", "I", "I"]],
}
NUMERALS = {"i": (0, "m"), "I": (0, ""), "ii": (2, "m"), "iv": (5, "m"), "IV": (5, ""), "V": (7, ""),
            "v": (7, "m"), "vi": (9, "m"), "bVI": (8, ""), "bVII": (10, ""), "bIII": (3, "")}

# Horn riffs as (start step within the 2-bar riff, scale degree index (0 = tonic, 7 = octave),
# length in 16ths). Unison/octave only; written for the 2nd bar of a 2-bar phrase where noted.
HORN_RIFFS = {
    "pent_call": [(3, 4, 1), (4, 6, 1), (5, 7, 2), (9, 6, 1), (10, 4, 1), (13, 3, 2), (21, 4, 2),
                  (23, 3, 2), (25, 4, 6)],
    "answer": [(19, 4, 1), (20, 5, 2), (22, 4, 2), (24, 3, 3), (27, 2, 1), (28, 3, 1), (29, 0, 2)],
    "stab": [(7, 7, 1), (11, 7, 1), (23, 6, 1), (27, 7, 2)],
    "afro": [(1, 7, 2), (3, 7, 1), (4, 6, 3), (7, 4, 2), (9, 3, 2), (11, 4, 6), (19, 2, 1), (20, 3, 1),
             (21, 4, 6), (29, 6, 2), (31, 7, 1)],
}
