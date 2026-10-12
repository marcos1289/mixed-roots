#!/usr/bin/env python3
"""Mixed Roots stem studio: split recordings into parts and turn them into Reason material.

    tools/stems/run.sh [input_dir] [output_dir] [--fast] [--only NAME]

For every audio file in input_dir (default band-audio/) this writes
output_dir/<song>/ (default band-stems/) containing:

  stems/     vocals, drums, bass, guitar, keys, horns, other (WAV, same length as the mix)
  midi/      bass, guitar, keys, horns, vocal melody and drums as MIDI at the song's tempo,
             plus all-parts.mid with every part on its own track
  kit/       the cleanest isolated kick, snare and hi-hat hits (one-shots for Kong/Redrum)
  phrases/   horn and vocal phrases cut at the gaps (for a sampler or to chop up)
  groove.json  how the drummer sits against the grid (push/pull per 16th, swing, accents)
  index.html   a mixer page: solo/mute each stem in the browser to judge the separation

Separation runs in stages so each model does the job it is best at:
  1. a dedicated vocal model (Kim Vocal 2; BS-Roformer with --max-quality) pulls vocals off the mix
  2. Demucs v4 6-stem splits the instrumental into drums, bass, guitar, piano, other
  3. a wind-instrument model pulls brass and woodwind out of "other" -> horns
--fast skips 1 and 3 and uses Demucs alone (about 3x quicker, lower quality, no horns stem).
--max-quality swaps in BS-Roformer for vocals: noticeably cleaner, but hours per song on an
Intel CPU, so only worth it overnight or on a rented GPU.
"""
import argparse
import html
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import pretty_midi
import soundfile as sf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
SR = 44100
AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".aiff", ".aif", ".ogg", ".mp4", ".mov"}

VOCAL_MODEL = "Kim_Vocal_2.onnx"                               # fast on a CPU, strong vocal model
VOCAL_MODEL_MAX = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"  # best vocals, ~70x real time on this Mac
SIX_STEM_MODEL = "htdemucs_6s.yaml"
WIND_MODEL = "17_HP-Wind_Inst-UVR.pth"

# stem name -> (General MIDI program, basic-pitch settings)
TRANSCRIBE = {
    "bass": (33, dict(minimum_frequency=30, maximum_frequency=400, onset_threshold=0.55, minimum_note_length=80)),
    "guitar": (27, dict(minimum_frequency=70, maximum_frequency=1500, onset_threshold=0.5, minimum_note_length=60)),
    "keys": (4, dict(minimum_frequency=50, maximum_frequency=2500, onset_threshold=0.5, minimum_note_length=60)),
    "horns": (61, dict(minimum_frequency=80, maximum_frequency=1400, onset_threshold=0.5, minimum_note_length=90)),
    "vocals": (54, dict(minimum_frequency=80, maximum_frequency=1100, onset_threshold=0.6, minimum_note_length=120)),
}
GM_DRUM = {"kick": 36, "snare": 38, "hat": 42}
STEM_ORDER = ["vocals", "drums", "bass", "guitar", "keys", "horns", "other"]
COLORS = {"vocals": "#bf5834", "drums": "#2f6f4f", "bass": "#6b4ea0", "guitar": "#c48a1b",
          "keys": "#2d7fb8", "horns": "#d24f7b", "other": "#7a7a6a", "mix": "#172c24"}

_separators = {}
OVERLAP = 2   # BS-Roformer passes per sample; the library default of 8 is ~4x slower for little gain
SHIFTS = 2    # Demucs random-shift averaging


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- separation

def separator(model, out_dir):
    from audio_separator.separator import Separator
    if model not in _separators:
        # Thresholds 1.0/1e-9 stop the library rescaling each stem, which would break the
        # balance between parts and stop them summing back to the mix.
        sep = Separator(output_dir=str(out_dir), model_file_dir=str(MODELS), output_format="WAV",
                        log_level=40, normalization_threshold=1.0, amplification_threshold=1e-9,
                        mdxc_params={"segment_size": 256, "override_model_segment_size": False,
                                     "batch_size": 1, "overlap": OVERLAP, "pitch_shift": 0},
                        demucs_params={"segment_size": "Default", "shifts": SHIFTS, "overlap": 0.25,
                                       "segments_enabled": True})
        sep.load_model(model_filename=model)
        _separators[model] = sep
    sep = _separators[model]
    sep.output_dir = str(out_dir)
    if getattr(sep, "model_instance", None) is not None:
        sep.model_instance.output_dir = str(out_dir)
    return sep


def split(model, wav, work):
    """Run one model; return {stem label (lowercase): path}."""
    work.mkdir(parents=True, exist_ok=True)
    outputs = separator(model, work).separate(str(wav))
    stems = {}
    for name in outputs:
        p = Path(name)
        if not p.is_absolute():
            p = work / p.name
        label = p.name.split("_(")[-1].split(")")[0].lower()
        stems[label] = p
    return stems


def load(path):
    y, _ = librosa.load(path, sr=SR, mono=False)
    return np.nan_to_num(np.atleast_2d(y))


def fit(y, n):
    if y.shape[1] >= n:
        return y[:, :n]
    return np.pad(y, ((0, 0), (0, n - y.shape[1])))


def separate(mix_path, song_dir, fast):
    work = song_dir / ".work"
    stems_dir = song_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)
    mix = load(mix_path)
    n = mix.shape[1]
    out = {}

    if fast:
        log("  separating (Demucs 6-stem, fast mode)")
        six = split(SIX_STEM_MODEL, mix_path, work / "six")
        out["vocals"] = load(six["vocals"])
        instrumental_parts = six
    else:
        log(f"  1/3 vocals ({VOCAL_MODEL.split('.')[0]})")
        voc = split(VOCAL_MODEL, mix_path, work / "vocal")
        out["vocals"] = load(voc["vocals"])
        inst_path = voc.get("instrumental") or next(p for k, p in voc.items() if k != "vocals")
        log("  2/3 instruments (Demucs 6-stem)")
        instrumental_parts = split(SIX_STEM_MODEL, inst_path, work / "six")

    out["drums"] = load(instrumental_parts["drums"])
    out["bass"] = load(instrumental_parts["bass"])
    out["guitar"] = load(instrumental_parts["guitar"])
    out["keys"] = load(instrumental_parts["piano"])
    other = load(instrumental_parts["other"])
    if not fast:
        # Demucs' own vocal output here is leftover bleed from stage 1; it belongs with "other".
        other = fit(other, n) + fit(load(instrumental_parts["vocals"]), n)
        other_path = work / "other.wav"
        sf.write(other_path, other.T, SR)
        log("  3/3 horns (wind-instrument model)")
        wind = split(WIND_MODEL, other_path, work / "wind")
        horn_key = next((k for k in wind if "wind" in k and not k.startswith("no")), None)
        rest_key = next((k for k in wind if k != horn_key), None)
        out["horns"] = load(wind[horn_key]) if horn_key else np.zeros_like(other)
        out["other"] = load(wind[rest_key]) if rest_key else other
    else:
        out["horns"] = np.zeros_like(other)
        out["other"] = other

    for k in out:
        out[k] = fit(out[k], n)
        sf.write(stems_dir / f"{k}.wav", out[k].T, SR, subtype="PCM_24")
    residual = mix - sum(out.values())
    recon = 1 - float(np.sum(residual ** 2) / max(np.sum(mix ** 2), 1e-9))
    shutil.rmtree(work, ignore_errors=True)
    return out, mix, recon


# ---------------------------------------------------------------- analysis

KRUMHANSL_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KRUMHANSL_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
PITCHES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def detect_key(harmonic_mono):
    chroma = librosa.feature.chroma_cqt(y=harmonic_mono, sr=SR).mean(axis=1)
    best = (-2, "C major")
    for i in range(12):
        for prof, mode in ((KRUMHANSL_MAJ, "major"), (KRUMHANSL_MIN, "minor")):
            r = np.corrcoef(np.roll(prof, i), chroma)[0, 1]
            if r > best[0]:
                best = (r, f"{PITCHES[i]} {mode}")
    return best[1], round(float(best[0]), 2)


def detect_tempo(drums_mono, mix_mono):
    src = drums_mono if np.abs(drums_mono).max() > 1e-3 else mix_mono
    onset_env = librosa.onset.onset_strength(y=src, sr=SR)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=SR, start_bpm=90, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    return round(tempo, 1), beats


# ---------------------------------------------------------------- drums

DRUM_BANDS = {  # kind -> (low Hz, high Hz, detection threshold)
    "kick": (35, 140, 0.18),
    "snare": (180, 2200, 0.22),
    "hat": (6000, 16000, 0.2),
}


def classify_drum_hits(drums_mono):
    """Find kick, snare and hat hits with a separate onset detector per frequency band.

    Comparing one hit's energy across bands fails on phone recordings, where loud cymbals
    swamp the low end; detecting each band on its own envelope doesn't have that problem
    and also catches simultaneous kick + hat hits.
    """
    hop = 256
    S = np.abs(librosa.stft(drums_mono, n_fft=2048, hop_length=hop)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    hits = []
    for kind, (lo, hi, delta) in DRUM_BANDS.items():
        # Flux in linear amplitude, not dB: in dB, quiet leakage (hat hiss in the snare band,
        # bass in the kick band) jumps as much as a real hit does.
        level = S[(freqs >= lo) & (freqs < hi)].sum(axis=0)
        amp = np.sqrt(level)
        env = np.maximum(0, np.diff(amp, prepend=amp[0]))
        env = env / max(np.percentile(env, 99.5), 1e-9)
        frames = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=12, post_avg=12,
                                        delta=delta, wait=int(0.09 * SR / hop))
        for f in frames:
            s = int(f * hop)
            hits.append({"t": s / SR, "kind": kind, "peak": float(level[f:f + 4].max()),
                         "strength": float(env[f])})
    hits.sort(key=lambda h: h["t"])
    # A kick and hat landing together spill enough into the snare band to look like a snare.
    # Compare against the song's strongest snares, not isolated ones: in a one-drop the snare
    # always lands with the kick, so there may be no isolated snare to compare with.
    def coincides(h):
        return any(o is not h and o["kind"] != "snare" and abs(o["t"] - h["t"]) < 0.025 for o in hits)
    strengths = sorted(h["strength"] for h in hits if h["kind"] == "snare")
    if len(strengths) >= 4:
        floor = 0.45 * float(np.median(strengths[len(strengths) // 2:]))
        hits = [h for h in hits if not (h["kind"] == "snare" and h["strength"] < floor and coincides(h))]
    for kind in DRUM_BANDS:
        mine = [h for h in hits if h["kind"] == kind]
        if mine:
            top = max(h["peak"] for h in mine)
            for h in mine:
                h["vel"] = int(np.clip(40 + 87 * (h["peak"] / top) ** 0.35, 1, 127))
    return hits


def cut(y, start, length, fade_out=0.03):
    a, b = int(start * SR), int((start + length) * SR)
    clip = y[:, a:b].copy()
    if clip.shape[1] == 0:
        return clip
    fi, fo = int(0.003 * SR), int(fade_out * SR)
    clip[:, :fi] *= np.linspace(0, 1, min(fi, clip.shape[1]))
    clip[:, -fo:] *= np.linspace(1, 0, min(fo, clip.shape[1]))
    peak = np.abs(clip).max()
    return clip * (0.89 / peak) if peak > 0 else clip


def build_kit(drums, hits, kit_dir, per_kind=4):
    """Keep the loudest hits that have nothing else ringing right after them."""
    kit_dir.mkdir(exist_ok=True)
    times = np.array([h["t"] for h in hits])
    length = {"kick": 0.45, "snare": 0.4, "hat": 0.18}
    written = {}
    for kind in ("kick", "snare", "hat"):
        cands = []
        for h in hits:
            if h["kind"] != kind:
                continue
            clear_after = length[kind] * 0.8
            near = times[(times > h["t"] + 0.002) & (times < h["t"] + clear_after)]
            if len(near) == 0:
                cands.append(h)
        cands.sort(key=lambda h: -h["peak"])
        written[kind] = []
        for i, h in enumerate(cands[:per_kind], 1):
            name = f"{kind}_{i:02d}.wav"
            sf.write(kit_dir / name, cut(drums, max(0, h["t"] - 0.004), length[kind]).T, SR, subtype="PCM_24")
            written[kind].append(name)
    return written


def groove(hits, beats):
    """Push/pull of each 16th position against the beat grid, in ms (positive = behind the beat)."""
    if len(beats) < 4 or not hits:
        return {}
    grid, pos = [], []
    for b0, b1 in zip(beats[:-1], beats[1:]):
        for k in range(4):
            grid.append(b0 + (b1 - b0) * k / 4)
            pos.append(k)
    grid, pos = np.array(grid), np.array(pos)
    sixteenth = float(np.median(np.diff(beats))) / 4
    names = ["on the beat", "1st 16th (e)", "8th offbeat (&)", "3rd 16th (a)"]
    # The beat tracker's grid can sit a few ms off the band. Re-centre it on the median of
    # hits that land on the beat, so offsets describe feel rather than tracker error.
    on_beat = []
    for h in hits:
        i = int(np.argmin(np.abs(grid - h["t"])))
        if pos[i] == 0 and abs(h["t"] - grid[i]) < sixteenth / 2:
            on_beat.append(h["t"] - grid[i])
    grid_shift = float(np.median(on_beat)) if on_beat else 0.0
    grid = grid + grid_shift
    table = {}
    for kind in ("kick", "snare", "hat"):
        rows = {}
        for h in hits:
            if h["kind"] != kind or h["t"] < grid[0] or h["t"] > grid[-1] + sixteenth:
                continue
            i = int(np.argmin(np.abs(grid - h["t"])))
            off = h["t"] - grid[i]
            if abs(off) > sixteenth / 2:
                continue
            rows.setdefault(int(pos[i]), []).append((off * 1000, h["vel"]))
        table[kind] = {names[p]: {"hits": len(v), "median_offset_ms": round(float(np.median([o for o, _ in v])), 1),
                                  "avg_velocity": int(np.mean([vv for _, vv in v]))}
                       for p, v in sorted(rows.items())}
    hat_8ths = [h for h in hits if h["kind"] == "hat"]
    swing = None
    if hat_8ths:
        offs = []
        for h in hat_8ths:
            i = int(np.argmin(np.abs(grid - h["t"])))
            if pos[i] == 2 and abs(h["t"] - grid[i]) < sixteenth / 2:
                offs.append((h["t"] - grid[i]) / sixteenth)
        if offs:
            swing = round(50 + 25 * float(np.median(offs)), 1)
    return {"sixteenth_ms": round(sixteenth * 1000, 1), "grid_shift_ms": round(grid_shift * 1000, 1),
            "swing_percent_on_offbeat_8ths": swing, "positions": table}


# ---------------------------------------------------------------- MIDI

def transcribe(stem_path, settings):
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict
    _, midi, _ = predict(str(stem_path), ICASSP_2022_MODEL_PATH, melodia_trick=True,
                         frame_threshold=0.3, **settings)
    notes = [n for inst in midi.instruments for n in inst.notes]
    return notes


def write_midi(path, tempo, tracks):
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    for name, program, is_drum, notes in tracks:
        inst = pretty_midi.Instrument(program=program, is_drum=is_drum, name=name)
        inst.notes = notes
        pm.instruments.append(inst)
    pm.write(str(path))


def drum_notes(hits):
    return [pretty_midi.Note(velocity=h["vel"], pitch=GM_DRUM[h["kind"]], start=h["t"], end=h["t"] + 0.08)
            for h in hits]


# ---------------------------------------------------------------- phrases

def phrases(y, out_dir, prefix, min_len=1.0, max_len=8.0, keep=8):
    mono = y.mean(axis=0)
    if np.abs(mono).max() < 1e-3:
        return []
    spans = librosa.effects.split(mono, top_db=32, frame_length=2048, hop_length=512)
    found = []
    for a, b in spans:
        dur = (b - a) / SR
        if min_len <= dur <= max_len:
            found.append((float(np.sqrt(np.mean(mono[a:b] ** 2))), a, b))
    found.sort(reverse=True)
    out_dir.mkdir(exist_ok=True)
    names = []
    for i, (_, a, b) in enumerate(sorted(found[:keep], key=lambda x: x[1]), 1):
        name = f"{prefix}_{i:02d}_{a / SR:06.1f}s.wav"
        sf.write(out_dir / name, cut(y, max(0, a / SR - 0.01), (b - a) / SR + 0.05, 0.04).T, SR, subtype="PCM_24")
        names.append(name)
    return names


# ---------------------------------------------------------------- report page

def waveform_png(y, path, color, w=1200, h=56):
    mono = np.abs(y.mean(axis=0))
    if len(mono) == 0:
        mono = np.zeros(w)
    cols = np.array_split(mono, w)
    peaks = np.array([c.max() if len(c) else 0 for c in cols])
    peaks = peaks / max(peaks.max(), 1e-6) if peaks.max() > 0.003 else peaks
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for x, p in enumerate(peaks):
        half = max(1, p * (h / 2 - 1))
        d.line([(x, h / 2 - half), (x, h / 2 + half)], fill=color)
    img.save(path)


def stem_level(y):
    return round(float(20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-9)), 1)


def report_page(song_dir, title, info, stems, mix):
    (song_dir / "wave").mkdir(exist_ok=True)
    rows = []
    for name in ["mix"] + STEM_ORDER:
        y = mix if name == "mix" else stems[name]
        waveform_png(y, song_dir / "wave" / f"{name}.png", COLORS[name])
        src = "mix.wav" if name == "mix" else f"stems/{name}.wav"
        silent = name != "mix" and stem_level(y) < -60
        rows.append(f'''<div class="row{' silent' if silent else ''}" data-stem="{name}">
  <div class="label"><strong>{name}</strong><span>{stem_level(y)} dB{' · nearly silent' if silent else ''}</span></div>
  <button class="mute" title="Mute">M</button><button class="solo" title="Solo">S</button>
  <input class="vol" type="range" min="0" max="1" step="0.01" value="{0 if name == 'mix' else 1}">
  <div class="wave" style="background-image:url('wave/{name}.png')"><div class="head"></div></div>
  <audio preload="auto" src="{src}"></audio>
</div>''')
    midi_links = " ".join(f'<a href="midi/{html.escape(m)}">{html.escape(m)}</a>' for m in info["midi"])
    kit_links = " ".join(f'<a href="kit/{k}">{k}</a>' for ks in info["kit"].values() for k in ks) or "none found"
    phrase_links = " ".join(f'<a href="phrases/{p}">{p}</a>' for p in info["phrases"]) or "none found"
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · stems</title>
<style>
body{{margin:0;font:15px/1.5 system-ui,sans-serif;background:#f4f0e6;color:#172c24}}
header{{padding:20px 24px;background:#172c24;color:#f4f0e6}} header h1{{margin:0;font-size:24px}}
header p{{margin:4px 0 0;opacity:.8}} main{{padding:16px 24px 60px;max-width:1300px}}
.facts{{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 16px}} .facts span{{background:#fff;border-radius:8px;padding:6px 12px}}
.transport{{display:flex;gap:10px;align-items:center;margin-bottom:12px;position:sticky;top:0;background:#f4f0e6;padding:8px 0;z-index:2}}
button{{font:inherit;border:1.5px solid #172c24;background:#fff;border-radius:6px;padding:4px 10px;cursor:pointer}}
#play{{background:#172c24;color:#f4f0e6;padding:6px 18px}} #time{{font-variant-numeric:tabular-nums}}
.row{{display:grid;grid-template-columns:150px 36px 36px 90px 1fr;gap:8px;align-items:center;margin:6px 0}}
.row.silent{{opacity:.45}} .label strong{{display:block;text-transform:capitalize}} .label span{{font-size:12px;opacity:.7}}
.wave{{height:56px;background:#fff center/100% 100% no-repeat;border-radius:6px;position:relative;cursor:pointer}}
.head{{position:absolute;top:0;bottom:0;width:2px;background:#bf5834;left:0}}
button.on{{background:#bf5834;color:#fff;border-color:#bf5834}} h2{{font-size:16px;margin:28px 0 6px}}
.files a{{display:inline-block;margin:2px 10px 2px 0}} code{{background:#fff;padding:1px 5px;border-radius:4px}}
</style></head><body>
<header><h1>{html.escape(title)}</h1><p>Separated stems · solo (S) or mute (M) parts to hear how clean the split is</p></header>
<main>
<div class="facts"><span>Tempo ≈ <b>{info["tempo"]} BPM</b> (or {round(info["tempo"] / 2, 1)} / {round(info["tempo"] * 2, 1)})</span>
<span>Key ≈ <b>{info["key"]}</b> (confidence {info["key_confidence"]})</span><span>Length {info["duration"]}s</span>
<span>Stems account for {info["reconstruction_percent"]}% of the mix energy</span><span>Mode: {info["mode"]}</span></div>
<div class="transport"><button id="play">Play</button><button id="stop">Stop</button><span id="time">0:00</span>
<button id="clear">Clear solo/mute</button></div>
{''.join(rows)}
<h2>MIDI (set Reason's tempo to {info["tempo"]} BPM, then drag in)</h2><p class="files">{midi_links}</p>
<h2>Drum kit one-shots</h2><p class="files">{kit_links}</p>
<h2>Phrases (horns / vocals)</h2><p class="files">{phrase_links}</p>
<h2>Groove</h2><p>Swing on offbeat 8ths: <b>{info["groove"].get("swing_percent_on_offbeat_8ths", "n/a")}%</b> (50 = straight, 66 = triplet swing).
Full push/pull table in <code>groove.json</code>.</p>
</main>
<script>
const rows=[...document.querySelectorAll('.row')], auds=rows.map(r=>r.querySelector('audio'));
const master=auds[0]; let playing=false;
function apply(){{const solo=rows.some(r=>r.querySelector('.solo').classList.contains('on'));
rows.forEach((r,i)=>{{const m=r.querySelector('.mute').classList.contains('on'), s=r.querySelector('.solo').classList.contains('on');
auds[i].volume=(m||(solo&&!s))?0:+r.querySelector('.vol').value;}});}}
rows.forEach(r=>{{r.querySelector('.mute').onclick=e=>{{e.target.classList.toggle('on');apply()}};
r.querySelector('.solo').onclick=e=>{{e.target.classList.toggle('on');apply()}};
r.querySelector('.vol').oninput=apply;
r.querySelector('.wave').onclick=e=>{{const b=e.currentTarget.getBoundingClientRect();seek((e.clientX-b.left)/b.width*master.duration)}};}});
function seek(t){{auds.forEach(a=>a.currentTime=t)}}
document.getElementById('play').onclick=()=>{{playing=!playing;auds.forEach(a=>playing?a.play():a.pause());
document.getElementById('play').textContent=playing?'Pause':'Play'}};
document.getElementById('stop').onclick=()=>{{playing=false;auds.forEach(a=>{{a.pause();a.currentTime=0}});document.getElementById('play').textContent='Play'}};
document.getElementById('clear').onclick=()=>{{document.querySelectorAll('.on').forEach(b=>b.classList.remove('on'));apply()}};
setInterval(()=>{{const t=master.currentTime;document.getElementById('time').textContent=Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0');
document.querySelectorAll('.head').forEach(h=>h.style.left=(t/(master.duration||1)*100)+'%');
if(playing)auds.forEach(a=>{{if(Math.abs(a.currentTime-t)>0.04)a.currentTime=t}});}},120);
apply();
</script></body></html>'''
    (song_dir / "index.html").write_text(page)


def library_page(out_root):
    songs = []
    for d in sorted(p for p in out_root.iterdir() if (p / "info.json").exists()):
        i = json.loads((d / "info.json").read_text())
        songs.append(f'<li><a href="{html.escape(d.name)}/index.html">{html.escape(i["title"])}</a>'
                     f' <span>{i["tempo"]} BPM · {i["key"]} · {i["duration"]}s</span></li>')
    (out_root / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Mixed Roots stems</title>'
        '<style>body{font:16px/1.6 system-ui;background:#f4f0e6;color:#172c24;max-width:800px;margin:40px auto;padding:0 16px}'
        'span{opacity:.7;font-size:14px}a{font-weight:600}</style><h1>Mixed Roots stems</h1><ul>'
        + "".join(songs) + "</ul>")


# ---------------------------------------------------------------- main

def process(src, out_root, fast, reanalyze=False):
    title = src.stem
    song_dir = out_root / title
    song_dir.mkdir(parents=True, exist_ok=True)
    mix_path = song_dir / "mix.wav"
    t0 = time.time()
    log(f"{title}")
    if not (reanalyze and mix_path.exists()):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "2", "-ar", str(SR),
                        str(mix_path)], check=True)
    if reanalyze and all((song_dir / "stems" / f"{k}.wav").exists() for k in STEM_ORDER):
        log("  reusing existing stems")
        mix = load(mix_path)
        stems = {k: fit(load(song_dir / "stems" / f"{k}.wav"), mix.shape[1]) for k in STEM_ORDER}
        recon = 1 - float(np.sum((mix - sum(stems.values())) ** 2) / max(np.sum(mix ** 2), 1e-9))
    else:
        stems, mix, recon = separate(mix_path, song_dir, fast)

    log("  analysing tempo, key and drums")
    drums_mono = stems["drums"].mean(axis=0)
    tempo, beats = detect_tempo(drums_mono, mix.mean(axis=0))
    harmonic = (stems["bass"] + stems["guitar"] + stems["keys"] + stems["horns"] + stems["other"]).mean(axis=0)
    key, key_conf = detect_key(harmonic)
    hits = classify_drum_hits(drums_mono)
    kit = build_kit(stems["drums"], hits, song_dir / "kit")
    groove_info = groove(hits, beats)
    (song_dir / "groove.json").write_text(json.dumps(groove_info, indent=2))

    log("  transcribing to MIDI")
    midi_dir = song_dir / "midi"
    midi_dir.mkdir(exist_ok=True)
    tracks, midi_files = [], []
    mix_db = stem_level(mix)
    for name, (program, settings) in TRANSCRIBE.items():
        # A stem 21 dB under the mix is mostly bleed; transcribing it yields hundreds of junk notes.
        if stem_level(stems[name]) < mix_db - 21:
            continue
        notes = transcribe(song_dir / "stems" / f"{name}.wav", settings)
        if not notes:
            continue
        label = "vocal melody" if name == "vocals" else name
        tracks.append((label, program, False, notes))
        fn = f"{title} - {label} - {tempo}bpm.mid"
        write_midi(midi_dir / fn, tempo, [tracks[-1]])
        midi_files.append(fn)
    if hits:
        tracks.insert(0, ("drums", 0, True, drum_notes(hits)))
        fn = f"{title} - drums - {tempo}bpm.mid"
        write_midi(midi_dir / fn, tempo, [tracks[0]])
        midi_files.insert(0, fn)
    if tracks:
        fn = f"{title} - all parts - {tempo}bpm.mid"
        write_midi(midi_dir / fn, tempo, tracks)
        midi_files.insert(0, fn)

    log("  cutting phrases and building the page")
    phrase_files = phrases(stems["horns"], song_dir / "phrases", "horns") + \
        phrases(stems["vocals"], song_dir / "phrases", "vocals")
    info = {
        "title": title, "source": str(src), "mode": "fast" if fast else "best",
        "duration": round(mix.shape[1] / SR, 1), "tempo": tempo, "key": key, "key_confidence": key_conf,
        "reconstruction_percent": round(recon * 100, 1),
        "stem_levels_db": {k: stem_level(v) for k, v in stems.items()},
        "drum_hits": {k: sum(1 for h in hits if h["kind"] == k) for k in ("kick", "snare", "hat")},
        "midi": midi_files, "kit": kit, "phrases": phrase_files, "groove": groove_info,
        "seconds_to_process": round(time.time() - t0),
    }
    (song_dir / "info.json").write_text(json.dumps(info, indent=2))
    report_page(song_dir, title, info, stems, mix)
    log(f"  done in {info['seconds_to_process']}s -> {song_dir / 'index.html'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", default=str(ROOT.parent.parent / "band-audio"))
    ap.add_argument("output", nargs="?", default=str(ROOT.parent.parent / "band-stems"))
    ap.add_argument("--fast", action="store_true", help="Demucs only: quicker, lower quality, no horns stem")
    ap.add_argument("--max-quality", action="store_true", help="slowest, squeezes out the last bit of separation quality")
    ap.add_argument("--only", help="process only files whose name contains this text")
    ap.add_argument("--redo", action="store_true", help="reprocess songs that already have results")
    ap.add_argument("--reanalyze", action="store_true",
                    help="keep existing stems, redo tempo/key/drums/MIDI/kit/groove (fast)")
    a = ap.parse_args()
    global OVERLAP, SHIFTS, VOCAL_MODEL
    if a.fast:
        SHIFTS = 1
    if a.max_quality:
        OVERLAP, SHIFTS, VOCAL_MODEL = 4, 4, VOCAL_MODEL_MAX
    src_dir, out_root = Path(a.input), Path(a.output)
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in AUDIO_EXT)
    if a.only:
        files = [p for p in files if a.only.lower() in p.name.lower()]
    if not files:
        sys.exit(f"No audio files in {src_dir}")
    out_root.mkdir(parents=True, exist_ok=True)
    for f in files:
        if not (a.redo or a.reanalyze) and (out_root / f.stem / "info.json").exists():
            log(f"{f.stem}: already done (use --redo to reprocess)")
            continue
        process(f, out_root, a.fast, a.reanalyze)
        library_page(out_root)
    library_page(out_root)
    log(f"All done. Open {out_root / 'index.html'}")


if __name__ == "__main__":
    main()
