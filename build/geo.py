import json,math,re
def dp(pts,tol):
    if len(pts)<3:return pts
    a,b=pts[0],pts[-1];dx,dy=b[0]-a[0],b[1]-a[1];L=math.hypot(dx,dy) or 1e-12
    imax,dmax=0,-1
    for i in range(1,len(pts)-1):
        p=pts[i];d=abs(dy*p[0]-dx*p[1]+b[0]*a[1]-b[1]*a[0])/L
        if d>dmax:dmax,imax=d,i
    if dmax<=tol:return [a,b]
    return dp(pts[:imax+1],tol)[:-1]+dp(pts[imax:],tol)
j=json.load(open('/home/claude/usb/dl/ne_10m_roads.geojson'))
roads=[];npts=0
for f in j['features']:
    p=f['properties']
    if p.get('sov_a3')!='USA' or p.get('type') in('Ferry Route',) :continue
    lv=p.get('level');num=str(p.get('name') or '').split(';')[0].split('/')[0].strip()
    if lv=='Interstate' and re.fullmatch(r'\d+[A-Z]?',num):no,sec='I-'+num,0
    elif lv=='Federal' and re.fullmatch(r'\d+[A-Z]?',num):no,sec='US-'+num,1
    else:continue
    g=f['geometry'];lines=[g['coordinates']] if g['type']=='LineString' else g['coordinates']
    for ln in lines:
        s=dp([(q[0],q[1]) for q in ln],0.012)
        if len(s)<2:continue
        flat=[]
        for x,y in s:flat+= [round(y,3),round(x,3)]
        roads.append([no,sec,flat]);npts+=len(s)
print('roads',len(roads),'pts',npts)
json.dump(roads,open('/home/claude/usb/us_roads.json','w'),separators=(',',':'))
us=json.load(open('/tmp/us.json'))
sh={}
for f in us['features']:
    g=f['geometry'];polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
    sh[f['properties']['name']]=[[[round(x,2),round(y,2)] for x,y in dp([tuple(q) for q in poly[0]],0.02)] for poly in polys if len(poly[0])>8]
    sh[f['properties']['name']+'#o']=[[[round(x,2),round(y,2)] for x,y in dp([tuple(q) for q in poly[0]],0.08)] for poly in polys if len(poly[0])>30]
json.dump(sh,open('/home/claude/usb/us_shapes.json','w'),separators=(',',':'))
import os;print(os.path.getsize('/home/claude/usb/us_roads.json'),os.path.getsize('/home/claude/usb/us_shapes.json'))
