"""探测 agnes 平台的模型列表（只打印模型名与端点路径，不打印 key）。"""
import re
import requests

cfg = {}
for line in open(".env", encoding="utf-8"):
    m = re.match(r"\s*([A-Z_0-9]+)\s*=\s*(.+)", line)
    if m:
        cfg[m.group(1)] = m.group(2).split("#")[0].strip().strip('"').strip("'")
base = cfg["BLENDER_AGENT_BASE_URL"].rstrip("/")
key = cfg["BLENDER_AGENT_API_KEY"]

for path in ("/models", "/v1/models"):
    try:
        r = requests.get(base + path, headers={"Authorization": "Bearer " + key}, timeout=20)
        print(path, "-> HTTP", r.status_code)
        print(r.text[:1500])
    except Exception as e:
        print(path, "ERR", type(e).__name__, str(e)[:150])
    print("-" * 40)
