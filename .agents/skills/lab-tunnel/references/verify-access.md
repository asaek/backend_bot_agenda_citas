# Verificar acceso directo desde la Pi y el Mac

Ejecutar desde el Mac con `PI_SSH`, `PI_PROJECT`, `LAB_PID`, `LOCAL_PORT` y
`AUDIO_MODE` definidos. El PID debe haberse relacionado con el listener 8001 en
el paso 2 de la skill. El script usa solo biblioteca estandar local; el backend
y sus comprobaciones internas siguen en la Pi.

Se comprueban salud remota/local y HTML sin cabecera de autenticacion.
Si SSH/HTTP fallan, se informa solo el tipo de error.

```sh
python3 - "$PI_SSH" "$PI_PROJECT" "$LAB_PID" "$LOCAL_PORT" "$AUDIO_MODE" <<'PY'
import json
import shlex
import subprocess
import sys
import urllib.request

remote = r'''
import json
import sys
import urllib.request
from pathlib import Path

root = Path(sys.argv[1]).resolve()
proc = Path("/proc") / str(int(sys.argv[2]))
assert (proc / "cwd").resolve() == root
command = (proc / "cmdline").read_bytes().split(b"\0")
assert b"main:create_lab_app" in command and b"--factory" in command
assert command[command.index(b"--port") + 1] == b"8001"
with urllib.request.urlopen("http://127.0.0.1:8001/lab/health", timeout=5) as response:
    assert response.status == 200
    assert json.load(response) == {"status": "ok", "mode": "laboratory", "audio_mode": sys.argv[3]}
print("remote_health_ok")
'''

try:
    target, root, pid, port, mode = sys.argv[1:]
    command = shlex.join([root + "/.venv/bin/python", "-c", remote, root, pid, mode])
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", target, command],
        capture_output=True, timeout=20,
    )
    if result.returncode:
        raise RuntimeError("No se pudo validar el laboratorio remoto")
    base = "http://127.0.0.1:" + str(int(port))
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with client.open(base + "/lab/health", timeout=5) as response:
        assert response.status == 200
        assert json.load(response) == {"status": "ok", "mode": "laboratory", "audio_mode": mode}
    with client.open(base + "/lab", timeout=5) as response:
        assert response.status == 200 and "text/html" in response.headers.get("Content-Type", "")
        html = response.read().decode()
        assert 'id="token"' not in html and 'id="check"' not in html
        assert "Conectar e iniciar llamada" in html
    print(json.dumps({"url": "http://localhost:" + str(int(port)) + "/lab",
                      "remote_health": 200, "local_health_without_token": 200,
                      "page": 200, "token_required": False}))
except Exception as error:
    print(json.dumps({"ready": False, "error_type": type(error).__name__}))
    raise SystemExit(1)
PY
```

Si falla, identifica el paso mediante checks seguros y reporta el bloqueo concreto.
