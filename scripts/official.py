#!/usr/bin/env python3
"""Collect official road reports from provincial 511 sites into official.json.

Runs in GitHub Actions every 15 minutes. Standard library only.
Row format (same as the app's p.rc): [road, description, code, points, kind, updated]
  code: Alberta-style condition code ("Cvd Ice", "Ptly Cvd Snw", "Bare Wet", ...)
        or "Closed", "Incident", "Slippery", "Frost", "Drifting", "Poor Vis"
  points: [[lat, lon], ...] (may be empty: the app then matches by highway number)
  kind: "c" condition, "i" incident/closure
"""
import json, re, sys, time, datetime, urllib.request, urllib.parse, html

UA = "CanadianRoad/1.0 (+https://harpreetsinghjagpal-dot.github.io/BLACK-CE/)"
IBI = {  # province: (host, conditions list name, source label)
    "AB": ("https://511.alberta.ca", "WinterRoads", "Alberta 511"),
    "SK": ("https://hotline.gov.sk.ca", "WinterRoads", "SK Highway Hotline"),
    "MB": ("https://www.manitoba511.ca", "WinterRoads", "Manitoba 511"),
    "ON": ("https://511on.ca", "RoadConditions", "Ontario 511"),
    "NB": ("https://511.gnb.ca", "WinterRoads", "New Brunswick 511"),
    "NS": ("https://511.novascotia.ca", "WinterRoads", "511 Nova Scotia"),
    "NL": ("https://511nl.ca", "WinterRoads", "511 NL"),
    "YT": ("https://511yukon.ca", "WinterRoads", "511 Yukon"),
    "PE": ("https://511.gov.pe.ca", "WinterRoads", "PEI 511"),
}
QC_REGIONS = ["1000", "2000", "3000", "4000", "5000", "6000", "7000", "8000", "9000", "10000",
              "11000", "12000", "13000", "14000"]
NOW = datetime.datetime.now(datetime.timezone.utc)


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def ibi_list(host, name):
    q = json.dumps({"columns": [{"data": None, "name": ""}, {"name": "sortOrder", "s": True}],
                    "start": 0, "length": 5000})
    return get(f"{host}/List/GetData/{name}?query={urllib.parse.quote(q)}&lang=en").get("data", [])


def clean(s, n=240):
    s = html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def age_days(s):
    """511 dates look like '11/20/26, 1:55 PM' or (Ontario) '26-11-26 5:12 AM'."""
    s = str(s or "")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)
    if m:
        mo, d, y = map(int, m.groups())
    else:
        m = re.match(r"(\d{2})-(\d{1,2})-(\d{1,2})", s)
        if not m:
            return 0
        y, mo, d = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return (NOW.date() - datetime.date(y, mo, d)).days
    except ValueError:
        return 0


def code_for(text):
    t = text.lower()
    part = bool(re.search(r"ptly|partly|partial|patch|spots|track", t))
    if "closed" in t or "impassable" in t or "travel not recommended" in t:
        return "Closed"
    if re.search(r"\bice\b|icy|glace|black ice", t):
        return "Ptly Cvd Ice" if part else "Cvd Ice"
    if re.search(r"snow|snw|slush|neige|packed", t):
        return "Ptly Cvd Snw" if part else "Cvd Snw"
    if "slippery" in t or "slick" in t:
        return "Slippery"
    if "frost" in t:
        return "Frost"
    if "drift" in t:
        return "Drifting"
    if "wet" in t:
        return "Bare Wet"
    return None


def hw_road(name):
    return bool(re.search(r"\d", str(name or "")))


def ibi(prov):
    host, cond, _ = IBI[prov]
    rows = []
    for r in ibi_list(host, cond):
        if r.get("stale") or age_days(r.get("lastUpdated")) > 3 or not hw_road(r.get("roadway")):
            continue
        txt = " ".join([str(r.get("primaryCondition") or "")] + [str(x) for x in (r.get("secondaryConditions") or [])])
        c = code_for(txt)
        vis = str(r.get("visibility") or "").lower()
        if not c and vis.startswith("poor"):
            c = "Poor Vis"
        if not c and str(r.get("drifting") or "").lower() == "yes":
            c = "Drifting"
        if not c:
            continue
        rows.append([clean(r.get("roadway"), 60), clean(r.get("description"), 120), c, [], "c",
                     str(r.get("lastUpdated") or "")])
    for layer in ("Incidents", "Closures"):
        try:
            items = ibi_list(host, layer)
        except Exception as e:  # some sites lack a layer
            print(prov, layer, "skip:", e, file=sys.stderr)
            continue
        for r in items:
            road = r.get("roadwayName")
            if not hw_road(road):
                continue
            desc = clean(r.get("description"))
            full = r.get("isFullClosure") or layer == "Closures" or "all lanes closed" in desc.lower()
            c = "Closed" if full else (code_for(desc) or "Incident")
            rows.append([clean(road, 60), desc, c, [], "i", str(r.get("lastUpdated") or "")])
    return rows


def get_text(url, timeout=40, enc=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode(enc or r.headers.get_content_charset() or "utf-8", "replace")


def qc():
    """Quebec 511 RSS: road conditions + warnings, per region."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    host = "https://www.quebec511.info"
    rows, seen = [], set()
    for reg in QC_REGIONS:
        try:
            page = get_text(f"{host}/Diffusion/Rss/RoutesRss.aspx?regn={reg}&lang=En")
            ids = re.findall(r'id="chk(\d+)"', page)
            if not ids:
                continue
            xml = get_text(f"{host}/Diffusion/Rss/GenererRss.aspx?regn={reg}&routes={';'.join(ids)}&lang=En",
                           enc="iso-8859-1")
            root = ET.fromstring(xml.encode("iso-8859-1", "replace"))
        except Exception as e:
            print("QC", reg, "skip:", e, file=sys.stderr)
            continue
        for it in root.iter("item"):
            title = it.findtext("title") or ""
            desc = clean(it.findtext("description"))
            cat = (it.findtext("category") or "").lower()
            try:
                when = parsedate_to_datetime(it.findtext("pubDate"))
                age = (NOW - when).days
                upd = when.strftime("%Y-%m-%d %H:%M")
            except Exception:
                age, upd = 0, ""
            key = (title, desc)
            if key in seen:
                continue
            seen.add(key)
            if "condition" in cat:
                if age > 3:
                    continue
                parts = [p.strip() for p in desc.split("|")]
                c = code_for(" ".join(parts[1:2]))
                if not c and len(parts) > 2 and parts[2].lower().startswith("poor"):
                    c = "Poor Vis"
                if not c:
                    continue
                road = title.split(":")[0].strip()
                rows.append([road, parts[0], c, [], "c", upd])
            else:  # warnings: keep closures and weather, skip roadwork
                low = desc.lower()
                if "roadwork" in low or "travaux" in low:
                    continue
                m = re.search(r"\b([AR])-(\d+)", desc)
                if not m:
                    continue
                full = re.search(r"\bclosed\b", low) and "lane closed" not in low and "lanes closed out of" not in low
                c = "Closed" if full else code_for(desc)
                if not c:
                    continue
                rows.append([f"{m.group(1)}-{m.group(2)}", desc, c, [], "i", upd])
    return rows


def nt():
    """DriveNWT: road conditions and advisories from the map's data file."""
    host = "https://drivenwt.ca"
    path = json.loads(get_text(f"{host}/Home/GetJsonDataPath?installationIndex=0"))["filePath"].replace("/../", "/")
    j = json.loads(get_text(host + path))
    sub = {k: (v.get("en-us") if isinstance(v, dict) else str(v)) for k, v in j.get("EntitySubTypeNames", {}).items()}
    rows = []
    for i in j.get("Issues", []):
        tv, d = i.get("TableViewInfo") or {}, i.get("Description") or {}
        typ = sub.get(tv.get("IssueTypeId"), "") or ""
        loc = ((tv.get("LocationLocalizations") or {}).get("en-us") or tv.get("Location") or "").strip()
        text = clean(re.sub(r"^\[\d+\]\s*", "", d.get("BaseDescription") or ""))
        upd_ms = d.get("UpdateTimeUtcEpochMillis") or 0
        age = (NOW.timestamp() * 1000 - upd_ms) / 864e5 if upd_ms else 99
        upd = datetime.datetime.fromtimestamp(upd_ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M") if upd_ms else ""
        div = str(i.get("DivisionId"))
        if div == "8128":  # road conditions
            if "Winter Road" in typ or typ.startswith("Open ("):
                continue
            c = "Closed" if typ.startswith("Closed") else (code_for(text) or "Caution")
            rows.append([loc.split(":")[0][:60], text or loc, c, [], "c", upd])
        elif div == "8136":  # advisories
            if age > 14 or typ in ("Construction", "Width Reduction", "Equipment Working"):
                continue
            c = {"Closure": "Closed", "Fire and Smoke": "Poor Vis"}.get(typ) or code_for(text) or "Caution"
            rows.append([loc.split(" at ")[0][:60], f"{loc} — {text}" if text else loc, c, [], "i", upd])
        elif div == "8131" and "Closed" in typ:  # ferries / ice crossings
            rows.append([loc[:60], typ, "Closed", [], "i", upd])
    return rows


def bc():
    j = get("https://api.open511.gov.bc.ca/events?format=json&status=ACTIVE&limit=500")
    rows = []
    for e in j.get("events", []):
        et = e.get("event_type", "")
        desc = clean(e.get("description"))
        roads = e.get("roads") or [{}]
        road = roads[0].get("name", "")
        if et not in ("INCIDENT", "WEATHER_CONDITION", "ROAD_CONDITION") or "rest area" in desc.lower():
            continue
        if not hw_road(road):
            continue
        c = code_for(desc) or ("Closed" if "closed" in desc.lower() else "Incident")
        g = e.get("geography") or {}
        pts = []
        if g.get("type") == "Point":
            pts = [[round(g["coordinates"][1], 3), round(g["coordinates"][0], 3)]]
        elif g.get("type") == "LineString":
            cs = g["coordinates"]
            pts = [[round(p[1], 3), round(p[0], 3)] for p in cs[:: max(1, len(cs) // 12)]]
        kind = "c" if et in ("WEATHER_CONDITION", "ROAD_CONDITION") else "i"
        rows.append([clean(road, 60), desc, c, pts, kind, e.get("updated", "")[:16]])
    return rows


def main():
    out = {"t": int(time.time() * 1000), "p": {}, "src": {}, "err": {}}
    try:
        old = json.load(open("official.json"))
    except Exception:
        old = {"p": {}}
    for prov in IBI:
        try:
            out["p"][prov] = ibi(prov)
            out["src"][prov] = IBI[prov][2]
        except Exception as e:
            out["err"][prov] = str(e)[:200]
            if prov in old.get("p", {}):  # keep last good data for up to 6 h
                if out["t"] - old.get("t", 0) < 6 * 3600e3:
                    out["p"][prov] = old["p"][prov]
                    out["src"][prov] = IBI[prov][2]
    for prov, fn, label in (("BC", bc, "DriveBC"), ("QC", qc, "Québec 511"), ("NT", nt, "DriveNWT")):
        try:
            out["p"][prov] = fn()
            out["src"][prov] = label
        except Exception as e:
            out["err"][prov] = str(e)[:200]
            if prov in old.get("p", {}) and out["t"] - old.get("t", 0) < 6 * 3600e3:
                out["p"][prov] = old["p"][prov]
                out["src"][prov] = label
    for k, v in out["p"].items():
        print(k, len(v), "reports")
    for k, v in out["err"].items():
        print(k, "ERROR", v, file=sys.stderr)
    with open("official.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
