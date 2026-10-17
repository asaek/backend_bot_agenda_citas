# 0053 - Bloques compartidos de cita y paciente en confirmaciones

## Estado

Aceptada e implementada el 14 de octubre de 2026.

## Contexto

El usuario solicito que la confirmacion al paciente se parezca a la notificacion
del doctor y que el codigo del formato sea reutilizable. Aclaro que el paciente
debe recibir solo cita y paciente. El resumen y las señales de prioridad son internos.
ADR 0052 ya exige solo hora de inicio con AM/PM para el paciente; el mensaje del
doctor tiene un contrato de fecha ISO e intervalo horario.

## Decision

Extraer un renderizador determinista con dos audiencias. Comparte etiquetas,
estructura, estado, nombre y telefono de los bloques, con presentacion temporal y
encabezado propios de cada audiencia. La confirmacion usa el resultado definitivo
de la herramienta y el nombre persistido, sin una generacion adicional con IA.

El compositor del doctor sigue saneando su contenido y agrega resumen/prioridad
despues del bloque compartido. La confirmacion se prepara y persiste con el flujo
existente de reintentos antes de notificar al doctor.

## Consecuencias

- Cambiar una etiqueta o estructura comun se resuelve en un solo modulo.
- La confirmacion al paciente funciona aunque el resumen o la entrega al doctor fallen.
- Fecha/hora y estado provienen del resultado real; no se reconstruyen desde el historial.
- El resumidor debe reconocer tambien el nuevo encabezado de cierre para no
  heredar sintomas de gestiones anteriores.
