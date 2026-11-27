#!/usr/bin/env python3
"""Probe US state DOT traveller sites for cameras, road conditions and events.
Runs in GitHub Actions (build branch only). Writes build/out/probe.json."""
import json, urllib.request, urllib.parse, concurrent.futures as cf, os, re

UA = "CanadianRoad/1.0 (+https://harpreetsinghjagpal-dot.github.io/BLACK-CE/)"
HOSTS = {
    "AK": ["https://511.alaska.gov"], "AZ": ["https://az511.gov", "https://www.az511.gov"],
    "AL": ["https://algotraffic.com"], "AR": ["https://www.idrivearkansas.com"],
    "CA": [], "CO": ["https://maps.cotrip.org", "https://www.cotrip.org"],
    "CT": ["https://ctroads.org"], "DE": ["https://deldot.gov"], "FL": ["https://fl511.com"],
    "GA": ["https://511ga.org"], "IA": ["https://511ia.org"], "ID": ["https://511.idaho.gov"],
    "IL": ["https://www.gettingaroundillinois.com"], "IN": ["https://511in.org"],
    "KS": ["https://www.kandrive.gov", "https://kandrive.gov"], "KY": ["https://goky.ky.gov"],
    "LA": ["https://www.511la.org", "https://511la.org"], "MA": ["https://mass511.com"],
    "MD": ["https://md511.maryland.gov", "https://chart.maryland.gov"], "ME": ["https://newengland511.org"],
    "MI": ["https://mdotjboss.state.mi.us"], "MN": ["https://511mn.org"],
    "MO": ["https://traveler.modot.org"], "MS": ["https://www.mdottraffic.com"],
    "MT": ["https://www.511mt.net", "https://511mt.net"], "NC": ["https://drivenc.gov"],
    "ND": ["https://travel.dot.nd.gov"], "NE": ["https://511.nebraska.gov"],
    "NH": ["https://newengland511.org"], "NJ": ["https://511nj.org"], "NM": ["https://nmroads.com"],
    "NV": ["https://www.nvroads.com", "https://nvroads.com"], "NY": ["https://511ny.org"],
    "OH": ["https://www.ohgo.com"], "OK": ["https://oktraffic.org"], "OR": ["https://tripcheck.com"],
    "PA": ["https://www.511pa.com"], "RI": ["https://www.dot.ri.gov"], "SC": ["https://www.511sc.org"],
    "SD": ["https://sd511.org"], "TN": ["https://smartway.tn.gov"], "TX": ["https://drivetexas.org"],
    "UT": ["https://udottraffic.utah.gov", "https://prod-ut.ibi511.com"], "VA": ["https://511.vdot.virginia.gov", "https://www.511virginia.org"],
    "VT": ["https://newengland511.org"], "WA": ["https://wsdot.com"], "WI": ["https://511wi.gov"],
    "WV": ["https://wv511.org"], "WY": ["https://map.wyoroad.info", "https://www.wyoroad.info"],
}
LISTS = ["Cameras", "WinterRoads", "RoadConditions", "Incidents", "Closures", "Construction", "MountainPasses"]
EXTRA = [  # (state, url) plain GETs
    ("CA", "https://cwwp2.dot.ca.gov/data/d3/cctv/cctvStatusD03.json"),
    ("CA", "https://cwwp2.dot.ca.gov/data/d3/cc/ccStatusD03.json"),
    ("CA", "https://cwwp2.dot.ca.gov/data/d2/rwis/rwisStatusD02.json"),
    ("OR", "https://tripcheck.com/Scripts/map/data/cctvinventory.js"),
    ("OR", "https://www.tripcheck.com/Scripts/map/data/cctvinventory.js"),
    ("WA", "https://wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc/GetCamerasAsJson"),
    ("WA", "https://data.wsdot.wa.gov/travelcenter/Cameras.json"),
    ("WA", "https://wsdot.com/Travel/Real-time/Service/api/Camera/GetCameras"),
    ("MD", "https://chart.maryland.gov/rest/publicData/getCameraMapDataJSON"),
    ("MD", "https://chartexp1.sha.maryland.gov/CHARTExportClientService/getCameraMapDataJSON.do"),
    ("TN", "https://smartway.tn.gov/Traffic/api/Cameras/0"),
    ("TN", "https://www.tdot.tn.gov/opendata/api/public/RoadwayCameras"),
    ("MI", "https://mdotjboss.state.mi.us/MiDrive/camera/list"),
    ("MO", "https://traveler.modot.org/timconfig/feed/desktop/StreamingCams2.json"),
    ("MO", "https://traveler.modot.org/timconfig/feed/desktop/message.v2.json"),
    ("NC", "https://eapps.ncdot.gov/services/traffic-prod/v1/cameras/"),
    ("TX", "https://its.txdot.gov/ITS_WEB/FrontEnd/svc/DataRequestWebService.svc/GetCctvDataOfArea/ELP"),
    ("IL", "https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/TrafficCamerasTM_Public/FeatureServer/0/query?where=1%3D1&outFields=*&f=json&resultRecordCount=3"),
    ("OH", "https://publicapi.ohgo.com/api/v1/cameras"),
    ("WY", "https://map.wyoroad.info/wtimap/data/wtimap-webcameras.json"),
    ("WY", "https://www.wyoroad.info/highway/webcameras/webcameras.html"),
    ("NM", "https://servicev5.nmroads.com/RealMapWAR/GetCameraInfo"),
    ("KY", "https://services2.arcgis.com/CcI36Pduqd0OR4W9/arcgis/rest/services/trafficCamerasCur_Prd/FeatureServer/0/query?where=1%3D1&outFields=*&f=json&resultRecordCount=3"),
    ("VA", "https://511.vdot.virginia.gov/services/map/layers/map/cams"),
    ("PA", "https://www.511pa.com/map/mapIcons/Cameras"),
    ("ALL", "https://api.weather.gov/alerts/active?area=MT"),
    ("ALL", "https://api.weather.gov/points/46.87,-113.99"),
    ("ALL", "https://geocoding-api.open-meteo.com/v1/search?name=Missoula&count=3&countryCode=US"),
]


def fetch(url, data=None, ctype=None, timeout=25):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if ctype:
        h["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read(400000)
            return r.status, r.headers.get("Content-Type", ""), b.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, "", ""
    except Exception as e:
        return -1, "", str(e)[:200]


def ibi(host, name):
    q = json.dumps({"columns": [{"data": None, "name": ""}, {"name": "sortOrder", "s": True}], "start": 0, "length": 3})
    st, ct, body = fetch(f"{host}/List/GetData/{name}?query={urllib.parse.quote(q)}&lang=en")
    out = {"st": st}
    try:
        j = json.loads(body)
        out["total"] = j.get("recordsTotal")
        out["sample"] = j.get("data", [])[:1]
    except Exception:
        out["head"] = body[:120]
    return out


def gql(host):
    st, ct, body = fetch(f"{host}/api/graphql", data=b'{"query":"{__typename}"}', ctype="application/json")
    return {"st": st, "head": body[:200]}


def probe_host(st_code, host):
    r = {"state": st_code, "host": host}
    st, ct, body = fetch(host)
    r["home"] = st
    r["homehint"] = " ".join(sorted(set(re.findall(r"(ibi511|castlerock|crc|graphql|iteris|List/GetData|Cctv|cameraListing|mapIcons)", body, re.I))))[:200]
    r["ibi"] = {n: ibi(host, n) for n in LISTS}
    r["gql"] = gql(host)
    return r


def main():
    os.makedirs("build/out", exist_ok=True)
    jobs, res = [], {"hosts": [], "extra": []}
    with cf.ThreadPoolExecutor(16) as ex:
        for s, hs in HOSTS.items():
            for h in hs:
                jobs.append(ex.submit(probe_host, s, h))
        ej = [(s, u, ex.submit(fetch, u)) for s, u in EXTRA]
        for j in jobs:
            try:
                res["hosts"].append(j.result())
            except Exception as e:
                res["hosts"].append({"err": str(e)})
        for s, u, f in ej:
            st, ct, body = f.result()
            res["extra"].append({"state": s, "url": u, "st": st, "ct": ct, "len": len(body), "head": body[:600]})
    json.dump(res, open("build/out/probe.json", "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
