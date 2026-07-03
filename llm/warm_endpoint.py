"""Warm + smoke-test the Modal vLLM endpoint (urllib, long timeout for cold-start model load).
Reads the bearer key from _staging/.llm_key. Run: python3 llm/warm_endpoint.py"""

import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.environ.get("MODAL_LLM_URL", "https://<your-modal-app>.modal.run")
MODEL = "Qwen/Qwen2.5-72B-Instruct-AWQ"

key = ""
with open(os.path.join(HERE, "_staging", ".llm_key")) as f:
    key = f.read().strip().split("=", 1)[1]

hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def call(path, data=None, timeout=900):
    req = urllib.request.Request(URL + path, data=(json.dumps(data).encode() if data else None), headers=hdr)
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r), round(time.monotonic() - t0, 1)


print("warming (cold start = ~40GB download + vLLM load; up to 15 min)…", flush=True)
try:
    models, dt = call("/v1/models", timeout=900)
    print(f"/v1/models OK in {dt}s: {[m['id'] for m in models.get('data', [])]}", flush=True)
    out, dt = call("/v1/chat/completions", {
        "model": MODEL, "max_tokens": 8, "temperature": 0,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    }, timeout=120)
    print(f"completion in {dt}s: {out['choices'][0]['message']['content']!r}", flush=True)
    print("ENDPOINT READY")
except Exception as e:  # noqa: BLE001
    print(f"ERROR: {type(e).__name__}: {str(e)[:200]}")
