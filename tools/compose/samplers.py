"""Sample instruments built from the band's own separated recordings.

tools/stems leaves, for each recording, a stem per instrument plus a MIDI transcription of
it. That transcription says where every real note starts and what pitch it is, so we can
cut those notes out and play new music with them.

  NoteSampler   monophonic parts (bass, horns): one clip per pitch, each confirmed with a
                pitch tracker, re-pitched to the nearest new note like a hardware sampler.
  StabSampler   chordal parts (skank guitar, keys): whole chord stabs, sorted by major or
                minor, shifted to the new chord's root.
"""
from pathlib import Path

import librosa
import numpy as np
import pretty_midi
import soundfile as sf

SR = 44100
MAJOR, MINOR = {0, 4, 7}, {0, 3, 7}


def _mono(path):
    y, sr = sf.read(path)
    y = y.mean(axis=1) if y.ndim > 1 else y
    return librosa.resample(y, orig_sr=sr, target_sr=SR) if sr != SR else y


def _midi_notes(path):
    pm = pretty_midi.PrettyMIDI(str(path))
    return sorted((n for i in pm.instruments for n in i.notes), key=lambda n: n.start)


def _shift(clip, semitones):
    """Re-pitch by resampling (what a sampler does: higher notes also get shorter)."""
    if abs(semitones) < 1e-3:
        return clip
    ratio = 2 ** (semitones / 12)
    idx = np.arange(0, len(clip) - 1, ratio)
    return np.interp(idx, np.arange(len(clip)), clip)


def _fit(clip, seconds, release=0.04, stretch_ok=False):
    want = int(seconds * SR)
    if len(clip) < want and stretch_ok:
        attack = min(int(0.08 * SR), len(clip) // 3)
        body = clip[attack:]
        if len(body) > 2048:
            rate = len(body) / max(want - attack, 1)
            body = librosa.effects.time_stretch(body, rate=max(rate, 0.25))
        clip = np.concatenate([clip[:attack], body])
    clip = clip[:want + int(release * SR)].copy()
    r = min(int(release * SR), len(clip))
    clip[-r:] *= np.linspace(1, 0, r)
    f = min(int(0.003 * SR), len(clip))
    clip[:f] *= np.linspace(0, 1, f)
    return clip


def _usable(stem, mix_db, margin=21):
    y = _mono(stem)
    level = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-9)
    return level >= mix_db - margin


class NoteSampler:
    def __init__(self, name):
        self.name = name
        self.samples = {}   # midi pitch -> (clip, score, source)

    def harvest(self, stem_wav, midi_file, min_dur=0.15, max_len=1.6):
        y = _mono(stem_wav)
        notes = _midi_notes(midi_file)
        starts = np.array([n.start for n in notes])
        peak = np.abs(y).max() + 1e-9
        for n in notes:
            dur = n.end - n.start
            if dur < min_dur:
                continue
            # monophonic: nothing else may start while this note sounds
            if np.any((starts > n.start + 0.02) & (starts < n.end)):
                continue
            a = max(0, int((n.start - 0.005) * SR))
            b = min(len(y), int((n.start + min(dur + 0.12, max_len)) * SR))
            clip = y[a:b]
            if len(clip) < int(0.1 * SR):
                continue
            f0, voiced, _ = librosa.pyin(clip, fmin=35, fmax=1400, sr=SR, frame_length=2048)
            f0 = f0[voiced] if voiced.any() else np.array([])
            if len(f0) < 3:
                continue
            measured = librosa.hz_to_midi(np.median(f0))
            if abs(measured - n.pitch) > 0.6:
                continue                       # transcription and pitch tracker disagree
            score = np.sqrt(np.mean(clip ** 2)) / peak * min(dur, 0.8) * voiced.mean()
            have = self.samples.get(n.pitch)
            if have is None or score > have[1]:
                self.samples[n.pitch] = (clip / (np.abs(clip).max() + 1e-9), score, Path(stem_wav).parent.parent.name)
        return self

    def __len__(self):
        return len(self.samples)

    def play(self, pitch, seconds, vel, sustain=False):
        if not self.samples:
            return None
        nearest = min(self.samples, key=lambda p: (abs(p - pitch), p < pitch))
        clip = _shift(self.samples[nearest][0], pitch - nearest)
        return _fit(clip, seconds, stretch_ok=sustain) * (vel / 127)


class StabSampler:
    def __init__(self, name):
        self.name = name
        self.stabs = {"major": [], "minor": []}   # (root pitch class, clip, score)

    def harvest(self, stem_wav, midi_file, max_len=0.45):
        y = _mono(stem_wav)
        notes = _midi_notes(midi_file)
        groups, cur = [], []
        for n in notes:
            if cur and n.start - cur[0].start > 0.03:
                groups.append(cur)
                cur = []
            cur.append(n)
        if cur:
            groups.append(cur)
        onsets = [g[0].start for g in groups]
        peak = np.abs(y).max() + 1e-9
        for i, g in enumerate(groups):
            pcs = {n.pitch % 12 for n in g}
            if len(pcs) < 2:
                continue
            best = None
            for root in range(12):
                rel = {(p - root) % 12 for p in pcs}
                for quality, tmpl in (("major", MAJOR), ("minor", MINOR)):
                    fit = len(rel & tmpl) - len(rel - tmpl)
                    if 0 in rel and fit >= 2 and (best is None or fit > best[0]):
                        best = (fit, root, quality)
            if not best:
                continue
            nxt = onsets[i + 1] if i + 1 < len(onsets) else g[0].start + max_len
            end = min(g[0].start + max_len, nxt - 0.01)
            a, b = max(0, int((g[0].start - 0.005) * SR)), int(end * SR)
            clip = y[a:b]
            if len(clip) < int(0.08 * SR):
                continue
            score = np.sqrt(np.mean(clip ** 2)) / peak * best[0]
            self.stabs[best[2]].append((best[1], clip / (np.abs(clip).max() + 1e-9), score))
        for q in self.stabs:
            self.stabs[q] = sorted(self.stabs[q], key=lambda s: -s[2])[:8]
        return self

    def __len__(self):
        return sum(len(v) for v in self.stabs.values())

    def play(self, root_pc, quality, seconds, vel, variant=0):
        pool = self.stabs.get(quality) or self.stabs["major"] or self.stabs["minor"]
        if not pool:
            return None
        src_root, clip, _ = pool[variant % min(len(pool), 3)]
        semis = ((root_pc - src_root + 6) % 12) - 6     # shift by at most a tritone
        return _fit(_shift(clip, semis), seconds, release=0.03) * (vel / 127)


def build(repo, plan):
    """plan: {part: [(song folder, stem name, sampler kind)]} -> {part: sampler or None}

    Harvesting runs a pitch tracker over every candidate note (minutes on a CPU), so the result
    is cached and reused until a source stem or transcription changes."""
    import hashlib
    import pickle
    stamp = hashlib.sha256(repr(sorted(
        (str(f), f.stat().st_mtime) for part in plan.values() for song, stem, _ in part
        for f in [Path(repo) / "band-stems" / song / "stems" / f"{stem}.wav"] if f.exists())).encode()).hexdigest()
    cache = Path(repo) / "band-stems" / ".sampler-cache.pkl"
    if cache.exists():
        saved = pickle.loads(cache.read_bytes())
        if saved.get("stamp") == stamp:
            return saved["samplers"]
    out = {}
    for part, sources in plan.items():
        kind = sources[0][2]
        sampler = NoteSampler(part) if kind == "note" else StabSampler(part)
        for song, stem, _ in sources:
            d = Path(repo) / "band-stems" / song
            info = __import__("json").loads((d / "info.json").read_text())
            mix_db = 20 * np.log10(np.sqrt(np.mean(_mono(d / "mix.wav") ** 2)) + 1e-9)
            wav = d / "stems" / f"{stem}.wav"
            midi = next(iter(sorted((d / "midi").glob(f"* - {'vocal melody' if stem == 'vocals' else stem} - *.mid"))), None)
            if midi is None or not _usable(wav, mix_db):
                continue
            sampler.harvest(wav, midi)
        out[part] = sampler if len(sampler) else None
    cache.write_bytes(pickle.dumps({"stamp": stamp, "samplers": out}))
    return out
