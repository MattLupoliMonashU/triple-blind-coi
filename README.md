# Triple-Blind COI Network

**Research artifact for:**
> Lupoli, M. J. (2026). *Cleaning Up the Ivory Tower: How Artificial
> Intelligence Can Facilitate Triple-Blind Peer Review, Mitigate Conflicts
> of Interest, and Promote Scientific Progress.* Proposal submitted to the
> Organization Science AI Special Issue.

[![Tests](https://img.shields.io/badge/tests-17%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](src/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## What this is

A working prototype of the AI-facilitated conflict-of-interest (COI)
detection system described in the manuscript. The system enables
**triple-blind peer review** — in which neither editors, reviewers, nor
authors know one another's identities — by automating the COI assessments
that currently force journal editors to know who submitted.

---

## The two-component architecture

The system has two deliberately separated components:

```
FRONT-END (conversational LLM interface)
  Powered by a commercial LLM (Claude, Gemini) via API agreement.
  Customised with a system prompt defining its role and constraints,
  including: never reveal author identities to editors.
  Editors type natural-language queries; the LLM queries the back-end.

        ↕  queries only — no inference of relationships

BACK-END (structured network database)   ← this repository
  Populated by an AI data-gathering agent from publicly available
  sources (university pages, Google Scholar, OpenAlex, Semantic Scholar).
  Updated automatically on a daily basis.
  The LLM retrieves from this database but cannot modify or hallucinate it.
  Any flagged COI corresponds to a verifiable, documented relationship.
```

This separation is critical: **the system cannot hallucinate COIs.**

---

## How the COI score works

Each scholar in the editor's network is assigned a COI score in [0, 1]
based on the type and recency of their professional relationship with the
editor. Direct ties (co-authorship) receive greater weight than indirect
ties (shared institution or shared collaborator).

Relationship channels are combined using the **complement product rule**:

```
COI_score = 1 − ∏ᵢ (1 − wᵢ)
```

A score above the journal's threshold (default: **0.50**) triggers a
plain-language notification to the editor.

See [`docs/weight_schema.md`](docs/weight_schema.md) for the full weight
table and rationale.

---

## Worked example (from the manuscript)

Using Professor Lamar Pierce (EIC, *Organization Science*) as the editor:

| Case | Author | COI Score | Flagged? | Key reason |
|---|---|---|---|---|
| High COI | Dennis Zhang | **0.98** | ✓ | Recent co-author; same institution; shared editorial role |
| Medium COI | Evan Rawley | **0.68** | ✓ | Former co-author (2020); formerly at same institution |
| Low COI | Jane Researcher | **0.20** | ✗ | 2nd-degree only (shared collaborator) |
| High COI | Alex Former-Student | **0.98** | ✓ | Advisor–advisee + co-author; formerly same institution |

The manuscript example notification (Case 1 equivalent, score 0.63):
> *"John Doe has a conflict-of-interest score with one or more of the
> authors of .63, which exceeds the journal's recommended threshold of
> .50. The score of .63 is based on: previous co-authorship and previous
> shared university."*

Run the worked examples yourself:
```bash
python -m src.demo_data
```

---

## Quick start

**Requirements:** Python 3.10+, `pip install requests networkx`

```bash
git clone https://github.com/YOUR_USERNAME/triple-blind-coi
cd triple-blind-coi
pip install -r requirements.txt

# Run worked examples (no internet required)
python -m src.demo_data

# Run tests
python tests/test_coi_engine.py

# Score two scholars via live API
python -c "
from src.coi_engine import COIEngine
engine = COIEngine(threshold=0.50)
result = engine.score('Lamar Pierce', 'Jason Snyder')
print(result.score)
print(result.notification_text())
"
```

---

## Repository structure

```
triple-blind-coi/
│
├── src/
│   ├── coi_engine.py      Core scoring engine, weight schema, API fetchers
│   └── demo_data.py       Synthetic profiles + worked examples (offline)
│
├── tests/
│   └── test_coi_engine.py 17 unit tests (all passing)
│
├── docs/
│   ├── weight_schema.md   Full weight rationale with references
│   └── system_prompt.md   Example LLM system prompt for journal platforms
│
├── examples/
│   └── worked_example.json Machine-readable output of the four cases
│
├── README.md
├── requirements.txt
└── LICENSE
```

---

## Data sources (back-end agent)

| Source | What it provides |
|---|---|
| [OpenAlex](https://openalex.org) | Co-authorship, affiliations, 200M+ papers (free) |
| [Semantic Scholar](https://www.semanticscholar.org) | Paper index, author disambiguation (free) |
| [DBLP](https://dblp.org) | Curated CS co-authorship (free) |
| [ORCID](https://orcid.org) | Employment history, education (planned) |
| University/personal pages | Current affiliations, CVs (via web agent) |

---

## Limitations (v0.1)

- Name disambiguation is imperfect, particularly for non-Western names.
  ORCID integration (planned) substantially reduces this error.
- Weights are theoretically grounded but not yet empirically calibrated.
  Calibration using known COI cases from adopting journals is planned.
- Some relationship types (funding ties, conference co-organisation) are
  not yet included. See `docs/weight_schema.md` for planned additions.
- The LLM front-end is described architecturally but not implemented here;
  it requires a commercial API agreement between the publisher and an LLM
  provider (e.g., Anthropic, Google).

---

## Citation

```bibtex
@misc{lupoli2026tripleblind,
  author    = {Lupoli, Matthew J.},
  title     = {Triple-Blind COI Network: Research Artifact},
  year      = {2026},
  publisher = {GitHub},
  url       = {https://github.com/YOUR_USERNAME/triple-blind-coi}
}
```

---

## License

MIT — see [LICENSE](LICENSE).
