"""Retrieval-augmented free-form Q&A over one race session's real data.

Two chunk sources, both natural-language (not raw leaderboard OCR numbers,
which aren't semantically "askable" on their own):
  - phrased events (analysis.py's get_phrased_events output) -- headline +
    insight, already concise and high-signal.
  - audio commentary, grouped into fixed windows per source (screen/mic) so
    a single short utterance isn't embedded without enough context to be
    useful alone.

Incremental by design: index_new_content() only embeds chunks not already
in the session's index (by stable id), so the existing 5-minute background
refresh loop (app.py's _event_refresh_loop) can call this every tick during
a live race without re-embedding anything already done -- same
"cache what's already computed" principle as chunk_notes.json /
vision_corrections.json elsewhere in this project.

Storage is two parallel flat files per session (matches this project's
"plain file, no database" convention) rather than a real vector DB: at our
scale (a few hundred chunks per race) a brute-force cosine search over an
in-memory numpy array is comfortably sub-millisecond, so there is no reason
to stand up pgvector or similar for this.
"""

import json
import os
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

from analysis import _event_key

load_dotenv()

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_MODEL = "voyage-3-lite"
VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
EMBED_DIM = 512  # voyage-3-lite's real output size, confirmed by hand
EMBED_BATCH_SIZE = 64  # comfortably under Voyage's per-request cap
AUDIO_WINDOW_MS = 45_000  # group raw commentary into ~45s windows for embedding context

SESSIONS_DIR = Path(__file__).parent / "sessions"


def _chunks_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id / "rag_chunks.json"


def _embeddings_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id / "rag_embeddings.npy"


def _load_chunks(session_id: str) -> list[dict]:
    path = _chunks_path(session_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _load_embeddings(session_id: str) -> np.ndarray:
    path = _embeddings_path(session_id)
    return np.load(path) if path.exists() else np.zeros((0, EMBED_DIM), dtype=np.float32)


def _save(session_id: str, chunks: list[dict], embeddings: np.ndarray) -> None:
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    _chunks_path(session_id).write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    np.save(_embeddings_path(session_id), embeddings)


def _embed_batch(texts: list[str], input_type: str) -> np.ndarray:
    """input_type: 'document' for indexing, 'query' for search -- Voyage's
    asymmetric embeddings improve retrieval quality when the two sides are
    labeled, rather than embedding both the same way."""
    if not VOYAGE_API_KEY:
        raise RuntimeError("VOYAGE_API_KEY not set in .env")
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        resp = httpx.post(
            VOYAGE_URL,
            headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"},
            json={"input": batch, "model": VOYAGE_MODEL, "input_type": input_type},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        vectors.extend(item["embedding"] for item in data["data"])
    return np.array(vectors, dtype=np.float32)


def _event_chunks(events: list[dict]) -> list[dict]:
    chunks = []
    for e in events:
        if e.get("degraded") or e.get("importance") == 0:
            continue  # same filter as the frontend's usableEvents -- don't index noise
        text = f"Lap {e['lap']}" + (f"-{e['end_lap']}" if e.get("end_lap") else "")
        text += f" [{e['type']}] {e['headline']} {e.get('insight', '')}".strip()
        chunks.append(
            {
                "id": "event:" + _event_key(e),
                "text": text,
                "lap": e["lap"],
                "timestamp": None,
                "source": "event",
                "drivers": e.get("drivers", []),
            }
        )
    return chunks


def _audio_chunks(records: list[dict]) -> list[dict]:
    """Group consecutive same-source audio records into fixed windows so a
    single short utterance isn't embedded without context."""
    by_source: dict[str, list[dict]] = {}
    for r in records:
        if r.get("stream") != "audio":
            continue
        by_source.setdefault(r["source"], []).append(r)

    chunks = []
    for source, recs in by_source.items():
        recs.sort(key=lambda r: r["timestamp"])
        window_start = None
        window_texts: list[str] = []

        def _flush():
            if window_texts:
                chunks.append(
                    {
                        "id": f"audio:{source}:{window_start}",
                        "text": " ".join(window_texts),
                        "lap": None,
                        "timestamp": window_start,
                        "source": f"audio_{source}",
                        "drivers": [],
                    }
                )

        for r in recs:
            if window_start is None:
                window_start = r["timestamp"]
            elif r["timestamp"] - window_start > AUDIO_WINDOW_MS:
                _flush()
                window_start = r["timestamp"]
                window_texts = []
            window_texts.append(r["text"])
        _flush()
    return chunks


def index_new_content(session_id: str, events: list[dict], records: list[dict]) -> int:
    """Embed only chunks not already in the session's index. Returns how
    many new chunks were added (0 means already fully up to date -- the
    common case when this runs on every background refresh tick)."""
    existing = _load_chunks(session_id)
    existing_ids = {c["id"] for c in existing}
    candidates = _event_chunks(events) + _audio_chunks(records)
    new_chunks = [c for c in candidates if c["id"] not in existing_ids]
    if not new_chunks:
        return 0
    new_vectors = _embed_batch([c["text"] for c in new_chunks], input_type="document")
    all_chunks = existing + new_chunks
    existing_vectors = _load_embeddings(session_id)
    all_vectors = np.vstack([existing_vectors, new_vectors]) if len(existing) else new_vectors
    _save(session_id, all_chunks, all_vectors)
    return len(new_chunks)


def search(
    session_id: str,
    query: str,
    top_k: int = 6,
    max_lap: int | None = None,
    cutoff_ms: int | None = None,
) -> list[dict]:
    """Real semantic search, cosine similarity over the session's index.
    max_lap filters event chunks (lap-indexed), cutoff_ms filters audio
    chunks (timestamp-indexed) -- same "no lookahead past what's been shown
    so far" principle as the frontend's renderForLap, applied to whichever
    unit each chunk type is naturally keyed by."""
    chunks = _load_chunks(session_id)
    if not chunks:
        return []
    vectors = _load_embeddings(session_id)
    query_vec = _embed_batch([query], input_type="query")[0]
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec)
    norms[norms == 0] = 1e-9
    scores = (vectors @ query_vec) / norms
    order = np.argsort(-scores)

    results = []
    for i in order:
        c = chunks[i]
        if max_lap is not None and c.get("lap") is not None and c["lap"] > max_lap:
            continue
        if cutoff_ms is not None and c.get("timestamp") is not None and c["timestamp"] > cutoff_ms:
            continue
        results.append({**c, "score": float(scores[i])})
        if len(results) >= top_k:
            break
    return results
