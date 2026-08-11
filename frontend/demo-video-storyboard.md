# Home page demo video — storyboard draft

**Status: approved (2026-08-11) — production can start.** Fully settled,
including the source for shots 1/1b (licensed stock footage — see below).

Target: a **~18-20s** clip embedded in `home.html`'s `#demo` section
(`video/demo-walkthrough.mp4`, 16:9, drop it in and the placeholder swaps
out automatically — see that file's inline script). Cut for attention span,
not for a walkthrough — this is a teaser, not a tutorial.

**Locked in:** Hungarian GP footage (`race-1785212472206` under
`backend/sessions/` — the real PIA/NOR overcut session already referenced
in `index.html`'s own direction comment and `CURRENT-STATUS.md`) for every
real-screen-recording shot below.

## The core call: real screen recording + licensed stock footage

No AI-generated video anywhere in this cut. Two source types only:

- **Licensed stock footage**: the human "watching together" moment (shots
  1/1b) — pick a couple-watching-a-laptop-at-night clip from a stock
  library (Pexels/Envato/etc., pick one actually licensed for this use).
- **Real screen recording**: every shot where UI text needs to be
  legible and actually prove a real feature — the survey, the event feed,
  the notification, the Question answer.

## Corrected from the first draft (still true, just no AI-gen now)

- **The device is a MacBook, not a TV.** Luci reads the screen it's
  installed next to — there's no camera pointed at a TV, no way to OCR a
  TV from across a room. The whole premise only works if the livestream is
  playing *on the same Mac* Luci is watching. So shots 1/1b need a
  laptop-watching clip, not a couch-facing-TV one.
- **The notification is a browser/desktop push on that same Mac, not a
  phone.** Web Push (VAPID) fires as an OS-level notification banner on
  whatever device has the browser subscription — for this demo that's the
  Mac that's already playing the stream, not a separate phone.
- **Includes the pre-race personalized survey** — this is real,
  already-built UI (`index.html`'s onboarding overlay: "Who are you
  rooting for?" driver picker, then "What are you most interested in this
  race?"), and it's the setup that makes the later notification feel
  personal rather than generic.

## Keeping the couple in frame during the screen shots

20s isn't enough time to fully cut away to full-screen UI for 5 separate
beats and still feel like "two people watching a race," so shots 2-6 use a
**persistent reaction PiP** — a small rounded corner inset (bottom-left,
~18% of frame width) holding a short looping trim from the stock clip
(shot 1b), composited over each full-screen UI recording for its whole
duration. This is a plain picture-in-picture layer in CapCut/iMovie, not
real-time compositing — just two source clips (the stock loop + each
screen recording) layered in the edit.

## Shot list (v4 — stock footage, ~18-20s)

| # | Shot | Source | Length | Notes |
|---|------|--------|--------|-------|
| 1 | Establishing: two people close together, a laptop screen glowing between them, warm room light, one leaning in | Licensed stock footage | 2.5s | Pick a clip where the laptop screen content isn't legible/prominent — it's not meant to show real UI, just the mood |
| 1b | Reaction moment: same clip (or a second clip from the same library/scene), a beat of them reacting — leaning in further, a smile, a point at the screen — trimmed into a short loop, reused as the PiP source for shots 2-6 | Licensed stock footage | 5-6s source, trimmed as needed | One stock clip, reused throughout rather than sourcing 5 separate reaction shots |
| 2 | Full-screen: the pre-race survey overlay (driver picker → "what are you most interested in?") + reaction PiP corner | Real recording + PiP | 2s | Quick flash — just long enough to register it's a real, personal setup step |
| 3 | Full-screen: dashboard event feed on `/race`, landing on the PIA/NOR overcut moment + reaction PiP | Real recording, Hungarian GP session + PiP | 3s | The genuinely dramatic real event in this data |
| 4 | Full-screen: macOS-style notification banner slides in with real copy (see below) + reaction PiP, held slightly longer as this is the hero beat | Real recording + PiP | 3.5s | Visibly a desktop/browser notification on the same screen as the stream — not a phone |
| 5 | Full-screen: click into Question, type "what just happened with NOR" + reaction PiP | Real recording + PiP | 2s | Sped up slightly if needed to hit the time budget |
| 6 | Full-screen: streamed answer appearing token-by-token + reaction PiP | Real recording + PiP | 2.5s | The streaming itself is worth the half-second it costs |
| 7 | End card: wordmark + "Open your races →" | Simple graphic | 2s | Match the site's red/dark palette |

Total: ~18-20s. If it's still running long once cut together, trim shot 2
(the survey) first — it's the least essential beat if something has to
give, since shot 4 (notification) is the actual hero moment.

## Sound design

Racing BGM, not silent:

- **Shots 1-3**: engine drone / cars passing, mixed low enough to read as
  ambient rather than a soundtrack.
- **Shot 4 (the notification hit)**: the engine sound briefly tightens up
  right as the banner slides in — same trick broadcasts use to sell an
  overtake, cueing the viewer that *this* moment matters before they've
  even read the text.
- **Shots 5-7**: audio settles down so the streamed text is easy to read.

**Notification copy for shot 4** — needs the driver name + standings
position filled in, e.g.:

> **NOR overtakes PIA** — hold this position and you move up to **P2** in
> the championship

Keep it two lines max so it's legible in a 3.5s shot. The real
`push.send_push()` call in `app.py` (`_maybe_push_notification`) is
already instructed to connect events to championship-standings stakes
when relevant — this is just picking a driver/position combo that reads
as a genuine stakes-raiser for the demo.

## Practical steps

1. Source the stock clip(s) for shots 1/1b — a licensed
   couple-watching-a-laptop-at-night clip, confirm the license actually
   covers this use (a public site's marketing page) before buying/using.
2. Load the Hungarian GP session (`race-1785212472206`) on `/race`, use
   the replay slider to land on the PIA/NOR overcut moment.
3. Screen-record shots 2, 3, 4, 5, 6 at native resolution, no browser
   chrome — keep the real UI as the only thing on screen. Shot 2 needs the
   onboarding overlay actually triggered (it's a one-time flow, check
   `index.html` for how to re-trigger it for the recording).
4. Source or build the racing-ambience BGM bed (see "Sound design").
5. Cut together in CapCut/iMovie: shots 2-6 as full-screen layers with a
   trim of the stock clip composited as a corner PiP, 1920x1080, h264 mp4.
6. Export as `demo-walkthrough.mp4`, drop into `frontend/video/` (already
   gitignored — the file itself doesn't need to go into git, it's binary
   media, not source).
