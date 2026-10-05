# ADR 0038 - Diagnostico de errores limitado por modo y remitente

## Estado

Aceptada.

## Contexto

Durante el MVP tecnico, la respuesta generica protege los detalles internos, pero no
permite al desarrollador distinguir rapidamente errores del proveedor LLM mientras
depura conversaciones reales de prueba.

## Decision

Agregar `DEBUG_MODE`, apagado por defecto, y `DEBUG_WHATSAPP_NUMBERS`, una allowlist de
remitentes E.164. Solo cuando ambas condiciones se cumplen el webhook reemplaza la
respuesta generica por el nombre del proveedor, tipo de error y codigo HTTP disponible.
No se exponen mensajes crudos, cuerpos, encabezados, prompts ni credenciales.

## Consecuencias

- El modo estandar conserva la respuesta generica.
- Un remitente que no este en la allowlist nunca recibe detalles, aunque el modo este
  activo.
- Los fallos continuan guardandose en SQLite y registrandose con el tipo y codigo HTTP.
- La depuracion no añade llamadas al proveedor ni cambia el estado de una cita.
