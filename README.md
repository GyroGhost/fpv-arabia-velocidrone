# FPV Arabia — Daily VelociDrone Track 🏁

A Discord bot for **FPV Arabia**, the Arabic-speaking FPV community. Every day it picks a VelociDrone track, follows its public leaderboard for pilots from Arab countries, and posts the results, all in Arabic.

---

## How it works

1. At the start hour the bot picks a random official track and posts it.
2. Pilots fly it in **3 Lap: Single Class** with **Auto Leaderboard Upload** turned on.
3. Every few minutes the bot reads the track's leaderboard on velocidrone.com. Any pilot with an Arab country flag who sets a new or faster time is posted in the channel.
4. When the day ends the bot posts the final results, adds monthly points and starts the next track.

Only times set during the day count. Times that were already on the leaderboard before the track was announced are ignored.

**Points:** 10 · 8 · 6 · 5 · 4 · 3 · 2 · 1, and 1 point for every other pilot who flew.

### Why tracks with room on the leaderboard

The VelociDrone website shows the top 200 times of a track and nothing below. The bot prefers tracks with fewer entries (`MAX_ENTRIES`), so every member's time shows up, not only the fastest ones.

---

## Running on GitHub Actions

The bot does not need a server. `.github/workflows/daily-track.yml` runs `run.py` every 15 minutes, and the run saves its state to `data/state.json` in this repo.

1. Add the bot token as a repository secret named `DISCORD_TOKEN` (Settings → Secrets and variables → Actions).
2. Channel and server ids are set in the workflow file.
3. Optional: add a repository variable `WINNER_ROLE_ID` to give the daily winner a role. The bot role must be above that role in the server settings.

Every new track pings `@everyone` (the bot needs the **Mention @everyone** permission in the channel). Change `PING_NEW_TRACK` in the workflow to `here`, a role id, or leave it empty for no ping.

The Gyro logo and banner are loaded from `assets/logo.png` and `assets/banner.png` in this repo.

Current standings are posted at 9:00 and 15:00 (Kuwait time) when someone has flown.

### Replacing today's track

Actions → Daily VelociDrone track → Run workflow, then type `random` or paste a leaderboard link. No points are given for the replaced track.

### Linking pilots to Discord

Add pilots to `links.json` to mention them and give the winner role:

```json
{
  "VelociDrone name": "Discord user id"
}
```

---

## Project layout

| File | Purpose |
|---|---|
| `run.py` | One check: open, update or close the day's track |
| `velocidrone.py` | Reads the public leaderboard pages |
| `rounds.py` | Daily round logic, points and storage |
| `messages.py` | Arabic messages |
| `links.json` | VelociDrone names linked to Discord accounts |
| `tests/` | Tests with saved leaderboard pages |

Run the tests:
```
pip install requests pytest
python -m pytest tests
```

---

## Notes

- Data comes only from the public pages of velocidrone.com, checked every 15 minutes.
- Pilots need their country set on their VelociDrone account for the flag to show.
- The website keeps the race mode in the session; the bot always reads the **3 Lap: Single Class** boards.

## License

GPL-3.0
