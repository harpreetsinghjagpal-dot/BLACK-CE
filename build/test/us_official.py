#!/usr/bin/env python3
"""Official US road reports for official.json (called from official.py).

Sources (all public, no key):
  * US National Weather Service active alerts (all states): ice, snow, blizzard, fog
  * State 511 sites on the same platform as the Canadian ones (AK AZ CT FL GA ID LA ME NH VT NC NV PA UT WI)
  * Castle Rock 511 sites (IA IN KS MA NE): incidents and road reports
  * Caltrans chain controls (CA)
Rows use the app format: [road, description, code, points, kind, updated]. US road names are
normalised to the app's highway ids: "I-90", "US-2", "MT-200".
"""
import json, re, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

import official as O

US_IBI = {  # state: (host, conditions list or None, label)
    "AK": ("https://511.alaska.gov", "WinterRoads", "Alaska 511"),
    "AZ": ("https://az511.gov", None, "AZ 511"),
    "CT": ("https://ctroads.org", None, "CTroads"),
    "FL": ("https://fl511.com", None, "FL511"),
    "GA": ("https://511ga.org", None, "511 Georgia"),
    "ID": ("https://511.idaho.gov", "WinterRoads", "Idaho 511"),
    "LA": ("https://www.511la.org", None, "511 Louisiana"),
    "NE511": ("https://newengland511.org", "WinterRoads", "New England 511"),
    "NC": ("https://drivenc.gov", None, "DriveNC"),
    "NV": ("https://www.nvroads.com", "RoadConditions", "NVroads"),
    "PA": ("https://www.511pa.com", None, "511PA"),
    "UT": ("https://udottraffic.utah.gov", "RoadConditions", "UDOT Traffic"),
    "WI": ("https://511wi.gov", "WinterRoads", "511 Wisconsin"),
}
CRC = {"IA": "https://511ia.org", "IN": "https://511in.org", "KS": "https://www.kandrive.gov", "MA": "https://mass511.com", "NE": "https://511.nebraska.gov"}
STATES = set("AK AL AR AZ CA CO CT DE FL GA IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY".split())
AK_NAMES = {"sterling": "AK-1", "glenn": "AK-1", "tok cutoff": "AK-1", "seward": "AK-9", "parks": "AK-3", "richardson": "AK-4",
            "alaska highway": "AK-2", "alaska hwy": "AK-2", "elliott": "AK-2", "dalton": "AK-11"}


def road_id(name, st):
    """Normalise a US road name to the app's highway id, or None."""
    n = str(name or "")
    m = re.search(r"\b(?:I|IH|Interstate)[\s-]*(\d{1,3})\b", n, re.I)
    if m:
        return "I-" + m.group(1)
    m = re.search(r"\b(?:US|U\.S\.|USH|US Hwy|US Highway)[\s-]*(\d{1,3}[A-Z]?)\b", n, re.I)
    if m:
        return "US-" + m.group(1).upper()
    m = re.search(r"\b([A-Z]{2})[\s-]+(\d{1,4}[A-Z]?)\b", n)
    if m and m.group(1) in STATES:
        return m.group(1) + "-" + m.group(2)
    m = re.search(r"\b(?:SR|SH|STH|K|M|State Route|State Highway|State Hwy|Route|Highway|Hwy)[\s-]*(\d{1,4}[A-Z]?)\b", n, re.I)
    if m:
        return st + "-" + m.group(1).upper()
    if st == "AK":
        low = n.lower()
        for k, v in AK_NAMES.items():
            if k in low:
                return v
    return None


def cond_text(r):
    parts = []
    for k in ("primaryCondition", "roadCondition", "overallStatus", "secondaryConditions", "surfaceConditions",
              "weatherConditions", "specialConditions", "warnings", "weatherCondition", "restriction"):
        v = r.get(k)
        if isinstance(v, list):
            parts += [str(x) for x in v]
        elif v:
            parts.append(str(v))
    return " ".join(p for p in parts if not p.startswith("#"))


NE511_AREA = {"maine": "ME", "vermont": "VT", "vt": "VT", "new hampshire": "NH", "nh": "NH", "me": "ME"}


def us_ibi(key):
    host, cond, _ = US_IBI[key]
    rows = {}

    def put(st, row):
        rows.setdefault(st, []).append(row)

    def st_for(r):
        if key != "NE511":
            return key
        a = str(r.get("area") or r.get("areaId") or "").lower()
        for k, v in NE511_AREA.items():
            if a.startswith(k):
                return v
        return None

    if cond:
        for r in O.ibi_list(host, cond):
            if r.get("stale") or O.age_days(r.get("lastUpdated")) > 3:
                continue
            st = st_for(r)
            rid = st and road_id(r.get("roadway"), st)
            if not rid:
                continue
            txt = cond_text(r)
            c = O.code_for(txt)
            if not c and re.search(r"chain", txt, re.I):
                c = "Chains"
            if not c and re.search(r"poor vis|blowing|fog", txt, re.I):
                c = "Poor Vis"
            if not c:
                continue
            put(st, [rid, O.clean(f"{r.get('roadway') or ''} — {r.get('description') or ''}: {txt}", 200), c, [], "c", str(r.get("lastUpdated") or "")])
    for layer in ("Incidents", "Closures"):
        try:
            items = O.ibi_list(host, layer, cap=1500)
        except Exception as e:
            print(key, layer, "skip:", e, file=sys.stderr)
            continue
        for r in items:
            if r.get("source") == "SurroundingState":
                continue
            st = st_for(r) or ("VT" if key == "NE511" else key)
            if key == "NE511":
                src = str(r.get("source") or "").lower()
                st = "ME" if src.startswith("maine") else "VT" if src.startswith(("vermont", "vt")) else "NH" if src.startswith(("nh", "newhampshire", "new hampshire")) else None
                if not st:
                    d0 = str(r.get("description") or "")
                    st = next((v for k, v in (("Maine", "ME"), ("Vermont", "VT"), ("New Hampshire", "NH")) if k in d0), None)
                if not st:
                    continue
            rid = road_id(r.get("roadwayName"), st)
            if not rid:
                continue
            desc = O.clean(r.get("description"))
            if re.search(r"roadwork|construction|lane closure|shoulder", desc, re.I) and not re.search(r"all lanes|road closed|closed in both", desc, re.I):
                continue
            full = r.get("isFullClosure") or "all lanes closed" in desc.lower() or "road closed" in desc.lower()
            c = "Closed" if full else (O.code_for(desc) or "Incident")
            put(st, [rid, desc, c, [], "i", str(r.get("lastUpdated") or "")])
    return rows


CRC_Q = ("query MapFeatures($input: MapFeaturesArgs!){mapFeaturesQuery(input:$input){mapFeatures{tooltip uri features{geometry}}"
         " error{message}}}")


def crc(st):
    host = CRC[st]
    rows = []
    for slug in ("incidents", "roadReports"):
        v = {"input": {"north": 49.5, "south": 24, "east": -66, "west": -125, "zoom": 12, "layerSlugs": [slug], "nonClusterableUris": ["dashboard"]}}
        req = urllib.request.Request(host + "/api/graphql", data=json.dumps({"query": CRC_Q, "variables": v}).encode(),
                                     headers={"User-Agent": O.UA, "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
        for m in ((j.get("data") or {}).get("mapFeaturesQuery") or {}).get("mapFeatures") or []:
            tip = O.clean(m.get("tooltip"), 220)
            rid = road_id(tip.split(":")[0], st)
            if not rid:
                continue
            g = ((m.get("features") or [{}])[0] or {}).get("geometry") or {}
            pts = [[round(g["coordinates"][1], 3), round(g["coordinates"][0], 3)]] if g.get("type") == "Point" else []
            low = tip.lower()
            c = "Closed" if "road closed" in low or "closed in both" in low else (O.code_for(tip) or "Incident")
            if c == "Incident" and re.search(r"rest area|construction|roadwork|shoulder", low):
                continue
            rows.append([rid, tip, c, pts, "i", ""])
    return rows


def ca_chain():
    rows = []
    for d in (1, 2, 3, 6, 7, 8, 9, 10):
        try:
            j = O.get(f"https://cwwp2.dot.ca.gov/data/d{d}/cc/ccStatusD{d:02d}.json", timeout=60)
        except Exception:
            continue
        for it in j.get("data", []):
            cc = it.get("cc", {})
            st = (cc.get("statusData") or {})
            status = str(st.get("status") or "")
            if not re.match(r"R-?[123]", status):
                continue
            loc = cc.get("location", {})
            rid = road_id(loc.get("route"), "CA")
            if not rid:
                continue
            desc = O.clean(f"{loc.get('locationName','')} ({loc.get('nearbyPlace','')}): chain control {status} — {st.get('statusDescription','')}", 200)
            pts = []
            try:
                pts = [[round(float(loc["latitude"]), 3), round(float(loc["longitude"]), 3)]]
            except Exception:
                pass
            rows.append([rid, desc, "Chains", pts, "c", f"{(cc.get('recordTimestamp') or {}).get('recordDate','')} {(cc.get('recordTimestamp') or {}).get('recordTime','')[:5]}"])
    return rows


NWS_EV = {"Ice Storm Warning": "Wx Ice", "Freezing Rain Advisory": "Wx Ice", "Freezing Drizzle Advisory": "Wx Ice", "Freezing Fog Advisory": "Wx Ice",
          "Winter Storm Warning": "Wx Snw", "Winter Weather Advisory": "Wx Snw", "Lake Effect Snow Warning": "Wx Snw", "Snow Squall Warning": "Wx Snw",
          "Heavy Snow Warning": "Wx Snw", "Blizzard Warning": "Wx Wind", "Dense Fog Advisory": "Poor Vis"}


def nws(towns, zones):
    """towns: {st: {town: (lat, lon, [highways])}}; zones: {st: {town: [forecastZone, county]}}"""
    url = ("https://api.weather.gov/alerts/active?status=actual&event=" + urllib.parse.quote(",".join(NWS_EV)))
    req = urllib.request.Request(url, headers={"User-Agent": O.UA, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read().decode("utf-8", "replace"))
    by_zone = {}
    for st, tz in zones.items():
        for t, (fz, cz) in tz.items():
            for z in (fz, cz):
                if z:
                    by_zone.setdefault(z, []).append((st, t))
    rows = {}
    for f in j.get("features", []):
        p = f.get("properties") or {}
        code = NWS_EV.get(p.get("event"))
        if not code:
            continue
        hit = set()
        for z in (p.get("geocode") or {}).get("UGC") or []:
            hit.update(by_zone.get(z, []))
        per = {}
        for st, t in hit:
            info = towns.get(st, {}).get(t)
            if not info:
                continue
            for h in info[2]:
                per.setdefault((st, h), []).append([info[0], info[1]])
        when = str(p.get("sent") or "")[:16].replace("T", " ")
        area = O.clean(p.get("areaDesc"), 110)
        for (st, h), pts in per.items():
            rows.setdefault(st, []).append([h, f"{p.get('event')} — {area}", code, pts[:12], "c", when])
    return rows


def collect(out, old):
    """Add US rows into out['p'] (state -> rows). Errors are recorded per source."""
    try:
        us = json.load(open("us.json"))
        towns = {st: {t[0]: (t[1], t[2], [h[0] for h in p["hw"] if t[0] in h[2]]) for t in p["towns"]} for st, p in us["p"].items()}
        zones = json.load(open("us_zones.json"))
    except Exception as e:
        out["err"]["US"] = "data: " + str(e)[:150]
        return
    res = {}
    jobs = {}
    with ThreadPoolExecutor(8) as ex:
        jobs["NWS"] = ex.submit(nws, towns, zones)
        for k in US_IBI:
            jobs["IBI_" + k] = ex.submit(us_ibi, k)
        for k in CRC:
            jobs["CRC_" + k] = ex.submit(crc, k)
        jobs["CA_chain"] = ex.submit(ca_chain)
        for name, fut in jobs.items():
            try:
                r = fut.result()
                if isinstance(r, list):
                    r = {name.split("_")[1] if name.startswith("CRC_") else "CA": r}
                for st, rows in r.items():
                    res.setdefault(st, []).extend(rows)
            except Exception as e:
                out["err"][name] = str(e)[:200]
    for st, rows in res.items():
        if st not in towns:
            continue
        seen, keep = set(), []
        for r in rows:
            k = (r[0], r[1], r[2])
            if k not in seen:
                seen.add(k)
                keep.append(r)
        out["p"][st] = keep[:400]
        out["src"][st] = "US 511 / National Weather Service"
