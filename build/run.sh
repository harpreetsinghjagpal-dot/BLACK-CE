echo run-7
cd build/test
python3 official.py
python3 -c "import json;d=json.load(open(\"official.json\"));print(\"ERR\",json.dumps(d[\"err\"]));print({k:len(v) for k,v in d[\"p\"].items()})"
timeout 600 python3 wx_us.py --force || true
mkdir -p ../out && cp official.json wx_us.json ../out/ 2>/dev/null || true
# rerun
