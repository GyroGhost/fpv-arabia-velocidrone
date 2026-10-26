"""Read public VelociDrone leaderboards from velocidrone.com.

Only the public website pages are used. The site keeps the race mode in the
session, so every session switches to "3 Lap: Single Class" before reading.
Each leaderboard page shows at most 200 rows.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, asdict
from html import unescape

import requests

BASE = "https://www.velocidrone.com"
RACE_MODE_3_LAPS = 6
PAGE_ROW_LIMIT = 200

# Arab League members (ISO 3166-1 alpha-2, lowercase like the site's flag classes)
ARAB_COUNTRIES = {
    "kw", "sa", "ae", "qa", "bh", "om", "ye", "iq", "sy", "jo", "lb", "ps",
    "eg", "sd", "ly", "tn", "dz", "ma", "mr", "so", "dj", "km",
}

HEADERS = {
    "User-Agent": "FPV-Arabia-VelociDrone-Bot/1.0 (+https://github.com/GyroGhost)",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class Entry:
    pilot: str
    time: float
    country: str
    model: str
    date: str  # dd/mm/yyyy as shown on the site

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Track:
    scenery_id: int
    track_id: int
    scenery: str
    name: str

    @property
    def url(self) -> str:
        return f"{BASE}/leaderboard/{self.scenery_id}/{self.track_id}/All"

    def to_dict(self) -> dict:
        return asdict(self)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_leaderboard(html: str) -> list[Entry]:
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.S | re.I)
    if not body:
        return []
    entries = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        if len(cells) < 7:
            continue
        pilot_html = re.sub(r'<span class="subtext">.*?</span>', "", cells[2], flags=re.S)
        flag = re.search(r'class="fi fi-([a-z]{2})"', cells[3])
        try:
            lap_time = float(_text(cells[1]))
        except ValueError:
            continue
        entries.append(Entry(
            pilot=_text(pilot_html),
            time=lap_time,
            country=flag.group(1) if flag else "",
            model=_text(cells[5]),
            date=_text(cells[6]),
        ))
    return entries


def parse_titles(html: str) -> tuple[str, str]:
    """(scenery, track) from a leaderboard page."""
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", html, re.S)
    h3 = re.search(r"<h3[^>]*>(.*?)</h3>", html, re.S)
    return (_text(h2.group(1)) if h2 else "", _text(h3.group(1)) if h3 else "")


def parse_sceneries(html: str) -> dict[int, str]:
    found = {}
    for name, sid in re.findall(
        r'<h2 class="card-title">(.*?)</h2>\s*<div class="card-actions[^"]*">\s*'
        r'<a href\s*=\s*"[^"]*/leaderboard_by_version/(\d+)/All"', html, re.S):
        found[int(sid)] = _text(name)
    return found


def parse_tracks(html: str) -> list[tuple[int, int, str]]:
    return [(int(s), int(t), _text(n)) for s, t, n in re.findall(
        r'href="[^"]*/leaderboard/(\d+)/(\d+)/All"[^>]*>(.*?)</a>', html, re.S)]


def best_per_pilot(entries: list[Entry]) -> dict[str, Entry]:
    best: dict[str, Entry] = {}
    for e in entries:
        if e.pilot and (e.pilot not in best or e.time < best[e.pilot].time):
            best[e.pilot] = e
    return best


def arab_only(entries: list[Entry]) -> dict[str, Entry]:
    return best_per_pilot([e for e in entries if e.country in ARAB_COUNTRIES])


class Client:
    def __init__(self, delay: float = 1.5, timeout: float = 30):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._mode_set_at = 0.0

    def _get(self, url: str) -> str:
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        time.sleep(self.delay)
        return r.text

    def _ensure_mode(self) -> None:
        if time.time() - self._mode_set_at > 600:
            self._get(f"{BASE}/set_race_mode/{RACE_MODE_3_LAPS}")
            self._mode_set_at = time.time()

    def leaderboard(self, track: Track) -> list[Entry]:
        self._ensure_mode()
        return parse_leaderboard(self._get(track.url))

    def track_from_url(self, url: str) -> Track:
        m = re.search(r"/leaderboard/(\d+)/(\d+)", url)
        if not m:
            raise ValueError("not a VelociDrone leaderboard link")
        self._ensure_mode()
        scenery, name = parse_titles(self._get(f"{BASE}/leaderboard/{m.group(1)}/{m.group(2)}/All"))
        return Track(int(m.group(1)), int(m.group(2)), scenery, name)

    def pick_track(self, avoid: set[str], max_entries: int, tries: int = 25) -> tuple[Track, list[Entry]]:
        """Random official track that still has room on its leaderboard.

        A board below the 200-row limit shows every pilot, so a new time from
        any member is visible to the bot.
        """
        sceneries = parse_sceneries(self._get(f"{BASE}/leaderboards"))
        if not sceneries:
            raise RuntimeError("could not read the scenery list")
        self._ensure_mode()
        fallback = None
        for _ in range(tries):
            sid = random.choice(list(sceneries))
            tracks = [t for t in parse_tracks(self._get(f"{BASE}/leaderboard_by_version/{sid}/All"))
                      if f"{t[0]}/{t[1]}" not in avoid]
            if not tracks:
                continue
            s, t, name = random.choice(tracks)
            track = Track(s, t, sceneries.get(s, ""), name)
            entries = self.leaderboard(track)
            if 0 < len(entries) <= max_entries:
                return track, entries
            if entries and (fallback is None or len(entries) < len(fallback[1])):
                fallback = (track, entries)
        if fallback is None:
            raise RuntimeError("no track found")
        return fallback
