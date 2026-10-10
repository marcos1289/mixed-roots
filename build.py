#!/usr/bin/env python3
"""Build the Mixed Roots site into docs/ (served by GitHub Pages).

    python3 build.py

Content lives in content/*.json (edited by hand or through the /admin page),
page templates and styles in src/. Photos named "uploads/<file>" live in
content/photos/ (added through the admin page); all others come from
recovery/media/photos. Every photo is resized, re-encoded and
stripped of metadata (phone photos can carry GPS coordinates). Videos are
re-encoded with ffmpeg. Both are cached, so re-runs only redo new files.
"""
import datetime
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
PHOTOS = ROOT / "recovery/media/photos"
UPLOADS = ROOT / "content/photos"
VIDEOS = ROOT / "recovery/media/video"
SRC = ROOT / "src"
DOMAIN = "www.mixedrootsnewyork.com"
WIDTHS = (640, 1600)
WRITTEN = set()

VIDEO_INFO = {
    "troy_night_out_-_mixed_roots_502": "Troy Night Out, June 2025",
    "p83_349": "Mixed Roots: AfroBeat and reggae",
    "p86_414": "Live clip",
}

e = html.escape


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", Path(name).name.lower()).strip("-")


def photo_source(name):
    if name.startswith("uploads/"):
        return UPLOADS / name.removeprefix("uploads/")
    return PHOTOS / name.replace("background-images/", "backgrounds/")


def photo(name, widths=WIDTHS):
    """Resize one photo to each of widths; return its metadata."""
    with Image.open(photo_source(name)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        w, h = im.size
        out = {}
        for target in widths:
            tw = min(target, w)
            dest = OUT / "img" / f"{slug(name)}-{target}.jpg"
            if not dest.exists():
                im.resize((tw, round(h * tw / w)), Image.LANCZOS).save(
                    dest, "JPEG", quality=80, optimize=True, progressive=True)
            WRITTEN.add(dest.name)
            out[target] = (f"img/{dest.name}", tw)
    if 1600 not in out:
        return {"small": out[640][0]}
    return {"small": out[640][0], "large": out[1600][0], "w": w, "h": h,
            "srcset": f"{out[640][0]} {out[640][1]}w, {out[1600][0]} {out[1600][1]}w"}


def safe_url(url):
    if not re.match(r"(https?://|mailto:)", url or ""):
        raise SystemExit(f"Refusing link that isn't http(s) or mailto: {url!r}")
    return e(url)


def ext_link(label, url, arrow=""):
    return f'<a href="{safe_url(url)}" target="_blank" rel="noopener">{e(label)}{arrow}</a>'


def img_tag(p, alt, sizes, cls="", lazy=True):
    return (f'<img src="{p["small"]}" srcset="{p["srcset"]}" sizes="{sizes}" '
            f'width="{p["w"]}" height="{p["h"]}" alt="{e(alt)}"'
            + (' loading="lazy"' if lazy else '') + (f' class="{cls}"' if cls else "") + ">")


def thumb(name, caption, sizes):
    p = photo(name)
    return (f'<button class="thumb" type="button" data-full="{p["large"]}" data-caption="{e(caption)}">'
            f'{img_tag(p, caption, sizes)}</button>')


def video(key):
    dest = OUT / "video" / f"{slug(key)}.mp4"
    if not dest.exists():
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(VIDEOS / f"{key}.mp4"),
                        "-vf", "scale='min(720,iw)':-2", "-c:v", "libx264", "-crf", "27",
                        "-preset", "slow", "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart", str(dest)], check=True)
    poster = OUT / "video" / f"{slug(key)}.jpg"
    if not poster.exists():
        with Image.open(VIDEOS / f"{key}.jpg") as im:
            im.convert("RGB").save(poster, "JPEG", quality=80, optimize=True)
    WRITTEN.update({dest.name, poster.name})
    with Image.open(poster) as im:
        w, h = im.size
    title = VIDEO_INFO.get(key, "")
    orient = "tall" if h > w else "wide"
    return (f'<figure class="video {orient}"><video controls preload="none" playsinline '
            f'poster="video/{poster.name}" width="{w}" height="{h}">'
            f'<source src="video/{dest.name}" type="video/mp4"></video>'
            f'<figcaption>{e(title)}</figcaption></figure>')


def show_date(s):
    if s.get("dateLabel"):
        return s["dateLabel"]
    d = datetime.date.fromisoformat(s["date"])
    return f"{d:%B} {d.day}, {d.year}"


def show_entry(s, with_media=True):
    parts = [f'<article class="show" id="{s["date"]}-{slug(s["title"])}">',
             f'<p class="show-date"><time datetime="{s["date"]}">{e(show_date(s))}</time></p>',
             f'<h3>{e(s["title"])}</h3>']
    if s.get("place") or s.get("time"):
        where = " · ".join(x for x in (s.get("time"), s.get("place")) if x)
        parts.append(f'<p class="show-place">{e(where)}</p>')
    if s.get("text"):
        parts.append(f'<p>{e(s["text"])}</p>')
    if with_media and s.get("photos"):
        parts.append('<div class="show-photos">' + "".join(
            thumb(p, f'{s["title"]}, {show_date(s)}', "(max-width: 600px) 45vw, 220px")
            for p in s["photos"]) + "</div>")
    if with_media and s.get("video"):
        parts.append(video(s["video"]))
    if s.get("links"):
        parts.append('<p class="show-links">' + " ".join(
            ext_link(l["label"], l["url"], " ↗") for l in s["links"]) + "</p>")
    parts.append("</article>")
    return "".join(parts)


def recent_card(s):
    media = ""
    if s.get("photos"):
        media = img_tag(photo(s["photos"][0]), f'{s["title"]}, {show_date(s)}',
                        "(max-width: 700px) 90vw, 30vw")
    return (f'<a class="card" href="shows.html#{s["date"]}-{slug(s["title"])}">{media}'
            f'<span class="show-date">{e(show_date(s))}</span>'
            f'<strong>{e(s["title"])}</strong><span class="show-place">{e(s.get("place", ""))}</span></a>')


def render(template, **values):
    text = (SRC / template).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    missing = re.findall(r"\{\{(\w+)\}\}", text)
    if missing:
        raise SystemExit(f"{template}: no value for {missing}")
    (OUT / template).write_text(text)


def validate(shows, gallery):
    for s in shows:
        datetime.date.fromisoformat(s.get("date", ""))
        if not s.get("title"):
            raise SystemExit(f"Show on {s['date']} has no title")
        for f in s.get("photos", []):
            if not photo_source(f).exists():
                raise SystemExit(f"Show {s['title']!r}: photo {f} not found")
    for g in gallery:
        if not photo_source(g["file"]).exists():
            raise SystemExit(f"Gallery photo {g['file']} not found")


def library():
    """Thumbnails of every available photo, for the admin page's photo picker."""
    files = sorted((f"uploads/{p.name}" for p in UPLOADS.glob("*.jpg")), reverse=True) if UPLOADS.exists() else []
    files += sorted(str(p.relative_to(PHOTOS)).replace("backgrounds/", "background-images/")
                    for p in PHOTOS.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    return [{"file": f, "thumb": photo(f, (640,))["small"]} for f in files]


def main():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    (OUT / "video").mkdir(exist_ok=True)
    site = json.loads((ROOT / "content/site.json").read_text())
    shows = sorted(json.loads((ROOT / "content/shows.json").read_text()),
                   key=lambda s: s["date"], reverse=True)
    gallery = json.loads((ROOT / "content/gallery.json").read_text())
    validate(shows, gallery)
    today = datetime.date.today().isoformat()
    upcoming = [s for s in reversed(shows) if s["date"] >= today]
    past = [s for s in shows if s["date"] < today]
    links = site["links"]
    facebook = next((l["url"] for l in links if "facebook.com" in l["url"]), None)

    if upcoming:
        upcoming_html = "".join(show_entry(s, with_media=False) for s in upcoming)
    else:
        upcoming_html = '<p class="empty">No dates are posted right now. New shows go up here' + (
            f' and on {ext_link("Facebook", facebook)}.</p>' if facebook else ".</p>")

    years = {}
    for s in past:
        years.setdefault(s["date"][:4], []).append(s)
    archive = "".join(
        f'<section class="year" id="y{y}"><h2>{y}</h2>' + "".join(show_entry(s) for s in ss) + "</section>"
        for y, ss in years.items())
    year_nav = " ".join(f'<a href="#y{y}">{y}</a>' for y in years)

    hero = photo("background-images/603193851.jpeg")
    roots = photo("background-images/1473576544.png")
    footer_links = "".join(ext_link(l["label"], l["url"]) for l in links) + \
        f'<a href="mailto:{e(site["email"])}">Email</a>'
    json_ld = json.dumps({
        "@context": "https://schema.org", "@type": "MusicGroup", "name": "Mixed Roots",
        "genre": ["AfroBeat", "Reggae"], "url": f"https://{DOMAIN}/", "email": site["email"],
        "foundingLocation": {"@type": "Place", "name": "Albany, New York"},
        "sameAs": [l["url"] for l in links]}).replace("</", "<\\/")
    common = {"year": str(datetime.date.today().year), "footer_links": footer_links,
              "show_count": str(len(past)), "first_year": past[-1]["date"][:4]}

    render("index.html",
           json_ld=f'<script type="application/ld+json">{json_ld}</script>',
           hero_img=img_tag(hero, "Mixed Roots on stage", "100vw", lazy=False),
           roots_img=roots["large"],
           og_image=f'https://{DOMAIN}/{hero["large"]}',
           tagline=e(site["tagline"]),
           band_heading=e(site["bandHeading"]),
           band_lead=e(site["bandLead"]),
           band_text="".join(f"<p>{e(x)}</p>" for x in site["bandText"].split("\n") if x.strip()),
           motto=e(site["motto"]),
           lineup="".join(f'<li><strong>{e(m["name"])}</strong><span>{e(m["role"])}</span>'
                          f'<p>{e(m.get("bio", ""))}</p></li>' for m in site["lineup"]),
           booking_text=e(site["bookingText"]),
           email=e(site["email"]),
           media_links="".join(ext_link(l["label"], l["url"], " ↗").replace("<a ", '<a class="text-link" ', 1)
                               for l in links if l["url"] != facebook),
           upcoming=upcoming_html,
           recent="".join(recent_card(s) for s in [s for s in past if s.get("photos")][:3]),
           videos="".join(video(k) for k in VIDEO_INFO),
           gallery="".join(f'<figure>{thumb(g["file"], g.get("caption", ""), "(max-width: 600px) 50vw, (max-width: 1000px) 33vw, 25vw")}'
                           + (f'<figcaption>{e(g["caption"])}</figcaption>' if g.get("caption") else "") + "</figure>"
                           for g in gallery),
           **common)
    render("shows.html", archive=archive, year_nav=year_nav, **common)
    for f in ("style.css", "app.js", "favicon.svg"):
        shutil.copy2(SRC / f, OUT / f)
    (OUT / "admin").mkdir(exist_ok=True)
    for f in (SRC / "admin").iterdir():
        shutil.copy2(f, OUT / "admin" / f.name)
    (OUT / "admin" / "library.json").write_text(json.dumps(library()))
    (OUT / "CNAME").write_text(DOMAIN + "\n")
    (OUT / ".nojekyll").write_text("")

    for f in list((OUT / "img").iterdir()) + list((OUT / "video").iterdir()):
        if f.name not in WRITTEN:
            f.unlink()
    print(f"Built {OUT}: {len(past)} past shows, {len(upcoming)} upcoming, {len(gallery)} gallery photos")


if __name__ == "__main__":
    main()
