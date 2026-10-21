# Reserva tras una pregunta interrumpida — 2026-10-20

## Evidencia y causa

Se reviso en modo lectura la llamada reportada de 15:14–15:16 UTC en la SQLite
exclusiva de voz de la Raspberry. Nombre y motivo habian sido recibidos; la
herramienta preparo correctamente una propuesta. La pregunta literal genero
12000 ms y emitio 11700 ms antes de interrumpirse. La accion quedo `invalidated`.
El intento posterior de confirmar devolvio:

```text
{"ok": false, "error": "No hay una propuesta vigente en esta llamada"}
```

La sesion no registro fallo de proveedor. Las hipotesis contrastadas fueron
descarte de propuesta por interrupcion, desfase del turno y limite de duracion.
El reproducer minimo falla sin agotar tiempo ni introducir turnos intermedios:
`VoiceTools.interrupt` descartaba la propuesta sin conservar una ruta de nueva
confirmacion. El contrato CA-11 ya exigia volver a preguntar ante ese caso.
No se copian transcripciones, datos personales ni credenciales en esta evidencia.

## Reproduccion y correccion

Desde la raiz del mirror, en la Pi:

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice_session.py \
  -k confirmation_after_interrupted -v
```

Antes del cambio: **1 fallo**, con el mismo error de propuesta inexistente.
Tras el cambio, el mismo escenario conserva los datos, devuelve otra pregunta
con otro ID, no reserva ante el primer intento y crea exactamente una cita
despues de emitir completa la pregunta nueva y recibir otra afirmacion.

La propuesta interrumpida se conserva aparte de una autorizacion vigente. La
recuperacion requiere su ID, llamada y canal originales, revalida los datos y la
agenda y vuelve a preparar la accion. Rechazo, correccion, nueva gestion y cierre
descartan esa recuperacion local. El traspaso entre canales sigue siendo explicito.

## Verificacion

- Pruebas focalizadas de voz: **37 correctas en 9.244 s**, sin consumir APIs.
- Se cubre respuesta repetida tras otro turno interrumpido, ID/canal ajenos,
  rechazo/correccion/nueva gestion y horario ocupado antes de renovar la pregunta.
- Regresion completa: **458 tests correctos en 64.263 s** en la Pi.
- `scripts/verify_lab_controls.py`: Chromium/WebRTC reales con Realtime falso,
  conexion sin token, historial voz/texto, reintento sin duplicar tras perder la
  respuesta y contexto despues de colgar; cero errores JavaScript/APIs externas.

## Despliegue y comprobaciones

Se sincronizaron los cambios locales de codigo, pruebas y SDD al mirror. El
dry-run con checksum de los archivos de esta correccion no mostro diferencias.
Se transfirio el `.env` completo: comparacion byte a byte en memoria correcta,
modo `600` y entorno efectivo de ambos procesos coincidente, sin imprimir valores.
No habia sesiones activas al recargar ni unidades systemd del proyecto.

| Proceso | PID previo | PID nuevo |
| --- | --- | --- |
| Backend de texto, loopback 8000 | 257324 | 270424 |
| Laboratorio Realtime, loopback 8001 | 257384 | 270508 |

Solo se terminaron los PID verificados mediante puerto, argumentos y directorio
del mirror. Se conservaron ngrok PID 22863 y forwarding Mac PID 8546.

| Comprobacion | Resultado |
| --- | --- |
| `GET /` local | 200, `{"status":"ok"}` |
| `GET /webhook/whatsapp` local y publico | 200, challenge correcto |
| `POST /webhook/whatsapp` vacio, local y publico | 200, `{"status":"ok"}` |
| `GET /lab/health`, Pi y Mac | 200, laboratorio Realtime |
| `GET /lab/history` | 200, historial disponible |
| `GET /lab` desde Mac | 200 mediante `http://localhost:8001/lab` |
| Graph v23.0, GET de solo lectura con `fields=id` | 401, codigo 190/subcodigo 463 |

El token de envio WhatsApp esta vencido, igual que en la evidencia previa. Ese
ramal no queda autenticado/verificado para envios hasta renovar la credencial;
el laboratorio y la correccion de confirmacion no dependen de ese token.
La regresion de la reserva usa eventos/proveedores de prueba y la agenda falsa;
no crea una cita operativa ni acredita una nueva conversacion humana con el modelo.
