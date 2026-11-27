#!/usr/bin/env python3
"""Assemble us.json for the app from the collected pieces (runs locally)."""
import json, math, re, sys, os, glob, html
from collections import defaultdict

B = "/home/claude/usb/wt/build"
O = B + "/out"
T = json.load(open(B + "/us_towns.json"))
SH = json.load(open("/home/claude/usb/us_shapes.json"))
ROADS = json.load(open("/home/claude/usb/us_roads.json"))
ADM = json.load(open("/home/claude/usb/dl/adm1.geojson"))
POLY = {}
for f in ADM["features"]:
    if f["properties"].get("iso_a2") == "US":
        g = f["geometry"]
        POLY[f["properties"]["postal"]] = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]


def km(a, b, c, d):
    x = (d - b) * math.cos(math.radians((a + c) / 2))
    return math.hypot(x, c - a) * 111.2


def inside(la, lo, c):
    for poly in POLY.get(c, []):
        ring = poly[0]
        x, y, inn = lo, la, False
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inn = not inn
        if inn:
            return True
    return False


def state_of(la, lo, hint=None):
    if hint and inside(la, lo, hint):
        return hint
    for c in T:
        if inside(la, lo, c):
            return c
    return None


# ---------- weather rows (same maths as the app's liveWx/fcPeak) ----------
FRZ = [56, 57, 66, 67]; RAIN = [51, 53, 55, 61, 63, 65, 80, 81, 82]; SNOW = [71, 73, 75, 77, 85, 86]; FOG = [45, 48]


def sc(w):
    s, T_ = 0, w["air"]
    if -6 <= T_ <= 1: s += 25
    elif 1 < T_ <= 3: s += 12
    elif -14 <= T_ < -6: s += 15
    elif T_ < -14: s += 6
    if w["code"] in FRZ: s += 45
    elif w["code"] in RAIN and T_ <= 2: s += 30
    if w["pp"] >= 0.2 and T_ <= 2: s += 22
    if w["pm"] >= 1 and T_ <= 0: s += 20
    if w["code"] in FOG and T_ <= 1: s += 15
    if w["dew"] is not None and w["air"] - w["dew"] <= 2 and T_ <= 1: s += 12
    if T_ > 0 and w["fm"] is not None and w["fm"] <= 0 and (w["pp"] >= 0.2 or w["code"] in RAIN): s += 15
    if not w["day"] and w["cloud"] < 30 and w["wind"] < 10 and T_ <= 2: s += 8
    if w["code"] in SNOW: s += 8
    if T_ > 4 and w["code"] not in FRZ: s = min(s, 10)
    return max(0, min(100, s))


def fc_peak(h, now_iso):
    t = h["time"]; n = len(t)
    i0 = next((i for i, x in enumerate(t) if x > now_iso[:13] + ":00"), 0)
    best = None
    for i in range(i0, min(n, i0 + 24)):
        pm = max([h["temperature_2m"][j] for j in range(max(0, i - 9), i)] or [-99])
        pp = sum((h["precipitation"][j] or 0) for j in range(max(0, i - 6), i + 1))
        fm_l = [h["temperature_2m"][j] for j in range(i + 1, min(n - 1, i + 6) + 1)]
        fm = min(fm_l) if fm_l else None
        w = {"air": h["temperature_2m"][i], "dew": h["dew_point_2m"][i], "code": h["weather_code"][i], "cloud": h["cloud_cover"][i],
             "wind": h["wind_speed_10m"][i], "day": bool(h["is_day"][i]), "pm": pm, "pp": round(pp, 1), "fm": fm}
        s = sc(w)
        if best is None or s > best[0]:
            best = (s, i, w)
    if not best:
        return None
    s, i, w = best
    return [t[i], w["air"], w["dew"], w["code"], w["cloud"], round(w["wind"]), 1 if w["day"] else 0, w["pm"], w["pp"], w["fm"], s]


def wx_row(d):
    c, h = d["current"], d["hourly"]
    pm, pp, fm = -99, 0.0, 99
    import datetime
    lim = (datetime.datetime.fromisoformat(c["time"]) + datetime.timedelta(hours=6)).isoformat()[:16]
    for k, tm in enumerate(h["time"]):
        if tm <= c["time"]:
            pm = max(pm, h["temperature_2m"][k]); pp += h["precipitation"][k] or 0
        elif tm <= lim:
            fm = min(fm, h["temperature_2m"][k])
    return [c["temperature_2m"], c["dew_point_2m"], c["weather_code"], c["cloud_cover"], round(c["wind_speed_10m"]), c["is_day"],
            pm, round(pp, 1), None if fm == 99 else fm, fc_peak(h, c["time"])]


WX = json.load(open(O + "/wx.json")) if os.path.exists(O + "/wx.json") else {}
NEUTRAL = [5, 0, 3, 80, 10, 1, 6, 0, 2, None]  # mild placeholder until live weather arrives

# ---------- cameras ----------
IBIH = {"AK": "https://511.alaska.gov", "AZ": "https://az511.gov", "CT": "https://ctroads.org", "FL": "https://fl511.com", "GA": "https://511ga.org",
        "ID": "https://511.idaho.gov", "LA": "https://www.511la.org", "NE511": "https://newengland511.org", "NC": "https://drivenc.gov",
        "NV": "https://www.nvroads.com", "PA": "https://www.511pa.com", "UT": "https://udottraffic.utah.gov", "WI": "https://511wi.gov"}
cams = defaultdict(list)  # state -> [(id, name, la, lo, road)]
camurl = {}


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))
    return re.sub(r"\s+", " ", s).strip()[:70]


for k, host in IBIH.items():
    f = f"{O}/j5_ibi_{k}.json"
    if not os.path.exists(f):
        f = f"{O}/c_ibi_{k}.json"
    if not os.path.exists(f):
        continue
    own = ["ME", "NH", "VT"] if k == "NE511" else [k]
    for r in json.load(open(f)):
        iid, road, loc, la, lo = r[:5]
        c = state_of(la, lo, own[0])
        if c not in own or (len(r) > 6 and r[6] == "SurroundingState"):
            continue
        cams[c].append((iid, clean(loc or road), la, lo, road))
        camurl[c] = host + "/map/Cctv/{id}"
for k in ["CA", "OR", "WA", "MI", "NM", "MD", "IL"]:
    f = f"{O}/c_{k}.json"
    if not os.path.exists(f):
        continue
    d = json.load(open(f))
    rows = d[0] if k == "IL" else d
    for r in rows:
        url, road, name, la, lo = r[:5]
        if la is None or lo is None or not url:
            continue
        c = state_of(float(la), float(lo), k)
        if not c or c in ("ID", "AK", "AZ", "CT", "FL", "GA", "LA", "ME", "NH", "VT", "NC", "NV", "PA", "UT", "WI"):
            continue
        cams[c].append((url, clean(name), float(la), float(lo), road))
        camurl.setdefault(c, "{id}")
for k in ["IA", "IN", "KS", "MA", "NE", "MN", "CO", "NY"]:
    f = f"{O}/c_gqlt_{k}.json"
    if not os.path.exists(f):
        continue
    try:
        mf = json.load(open(f))["data"]["mapFeaturesQuery"]["mapFeatures"]
    except Exception:
        continue
    for m in mf:
        v = [x for x in (m.get("views") or []) if x.get("url")]
        g = (m.get("features") or [{}])[0].get("geometry") or {}
        if not v or g.get("type") != "Point":
            continue
        lo, la = g["coordinates"]
        c = state_of(la, lo, k)
        if c != k:
            continue
        cams[c].append((v[0]["url"], clean(m.get("tooltip")), la, lo, (m.get("tooltip") or "").split(":")[0]))
        camurl[c] = "{id}"
# Wyoming: camera pages listed by route, placed by "N miles east/west of Town"
WYT = T["WY"]["towns"]
for rt in ["I25Cameras", "I80Cameras", "I90Cameras", "NonInterstateCameras"]:
    f = f"{O}/j5_WY_{rt}.txt"
    if not os.path.exists(f):
        continue
    h = json.loads(open(f).read())
    for m in re.finditer(r'<a href="(/highway/webcameras/view\?site=[^"]+)">([^<]+)</a>\s*</td>\s*<td>\s*([^<]+?)\s*</td>', h, re.I):
        url, name, where = m.groups()
        mm = re.search(r"([\d.]+)\s*miles?\s*(north|south|east|west)\s*of\s*([A-Z][\w .']+?)(?:\s*\(|$)", where)
        town = None
        if mm and mm.group(3).strip() in WYT:
            town = mm.group(3).strip(); dist = float(mm.group(1)) * 1.609; dr = mm.group(2)
        else:
            for t in WYT:
                if t.lower() in (name + " " + where).lower():
                    town, dist, dr = t, 0, "east"
                    break
        if not town:
            continue
        la, lo = WYT[town]
        dl = dist / 111.2
        la += {"north": dl, "south": -dl}.get(dr, 0)
        lo += {"east": dl / math.cos(math.radians(la)), "west": -dl / math.cos(math.radians(la))}.get(dr, 0)
        cams["WY"].append(("https://www.wyoroad.info" + url, clean(name + " — " + where), round(la, 4), round(lo, 4), rt[:3]))
        camurl["WY"] = "{id}"

# keep cameras near our highways, spread out, at most 240 per state
RD = defaultdict(list)
for no, sec, flat in ROADS:
    for i in range(0, len(flat), 2):
        RD[(math.floor(flat[i] * 4), math.floor(flat[i + 1] * 4))].append((flat[i], flat[i + 1]))


def near_road(la, lo):
    gy, gx = math.floor(la * 4), math.floor(lo * 4)
    pts = [p for i in (-1, 0, 1) for j in (-1, 0, 1) for p in RD.get((gy + i, gx + j), [])]
    return min((km(la, lo, p[0], p[1]) for p in pts), default=99)


CAMS = {}
for c, lst in cams.items():
    tw = list(T[c]["towns"].values())
    keep, cell = [], set()
    scored = []
    for cam in lst:
        dt = min(km(cam[2], cam[3], t[0], t[1]) for t in tw)
        dr = near_road(cam[2], cam[3])
        if dt > 60 and dr > 6:
            continue
        scored.append((0 if dr < 3 else 1, dt, cam))
    scored.sort(key=lambda x: (x[0], x[1]))
    for _, _, cam in scored:
        k = (round(cam[2] / 0.07), round(cam[3] / 0.09))
        if k in cell:
            continue
        cell.add(k)
        keep.append([cam[0], cam[1] or "Camera", round(cam[2], 4), round(cam[3], 4)])
        if len(keep) >= 240:
            break
    CAMS[c] = keep

# ---------- assemble ----------
out = {"order": [], "p": {}, "over": {}, "roads": ROADS, "xl": []}
nowx = 0
for c, s in T.items():
    towns = []
    for t, (la, lo) in s["towns"].items():
        d = WX.get(c, {}).get(t)
        try:
            w = wx_row(d) if d and d.get("current") else None
        except Exception:
            w = None
        if not w:
            w = NEUTRAL; nowx += 1
        towns.append([t, la, lo] + w)
    hw = [[no, name, ts] for no, name, ts in s["hw"]]
    shp = SH.get(c, {})
    out["order"].append(c)
    out["p"][c] = {"pa": s["pa"], "en": s["en"], "link": s["link"], "camurl": camurl.get(c, "{id}"), "towns": towns, "hw": hw,
                   "cams": CAMS.get(c, []), "shape": [[[x, y] for x, y in r] for r in shp.get("shape", [])], "us": 1}
    out["over"][c] = [[[x, y] for x, y in r] for r in shp.get("over", [])]

# ---------- links between states/provinces ----------
MAN = [  # Canada <-> USA border crossings, and US gaps the highway lists do not close
    ["BC", "Vancouver", "WA", "Blaine", 45], ["BC", "Abbotsford", "WA", "Bellingham", 40], ["BC", "Osoyoos", "WA", "Oroville", 8],
    ["BC", "Creston", "ID", "Bonners Ferry", 55], ["BC", "Cranbrook", "ID", "Eastport", 75], ["BC", "Cranbrook", "MT", "Eureka", 105],
    ["AB", "Coutts", "MT", "Sweet Grass", 2], ["SK", "Estevan", "ND", "Portal", 25], ["MB", "Emerson", "ND", "Pembina", 4],
    ["ON", "Fort Frances", "MN", "International Falls", 2], ["ON", "Thunder Bay", "MN", "Grand Portage", 60],
    ["ON", "Sault Ste. Marie", "MI", "Sault Ste. Marie", 4], ["ON", "Sarnia", "MI", "Port Huron", 4], ["ON", "Windsor", "MI", "Detroit", 4],
    ["ON", "Niagara Falls", "NY", "Buffalo", 30], ["ON", "Kingston", "NY", "Alexandria Bay", 55], ["QC", "Montreal", "NY", "Champlain", 70],
    ["QC", "Montreal", "VT", "Swanton", 90], ["QC", "Sherbrooke", "VT", "Derby Line", 55], ["QC", "Saint-Georges", "ME", "Jackman", 60],
    ["NB", "Woodstock", "ME", "Houlton", 20], ["NB", "St. Stephen", "ME", "Calais", 2], ["NB", "Edmundston", "ME", "Fort Kent", 30],
    ["NB", "Grand Falls", "ME", "Van Buren", 20], ["YT", "Beaver Creek", "AK", "Tok", 185],
    ["ID", "Kooskia", "MT", "Lolo", 190], ["ID", "Island Park", "MT", "West Yellowstone", 40], ["CO", "Julesburg", "NE", "Ogallala", 55],
    ["MT", "Troy", "ID", "Moyie Springs", 40], ["OK", "Lawton", "TX", "Wichita Falls", 80], ["TX", "Stratford", "OK", "Boise City", 55],
    ["IL", "Joliet", "IN", "Hammond", 55], ["OH", "Saint Clairsville", "PA", "Washington", 75], ["MD", "Hancock", "PA", "Breezewood", 40],
    ["WV", "Bruceton Mills", "MD", "Grantsville", 30], ["IN", "Batesville", "OH", "Cincinnati", 60], ["LA", "Slidell", "MS", "Picayune", 25],
    ["MS", "Southaven", "TN", "Memphis", 15], ["AL", "Fort Payne", "TN", "Chattanooga", 75], ["NJ", "Fort Lee", "NY", "New York", 15],
    ["CT", "Greenwich", "NY", "New York", 45], ["NH", "Littleton", "VT", "Saint Johnsbury", 35], ["ME", "Bethel", "NH", "Gorham", 35],
    ["WA", "Kennewick", "OR", "Hermiston", 50], ["WA", "Pullman", "ID", "Moscow", 15], ["KS", "Liberal", "OK", "Guymon", 65],
    ["UT", "Green River", "CO", "Fruita", 160], ["MD", "Washington", "VA", "Arlington", 6], ["PA", "Philadelphia", "NJ", "Cherry Hill", 15],
    ["PA", "Easton", "NJ", "Phillipsburg", 3], ["MO", "Saint Louis", "IL", "East Saint Louis", 5], ["KY", "Louisville", "IN", "Jeffersonville", 5],
]
CAN = json.load(open("/home/claude/usb/can_towns.json"))
ok = []
for a, an, b, bn, d in MAN:
    ga = (T.get(a) or {}).get("towns", {}).get(an) or CAN.get(a, {}).get(an)
    gb = (T.get(b) or {}).get("towns", {}).get(bn) or CAN.get(b, {}).get(bn)
    if not ga or not gb:
        print("MANUAL LINK MISSING", a, an, b, bn); continue
    straight = km(ga[0], ga[1], gb[0], gb[1])
    ok.append([a, an, b, bn, max(d, round(straight * 1.2))])
# automatic: highway ends in neighbouring states with the same number
ends = []
for c, s in T.items():
    for no, name, ts in s["hw"]:
        for t in (ts[0], ts[-1]):
            ends.append((c, no, t, s["towns"][t]))
have = {(x[0], x[1], x[2], x[3]) for x in ok} | {(x[2], x[3], x[0], x[1]) for x in ok}
auto = []
for c, no, t, p in ends:
    best = None
    for c2, no2, t2, p2 in ends:
        if c2 == c or no2 != no:
            continue
        d = km(p[0], p[1], p2[0], p2[1])
        if d <= 160 and (best is None or d < best[0]):
            best = (d, c2, t2)
    if best:
        d, c2, t2 = best
        key = tuple(sorted([(c, t), (c2, t2)]))
        if key in {tuple(sorted([(x[0], x[1]), (x[2], x[3])])) for x in auto} or (c, t, c2, t2) in have:
            continue
        auto.append([c, t, c2, t2, max(1, round(d * 1.15))])
out["xl"] = ok + auto
json.dump(out, open("/home/claude/usb/us.json", "w"), ensure_ascii=False, separators=(",", ":"))
print("states", len(out["order"]), "towns", sum(len(p["towns"]) for p in out["p"].values()), "no-weather", nowx,
      "cams", sum(len(p["cams"]) for p in out["p"].values()), "links", len(ok), "+", len(auto),
      "size", os.path.getsize("/home/claude/usb/us.json"))
print("cams per state:", {c: len(v) for c, v in sorted(CAMS.items())})
print("no cams:", [c for c in T if not CAMS.get(c)])
