# Verificacion - Mensajes conjuntos y complejos de reserva

Fecha: 28/10/2026. Referencias: RF-1319, ADR 0064 y corte 13 de spec 013.
Codigo y documentos editados localmente; todas las ejecuciones se realizaron en
la Raspberry Pi despues de sincronizar los cambios.

## Reproduccion roja

```sh
.venv/bin/python -m unittest discover -s tests -p test_booking_details_capture.py -k regression -v
```

Resultado inicial: **4 pruebas, 4 fallos**, en 0.304 s. Se reprodujo el rechazo
de `Asael Ponce Silva, el motivo de la cita es que tengo los ojos rojos`, con y
sin `Mi nombre es`, y dos mensajes complejos. Los primeros volvian a pedir
`Necesito tu nombre completo para continuar. ¿Cómo te llamas?`. Un saludo con
datos desviaba la respuesta hacia el agente en lugar de completar la captura.

La causa era el separador limitado a `motivo de la consulta`, la ausencia de
extraccion semantica de respaldo y la deteccion de pausas antes de identificar
los campos de un mensaje mixto. Las regresiones anteriores cubrian otra redaccion
(`el motivo es`) y no detectaban estas variantes.

## Correccion comprobada

- Separacion local de los motivos de consulta/cita/visita y preservacion de `que
  tengo los ojos rojos` como fragmento del paciente, separado del nombre.
- Respaldo semantico para explicaciones largas, presentaciones no estandar,
  saludos/peticiones de cortesia y campos en distinto orden.
- Esquema, confianza y evidencia literal validados antes de guardar los campos.
- Rechazo de nombre inventado, motivo resumido, campos superpuestos, negacion
  inmediata omitida, JSON invalido y confianza invalida/insuficiente.
- Fallo HTTP 429 registrado como tecnico, conservando horario y nombre previo.
- Continuidad tras reiniciar o reenviar el mismo mensaje, y confirmacion de un
  nombre inusual aunque haya sido extraido por el modelo.
- Abandonos y preguntas informativas reales conservan su enrutamiento.
- La captura activa y la entrada tardia a `create_appointment` comparten el interprete.

## Conversacion completa por webhook

`test_main.WebhookTests.test_reason_of_the_appointment_after_typo_slot_confirms_without_repeating_name`
fija el reloj al 28/10/2026 a las 10:04 y reproduce:

1. `QUisiera agendar una cita para hoy` -> disponibilidad del dia.
2. `a las 2 pm est abien` -> pregunta por el nombre.
3. `Asael Ponce Silva, el motivo de la cita es que tengo los ojos rojos` -> cita
   confirmada a las 2:00 PM, con nombre y motivo separados.
4. El mismo webhook final duplicado -> una sola cita, tres respuestas al paciente
   en total y un unico aviso al doctor con los datos correctos.

El transporte WhatsApp y el calendario de esta prueba son falsos.

## IA real en agenda aislada

Se probaron cinco variantes con el proveedor y evaluador estructurado configurados,
SQLite temporal y agenda falsa, sin enviar WhatsApp ni modificar Google Calendar:

1. La frase exacta `Asael Ponce Silva, el motivo de la cita es que tengo los ojos rojos`,
   incluyendo la seleccion previa con `est abien` interpretada por el LLM real.
2. La misma frase con `Mi nombre es`.
3. `Para registrarme, puede poner Asael Ponce Silva. Tengo los ojos rojos desde ayer
   y quisiera que el doctor revise mis estudios.`
4. `Hola, ¿me puedes registrar como Asael Ponce Silva? tengo los ojos rojos desde ayer`.
5. `Me preocupa que desde ayer tengo los ojos rojos, por favor regístrame como Asael Ponce Silva`.

Resultado: **5/5 correctas**. En todos los casos se verificaron nombre completo,
motivo completo literal, horario de las 2 PM, una cita, un evento y confirmacion.
Solo se tolero presencia/ausencia del punto final al comparar la explicacion;
no se permitieron resumenes ni omisiones de contenido.

## Suite completa

```sh
.venv/bin/python -m unittest discover -s tests
```

Resultado: **584 pruebas correctas**, en 91.239 s. Son 13 pruebas nuevas respecto
al corte anterior; la suite de captura contiene 28 pruebas. Tambien pasaron las
15 pruebas de captura del nombre y las 78 de continuidad conversacional.
La suite conserva advertencias de dependencias/recursos y mensajes de fallos
inyectados; termina en `OK`. `git diff --check` no informa errores.

## Despliegue

- Codigo, pruebas y SDD sincronizados al mirror, sin transferir Git, entornos,
  caches ni datos de pacientes.
- `.env` completo transferido; igualdad byte por byte comprobada en memoria,
  permisos `600` y configuracion efectiva del listener nuevo igual al archivo.
- Inspeccion de servicios del sistema/usuario, puerto, PID, comando y directorio
  antes del reinicio manual. Registro de recarga verificada: `182332 -> 184092`;
  el listener nuevo es propietario de `127.0.0.1:8000` y usa la raiz del proyecto.
- Tunel ngrok existente conservado (PID `167687`).
- `GET /` local: HTTP 200 con `{"status":"ok"}`.
- GET de verificacion del webhook, local y publico: HTTP 200 con el challenge esperado.
- POST del webhook con evento vacio, local y publico: HTTP 200 con `{"status":"ok"}`.
- Autenticacion WhatsApp, GET de solo lectura al recurso del telefono con
  `fields=id`: HTTP 200.

Los secretos usados por `curl` se transmitieron en stdin, sin imprimirlos ni
incluirlos en argumentos. No se añadieron logs de depuracion al codigo ni commits.
