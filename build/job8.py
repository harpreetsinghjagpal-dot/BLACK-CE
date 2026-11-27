import json,sys,time,unicodedata,urllib.parse,concurrent.futures as cf
sys.path.insert(0,'build');from collect import fetch,save,nws_zone,wx
nz=lambda s:unicodedata.normalize("NFD",str(s or "")).encode("ascii","ignore").decode().lower()
Q=json.load(open("build/mx_query.json"));out={};log=[]
for st,t in Q["towns"]:
    wants=[nz(a) for a in Q["states"][st]];best=None
    try:j=json.loads(fetch("https://geocoding-api.open-meteo.com/v1/search?count=20&language=en&format=json&countryCode=MX&name="+urllib.parse.quote(t)))
    except Exception as e:log.append([st,t,"ERR",str(e)]);continue
    for r in j.get("results",[]) or []:
        a1=nz(r.get("admin1"))
        if not any(a1==w or a1.startswith(w) or w.startswith(a1) and len(a1)>5 for w in wants):continue
        score=(1 if str(r.get("feature_code","")).startswith("PPL") else 0, nz(r.get("name"))==nz(t), r.get("population") or 0)
        if best is None or score>best[0]:best=(score,r)
    if best:out[st+"|"+t]=[round(best[1]["latitude"],3),round(best[1]["longitude"],3),best[1].get("name"),best[1].get("population"),best[1].get("admin2")]
    else:log.append([st,t,"none",[(r.get("name"),r.get("admin1")) for r in (j.get("results") or [])[:5]]])
    time.sleep(0.3)
save("mx_pos.json",out);save("mx_log.json",log);print("mx",len(out),"/",len(Q["towns"]),"missing",log)
HI=json.load(open("build/hi_towns.json"))
z={}
for t,la,lo in HI:
    c,tt,fz,cz=nws_zone("HI",t,la,lo);z[t]=[fz,cz]
save("hi_zones.json",z);print("hi zones",sum(1 for v in z.values() if v[0]),"/",len(HI))
