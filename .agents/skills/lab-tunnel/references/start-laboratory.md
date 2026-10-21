# Iniciar el laboratorio si esta detenido

Usa esta rama despues de comprobar que 8001 esta libre y que no hay un servicio
de laboratorio activo. Si existe una unidad configurada para el modo pedido,
inicia esa unidad y verifica su `MainPID`/puerto. Para el proceso manual usa lo
siguiente desde el Mac, con `PI_SSH`, `PI_PROJECT` y `AUDIO_MODE` ya definidos.

## Dependencias y configuracion

Comprueba en la Pi `.venv/bin/uvicorn`, `python-dotenv` y las dependencias del
modo elegido. Si faltan, sincroniza primero segun `AGENTS.md` y ejecuta desde la
raiz del mirror `uv sync --locked --extra audio --extra voice` para Realtime, o
solo `--extra audio` para greeting, usando el binario `uv` disponible en la Pi.

Realtime requiere `OPENAI_REALTIME_API_KEY` o `OPENAI_API_KEY`. Si falta o es un
placeholder, informa el bloqueo; conserva el modo que pidio el usuario.
Las bases y perfiles se toman de la configuracion del laboratorio; se mantienen
las comprobaciones de aislamiento y las cuotas existentes.

## Arranque manual

El siguiente launcher se ejecuta en la Pi. Carga `.env` sin shell-source,
limpia exports antiguos de sus claves y aplica dos overrides al proceso:
habilitacion y modo. Mantiene `.env` como esta; no requiere token de laboratorio.
La salida contiene solamente el PID. La verificacion posterior confirma que
ese PID realmente abre el puerto y sirve el modo esperado.

```sh
ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_SSH" \
  "'${PI_PROJECT}/.venv/bin/python' - '${PI_PROJECT}' '${AUDIO_MODE}'" <<'PY'
import os
import socket
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

root = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
if mode not in {"greeting", "realtime"}:
    raise SystemExit("Modo de laboratorio invalido")
os.chdir(root)
if not (root / ".env").is_file():
    raise SystemExit("Falta .env en el mirror")
values = dotenv_values(root / ".env")
environment = dict(os.environ)
for key in values:
    environment.pop(key, None)
environment.update({key: value for key, value in values.items() if value is not None})
environment.update(LAB_CALLS_ENABLED="true", LAB_AUDIO_MODE=mode)
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 8001))
process = subprocess.Popen(
    [str(root / ".venv/bin/uvicorn"), "main:create_lab_app", "--factory",
     "--host", "127.0.0.1", "--port", "8001", "--no-access-log", "--no-proxy-headers"],
    cwd=root, env=environment, start_new_session=True,
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
print(process.pid)
PY
```

Guarda el PID como `LAB_PID`; espera hasta 20 segundos a que sea el listener de
8001 y a que la salud sin token responda. Confirma `/proc/<PID>/cwd`, argumentos
y modo efectivo. Si sale o no abre el puerto, informa fallo de arranque en vez
de dar el tunel por listo. Conserva solo diagnosticos seguros, sin volcar `.env`,
entorno completo, credenciales o cuerpos de error del proveedor.

Comprueba tambien acceso desde el Mac con `verify-access.md`.
