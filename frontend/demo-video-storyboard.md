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

1. Source the stock clip(s) for shots 1/1b — candidates found:
   [couch/laptop, cozy](https://www.pexels.com/video/a-couple-sitting-on-a-couch-while-having-fun-watching-at-a-laptop-5657782/)
   for shot 1, [excited reaction](https://www.pexels.com/video/great-news-27155332/)
   for shot 1b (daytime-lit — may need a color grade to match shot 1's
   warmer tone). Pexels License confirmed OK for this use (website B-roll,
   not implying the people endorse the product) — preview both before
   committing, description-only judgment isn't a substitute for watching
   them.
2. Screen-record shots 2-6 — see "Recording checklist" below for the
   exact steps, in order, including how to fire a real test notification
   for shot 4 without waiting for a live race.
3. Source or build the racing-ambience BGM bed (see "Sound design").
4. Cut together: shots 2-6 as full-screen layers with a trim of the stock
   clip composited as a corner PiP, 1920x1080, h264 mp4 — ask for help
   scripting this with `ffmpeg` once the raw clips exist, no CapCut/
   iMovie required if you'd rather not do it by hand.
5. Export as `demo-walkthrough.mp4`, drop into `frontend/video/` (already
   gitignored — the file itself doesn't need to go into git, it's binary
   media, not source).

## Recording checklist (shots 2-6)

Do these in order, in one browser window, screen recording running the
whole time (macOS: `Cmd+Shift+5` → "Record Selected Portion", crop to just
the browser viewport, no menu bar/dock).

1. **Reset shot 2's trigger condition.** The pre-race survey only shows
   once per session per browser — open devtools console on any page of
   the site and run:
   ```js
   localStorage.removeItem('f1-fav-driver');
   localStorage.removeItem('f1-interest-race-1785212472206');
   localStorage.removeItem('f1-onboard-skipped-race-1785212472206');
   ```
2. **Make sure notifications are already enabled** (Settings page → the
   one-time "Enable notifications" flow) *before* you start recording —
   that permission dialog is a real one-time browser prompt, doesn't need
   to be in the final cut.
3. **Start recording. Navigate to** `/race?session=race-1785212472206` —
   the survey overlay should appear immediately (shot 2). Pick a driver,
   click through the interest question.
4. **Once the overlay closes**, the dashboard is on screen — this is
   shot 3. Either let it settle on the current lap, or navigate to
   `/race?session=race-1785212472206&lap=44` first to land directly on
   the PIA/NOR overcut lap without scrubbing the slider on camera.
5. **For shot 4 (the notification)**: once you're recording this part,
   say so — the real `push.send_push()` function can be called directly
   from the command line with the exact demo copy (`NOR overtakes PIA —
   hold this position and you move up to P2 in the championship`, url
   `/race?session=race-1785212472206`), firing a genuine banner on your
   already-subscribed browser without waiting for a live event to trigger
   it naturally. No GUI automation needed for this step, just a one-line
   script run at the moment you're ready.
6. **Shot 5-6**: click into Question (top nav), type "what just happened
   with NOR", let the streamed answer play out fully (trim in editing,
   don't cut the recording short — a cut-off stream reads as broken).
7. Stop recording once the answer finishes.
