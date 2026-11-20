#!/usr/bin/env python3
"""Lanza en paralelo los jobs de un plan (imágenes o videos) en Higgsfield, espera y baja cada resultado.

  python3 hf_run.py plan.json out_dir            # genera (gasta créditos)
  python3 hf_run.py plan.json out_dir --dry-run  # solo pide el costo de cada job (gratis) y valida el plan

Plan de imágenes:
  {"model": "nano_banana_pro", "aspect_ratio": "9:16", "resolution": "2k",
   "jobs": [{"label": "1A_salivales", "prompt": "...", "refs": ["<job id o ruta>"], "n": 2}]}
Plan de videos:
  {"model": "kling3_0", "mode": "pro", "aspect_ratio": "9:16", "sound": "off", "duration": 3,
   "jobs": [{"label": "1_salivales", "start": "<job id>", "prompt": "...", "duration": 3, "end": "<job id>"}]}

"n" crea variantes con sufijo _1, _2 (mismo prompt). Guarda <label>.log, <label>.png|.mp4 y results.json.
Sale con código 1 si algún job falló y 2 si el plan no tenía jobs.
"""
import concurrent.futures as cf
import json
import pathlib
import re
import subprocess
import sys
import time

plan_path, out_dir = sys.argv[1], pathlib.Path(sys.argv[2])
dry = "--dry-run" in sys.argv
plan = json.load(open(plan_path))
model = plan["model"]
is_video = model.startswith(("kling", "seedance", "veo", "wan", "minimax", "hailuo"))

jobs = []
for j in plan.get("jobs", []):
    n = int(j.get("n", 1))
    for k in range(n):
        jj = dict(j)
        jj["label"] = j["label"] if n == 1 else f"{j['label']}_{k + 1}"
        jobs.append(jj)
if not jobs:
    print("el plan no tiene jobs"); sys.exit(2)
out_dir.mkdir(parents=True, exist_ok=True)


def args_for(j):
    a = [model, "--prompt", j["prompt"]]
    if is_video:
        a += ["--mode", str(j.get("mode", plan.get("mode", "pro"))),
              "--aspect_ratio", str(j.get("aspect_ratio", plan.get("aspect_ratio", "9:16"))),
              "--duration", str(j.get("duration", plan.get("duration", 3))),
              "--sound", str(j.get("sound", plan.get("sound", "off")))]
        if j.get("start"):
            a += ["--start-image", j["start"]]
        if j.get("end"):
            a += ["--end-image", j["end"]]
    else:
        a += ["--aspect_ratio", str(j.get("aspect_ratio", plan.get("aspect_ratio", "9:16"))),
              "--resolution", str(j.get("resolution", plan.get("resolution", "2k")))]
        for r in j.get("refs", []):
            a += ["--image", r]
    return a


def caido(stderr):
    """True si Higgsfield respondió que el servicio no está disponible (no se creó ningún job)."""
    return bool(re.search(r"HTTP 503|503 Service Unavailable", stderr or ""))


def run(j):
    if dry:
        p = subprocess.run(["higgsfield", "generate", "cost", *args_for(j)], capture_output=True, text=True)
        return j["label"], p.returncode, None, (p.stdout.strip().splitlines() or [p.stderr.strip()])[-1]
    cmd = ["higgsfield", "generate", "create", *args_for(j), "--wait", "--wait-timeout", "30m",
           "--wait-interval", "10s" if is_video else "5s", "--json"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1900)
    log = p.stdout + "\n--- stderr ---\n" + p.stderr
    if p.returncode != 0 and not re.search(r'"result_url"', p.stdout) and caido(p.stderr):
        # 503: el servidor de Higgsfield se cayó un momento y no se creó el job. Un reintento.
        time.sleep(30)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=1900)
        log += "\n--- reintento tras 503 ---\n" + p.stdout + "\n--- stderr ---\n" + p.stderr
    (out_dir / f"{j['label']}.log").write_text(log)
    urls = re.findall(r'"result_url":\s*"([^"]+)"', p.stdout)
    ids = re.findall(r'"id":\s*"([0-9a-f-]{36})"', p.stdout)
    if urls:
        ext = pathlib.Path(urls[0].split("?")[0]).suffix or (".mp4" if is_video else ".png")
        subprocess.run(["curl", "-s", "-o", str(out_dir / f"{j['label']}{ext}"), urls[0]], check=True)
    return j["label"], p.returncode, (ids[0] if ids else None), (urls[0] if urls else "SIN RESULTADO")


results, failed = {}, 0
with cf.ThreadPoolExecutor(max_workers=min(len(jobs), 10)) as ex:
    for label, rc, jid, info in ex.map(run, jobs):
        results[label] = {"rc": rc, "job_id": jid, "info": info}
        failed += int(rc != 0 or info == "SIN RESULTADO")
        print(f"{label:28s} rc={rc} {jid or ''} {info}", flush=True)
if not dry:
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
print(f"{len(jobs)} jobs · {failed} con problema" + (" · (dry-run: nada generado)" if dry else ""))
sys.exit(1 if failed else 0)
