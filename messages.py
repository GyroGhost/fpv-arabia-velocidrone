"""All Arabic text the bot posts. English labels stay on their own lines or in code blocks."""
from __future__ import annotations

from datetime import datetime

import discord

from rounds import flag, fmt_time

COLOR = 0xE53935  # GyroGhost red
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _ts(iso: str, style: str = "R") -> str:
    return f"<t:{int(datetime.fromisoformat(iso).timestamp())}:{style}>"


def _who(pilot: str, links: dict) -> str:
    uid = links.get(pilot.lower())
    return f"**{pilot}** (<@{uid}>)" if uid else f"**{pilot}**"


def announce(rnd: dict, number: int) -> discord.Embed:
    t = rnd["track"]
    e = discord.Embed(
        title=f"🏁 حلبة اليوم #{number}",
        color=COLOR,
        url=f"https://www.velocidrone.com/leaderboard/{t['scenery_id']}/{t['track_id']}/All",
        description=(
            "طير الحلبة في VelociDrone بأي درون، والبوت يلقط وقتك من الموقع تلقائياً.\n\n"
            f"تنتهي البطولة {_ts(rnd['ends_at'])}"
        ),
    )
    e.add_field(name="المكان", value=f"```{t['scenery']}```", inline=True)
    e.add_field(name="الحلبة", value=f"```{t['name']}```", inline=True)
    e.add_field(
        name="عشان ينحسب وقتك",
        value=(
            "1️⃣ اختر وضع السباق:\n```3 Lap: Single Class```"
            "2️⃣ فعّل رفع الأوقات:\n```Options → Main Settings → Auto Leaderboard Upload → Yes```"
            "3️⃣ خل علم دولتك العربية ظاهر في حسابك على موقع VelociDrone.\n"
            "4️⃣ اربط اسمك في المحاكي بحسابك هنا:\n```/vd_link```"
        ),
        inline=False,
    )
    e.set_footer(text="النقاط: 10 · 8 · 6 · 5 · 4 · 3 · 2 · 1 · وكل مشارك ياخذ نقطة")
    return e


def new_time(entry, place: int, prev: float | None, links: dict) -> str:
    line = f"⏱️ {flag(entry.country)} {_who(entry.pilot, links)} سجل وقت جديد: `{fmt_time(entry.time)}`"
    if prev is not None:
        line += f" (أسرع بـ `{prev - entry.time:.3f}` ثانية)"
    return line + f"\nترتيبه الحين: {MEDALS.get(place, '')} المركز {place}"


def standings_embed(rnd: dict, rows: list[dict], links: dict, final: bool) -> discord.Embed:
    t = rnd["track"]
    title = "🏆 نتائج حلبة اليوم" if final else "📊 الترتيب الحالي"
    e = discord.Embed(title=title, color=COLOR)
    e.description = f"```{t['scenery']} — {t['name']}```"
    if not rows:
        e.description += "\nما أحد سجل وقت للحين."
        return e
    lines = []
    for i, r in enumerate(rows[:20], 1):
        pts = f" · +{r['points']}" if final else ""
        lines.append(f"{MEDALS.get(i, f'`{i}.`')} {flag(r['country'])} {_who(r['pilot'], links)} — `{fmt_time(r['time'])}`{pts}")
    e.description += "\n" + "\n".join(lines)
    if not final:
        e.description += f"\n\nتنتهي {_ts(rnd['ends_at'])}"
    return e


def month_embed(month: str, table: list[tuple[str, int]], links: dict) -> discord.Embed:
    e = discord.Embed(title="📅 ترتيب الشهر", color=COLOR)
    e.description = f"```{month}```"
    if not table:
        e.description += "\nما فيه نقاط هالشهر للحين."
        return e
    e.description += "\n" + "\n".join(
        f"{MEDALS.get(i, f'`{i}.`')} {_who(p, links)} — **{pts}** نقطة" for i, (p, pts) in enumerate(table[:15], 1))
    return e


NO_ROUND = "ما فيه بطولة شغالة الحين."
LINKED = "تم ربط اسمك في VelociDrone:\n```{name}```"
UNLINKED = "تم فك الربط."
NEW_TRACK_STARTED = "تم اختيار حلبة جديدة ✅"
BAD_LINK = "الرابط لازم يكون صفحة Leaderboard من موقع VelociDrone، مثل:\n```https://www.velocidrone.com/leaderboard/33/467/All```"
FETCH_ERROR = "ما قدرت أوصل لموقع VelociDrone الحين، جرب بعد شوي."
WINNER_ROLE_NOTE = "🎖️ {mention} ياخذ رتبة بطل الحلبة لين البطولة الجاية."
