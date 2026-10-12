#!/usr/bin/env python3
"""Publish band-stems/ to a hidden, password-protected page on the live site.

    tools/stems/.venv/bin/python tools/stems/publish_private.py

The site is served from a public GitHub repo, so a login screen alone would hide the
page but not the files. Every file here is encrypted with AES-256-GCM using a key derived
from the password (PBKDF2-SHA256); the browser decrypts after login. The ciphertext is
public, the content isn't.

The password is read from .studio-password at the repo root (gitignored; created with a
random passphrase on first run). Change it by editing that file and re-running. The page
lives at docs/<slug>/ where the slug, from tools/stems/private_studio.json, is unlisted
(that file also holds the PBKDF2 salt and a key fingerprint, neither of them secret);
"titles" there maps song folder names to display names.
"""
import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

REPO = Path(__file__).resolve().parents[2]
STEMS = REPO / "band-stems"
CONFIG = Path(__file__).with_name("private_studio.json")
PASSWORD_FILE = REPO / ".studio-password"
PAGE = Path(__file__).with_name("private_studio.html")
ITERATIONS = 600_000
STEM_ORDER = ["vocals", "drums", "bass", "guitar", "keys", "horns", "other"]
WORDS = ("mango palm drum horn bass skank riddim groove sunset harbor lark river ginger cocoa "
         "rhythm echo dub roots summit cedar maple violet ember tide").split()


def password():
    if not PASSWORD_FILE.exists():
        pw = "-".join(secrets.choice(WORDS) for _ in range(4)) + "-" + str(secrets.randbelow(90) + 10)
        PASSWORD_FILE.write_text(pw + "\n")
        os.chmod(PASSWORD_FILE, 0o600)
    return PASSWORD_FILE.read_text().strip()


def config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text())
    cfg = {"slug": "studio-" + secrets.token_hex(5)}
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    return cfg


def encode_aac(src, dest, kbps=192):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-c:a", "aac", "-b:a", f"{kbps}k",
                    "-movflags", "+faststart", str(dest)], check=True)


def main():
    cfg = config()
    out = REPO / "docs" / cfg["slug"]
    if "salt" not in cfg:
        cfg["salt"] = base64.b64encode(secrets.token_bytes(16)).decode()
    salt = base64.b64decode(cfg["salt"])
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, ITERATIONS).derive(password().encode())
    key_check = hashlib.sha256(key).hexdigest()[:16]
    if cfg.get("key_check") != key_check and out.exists():
        shutil.rmtree(out)          # password changed: nothing old can be decrypted any more
    cfg["key_check"] = key_check
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
    (out / "f").mkdir(parents=True, exist_ok=True)
    aes = AESGCM(key)
    written = set()
    tmp = REPO / "band-stems" / ".publish-tmp"
    tmp.mkdir(exist_ok=True)

    def seal(data, mime):
        """Encrypt bytes to an opaque file; return the reference the page needs."""
        # Named by content so a republish reuses unchanged files instead of re-uploading them.
        name = hashlib.sha256(key + data).hexdigest()[:20]
        if not (out / "f" / name).exists():
            nonce = secrets.token_bytes(12)
            (out / "f" / name).write_bytes(nonce + aes.encrypt(nonce, data, None))
        written.add(name)
        return {"id": name, "type": mime, "bytes": len(data)}

    batch_nums = sorted({int(p.name.split()[1]) for p in STEMS.iterdir() if p.name.startswith("Batch ")})
    recent_batches = set(batch_nums[-2:])
    songs = []
    for d in sorted((p for p in STEMS.iterdir() if (p / "info.json").exists()),
                    key=lambda p: (not p.name.startswith("Batch"), p.name), reverse=False):
        info = json.loads((d / "info.json").read_text())
        generated = d.name.startswith("Batch ")
        if generated and int(d.name.split()[1]) not in recent_batches:
            continue                    # older batches: their hooks stay on Compare, full songs retire
        print("sealing", info["title"])
        tracks = []
        # generated variants publish the mix and vocal only; all 8 stems per variant would add
        # ~25 MB to the repo per song, every batch
        for name in ["mix", "vocals"] if generated else ["mix"] + STEM_ORDER:
            src = d / ("mix.wav" if name == "mix" else f"stems/{name}.wav")
            m4a = tmp / f"{name}.m4a"
            encode_aac(src, m4a)
            tracks.append({"name": name, "level": info["stem_levels_db"].get(name),
                           "audio": seal(m4a.read_bytes(), "audio/mp4"),
                           "wave": seal((d / "wave" / f"{name}.png").read_bytes(), "image/png")})
        downloads = []
        for f in sorted((d / "midi").glob("*.mid")):
            downloads.append({"group": "MIDI", "name": f.name, **seal(f.read_bytes(), "audio/midi")})
        for f in sorted((d / "kit").glob("*.wav")):
            downloads.append({"group": "Drum hits", "name": f.name, **seal(f.read_bytes(), "audio/wav")})
        for f in sorted((d / "phrases").glob("*.wav")):
            m4a = tmp / (f.stem + ".m4a")
            encode_aac(f, m4a, 256)
            downloads.append({"group": "Phrases", "name": m4a.name, **seal(m4a.read_bytes(), "audio/mp4")})
        for f in sorted((d / "sheet").glob("*")):
            downloads.insert(0, {"group": "Song sheet", "name": f.name, **seal(f.read_bytes(), "text/markdown")})
        downloads.append({"group": "Groove", "name": "groove.json",
                          **seal((d / "groove.json").read_bytes(), "application/json")})
        songs.append({"title": cfg.get("titles", {}).get(info["title"], info["title"]), "tempo": info["tempo"], "key": info["key"],
                      "duration": info["duration"], "reconstruction": info["reconstruction_percent"],
                      "swing": info["groove"].get("swing_percent_on_offbeat_8ths"),
                      "tracks": tracks, "downloads": downloads})
    shutil.rmtree(tmp, ignore_errors=True)

    batches = []
    for bf in sorted((STEMS / "_batches").glob("batch-*.json")) if (STEMS / "_batches").exists() else []:
        batch = json.loads(bf.read_text())
        variants = []
        for v in batch["variants"]:
            hook = STEMS / v["folder"] / "hook.wav"
            if not hook.exists():
                continue
            m4a = tmp / f"hook-{v['folder']}.m4a"
            tmp.mkdir(exist_ok=True)
            encode_aac(hook, m4a)
            p = v["params"]
            variants.append({"id": v["id"], "folder": v["folder"], "hook": seal(m4a.read_bytes(), "audio/mp4"),
                             "summary": f"{p['groove']} · {p['tempo']} BPM · {p['key']} · horns {p['horns']}"
                                        f" · {p['perc']} perc · {p['bridge']} bridge · keys {p.get('keys', 'band')}"})
        if len(variants) >= 2:
            ids = {v["id"] for v in variants}
            batches.append({"id": batch["id"], "created": batch["created"], "variants": variants,
                            "pairs": [pr for pr in batch["pairs"] if set(pr) <= ids]})
    shutil.rmtree(tmp, ignore_errors=True)
    manifest = json.dumps({"songs": songs, "batches": batches,
                           "repo": "marcos1289/mixed-roots"}).encode()
    nonce = secrets.token_bytes(12)
    (out / "manifest.bin").write_bytes(nonce + aes.encrypt(nonce, manifest, None))
    for f in (out / "f").iterdir():
        if f.name not in written:
            f.unlink()
    params = {"salt": cfg["salt"], "iterations": ITERATIONS}
    (out / "index.html").write_text(PAGE.read_text().replace("__PARAMS__", json.dumps(params)))
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"Published {len(songs)} songs to docs/{cfg['slug']}/ ({total / 1e6:.1f} MB encrypted)")
    print(f"URL: https://www.mixedrootsnewyork.com/{cfg['slug']}/")


if __name__ == "__main__":
    main()
