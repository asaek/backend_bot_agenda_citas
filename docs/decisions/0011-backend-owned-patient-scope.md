# 0011 - Alcance del paciente resuelto por el backend

## Estado

Aceptada e implementada en el flujo de recepcion de WhatsApp.

## Contexto

Las herramientas de agenda necesitan conocer al paciente y la conversacion
actuales, pero esos valores identifican el alcance de datos y no son una
preferencia conversacional. El LLM no debe poder elegirlos ni sustituirlos.

## Decision

`ConversationService.receive_message()` resuelve el paciente usando el `from`
del mensaje de WhatsApp, obtiene o crea su conversacion activa y construye un
`PatientScope` inmutable con `patient_id`, `conversation_id` y
`whatsapp_number`. `ConversationContext` transporta ese objeto hacia las capas
posteriores.

El LLM continua recibiendo solamente mensajes conversacionales. Cuando se
integre el tool calling, el backend enriquecera la solicitud con el
`PatientScope` y los argumentos del LLM no podran incluir esos campos.

## Consecuencias

- La identidad usada por agenda queda vinculada al evento de WhatsApp recibido.
- Los webhooks duplicados reconstruyen el mismo alcance desde SQLite.
- El LLM no puede leer un identificador enviado por si mismo ni cambiar el
  paciente objetivo.
- La integracion de herramientas puede usar el contexto sin modificar el
  contrato conversacional del proveedor LLM.

## Alternativas descartadas

- Pedir al LLM `patient_id`, `conversation_id` o `whatsapp_number`.
- Inferir el paciente a partir del texto libre del mensaje.
- Construir el alcance en `main.py` despues de que el LLM solicite una
  herramienta.
