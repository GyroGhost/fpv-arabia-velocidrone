import os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import velocidrone as V
from rounds import Store, start_round, update_round, finish_round, ranking, month_table, fmt_time, flag

HERE = os.path.dirname(os.path.abspath(__file__))
read = lambda n: open(os.path.join(HERE, n), encoding="utf-8").read()


def entries():
    return V.parse_leaderboard(read("leaderboard.html"))


def test_parse_leaderboard():
    e = entries()
    assert len(e) == 7
    assert e[0].pilot == "neonfpv" and e[0].time == 217.008 and e[0].country == "us"
    assert e[3].pilot == ".MrE."  # "(Beta Tester)" removed
    assert e[6].country == ""
    assert e[1].model == "Twig XL 3" and e[1].date == "20/10/2026"


def test_titles_sceneries_tracks():
    assert V.parse_titles(read("leaderboard.html")) == ("Night Club", "The Racing Hour - TRH2212 - Micro")
    assert V.parse_sceneries(read("leaderboards.html")) == {38: "Night Club", 33: "Dynamic Weather"}
    assert V.parse_tracks(read("scenery.html"))[1] == (38, 1160, "The Racing Hour - TRH2212 - Micro")


def test_arab_best_per_pilot():
    a = V.arab_only(entries())
    assert set(a) == {"Bader", "Saud_FPV"}
    assert a["Bader"].time == 228.528  # best of his two quads


def test_round_flow(tmp_path):
    tz = ZoneInfo("Asia/Kuwait")
    t0 = datetime(2026, 10, 26, 20, tzinfo=tz)
    track = V.Track(38, 1160, "Night Club", "TRH")
    base = entries()
    rnd = start_round(track, base, t0, t0 + timedelta(days=1))
    assert rnd["baseline"] == {"Bader": 228.528, "Saud_FPV": 250.1}

    # nothing changed -> no results
    assert update_round(rnd, base) == []

    # Bader improves, a new Egyptian pilot appears, Saud stays the same
    later = base + [V.Entry("Bader", 220.5, "kw", "Twig", "26/10/2026"),
                    V.Entry("Omar", 240.0, "eg", "Twig", "26/10/2026")]
    ch = update_round(rnd, later)
    assert sorted(e.pilot for e, _ in ch) == ["Bader", "Omar"]
    assert update_round(rnd, later) == []  # same data twice -> no repeat posts

    later2 = later + [V.Entry("Omar", 219.0, "eg", "Twig", "27/10/2026")]
    ch = update_round(rnd, later2)
    assert ch[0][0].pilot == "Omar" and ch[0][1] == 240.0
    assert [r["pilot"] for r in ranking(rnd)] == ["Omar", "Bader"]

    store = Store(str(tmp_path / "s.json"))
    store.data["round"] = rnd
    final = finish_round(store, rnd, t0 + timedelta(days=1))
    assert [(r["pilot"], r["points"]) for r in final] == [("Omar", 10), ("Bader", 8)]
    store.save()
    again = Store(str(tmp_path / "s.json"))
    assert month_table(again, "2026-10") == [("Omar", 10), ("Bader", 8)]
    assert again.recent_track_keys(90, t0 + timedelta(days=2)) == {"38/1160"}
    assert again.data["round"] is None


def test_format():
    assert fmt_time(228.528) == "3:48.528"
    assert fmt_time(31.2) == "31.200"
    assert flag("kw") == "🇰🇼"


def test_pick_track_prefers_room(monkeypatch):
    c = V.Client(delay=0)
    pages = {
        V.BASE + "/leaderboards": read("leaderboards.html"),
        V.BASE + "/set_race_mode/6": "",
        V.BASE + "/leaderboard_by_version/38/All": read("scenery.html"),
        V.BASE + "/leaderboard_by_version/33/All": read("scenery.html").replace("/38/", "/33/"),
    }
    full = read("leaderboard.html")
    monkeypatch.setattr(c, "_get", lambda url: pages.get(url, full))
    track, e = c.pick_track(avoid={"38/400", "33/400"}, max_entries=180)
    assert track.track_id == 1160 and len(e) == 7
