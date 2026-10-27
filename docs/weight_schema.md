# COI Weight Schema — v0.2

## Overview

Each pair of scholars is assigned a COI score in [0, 1] that reflects the
probability of a meaningful conflict of interest. The score is based on the
**type and recency** of the professional relationship between the two
scholars, consistent with the approach described in the manuscript:

> "A given individual's COI score is based on the type and recency of their
> professional relationship with Professor Pierce, where direct ties, such as
> co-authorship, receive greater weight than indirect ties, such as shared
> institutional affiliation."
> — Lupoli (2026)

## Combination formula

Independent relationship channels are combined using the **complement
product rule**:

```
COI_score = 1 − ∏ᵢ (1 − wᵢ)
```

This computes P(at least one conflict channel is active), prevents any single
channel from dominating, and caps naturally at 1.0. It is consistent with
related systems in the literature (Aleman-Meza et al., 2006; Wu et al., 2018).

## Relationship types and base weights (v0.2)

Tier boundaries for co-authorship recency align with ACM (2 yr), NSF (48 mo / 4 yr),
and IACR (2 yr institutional window) published COI policies.
The advisor–advisee relationship is treated as **permanent** per ACM, IACR, and NSF,
which all classify it as a lifelong COI with no time limit.

| Relationship type | Base weight | Notes |
|---|---|---|
| Co-authorship 0–2 years | **0.90** | ACM 2-yr policy threshold |
| Co-authorship 2–4 years | **0.70** | NSF 48-month policy threshold |
| Co-authorship 4–6 years | **0.40** | Beyond any policy window; moderate decay |
| Co-authorship > 6 years | **0.15** | Weak residual tie; design judgement |
| Current shared institution | **0.85** | IACR/ACM/NSF: automatic COI |
| Former shared institution | **0.35 − 0.175×yrs** | ~0 at 2 yrs (IACR window); floored at 0 |
| Advisor–advisee | **0.95** | Permanent — IACR/ACM/NSF: lifetime COI; no decay |
| Editorial board co-membership | **0.40** | COPE/ACM policy basis; no empirical anchor |
| Shared collaborator (2nd-degree) | **0.20** | Aleman-Meza et al. (2006): low-to-medium boundary |

## Default alert threshold

**0.50** — configurable per journal. The manuscript example uses 0.50:
> "John Doe has a conflict-of-interest score ... of .63, which exceeds the
> journal's recommended threshold of .50."

Journals with larger editorial boards may lower this threshold; smaller or
specialist journals may raise it to avoid blocking the eligible reviewer pool.

## Calibration note

These weights represent **v0.2 defaults** calibrated against the published COI policies
of ACM, IACR, and NSF — the three bodies that publish unusually detailed, explicit
COI rules. Where those policies set time windows for particular relationship types,
the weights are anchored to those windows. Where no policy guidance exists, the weights
are stated as design choices. As stated in the manuscript, "the final calculation of
the COI score is a work in progress that will undergo extensive recursive testing with
external feedback."

Future calibration will use:
1. Known COI cases reported by adopting journals
2. Comparison against outcomes in Colussi (2018) and Brogaard et al. (2014)
3. Bayesian updating of weights using accumulated validation data

## Planned additions (future versions)

| Relationship | Planned detection method |
|---|---|
| Funding co-receipt | NIH Reporter, OpenAire |
| Conference co-organisation | DBLP proceedings |
| Financial ties | SEC filings, company registries |
| Patent co-inventorship | USPTO, EPO APIs |

## References

- Aleman-Meza, B., et al. (2006). Semantic analytics on social networks. *WWW 2006*, 407–416.
- Brogaard, J., Engelberg, J., & Parsons, C. A. (2014). Networks and productivity. *JFE*, 111(1), 251–270.
- Colussi, T. (2018). Social ties in academia. *RES*, 100(1), 45–50.
- Freeman, L. C. (1979). Centrality in social networks. *Social Networks*, 1(3), 215–239.
- Harvey, D., et al. (2024). Prophy. *ISU*, 44(1), 37–42.
- Wu, S., et al. (2018). PISTIS. *SIGMOD 2018*.
