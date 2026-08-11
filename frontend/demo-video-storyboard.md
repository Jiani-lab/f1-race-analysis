# Home page demo video — storyboard draft

Target: a ~35-45s clip embedded in `home.html`'s `#demo` section
(`video/demo-walkthrough.mp4`, 16:9, drop it in and the placeholder swaps
out automatically — see that file's inline script). Silent is fine, a
couple of text overlays do the explaining.

## The core call: mix real screen recording with AI-generated B-roll

AI video tools (Seedance, LibTV/Kling, etc.) are good at photoreal *people
and rooms*, but still bad at rendering **legible UI text** — a generated
"dashboard" would show fake, swimming, unreadable text, which undercuts the
one thing this video needs to prove (that the notification and the answer
are real). So:

- **AI-generate**: the human moment — someone watching the race, reacting
  to their phone.
- **Screen-record for real**: every shot where UI text needs to be readable
  — the event feed, the notification banner, the Question tab answer. This
  is just QuickTime (`Cmd+Shift+5` on Mac) over the actual site running
  against a real captured session (use the replay slider on `/race` to
  land on a good moment instead of waiting for a live race).

## Shot list

| # | Shot | Source | Length | Notes |
|---|------|--------|--------|-------|
| 1 | Someone on a couch, TV glowing with an F1 broadcast in the background, phone resting nearby, leaning in as cars pass | AI-gen | 4-5s | This is the one shot worth spending AI-gen credits on — establishes "watching live," not staged desktop screenshots |
| 2 | Phone buzzes, notification banner slides in with real text (e.g. "Lap 44 — NOR: Overcut on PIA") | **Real recording** — trigger a test push and screen-record the banner, phone or browser | 3-4s | Needs to be the real notification copy, not a mockup |
| 3 | Cut to the dashboard: event feed on `/race` scrolling, the just-fired event highlighting in | Real recording | 5-6s | Use a session with a genuinely interesting moment (the Hungarian GP overcut mentioned in CURRENT-STATUS.md is a strong pick) |
| 4 | Tap into Question, type something like "what just happened with NOR" | Real recording | 5-6s | Type at a natural pace, don't speed it up unnaturally |
| 5 | Streamed answer appearing token-by-token | Real recording | 4-5s | The streaming itself is a real feature worth showing, not cutting away from |
| 6 | End card: wordmark + "Open your races →" | Simple graphic (not AI-gen — just a static/CSS export) | 2-3s | Match the site's red/dark palette so it doesn't feel bolted-on |

Total: ~25-30s of content, pad to 35-45s with slightly longer holds on 3-5
if it feels rushed.

## Practical steps

1. Pick one real session under `backend/sessions/` with a clear "moment"
   (a lead change or overcut reads better on camera than a quiet lap).
2. Screen-record shots 2-5 at native resolution, no browser chrome
   (fullscreen or a cropped capture) — keep the red/dark UI as the only
   thing on screen.
3. Generate shot 1 (and maybe a variant or two to pick from) with
   Seedance or LibTV from a prompt like: *"Medium shot, cozy dim living
   room at night, TV glowing with a motorsport broadcast reflected on the
   wall, person leaning forward on a couch, phone resting on the couch arm
   beside them, warm ambient light, shallow depth of field, cinematic"*.
4. Cut together in CapCut/iMovie, 1920x1080, h264 mp4.
5. Export as `demo-walkthrough.mp4`, drop into `frontend/video/` (already
   gitignored — the file itself doesn't need to go into git, it's binary
   media, not source).

## Open questions to settle together before generating anything

- Shot 1: a real photo of yourself as the reference/seed image (more
  "this is genuinely how I use it"), or fully text-to-video with a
  generic person?
- Silent with text overlays, or do you want a voiceover?
- Which session's data to feature in shots 3-5?
