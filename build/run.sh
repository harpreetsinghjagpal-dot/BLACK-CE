echo run-9
cd build/test
timeout 1200 python3 wx_us.py --force || true
mkdir -p ../out && cp wx_us.json ../out/wx_us.json 2>/dev/null || true
