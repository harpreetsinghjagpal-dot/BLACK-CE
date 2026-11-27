import json,sys,concurrent.futures as cf
sys.path.insert(0,'build');from collect import fetch,save
H={"MN":"https://new.511mn.org","CO":"https://511.cotrip.org","NY":"https://demo.511ny.org","IA":"https://511ia.org","IN":"https://511in.org","KS":"https://www.kandrive.gov","MA":"https://mass511.com","NE":"https://511.nebraska.gov"}
SLUGS=["normalCameras","incidents","closures","roadReports","winterDriving","roadConditions","weatherWarnings","constructionClosures","construction","towingProhibited","truckersReports","mountainPasses","chainLaws","plowCameras","roadWeather","winterRoads","weatherReports","restAreas","alerts","flooding","futureRoadwork","roadwork","winterRoadConditions","signs","messageSigns","weatherStations","rwis","trafficSpeeds","crashes","truckRestrictions"]
Q=("query MapFeatures($input: MapFeaturesArgs!){mapFeaturesQuery(input:$input){mapFeatures{bbox tooltip uri features{id geometry properties} __typename "
   "... on Camera{views(limit:5){uri category ... on CameraView{url}}}} error{message type}}}")
def mf(host,slug,box=(49.5,24,-66,-125)):
    v={"input":{"north":box[0],"south":box[1],"east":box[2],"west":box[3],"zoom":12,"layerSlugs":[slug],"nonClusterableUris":["dashboard"]}}
    return json.loads(fetch(host+"/api/graphql",data=json.dumps({"query":Q,"variables":v}).encode(),ctype="application/json",timeout=120))
res={}
def one(k,h):
    r={}
    try:r["config"]=fetch(h+"/configs/main.json?v=1.10.1")[:6000]
    except Exception as e:r["config"]=str(e)
    for s in SLUGS:
        try:
            j=mf(h,s);d=(j.get("data") or {}).get("mapFeaturesQuery") or {};fs=d.get("mapFeatures") or []
            r[s]={"n":len(fs),"err":d.get("error") or j.get("errors"),"sample":fs[:2]}
        except Exception as e:r[s]={"exc":str(e)[:200]}
    return k,r
with cf.ThreadPoolExecutor(8) as ex:
    for k,r in ex.map(lambda a:one(*a),H.items()):res[k]=r
for k in ["MN","CO","NY"]:
    try:
        if res[k]["normalCameras"].get("n"):save(f"c_gqlt_{k}.json",mf(H[k],"normalCameras"))
    except Exception as e:print(k,e)
try:res["WY_page"]=fetch("https://www.wyoroad.info/highway/webcameras/webcameras.html",accept="text/html")
except Exception as e:res["WY_page"]=str(e)
save("scan4.json",res)
for k,v in res.items():
    if isinstance(v,dict):print(k,{s:(x.get("n"),str(x.get("err") or x.get("exc") or "")[:60]) for s,x in v.items() if s!="config"})
