# Mixed Roots website

The rebuilt site for Mixed Roots (AfroBeat and reggae, Albany NY), made from the band's original Weebly site after they lost access to it. How the content was recovered is in `recovery/RECOVERY.md`.

```
content/shows.json     every show (date, title, place, text, photos, links, video)
content/gallery.json   the photo grid on the home page, in order
src/                   page templates, styles, script
build.py               renders the site into docs/
docs/                  the built site; GitHub Pages serves this folder
recovery/              everything recovered from the old site (media, page history, inventory)
```

## Editing

1. Edit `content/shows.json` or `content/gallery.json`. Photo names refer to files in `recovery/media/photos/`; add new photos there.
2. Run `python3 build.py` (needs Pillow and ffmpeg, both already on Mark's Mac).
3. Preview with `cd docs && python3 -m http.server 8000` and open http://localhost:8000.
4. Commit and push. GitHub Pages republishes within a minute or two.

A show dated in the future appears under "Catch us live" automatically. Add `"dateLabel": "Summer 2026"` when the exact date isn't known. The date still controls sort order.

## Going live

The domain `mixedrootsnewyork.com` is registered at **Wix** and paid through 2031. The plan is to keep it there and only change its DNS records so they point at GitHub Pages, which is free. Nothing has to be transferred.

### 1. Put the site on GitHub Pages
1. Create a **public** GitHub repo (free Pages hosting requires public) and push this repo to it.
2. In the repo, go to Settings → Pages → Build and deployment. Set the source to "Deploy from a branch", the branch to `main`, and the folder to `/docs`.
3. Under Custom domain, enter `www.mixedrootsnewyork.com` (`docs/CNAME` already contains it).
4. Check the site at `https://<your-github-username>.github.io/<repo>/`.

### 2. Point the domain at it (in Wix)
Log in to the band's Wix account, go to **Domains**, open the ⋯ menu next to `mixedrootsnewyork.com`, and choose **Manage DNS Records**.

If Wix won't let you edit the A or CNAME records, the domain is still attached to a Wix site. Disconnect it from that site first, without deleting the domain, and then edit the records.

| Type | Host | Value | What to do |
|---|---|---|---|
| A | `@` (root) | `185.199.108.153` | Replace the Wix `185.230.63.x` records with these four |
| A | `@` | `185.199.109.153` | |
| A | `@` | `185.199.110.153` | |
| A | `@` | `185.199.111.153` | |
| CNAME | `www` | `<your-github-username>.github.io` | Replace the current `cdn3.wixdns.net` value |
| MX | `@` | `aspmx.l.google.com` and the `alt*` entries | **Leave these alone.** The domain receives email through Google. |

Changes take anywhere from a few minutes to a few hours. When GitHub shows the domain as verified, tick **Enforce HTTPS** in Settings → Pages.

Optional: in GitHub, go to your account Settings → Pages → Add a verified domain. This gives you a TXT record to add in Wix, which stops anyone else's GitHub repo from claiming the domain.

### 3. After launch
- The old Weebly URLs (`/about.html`, `/performances.html`, `/contact.html`) will return 404. Old links to them are mostly from search engines and will drop off.
- Re-check the site on a phone.

## Still to confirm with the band

- Current lineup. The site uses the newest bio (George, Gideon, Seth, Brian, Pete, Dillon, Catherine).
- The booking email `MixedRootsNewYork@gmail.com`.
- Who uses email at `@mixedrootsnewyork.com` (Google MX records exist), so nobody's mail breaks.
- Photo credits, and full-resolution originals of photos and videos if they have them.
- `p115.png` and `p150.png` from the old site may not be Mixed Roots, so they're left off the site.
- Inferred dates: the Big Takeover show "Sunday, July 11" is listed as 2021 (the only recent year July 11 was a Sunday), Westminster Commons as Nov 20 2022, and Alive at Five as June 30 2021 (from the rain-site flyer).
- Upcoming shows to add.
- Current Instagram, Bandcamp, Spotify or other links. The old site only had Facebook, YouTube Music and one Vimeo video.
