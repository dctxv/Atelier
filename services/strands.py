"""Strand registry — Prescient Memory Part 1, §0.2.

Strands are predicate/subject bundles that aggregate related memory atoms
into named life-area timelines (career, places, relationships, projects,
health, creative).  Stored in app_config key 'memory.strands' as a JSON
array.  Membership is a view (atoms may belong to multiple strands).

Visibility Law (restated per design mandate):
  Nothing inferred enters chat context until user-confirmed or explicitly
  tagged as inference at render time.  Strand metadata is never injected
  into chat; it is a UI-only surface.

The embedder is currently a lexical hashing fallback, not semantic.
Clustering below uses conservative cosine thresholds and a hard cap to
defend against nonsensical clusters; thresholds are app_config knobs.
"""
from __future__ import annotations

import json

from . import config, db, memory

_REGISTRY_KEY = "memory.strands"

_STATIC_BUNDLES: list[dict] = [
    {
        "id": "career",
        "name": "Career",
        "kind": "static",
        "predicates": ["employer", "job_title", "working_on"],
        "subjects": [],
    },
    {
        "id": "places",
        "name": "Places",
        "kind": "static",
        "predicates": ["lives_in", "visited"],
        "subjects": [],
    },
    {
        "id": "relationships",
        "name": "Relationships",
        "kind": "static",
        "predicates": ["partner"],
        "subjects": [],
    },
    {
        "id": "projects",
        "name": "Projects",
        "kind": "static",
        "predicates": ["working_on", "building", "shipped"],
        "subjects": [],
    },
    {
        "id": "health",
        "name": "Health",
        "kind": "static",
        "predicates": ["exercise", "sleep", "diet", "symptom", "injury"],
        "subjects": [],
    },
    {
        "id": "creative",
        "name": "Creative",
        "kind": "static",
        "predicates": ["writing", "making", "composing", "hobby"],
        "subjects": [],
    },
]


async def load_registry() -> list[dict]:
    raw = await config.get_setting(_REGISTRY_KEY)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Strand registry JSON corrupted; falling back to static bundles"
        )
        return []


async def save_registry(strands: list[dict]) -> None:
    await config.set_setting(_REGISTRY_KEY, json.dumps(strands))


async def strand_bootstrap() -> None:
    """Initialise static strand bundles if not already present. Idempotent."""
    existing = await load_registry()
    existing_ids = {s["id"] for s in existing}
    added = False
    for bundle in _STATIC_BUNDLES:
        if bundle["id"] not in existing_ids:
            existing.append({**bundle, "created_at": db.now()})
            added = True
    if added:
        await save_registry(existing)


async def add_strand(name: str, predicates: list[str]) -> dict:
    """Add a user-created strand to the registry. Returns the new strand dict."""
    import re
    import uuid
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or str(uuid.uuid4())[:8]
    registry = await load_registry()
    # Ensure slug uniqueness
    existing_ids = {s["id"] for s in registry}
    sid = slug
    n = 2
    while sid in existing_ids:
        sid = f"{slug}_{n}"
        n += 1
    strand = {
        "id": sid,
        "name": name,
        "kind": "user",
        "predicates": [p.lower() for p in predicates],
        "subjects": [],
        "created_at": db.now(),
    }
    registry.append(strand)
    await save_registry(registry)
    return strand


async def resolve_strands(atom: dict) -> list[str]:
    """Return list of strand IDs that claim this atom (may be multiple)."""
    pred = (atom.get("predicate") or "").lower().strip()
    subj = (atom.get("subject") or "").lower().strip()
    registry = await load_registry()
    if not registry:
        registry = [{**b, "created_at": db.now()} for b in _STATIC_BUNDLES]

    strand_ids: list[str] = []
    for strand in registry:
        predicates = [p.lower() for p in strand.get("predicates", [])]
        subjects = [s.lower() for s in strand.get("subjects", [])]
        if (pred and pred in predicates) or (subj and subj in subjects):
            strand_ids.append(strand["id"])
    return strand_ids


async def atoms_for_strand(
    strand_id: str,
    window: tuple[int, int] | None = None,
) -> list[dict]:
    """Return all active atoms belonging to a strand, optionally within [from, to]."""
    registry = await load_registry()
    if not registry:
        registry = [{**b, "created_at": db.now()} for b in _STATIC_BUNDLES]

    strand = next((s for s in registry if s["id"] == strand_id), None)
    if not strand:
        return []

    predicates = [p.lower() for p in strand.get("predicates", [])]
    subjects = [s.lower() for s in strand.get("subjects", [])]

    rows: list[dict] = []
    seen_ids: set[str] = set()

    if predicates:
        placeholders = ",".join("?" * len(predicates))
        q = (
            f"SELECT * FROM memory_atom WHERE predicate IN ({placeholders}) "
            "AND (status='active' OR status IS NULL)"
        )
        params: tuple = tuple(predicates)
        if window:
            q += " AND COALESCE(valid_from, created_at) BETWEEN ? AND ?"
            params = params + window
        for r in await db.fetchall(q, params):
            if r["id"] not in seen_ids:
                rows.append(r)
                seen_ids.add(r["id"])

    if subjects:
        placeholders = ",".join("?" * len(subjects))
        q = (
            f"SELECT * FROM memory_atom WHERE subject IN ({placeholders}) "
            "AND (status='active' OR status IS NULL)"
        )
        params = tuple(subjects)
        if window:
            q += " AND COALESCE(valid_from, created_at) BETWEEN ? AND ?"
            params = params + window
        for r in await db.fetchall(q, params):
            if r["id"] not in seen_ids:
                rows.append(r)
                seen_ids.add(r["id"])

    return [memory._row_to_atom(r) for r in rows]


async def propose_strand_clusters() -> None:
    """Quarterly: scan predicates outside existing strands.

    Because the embedder is lexical (word-overlap only), thresholds are
    conservative and a hard cap of 2 open insight_offer questions prevents
    spam.  Suppress if a per-cluster cooldown is active.

    [VALIDATE] memory.strand_cluster_min (default 5) after real usage data.
    """
    from . import questions as q_svc

    min_predicates = int(await config.get_setting("memory.strand_cluster_min") or 5)

    # Count open insight_offer questions — hard cap at 2
    open_offers = await db.fetchall(
        "SELECT id FROM memory_question WHERE kind='insight_offer' AND status='open'"
    )
    if len(open_offers) >= 2:
        return

    registry = await load_registry()
    if not registry:
        registry = [{**b, "created_at": db.now()} for b in _STATIC_BUNDLES]

    known_predicates: set[str] = set()
    for strand in registry:
        known_predicates.update(p.lower() for p in strand.get("predicates", []))

    # Find predicates with >= 3 atoms each that are outside existing strands
    rows = await db.fetchall(
        "SELECT predicate, COUNT(*) AS n FROM memory_atom "
        "WHERE predicate IS NOT NULL AND (status='active' OR status IS NULL) "
        "GROUP BY predicate HAVING n >= 3"
    )
    novel_preds = [r["predicate"] for r in rows
                   if r["predicate"].lower() not in known_predicates]

    if len(novel_preds) < min_predicates:
        return

    # Propose a grouping — suggest the user name it
    prompt = (
        f"You have {len(novel_preds)} memory predicates that don't fit existing "
        f"life-area timelines: {', '.join(novel_preds[:20])}. "
        "Consider grouping some of these into a new timeline."
    )
    # Signature for dedup / cooldown
    sig = ",".join(sorted(novel_preds[:20]))
    import hashlib
    sig_hash = hashlib.md5(sig.encode()).hexdigest()[:12]

    # Check 30-day cooldown for this signature
    cooldown_key = f"strand_cluster_cooldown_{sig_hash}"
    last = await config.get_setting(cooldown_key)
    if last:
        try:
            if db.now() - int(last) < 30 * 86400:
                return
        except ValueError:
            pass

    # Store novel predicates in atom_ids (strings, not UUIDs) so resolve_question
    # can populate the new strand's predicate list when accept_named fires.
    await q_svc.open_question("insight_offer", novel_preds[:20], prompt)
    await config.set_setting(cooldown_key, str(db.now()))
