# ADR 0023 - Motivo de cita controlado por el backend

## Estado

Aceptada.

## Contexto

La herramienta `create_appointment` necesita un motivo, pero un LLM puede completar
ese argumento aunque el paciente solo haya indicado un horario. Crear la cita en ese
primer turno puede guardar un motivo predeterminado o inventado y producir una
notificacion incorrecta al doctor.

## Decision

El backend interceptara toda solicitud de `create_appointment` que llegue desde el
agente, ignorara el `reason` propuesto por el LLM y guardara el horario como una
solicitud pendiente en `conversations.context_json`. El siguiente mensaje no vacio
del paciente sera el motivo que se enviara al `ToolExecutor`. La solicitud expirara
despues de 10 minutos.

## Consecuencias

- Ninguna cita se crea antes de que el paciente exprese un motivo.
- El paciente puede responder solo el motivo sin repetir el horario.
- El flujo agrega un turno conversacional para solicitudes sin motivo.
- Los eventos y notificaciones se mantienen vinculados a la creacion exitosa.
- La normalizacion del texto no clasifica ni interpreta clinicamente el motivo.
