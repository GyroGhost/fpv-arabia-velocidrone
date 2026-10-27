"""All Arabic text the bot posts. English labels stay on their own lines or in code blocks."""
from __future__ import annotations

import os
from datetime import datetime

from rounds import flag, fmt_time

COLOR = 0xE53935  # GyroGhost red
ASSETS = "https://raw.githubusercontent.com/GyroGhost/fpv-arabia-velocidrone/main/assets"
LOGO_URL = os.getenv("LOGO_URL") or f"{ASSETS}/logo.png"
BANNER_URL = os.getenv("BANNER_URL") or f"{ASSETS}/banner.png"
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _embed(**kw) -> dict:
    """Plain Discord embed dict, sent through the REST API, with the Gyro logo in the corner."""
    e = {k: v for k, v in kw.items() if v is not None}
    if LOGO_URL:
        e["thumbnail"] = {"url": LOGO_URL}
    return e


LRM = "\u200e"  # keeps English code blocks left-to-right inside Arabic messages


def _code(text: str) -> str:
    return f"```{LRM}{text}```"


def _ltr(text: str) -> str:
    """Isolate an English or number run so Arabic text around it does not reorder it."""
    return f"\u2066{text}\u2069"


def _ts(iso: str, style: str = "R") -> str:
    return f"<t:{int(datetime.fromisoformat(iso).timestamp())}:{style}>"


def _who(pilot: str, links: dict) -> str:
    uid = links.get(pilot.lower())
    return f"**{pilot}** (<@{uid}>)" if uid else f"**{pilot}**"


def announce(rnd: dict, number: int) -> dict:
    t = rnd["track"]
    e = _embed(
        title=f"🏁 حلبة اليوم #{number}",
        color=COLOR,
        url=f"https://www.velocidrone.com/leaderboard/{t['scenery_id']}/{t['track_id']}/All",
        description=(
            "طير الحلبة في VelociDrone بأي درون، والبوت يلقط وقتك من الموقع تلقائياً.\n\n"
            f"تنتهي البطولة {_ts(rnd['ends_at'])}"
        ),
    )
    e["fields"] = [
        {"name": "المكان", "value": _code(t['scenery']), "inline": True},
        {"name": "الحلبة", "value": _code(t['name']), "inline": True},
        {"name": "عشان ينحسب وقتك", "inline": False, "value": (
            f"1️⃣ اختر وضع السباق:\n{_code('3 Lap: Single Class')}"
            f"2️⃣ فعّل رفع الأوقات:\n{_code('Options → Main Settings → Auto Leaderboard Upload → Yes')}"
            "3️⃣ خل علم دولتك العربية ظاهر في حسابك على موقع VelociDrone."
        )},
    ]
    if BANNER_URL:
        e["image"] = {"url": BANNER_URL}
    e["footer"] = {"text": f"النقاط من الأول للثامن: {_ltr('10 · 8 · 6 · 5 · 4 · 3 · 2 · 1')}\nوكل مشارك ثاني ياخذ نقطة"}
    return e


def new_time(entry, place: int, prev: float | None, links: dict) -> str:
    line = f"⏱️ {flag(entry.country)} {_who(entry.pilot, links)} سجل وقت جديد: `{fmt_time(entry.time)}`"
    if prev is not None:
        line += f" (أسرع بـ `{prev - entry.time:.3f}` ثانية)"
    return line + f"\nترتيبه الحين: {MEDALS.get(place, '')} المركز {place}"


def standings_embed(rnd: dict, rows: list[dict], links: dict, final: bool) -> dict:
    t = rnd["track"]
    title = "🏆 نتائج حلبة اليوم" if final else "📊 الترتيب الحالي"
    e = _embed(title=title, color=COLOR)
    e["description"] = _code(f"{t['scenery']} — {t['name']}")
    if not rows:
        e["description"] += "\nما أحد سجل وقت في هالحلبة 😅" if final else "\nما أحد سجل وقت للحين."
        return e
    lines = []
    for i, r in enumerate(rows[:20], 1):
        pts = f" · +{r['points']}" if final else ""
        lines.append(f"{MEDALS.get(i, f'`{i}.`')} {flag(r['country'])} {_who(r['pilot'], links)} — `{fmt_time(r['time'])}`{pts}")
    e["description"] += "\n" + "\n".join(lines)
    if not final:
        e["description"] += f"\n\nتنتهي {_ts(rnd['ends_at'])}"
    return e


def month_embed(month: str, table: list[tuple[str, int]], links: dict) -> dict:
    e = _embed(title="📅 ترتيب الشهر", color=COLOR)
    e["description"] = _code(month)
    if not table:
        e["description"] += "\nما فيه نقاط هالشهر للحين."
        return e
    e["description"] += "\n" + "\n".join(
        f"{MEDALS.get(i, f'`{i}.`')} {_who(p, links)} — **{pts}** نقطة" for i, (p, pts) in enumerate(table[:15], 1))
    return e


WINNER_ROLE_NOTE = "🎖️ {mention} ياخذ رتبة بطل الحلبة لين البطولة الجاية."
