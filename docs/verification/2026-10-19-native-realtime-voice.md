# Voz nativa OpenAI Realtime - 2026-10-19

## Estado y alcance

Implementado y verificado el laboratorio navegador -> Raspberry -> OpenAI Realtime
-> Raspberry -> navegador. Incluye herramientas de agenda falsa, historial
asincrono y confirmaciones de laboratorio. Meta Calling y la continuidad con
pacientes/chat operativos permanecen en C4/C5. La ADR 0056 recoge la decision.

El mirror actual es `asaek@192.168.1.12:~/Downloads/chatbot_test_repo`, indicado
por el usuario al cambiar de red. La evidencia del dia 18 conserva la direccion
que se uso entonces; las instrucciones activas usan la direccion actual.

## Entorno y protocolo

- Backend y todos los tests/driver en Raspberry Pi, Python 3.13.5.
- `aiortc==1.14.0`, `av==16.1.0`, `websockets==16.1.1`, dependencias bloqueadas con
  extras `audio` y `voice`. `uv sync --locked --extra audio --extra voice` correcto.
- Entrada/salida de llamada por WebRTC/Opus, puente PCM16 mono 24 kHz y WebSocket
  Realtime GA. Modelo real `gpt-realtime-2.1`, voz `marin`, transcripcion paralela
  `gpt-4o-mini-transcribe`. El agente de texto no se ejecuta por turno hablado.
- Chrome 155.0.8059.82 en macOS, perfil aislado headless. HTTP/CDP reenviados por
  SSH a loopback; el candidato remoto de medios se verifico contra las direcciones
  reales de la Pi. Hay interfaces adicionales: no se infiere que el par siempre
  seleccione una sola subred IPv4 concreta.
- Navegador automatizado silenciado y muestras sinteticas Paulina. No se capturo
  microfono fisico ni se verifico escucha humana. No se enviaron mensajes WhatsApp
  ni se escribio Google Calendar.

## Verificacion de contratos y regresion

**431 tests correctos en 46.305 s** en la Pi, incluidos los nuevos tests de voz,
el WebSocket real local y el puente WebRTC real con proveedor falso.

Se verifico:

- Conexiones GA, PCM y resultados de herramientas por un WebSocket local real;
  cierre de handshake rechazado y errores sin cuerpos/credenciales.
- Opus entrante convertido a PCM24k y audio de proveedor devuelto por RTP.
- Respuesta de audio antes de recibir la transcripcion; eventos duplicados no
  duplican consumo, herramientas ni citas.
- Cancelacion, audio tardio descartado y contexto interrumpido sin afirmar una
  respuesta completa. `listening` espera a que drenen todos los elementos de audio.
- Nombre, motivo, fechas, alcance del paciente y rangos validados con contratos
  compartidos; crear/reprogramar/cancelar sobre agenda falsa persistida.
- Pregunta literal y emision completa antes de confirmar, turno posterior,
  expiracion, rechazo, cambio de tema y cierre.
- Confirmacion encolada obsoleta y revocacion mientras la reclamacion SQL espera:
  no ejecutan la mutacion. El escritor SQL se adquiere antes de comprobar la
  autorizacion y esta se conserva hasta hacer durable la reclamacion.
- SQLite bloqueada al cerrar: ambos transportes se liberan, la API conserva
  persistencia pendiente y DELETE reintenta sin cerrar recursos dos veces.
- Drenaje acotado de transcripcion al colgar, marcadores si falta texto y estados
  interrumpidos tras reinicio, sin respuestas huerfanas ni autorizaciones heredadas.
- Inactividad suspendida mientras hay habla, procesamiento o reproduccion;
  huecos de entrada completados con silencio para que VAD cierre el turno.
- Cuota de intentos, aislamiento de bases, bloqueo entre procesos y contador
  detallado por modelo, modalidad, cache y transcripcion.

La revision independiente encontro carreras de generacion/cierre, finalizacion
durable sin reintento, historia incompleta, inactividad y aislamiento de tests.
Se corrigieron y se agregaron regresiones especificas antes de la suite final.

## OpenAI real y WebRTC en la Pi

`scripts/probe_realtime_voice.py` inicio un backend/base/token temporales. Un peer
envio una entrada hablada conocida y recibio el saludo y una respuesta generada.

| Medida observada | Resultado |
| --- | --- |
| Turnos de audio de entrada / transcripciones | 1 / 1 |
| Transcripciones de salida del modelo | 2 |
| Frames recibidos no silenciosos | 620 |
| EOF de muestra -> primer audio de respuesta recibido | 1708 ms |
| Tokens de entrada / salida / transcripcion | 2389 / 448 / 65 |
| Tiempo total de pared | 26.710 s |
| Pico de audio en cola | 8430 ms |
| Recursos liberados | Si |

La latencia usa el final del archivo sintetico, no una medicion perceptual del
fin de habla humana. Es una observacion puntual, no p50/p95 ni un SLA.

La prueba real detecto que la salida se genera mas rapido que se emite. El limite
inicial de 8 s era insuficiente: la salida ahora admite hasta 30 s PCM (1.44 MB),
mantiene reloj de emision y vacia inmediatamente el audio pendiente al interrumpir.

## Chrome en el Mac -> Pi -> OpenAI, con herramienta

`scripts/verify_realtime_browser.py` utilizo el HTML real y
`assets/voice-availability-sample.wav`: «Hola, ¿que horarios disponibles tienes
para mañana?» Se envio el archivo desde Chrome despues del saludo del modelo.

| Resultado final | Observado |
| --- | --- |
| Contexto seguro y HTTP/token | Correctos |
| Peer remoto pertenece a la Pi | Comprobado |
| Modelo | `gpt-realtime-2.1` |
| Turnos de voz / solicitudes de herramientas | 1 / 1 |
| Herramienta | Consulta de disponibilidad sobre agenda falsa |
| Paquetes / bytes recibidos en Chrome | 1280 / 192268 |
| Reproductor | `paused=false`, `currentTime=25.681251 s` |
| Tokens de entrada / salida / transcripcion | 4454 / 637 / 52 |
| Colgar y liberar recursos | Correcto |
| Errores JavaScript | 0 |

El navegador detecto otra diferencia de transporte: al acabar una muestra pueden
dejar de llegar frames, sin un tramo explicito de silencio. El puente completa
huecos de 100 ms con PCM silencioso; asi VAD consolida el turno. La prueba final
paso tras corregirlo y tras exigir drenaje de toda la respuesta.

Se repitio tambien el verificador del saludo fijo desde Chrome/Mac: 278 paquetes,
60514 bytes, reproduccion, cancelacion de permiso tardio, respuesta HTTP obsoleta,
doble Colgar, reintento DELETE 503, desconexion y SIGTERM correctos; cero errores JS.

## Reproduccion

Tras sincronizar el checkout, desde la raiz del mirror:

```sh
~/.local/bin/uv sync --locked --extra audio --extra voice
.venv/bin/python -m unittest discover -s tests -v
# Prueba de pago acotada, sin dispositivos fisicos:
.venv/bin/python scripts/probe_realtime_voice.py
```

Para Chrome remoto dedicado con CDP en `127.0.0.1:9222`, desde el Mac:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8001:127.0.0.1:8001 \
  -R 127.0.0.1:9223:127.0.0.1:9222 asaek@192.168.1.12
```

Desde la Pi, con el puerto de laboratorio libre:

```sh
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_realtime_browser.py \
  --cdp-url http://127.0.0.1:9223 --port 8001
```

`--expected-peer` acepta las direcciones verificadas de la Pi, separadas por comas.
Los scripts reales consumen API y cierran su backend temporal. Sus cuotas son por
base temporal, no una cuota monetaria global. Presupuesto de referencia: 5 USD;
se informa uso observado por modelo/modalidad y no se inventa un costo facturado
con datos parciales. La transcripcion de entrada se contabiliza aparte.

## Pendiente y frontera

- Probar microfono y altavoces fisicos en una conversacion humana, incluidas
  interrupciones espontaneas y calidad percibida en español.
- Medir distribuciones de latencia y costo por tarea, no solo una muestra.
- Comprobar preguntas/confirmaciones con el modelo real sobre mas escenarios;
  su logica se verifico con dobles y agenda falsa, no con Google ni Meta.
- Completar C4 para continuidad/entregas del paciente operativo y C5 para Calling.
