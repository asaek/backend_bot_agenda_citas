# Tareas - Reintentos seguros de webhook

- [x] Reproducir el fallo antiguo y la doble generacion en pruebas integradas.
- [x] Agregar la bandeja de respuestas y la auditoria aditivas en SQLite.
- [x] Serializar turnos del paciente y reutilizar respuestas preparadas.
- [x] Excluir reintentos obsoletos y resultados inciertos.
- [x] Preservar eventos al doctor y acotar el historial al turno actual.
- [x] Actualizar ADR, arquitectura, alcance, README e indices del SDD.
- [x] Sincronizar y ejecutar regresiones y suite completa en la Raspberry (308 pruebas).
- [x] Recargar el backend y verificar configuracion, health y webhooks local/publico.
- [x] Verificar autenticacion de Meta con token vigente: HTTP 200 tras actualizar configuracion.

Evidencia: `../../verification/2026-10-08-safe-webhook-retries.md`.
Cierre de autenticacion: `../../verification/2026-10-08-local-to-raspberry-retry-auth-recovery.md`.
