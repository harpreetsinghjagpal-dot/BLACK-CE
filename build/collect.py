#!/usr/bin/env python3
"""Collect US data for the app (runs in GitHub Actions on the us-build branch).
Outputs in build/out/: cams_*.json, zones.json, wx.json, sites.json"""
import json, urllib.request, urllib.parse, concurrent.futures as cf, os, re, math, time, sys

UA = "CanadianRoad/1.0 (+https://harpreetsinghjagpal-dot.github.io/BLACK-CE/)"
OUT = "build/out"


def fetch(url, data=None, ctype=None, timeout=60, accept="application/json, */*"):
    h = {"User-Agent": UA, "Accept": accept}
    if ctype:
        h["Content-Type"] = ctype
    for k in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 401, 403, 405):
                raise
            time.sleep(2 + k * 3)
        except Exception:
            time.sleep(2 + k * 3)
    raise RuntimeError("fetch failed " + url)


def save(name, obj):
    json.dump(obj, open(f"{OUT}/{name}", "w"), ensure_ascii=False, separators=(",", ":"))


IBI = {"AK": "https://511.alaska.gov", "AZ": "https://az511.gov", "CT": "https://ctroads.org", "FL": "https://fl511.com",
       "GA": "https://511ga.org", "ID": "https://511.idaho.gov", "LA": "https://www.511la.org",
       "NE511": "https://newengland511.org", "NC": "https://drivenc.gov", "NV": "https://www.nvroads.com",
       "PA": "https://www.511pa.com", "UT": "https://udottraffic.utah.gov", "WI": "https://511wi.gov"}


def ibi_cams(key, host):
    q = json.dumps({"columns": [{"data": None, "name": ""}, {"name": "sortOrder", "s": True}], "start": 0, "length": 10000})
    j = json.loads(fetch(f"{host}/List/GetData/Cameras?query={urllib.parse.quote(q)}&lang=en", timeout=120))
    out = []
    for r in j.get("data", []):
        m = re.search(r"POINT \(([-\d.]+) ([-\d.]+)\)", json.dumps(r.get("latLng") or {}))
        imgs = [i for i in (r.get("images") or []) if not i.get("disabled") and not i.get("blocked")]
        if not m or not imgs:
            continue
        out.append([imgs[0]["id"], r.get("roadway") or "", r.get("location") or "", float(m.group(2)), float(m.group(1)), r.get("areaId") or ""])
    return out


def ca_cams():
    out = []
    for d in range(1, 13):
        try:
            j = json.loads(fetch(f"https://cwwp2.dot.ca.gov/data/d{d}/cctv/cctvStatusD{d:02d}.json", timeout=90))
        except Exception as e:
            print("CA d", d, e, file=sys.stderr)
            continue
        for it in j.get("data", []):
            c = it.get("cctv", {})
            if str(c.get("inService", "true")).lower() != "true":
                continue
            loc = c.get("location", {})
            img = ((c.get("imageData") or {}).get("static") or {}).get("currentImageURL")
            if img:
                out.append([img, loc.get("route", ""), loc.get("locationName", ""), float(loc["latitude"]), float(loc["longitude"])])
    return out


def ca_chain():
    out = []
    for d in range(1, 13):
        try:
            j = json.loads(fetch(f"https://cwwp2.dot.ca.gov/data/d{d}/cc/ccStatusD{d:02d}.json", timeout=90))
        except Exception:
            continue
        out += j.get("data", [])[:3]
    return out


def or_cams():
    j = json.loads(fetch("https://tripcheck.com/Scripts/map/data/cctvinventory.js"))
    out = []
    for f in j.get("features", []):
        a = f.get("attributes", {})
        if a.get("filename"):
            out.append(["https://tripcheck.com/RoadCams/cams/" + a["filename"], a.get("route") or "", a.get("title") or "", a.get("latitude"), a.get("longitude")])
    return out


def wa_cams():
    j = json.loads(fetch("https://data.wsdot.wa.gov/travelcenter/Cameras.json", timeout=90))
    out = []
    for f in j.get("features", []):
        a, g = f.get("attributes", {}), f.get("geometry", {})
        x, y = g.get("x"), g.get("y")
        if x is None or not a.get("ImageURL"):
            continue
        lon = x / 6378137 * 180 / math.pi
        lat = (2 * math.atan(math.exp(y / 6378137)) - math.pi / 2) * 180 / math.pi
        out.append([a["ImageURL"], "", a.get("CameraTitle") or "", round(lat, 5), round(lon, 5)])
    return out


def mi_cams():
    j = json.loads(fetch("https://mdotjboss.state.mi.us/MiDrive/camera/list", timeout=90))
    out = []
    for r in j:
        m = re.search(r'src=\\?"([^"\\]+)', r.get("image", "")) or re.search(r'src="([^"]+)"', r.get("image", ""))
        ll = re.search(r"lat=([-\d.]+)&lon=([-\d.]+)", r.get("county", ""))
        if m and ll:
            out.append([m.group(1), r.get("route", ""), (r.get("route", "") + " " + r.get("location", "")).strip(), float(ll.group(1)), float(ll.group(2))])
    return out


def nm_cams():
    j = json.loads(fetch("https://servicev5.nmroads.com/RealMapWAR/GetCameraInfo"))
    return [[c["snapshotFile"].replace("http://", "https://"), "", c.get("title", ""), c["lat"], c["lon"]] for c in j.get("cameraInfo", []) if c.get("enabled") and c.get("snapshotFile")]


def arcgis(url):
    out, off = [], 0
    while True:
        j = json.loads(fetch(f"{url}/query?where=1%3D1&outFields=*&outSR=4326&f=json&resultOffset={off}&resultRecordCount=1000", timeout=90))
        fs = j.get("features", [])
        out += fs
        if len(fs) < 1000 or not j.get("exceededTransferLimit", True):
            break
        off += 1000
    return out


def il_cams():
    out = []
    for f in arcgis("https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/TrafficCamerasTM_Public/FeatureServer/0"):
        a, g = f["attributes"], f.get("geometry") or {}
        if a.get("ImgPath") and "x" in g:
            out.append([a["ImgPath"], a.get("RoadName") or "", a.get("CameraLocation") or "", g["y"], g["x"]])
    return out, (f["attributes"] if f else None)


def ky_cams():
    fs = arcgis("https://services2.arcgis.com/CcI36Pduqd0OR4W9/arcgis/rest/services/trafficCamerasCur_Prd/FeatureServer/0")
    return fs[:2], len(fs), [[f["attributes"], f.get("geometry")] for f in fs]


def md_cams():
    j = json.loads(fetch("https://chartexp1.sha.maryland.gov/CHARTExportClientService/getCameraMapDataJSON.do", timeout=90))
    return [[c.get("publicVideoURL"), f"{c.get('routePrefix','')}-{c.get('routeNumber','')}", c.get("name", ""), c.get("lat"), c.get("lon")] for c in j.get("data", []) if c.get("opStatus") == "OK"]


GQL_HOSTS = {"IA": "https://511ia.org", "IN": "https://511in.org", "KS": "https://www.kandrive.gov", "MA": "https://mass511.com", "NE": "https://511.nebraska.gov"}


def gql_schema(host):
    q = {"query": "{__schema{queryType{fields{name args{name type{name kind ofType{name kind}}}}}}}"}
    try:
        return json.loads(fetch(f"{host}/api/graphql", data=json.dumps(q).encode(), ctype="application/json"))
    except Exception as e:
        return {"err": str(e)}


def gql_try(host):
    """Castle Rock map feature query used by their public map."""
    q = ("query MapFeatures($input: MapFeaturesArgs!){mapFeaturesQuery(input:$input){mapFeatures{bbox tooltip uri "
         "features{id geometry properties} __typename ... on Camera{views(limit:5){uri category ... on CameraView{url}}}} error{message type}}}")
    v = {"input": {"north": 49.5, "south": 24, "east": -66, "west": -125, "zoom": 12, "layerSlugs": ["normalCameras"], "nonClusterableUris": ["dashboard"]}}
    try:
        return json.loads(fetch(f"{host}/api/graphql", data=json.dumps({"query": q, "variables": v}).encode(), ctype="application/json", timeout=120))
    except Exception as e:
        return {"err": str(e)}


SITES = {"CO": "https://maps.cotrip.org", "MN": "https://511mn.org", "NY": "https://511ny.org", "WY": "https://map.wyoroad.info",
         "MT": "https://www.511mt.net", "SD": "https://sd511.org", "SC": "https://www.511sc.org", "TX": "https://drivetexas.org",
         "OH": "https://www.ohgo.com", "TN": "https://smartway.tn.gov", "VA": "https://511.vdot.virginia.gov", "WV": "https://wv511.org",
         "OK": "https://oktraffic.org", "ND": "https://travel.dot.nd.gov", "AR": "https://www.idrivearkansas.com",
         "AL": "https://algotraffic.com", "MS": "https://www.mdottraffic.com", "KY": "https://goky.ky.gov", "DE": "https://deldot.gov/map/",
         "NJ": "https://511nj.org", "RI": "https://www.dot.ri.gov/travel/", "WA": "https://wsdot.com/travel/real-time/map/",
         "OR": "https://tripcheck.com", "MO": "https://traveler.modot.org/map/"}


def site_scan(url):
    """Homepage + first scripts: collect API-looking strings."""
    res = {"url": url}
    try:
        h = fetch(url, accept="text/html,*/*")
    except Exception as e:
        return {"url": url, "err": str(e)}
    res["title"] = (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1][:80]
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', h)
    res["scripts"] = srcs[:15]
    found = set(re.findall(r'["\'](/?(?:api|data|services|feeds?|json|map)[\w/\-.]*(?:json|camera|cctv|cam|event|condition|incident)[\w/\-.?=&]*)["\']', h, re.I))
    for s in srcs[:6]:
        u = urllib.parse.urljoin(url, s)
        try:
            js = fetch(u, accept="*/*", timeout=40)
        except Exception:
            continue
        found |= set(re.findall(r'["\'`](https?://[\w.\-]+/[\w/\-.]*(?:camera|cctv|cam|event|condition|incident|graphql|api)[\w/\-.?=&{}]*)["\'`]', js, re.I))
        found |= set(re.findall(r'["\'`](/(?:api|data|services|feeds?)/[\w/\-.?=&{}]*)["\'`]', js, re.I))
    res["found"] = sorted(found)[:80]
    return res


def nws_zone(c, t, la, lo):
    try:
        j = json.loads(fetch(f"https://api.weather.gov/points/{la:.4f},{lo:.4f}", accept="application/geo+json", timeout=30))
        p = j["properties"]
        return c, t, p.get("forecastZone", "").rsplit("/", 1)[-1], p.get("county", "").rsplit("/", 1)[-1]
    except Exception as e:
        return c, t, "", ""


WXQ = ("&current=temperature_2m,dew_point_2m,weather_code,cloud_cover,wind_speed_10m,is_day"
       "&hourly=temperature_2m,precipitation,dew_point_2m,weather_code,cloud_cover,wind_speed_10m,is_day&past_hours=9&forecast_hours=31&timezone=auto")


def wx(batch):
    u = "https://api.open-meteo.com/v1/forecast?latitude=" + ",".join(str(b[2]) for b in batch) + "&longitude=" + ",".join(str(b[3]) for b in batch) + WXQ
    j = json.loads(fetch(u, timeout=120))
    return j if isinstance(j, list) else [j]


def main():
    os.makedirs(OUT, exist_ok=True)
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    T = json.load(open("build/us_towns.json"))
    towns = [(c, t, ll[0], ll[1]) for c, s in T.items() for t, ll in s["towns"].items()]
    if step in ("all", "cams"):
        res, info = {}, {}
        jobs = {}
        with cf.ThreadPoolExecutor(10) as ex:
            for k, h in IBI.items():
                jobs["ibi_" + k] = ex.submit(ibi_cams, k, h)
            for k, fn in (("CA", ca_cams), ("OR", or_cams), ("WA", wa_cams), ("MI", mi_cams), ("NM", nm_cams), ("MD", md_cams)):
                jobs[k] = ex.submit(fn)
            jobs["IL"] = ex.submit(il_cams)
            jobs["KY"] = ex.submit(ky_cams)
            jobs["CAchain"] = ex.submit(ca_chain)
            for k, h in GQL_HOSTS.items():
                jobs["gqls_" + k] = ex.submit(gql_schema, h)
                jobs["gqlt_" + k] = ex.submit(gql_try, h)
            for k, u in SITES.items():
                jobs["site_" + k] = ex.submit(site_scan, u)
            for k, f in jobs.items():
                try:
                    res[k] = f.result()
                    info[k] = len(res[k]) if isinstance(res[k], list) else "ok"
                except Exception as e:
                    info[k] = "ERR " + str(e)[:150]
        for k, v in res.items():
            save(f"c_{k}.json", v)
        save("cams_info.json", info)
        print(json.dumps(info, indent=0))
    if step in ("all", "zones"):
        z = {}
        with cf.ThreadPoolExecutor(6) as ex:
            for c, t, fz, cz in ex.map(lambda a: nws_zone(*a), towns):
                z.setdefault(c, {})[t] = [fz, cz]
        save("zones.json", z)
        print("zones", sum(1 for c in z.values() for v in c.values() if v[0]), "/", len(towns))
    if step in ("all", "wx"):
        out = {}
        for i in range(0, len(towns), 100):
            b = towns[i:i + 100]
            try:
                arr = wx(b)
            except Exception as e:
                print("wx batch", i, e, file=sys.stderr)
                continue
            for (c, t, la, lo), d in zip(b, arr):
                out.setdefault(c, {})[t] = {"current": d.get("current"), "hourly": d.get("hourly")}
            time.sleep(1)
        save("wx.json", out)
        print("wx", sum(len(v) for v in out.values()))


if __name__ == "__main__":
    main()
