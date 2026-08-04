// Sits in front of f1lightout.com / www.f1lightout.com. Tries the live
// origin (Jiani's Mac, reached via the Cloudflare Tunnel at
// origin.f1lightout.com) first, with a short timeout -- if that succeeds,
// the response is passed through untouched and the site behaves exactly
// as it does today (fully live, all interactive features work). Only when
// the origin is unreachable (Mac off/asleep, backend crashed, tunnel down)
// does it fall back to rendering a static page from the last snapshot a
// local sync job wrote to KV. The snapshot is read-only: no push
// subscribe, no What-If, no live polling -- just "here's where things
// stood as of the last sync."

const ORIGIN = "https://origin.f1lightout.com";
const ORIGIN_TIMEOUT_MS = 4000;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const originUrl = ORIGIN + url.pathname + url.search;

    // Cloudflare-edge-level failures (tunnel down, origin unreachable) come
    // back as a normal HTTP response with a 5xx status -- fetch() does NOT
    // throw for those, only for actual network-level errors. Both cases
    // mean "the Mac isn't answering" and both need the fallback, so treat
    // Cloudflare's own tunnel-error codes the same as a thrown exception.
    const CLOUDFLARE_TUNNEL_ERROR_CODES = new Set([502, 521, 522, 523, 524, 525, 526, 530]);
    try {
      const resp = await fetch(originUrl, {
        method: request.method,
        headers: request.headers,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual",
        signal: AbortSignal.timeout(ORIGIN_TIMEOUT_MS),
      });
      if (CLOUDFLARE_TUNNEL_ERROR_CODES.has(resp.status)) {
        return renderFallback(env, url);
      }
      return resp;
    } catch (err) {
      return renderFallback(env, url);
    }
  },
};

async function renderFallback(env, url) {
  const raw = await env.F1_SNAPSHOT.get("snapshot");
  if (!raw) {
    return new Response(shellHTML(`
      <div class="banner">Live view is offline right now, and no snapshot has been synced yet.</div>
      <div class="empty">Once Jiani's machine syncs at least once, a cached view will show up here automatically.</div>
    `), { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return new Response(shellHTML(`<div class="banner">Snapshot is corrupted -- waiting for the next sync.</div>`), {
      status: 200, headers: { "content-type": "text/html; charset=utf-8" },
    });
  }

  const syncedAt = data.synced_at ? new Date(data.synced_at).toLocaleString("en-US", { timeZone: "UTC" }) + " UTC" : "unknown time";
  const sessions = Array.isArray(data.sessions) ? data.sessions : [];
  const liveSession = data.live_session || null;

  const sessionCards = sessions.length
    ? sessions.map(sessionCard).join("")
    : `<div class="empty">No races captured yet.</div>`;

  const liveBlock = liveSession ? `
    <div class="card live-card">
      <div class="live-tag">Live (as of last sync)</div>
      <div class="round">${escapeHtml(liveSession.round || "")}</div>
      <div class="name">${escapeHtml(liveSession.name || "")}</div>
      ${(liveSession.events || []).length ? `
        <div class="events-label">Captured events</div>
        <div class="events">
          ${(liveSession.events || []).slice(-8).reverse().map(eventRow).join("")}
        </div>` : `<div class="events-label">No events captured yet in this session.</div>`}
    </div>` : "";

  if (url.pathname.startsWith("/race")) {
    return new Response(shellHTML(`
      <div class="banner">⚠ Live view is offline (Jiani's machine is asleep/off) -- showing the last synced snapshot from ${syncedAt}. Nothing here updates until it's back.</div>
      ${liveBlock || `<div class="empty">No live session in the last snapshot.</div>`}
      <a class="back" href="/">← All races</a>
    `), { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
  }

  return new Response(shellHTML(`
    <div class="banner">⚠ Live view is offline right now (Jiani's machine is asleep/off) -- showing a cached snapshot from ${syncedAt}. Real-time updates, notifications, and What-If resume once it's back online.</div>
    ${liveBlock}
    <div class="section-label">Past Sessions</div>
    <div class="grid">${sessionCards}</div>
  `), { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
}

function sessionCard(s) {
  const statusLabel = s.status === "ended" ? "Completed" : "Idle";
  return `
    <div class="card">
      <span class="status ${s.status === "ended" ? "ended" : "idle"}">${statusLabel}</span>
      <div class="round">${escapeHtml(s.round || "")}</div>
      <div class="name">${escapeHtml(s.name || "")}</div>
      <div class="date">${s.start_ms ? new Date(s.start_ms).toISOString().slice(0, 10) : "—"}</div>
    </div>`;
}

function eventRow(e) {
  return `<div class="event"><span class="lap">Lap ${e.lap ?? "?"}</span> ${escapeHtml(e.headline || "")}</div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function shellHTML(body) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>F1 Race Control — Offline Snapshot</title>
<style>
  :root {
    --track: #050506; --surface: #101013; --hairline: rgba(255,255,255,0.1);
    --ink: #f5f5f3; --ink-dim: #9c9c9f; --ink-faint: #616164;
    --f1-red: #E10600; --amber-dim: rgba(245,166,35,0.14); --amber: #f5a623;
    --green: #17c964; --green-dim: rgba(23,201,100,0.14);
    --mono: "SF Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace;
    --sans: -apple-system, "Segoe UI", sans-serif;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--track); color: var(--ink); font-family: var(--sans); padding: 30px 20px 60px; }
  main { max-width: 900px; margin: 0 auto; }
  h1 { font: 800 20px var(--sans); border-bottom: 3px solid var(--f1-red); padding-bottom: 12px; margin: 0 0 20px; }
  .banner { background: var(--amber-dim); color: var(--amber); border: 1px solid rgba(245,166,35,0.3); border-radius: 10px; padding: 14px 16px; font: 600 13px/1.5 var(--sans); margin-bottom: 22px; }
  .section-label { font: 800 14px var(--sans); margin: 26px 0 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
  .card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 12px; padding: 16px; }
  .live-card { border-color: rgba(225,6,0,0.3); margin-bottom: 10px; }
  .live-tag { display: inline-block; font: 800 10px/1 var(--mono); letter-spacing: .1em; color: #fff; background: var(--f1-red); padding: 4px 9px; border-radius: 20px; text-transform: uppercase; }
  .status { display: inline-block; font: 800 10px/1 var(--mono); letter-spacing: .1em; padding: 4px 9px; border-radius: 20px; text-transform: uppercase; }
  .status.ended { background: var(--green-dim); color: var(--green); }
  .status.idle { background: rgba(255,255,255,0.06); color: var(--ink-faint); }
  .round { font: 700 10.5px/1 var(--mono); letter-spacing: .1em; color: var(--ink-faint); text-transform: uppercase; margin-top: 12px; }
  .name { font: 800 15px var(--sans); margin-top: 5px; }
  .date { font: 600 12px var(--mono); color: var(--ink-faint); margin-top: 8px; }
  .events-label { font: 700 11px var(--mono); letter-spacing: .06em; color: var(--ink-faint); text-transform: uppercase; margin-top: 16px; }
  .events { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
  .event { font: 500 13px/1.5 var(--sans); color: var(--ink-dim); border-top: 1px solid var(--hairline); padding-top: 8px; }
  .event .lap { font: 700 11px var(--mono); color: var(--ink-faint); margin-right: 8px; }
  .empty { color: var(--ink-faint); font: 500 13px var(--sans); padding: 20px 0; }
  .back { display: inline-block; margin-top: 20px; color: var(--ink-dim); font: 600 12px var(--sans); text-decoration: none; }
</style>
</head>
<body>
<main>
  <h1>F1 RACE CONTROL — Offline Snapshot</h1>
  ${body}
</main>
</body>
</html>`;
}
