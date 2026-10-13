"""
demo_data.py
============
Synthetic scholar profiles and worked examples for offline demonstration.

These profiles reproduce the four cases described in the manuscript and
the Research Artifact without requiring live API access. In a production
deployment, profiles are assembled and updated daily by the AI
data-gathering agent from publicly available sources.

The worked example uses Professor Lamar Pierce (EIC, Organization Science,
Washington University in St. Louis) as the example editor, following the
manuscript's illustration.

Run this file directly to reproduce the worked examples:
    python -m src.demo_data
"""

from src.coi_engine import (
    ScholarProfile, COIResult, COIEdge,
    combine_weights, coauthor_weight,
    CURRENT_YEAR,
    INSTITUTION_WEIGHT_CURRENT,
    INSTITUTION_WEIGHT_FORMER_BASE,
    ADVISOR_ADVISEE_WEIGHT,
    EDITORIAL_BOARD_WEIGHT,
    SHARED_COAUTHOR_WEIGHT,
    _compute_coi,
)


# ---------------------------------------------------------------------------
# Synthetic profiles
# ---------------------------------------------------------------------------

LAMAR_PIERCE = ScholarProfile(
    name="Lamar Pierce",
    openalex_id="A2150895435",
    institutions=[
        {
            "name": "Washington University in St. Louis",
            "ror_id": "00cv6y642",
            "years": list(range(2010, CURRENT_YEAR + 1)),
        },
    ],
    coauthors=[
        {"name": "Jason Snyder",
         "id": "A2101234567", "most_recent_year": 2023, "n_papers": 8},
        {"name": "Todd Zenger",
         "id": "A2209876543", "most_recent_year": 2021, "n_papers": 3},
        {"name": "Kristina McElheran",
         "id": "A2312345678", "most_recent_year": 2022, "n_papers": 4},
        {"name": "Evan Rawley",
         "id": "A2423456789", "most_recent_year": 2020, "n_papers": 2},
        {"name": "Dennis Zhang",
         "id": "A2534567890", "most_recent_year": 2024, "n_papers": 5},
    ],
    editorial_roles=[
        {"journal": "Organization Science",
         "role": "Editor-in-Chief",
         "years": list(range(2022, CURRENT_YEAR + 1))},
        {"journal": "Management Science",
         "role": "Associate Editor",
         "years": [2018, 2019, 2020]},
    ],
    source_urls=[
        "https://openalex.org/A2150895435",
        "https://olin.wustl.edu/faculty/lamar-pierce",
    ],
)

# Case 1: HIGH COI — recent co-author at the same institution
# Matches the manuscript example: score ~0.98, flagged
AUTHOR_HIGH_COI = ScholarProfile(
    name="Dennis Zhang",
    openalex_id="A2534567890",
    institutions=[
        {
            "name": "Washington University in St. Louis",
            "ror_id": "00cv6y642",
            "years": list(range(2018, CURRENT_YEAR + 1)),
        },
    ],
    coauthors=[
        {"name": "Lamar Pierce",
         "id": "A2150895435", "most_recent_year": 2024, "n_papers": 5},
    ],
    editorial_roles=[
        {"journal": "Organization Science",
         "role": "Guest Editor", "years": [CURRENT_YEAR]},
    ],
    source_urls=["https://openalex.org/A2534567890"],
)

# Case 2: MEDIUM COI — former co-author, now at a different institution
# Score ~0.68, flagged above 0.50 threshold
AUTHOR_MEDIUM_COI = ScholarProfile(
    name="Evan Rawley",
    openalex_id="A2423456789",
    institutions=[
        {
            "name": "University of Minnesota",
            "ror_id": "017zqws13",
            "years": list(range(2015, CURRENT_YEAR + 1)),
        },
        {
            "name": "Washington University in St. Louis",
            "ror_id": "00cv6y642",
            "years": list(range(2010, 2015)),
        },
    ],
    coauthors=[
        {"name": "Lamar Pierce",
         "id": "A2150895435", "most_recent_year": 2020, "n_papers": 2},
    ],
    editorial_roles=[],
    source_urls=["https://openalex.org/A2423456789"],
)

# Case 3: LOW / NO COI — 2nd-degree connection only (shared collaborator)
# Score ~0.20, below 0.50 threshold — NOT flagged
AUTHOR_NO_COI = ScholarProfile(
    name="Jane Researcher",
    openalex_id="A2999999999",
    institutions=[
        {
            "name": "University of Melbourne",
            "ror_id": "01ej9dk98",
            "years": list(range(2015, CURRENT_YEAR + 1)),
        },
    ],
    coauthors=[
        # Shares Jason Snyder with Pierce, but no direct tie to Pierce
        {"name": "Jason Snyder",
         "id": "A2101234567", "most_recent_year": 2019, "n_papers": 1},
    ],
    editorial_roles=[],
    source_urls=["https://openalex.org/A2999999999"],
)

# Case 4: HIGH COI — advisor–advisee relationship + co-authorship
# Score ~0.97, flagged
AUTHOR_ADVISEE = ScholarProfile(
    name="Alex Former-Student",
    openalex_id="A2888888888",
    institutions=[
        {
            "name": "Harvard Business School",
            "ror_id": "03vek6s52",
            "years": list(range(2022, CURRENT_YEAR + 1)),
        },
        {
            "name": "Washington University in St. Louis",
            "ror_id": "00cv6y642",
            "years": list(range(2015, 2022)),
        },
    ],
    coauthors=[
        {"name": "Lamar Pierce",
         "id": "A2150895435", "most_recent_year": 2021, "n_papers": 2},
    ],
    advisor_ids=["A2150895435"],  # Pierce was this person's PhD advisor
    editorial_roles=[],
    source_urls=["https://openalex.org/A2888888888"],
)


# ---------------------------------------------------------------------------
# Offline scoring (no API calls required)
# ---------------------------------------------------------------------------

def score_offline(
    profile_a: ScholarProfile,
    profile_b: ScholarProfile,
) -> COIResult:
    """
    Compute COI score from two pre-built profiles without any API calls.
    Used for the demo, unit tests, and the worked examples.
    """
    return _compute_coi(profile_a, profile_b)


# ---------------------------------------------------------------------------
# Worked examples (reproduce Table in Research Artifact)
# ---------------------------------------------------------------------------

CASES = [
    (LAMAR_PIERCE, AUTHOR_HIGH_COI,
     "Case 1 — HIGH COI: recent co-author at same institution"),
    (LAMAR_PIERCE, AUTHOR_MEDIUM_COI,
     "Case 2 — MEDIUM COI: older co-author, now at different institution"),
    (LAMAR_PIERCE, AUTHOR_NO_COI,
     "Case 3 — LOW COI: 2nd-degree connection only (shared collaborator)"),
    (LAMAR_PIERCE, AUTHOR_ADVISEE,
     "Case 4 — HIGH COI: advisor–advisee + co-authorship"),
]


def run_worked_examples() -> list[dict]:
    results = []
    for editor, author, label in CASES:
        r = score_offline(editor, author)
        results.append({
            "case": label,
            "editor": editor.name,
            "author": author.name,
            "score": r.score,
            "flagged_at_050": r.exceeds_threshold(0.50),
            "reasons": r.reasons,
            "notification": r.notification_text(threshold=0.50),
            "edges": [
                {"type": e.relationship_type,
                 "weight": e.weight,
                 "details": e.details}
                for e in r.edges
            ],
        })
    return results


if __name__ == "__main__":
    print("=" * 65)
    print("Triple-Blind COI Network — Worked Examples")
    print("(Lupoli, 2026 — Organization Science AI Special Issue)")
    print("=" * 65)
    for ex in run_worked_examples():
        print(f"\n{ex['case']}")
        print(f"  Editor : {ex['editor']}")
        print(f"  Author : {ex['author']}")
        print(f"  Score  : {ex['score']:.2f}  |  "
              f"Flagged (threshold 0.50): {ex['flagged_at_050']}")
        print(f"  Reasons: {'; '.join(ex['reasons'])}")
        print(f"  → {ex['notification']}")
    print()
