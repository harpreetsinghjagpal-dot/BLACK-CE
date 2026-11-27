import json,re,urllib.request,urllib.parse,concurrent.futures as cf,sys
sys.path.insert(0,'build');from collect import fetch,save,OUT
B={"CO":"https://maps.cotrip.org","MN":"https://511mn.org","NY":"https://511ny.org","WY":"https://map.wyoroad.info","ND":"https://travel.dot.nd.gov",
   "TX":"https://drivetexas.org","TN":"https://smartway.tn.gov","VA":"https://511.vdot.virginia.gov","WV":"https://wv511.org","MT":"https://www.511mt.net",
   "SD":"https://sd511.org","SC":"https://www.511sc.org","OK":"https://oktraffic.org","AR":"https://www.idrivearkansas.com","MS":"https://www.mdottraffic.com","RI":"https://www.dot.ri.gov/travel/","WA":"https://wsdot.com/Travel/Real-time/Map/"}
def scan(k,u):
    r={"k":k}
    try:h=fetch(u,accept="text/html,*/*")
    except Exception as e:return {"k":k,"err":str(e)}
    srcs=[urllib.parse.urljoin(u,s) for s in re.findall(r'<script[^>]+src="([^"]+)"',h)]
    hits=set()
    for s in srcs:
        if any(x in s for x in("googletag","jquery","cloudflare","mapbox","google","unpkg","jsdelivr","zencdn","arcgis.com","doubleclick","elfsight")):continue
        try:js=fetch(s,accept="*/*",timeout=60)
        except Exception:continue
        for m in re.finditer(r'(graphql|/api/[\w/\-.]+|https?://[\w.\-]+/[\w/\-.]*(?:camera|cctv|Camera|snapshot|image|event|condition|graphql)[\w/\-.?=&{}]*|[\w/\-.]*(?:Camera|camera|cctv|Cctv)[\w/\-.]*\.(?:json|aspx|ashx|php))',js):
            hits.add(m.group(0)[:150])
        i=js.find('graphql')
        if i>=0:r.setdefault("gctx",[]).append(js[max(0,i-300):i+300])
    r["hits"]=sorted(hits)[:150];r["srcs"]=srcs[:12];return r
res={}
with cf.ThreadPoolExecutor(8) as ex:
    fs={k:ex.submit(scan,k,u) for k,u in B.items()}
    for extra,url in [("AL_list","https://api.algotraffic.com/v3/Cameras"),("AL_list2","https://api.algotraffic.com/v3.0/Cameras"),("RI_cams","https://www.dot.ri.gov/travel/cameras.js")]:
        fs[extra]=ex.submit(lambda u=url:fetch(u,accept="*/*")[:3000])
    for k,f in fs.items():
        try:res[k]=f.result()
        except Exception as e:res[k]={"err":str(e)}
for k in ["MN","CO","NY"]:
    for path in ["/api/graphql"]:
        try:
            res[k+"_gpost"]=fetch(B[k]+path,data=b'{"query":"{__typename}"}',ctype="application/json")[:300]
        except Exception as e:res[k+"_gpost"]=str(e)
save("scan3.json",res)
print({k:(len(v.get("hits",[])) if isinstance(v,dict) else len(v)) for k,v in res.items()})
