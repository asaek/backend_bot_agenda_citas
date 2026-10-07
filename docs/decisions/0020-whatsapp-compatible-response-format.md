# 0020 - Formato de respuestas compatible con WhatsApp

## Estado

Aceptada e implementada. Ampliada el 7 de octubre de 2026 para presentar las horas
de las listas en formato de 12 horas con AM/PM.

## Contexto

El proveedor LLM puede redactar una lista de citas como una tabla Markdown. Las
tablas no son una presentacion util para los mensajes de WhatsApp y pueden llegar
al paciente con separadores y columnas ilegibles. El prompt por si solo no ofrece
una garantia suficiente porque el proveedor puede ignorar o interpretar de forma
distinta la instruccion.

## Decision

`ConversationService` indica al LLM que nunca use tablas Markdown y que presente
varias citas como una lista simple con guiones. Antes de devolver el texto final,
`format_whatsapp_reply()` convierte las tablas Markdown reconocibles en elementos
de lista, descarta filas vacias y omite las columnas de ID interno.

Las listas de disponibilidad, citas y opciones de reprogramacion presentan cada
hora en formato `h:mm AM/PM`, sin cero inicial para la hora y con dos digitos para
los minutos. Cada extremo del intervalo lleva su propio periodo, por ejemplo
`11:30 AM a 12:00 PM`. Medianoche se muestra como `12:00 AM` y mediodia como
`12:00 PM`, sin depender del idioma o locale del servidor.

`format_patient_time()` se comparte entre las listas construidas por el backend.
El prompt solicita el mismo formato al LLM y `format_whatsapp_reply()` normaliza
los campos de horas de las listas reconocibles, incluidas las tablas convertidas,
sin reescribir horas que formen parte del motivo de consulta. La lectura del ultimo
listado admite AM/PM para conservar la identificacion de una cita al reprogramarla.

La respuesta normalizada es la que `main.py` envia y persiste en el historial. Las
fechas y horas estructuradas de las herramientas y del estado persistido siguen
siendo valores ISO con zona horaria; AM/PM es una regla de presentacion.

## Consecuencias

- Las listas de citas se leen correctamente en WhatsApp aunque el LLM produzca una tabla.
- El ID interno de una cita no se filtra por una tabla generada por el LLM.
- El formateador reconoce tablas Markdown con una fila separadora y campos de horario
  en listas; el motivo de consulta conserva su contenido.
- Las listas mantienen su zona horaria y permiten seleccionar horas como `3:00 PM`.
- El proveedor LLM sigue siendo responsable de redactar el contenido conversacional.

## Alternativas descartadas

- Confiar solamente en la instruccion del `SYSTEM_PROMPT`.
- Mantener las tablas y delegar su interpretacion a WhatsApp.
- Cambiar el contrato estructurado de `list_appointments` para resolver un problema de presentacion.
