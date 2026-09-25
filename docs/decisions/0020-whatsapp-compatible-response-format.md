# 0020 - Formato de respuestas compatible con WhatsApp

## Estado

Aceptada e implementada.

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

La respuesta normalizada es la que `main.py` envia y persiste en el historial. Las
respuestas que no son tablas y las solicitudes internas de herramientas conservan
su comportamiento actual.

## Consecuencias

- Las listas de citas se leen correctamente en WhatsApp aunque el LLM produzca una tabla.
- El ID interno de una cita no se filtra por una tabla generada por el LLM.
- El formateador reconoce tablas Markdown con una fila separadora; otros formatos no tabulares se conservan.
- El proveedor LLM sigue siendo responsable de redactar el contenido conversacional.

## Alternativas descartadas

- Confiar solamente en la instruccion del `SYSTEM_PROMPT`.
- Mantener las tablas y delegar su interpretacion a WhatsApp.
- Cambiar el contrato estructurado de `list_appointments` para resolver un problema de presentacion.
