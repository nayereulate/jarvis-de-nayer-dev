"""Crea data/conectar-celular.png: un QR con la dirección de Jarvis y su token. No lo compartas."""
import json
import subprocess
from pathlib import Path

import qrcode

DATA = Path(__file__).resolve().parent / "data"

status = json.loads(subprocess.run(["tailscale", "status", "--json"], capture_output=True, check=True).stdout)
host = status["Self"]["DNSName"].rstrip(".")
token = (DATA / "token.txt").read_text(encoding="utf-8").strip()
output = DATA / "conectar-celular.png"
qrcode.make(f"https://{host}/#token={token}", border=4).save(output)
print(f"https://{host}")
print(output)
