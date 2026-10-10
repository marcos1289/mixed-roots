# Recovery report — mixedrootsnewyork.com

Second pass, 2026-10-10. The first pass fetched one Wayback snapshot (2026-01-21) and recovered 13 images. This pass covered every capture and checked other sources.

## Sources checked

| Source | Result |
|---|---|
| Wayback CDX, whole domain, uncollapsed | 213 captures, 57 URLs, 2021-10 to 2026-06. All 89 distinct page versions saved in `snapshots/` (`<page>__<timestamp>.html`). Full index in `cdx-all-captures.json`. |
| Weebly upload CDN (`www.weebly.com/uploads/1/0/2/1/102180450/…`) | **Still serving the band's original uploads** even though the site is down. This is where almost all the photos came from. |
| Weebly video CDN (`www.weebly.com/uploads/b/102180450-548824018822533059/…`) | All 3 embedded videos recovered with their poster frames. |
| Common Crawl (every index since 2022) | Only copies of pages already in Wayback. Nothing new. |
| archive.today, `*.weebly.com` subdomains, alternate domains | No captures. |
| Live domain | `mixedrootsnewyork.com` now resolves to **Wix** DNS and returns 404 for everything. Find out who controls the registrar before relaunch. |

## What was recovered

- **54 unique photos and flyers**, up from 13, in `media/photos/` under their original Weebly filenames (`_orig` dropped; it is always the full-size copy). Page header backgrounds are in `media/photos/backgrounds/`. Weebly template placeholder icons were left out.
- **3 videos** in `media/video/`: `p86_414.mp4` (34 MB, on Performances since 2021), `p83_349.mp4` (15 MB, since 2024), `troy_night_out_-_mixed_roots_502.mp4` (17 MB, Troy Night Out, June 2025). The `.mp4` files are gitignored for size. **Back them up outside the repo.**
- `MEDIA.md` lists each file with the page it appeared on, when, and the show text beside it, which is effectively the caption. `contact-sheet.jpg` shows them all.
- Earlier text that later versions dropped (below).

## Text that only exists in older versions

**Earlier lineup (About page, 2021):**
- George, drummer and vocalist, "grew up in Accra, Ghana, where he learned and practiced traditional African beats."
- Gideon, keys, from Nigeria. Pete, guitar, "local to upstate New York," described as the band's roots-reggae anchor.
- T T, hand percussion, from Ghana (removed in the Nov 2021 version).
- Jah Red, bass, local, "mostly self taught in reggae."
- Horns "at times" two trombones, Dave and Catherine, plus Scott on sax.
- The current version lists Brian (bass), Pete (guitar, now called an Irishman), Dillon (sax), Catherine (trombone), Gideon, Seth (hand drums) and George. **Ask the band which lineup is current.** "Kofi" also appears on Performances (Feb 2020 acoustic set).

**Show announcements later rewritten as thank-yous (Performances):**
- Park Theater, 723 Warren St., Hudson NY, Nov 8 2024. Video at **vimeo.com/1016538628** (not on the preliminary site).
- Shepard Park, Lake George, originally announced for **Wed Aug 13 2025, 7:00 pm**. The thank-you says Aug 21, so it was probably rescheduled.
- Poughkeepsie Farm Project Harvest Fest, Oct 25 2025, 2:30.
- Albany Public Library Main Branch, 161 Washington Ave, 6:15-7:45.
- "After opening Alive at Five for Third World, a few musicians from Mixed Roots got to take photos with them." The photo that went with this (p98) is the only content photo not recovered.

**Links found anywhere on the old site:**
- Facebook page: facebook.com/Mixed-Roots-Reggae-1337569189643533
- YouTube Music: music.youtube.com/channel/UCyPiesgdO8TSPQgSf3rXtSA (not on the preliminary site)
- Vimeo: vimeo.com/1016538628
- Times Union, asylum-seekers benefit article
- Booking email: MixedRootsNewYork@gmail.com (plain text in 2021 captures; later hidden by Cloudflare)

## Not recoverable

- `p98.png`: Alive at Five / Third World photo. Never archived and gone from the CDN.
- `p83.jpeg` (2022 version) and `published/lake-george-8-13-25-promo-shepard-park.png` (Aug 2025 promo flyer).
- Homepage: every capture since 2021 is Weebly's "Highpeak Mountain tours" placeholder. The band never wrote homepage copy, so nothing was lost there.
- News/blog: only the one post that is already recovered. The RSS feed never had items.

## To confirm with the band

1. The current lineup and which bio to use.
2. Whether `p115.png` (five people against a yellow wall) and `p150.png` are Mixed Roots. They don't match the other band photos.
3. Photo credits. The original credits "Heather, our guitarist's wife" for the Franklin Alley set.
4. Who owns the domain (it now points at Wix), and whether they want to keep it.
5. Whether they have originals of the videos and full-resolution photos. Some CDN copies are 720 px.

## Re-running

`tools/getall.sh jobs.txt outdir` fetches Wayback captures politely. Wayback rate-limits parallel requests, and Python's `urllib` fails TLS on this Mac, so it uses curl. Some captures come back gzipped, so run `gunzip` before parsing. `tools/totext.py` turns snapshots into text and reports distinct versions. `tools/captions.py` pairs each image with its neighbouring text.
