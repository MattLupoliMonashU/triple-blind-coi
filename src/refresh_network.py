"""
refresh_network.py
==================
AI-driven network maintenance agent for the Triple-Blind COI system.

This script is run automatically every night by a GitHub Actions workflow
(.github/workflows/refresh.yml). It queries OpenAlex for each scholar
profile currently in the local cache, detects any changes (new publications,
affiliation changes, new co-authors), updates the cache, and writes a
structured log entry to data/refresh_log.jsonl.

This implements the daily network-update process described in the manuscript:

    "An AI data-gathering agent populates the scholarly network database
     from publicly available sources and updates it on a daily basis."
     — Lupoli (2026)

Usage
-----
    # Run manually (from repo root):
    python src/refresh_network.py

    # Automated: triggered nightly by .github/workflows/refresh.yml
    # View run history under the Actions tab on GitHub.

Output
------
    data/refresh_log.jsonl   — one JSON record per scholar per run;
                               append-only so the full update history
                               is preserved.
"""

import os
import json
import hashlib
import dataclasses
from datetime import datetime, timezone
from typing import Optional

# Ensure src/ is importable when run from repo root
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.coi_engine import (
    ScholarProfile,
    fetch_openalex_profile,
    CACHE_DIR,
    _cache_key,
    _save_cache,
    CURRENT_YEAR,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT    = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR     = os.path.join(REPO_ROOT, "data")
LOG_PATH     = os.path.join(DATA_DIR, "refresh_log.jsonl")
DEMO_SEEDS   = os.path.join(REPO_ROOT, "examples", "seed_scholars.json")


# ---------------------------------------------------------------------------
# Fingerprinting — detect meaningful changes in a profile
# ---------------------------------------------------------------------------

def _profile_fingerprint(profile: ScholarProfile) -> str:
    """
    A stable hash of the parts of a profile that matter for COI scoring:
    co-author list, institutions, editorial roles, advisor/advisee IDs.
    Ignores fetched_at (changes every run) and source_urls.
    """
    key_data = {
        "coauthors": sorted(
            [{"id": c.get("id", ""), "most_recent_year": c.get("most_recent_year", 0)}
             for c in profile.coauthors],
            key=lambda x: x["id"]
        ),
        "institutions": sorted(
            [{"name": i.get("name", ""), "years": sorted(i.get("years", []))}
             for i in profile.institutions],
            key=lambda x: x["name"]
        ),
        "editorial_roles": sorted(
            [r.get("journal", "") for r in profile.editorial_roles]
        ),
        "advisor_ids":  sorted(profile.advisor_ids),
        "advisee_ids":  sorted(profile.advisee_ids),
    }
    return hashlib.md5(
        json.dumps(key_data, sort_keys=True).encode()
    ).hexdigest()


def _load_cached_profile(name: str) -> Optional[ScholarProfile]:
    path = os.path.join(CACHE_DIR, f"{_cache_key(name)}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    return ScholarProfile(**d)


def _load_all_cached_names() -> list[str]:
    """Return the display names of all scholars currently in the cache."""
    if not os.path.exists(CACHE_DIR):
        return []
    names = []
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CACHE_DIR, fname)
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get("name"):
                names.append(d["name"])
        except (json.JSONDecodeError, KeyError):
            continue
    return names


def _load_seed_scholars() -> list[str]:
    """
    Load the list of seed scholars from examples/seed_scholars.json.
    These are refreshed even if they have never been queried (no cache entry).
    Falls back to an empty list if the file does not exist.
    """
    if not os.path.exists(DEMO_SEEDS):
        return []
    with open(DEMO_SEEDS) as f:
        data = json.load(f)
    return data.get("scholars", [])


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def _diff_profiles(old: ScholarProfile, new: ScholarProfile) -> dict:
    """
    Compare old and new profiles; return a dict describing what changed.
    Empty dict means no meaningful change.
    """
    changes = {}

    old_coauthor_ids = {c["id"] for c in old.coauthors if c.get("id")}
    new_coauthor_ids = {c["id"] for c in new.coauthors if c.get("id")}
    added   = new_coauthor_ids - old_coauthor_ids
    removed = old_coauthor_ids - new_coauthor_ids
    if added:
        added_names = [
            c["name"] for c in new.coauthors if c.get("id") in added
        ]
        changes["new_coauthors"] = added_names
    if removed:
        removed_names = [
            c["name"] for c in old.coauthors if c.get("id") in removed
        ]
        changes["removed_coauthors"] = removed_names

    # Recency updates for existing co-authors
    old_recency = {
        c["id"]: c.get("most_recent_year", 0)
        for c in old.coauthors if c.get("id")
    }
    new_recency = {
        c["id"]: c.get("most_recent_year", 0)
        for c in new.coauthors if c.get("id")
    }
    updated_recency = [
        {"id": aid, "old_year": old_recency[aid], "new_year": new_recency[aid]}
        for aid in old_coauthor_ids & new_coauthor_ids
        if new_recency.get(aid, 0) > old_recency.get(aid, 0)
    ]
    if updated_recency:
        changes["updated_coauthor_recency"] = updated_recency

    old_insts = {i["name"] for i in old.institutions}
    new_insts = {i["name"] for i in new.institutions}
    if new_insts - old_insts:
        changes["new_institutions"] = list(new_insts - old_insts)
    if old_insts - new_insts:
        changes["removed_institutions"] = list(old_insts - new_insts)

    return changes


# ---------------------------------------------------------------------------
# Per-scholar refresh
# ---------------------------------------------------------------------------

def refresh_scholar(name: str, run_id: str) -> dict:
    """
    Refresh one scholar's profile. Returns a log record (dict).
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    old_profile = _load_cached_profile(name)
    old_fp = _profile_fingerprint(old_profile) if old_profile else None

    new_profile = fetch_openalex_profile(name)

    if new_profile is None:
        return {
            "run_id":    run_id,
            "timestamp": timestamp,
            "scholar":   name,
            "status":    "fetch_failed",
            "changes":   {},
        }

    new_fp = _profile_fingerprint(new_profile)

    if old_fp == new_fp:
        # No meaningful change — update fetched_at only
        _save_cache(new_profile)
        return {
            "run_id":    run_id,
            "timestamp": timestamp,
            "scholar":   new_profile.name,
            "status":    "no_change",
            "changes":   {},
        }

    changes = _diff_profiles(old_profile, new_profile) if old_profile else {
        "note": "first_fetch"
    }
    _save_cache(new_profile)

    return {
        "run_id":    run_id,
        "timestamp": timestamp,
        "scholar":   new_profile.name,
        "status":    "updated",
        "changes":   changes,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_refresh() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    run_id    = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_start = datetime.now(timezone.utc).isoformat()

    # Combine cached scholars and seed scholars (deduplicated)
    cached_names = _load_all_cached_names()
    seed_names   = _load_seed_scholars()
    all_names    = list({n.strip() for n in cached_names + seed_names if n.strip()})

    print(f"[{run_id}] Starting refresh: {len(all_names)} scholar(s) to check.")

    records      = []
    n_updated    = 0
    n_no_change  = 0
    n_failed     = 0

    for name in all_names:
        print(f"  Refreshing: {name} ...", end=" ", flush=True)
        record = refresh_scholar(name, run_id)
        records.append(record)

        status = record["status"]
        if status == "updated":
            n_updated += 1
            print(f"UPDATED — {list(record['changes'].keys())}")
        elif status == "no_change":
            n_no_change += 1
            print("no change.")
        else:
            n_failed += 1
            print("FETCH FAILED.")

    # Write summary record
    summary = {
        "run_id":       run_id,
        "timestamp":    run_start,
        "scholar":      "__summary__",
        "status":       "summary",
        "changes": {
            "total_checked": len(all_names),
            "updated":       n_updated,
            "no_change":     n_no_change,
            "fetch_failed":  n_failed,
        },
    }
    records.append(summary)

    # Append all records to the log (one JSON object per line)
    with open(LOG_PATH, "a") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(
        f"[{run_id}] Done. "
        f"{n_updated} updated, {n_no_change} unchanged, {n_failed} failed. "
        f"Log: {LOG_PATH}"
    )


if __name__ == "__main__":
    run_refresh()
