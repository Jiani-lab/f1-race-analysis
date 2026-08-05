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
//
// The fallback page's own visual assets (masthead photo) are served via
// the ASSETS binding (wrangler.toml [assets]) -- Cloudflare's own edge,
// not the origin -- on purpose: if they went through origin.f1lightout.com
// like the live site's images do, they'd be exactly as unreachable as
// everything else on a Mac that's off, defeating the point.

const ORIGIN = "https://origin.f1lightout.com";
const ORIGIN_TIMEOUT_MS = 4000;
const ASSET_PREFIX = "/fallback-assets/";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Fallback-page assets always serve from Cloudflare's own edge,
    // regardless of origin health -- never proxied to the Mac.
    if (url.pathname.startsWith(ASSET_PREFIX)) {
      const assetUrl = new URL(request.url);
      assetUrl.pathname = url.pathname.slice(ASSET_PREFIX.length - 1); // keep leading /
      return env.ASSETS.fetch(new Request(assetUrl, request));
    }

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
    : `<div class="empty-state">No races captured yet.</div>`;

  // Every session card links here (?session=<id>) same as the live site --
  // each session's events were synced too (not just whichever was live at
  // sync time), so this actually has real content to show, not just a
  // "come back when the Mac is on" dead end.
  if (url.pathname.startsWith("/race")) {
    const sessionId = url.searchParams.get("session");
    const target = sessionId
      ? sessions.find((s) => s.session_id === sessionId)
      : liveSession;

    if (!target) {
      return new Response(shellHTML(`
        <div class="banner">⚠ Offline snapshot from ${syncedAt} — this session wasn't in it (never synced, or the ID doesn't match).</div>
        <a class="back-link" href="/">← All races</a>
      `), { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
    }

    const isLive = target.status === "active";
    return new Response(shellHTML(`
      <div class="banner">⚠ Live view is offline (Jiani's machine is asleep/off) — showing the last synced snapshot from ${syncedAt}. Nothing here updates until it's back${isLive ? " — this session was still live at last sync" : ""}.</div>
      <div class="card ${isLive ? "live-card" : ""}">
        ${isLive ? `<span class="live-tag"><span class="dot"></span>Live (as of last sync)</span>` : `<span class="status ${target.status === "ended" ? "ended" : "idle"}"><span class="dot"></span>${target.status === "ended" ? "Completed" : "Idle"}</span>`}
        <div class="round">${escapeHtml(target.round || "")}</div>
        <div class="name">${escapeHtml(target.name || "")}</div>
        ${(target.events || []).length ? `
          <div class="events-label">Captured events</div>
          <div class="events">
            ${(target.events || []).slice(-8).reverse().map(eventRow).join("")}
          </div>` : `<div class="events-label">No events captured for this session.</div>`}
      </div>
      <a class="back-link" href="/">← All races</a>
    `), { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
  }

  const liveBlock = liveSession ? `
    <a class="card live-card link-card" href="/race?session=${encodeURIComponent(liveSession.session_id)}">
      <span class="live-tag"><span class="dot"></span>Live (as of last sync)</span>
      <div class="round">${escapeHtml(liveSession.round || "")}</div>
      <div class="name">${escapeHtml(liveSession.name || "")}</div>
      <div class="cta">Open (offline snapshot) →</div>
    </a>` : "";

  return new Response(shellHTML(`
    <div class="intro">
      <h1>Your races</h1>
      <p>Offline snapshot — real-time updates, notifications, and What-If resume once the live machine is back.</p>
    </div>
    <div class="banner">⚠ Live view is offline right now — showing a cached snapshot from ${syncedAt}.</div>
    ${liveBlock}
    <div class="section-head"><h2>Past Sessions</h2><span class="count">${sessions.length} race${sessions.length === 1 ? "" : "s"}</span></div>
    <div class="grid">${sessionCards}</div>
  `), { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
}

function sessionCard(s) {
  const statusLabel = s.status === "ended" ? "Completed" : "Idle";
  return `
    <a class="card link-card" href="/race?session=${encodeURIComponent(s.session_id)}">
      <span class="status ${s.status === "ended" ? "ended" : "idle"}"><span class="dot"></span>${statusLabel}</span>
      <div class="round">${escapeHtml(s.round || "")}</div>
      <div class="name">${escapeHtml(s.name || "")}</div>
      <div class="date">${s.start_ms ? new Date(s.start_ms).toISOString().slice(0, 10) : "—"}</div>
      <div class="cta">Open (offline snapshot) →</div>
    </a>`;
}

function eventRow(e) {
  return `<div class="event"><span class="lap">Lap ${e.lap ?? "?"}</span> ${escapeHtml(e.headline || "")}</div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Same checkered-flag mark used in the live site's masthead (frontend/home.html)
// -- inline SVG, no image dependency, so it renders even if ASSETS somehow failed.
const FLAG_ICON_SVG = `
  <svg width="34" height="40" viewBox="0 0 34 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <rect x="2" y="2" width="3" height="37" rx="1.5" fill="#9c9c9f"/>
    <path d="M5 3 C 14 -1, 22 7, 31 3 L 31 21 C 22 25, 14 17, 5 21 Z" fill="#f5f5f3"/>
    <g fill="#101013">
      <rect x="5" y="3" width="4.3" height="4.5"/><rect x="13.6" y="2.4" width="4.3" height="4.5"/><rect x="22.2" y="3.6" width="4.3" height="4.5"/>
      <rect x="9.3" y="7.5" width="4.3" height="4.5"/><rect x="17.9" y="6.9" width="4.3" height="4.5"/><rect x="26.5" y="8.1" width="4.3" height="4.5"/>
      <rect x="5" y="12" width="4.3" height="4.5"/><rect x="13.6" y="11.4" width="4.3" height="4.5"/><rect x="22.2" y="12.6" width="4.3" height="4.5"/>
      <rect x="9.3" y="16.5" width="4.3" height="4.5"/><rect x="17.9" y="15.9" width="4.3" height="4.5"/>
    </g>
  </svg>`;

function shellHTML(body) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>F1 Race Control — Offline Snapshot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Saira+Condensed:ital,wght@0,500;0,600;0,700;0,800;0,900;1,900&display=swap" rel="stylesheet">
<style>
  :root {
    --track: #050506; --surface: #101013; --surface-raised: #17171b;
    --hairline: rgba(255,255,255,0.08); --hairline-strong: rgba(255,255,255,0.18);
    --ink: #f5f5f3; --ink-dim: #9c9c9f; --ink-faint: #616164;
    --f1-red: #E10600; --f1-red-bright: #ff2a1f;
    --amber-dim: rgba(245,166,35,0.14); --amber: #f5a623;
    --green: #17c964; --green-dim: rgba(23,201,100,0.14);
    --mono: "SF Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace;
    --sans: -apple-system, "Segoe UI", sans-serif;
    --sans-display: "Saira Condensed", "Helvetica Neue Condensed Bold", "Arial Narrow", "Roboto Condensed", var(--sans);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0 0 60px; background: var(--track); color: var(--ink); font-family: var(--sans);
    background-image: repeating-linear-gradient(115deg, rgba(255,255,255,0.014) 0px, rgba(255,255,255,0.014) 1px, transparent 1px, transparent 64px);
  }
  main { max-width: 1080px; margin: 0 auto; padding: 0 20px; }
  a { color: inherit; }

  .masthead { position: relative; background: linear-gradient(180deg, #170f0e 0%, var(--track) 100%); border-bottom: 3px solid var(--f1-red); padding: 22px 20px 20px; overflow: hidden; margin-bottom: 30px; }
  .masthead::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: linear-gradient(90deg, var(--track) 0%, rgba(5,5,6,0.82) 38%, rgba(5,5,6,0.1) 100%), url('${ASSET_PREFIX}img/masthead-track.jpg');
    background-repeat: no-repeat, no-repeat; background-size: 100% 100%, cover; background-position: 0 0, center 65%;
  }
  .masthead::after {
    content: ""; position: absolute; inset: 0; pointer-events: none; opacity: 0.05;
    background-image: repeating-conic-gradient(#fff 0% 25%, transparent 0% 50%); background-size: 16px 16px;
    -webkit-mask-image: linear-gradient(90deg, transparent, #000 30%, #000 70%, transparent);
            mask-image: linear-gradient(90deg, transparent, #000 30%, #000 70%, transparent);
  }
  .masthead-inner { position: relative; max-width: 1080px; margin: 0 auto; }
  .mh-title-row { display: flex; align-items: center; gap: 12px; }
  .mh-round { font: 700 11.5px/1 var(--mono); letter-spacing: 0.16em; color: var(--f1-red-bright); text-transform: uppercase; }
  .mh-title { font: italic 900 clamp(24px, 4.4vw, 32px)/1.1 var(--sans-display); letter-spacing: -0.01em; margin: 5px 0 0; }
  .mh-sub { font: 500 14.5px/1.5 var(--sans); color: var(--ink-dim); margin-top: 5px; max-width: 480px; }

  .intro h1 { font: italic 900 clamp(24px, 3.6vw, 30px)/1.2 var(--sans-display); margin: 0 0 6px; }
  .intro p { font: 500 14px/1.6 var(--sans); color: var(--ink-dim); margin: 0 0 20px; max-width: 600px; }

  .banner { background: var(--amber-dim); color: var(--amber); border: 1px solid rgba(245,166,35,0.3); border-radius: 10px; padding: 14px 16px; font: 600 13px/1.5 var(--sans); margin-bottom: 22px; }
  .section-head { display: flex; align-items: baseline; gap: 10px; margin: 30px 0 14px; }
  .section-head h2 { font: 700 clamp(18px, 2.4vw, 21px)/1.2 var(--sans-display); letter-spacing: -0.005em; margin: 0; }
  .section-head .count { font: 600 13px var(--sans); color: var(--ink-faint); }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
  .card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 14px; padding: 18px; }
  .live-card { border-color: rgba(225,6,0,0.3); background: linear-gradient(150deg, #1c0b0a 0%, #100708 55%, #0a0a0c 100%); margin-bottom: 16px; }
  .live-tag { display: inline-flex; align-items: center; gap: 7px; font: 800 11px/1 var(--mono); letter-spacing: .12em; color: #fff; background: var(--f1-red); padding: 5px 11px 5px 9px; border-radius: 20px; text-transform: uppercase; }
  .live-tag .dot { width: 7px; height: 7px; border-radius: 50%; background: #fff; }
  .status { display: inline-flex; align-items: center; gap: 6px; font: 800 10px/1 var(--mono); letter-spacing: .1em; padding: 4px 9px; border-radius: 20px; text-transform: uppercase; }
  .status .dot { width: 6px; height: 6px; border-radius: 50%; }
  .status.ended { background: var(--green-dim); color: var(--green); }
  .status.ended .dot { background: var(--green); }
  .status.idle { background: rgba(255,255,255,0.06); color: var(--ink-faint); }
  .status.idle .dot { background: var(--ink-faint); }
  .round { font: 700 10.5px/1 var(--mono); letter-spacing: .1em; color: var(--ink-faint); text-transform: uppercase; margin-top: 13px; }
  .name { font: 800 16px var(--sans-display); margin-top: 6px; }
  .date { font: 600 12px var(--mono); color: var(--ink-faint); margin-top: 10px; }
  .link-card { display: block; text-decoration: none; transition: border-color .15s; }
  .link-card:hover { border-color: var(--hairline-strong); }
  .cta { font: 700 11.5px/1 var(--mono); letter-spacing: .04em; color: var(--f1-red); margin-top: 14px; text-transform: uppercase; }
  .link-card:hover .cta { color: var(--f1-red-bright); }
  .events-label { font: 700 11px var(--mono); letter-spacing: .06em; color: var(--ink-faint); text-transform: uppercase; margin-top: 16px; }
  .events { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
  .event { font: 500 13px/1.5 var(--sans); color: var(--ink-dim); border-top: 1px solid var(--hairline); padding-top: 8px; }
  .event .lap { font: 700 11px var(--mono); color: var(--ink-faint); margin-right: 8px; }
  .empty-state { font: 500 14px/1.7 var(--sans); color: var(--ink-faint); padding: 30px 4px; text-align: center; border: 1px dashed var(--hairline-strong); border-radius: 12px; }
  .back-link { display: inline-block; margin-top: 20px; color: var(--ink-dim); font: 700 12px var(--sans-display); text-decoration: none; }
</style>
</head>
<body>

<div class="masthead">
  <div class="masthead-inner">
    <div class="mh-round">LIVE-WIRED DASHBOARD</div>
    <div class="mh-title-row">
      <span style="filter: drop-shadow(0 3px 8px rgba(0,0,0,0.5))">${FLAG_ICON_SVG}</span>
      <div class="mh-title">F1 RACE CONTROL</div>
    </div>
    <div class="mh-sub">Real screen + audio capture, real recall, no scripted content</div>
  </div>
</div>

<main>
  ${body}
</main>
</body>
</html>`;
}
