// Cloud-side "post-race summary" generation -- makes this feature work for
// an ENDED session even when Jiani's Mac is off, by calling the Anthropic
// API directly (Workers cannot shell out to the `claude -p` CLI the way
// the local backend does) against the full commentary log
// backend/sync_snapshot.py uploaded for that session.
//
// Scope, on purpose: ended sessions only. A still-live session has no
// synced log at all (sync_ended_session_logs in sync_snapshot.py never
// touches an active session) -- there is nothing new to generate about a
// race that is not actually being watched by anyone right now, and that
// is a separate, harder problem (see the "who is watching" discussion)
// this does not attempt to solve.
//
// v1 simplification, disclosed rather than silently shipped: the local
// backend's summary() switches to a chunked map-reduce pipeline above 400
// records (CHUNK_RECORD_THRESHOLD in analysis.py) because a single
// `claude -p` call reliably timed out on a full real race's ~2000+
// records. This Worker instead sends the whole formatted log in one
// Anthropic API call -- verified for real against the one full race on
// record (2238 records, ~140k prompt tokens) that this fits comfortably
// inside a 200k-token context with room to spare, and a single well-
// resourced API call does not carry the same practical timeout pressure
// the CLI subprocess path was built around. TRUNCATE_CHARS below is a
// defensive cap for a future much-longer session, not something the one
// real session tested here ever hits.

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_MODEL = "claude-sonnet-5";
const TRUNCATE_CHARS = 700_000; // ~175k tokens, leaves headroom under a 200k context

// Copied verbatim from backend/analysis.py's COMMENTATOR_TONE_NOTE /
// ANALYSIS_DEPTH_NOTE -- same prompt, same voice, whether the call runs
// locally via `claude -p` or here via the API. Keep these two in sync by
// hand if the source prompts change; there is no shared-import mechanism
// between a Python backend and a Workers JS bundle.
const COMMENTATOR_TONE_NOTE =
  "Writing tone: you're a live TV broadcast commentator, not an analyst writing a quarterly " +
  "report. Write in English, conversational, short sentences, with genuine reactions ('what a " +
  "move', 'that's costly', 'he's holding on') like you're chatting with a friend watching the " +
  "race, not report-speak ('overall, the data shows', 'from a strategic perspective'). But the " +
  "content must stay completely faithful to the source records -- the tone can be lively, but " +
  "facts can't be invented; say so plainly when you're unsure instead of guessing for effect.";

const ANALYSIS_DEPTH_NOTE =
  "Important -- don't just restate raw information that's already in the records in different " +
  "words, that's something the viewer could already see from watching the broadcast, no added " +
  "value. What you should do is analyze and infer:\n" +
  "1) Cross-record inference -- e.g. if one frame only clearly shows driver A's lap time/gap, " +
  "but nearby frames show other drivers' gaps to the leader, combine them to back out numbers " +
  "that were never directly read (driver B's approximate lap pace, position changes). Don't skip " +
  "mentioning something just because OCR never captured it directly.\n" +
  "2) Compute deltas and trends -- two drivers' gaps to the leader can be subtracted to get the " +
  "real gap between the two of them, and whether that gap is growing, shrinking, or oscillating " +
  "-- that 'relationship' and 'rate of change' isn't a number that exists directly in the raw data.\n" +
  "3) Cross-stream correlation -- vision (on-screen text) and audio (commentary) often each only " +
  "carry half the picture; find where they corroborate or explain each other (e.g. a sudden gap " +
  "change on screen, and the audio happens to mention a mechanical issue or a pit stop).\n" +
  "4) Tire/pit strategy is mandatory, not optional -- soft/hard/medium compound choices, pit lap, " +
  "stop duration, whether an undercut/overcut worked, lap-time deltas between compounds -- this " +
  "usually only appears in audio, not the on-screen leaderboard, and gets missed easily; whenever " +
  "the records mention tires even in passing, combine it with lap-time/gap data to work out the " +
  "real impact (e.g. how many seconds per lap a driver gained from a tire advantage, and how many " +
  "laps that takes to close a given gap). Don't skip it just because the source mentions are scattered.\n" +
  "Only conclusions that required this kind of inference are worth writing; don't just restate " +
  "what one record said.";

function formatRecords(jsonlText) {
  const lines = jsonlText.split("\n").filter((l) => l.trim());
  const formatted = [];
  for (const line of lines) {
    let r;
    try {
      r = JSON.parse(line);
    } catch {
      continue; // skip a malformed line rather than failing the whole generation
    }
    if (r.stream === "vision") {
      formatted.push(`[vision ${r.timestamp}] ${r.text}`);
    } else {
      formatted.push(`[audio/${r.source} ${r.timestamp}] ${r.text}`);
    }
  }
  let body = formatted.join("\n");
  let truncated = false;
  if (body.length > TRUNCATE_CHARS) {
    body = body.slice(0, TRUNCATE_CHARS);
    truncated = true;
  }
  return { body, truncated, recordCount: lines.length };
}

async function callAnthropic(env, prompt) {
  const resp = await fetch(ANTHROPIC_API_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: ANTHROPIC_MODEL,
      // Real bug found running this for the first time: this model defaults
      // to extended thinking, which draws from the SAME max_tokens budget --
      // at max_tokens: 2048 the entire budget went to an empty "thinking"
      // block (verified via a raw response dump) and zero tokens were left
      // for the actual answer, so `content` had no "text" block at all.
      // Explicitly disabled -- a post-race summary doesn't need visible
      // step-by-step reasoning, just the answer -- and max_tokens raised as
      // a safety margin regardless of thinking state.
      thinking: { type: "disabled" },
      max_tokens: 4096,
      messages: [{ role: "user", content: prompt }],
    }),
  });
  if (!resp.ok) {
    const errText = await resp.text().catch(() => "");
    throw new Error(`Anthropic API ${resp.status}: ${errText.slice(0, 300)}`);
  }
  const data = await resp.json();
  return (data.content || []).map((b) => b.text || "").join("");
}

// Generates (or returns the cached copy of) a post-race summary for an
// ENDED session. Cached forever once generated -- an ended session's log
// never changes again, same reasoning as the local backend's answer_cache
// keyed on _records_mtime.
export async function generateSummary(env, sessionId) {
  const cacheKey = `summary-cache:${sessionId}`;
  const cached = await env.F1_SNAPSHOT.get(cacheKey);
  if (cached) {
    return { text: cached, cached: true };
  }

  const logText = await env.F1_SNAPSHOT.get(`session-log:${sessionId}`);
  if (!logText) {
    throw new Error("No synced log for this session yet -- it may still be live, or has not synced.");
  }

  const { body, truncated, recordCount } = formatRecords(logText);
  const note = truncated
    ? "(mixed vision + audio records, sorted by time -- truncated to the first portion, this session's log was unusually long)"
    : "(mixed vision + audio records, sorted by time)";

  const prompt =
    `${COMMENTATOR_TONE_NOTE}\n\n${ANALYSIS_DEPTH_NOTE}\n\n` +
    `Below are the complete real records from an F1 race ${note}. ` +
    "Write a post-race summary (a few paragraphs at most) covering how the race unfolded, key " +
    `events (overtakes/pit stops/safety cars/penalties), and the final position trends.\n\n${body}`;

  const text = await callAnthropic(env, prompt);
  await env.F1_SNAPSHOT.put(cacheKey, text);
  return { text, cached: false, recordCount, truncated };
}
