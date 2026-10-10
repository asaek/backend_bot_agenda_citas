# Verificacion - Hora de reprogramacion no disponible

## Estado

9 de octubre de 2026. Implementado y verificado en Raspberry Pi.
Corresponde a RF-1610 de la especificacion 016.

## Reproduccion y causa

Se reprodujo el flujo con una cita a las 9 AM, disponibilidad a las 9:30 AM y
las 10 AM ocupadas. Tanto `Cambiala para las 10 am` como `a las 10` devolvian:

```text
No identifiqué una hora de la lista. Elige uno de los horarios ofrecidos
o dime si prefieres dejar tu cita como está.
```

La prueba `test_occupied_reschedule_selection_explains_unavailability_and_keeps_the_change`
fallo en ambas selecciones antes del cambio. Una comprobacion independiente confirmo
que el parser extraia `(10, 0)` y reconocia ambos mensajes como selecciones completas.
La cita y la gestion seguian presentes; el problema era que una seleccion sin
coincidencia unica recibia el mismo mensaje que una hora no reconocida.

## Comportamiento corregido

La respuesta para una hora valida sin disponibilidad ofrecida es:

```text
Ese horario ya está ocupado o no está disponible. Elige uno de los horarios
ofrecidos o dime si prefieres dejar tu cita como está.
```

La gestion conserva la lista y la cita original. Elegir despues las 9:30 AM pide
confirmacion; solamente una respuesta afirmativa modifica la cita y emite el evento.
No se hacen llamadas adicionales al LLM para las selecciones rechazadas.

`PendingAppointmentAvailability.matching_slots()` permite distinguir cero coincidencias
de una ambiguedad AM/PM. Si las 10 AM y las 10 PM aparecen en la lista, `a las 10`
pide indicar AM o PM, sin afirmar que este ocupado. Un mensaje sin hora valida,
como `a cualquier hora` o `a las 10:99`, conserva la aclaracion de hora no identificada.

## Pruebas

Se sincronizaron los cambios antes de ejecutar las comprobaciones en el mirror.
La suite de continuidad paso con 29 pruebas, incluidas las tres regresiones nuevas.
La compilacion de los modulos afectados paso. La suite completa se ejecuto desde
la raiz de `/home/asaek/Downloads/chatbot_test_repo`:

```text
DOCTOR_NOTIFICATIONS_ENABLED=false .venv/bin/python -m unittest discover -s tests
Ran 327 tests
OK
```

La desactivacion de notificaciones pertenece solo al proceso de pruebas; los casos
que necesitan notificaciones habilitan sus propios dobles. Se utilizaron SQLite
temporal y proveedores falsos, sin modificar citas reales ni enviar mensajes.

## Despliegue y rutas

Se copiaron proyecto y `.env` completo. La comparacion en memoria confirmo igualdad
byte a byte y modo `600`. Tras revisar unidades systemd, directorio, proceso y puerto,
se recargo el backend manual de PID `99274` a `117921`. La configuracion efectiva
coincidio con `.env` y la configuracion LLM fue valida. Ngrok permanecio activo con
PID `96317`.

Health `GET /` y webhook GET/POST devolvieron `200` y sus cuerpos esperados, tanto
localmente como a traves del tunel publico. Los POST usaron eventos vacios.
La consulta de solo lectura al recurso de telefono de Meta (`fields=id`) confirmo
autenticacion valida con `200`. No se imprimieron secretos ni hashes.
