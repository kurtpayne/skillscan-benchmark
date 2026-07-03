"""Open-weight LLM endpoint on Modal — one OpenAI-compatible API that serves BOTH the
scoreboard's LLM baseline AND the scanners' `--use-llm` backend (Principle 2: malicious corpus
only ever hits open-weight, never a commercial API).

Model: Qwen2.5-72B-Instruct-AWQ (4-bit, ~40GB → fits ONE H100; not gated, no HF token needed).
vLLM serves the OpenAI-compatible server at /v1. Cost-smart: scales to zero after idle, so the
H100 (~$4-6/hr) is only billed while actually serving requests.

Deploy:   infisical run --env=dev -- modal deploy llm/modal_vllm.py
URL:      printed on deploy (…/v1).  Auth: VLLM_API_KEY (Modal secret 'scoreboard-llm').
Teardown: modal app stop skillscan-benchmark-llm   (or just let it idle to zero)
"""

import modal

MODEL = "Qwen/Qwen2.5-72B-Instruct-AWQ"
MODEL_REVISION = "main"
N_GPU = 1

app = modal.App("skillscan-benchmark-llm")

vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.6.6", "huggingface_hub[hf_transfer]==0.27.0")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

# cache model weights on a volume so cold starts don't re-download ~40GB
hf_cache = modal.Volume.from_name("scoreboard-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("scoreboard-vllm-cache", create_if_missing=True)

# a shared bearer key so the endpoint isn't open to the world (consumed by the adapters)
api_secret = modal.Secret.from_name("scoreboard-llm", required_keys=["VLLM_API_KEY"])

VLLM_PORT = 8000


@app.function(
    image=vllm_image,
    gpu=f"H100:{N_GPU}",
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    secrets=[api_secret],
    timeout=20 * 60,
    scaledown_window=5 * 60,  # spin down 5 min after the last request → no idle H100 bill
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=15 * 60)
def serve():
    import os
    import subprocess

    cmd = [
        "vllm", "serve", MODEL,
        "--revision", MODEL_REVISION,
        "--host", "0.0.0.0", "--port", str(VLLM_PORT),
        "--api-key", os.environ["VLLM_API_KEY"],
        "--quantization", "awq_marlin",
        "--max-model-len", "8192",
        "--gpu-memory-utilization", "0.92",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
