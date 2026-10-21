# Verificacion de aiortc y laboratorio de audio - 2026-10-18

## Entorno y frontera

- Raspberry Pi 4 Model B Rev 1.4, aproximadamente 4 GB (3 886 840 KiB MemTotal).
- Debian GNU/Linux 13.7 (trixie), kernel `6.18.50+rpt-rpi-v8`, `aarch64`, glibc 2.41.
- CPython 3.13.5; `uv` 0.12.17 en `/home/asaek/.local/bin/uv`.
- `aiortc` 1.14.0, PyAV 16.1.0, NumPy 2.5.4, cryptography 50.0.1,
  pylibsrtp 1.0.0. Instalacion mediante el extra `audio` y `uv.lock`.
- Todas las ejecuciones del proyecto se hicieron en el mirror de la Pi tras
  sincronizar los cambios locales. El WAV fijo se preparo como recurso local
  con Paulina/es_MX; tiene 5.129 segundos, PCM16 mono a 16 kHz.
- Laboratorio entre procesos de la misma Pi, candidatos ICE host, sin STUN/TURN,
  Meta, Google, STT, LLM o TTS de red. No acredita elegibilidad ni medios de Meta.

## A. Compatibilidad y senal bidireccional

Comandos desde la raiz del mirror:

```sh
~/.local/bin/uv sync --locked --extra audio
.venv/bin/python scripts/probe_aiortc.py --seconds 10
```

Dos extremos WebRTC independientes envian tonos de 440 y 880 Hz. Se fuerza Opus,
se decodifica la senal recibida y se compara su frecuencia con la de entrada.

| Resultado | Observado con las dependencias bloqueadas |
| --- | --- |
| Codificador / decodificador PyAV | `libopus` / `opus` |
| Recepcion de 880 Hz | 500 frames, 10.0 s, 500 no silenciosos, 879.8 Hz, RMS 4008.4 |
| Recepcion de 440 Hz | 500 frames, 10.0 s, 500 no silenciosos, 440.0 Hz, RMS 3999.0 |
| Tiempo de pared | 10.143 s |
| CPU de ambos extremos juntos | 5.151 s; 50.8 % de un nucleo |
| RSS inicial / final / pico observado | 76.53 / 83.35 / 83.35 MiB |
| Cierre de ambas conexiones | Comprobado |

Son medidas puntuales de un proceso que contiene ambos extremos, no una estimacion
de capacidad concurrente ni una garantia de rendimiento.

## B-E. API, medios y cliente real

```sh
~/.local/bin/uv run --no-sync python -m unittest discover -s tests -p 'test_call*.py' -v
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_browser.py
```

La segunda prueba crea un backend temporal en un puerto libre y base temporal,
genera un token en memoria y abre el cliente HTML real en Chromium
`154.0.8037.92`. Playwright es solo una herramienta transitoria de verificacion;
el backend utiliza el entorno `.venv` del proyecto con las versiones bloqueadas.

Resultados de Chromium:

- API rechaza acceso sin token; conexion mediante POST, consulta y cierre por ID.
- Backend decodifica 280 frames de entrada, todos con senal, 5.60 s y RMS 3482.3.
- Backend emite los 5.129 s del saludo, en 257 frames de fuente.
- Navegador recibe 285 paquetes / 60 535 bytes; elemento de audio reproduciendo
  (`paused=false`), `currentTime=5.871998 s` al verificar.
- Saludo completo y cierre normal: correcto.
- Colgar durante el saludo: `interrupted`, recursos liberados.
- Cerrar el peer remoto durante el saludo: `input_ended`, recursos liberados.
- SIGTERM durante el saludo: cierre supervisado, `server_shutdown`, saludo
  `interrupted`, recursos liberados y proceso finalizado.
- Se reutiliza capacidad en llamadas sucesivas; cero errores JavaScript.
- Cancelar la adquisicion de microfono, reconectar con tono y resolver el permiso
  antiguo no desconecta el reproductor de la nueva llamada.
- Colgar dos veces simultaneamente permite volver a conectar. Un HTTP 503
  inyectado en el primer DELETE conserva el boton de reintento; el siguiente
  DELETE finaliza. La recuperacion de SQLite real se verifica por separado abajo.
- En el proceso backend de esta secuencia: 13.931 s de pared, 2.22 s de CPU,
  15.9 % de un nucleo, RSS inicial/final/pico muestreado
  102.98 / 111.04 / 111.04 MiB. Incluye pausas entre escenarios; no equivale al
  costo de una llamada continua. Estas cifras excluyen el consumo de Chromium.

Los tests automatizados verifican ademas oferta invalida, capacidad, expiracion de
negociacion e inactividad, cierre repetido/concurrente, reinicio, bloqueo de base
entre procesos y ausencia de rutas de laboratorio en `main:app`. Un subprocess
comprueba que importar la factory no inicializa Google ni carga `aiortc`.
La revision independiente encontro y se corrigio un cierre que dependia de
SQLite y una carrera de permiso tardio de microfono. Las regresiones reproducen
esos casos: un escritor SQLite bloquea las escrituras reales, pero el audio se
cierra y el resultado se puede persistir despues sin otro cierre; el navegador
conserva el stream propietario de la nueva llamada.
La prueba HTTP de POST fallido devuelve `session_id` aun con error de escritura,
libera medios y permite terminar mediante DELETE tras liberar el escritor.

## Regresion y espejo

- Suite completa en la Pi: **405 tests correctos**, incluidos 13 de laboratorio,
  en 41.263 segundos. Tras el ultimo ajuste solo del cliente se repitio Chromium,
  con los resultados anteriores.
- `compileall` correcto para backend, nuevos modulos, scripts y tests.
- Proyecto sincronizado desde el checkout local. `.env` completo transferido y
  comparado byte a byte, modo remoto `600`, sin imprimir valores.
- El cierre de despliegue recarga el proceso verificado de texto y comprueba
  salud, ambos metodos del webhook local/publico y autenticacion Meta de solo
  lectura conforme al procedimiento del mirror. Los resultados operativos se
  reportan con el despliegue.

Primera recarga comprobada: Uvicorn manual, PID 1683475 -> 3361713, cwd correcto
y configuracion efectiva igual a `.env`. Sin unidad de servicio del proyecto;
ngrok existente (PID 10223) conservado. Salud y GET/POST de webhook local y publico:
HTTP 200 con cuerpos esperados; `/lab` en `main:app`: 404 esperado.

La comprobacion de autenticacion de solo lectura contra Graph API v23.0 fallo:
HTTP **401**, codigo **190**, subcodigo **463** (token configurado vencido).
El laboratorio no necesita ese token, pero el cierre operativo de autenticacion
WhatsApp queda pendiente de renovarlo y repetir la comprobacion. No se enviaron
mensajes ni se realizo una renovacion de tokens durante esta prueba.

## Pendientes y cierre operativo

- La [verificacion posterior de cliente/LAN](./2026-10-18-webrtc-client-lan.md)
  comprobo Chrome en macOS contra la Pi. Falta escuchar fisicamente el saludo y
  probar el microfono real desde la computadora.
  Chromium headless acredita recepcion/decodificacion y avance de reproduccion,
  no escucha humana en altavoces.
- C1 completo de Calling, C3-C5 y la elegibilidad/conectividad con Meta siguen
  pendientes. La funcionalidad entregada corresponde al laboratorio A-E.
