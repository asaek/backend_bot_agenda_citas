# Consulta de hoy, reintentos y mensajes consecutivos

## Incidente y reproduccion

El 28/10/2026 el paciente de prueba recibio tres respuestas de fallo al pedir
una cita para hoy y repetir `Vuelve a intentarlo`. Una peticion posterior con
`Quiero agendar una cita para hoy` si mostro los horarios.

La lectura de SQLite en la Pi mostro que el saludo se respondio a las
16:46:01 UTC y la peticion siguiente se registro a las 16:46:03 UTC. No hubo
solapamiento en esos turnos ni fallos de transporte del LLM registrados.
No existe un registro historico de argumentos de herramientas para esos turnos;
la causa de la consulta se contrasto mediante reproduccion aislada.

La reproduccion con el proveedor LLM configurado, agenda falsa, base temporal y
reloj fijado a las 10:46 de America/Mexico_City produjo `check_availability`
desde `2026-10-28T00:00:00-06:00` hasta la medianoche siguiente. El ejecutor
rechazo el inicio pasado (`invalid_arguments`). Los reintentos reprodujeron
ese rango y la respuesta de no poder consultar hoy. En una de las respuestas
el modelo corrigio el inicio a las 10:46; esa salida tampoco coincidia con la
ruta backend de slots a la siguiente media hora y no persistia la seleccion.

La regresion determinista usa la llamada capturada con `FakeLLMProvider`,
`FakeCalendarProvider` y SQLite temporal. Antes de corregir, las tres pruebas
iniciales fallaron: consulta del dia via LLM, peticion con `quisiera` y reintento
tras fallo de calendario. La ultima devolvia una pregunta de fecha en lugar de
volver a consultar el dia solicitado.

## Correccion verificada

- Las peticiones corteses y `QUisiera una cita par ahoy` usan la ruta local.
- Una llamada del modelo para un dia completo se valida y usa el mismo rango,
  resultado, presentacion y persistencia que la ruta local. Hoy empieza en la
  siguiente media hora futura. Se mantienen los rechazos de fechas pasadas y
  argumentos desconocidos.
- Una consulta fallida conserva `target_date` opcional en el estado de fecha
  pendiente. Un reintento explicito vuelve a consultar ese dia durante su TTL
  de 10 minutos, tambien tras reiniciar o despues de varios fallos. Pausar y
  retomar conserva la fecha; un estado sin fecha o vencido no inventa un dia.
- La prueba HTTP bloquea el envio del saludo y recibe la solicitud y la
  seleccion mientras sigue pendiente. Al liberar el saludo, las respuestas
  salen en orden y la seleccion de las 11 AM solicita el nombre. No reserva
  una cita ni vuelve a llamar al modelo para consultar esos horarios.

## Ejecucion en Raspberry Pi

Codigo y documentacion editados en el Mac y sincronizados antes de ejecutar.
Desde `/home/asaek/Downloads/chatbot_test_repo`:

```text
.venv/bin/python -m unittest discover -s tests
Ran 596 tests in 93.046s
OK
```

Incluye 11 pruebas de `test_availability_recovery.py` y la nueva prueba de
mensajes consecutivos en `test_main.py`. La repeticion del transcript inicial
con el proveedor LLM configurado y agenda falsa devolvio saludo, lista desde
las 11 AM y pregunta fija de nombre.

Una comprobacion adicional con Google Calendar configurado, base temporal y
solo consulta devolvio 9 espacios futuros para hoy. No se crearon ni modificaron
citas y no se enviaron mensajes de WhatsApp desde esas comprobaciones.

## Despliegue y conectividad

- Proyecto sincronizado con exclusiones de Git, entornos, caches y datos.
- `.env` completo copiado; igualdad byte a byte comprobada sin mostrar valores,
  con modo `600`.
- No se encontro un servicio del proyecto en las unidades de sistema/usuario.
  Se verificaron proceso, puerto y directorio antes de reemplazar el listener
  Uvicorn. Primer reinicio verificado: PID `185147` a `187173`, puerto 8000 y
  directorio del mirror correctos. La configuracion efectiva coincide con `.env`.
- El proceso existente de ngrok se conservo.
- `GET /` local: HTTP 200 y `{"status":"ok"}`.
- `GET /webhook/whatsapp` local y publico: HTTP 200 y challenge esperado.
- `POST /webhook/whatsapp` local y publico, con evento vacio: HTTP 200 y
  `{"status":"ok"}`.
- GET autenticado de solo lectura al recurso telefonico configurado en Meta:
  HTTP 200 e identidad coincidente, sin exponer token ni IDs.

La comprobacion concurrente es automatizada mediante HTTP y transporte WhatsApp
falso; el transcript inicial se repitio de forma aislada. La recepcion y el orden
visibles en una nueva conversacion desde el telefono quedan como comprobacion
manual del paciente de prueba.
