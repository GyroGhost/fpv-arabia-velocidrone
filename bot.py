"""FPV Arabia — daily VelociDrone track.

Every day the bot picks a track, watches its public leaderboard for pilots
from Arab countries, posts new times, and closes the day with results and
monthly points.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import messages as M
from rounds import Store, finish_round, month_table, place_of, ranking, start_round, update_round
from velocidrone import Client, Track

load_dotenv()
log = logging.getLogger("vdbot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kuwait"))
START_HOUR = int(os.getenv("START_HOUR", "20"))
POLL_MINUTES = int(os.getenv("POLL_MINUTES", "10"))
MAX_ENTRIES = int(os.getenv("MAX_ENTRIES", "180"))
NO_REPEAT_DAYS = int(os.getenv("NO_REPEAT_DAYS", "90"))
WINNER_ROLE_ID = int(os.getenv("WINNER_ROLE_ID", "0"))
DATA_FILE = os.getenv("DATA_FILE", "data/state.json")

store = Store(DATA_FILE)
vd = Client()
lock = asyncio.Lock()
last_poll = datetime.min.replace(tzinfo=TZ)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def now() -> datetime:
    return datetime.now(TZ)


def next_start(t: datetime) -> datetime:
    """Next START_HOUR, at least 6 hours away so a round is never too short."""
    s = t.replace(hour=START_HOUR, minute=0, second=0, microsecond=0)
    while s - t < timedelta(hours=6):
        s += timedelta(days=1)
    return s


def links() -> dict:
    return store.data["links"]


async def channel() -> discord.abc.Messageable:
    return client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)


async def open_round(url: str | None = None) -> None:
    t = now()
    if url:
        track = await asyncio.to_thread(vd.track_from_url, url)
        entries = await asyncio.to_thread(vd.leaderboard, track)
    else:
        avoid = store.recent_track_keys(NO_REPEAT_DAYS, t)
        track, entries = await asyncio.to_thread(vd.pick_track, avoid, MAX_ENTRIES)
    rnd = start_round(track, entries, t, next_start(t))
    store.data["round"] = rnd
    number = len(store.data["history"]) + 1
    msg = await (await channel()).send(embed=M.announce(rnd, number))
    rnd["announce_message_id"] = msg.id
    store.save()
    log.info("round %s started: %s / %s (%d entries)", number, track.scenery, track.name, len(entries))


async def poll_round() -> None:
    rnd = store.data["round"]
    if not rnd:
        return
    entries = await asyncio.to_thread(vd.leaderboard, Track(**rnd["track"]))
    changes = update_round(rnd, entries)
    if changes:
        store.save()
        ch = await channel()
        for entry, prev in changes:
            await ch.send(M.new_time(entry, place_of(rnd, entry.pilot), prev, links()),
                          allowed_mentions=discord.AllowedMentions.none())


async def close_round() -> None:
    rnd = store.data["round"]
    try:
        await poll_round()  # last look before closing
    except Exception:
        log.exception("final poll failed")
    t = now()
    final = finish_round(store, rnd, t)
    store.save()
    ch = await channel()
    await ch.send(embed=M.standings_embed(rnd, final, links(), final=True),
                  allowed_mentions=discord.AllowedMentions.none())
    await ch.send(embed=M.month_embed(t.strftime("%Y-%m"), month_table(store, t.strftime("%Y-%m")), links()),
                  allowed_mentions=discord.AllowedMentions.none())
    if final:
        await move_winner_role(ch, final[0]["pilot"])


async def move_winner_role(ch, pilot: str) -> None:
    if not WINNER_ROLE_ID or not hasattr(ch, "guild"):
        return
    guild = ch.guild
    role = guild.get_role(WINNER_ROLE_ID)
    if not role:
        return
    for member in list(role.members):
        try:
            await member.remove_roles(role, reason="Daily VelociDrone track")
        except discord.HTTPException:
            log.warning("could not remove role from %s", member)
    uid = links().get(pilot.lower())
    if not uid:
        return
    member = guild.get_member(int(uid))
    if member:
        await member.add_roles(role, reason="Daily VelociDrone track winner")
        await ch.send(M.WINNER_ROLE_NOTE.format(mention=member.mention))


@tasks.loop(minutes=1)
async def scheduler() -> None:
    global last_poll
    if lock.locked():
        return
    async with lock:
        try:
            rnd = store.data["round"]
            t = now()
            if rnd and t >= datetime.fromisoformat(rnd["ends_at"]):
                await close_round()
                rnd = None
            if not rnd:
                await open_round()
                last_poll = t
            elif t - last_poll >= timedelta(minutes=POLL_MINUTES):
                last_poll = t
                await poll_round()
        except Exception:
            log.exception("scheduler step failed")


# ----------------------------------------------------------------- commands

@tree.command(name="vd_track", description="حلبة اليوم والترتيب الحالي")
async def vd_track(inter: discord.Interaction):
    rnd = store.data["round"]
    if not rnd:
        await inter.response.send_message(M.NO_ROUND, ephemeral=True)
        return
    await inter.response.send_message(
        embeds=[M.announce(rnd, len(store.data["history"]) + 1),
                M.standings_embed(rnd, ranking(rnd), links(), final=False)],
        allowed_mentions=discord.AllowedMentions.none())


@tree.command(name="vd_month", description="ترتيب الشهر")
async def vd_month(inter: discord.Interaction):
    m = now().strftime("%Y-%m")
    await inter.response.send_message(embed=M.month_embed(m, month_table(store, m), links()),
                                      allowed_mentions=discord.AllowedMentions.none())


@tree.command(name="vd_link", description="اربط اسمك في VelociDrone بحسابك")
@app_commands.describe(name="اسمك كما يظهر في VelociDrone")
async def vd_link(inter: discord.Interaction, name: str):
    name = name.strip()
    for k, v in list(links().items()):
        if v == inter.user.id:
            del links()[k]
    links()[name.lower()] = inter.user.id
    store.save()
    await inter.response.send_message(M.LINKED.format(name=name), ephemeral=True)


@tree.command(name="vd_unlink", description="فك ربط اسمك في VelociDrone")
async def vd_unlink(inter: discord.Interaction):
    for k, v in list(links().items()):
        if v == inter.user.id:
            del links()[k]
    store.save()
    await inter.response.send_message(M.UNLINKED, ephemeral=True)


@tree.command(name="vd_new", description="(للإدارة) تغيير حلبة اليوم بدون احتساب نقاط")
@app_commands.describe(url="رابط Leaderboard من موقع VelociDrone (اختياري)")
@app_commands.default_permissions(manage_guild=True)
async def vd_new(inter: discord.Interaction, url: str | None = None):
    if url and "velocidrone.com/leaderboard/" not in url:
        await inter.response.send_message(M.BAD_LINK, ephemeral=True)
        return
    await inter.response.defer(ephemeral=True)
    async with lock:
        old = store.data["round"]
        store.data["round"] = None
        try:
            await open_round(url)
        except Exception:
            log.exception("vd_new failed")
            store.data["round"] = old
            await inter.followup.send(M.FETCH_ERROR, ephemeral=True)
            return
    await inter.followup.send(M.NEW_TRACK_STARTED, ephemeral=True)


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    log.info("logged in as %s", client.user)
    if not scheduler.is_running():
        scheduler.start()


if __name__ == "__main__":
    client.run(TOKEN, log_handler=None)
