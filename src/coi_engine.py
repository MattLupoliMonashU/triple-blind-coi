"""
coi_engine.py
=============
Core conflict-of-interest (COI) scoring engine for the Triple-Blind Peer
Review system described in:

    Lupoli, M. J. (2026). Cleaning Up the Ivory Tower: How Artificial
    Intelligence Can Facilitate Triple-Blind Peer Review, Mitigate Conflicts
    of Interest, and Promote Scientific Progress. Proposal submitted to
    Organization Science AI Special Issue.

Architecture overview
---------------------
This module implements the BACK-END of the two-component system:

  FRONT-END (not implemented here):
    A conversational LLM interface (e.g., Claude, Gemini via API) embedded
    in the journal management platform. The LLM is customised via a system
    prompt that defines its role, constraints, and data access rules.
    Critically, the system prompt prohibits the LLM from revealing author
    identities to editors at any stage.

  BACK-END (this module):
    A structured scholarly network database, populated by an AI data-
    gathering agent from publicly available sources (university pages, CVs,
    Google Scholar, OpenAlex, Semantic Scholar, etc.), and updated on a
    daily basis. The LLM queries this database but does NOT generate or
    infer network relationships — it only retrieves them. This separation
    means the system CANNOT hallucinate COIs: any flagged conflict
    corresponds to a verifiable, documented relationship in the database,
    with a transparent audit trail.

COI score
---------
Each scholar in Professor Pierce's (or any EIC's) network is assigned a
COI score in [0, 1], reflecting the probability that the EIC would have a
meaningful conflict of interest with that scholar as a submitting author.

The score is based on the TYPE and RECENCY of the professional
relationship: direct ties (e.g., co-authorship) receive greater weight than
indirect ties (e.g., shared institutional affiliation or a shared
collaborator). Relationship weights are informed by prior work on
conflict-of-interest detection in scholarly networks (Aleman-Meza et al.,
2006; Freeman, 1979) and will undergo extensive recursive testing with
external feedback as the system develops.

The complement product rule is used to combine independent relationship
channels:

    COI_score = 1 - prod(1 - w_i)

This computes P(at least one active conflict channel) under the assumption
that channels are independent. It prevents any single channel from dominating
the final score and caps naturally at 1.0.

Default threshold: 0.50 (configurable per journal).

Usage
-----
    # Live API mode (requires network access to OpenAlex / Semantic Scholar)
    from src.coi_engine import COIEngine
    engine = COIEngine()
    result = engine.score("Lamar Pierce", "Jane Smith")
    print(result.score, result.notification_text())

    # Offline demo mode (uses pre-built synthetic profiles)
    from src.demo_data import score_offline, LAMAR_PIERCE, AUTHOR_HIGH_COI
    result = score_offline(LAMAR_PIERCE, AUTHOR_HIGH_COI)
    print(result.notification_text(threshold=0.50))
"""

import math
import json
import time
import hashlib
import os
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import requests
import networkx as nx


# ---------------------------------------------------------------------------
# Current year (used throughout for recency calculations)
# ---------------------------------------------------------------------------
CURRENT_YEAR = datetime.utcnow().year


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScholarProfile:
    """
    Normalised scholar profile assembled by the AI data-gathering agent
    from publicly available sources (university pages, Google Scholar,
    OpenAlex, Semantic Scholar, ORCID, etc.).
    """
    name: str
    openalex_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    # List of {name, ror_id, years: [int]}
    institutions: list = field(default_factory=list)
    # List of {name, id, most_recent_year, n_papers}
    coauthors: list = field(default_factory=list)
    # List of {journal, role, years: [int]}
    editorial_roles: list = field(default_factory=list)
    # OpenAlex author IDs of advisors / advisees
    advisor_ids: list = field(default_factory=list)
    advisee_ids: list = field(default_factory=list)
    # URLs from which this profile was assembled (audit trail)
    source_urls: list = field(default_factory=list)
    fetched_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


@dataclass
class COIEdge:
    """One identified conflict-of-interest relationship channel."""
    relationship_type: str   # e.g. "direct_coauthorship"
    weight: float            # contribution to combined score
    details: str             # human-readable explanation


@dataclass
class COIResult:
    """Full output of a COI assessment between two scholars."""
    scholar_a: str
    scholar_b: str
    score: float                          # Combined COI score in [0, 1]
    edges: list = field(default_factory=list)      # list[COIEdge]
    reasons: list = field(default_factory=list)    # list[str]
    data_sources: list = field(default_factory=list)
    computed_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    def exceeds_threshold(self, threshold: float = 0.50) -> bool:
        return self.score >= threshold

    def notification_text(self, threshold: float = 0.50) -> str:
        """
        Returns the plain-language notification string shown to the editor,
        matching the example in the manuscript.
        """
        if not self.exceeds_threshold(threshold):
            return (
                f"No conflict of interest detected (score: {self.score:.2f}). "
                f"This person may proceed as editor or reviewer."
            )
        reasons_str = "; ".join(self.reasons) if self.reasons else "see details"
        return (
            f"This person has a conflict-of-interest score with one or more "
            f"of the authors of {self.score:.2f}, which exceeds the journal's "
            f"recommended threshold of {threshold:.2f}. The score of "
            f"{self.score:.2f} is based on: {reasons_str}."
        )

    def to_dict(self) -> dict:
        return {
            "scholar_a": self.scholar_a,
            "scholar_b": self.scholar_b,
            "score": round(self.score, 4),
            "exceeds_threshold_050": self.exceeds_threshold(0.50),
            "reasons": self.reasons,
            "edges": [
                {
                    "type": e.relationship_type,
                    "weight": e.weight,
                    "details": e.details,
                }
                for e in self.edges
            ],
            "data_sources": self.data_sources,
            "computed_at": self.computed_at,
        }


# ---------------------------------------------------------------------------
# Weight schema (v0.1)
# See docs/weight_schema.md for full rationale and references.
# ---------------------------------------------------------------------------

# Co-authorship: weight by recency (most recent shared paper)
# (max_age_years, weight, label)
COAUTHOR_WEIGHTS = [
    (2,   0.90, "co-authorship within 2 years"),
    (5,   0.75, "co-authorship within 3-5 years"),
    (10,  0.50, "co-authorship within 6-10 years"),
    (999, 0.25, "co-authorship more than 10 years ago"),
]

INSTITUTION_WEIGHT_CURRENT      = 0.70   # currently at same institution
INSTITUTION_WEIGHT_FORMER_BASE  = 0.35   # formerly at same institution
INSTITUTION_WEIGHT_FORMER_DECAY = 0.05   # per year since departure

ADVISOR_ADVISEE_WEIGHT   = 0.85
EDITORIAL_BOARD_WEIGHT   = 0.40
SHARED_COAUTHOR_WEIGHT   = 0.20   # 2nd-degree (shared collaborator)


def coauthor_weight(most_recent_year: int) -> tuple[float, str]:
    """Return (weight, label) for a co-authorship relationship."""
    age = CURRENT_YEAR - most_recent_year
    for max_age, w, label in COAUTHOR_WEIGHTS:
        if age <= max_age:
            return w, label
    return COAUTHOR_WEIGHTS[-1][1], COAUTHOR_WEIGHTS[-1][2]


def institution_weight(departure_year: Optional[int] = None) -> float:
    """
    Return weight for a shared institution.
    departure_year=None means the institution is currently shared.
    """
    if departure_year is None:
        return INSTITUTION_WEIGHT_CURRENT
    years_since = CURRENT_YEAR - departure_year
    w = INSTITUTION_WEIGHT_FORMER_BASE - years_since * INSTITUTION_WEIGHT_FORMER_DECAY
    return max(w, 0.0)


def combine_weights(weights: list[float]) -> float:
    """
    Combine independent relationship channel weights using the complement
    product rule: P(at least one conflict) = 1 - prod(1 - w_i).
    Caps at 1.0; weights of 0 are ignored.
    """
    if not weights:
        return 0.0
    complement = math.prod(1.0 - w for w in weights if w > 0)
    return round(1.0 - complement, 4)


# ---------------------------------------------------------------------------
# Data-fetching layer
# (OpenAlex primary; Semantic Scholar fallback)
# ---------------------------------------------------------------------------

OPENALEX_BASE = "https://api.openalex.org"
S2_BASE       = "https://api.semanticscholar.org/graph/v1"
HEADERS       = {
    "User-Agent": "triple-blind-coi/0.1 (academic research; see GitHub)"
}
RATE_DELAY = 0.12   # seconds — OpenAlex polite-pool requirement


def _get(url: str, params: dict = None, retries: int = 3) -> Optional[dict]:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 ** attempt)
        except requests.RequestException:
            time.sleep(1)
    return None


def fetch_openalex_profile(name: str) -> Optional[ScholarProfile]:
    """Fetch and normalise a scholar profile from OpenAlex."""
    time.sleep(RATE_DELAY)
    data = _get(f"{OPENALEX_BASE}/authors",
                params={"search": name, "per_page": 1})
    if not data or not data.get("results"):
        return None

    a = data["results"][0]
    author_id = a["id"].replace("https://openalex.org/", "")

    works = _get(
        f"{OPENALEX_BASE}/works",
        params={
            "filter": f"author.id:{author_id}",
            "per_page": 200,
            "select": "id,publication_year,authorships",
        }
    )

    coauthors: dict = {}
    if works:
        for work in works.get("results", []):
            year = work.get("publication_year") or CURRENT_YEAR
            for auth in work.get("authorships", []):
                aid   = (auth.get("author") or {}).get("id", "")
                aname = (auth.get("author") or {}).get("display_name", "")
                if aid and aid != a["id"]:
                    if aid not in coauthors:
                        coauthors[aid] = {
                            "name": aname, "years": set(), "n_papers": 0
                        }
                    coauthors[aid]["years"].add(year)
                    coauthors[aid]["n_papers"] += 1

    institutions = []
    for entry in a.get("affiliations", []):
        inst  = entry.get("institution", {})
        years = entry.get("years", [])
        institutions.append({
            "name":   inst.get("display_name", ""),
            "ror_id": inst.get("ror", ""),
            "years":  sorted(years),
        })

    return ScholarProfile(
        name=a["display_name"],
        openalex_id=author_id,
        institutions=institutions,
        coauthors=[
            {
                "name": v["name"],
                "id": k,
                "most_recent_year": max(v["years"]) if v["years"]
                                    else CURRENT_YEAR,
                "n_papers": v["n_papers"],
            }
            for k, v in coauthors.items()
        ],
        source_urls=[
            a.get("id", ""),
            f"https://openalex.org/{author_id}",
        ],
    )


# ---------------------------------------------------------------------------
# Disk cache (24-hour TTL)
# ---------------------------------------------------------------------------

CACHE_DIR     = os.path.join(os.path.dirname(__file__), "..", "data", "cache")
CACHE_TTL_HRS = 24


def _cache_key(name: str) -> str:
    return hashlib.md5(name.lower().strip().encode()).hexdigest()


def _load_cache(name: str) -> Optional[ScholarProfile]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{_cache_key(name)}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    age = (datetime.utcnow() -
           datetime.fromisoformat(d.get("fetched_at", "2000-01-01"))
           ).total_seconds() / 3600
    if age > CACHE_TTL_HRS:
        return None
    return ScholarProfile(**d)


def _save_cache(profile: ScholarProfile) -> None:
    import dataclasses
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{_cache_key(profile.name)}.json")
    with open(path, "w") as f:
        json.dump(dataclasses.asdict(profile), f, default=list)


# ---------------------------------------------------------------------------
# COI Engine
# ---------------------------------------------------------------------------

class COIEngine:
    """
    Main entry point for conflict-of-interest scoring.

    Parameters
    ----------
    threshold : float
        COI score above which a conflict is flagged (default 0.50).
    use_cache : bool
        Cache scholar profiles to disk for 24 hours (recommended).
    """

    def __init__(self, threshold: float = 0.50, use_cache: bool = True):
        self.threshold = threshold
        self.use_cache = use_cache

    def _fetch(self, name: str) -> Optional[ScholarProfile]:
        if self.use_cache:
            cached = _load_cache(name)
            if cached:
                return cached
        profile = fetch_openalex_profile(name)
        if profile and self.use_cache:
            _save_cache(profile)
        return profile

    def score(self, name_a: str, name_b: str) -> COIResult:
        """
        Compute COI score between two named scholars via live API lookup.
        For offline/demo use, call score_offline() in demo_data.py instead.
        """
        pA = self._fetch(name_a)
        pB = self._fetch(name_b)
        return _compute_coi(
            pA, pB,
            name_a_fallback=name_a,
            name_b_fallback=name_b,
        )


def _compute_coi(
    pA: Optional[ScholarProfile],
    pB: Optional[ScholarProfile],
    name_a_fallback: str = "",
    name_b_fallback: str = "",
) -> COIResult:
    """
    Core COI computation given two profiles (or None if lookup failed).
    Used by both COIEngine.score() and demo_data.score_offline().
    """
    edges: list[COIEdge] = []
    sources: list[str] = []

    if pA:
        sources.extend(pA.source_urls)
    if pB:
        sources.extend(pB.source_urls)

    if pA and pB:
        a_ids = {c["id"] for c in pA.coauthors if c.get("id")}
        b_ids = {c["id"] for c in pB.coauthors if c.get("id")}

        # --- 1. Direct co-authorship ---
        direct = False
        if pB.openalex_id and pB.openalex_id in a_ids:
            m = next(c for c in pA.coauthors if c.get("id") == pB.openalex_id)
            w, label = coauthor_weight(m["most_recent_year"])
            edges.append(COIEdge(
                relationship_type="direct_coauthorship",
                weight=w,
                details=(f"Direct {label} "
                         f"({m['n_papers']} shared paper(s), "
                         f"most recent {m['most_recent_year']})"),
            ))
            direct = True
        elif pA.openalex_id and pA.openalex_id in b_ids:
            m = next(c for c in pB.coauthors if c.get("id") == pA.openalex_id)
            w, label = coauthor_weight(m["most_recent_year"])
            edges.append(COIEdge(
                relationship_type="direct_coauthorship",
                weight=w,
                details=(f"Direct {label} "
                         f"({m['n_papers']} shared paper(s), "
                         f"most recent {m['most_recent_year']})"),
            ))
            direct = True

        # --- 2. Shared collaborator (2nd-degree), only if no direct tie ---
        if not direct:
            common = a_ids & b_ids
            if common:
                edges.append(COIEdge(
                    relationship_type="shared_coauthor",
                    weight=SHARED_COAUTHOR_WEIGHT,
                    details=f"Share {len(common)} common collaborator(s)",
                ))

        # --- 3. Advisor–advisee ---
        if (
            (pB.openalex_id and pB.openalex_id in pA.advisor_ids) or
            (pA.openalex_id and pA.openalex_id in pB.advisor_ids) or
            (pB.openalex_id and pB.openalex_id in pA.advisee_ids) or
            (pA.openalex_id and pA.openalex_id in pB.advisee_ids)
        ):
            edges.append(COIEdge(
                relationship_type="advisor_advisee",
                weight=ADVISOR_ADVISEE_WEIGHT,
                details="Advisor–advisee relationship",
            ))

        # --- 4. Shared institution ---
        a_current = {
            i["name"] for i in pA.institutions
            if not i.get("years") or max(i["years"]) >= CURRENT_YEAR - 1
        }
        b_current = {
            i["name"] for i in pB.institutions
            if not i.get("years") or max(i["years"]) >= CURRENT_YEAR - 1
        }
        shared_now = a_current & b_current
        if shared_now:
            edges.append(COIEdge(
                relationship_type="current_shared_institution",
                weight=INSTITUTION_WEIGHT_CURRENT,
                details=f"Currently at same institution: "
                        f"{', '.join(shared_now)}",
            ))
        else:
            a_all = {i["name"] for i in pA.institutions}
            b_all = {i["name"] for i in pB.institutions}
            shared_former = a_all & b_all
            if shared_former:
                edges.append(COIEdge(
                    relationship_type="former_shared_institution",
                    weight=INSTITUTION_WEIGHT_FORMER_BASE,
                    details=f"Formerly at same institution: "
                            f"{', '.join(shared_former)}",
                ))

        # --- 5. Editorial board co-membership ---
        a_journals = {r["journal"] for r in pA.editorial_roles}
        b_journals = {r["journal"] for r in pB.editorial_roles}
        shared_boards = a_journals & b_journals
        if shared_boards:
            edges.append(COIEdge(
                relationship_type="editorial_board",
                weight=EDITORIAL_BOARD_WEIGHT,
                details=f"Shared editorial role: "
                        f"{', '.join(shared_boards)}",
            ))

    combined = combine_weights([e.weight for e in edges])
    reasons  = [e.details for e in edges] or [
        "No identifiable relationship found in public data"
    ]

    return COIResult(
        scholar_a=pA.name if pA else name_a_fallback,
        scholar_b=pB.name if pB else name_b_fallback,
        score=combined,
        edges=edges,
        reasons=reasons,
        data_sources=list(set(sources)),
    )
