# Song generator

Writes songs for Mixed Roots as MIDI plus a rendered demo. The demo uses the band's own sounds (from `tools/stems`) and a sung guide vocal. It learns from the band's A/B picks.

## The improvement cycle

1. **Generate:** `tools/compose/cycle.sh` (default 4 variants; `cycle.sh 6` for more). This learns from the ratings so far, writes a new batch, publishes it to the studio page, and pushes. Expect about 3 minutes per variant on this Mac.
2. **Rate:** on the studio page, open **Compare hooks**. Each pair is a blind A/B of 16-second first-chorus clips. Pick the catchier one, or "both good" or "neither works", and optionally add a note ("too slow", "love the horns"). The first time on each device, paste the band's GitHub access key so picks can be saved.
3. **Repeat.** `learn.py` credits the settings behind each winner. The next batch draws winners more often and still tries the alternatives (Thompson sampling), so the generator drifts toward what the band likes.

## Pieces

| File | Role |
|---|---|
| `styles.py` | Groove library: one drop, rockers, steppers, Marley four-on-the-floor, Slightly Stoopid hybrid, afrobeat. Drum grids, bass riffs, skank and bubble, tenor guitar, percussion, chord loops, and horn riffs written as scale degrees. Sources are in `research_notes/Reggae afrobeat style guide/`. |
| `melody.py` | Writes vocal melodies for any lyrics. It generates hundreds of candidates per section and keeps the one with the best catchiness score (repetition, contour, range, chord tones, syncopation), following `catchiness_and_learning.md`. |
| `evolve.py` | Samples settings per variant, builds the song, renders it and cuts the hook clip. |
| `learn.py` | Decrypts the picks in `feedback/`, updates `learned.json`, and prints standings plus everyone's notes. |
| `compose.py` | Renders a song file: arrangement, groove, the band's samples, singing, dub echo and spring reverb, and mix balance. |
| `samplers.py` | Builds instruments from the band's separated recordings. The result is cached in `band-stems/.sampler-cache.pkl`. |
| `sing.py`, `check_vocals.py` | Sung guide vocal, and the Whisper-based check of how clear the lyrics are. |

## Guardrails

These keep the output roots reggae and not Latin. See `styles.py` and the memory note on the "mariachi" feedback.

- Horns in unison or octaves only.
- Modal chord loops, with no major V resolving to minor i.
- Bass riffs that leave space.
- Snare or rim on 3 in one-drop.
- Swung hats where the groove calls for it.
- A bass-forward mix.

## Repo size

Generated variants publish only the mix and vocal, and only the two most recent batches keep their full songs on the studio page. Hooks for comparison stay.
