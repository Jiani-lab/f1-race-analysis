---
name: ocr-data-reliability
description: >
  Use when writing, reviewing, or debugging any code in this project that
  consumes Luci/OCR-derived race data -- retrieval.py's extraction functions,
  analysis.py's event pipeline, or any frontend logic in index.html that
  derives a ranking, comparison, chart, or narrative from strategy_trend.json
  / /session/events. Also use when a user reports a dashboard number, label,
  or "who's ahead" reading that looks wrong -- check this playbook's failure
  modes before assuming it's a fresh bug class.
---

# OCR Data Reliability Playbook

This file exists because of a real batch of bugs found on 2026-08-03, all
traced back to a small number of recurring failure modes in Luci's
screen-OCR-derived race data. About half were genuine Claude-authored logic
bugs (sign conventions, missing edge-case handling); the other half were
inherent characteristics of reading a live broadcast leaderboard via OCR
frame-by-frame. Neither category is fixed by "better parsing" alone -- the
first needs careful code, the second needs defensive code that assumes the
input is noisy in specific, characterizable ways. This playbook is that
defensive layer, written down so it gets applied by default instead of
rediscovered one user-reported bug at a time.

## Known failure modes, and the guard already built for each

**1. Large within-lap spread can be a real event, not corruption -- don't
average across it either way, and prefer re-verifying over guessing.**
Original case: Lindblad and Lawson's gap values swung from ~0.2s to ~39s
within lap 63's capture window, which read like a corrupted OCR pairing
swap. Re-checked against Luci's `get_detail` (real per-block screen
coordinates, not the flattened OCR text GAP_RE/_extract_columnar_gaps
parse) and found the regex extraction had actually paired everything
correctly all along -- both readings were real, just from before/after a
real mid-lap event (almost certainly a pit stop). Correction for the
record: don't assume a wide within-lap spread means corrupted pairing;
it can be genuine. **Guards, in preference order:**
(a) `correct_unreliable_frames()` in retrieval.py re-derives {driver: gap}
for any lap with spread > `UNRELIABLE_SPREAD_THRESHOLD` (8s) straight from
`get_detail`'s per-block `focusRect` coordinates, pairing driver-code and
gap-value tokens by shared row (nearest-Y, restricted to the leaderboard's
real X-range to avoid cross-matching sponsor-banner text -- a real bug
caught building this: an ad fragment reading "PER" cross-matched a
different driver's gap value purely on Y-proximity before the X-range
restriction was added). This is a deterministic geometry fix, no LLM call,
and it tells you what actually happened instead of just discarding the lap.
(b) Where (a) isn't available or fails: `reliableMedian()` in index.html
still rejects a lap's raw readings for a driver if `max - min` exceeds the
same threshold before taking the median -- correct to do regardless of
whether the cause is a pairing swap or a real transition, since averaging
across either fabricates a value that represents neither state. Apply (a)
first when building anything new that aggregates multiple raw OCR readings
per (entity, time-bucket); fall back to (b) as the cheap safety net.

**2. A missing row is not proof the corresponding entity is "the leader"
(or otherwise structurally absent) -- it can just be a missed capture.**
`rankAtLap()`'s implicit-leader inference ("whoever has no gap reading is
the leader") is a real, useful heuristic, but its own comments already
documented the risk: a single stray missed OCR row on an otherwise
well-covered lap reads identically to a genuine leader. Real case: Antonelli
got inferred as the leader from a lap where he simply wasn't captured,
producing a momentum card that said "leading" while the pairwise data (his
last real reading vs. the driver behind him) said the opposite. **Guard:**
don't trust a structural inference (leader-by-omission, retired-by-omission,
etc.) in isolation when a corroborating direct reading is available and
disagrees -- prefer the inference for primary framing (it's been through the
`RANK_WELL_COVERED_MIN` threshold), but degrade to a neutral message rather
than asserting something the direct data contradicts. See the `i === 0`
branch in the momentum-card builder in index.html for the pattern.

**3. Raw OCR/vision evidence text is not display-ready.**
`analysis.py`'s `_degraded_event()` (the LLM-phrasing-timeout fallback) used
to headline events with the first 60 chars of raw evidence text verbatim.
Real case: that raw text contained a macOS "can't connect to iCloud" system
notification banner and a streamer's watermark that happened to be on screen
during capture -- OCR read them faithfully (not an OCR error), but the code
had no business showing raw capture noise as if it were a phrased headline.
**Guard:** `_degraded_event()` now sets an explicit `degraded: true` flag;
the frontend's `usableEvents()` filters out anything degraded (or
`importance === 0`, which only this fallback path produces) before it
reaches any UI surface. Any new "best-effort fallback when generation
fails" path must degrade to something explicitly marked non-final, never to
raw capture text presented as finished content.

**4. Coverage is genuinely sparse and uneven, especially for whoever is
currently leading (leaders have no gap reading by definition).**
Real case: the "closest battle" picker chose whichever adjacent pair had the
smallest gap-diff at a single snapshot lap, without checking how much shared
history backed that reading -- surfaced a "closest battle" backed by only 2
real overlapping data points because the leader (Norris) has almost no gap
readings at all. **Guard:** `featuredDuel()` requires
`MIN_DUEL_DATAPOINTS` (5) shared readings before preferring a pair, falling
back to the closest snapshot pair only if nothing qualifies -- and when it
does fall back, that's an honest reflection of real data scarcity for that
stretch of the race, not something to paper over.

**5. A reading can be real but stale -- don't present it as current state.**
Real case: Norris's momentum card kept showing "falling behind, 1.50s off
the lead" through the entire back half of the race because that was his
last gap reading from BEFORE he retook the lead on lap ~17, and nothing
since then ever overwrote it (he had no further gap readings once back in
front). **Guard:** `momentumRelative()`/`momentumAbsolute()` both take the
current `lap` and return null if the last supporting datapoint is more than
`MAX_STALE_LAPS` (10) laps behind it. The "no data" fallback message is
worded to be honest whether data never existed or just aged out -- don't
say "never captured" when the real situation is "aged out."

**6. Sign/direction conventions must be checked against a known ground
truth before shipping, not just for internal consistency.**
Real case: `relativePairRows()` correctly documented `diff > 0 = favored
(codeFavored) ahead`, but `renderTerritoryChart()` -- a separate function
consuming that same `diff` -- had its own comment and every `diff >= 0 ? X :
Y` ternary backwards, so the chart confidently displayed the wrong driver as
leading. This wasn't caught by testing "does the chart render" -- it was
only caught because the user knew Norris won the race and the chart said
otherwise. **Guard:** when a new function consumes a value with a documented
sign convention, verify it against ONE fact you already know is true (a
known race winner, a known retirement, a known lead change) before trusting
that "it renders without errors" means "it's correct."

## Before shipping any new OCR-derived comparison, ranking, or chart

- [ ] If aggregating multiple raw readings into one value: re-verify
      high-spread single-bucket readings via get_detail's structured blocks
      rather than averaging through them; only fall back to plain rejection
      if re-verification isn't wired up yet (pattern 1).
- [ ] If inferring something from absence (missing row = X): check whether
      a corroborating direct reading exists and disagrees (pattern 2).
- [ ] If falling back on a generation/extraction failure: mark it
      explicitly non-final, never surface raw capture text as finished
      content (pattern 3).
- [ ] If picking a "best" pairing/entity from a snapshot: require a minimum
      amount of supporting data, don't spotlight a coincidentally-close but
      barely-supported result (pattern 4).
- [ ] If showing "current state" derived from a driver/entity's own sparse
      history: guard against staleness, and word the empty-state message to
      cover both "never had data" and "data aged out" (pattern 5).
- [ ] Before considering it done: check the output against at least one
      fact you already know is true from the real race, not just that it
      renders (pattern 6).
