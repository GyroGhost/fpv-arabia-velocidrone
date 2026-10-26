"""Daily round logic and JSON storage. No Discord code here, so it can be tested alone."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta

from velocidrone import Entry, Track, arab_only

POINTS = [10, 8, 6, 5, 4, 3, 2, 1]
PARTICIPATION_POINT = 1


def points_for(place: int) -> int:
    return POINTS[place - 1] if place <= len(POINTS) else PARTICIPATION_POINT


class Store:
    """Everything the bot remembers, in one JSON file."""

    def __init__(self, path: str):
        self.path = path
        self.data = {
            "round": None,        # current round
            "history": [],        # finished rounds (track key, date, results)
            "months": {},         # "2026-10" -> {pilot: points}
            "links": {},          # VelociDrone name -> Discord user id
            "winner_user": None,  # who holds the daily winner role
        }
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data.update(json.load(f))

    def save(self) -> None:
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def recent_track_keys(self, days: int, now: datetime) -> set[str]:
        cutoff = (now - timedelta(days=days)).isoformat()
        return {h["track_key"] for h in self.data["history"] if h["ended_at"] >= cutoff}


def start_round(track: Track, entries: list[Entry], now: datetime, ends_at: datetime) -> dict:
    """A new round. The baseline is every Arab pilot's best time before it starts."""
    return {
        "track": track.to_dict(),
        "track_key": f"{track.scenery_id}/{track.track_id}",
        "started_at": now.isoformat(),
        "ends_at": ends_at.isoformat(),
        "board_size": len(entries),
        "baseline": {p: e.time for p, e in arab_only(entries).items()},
        "results": {},        # pilot -> entry dict, only times set during the round
        "announce_message_id": None,
    }


def update_round(rnd: dict, entries: list[Entry]) -> list[tuple[Entry, float | None]]:
    """Record new or faster times. Returns (entry, previous round time or None) per change."""
    changes = []
    for pilot, e in arab_only(entries).items():
        before = rnd["baseline"].get(pilot)
        if before is not None and e.time >= before - 1e-6:
            continue  # same time as before the round started
        prev = rnd["results"].get(pilot)
        if prev and e.time >= prev["time"] - 1e-6:
            continue
        rnd["results"][pilot] = e.to_dict()
        changes.append((e, prev["time"] if prev else None))
    return changes


def ranking(rnd: dict) -> list[dict]:
    return sorted(rnd["results"].values(), key=lambda r: r["time"])


def place_of(rnd: dict, pilot: str) -> int:
    for i, r in enumerate(ranking(rnd), 1):
        if r["pilot"] == pilot:
            return i
    return 0


def finish_round(store: Store, rnd: dict, now: datetime) -> list[dict]:
    """Award points and archive the round. Returns the final ranking with points."""
    final = []
    month = store.data["months"].setdefault(now.strftime("%Y-%m"), {})
    for place, r in enumerate(ranking(rnd), 1):
        pts = points_for(place)
        month[r["pilot"]] = month.get(r["pilot"], 0) + pts
        final.append({**r, "place": place, "points": pts})
    store.data["history"].append({
        "track_key": rnd["track_key"],
        "track": rnd["track"],
        "started_at": rnd["started_at"],
        "ended_at": now.isoformat(),
        "results": final,
    })
    store.data["history"] = store.data["history"][-400:]
    store.data["round"] = None
    return final


def month_table(store: Store, month: str) -> list[tuple[str, int]]:
    return sorted(store.data["months"].get(month, {}).items(), key=lambda kv: (-kv[1], kv[0]))


def fmt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}" if m else f"{s:.3f}"


def flag(code: str) -> str:
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - ord("a")) for c in code.lower())
