# Verificacion - Confirmacion contextual de cancelacion

## Fecha y alcance

11/10/2026. Implementacion de ADR 0049 en el checkout local y sincronizacion de
codigo, pruebas y SDD a `/home/asaek/Downloads/chatbot_test_repo` en Raspberry Pi.
La solicitud no incluye reemplazar `.env` ni reiniciar el backend activo. La
correccion esta verificada en procesos de prueba nuevos; no se declara activada
en el proceso Uvicorn existente.

No se modificaron citas reales, configuracion ni credenciales. Los escenarios
usan SQLite temporal, agenda y LLM simulados. Las comprobaciones HTTP usan
un evento vacio para no invocar el LLM ni enviar WhatsApp.

## Reproduccion antes de corregir

Con reloj fijo en 11/10/2026 y una cita del 12/10/2026 a las 9 AM, el replay de la
conversacion reprodujo las respuestas originales: la instruccion directa repetia
la confirmacion y `Si cancelala` preguntaba si se queria abandonar la operacion.
Ambos escenarios minimos fallaron con solo solicitar la cancelacion y confirmarla.

Primera regresion permanente ejecutada en rojo:

```text
.venv/bin/python -m unittest discover -s tests -p test_conversation_continuity.py -k reported_cancellation_accepts -v
Ran 1 test
FAILED (failures=1)
Esperado: Tu cita ha sido cancelada.
Recibido: ¿Quieres abandonar la operación pendiente ...?
```

Los ciclos siguientes reprodujeron y corrigieron instrucciones naturales,
contradicciones descartadas, respuestas durante una pausa, aclaracion de `cancela`
y negativas sin informacion explicita de la cita conservada.

La revision tambien reprodujo una autorizacion incorrecta para `Si, mañana`,
`Si, si es gratis` y `Si, pero...`. El reconocimiento completo y la eliminacion
del respaldo permisivo impiden ejecutar la accion por encontrar una afirmacion
aislada dentro de esas respuestas.

## Resultado final

Ejecutado sobre los archivos sincronizados, desde la raiz del mirror:

```text
.venv/bin/python -m unittest discover -s tests
Ran 370 tests in 23.246s
OK

.venv/bin/python -m compileall -q *.py tests
exit 0
```

Las regresiones cubren:

- `Si cancelala`, `Cancela la cita por favor`, `Si, quiero cancelar la cita`,
  `Si, cancelar` y cortesia; la accion se ejecuta una sola vez sin LLM.
- Recreacion del servicio con historial acotado y la cita exacta del reporte.
- Negativas y abandono conservando la cita y comunicando fecha/hora originales.
- Contradicciones y preguntas tentativas que permiten una confirmacion clara posterior.
- Condiciones, texto adicional y otra fecha sin autorizacion por coincidencia parcial.
- Otra cita con confirmacion nueva, sin cancelar la anterior.
- Pausa y expiracion sin reactivacion ni renovacion por una respuesta natural.
- Palabras de cancelacion que no autorizan una reprogramacion pendiente.
- Reintentos del webhook con `Si cancelala`: una sola pregunta, cancelacion y
  notificacion al doctor; el reintento viejo no reabre la gestion.
- Fragmentos repetidos con texto adicional sin mutacion.

El replay original completo ahora pasa: `Cancela la cita por favor` cancela al
primer permiso explicito y solo se emite un evento.

Una prueba de estres aislada encontro backtracking con quince repeticiones de
`no quiero cancelarla` y texto adicional (timeout de dos segundos). Se limito el
reconocimiento a ocho clausulas. Repetir la misma prueba con 5, 10 y 15 fragmentos
termino en 0.501-0.623 segundos, incluyendo el inicio/importacion del proceso.

La suite emite una advertencia preexistente de Starlette sobre su integracion con
`httpx`; no afecta los resultados ni se cambiaron dependencias para este corte.

## Rutas del backend existente

Comprobadas por HTTP contra `127.0.0.1:8000` en la Raspberry, sin mostrar el token:

| Ruta | Resultado |
| --- | --- |
| `GET /` | HTTP 200 y `{"status":"ok"}` |
| `GET /webhook/whatsapp` | HTTP 200 y el challenge esperado |
| `POST /webhook/whatsapp` con `entry: []` | HTTP 200 y `{"status":"ok"}` |

Estas comprobaciones verifican la salud del backend existente; no equivalen a
recargar la correccion en Uvicorn ni a verificar una cancelacion en Google real.
Para activarla en WhatsApp se requiere una recarga verificada del backend.

## Activacion posterior

La solicitud `local to raspberry` del 12/10/2026 activo la correccion con `.env`
completo y verificaciones locales, publicas y de Meta satisfactorias. Evidencia:
`2026-10-12-contextual-cancellation-deployment.md`.
