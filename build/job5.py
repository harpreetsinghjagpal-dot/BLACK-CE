import json,sys,urllib.parse,re,time,concurrent.futures as cf
sys.path.insert(0,'build');from collect import fetch,save,IBI,wx
def ibi_page(host,name,maxn=20000):
    out=[];start=0;total=None
    while True:
        q=json.dumps({"columns":[{"data":None,"name":""},{"name":"sortOrder","s":True}],"start":start,"length":100})
        j=json.loads(fetch(f"{host}/List/GetData/{name}?query={urllib.parse.quote(q)}&lang=en",timeout=90))
        d=j.get("data",[]);total=j.get("recordsTotal");out+=d
        if not d or len(out)>=(total or 0) or len(out)>=maxn:break
        start+=len(d)
    return out,total
def ibi_cams(host):
    rows,total=ibi_page(host,"Cameras");out=[]
    for r in rows:
        m=re.search(r"POINT \(([-\d.]+) ([-\d.]+)\)",json.dumps(r.get("latLng") or {}))
        imgs=[i for i in (r.get("images") or []) if not i.get("disabled") and not i.get("blocked")]
        if m and imgs:out.append([imgs[0]["id"],r.get("roadway") or "",r.get("location") or "",float(m.group(2)),float(m.group(1)),r.get("areaId") or "",r.get("source") or ""])
    return out,total
res={}
with cf.ThreadPoolExecutor(8) as ex:
    fs={k:ex.submit(ibi_cams,h) for k,h in IBI.items()}
    fs["AB_wr"]=ex.submit(ibi_page,"https://511.alberta.ca","WinterRoads",400)
    for st,h in [("MN","mn"),("CO","co"),("NY","nysdot")]:
        for p in ["cameras","events"]:
            fs[f"cars_{st}_{p}"]=ex.submit(lambda u=f"https://api-511x-{h}.carsprogram.org/{p}":fetch(u,timeout=120))
    for rt in ["I25Cameras","I80Cameras","I90Cameras","NonInterstateCameras"]:
        fs["WY_"+rt]=ex.submit(lambda u="https://www.wyoroad.info/Highway/webcameras/all?route="+rt:fetch(u,accept="text/html",timeout=90))
    for k,f in fs.items():
        try:res[k]=f.result()
        except Exception as e:res[k]="ERR "+str(e)[:200]
info={}
for k,v in res.items():
    if k.startswith("cars_") or k.startswith("WY_"):
        save(f"j5_{k}.txt",v);info[k]=len(v) if isinstance(v,str) else "?"
    elif k=="AB_wr":info[k]=("rows",len(v[0]),"total",v[1]) if not isinstance(v,str) else v
    else:
        if isinstance(v,str):info[k]=v
        else:save(f"j5_ibi_{k}.json",v[0]);info[k]=(len(v[0]),v[1])
print(json.dumps(info,indent=0))
T=json.load(open("build/us_towns.json"));towns=[(c,t,ll[0],ll[1]) for c,s in T.items() for t,ll in s["towns"].items()]
out={}
for i in range(0,len(towns),100):
    b=towns[i:i+100]
    for k in range(4):
        try:
            arr=wx(b)
            for (c,t,la,lo),d in zip(b,arr):out.setdefault(c,{})[t]={"current":d.get("current"),"hourly":d.get("hourly")}
            break
        except Exception as e:print("wx",i,"retry",k,file=sys.stderr);time.sleep(30)
    time.sleep(13)
save("wx.json",out);print("wx",sum(len(v) for v in out.values()),"/",len(towns))
