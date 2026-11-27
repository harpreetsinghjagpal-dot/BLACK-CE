import csv,json,math,re,sys,unicodedata
def nz(s): return re.sub(r"[^a-z0-9]","",unicodedata.normalize("NFD",s).encode("ascii","ignore").decode().lower().replace("saint","st").replace("sainte","ste").replace("mount","mt").replace("fort","ft"))
db={}
for r in csv.DictReader(open('/home/claude/usb/dl/us_cities.csv')):
    db.setdefault((r['STATE_CODE'],nz(r['CITY'])),[]).append((float(r['LATITUDE']),float(r['LONGITUDE']),r['CITY']))
def km(a,b,c,d):
    x=(d-b)*math.cos(math.radians((a+c)/2));y=c-a;return math.hypot(x,y)*111.2
S={};cur=None
for ln in open('build/corridors.txt',encoding='utf8'):
    ln=ln.strip()
    if not ln or ln.startswith('#'):continue
    if ln.startswith('@'):
        c,en,pa,link=ln[1:].split('|');cur=c;S[c]={'en':en,'pa':pa,'link':link,'hw':[],'pos':{}};continue
    no,name,ts=ln.split('|');S[cur]['hw'].append([no,name,[t.split('@')[0] for t in ts.split(',')]])
    for t in ts.split(','):
        if '@' in t:
            n,ll=t.split('@');la,lo=map(float,ll.split('/'));S[cur]['pos'][n]=(la,lo,'fixed')
miss=[];amb=[]
for c,s in S.items():
    for no,name,ts in s['hw']:
        for t in ts:
            if t in s['pos']:continue
            cand=db.get((c,nz(t)),[])
            if not cand: miss.append((c,t));continue
            if len(cand)>1: amb.append((c,t,cand))
            s['pos'][t]=cand[0][:2]+('db',) if len(cand)==1 else ('AMB',cand)
print('missing',len(miss),miss)
print('ambiguous',len(amb))
for a in amb:print(' ',a[0],a[1],[(round(x[0],2),round(x[1],2)) for x in a[2]])
json.dump({c:{'en':s['en'],'pa':s['pa'],'link':s['link'],'hw':s['hw'],'pos':{k:v for k,v in s['pos'].items()}} for c,s in S.items()},open('/home/claude/usb/stage1.json','w'))

# resolve multi-entry towns by closeness to their highway neighbours, then sanity-check
import statistics
st=json.load(open('/home/claude/usb/stage1.json'))
def P(c,t):
    v=st[c]['pos'][t];return None if v[0]=='AMB' else v
for it in range(3):
    for c,s in st.items():
        for no,name,ts in s['hw']:
            for i,t in enumerate(ts):
                v=s['pos'][t]
                if v[0]!='AMB':continue
                nb=[P(c,ts[j]) for j in (i-1,i+1) if 0<=j<len(ts) and P(c,ts[j])]
                if not nb and it<2:continue
                cand=v[1]
                if nb:best=min(cand,key=lambda q:sum(km(q[0],q[1],n[0],n[1]) for n in nb))
                else:best=sorted(cand)[len(cand)//2]
                s['pos'][t]=[best[0],best[1],'amb']
bad=[]
for c,s in st.items():
    for no,name,ts in s['hw']:
        for a,b in zip(ts,ts[1:]):
            A,B=s['pos'][a],s['pos'][b];d=km(A[0],A[1],B[0],B[1])
            if d>230 or d<1:bad.append((c,no,a,b,round(d)))
print('suspicious hops',len(bad));[print(' ',x) for x in bad]
out={c:{'en':s['en'],'pa':s['pa'],'link':s['link'],'hw':s['hw'],'towns':{t:[round(v[0],3),round(v[1],3)] for t,v in s['pos'].items()}} for c,s in st.items()}
json.dump(out,open('build/us_towns.json','w'),ensure_ascii=False)
print('towns',sum(len(s['towns']) for s in out.values()),'hw',sum(len(s['hw']) for s in out.values()))
