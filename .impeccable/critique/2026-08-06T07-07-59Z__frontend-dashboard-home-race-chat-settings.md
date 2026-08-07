---
target: frontend dashboard (home/race/chat/settings)
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
timestamp: 2026-08-06T07-07-59Z
slug: frontend-dashboard-home-race-chat-settings
---
Method: dual-agent (A: ae2ac102687074153 · B: a32a89737b5523510)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Status pill's `className` (color) isn't reset on a failed `/session/status` fetch — text says "Backend not responding" but the dot can stay green/idle |
| 2 | Match System / Real World | 4 | F1-fluent throughout; only ding is the invented 0-100 "Importance" gauge with no explained real-world analog |
| 3 | User Control and Freedom | 2 | Replay scrub is real freedom, but Summary/Catchup/What-If generation has no cancel once started |
| 4 | Consistency and Standards | 3 | Visually cohesive, but 4 independent `<style>` blocks with drifting token names/values (`--track`, `--ink-faint`, `.surface` vs `.panel`) — no shared stylesheet |
| 5 | Error Prevention | 2 | `doWhatIf()` sends an empty/unvalidated hypothesis straight to a multi-minute backend job; the chat composer three sections later already guards this correctly |
| 6 | Recognition Rather Than Recall | 3 | Team colors reinforce recognition well; bare 3-letter driver codes in the ticker have no full-name hover/title |
| 7 | Flexibility and Efficiency | 3 | Real power-user wins (`?lap=` deep-linking, auto-scrub, table-view fallback); missing keyboard shortcuts on the scrubber and no glance/compact mode |
| 8 | Aesthetic and Minimalist Design | 2 | ~10 co-equal-weight sections stacked with no page-level hierarchy or way to prioritize one over another |
| 9 | Error Recovery | 2 | Raw `'Error: ' + e.message` dumps with no retry/diagnosis; the one bright spot is the chat SSE reconnect's genuinely well-written "connection lost" message |
| 10 | Help and Documentation | 2 | The onboarding modal's copy is a real good example, but it's the only one — importance score, chart crosshair, chat scope differences all go unexplained |
| **Total** | | **26/40** | **Acceptable** |

Scored across all 10 heuristics (Operate-mode surface; heuristics 7 and 10 genuinely apply here and were scored normally, not n/a).

## Design Specificity Verdict

**LLM assessment**: Specifically authored for F1, not a reskinned generic dashboard — real 2026 driver/team roster hardcoded, original illustrated helmet-badge SVGs (deliberately avoiding real photos), a domain-specific event taxonomy (VSC, safety car, pit stop, penalty, team radio) each with its own icon, a gap-to-leader "duel" chart modeling F1-specific race semantics rather than a generic line chart, and F1-fluent copy throughout pulled straight from real detected events. The onboarding "who are you rooting for" flow wires into a real personalization loop (favorite driver → notification → suggested What-If), not decoration. One deliberate exception: `home.html`'s account-switcher is explicitly commented in the code as cosmetic-only decoration mimicking "real racing sites" — honest in the comment, but it implies multi-account state that doesn't exist (confirmed no-auth, single-process backend).

**Deterministic scan**: 1 finding across all 4 files — `flat-type-hierarchy` on `index.html:73` (font sizes 10–18px cluster within a 1.8:1 ratio). Judgment call, not a clean true/false positive: the clustered sizes are dominated by small mono metadata labels that legitimately sit close together in a dense telemetry-style UI (a defensible pattern for this domain), but it's still worth a human look. No color-count or contrast findings were raised despite the team-color-heavy pages — the detector didn't flag `--ink-faint`'s low contrast (Assessment A caught that manually; see P2 below), so treat the "clean" contrast result as the detector's blind spot, not a clean bill of health.

**Visual overlays**: unavailable this session — no browser automation tool was exposed, so no live `[Human]`-tab overlay was generated. This critique is based on source review plus real backend data (`curl` against the live session data), not a rendered screenshot.

## Overall Impression

This is an unusually well-built personal project for the amount of real engineering rigor behind the data (documented OCR-swap detection, lap-gated data filtering, honest "Unconfirmed" badges on uncertain events) — but the *page-level* design hasn't caught up to that rigor. `index.html` in particular reads as ~10 features bolted on in the order they were built, each with equal visual weight, rather than a single coherent "glance at this during a race" experience. The single biggest opportunity: the backend already computes which events are personally notification-worthy for this viewer — the frontend doesn't use that same signal to promote anything visually, so a page that could resolve to "one clear answer at a glance" instead asks the viewer to scan a wall of equally-weighted sections every time.

## What's Working

1. **Data honesty enforced in code, not just claimed in copy** — `renderForLap()` filters every source to `lap <= currentLap` with real inline documentation of bugs found and fixed; uncertain events get a visible `⚠ Unconfirmed` badge instead of being silently smoothed over. This shows up as genuine trustworthiness in the UI.
2. **Progressive disclosure discipline on lists** — the ticker and timeline both cap at 5 visible items with an explicit "Show N earlier" toggle, applied consistently across the page rather than as a one-off.
3. **The replay slider defaulting to the actual current live lap** (not full race distance), and instantly re-rendering the entire page as a pure function of lap position with no lookahead leakage — a real "wow, this is trustworthy" interaction, not a gimmick.

## Priority Issues

**[P0] Status pill color contradicts its own text on backend failure**
Why it matters: `refreshStatus()`'s `catch` block rewrites the status text to "Backend not responding" but never resets `pill.className` — a user glancing mid-race specifically to answer "is this actually live right now" can see a green/idle-colored dot next to red-flag text. That's worse than no indicator, at exactly the moment reassurance matters most.
Fix: in the `catch`, also set a distinct `status-error` class on the pill so color and text always agree.
Suggested command: `/impeccable harden` (or a direct fix — this is small and mechanical enough to just patch).

**[P1] Notification badge and account-switcher menu are keyboard-unreachable**
Why it matters: both are `<div onclick>` elements with no `tabindex`, `role`, or keyboard handler — a keyboard-only user cannot open the one panel that surfaces personalized live alerts, the dashboard's flagship personalization feature.
Fix: real `<button>` elements (or `role="button" tabindex="0"` + Enter/Space handling), plus `aria-expanded`/`aria-haspopup` and an Escape-to-close handler.
Suggested command: `/impeccable audit` to enumerate the rest, `/impeccable harden` to fix.

**[P1] Live status and streamed chat answers have zero `aria-live` regions**
Why it matters: `aria-live` doesn't appear once across all 4 real pages. Status transitions and the chatbot's streamed SSE answer — the two places "what's happening right now" matters most — are silent to a screen reader. The flagship chatbot feature is functionally invisible to Sam until manually re-checked after the fact.
Fix: `aria-live="polite"` on `#status-text` and the chat panel-body container; consider reserving `assertive` for the final answer only, not every streaming chunk.
Suggested command: `/impeccable audit`, then `/impeccable harden`.

**[P2] `--ink-faint` fails WCAG AA contrast (~3.3:1 on `#050506`)**
Why it matters: used pervasively for functional metadata — timestamps, section notes, ticker/timeline detail, the "Table view" toggle label — not just decorative text. Hurts most exactly when glancing at a phone in bright light during a live broadcast.
Fix: lift the token to ~4.5:1+, or restrict the current value to genuinely decorative text only (e.g. photo credits).
Suggested command: `/impeccable colorize` or `/impeccable audit`.

**[P2] `doWhatIf()` has no input validation**
Why it matters: an empty/whitespace hypothesis can trigger a multi-minute backend generation job for nothing — inconsistent with the chat composer's own `if (!question) return;` guard three sections later in the same file.
Fix: mirror the chat composer's existing guard; disable Simulate until the input has content.
Suggested command: direct fix (small, mechanical).

## Persona Red Flags

**Alex (impatient power user, phone, mid-race glance)**: `home.html` renders a blank `#live-hero-slot` when no race is currently live — indistinguishable from a loading/broken state rather than a designed "no live race, here's your last one" placeholder. Landing on `index.html` before answering onboarding blocks the live dashboard behind a full-screen "who are you rooting for" modal (Skip exists but is visually secondary to the primary button) — one avoidable tap between Alex and the thing he opened the page for.

**Sam (accessibility-dependent, keyboard/screen-reader)**: Cannot open the notification badge or account-switcher at all (P1 above). Gets no live announcement of status changes or streamed chat answers (P1 above). The replay slider is natively keyboard-operable (a real pass) but has no `aria-label` — a user tabbing to it in isolation hears an unlabeled range control. Text inputs across the dashboard (`#race-search`, `#whatif-input`, chat composers) rely on placeholder-only text with no associated `<label>`, inconsistent with `settings.html`'s own correctly-labeled selects.

## Minor Observations

- `mh-sub` on `index.html` hardcodes "bilibili.com" as the platform even though `CURRENT-STATUS.md` states detection is explicitly not platform-locked — a live mismatch between backend capability and frontend copy.
- `.whatif-card` is reused for two structurally different cards (photo-backed catchup card vs. the actual simulator) — a naming collision invisible today but a real trap for the next styling pass.
- Auto-detected sessions with no identified GP name (e.g. `"F1 LIVE SESSION — 2026-08-03"`) render at the same visual weight as a properly-identified race card on `home.html`, with no visual cue that identification is pending.
- `doCatchup()`/`doSummary()` buttons read as uniformly slow even though the chart renders instantly and only the prose streams in afterward — undersells an already well-designed fast/slow split.

## Questions to Consider

1. If the replay slider is the single most powerful interaction on the page, why does it sit visually equal-weight with a stat strip and a raw-log toggle instead of the whole page being organized around it as the primary lens?
2. The backend already computes `notification_worthy`/`notification_hook` per event to know what matters to this specific viewer — why doesn't the dashboard use that same signal to visually promote anything, instead of showing every event at uniform weight?
3. `CURRENT-STATUS.md` frames this as one person's live-glance companion for a broadcast they're already half-watching — what would the page look like designed for a single glance under 3 seconds (one number, one verdict, one color), with everything on `index.html` today demoted to a drill-down?
