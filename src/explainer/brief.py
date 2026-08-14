"""The Course Brief (PRD v0.2 §6 Stage 1).

    "The Course Brief is itself a versioned, editable object, so 'regenerate
     from an edited brief' is a first-class operation rather than a fresh start."

Two properties this file exists to guarantee:

1. **Nothing may block generation.** Every field has a defensible default, and
   nothing here raises on a thin brief. A human who types a title and a topic
   gets a complete, usable brief; the defaults are stated in one place so they
   can be argued with rather than discovered.

2. **Edits are versions, never overwrites.** `save` always writes
   `max(version) + 1`. A brief a human approved is never mutated underneath
   them — the same reason beat briefs live in their own rows (§5.1): the second
   time the system quietly changes something a human signed off on, they stop
   trusting any output.

The brief is also a hash-closure input for every downstream stage, so it
serialises canonically: `to_closure()` returns sorted, plain-JSON data with no
timestamps, no course id and no version in it. Identity is inputs only
(invariant 1) — two courses whose briefs are word-for-word identical must
produce the same objective graph hash.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from . import db

# ---------------------------------------------------------------- defaults
#
# Each default is a decision, not a placeholder. If you change one, say what
# breaks: these values reach the model, the renderer and the cost model.

DEFAULT_AUDIENCE_LEVEL = "intermediate"       # §2 D1
DEFAULT_TARGET_SECONDS = 240
# How many videos the course may spend. The extractor uses it to size an
# objective: without it, prompt v1 reproducibly emitted ~10 scene-sized
# objectives (measured: 8, 7, 7 taught across three samples) where the gold
# graph has video-sized ones.
#
# This is a SHIPPING decision, not a content one, and the two were conflated
# once already. §5.3 caps a video at 1-2 objectives; that is satisfied just as
# well by two videos of two objectives as by one. Setting max_videos=1 for a
# Milestone A that only renders one video pushed the extractor to drop content
# the gold requires — measured at 0 of 3 samples naming the three anomalies,
# against 3 of 3 for the ungoverned prompt v1. The default stays 1 because a
# course with no stated budget should not sprawl, but raising it is the right
# move whenever the objective graph is being starved rather than shaped.
DEFAULT_MAX_VIDEOS = 1
DEFAULT_LOCALE = "en"                         # D7 — ship EN only, keep the field
DEFAULT_TONE = ("plain, concrete and unhurried; explain the mechanism rather "
                "than the vocabulary; no hype, no filler")


@dataclass(frozen=True)
class Audience:
    """Who this is for. Feeds objective difficulty, assumed prerequisites and
    the lexicon."""

    level: str = DEFAULT_AUDIENCE_LEVEL
    # What a learner is expected to arrive with. Drives `assumed` objectives:
    # an empty list is honest ("assume nothing"), not a missing value.
    prior_knowledge: tuple[str, ...] = ()
    # §15.3 — proportion of narration expected in the learner's first language.
    # 0.0 means "one language, the locale's". Present from day one because
    # retrofitting a mixed-language track means re-cutting every scene.
    native_language_ratio: float = 0.0

    def to_json(self) -> dict:
        return {"level": self.level,
                "prior_knowledge": list(self.prior_knowledge),
                "native_language_ratio": self.native_language_ratio}

    @classmethod
    def from_json(cls, obj: dict | None) -> Audience:
        obj = obj or {}
        return cls(
            level=obj.get("level") or DEFAULT_AUDIENCE_LEVEL,
            prior_knowledge=tuple(obj.get("prior_knowledge") or ()),
            native_language_ratio=float(obj.get("native_language_ratio") or 0.0),
        )


@dataclass(frozen=True)
class CourseBrief:
    """§6 Stage 1. The only human input the pipeline requires."""

    title: str
    description: str = ""
    # Refs, never inlined bytes: a URL, a doc id, or a content sha in
    # media_assets (R7). Keeping them as refs means the brief stays small enough
    # to sit in a hash closure.
    source_material: tuple[str, ...] = ()
    audience: Audience = field(default_factory=Audience)
    target_seconds_per_video: int = DEFAULT_TARGET_SECONDS
    max_videos: int = DEFAULT_MAX_VIDEOS
    locales: tuple[str, ...] = (DEFAULT_LOCALE,)
    brand_kit_ref: str | None = None
    tone: str = DEFAULT_TONE
    reference_video_ref: str | None = None

    # Set by `save`/`load`. Not part of the closure — see `to_closure`.
    version: int = 0

    # ------------------------------------------------------------ accessors

    @property
    def locale(self) -> str:
        """The primary locale. D7 ships one; the field is plural so the second
        one is a data change rather than a schema migration."""
        return self.locales[0] if self.locales else DEFAULT_LOCALE

    def to_json(self) -> dict:
        out = asdict(self)
        out["audience"] = self.audience.to_json()
        out["source_material"] = list(self.source_material)
        out["locales"] = list(self.locales)
        return out

    def to_closure(self) -> dict:
        """The subset that legitimately changes downstream output identity.

        Excludes `version` deliberately: bumping the version without changing a
        field must NOT invalidate artifacts (invariant 1 — identity is inputs
        only). Two versions with identical content are the same input.
        """
        obj = self.to_json()
        obj.pop("version", None)
        return json.loads(json.dumps(obj, sort_keys=True))

    def render_for_prompt(self) -> str:
        """What the extractor actually sees. Deterministic ordering — this
        string enters a prompt whose output we cache on.

        `ensure_ascii=False` so an em dash in the description reaches the model
        as an em dash rather than as \u2014. It costs nothing, keeps the
        prompt readable when a human inspects it, and makes "the brief reaches
        the model verbatim" literally true. Hashing is unaffected: closures go
        through `hashing.canonical_json`, not through here.
        """
        return json.dumps(self.to_closure(), indent=2, sort_keys=True,
                          ensure_ascii=False)

    @classmethod
    def from_json(cls, obj: dict, version: int = 0) -> CourseBrief:
        """Tolerant by design: unknown keys are ignored and missing keys take
        their default. A brief written by an older version of this code, or by
        hand, must still load."""
        return cls(
            title=obj.get("title") or "",
            description=obj.get("description") or "",
            source_material=tuple(obj.get("source_material") or ()),
            audience=Audience.from_json(obj.get("audience")),
            target_seconds_per_video=int(
                obj.get("target_seconds_per_video") or DEFAULT_TARGET_SECONDS),
            max_videos=int(obj.get("max_videos") or DEFAULT_MAX_VIDEOS),
            locales=tuple(obj.get("locales") or (DEFAULT_LOCALE,)),
            brand_kit_ref=obj.get("brand_kit_ref"),
            tone=obj.get("tone") or DEFAULT_TONE,
            reference_video_ref=obj.get("reference_video_ref"),
            version=int(obj.get("version") or version),
        )

    def edited(self, **changes: Any) -> CourseBrief:
        """Return a copy with `changes` applied. Pure — persisting is `save`.

        Accepts `audience` as a dict so a CLI or an editor can send a partial
        patch without constructing the dataclass.
        """
        if isinstance(changes.get("audience"), dict):
            merged = {**self.audience.to_json(), **changes["audience"]}
            changes["audience"] = Audience.from_json(merged)
        for key in ("source_material", "locales"):
            if key in changes and changes[key] is not None:
                changes[key] = tuple(changes[key])
        return replace(self, **changes)


# ------------------------------------------------------------- persistence

def save(conn, course_id: str, brief: CourseBrief,
         provenance: dict | None = None) -> CourseBrief:
    """Write the brief as a NEW version. Never updates in place."""
    row = db.one(conn, """
        insert into course_briefs(course_id, version, brief, provenance)
        select %s, coalesce(max(version), 0) + 1, %s, %s
          from course_briefs where course_id = %s
        returning version
    """, (course_id, json.dumps(brief.to_closure()),
          json.dumps(provenance or {}), course_id))
    return replace(brief, version=int(row["version"]))


def load(conn, course_id: str, version: int | None = None) -> CourseBrief:
    """Load a brief. `None` means the latest version."""
    if version is None:
        row = db.one(conn, """select version, brief from course_briefs
                              where course_id = %s
                              order by version desc limit 1""", (course_id,))
    else:
        row = db.one(conn, """select version, brief from course_briefs
                              where course_id = %s and version = %s""",
                     (course_id, version))
    if not row:
        raise LookupError(
            f"no course brief for course {course_id}"
            + (f" at version {version}" if version is not None else "")
            + " — create one with `explainer course create`")
    return CourseBrief.from_json(row["brief"], version=int(row["version"]))


def history(conn, course_id: str) -> list[dict]:
    return db.query(conn, """select version, provenance, created_at
                             from course_briefs where course_id = %s
                             order by version""", (course_id,))


def revise(conn, course_id: str, changes: dict[str, Any],
           note: str | None = None) -> CourseBrief:
    """Edit the latest brief and persist the result as the next version."""
    current = load(conn, course_id)
    edited = current.edited(**changes)
    return save(conn, course_id, edited,
                provenance={"edited_from_version": current.version,
                            "changed_keys": sorted(changes),
                            "note": note})


def regenerate_from_edited_brief(conn, course_id: str,
                                 changes: dict[str, Any] | None = None,
                                 note: str | None = None,
                                 **extract_kwargs):
    """§6 Stage 1's first-class operation: edit the brief, then rebuild the
    objective graph from the edited brief.

    Kept here rather than in the extractor because the *brief* is the thing that
    is versioned and edited; extraction is what happens to fall out of it. The
    import is local to avoid a module cycle (the extractor reads briefs).

    Returns the `ExtractionOutcome`. Raises `ExtractionEscalated` if the model
    could not produce a schema-valid graph (invariant 7 — the failure is
    recorded, never silent).
    """
    from .agents import objective_extractor

    if changes:
        edited = revise(conn, course_id, changes, note=note)
    else:
        edited = load(conn, course_id)
    return objective_extractor.extract(conn, course_id, edited, **extract_kwargs)


# ------------------------------------------------------------------ course

def ensure_org(conn, name: str = "default") -> str:
    row = db.one(conn, "select id from organisations where name = %s", (name,))
    if row:
        return str(row["id"])
    row = db.one(conn, "insert into organisations(name) values (%s) returning id",
                 (name,))
    return str(row["id"])


def ensure_course(conn, slug: str, brief: CourseBrief,
                  org: str = "default") -> str:
    """Create-or-update the course row and return its id.

    `courses` holds only what other tables need to join on (slug, title,
    audience, locale). The brief itself is the source of truth and lives in
    `course_briefs` — these columns are a denormalised read path, not a second
    copy to edit.
    """
    org_id = ensure_org(conn, org)
    row = db.one(conn, """
        insert into courses(org_id, slug, title, audience, locale)
        values (%s, %s, %s, %s, %s)
        on conflict (org_id, slug) do update
          set title = excluded.title,
              audience = excluded.audience,
              locale = excluded.locale
        returning id
    """, (org_id, slug, brief.title or slug,
          json.dumps(brief.audience.to_json()), brief.locale))
    return str(row["id"])


def course_id_for(conn, slug: str, org: str = "default") -> str:
    row = db.one(conn, """select c.id from courses c join organisations o on o.id = c.org_id
                          where c.slug = %s and o.name = %s""", (slug, org))
    if not row:
        raise LookupError(f"no course '{slug}' — create it with "
                          f"`explainer course create {slug} --title ...`")
    return str(row["id"])


def list_courses(conn, org: str = "default") -> list[dict]:
    return db.query(conn, """
        select c.slug, c.title, c.locale, c.status,
               (select max(version) from course_briefs b where b.course_id = c.id) as brief_version,
               (select count(*) from objectives ob where ob.course_id = c.id) as objectives
          from courses c join organisations o on o.id = c.org_id
         where o.name = %s order by c.slug""", (org,))
