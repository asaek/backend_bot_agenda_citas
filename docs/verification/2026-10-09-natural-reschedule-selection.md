# Verificacion - Seleccion natural de reprogramacion

## Estado

9 de octubre de 2026. Implementado, revisado y con suite completa verificada en
Raspberry Pi. Backend recargado, rutas y autenticacion de WhatsApp verificadas.
Despliegue completo tras actualizar la credencial local vencida.
Corresponde a RF-1611, RF-1612 y RF-1613 de la especificacion 016.

## Reproduccion y causa

La prueba `test_natural_reschedule_selection_confirms_the_listed_appointment_for_today`
fija el reloj en 09/10/2026 09:23 UTC, prepara una cita a las 10 con motivo `Veo oscuro`,
presenta esa cita y solicita modificarla. Elegir `quisiera cambiarla a las 12 pm`
fallo antes del cambio: la respuesta repetia la disponibilidad en lugar de confirmar.

```text
DOCTOR_NOTIFICATIONS_ENABLED=false .venv/bin/python -m unittest discover -s tests -p test_conversation_continuity.py -k natural_reschedule_selection -v
Ran 1 test
FAILED (failures=1)
```

Un sondeo de las funciones publicas mostro que `parse_time_selection()` devolvia
`(12, 0)`, pero el reconocimiento de seleccion era falso y el router devolvia `switch`.
Las variantes `cambiala a las 12 pm` y `12 pm` eran selecciones y devolvian `none`.
La causa fue el prefijo limitado: la expresion natural reiniciaba la gestion y
permitia que el agente volviera a ofrecer la lista. Tras corregirlo, la misma prueba
paso y verifico confirmacion, identidad, motivo, duracion y un unico evento.

## Cobertura incremental

- 31 expresiones numericas, imperativos, preferencias y peticiones corteses:
  23 de los 28 subcasos iniciales fallaron antes de ampliar el reconocimiento.
  La revision agrego peticiones con saludo/cortesia antes o despues de los signos de pregunta.
- Siete expresiones de mediodia: las cinco iniciales fallaron antes de ampliar la
  interpretacion; la revision agrego `elijo el horario de las 12 del dia` y
  `quisiera cambiarla 12 del dia` para proteger el orden de los resolvers.
- AM/PM incompleto: reproduccion en rojo de `12 p,`, `12 p.` y `12 a,`, seguida
  de aclaracion sin perder estado y correccion/confirmacion despues de reiniciar.
- Ocupacion, hora invalida y AM/PM ambiguo tambien se prueban con frases naturales.
- Otra cita, otra fecha, cancelacion, abandono y preguntas informativas conservan
  sus rutas; una pregunta tentativa no selecciona un horario automaticamente.
- Una seleccion natural retoma la disponibilidad pausada vigente tras reiniciar.
- El AM/PM incompleto se aclara deterministamente tambien durante una pausa.
- Con medianoche y mediodia libres, `a las 12` pide AM/PM antes de confirmar.

## Revision

Dos revisiones estaticas independientes (estandares y especificacion) encontraron
casos de prioridad de los resolvers, nuevas tareas con imperativos, signos de pregunta
despues de un saludo, aclaraciones durante pausa y ambiguedad de las 12.
Se reprodujeron en Raspberry Pi con nueve fallos antes de corregirlos. Los resolvers
pendientes ahora preceden a los detectores genericos, los verbos comparten patrones,
los wrappers interrogativos se normalizan y las aclaraciones pausadas usan el snapshot.
La hora 12 sin periodo considera ambos extremos del ciclo AM/PM.
La segunda revision agrego tres escenarios: `dejarla como esta` debe abandonar,
dejar el coche es una pregunta informativa y la cortesia despues de `?` no descarta
la seleccion. Cinco subcasos fallaron antes de ajustar estos patrones; quedaron
cubiertos por regresiones de continuidad.

Las pruebas usan SQLite temporal y proveedores falsos; los eventos se recolectan
en memoria. No utilizan citas reales ni envios externos.

## Pruebas finales

Tras sincronizar los cambios, la compilacion de los tres modulos afectados y sus
dos archivos de pruebas paso con `python -m py_compile`. Desde la raiz del mirror:

```text
DOCTOR_NOTIFICATIONS_ENABLED=false .venv/bin/python -m unittest discover -s tests
Ran 337 tests
OK
```

La configuracion de notificaciones desactivadas corresponde solo al proceso de
pruebas. Los casos que necesitan entrega usan sus propios dobles/configuracion.

## Sincronizacion y runtime

Se sincronizaron codigo y documentacion desde el checkout local. Se copio el `.env`
completo, se comparo byte a byte en memoria y se verifico modo `600` sin imprimir
valores ni hashes. Se revisaron unidades de servicio, proceso y puerto: el backend
seguia siendo manual. El proceso verificado de PID `119931` se recargo a `225532`
desde `/home/asaek/Downloads/chatbot_test_repo` con el comando estandar.
La configuracion efectiva coincidio con el archivo copiado y la configuracion LLM
fue valida. El tunel ngrok existente de PID `96317` permanecio activo.

| Comprobacion | Resultado |
| --- | --- |
| Health local `GET /` | 200, cuerpo esperado |
| Webhook local GET | 200, challenge esperado |
| Webhook local POST vacio | 200, cuerpo esperado |
| Health publico `GET /` | 200, cuerpo esperado |
| Webhook publico GET | 200, challenge esperado |
| Webhook publico POST vacio | 200, cuerpo esperado |
| Autenticacion Meta, recurso de telefono con `fields=id` | 200, cuerpo esperado en el cierre |

## Recuperacion de autenticacion y cierre

La primera comprobacion de Meta devolvio 401, codigo 190/subcodigo 463, por token
vencido. El usuario actualizo `WHATSAPP_ACCESS_TOKEN` en el `.env` local y confirmo
la actualizacion. Se volvio a copiar el archivo completo y se verificaron igualdad
byte a byte y modo `600` sin imprimir secretos.

El backend se recargo del PID `225532` al `394567` con configuracion efectiva
coincidente y configuracion LLM valida. Ngrok mantuvo el PID `96317`. Se repitieron
salud y ambos metodos del webhook local/publico: todos devolvieron 200 con el cuerpo
esperado. La consulta autenticada de solo lectura a Meta con `fields=id` devolvio
200 y la identidad esperada. El bloqueo quedo resuelto; no se enviaron mensajes
reales ni se modificaron citas reales durante estas comprobaciones.
