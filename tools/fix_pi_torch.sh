#!/bin/bash
# Replace CUDA / too-new PyTorch wheels with a Raspberry Pi 4-safe CPU build.
# Pi 4 Cortex-A72 is ARMv8.0 and SIGILLs on torch 2.10+/2.13 and on +cu wheels.
set -euo pipefail

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "Activate the project venv first:  source venv/bin/activate" >&2
  exit 1
fi

echo "Removing CUDA / current torch wheels..."
pip uninstall -y torch torchvision torchaudio || true
# xargs -r is GNU; fall back if it is missing.
pkgs="$(pip freeze | grep -E '^(nvidia-|cuda-)' | cut -d= -f1 || true)"
if [[ -n "${pkgs}" ]]; then
  echo "${pkgs}" | xargs pip uninstall -y
fi

echo "Installing Pi 4-safe CPU torch 2.3.1 + torchvision 0.18.1..."
pip install 'torch==2.3.1' 'torchvision==0.18.1'

python3 - <<'PY'
import torch
x = torch.zeros(1) + 1
print(f"torch {torch.__version__} ok: {x.item()}")
if "+cu" in torch.__version__.lower() or "cuda" in torch.__version__.lower():
    raise SystemExit("ERROR: still a CUDA wheel. Re-run this script.")
PY

echo "Done. Retry: python3 app.py --person-only --display"
