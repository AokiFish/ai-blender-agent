"""探测 agnes image 模型调用方式（chat completions vs images/generations）。"""
import re
import base64
import requests

cfg = {}
for line in open(".env", encoding="utf-8"):
    m = re.match(r"\s*([A-Z_0-9]+)\s*=\s*(.+)", line)
    if m:
        cfg[m.group(1)] = m.group(2).split("#")[0].strip().strip('"').strip("'")
base = cfg["BLENDER_AGENT_BASE_URL"].rstrip("/")
key = cfg["BLENDER_AGENT_API_KEY"]
H = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

# 方式1: images/generations
print("== /images/generations")
r = requests.post(base + "/images/generations", headers=H, json={
    "model": "agnes-image-2.5-flash",
    "prompt": "a red cube on white background",
    "n": 1, "size": "512x512",
}, timeout=120)
print("HTTP", r.status_code, r.text[:400])

# 方式2: chat completions（多模态返回）
print("== chat completions with image model")
r = requests.post(base + "/chat/completions", headers=H, json={
    "model": "agnes-image-2.5-flash",
    "messages": [{"role": "user", "content": "Generate an image of a red cube on white background"}],
}, timeout=180)
print("HTTP", r.status_code)
body = r.text
print(body[:600])
