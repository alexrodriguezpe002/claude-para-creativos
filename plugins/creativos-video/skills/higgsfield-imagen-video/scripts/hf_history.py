#!/usr/bin/env python3
"""Historial de Higgsfield con prompt, referencias y ajustes: sirve para recuperar cómo se hizo algo
(también lo que se generó a mano en la web).

  python3 hf_history.py --video --since 2026-09-16 --grep thyroid
  python3 hf_history.py --image --full <job_id>

--image / --video (por defecto ambos), --since AAAA-MM-DD, --grep texto (en el prompt),
--full imprime el prompt entero. Pide hasta 100 por tipo (el máximo de la CLI).
"""
import json
import subprocess
import sys

a = sys.argv[1:]
kinds = [k for k in ("--image", "--video") if k in a] or ["--image", "--video"]
since = a[a.index("--since") + 1] if "--since" in a else ""
grep = a[a.index("--grep") + 1].lower() if "--grep" in a else ""
full = "--full" in a
only = [x for x in a if len(x) == 36 and x.count("-") == 4]

n = 0
for k in kinds:
    p = subprocess.run(["higgsfield", "generate", "list", k, "--size", "100", "--json"], capture_output=True, text=True)
    try:
        rows = json.loads(p.stdout[p.stdout.index("["):])
    except ValueError:
        print("no se pudo leer el historial:", p.stderr.strip()[:200]); sys.exit(2)
    for j in rows:
        pr = (j.get("params") or {}).get("prompt") or ""
        if since and j["created_at"][:10] < since: continue
        if grep and grep not in pr.lower(): continue
        if only and j["id"] not in only: continue
        pa = j.get("params") or {}
        refs = [m.get("id") for m in (pa.get("input_images") or [])] + \
               [m.get("data", {}).get("id") for m in (pa.get("medias") or []) if isinstance(m, dict)]
        extra = {x: pa.get(x) for x in ("aspect_ratio", "resolution", "duration", "mode") if pa.get(x)}
        print(f"{j['created_at'][:16]} {j['job_type']:16s} {j['id']} {extra} refs={[r for r in refs if r]}")
        print("   ", pr if full else pr[:160].replace("\n", " "))
        n += 1
print(f"— {n} jobs")
sys.exit(0 if n else 2)
