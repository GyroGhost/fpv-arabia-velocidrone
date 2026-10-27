"""FPV Arabia — daily VelociDrone track.

Runs once and exits. GitHub Actions starts it every 15 minutes:
  - closes the day's track when its time is up (results, monthly points, winner role)
  - opens a new track when none is running
  - otherwise checks the leaderboard and posts new times
State is kept in data/state.json, which the workflow commits back to the repo.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import messages as M
from rounds import Store, finish_round, month_table, place_of, ranking, start_round, update_round
from velocidrone import Client, Track

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
GUILD_ID = os.getenv("GUILD_ID", "")
TZ = ZoneInfo(os.getenv("TIMEZONE") or "Asia/Kuwait")
START_HOUR = int(os.getenv("START_HOUR") or 20)
MAX_ENTRIES = int(os.getenv("MAX_ENTRIES") or 180)
NO_REPEAT_DAYS = int(os.getenv("NO_REPEAT_DAYS") or 90)
WINNER_ROLE_ID = os.getenv("WINNER_ROLE_ID") or ""
STANDINGS_HOURS = {int(h) for h in (os.getenv("STANDINGS_HOURS") or "9,15").split(",") if h.strip()}
DATA_FILE = os.getenv("DATA_FILE") or "data/state.json"
LINKS_FILE = os.getenv("LINKS_FILE") or "links.json"
NEW_TRACK = (os.getenv("NEW_TRACK") or "").strip()  # manual run: "random" or a leaderboard link

API = "https://discord.com/api/v10"
NO_PINGS = {"parse": []}
# who gets pinged when a new track opens: "everyone", "here", a role id, or empty for nobody
PING = (os.getenv("PING_NEW_TRACK") if os.getenv("PING_NEW_TRACK") is not None else "everyone").strip()


def discord(method: str, path: str, **body) -> dict | None:
    r = requests.request(method, API + path, timeout=30,
                         headers={"Authorization": f"Bot {TOKEN}"},
                         json=body or None)
    if r.status_code >= 400:
        print(f"Discord {method} {path} -> {r.status_code}: {r.text[:300]}", file=sys.stderr)
        r.raise_for_status()
    return r.json() if r.content else None


def send(content: str | None = None, embeds: list[dict] | None = None,
         allowed: dict = NO_PINGS) -> dict | None:
    return discord("POST", f"/channels/{CHANNEL_ID}/messages",
                   content=content, embeds=embeds, allowed_mentions=allowed)


def new_track_ping() -> tuple[str | None, dict]:
    if PING in ("everyone", "here"):
        return f"@{PING}", {"parse": ["everyone"]}
    if PING.isdigit():
        return f"<@&{PING}>", {"parse": [], "roles": [PING]}
    return None, NO_PINGS


def load_links() -> dict:
    if not os.path.exists(LINKS_FILE):
        return {}
    with open(LINKS_FILE, encoding="utf-8") as f:
        return {k.strip().lower(): str(v).strip() for k, v in json.load(f).items()
                if str(v).strip().isdigit()}


def next_start(t: datetime) -> datetime:
    """Next START_HOUR, at least 6 hours away so a round is never too short."""
    s = t.replace(hour=START_HOUR, minute=0, second=0, microsecond=0)
    while s - t < timedelta(hours=6):
        s += timedelta(days=1)
    return s


def open_round(store: Store, vd: Client, now: datetime, url: str | None = None) -> None:
    if url:
        track = vd.track_from_url(url)
        entries = vd.leaderboard(track)
    else:
        track, entries = vd.pick_track(store.recent_track_keys(NO_REPEAT_DAYS, now), MAX_ENTRIES)
    rnd = start_round(track, entries, now, next_start(now))
    store.data["round"] = rnd
    store.save()  # saved before posting, so a failed post never opens a second track
    content, allowed = new_track_ping()
    send(content, embeds=[M.announce(rnd, len(store.data["history"]) + 1)], allowed=allowed)
    print(f"opened: {track.scenery} / {track.name} ({len(entries)} entries)")


def poll_round(store: Store, vd: Client, links: dict) -> None:
    rnd = store.data["round"]
    changes = update_round(rnd, vd.leaderboard(Track(**rnd["track"])))
    if changes:
        store.save()
    for entry, prev in changes:
        send(M.new_time(entry, place_of(rnd, entry.pilot), prev, links))
    print(f"poll: {len(changes)} new times")


def close_round(store: Store, vd: Client, links: dict, now: datetime) -> None:
    rnd = store.data["round"]
    try:
        poll_round(store, vd, links)  # last look before closing
    except Exception as e:
        print(f"final poll failed: {e}", file=sys.stderr)
    final = finish_round(store, rnd, now)
    store.save()
    month = now.strftime("%Y-%m")
    send(embeds=[M.standings_embed(rnd, final, links, final=True),
                 M.month_embed(month, month_table(store, month), links)])
    if final:
        move_winner_role(store, links.get(final[0]["pilot"].lower()))


def move_winner_role(store: Store, winner_id: str | None) -> None:
    if not (WINNER_ROLE_ID and GUILD_ID):
        return
    old = store.data.get("winner_user")
    if old and old != winner_id:
        try:
            discord("DELETE", f"/guilds/{GUILD_ID}/members/{old}/roles/{WINNER_ROLE_ID}")
        except requests.HTTPError:
            pass
    store.data["winner_user"] = winner_id
    store.save()
    if winner_id:
        discord("PUT", f"/guilds/{GUILD_ID}/members/{winner_id}/roles/{WINNER_ROLE_ID}")
        send(M.WINNER_ROLE_NOTE.format(mention=f"<@{winner_id}>"))


def maybe_post_standings(store: Store, links: dict, now: datetime) -> None:
    """Current standings a couple of times a day, once per slot."""
    rnd = store.data["round"]
    slot = now.strftime("%Y-%m-%d ") + str(now.hour)
    if now.hour in STANDINGS_HOURS and rnd.get("standings_slot") != slot and rnd["results"]:
        rnd["standings_slot"] = slot
        store.save()
        send(embeds=[M.standings_embed(rnd, ranking(rnd), links, final=False)])


def main() -> None:
    now = datetime.now(TZ)
    store = Store(DATA_FILE)
    vd = Client()
    links = load_links()

    if NEW_TRACK:
        # manual replacement: no points for the replaced track
        store.data["round"] = None
        open_round(store, vd, now, None if NEW_TRACK.lower() == "random" else NEW_TRACK)
        return

    rnd = store.data["round"]
    if rnd and now >= datetime.fromisoformat(rnd["ends_at"]):
        close_round(store, vd, links, now)
        rnd = None
    if not rnd:
        open_round(store, vd, now)
        return
    poll_round(store, vd, links)
    maybe_post_standings(store, links, now)


if __name__ == "__main__":
    main()
