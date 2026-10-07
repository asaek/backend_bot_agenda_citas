# Tareas - Enrutamiento de intencion con flujos pendientes

## Implementacion

- [x] Definir tipos de flujo pendiente e interrupcion.
- [x] Clasificar el mensaje nuevo antes de procesar los estados pendientes.
- [x] Limpiar los estados relacionados al abandonar o cambiar de tarea.
- [x] Mantener la aclaracion ambigua sin cambiar ni limpiar la agenda pendiente.
- [x] Priorizar el mensaje nuevo y descartar confirmaciones que ya no corresponden.

## Pruebas y verificacion

- [x] Probar abandono de una reserva sin crear una cita.
- [x] Probar consulta de citas durante una seleccion de horario.
- [x] Probar aclaracion de `cancela` durante una reprogramacion pendiente.
- [x] Probar cambio explicito a cancelacion con confirmacion obligatoria.
- [x] Probar que un `Sí` tardio no ejecute una reprogramacion descartada.
- [x] Probar saludos y peticiones de olvidar el flujo pendiente.
- [x] Ejecutar la suite completa y verificar los endpoints en Raspberry Pi.
