#!/usr/bin/env python3
"""Shared weather snapshot for the US towns (wx_us.json), refreshed at most every 6 hours.

The app refreshes the state you are looking at live; this file keeps the rest of the US map
fresh without every phone downloading weather for ~1,800 towns. Open-Meteo counts each town
as one call, so requests are spaced out to stay inside the free limits."""
import json, sys, time, datetime, urllib.request

UA = "CanadianRoad/1.0 (+https://harpreetsinghjagpal-dot.github.io/BLACK-CE/)"
Q = ("&current=temperature_2m,dew_point_2m,weather_code,cloud_cover,wind_speed_10m,is_day"
     "&hourly=temperature_2m,precipitation,dew_point_2m,weather_code,cloud_cover,wind_speed_10m,is_day&past_hours=9&forecast_hours=31&timezone=auto")
FRZ = [56, 57, 66, 67]; RAIN = [51, 53, 55, 61, 63, 65, 80, 81, 82]; SNOW = [71, 73, 75, 77, 85, 86]; FOG = [45, 48]


def sc(w):  # same as the app's fcPeak scoring
    s, T = 0, w["air"]
    if -6 <= T <= 1: s += 25
    elif 1 < T <= 3: s += 12
    elif -14 <= T < -6: s += 15
    elif T < -14: s += 6
    if w["code"] in FRZ: s += 45
    elif w["code"] in RAIN and T <= 2: s += 30
    if w["pp"] >= 0.2 and T <= 2: s += 22
    if w["pm"] >= 1 and T <= 0: s += 20
    if w["code"] in FOG and T <= 1: s += 15
    if w["dew"] is not None and w["air"] - w["dew"] <= 2 and T <= 1: s += 12
    if T > 0 and w["fm"] is not None and w["fm"] <= 0 and (w["pp"] >= 0.2 or w["code"] in RAIN): s += 15
    if not w["day"] and w["cloud"] < 30 and w["wind"] < 10 and T <= 2: s += 8
    if w["code"] in SNOW: s += 8
    if T > 4 and w["code"] not in FRZ: s = min(s, 10)
    return max(0, min(100, s))


def fc_peak(h, now):
    t = h["time"]; n = len(t)
    i0 = next((i for i, x in enumerate(t) if x > now[:13] + ":00"), 0)
    best = None
    for i in range(i0, min(n, i0 + 24)):
        pm = max([h["temperature_2m"][j] for j in range(max(0, i - 9), i)] or [-99])
        pp = sum((h["precipitation"][j] or 0) for j in range(max(0, i - 6), i + 1))
        fl = [h["temperature_2m"][j] for j in range(i + 1, min(n - 1, i + 6) + 1)]
        w = {"air": h["temperature_2m"][i], "dew": h["dew_point_2m"][i], "code": h["weather_code"][i], "cloud": h["cloud_cover"][i],
             "wind": h["wind_speed_10m"][i], "day": bool(h["is_day"][i]), "pm": pm, "pp": round(pp, 1), "fm": min(fl) if fl else None}
        s = sc(w)
        if best is None or s > best[0]:
            best = (s, i, w)
    if not best:
        return None
    s, i, w = best
    return [t[i], w["air"], w["dew"], w["code"], w["cloud"], round(w["wind"]), 1 if w["day"] else 0, w["pm"], w["pp"], w["fm"], s]


def row(d):
    c, h = d["current"], d["hourly"]
    pm, pp, fm = -99, 0.0, 99
    lim = (datetime.datetime.fromisoformat(c["time"]) + datetime.timedelta(hours=6)).isoformat()[:16]
    for k, tm in enumerate(h["time"]):
        if tm <= c["time"]:
            pm = max(pm, h["temperature_2m"][k]); pp += h["precipitation"][k] or 0
        elif tm <= lim:
            fm = min(fm, h["temperature_2m"][k])
    return [c["temperature_2m"], c["dew_point_2m"], c["weather_code"], c["cloud_cover"], round(c["wind_speed_10m"]), c["is_day"],
            pm, round(pp, 1), None if fm == 99 else fm, fc_peak(h, c["time"])]


def main():
    force = "--force" in sys.argv
    try:
        old = json.load(open("wx_us.json"))
    except Exception:
        old = {"t": 0, "p": {}}
    if not force and time.time() * 1000 - old.get("t", 0) < 5.9 * 3600e3:
        print("wx_us: fresh, skip"); return
    us = json.load(open("us.json"))
    towns = [(c, t[0], t[1], t[2]) for c in us["order"] for t in us["p"][c]["towns"]]
    out = {c: [] for c in us["order"]}
    got = 0
    for i in range(0, len(towns), 100):
        b = towns[i:i + 100]
        u = "https://api.open-meteo.com/v1/forecast?latitude=" + ",".join(str(x[2]) for x in b) + "&longitude=" + ",".join(str(x[3]) for x in b) + Q
        for k in range(3):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as r:
                    j = json.loads(r.read())
                arr = j if isinstance(j, list) else [j]
                for (c, n, la, lo), d in zip(b, arr):
                    out[c].append([n] + row(d)); got += 1
                break
            except Exception as e:
                print("wx_us batch", i, "try", k, e, file=sys.stderr); time.sleep(40)
        time.sleep(12)
    if got < len(towns) * 0.5 and old.get("p"):
        print("wx_us: too few towns", got, "- keeping old file"); return
    json.dump({"t": int(time.time() * 1000), "p": out}, open("wx_us.json", "w"), separators=(",", ":"))
    print("wx_us:", got, "/", len(towns))


if __name__ == "__main__":
    main()
