import json,sys,re,concurrent.futures as cf
sys.path.insert(0,'build');from collect import fetch,save
H={"MN":("https://new.511mn.org","mn"),"CO":("https://511.cotrip.org","co"),"NY":("https://demo.511ny.org","nysdot")}
res={}
def go(k,host,code):
    r={}
    try:cfg=fetch(host+"/configs/main.json?v=1.10.1");r["config"]=cfg
    except Exception as e:r["config"]="ERR "+str(e);cfg=""
    pairs=sorted(set(re.findall(r'"api":\s*"([^"]+)",\s*"collection":\s*"([^"]+)"',cfg)))
    r["pairs"]=pairs
    base=f"https://api-511x-{code}.carsprogram.org"
    cands=set()
    for api,col in pairs:
        cands|={api+"/"+col,api+"/api/"+col,api+"/v1/"+col,api+"/api/v1/"+col,api+"/"+col+"/all",api+"?collection="+col}
    cands|={base+"/cameras/cameras",base+"/events/events",base+"/cameras/api/cameras",base+"/events/api/events"}
    for u in sorted(cands):
        try:t=fetch(u,timeout=60);r[u]=[len(t),t[:400]]
        except Exception as e:r[u]=["ERR",str(e)[:120]]
    return k,r
with cf.ThreadPoolExecutor(3) as ex:
    for k,r in ex.map(lambda a:go(a[0],*a[1]),H.items()):res[k]=r
save("job6.json",res)
for k,r in res.items():
    print(k,r["pairs"])
    for u,v in r.items():
        if u.startswith("http"):print("  ",v[0],u,str(v[1])[:120].replace("\n"," "))
