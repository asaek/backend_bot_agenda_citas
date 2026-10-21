# Cliente WebRTC y red LAN - 2026-10-18

Estado: cliente y transporte LAN verificados automaticamente; captura/escucha
fisicas pendientes de comprobacion humana.

## Frontera comprobada

- Backend y driver Playwright ejecutados en el mirror de Raspberry Pi despues de
  sincronizar el checkout local; dependencias de audio del extra bloqueado.
- Cliente real `assets/lab-client.html` ejecutado en Google Chrome
  **155.0.8059.82 en la computadora macOS**, con perfil aislado y modo headless.
- Cliente/API en `http://127.0.0.1:8001` mediante reenvio SSH hacia la Pi.
  Contexto seguro comprobado; no se agregaron certificados, CORS ni otro servicio.
- Control CDP reenviado en sentido inverso por SSH, limitado a loopback. No se
  reutilizo el perfil personal de Chrome. El backend/token/base fueron temporales.
- Medios WebRTC directos con **Opus, candidatos host/host y UDP**, sin STUN/TURN.
  El candidato remoto seleccionado pertenece a `192.168.101.0/24`; Chrome oculta
  su direccion local en las estadisticas por privacidad/mDNS. La ruta del equipo
  hacia `192.168.101.19` usa la interfaz LAN `en0`, sin gateway de tunel.
- No se usaron Meta, STT, LLM, TTS de red ni el tunel HTTP de ngrok para el audio.

## Resultados

| Comprobacion | Resultado |
| --- | --- |
| GET `/lab/health` con token | HTTP 200, sin crear sesion ni medios |
| Sin token / token incorrecto | HTTP 401 |
| HTTP correcto con candidatos retirados en ambos SDP | Fallo de medios identificado; cero paquetes recibidos; recursos liberados |
| Contexto HTTP no confiable con microfono seleccionado | Error que indica HTTPS/localhost, sin adquirir microfono ni crear llamada |
| ICE / conexion en LAN | `connected` / `connected` |
| Pi recibe muestra de 440 Hz | 277 frames no silenciosos, 5.54 s, RMS PCM16 3479.8 |
| Pi emite saludo | 257 frames de fuente, 5.129 s |
| Chrome recibe saludo | 276 paquetes, 60 508 bytes |
| Reproduccion en Chrome | `paused=false`, `currentTime=5.691914 s` |
| Cierre, doble Colgar y reconexion | Correctos |
| Primer DELETE con HTTP 503 inyectado y posterior reintento | Correcto |
| Colgar/desconectar durante saludo y SIGTERM del backend | Recursos liberados y estado persistido |
| Permiso de microfono antiguo resuelto tras reconectar | No desconecta el reproductor nuevo |
| Health antiguo resuelto despues de reconectar | No sobrescribe el diagnostico HTTP de la llamada nueva |
| Estado de reproduccion despues de Colgar | `Sin audio`, sin conservar `Reproduciendo` |
| Errores JavaScript | 0 |

La secuencia inicial tambien paso en Chromium 154.0.8037.92 en la Pi. En esa
ejecucion se recibieron 285 paquetes y 60 535 bytes en el navegador; la Pi
decodifico 281 frames no silenciosos, 5.62 s.

Regresion final en la Pi: **405 tests correctos en 43.307 s**. La revision de
estandares y especificacion encontro dos diagnosticos tardios: respuesta HTTP de
una generacion cancelada y etiqueta de reproduccion despues de Colgar. Se
corrigieron y la secuencia LAN final reprodujo y verifico ambos casos. El indice
SDD tambien refleja ahora la ruta LAN comprobada.

## Reproduccion de la verificacion LAN

La ejecucion automatizada utiliza un navegador Chromium dedicado en la computadora
con CDP en loopback, politica de autoplay para la prueba y un perfil temporal.
Con el backend de laboratorio 8001 libre, se abren estos reenvios desde la computadora:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:8001:127.0.0.1:8001 \
  -R 127.0.0.1:9223:127.0.0.1:9222 asaek@192.168.101.19
```

Desde la raiz del mirror de la Pi:

```sh
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_browser.py \
  --cdp-url http://127.0.0.1:9223 --port 8001 --expected-lan 192.168.101.0/24
```

El driver inicia/cierra su propio backend y no imprime el token. La opcion
`--expected-lan` comprueba la direccion remota seleccionada y la local si Chrome
la expone; el resultado indica explicitamente cuando esta ultima queda oculta.
Para la prueba humana basta el tunel HTTP normal y el procedimiento del README;
no hace falta CDP ni el driver automatizado.

## Pendiente humano

- Escuchar fisicamente el saludo en los altavoces de la computadora.
- Conceder permiso al microfono real, hablar y comprobar que activa el saludo.

La prueba headless usa una muestra generada y acredita recepcion/reproduccion, no
captura fisica del microfono ni escucha humana. La evidencia de esta LAN no
garantiza conectividad desde otra red ni hacia Meta. No hay necesidad observada
de STUN/TURN para esta ruta; se evaluara al probar una ruta distinta que falle.
