# Home page demo video — storyboard draft

**Status: approved (2026-08-11) — production in progress.** Shots 2, 3,
5, 6 are captured for real (see "Capture status" below). Shots 1/1b source
switched back to AI-gen (2026-08-12, see "AI-gen prompts" below) — text-
to-video only, no reference photo of any real person, generic/non-
identifiable people.

Target: a **~18-20s** clip embedded in `home.html`'s `#demo` section
(`video/demo-walkthrough.mp4`, 16:9, drop it in and the placeholder swaps
out automatically — see that file's inline script). Cut for attention span,
not for a walkthrough — this is a teaser, not a tutorial.

**Locked in:** Hungarian GP footage (`race-1785212472206` under
`backend/sessions/`, the real Norris/Piastri battle already referenced in
`index.html`'s own direction comment and `CURRENT-STATUS.md`) for every
real-screen-recording shot below. **The exact moment was corrected while
capturing** — checked the real events directly (`curl /session/events`)
rather than trust the earlier "around lap 40-44" guess: the actual
overtake is "Norris takes the race lead from Piastri on lap 36" (leader
change confirmed lap 37). Shot 3 uses `?lap=37` accordingly, not 44.

## The core call: real screen recording + AI-gen B-roll

Two source types:

- **AI-generated video**: the human "watching together" moment (shots
  1/1b) — text-to-video only, no reference photo/likeness of any real
  person. See "AI-gen prompts" below.
- **Real screen recording**: every shot where UI text needs to be
  legible and actually prove a real feature — the survey, the event feed,
  the notification, the Question answer. AI video tools still render UI
  text illegibly, that constraint hasn't changed.

## AI-gen prompts (Seedance)

Access: [即梦AI](https://jimeng.jianying.com) (国内直连) or
[Dreamina](https://dreamina.capcut.com/tools/seedance-1) (international) —
same underlying Seedance model, pick whichever account you've got. Both
are pure text-to-video below, no image/photo upload for either shot.

**Shot 1 (establishing, need ~2.5s usable)**

> Medium shot, cozy dim room at night, two people sitting close together
> at a table, a laptop open between them glowing softly, warm ambient
> lighting, one person leaning in toward the screen, intimate and relaxed
> mood, shallow depth of field, cinematic, screen content out of focus —
> an abstract glow only, no legible text or UI

中文版（即梦上可直接用）：
> 中景镜头，深夜温馨昏暗的房间，两人紧挨着坐在桌前，中间摊开一台发着柔光的笔记本电脑，暖色氛围灯光，其中一人身体前倾靠近屏幕，亲密放松的氛围，浅景深，电影感；屏幕内容虚化只呈现光晕，不需要清晰文字或界面

**Shot 1b (reaction loop, need ~5-6s usable, reused as the PiP source for shots 2-6)**

> Same two people from before, close-up on their faces reacting to the
> laptop screen, leaning in further, a genuine smile, one of them points
> at the screen with excitement, warm night lighting, cinematic, subtle
> handheld camera feel, smooth motion suitable for a looping cutaway

中文版：
> 同样的两人，特写反应镜头，对着笔记本电脑屏幕，身体更靠近，露出真实的笑容，其中一人兴奋地指向屏幕，暖色夜晚灯光，电影感，轻微手持镜头质感，动作流畅适合循环剪辑使用

Generate a couple of variants of each if the first pass doesn't feel
right — send whatever comes out and it can get cut into the PiP either
way, no need to pre-judge before generating.

## Corrected from the first draft (still true regardless of shot 1/1b's source)

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
~18% of frame width) holding a short looping trim from the AI-gen clip
(shot 1b), composited over each full-screen UI recording for its whole
duration. This is a plain picture-in-picture layer in CapCut/iMovie, not
real-time compositing — just two source clips (the reaction loop + each
screen recording) layered in the edit.

## Shot list (v5 — AI-gen B-roll, ~18-20s)

| # | Shot | Source | Length | Notes |
|---|------|--------|--------|-------|
| 1 | Establishing: two people close together, a laptop screen glowing between them, warm room light, one leaning in | AI-gen (Seedance) | 2.5s | Prompt above — screen content stays an abstract glow, not meant to show real UI |
| 1b | Reaction moment: same two people, a beat of them reacting — leaning in further, a smile, a point at the screen — trimmed into a short loop, reused as the PiP source for shots 2-6 | AI-gen (Seedance) | 5-6s source, trimmed as needed | One clip, reused throughout rather than generating 5 separate reaction shots |
| 2 | Full-screen: the pre-race survey overlay (driver picker → "what are you most interested in?") + reaction PiP corner | Real recording + PiP | 2s | Quick flash — just long enough to register it's a real, personal setup step |
| 3 | Full-screen: dashboard event feed on `/race`, landing on lap 37 (Norris just took the lead from Piastri) + reaction PiP | Real recording, Hungarian GP session + PiP | 3s | The genuinely dramatic real event in this data |
| 4 | Full-screen: macOS-style notification banner slides in with real copy (see below) + reaction PiP, held slightly longer as this is the hero beat | Real recording + PiP | 3.5s | Visibly a desktop/browser notification on the same screen as the stream — not a phone |
| 5 | Full-screen: click into Question, type "what just happened with NOR" + reaction PiP | Real recording + PiP | 2s | Sped up slightly if needed to hit the time budget |
| 6 | Full-screen: streamed answer appearing token-by-token + reaction PiP | Real recording + PiP | 2.5s | The streaming itself is worth the half-second it costs |
| 7 | End card: wordmark + "Open your races →" | Simple graphic | 2s | Match the site's red/dark palette |

Total: ~18-20s. If it's still running long once cut together, trim shot 2
(the survey) first — it's the least essential beat if something has to
give, since shot 4 (notification) is the actual hero moment.

## Sound design

Racing BGM, not silent. Candidates sourced from Pixabay (Content License
confirmed: free commercial use, no attribution required, fine for this —
verified against the actual license page, not assumed):

- **Bed for shots 1-3** (ambient engine drone, mixed low): [Sounds of
  Nuerburgring — Engines of classic race cars](https://pixabay.com/sound-effects/search/race-car/)
  (fjc_media, 2:08 — long enough to cover the whole clip if needed, trim
  to taste). Preview before committing — judged by listing metadata, not
  by actually listening.
- **Shot 4 (the notification hit)**: layer in a quick pass-by/accent —
  [Fast Car Passing Sound](https://pixabay.com/sound-effects/search/race-car/)
  (moeeza3, 0:08) or [Heavy Race Car Speeding Reverb](https://pixabay.com/sound-effects/search/race-car/)
  (kalsstockmedia, 0:12) — right as the banner slides in, same trick
  broadcasts use to sell an overtake, cueing the viewer that *this* moment
  matters before they've even read the text.
- **Shots 5-7**: audio settles back down to the ambient bed so the
  streamed text is easy to read.

**Notification copy for shot 4** — needs the driver name + standings
position filled in, e.g.:

> **NOR overtakes PIA** — hold this position and you move up to **P2** in
> the championship

Keep it two lines max so it's legible in a 3.5s shot. The real
`push.send_push()` call in `app.py` (`_maybe_push_notification`) is
already instructed to connect events to championship-standings stakes
when relevant — this is just picking a driver/position combo that reads
as a genuine stakes-raiser for the demo.

## Capture status

Shots 2, 3, 5, 6 are captured — for real, not mocked up. Automated via
Playwright driving a real headless Chromium against the actual running
dev server (`localhost:8800`), recording the browser viewport directly
(Playwright's own video capture, not OS screen recording — this is why it
needed no macOS Screen Recording permission and doesn't touch your real
browser/profile at all):

| Shot | File | Real duration | What's on screen |
|---|---|---|---|
| 2 (survey) | `out/shot2-survey/*.webm` | 7.96s | The real onboarding overlay, driver picker → interest question, both actually clicked through |
| 3 (event feed) | `out/shot3-eventfeed/*.webm` | 26s (mostly load/settle time, trims down easily) | `/race?session=race-1785212472206&lap=37` — Norris shown P1, "Lead is growing," right after the real lap-36 overtake |
| 5-6 (question+answer) | `out/shot5-6-question/*.webm` | 55.6s (full untrimmed stream) | Typed "what just happened with NOR" into the real Question page, waited for the real streamed answer to finish |

All three verified by extracting preview frames and actually looking at
them (not just checking the files aren't empty) — nav bar renders
correctly and shows the right active tab in every one. One cosmetic,
pre-existing quirk noticed along the way, not something this work
introduced: the small grey "session race-xxxxx" status-note text in the
status row reflects the *backend's global live-tracking state*
(`state.session_id` — whatever session it last auto-resumed on startup),
not the `?session=` you're actually viewing, so it can show a different
ID than the page's real content when they don't happen to match. Everything
else on the page (title, lap counter, events, battles) correctly reflects
the URL's session. Worth a real fix at some point (TODO'd separately,
harmless for this video — that text is tiny and easy to crop/ignore).

These raw clips are copied to `frontend/video/_raw/` (gitignored, same as
the final export), so they're on disk here rather than only in this
session's scratch directory — paths in the table above are relative to
that folder.

**Still not captured — genuinely can't be, from here:**

- **Shot 4 (the notification banner)**: Web Push notifications render at
  the OS level, outside any page's DOM — Playwright's viewport recording
  fundamentally cannot show them, and the real subscription in
  `push_subscription.json` is bound to *your actual browser profile*, not
  an isolated automation instance. This one has to be real screen
  recording on your actual machine, in your actual browser, while it's
  actually subscribed. Tell me when you're rolling and I'll fire the real
  `push.send_push()` call the moment you need it — copy still: `NOR
  overtakes PIA — hold this position and you move up to P2 in the
  championship`.
- **Shots 1/1b (the human moment)**: no video-generation tool exists
  here — this is genuinely outside what can be done from this session,
  not a matter of trying harder. Prompts are ready above (即梦AI/Dreamina,
  both text-to-video, no reference photo of anyone).

## Practical steps

1. Generate shots 1/1b on 即梦AI or Dreamina (prompts above) — send
   whatever comes out, a couple of variants if the first pass doesn't
   land, no need to pre-judge before generating.
2. Do the shot-4 screen recording (see "Still not captured" above) — say
   when you're ready and the real notification fires on cue.
3. Source or build the racing-ambience BGM bed (see "Sound design").
4. Cut together: shots 2-6 (already captured) as full-screen layers with
   a trim of the AI-gen reaction clip composited as a corner PiP,
   1920x1080, h264 mp4 — ask for help scripting this with `ffmpeg` once
   shot 4 and the AI-gen clips are in hand, no CapCut/iMovie required if
   you'd rather not do it by hand.
5. Export as `demo-walkthrough.mp4`, drop into `frontend/video/` (already
   gitignored — the file itself doesn't need to go into git, it's binary
   media, not source).
