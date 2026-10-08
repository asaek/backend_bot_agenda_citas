# Tareas - Enrutamiento de intencion con flujos pendientes

## Implementacion

- [x] Definir tipos de flujo pendiente e interrupcion.
- [x] Clasificar el mensaje nuevo antes de procesar los estados pendientes.
- [x] Limpiar los estados relacionados al abandonar o cambiar de tarea.
- [x] Mantener la aclaracion ambigua sin cambiar ni limpiar la agenda pendiente.
- [x] Priorizar el mensaje nuevo y descartar confirmaciones que ya no corresponden.
- [x] Reconocer selecciones completas con `agendame` sin reiniciar la reserva.
- [x] Persistir una gestion pausada y recuperar su paso despues de otro tema.
- [x] Incorporar el recordatorio de pausa al contexto del modelo y bloquear mutaciones.
- [x] Reconsultar disponibilidad vencida conservando el nombre de la misma reserva.
- [x] Generar confirmaciones nuevas al retomar cancelaciones o reprogramaciones.

## Pruebas y verificacion

- [x] Probar abandono de una reserva sin crear una cita.
- [x] Probar consulta de citas durante una seleccion de horario.
- [x] Probar aclaracion de `cancela` durante una reprogramacion pendiente.
- [x] Probar cambio explicito a cancelacion con confirmacion obligatoria.
- [x] Probar que un `Sí` tardio no ejecute una reprogramacion descartada.
- [x] Probar saludos y peticiones de olvidar el flujo pendiente.
- [x] Ejecutar la suite completa y verificar los endpoints en Raspberry Pi.

## Verificacion del incremento de pausa

- [x] Reproducir la perdida de estado de `agendame a las 11 am` antes de corregirla.
- [x] Probar pausa tras entregar nombre, reinicio e historial acotado.
- [x] Probar disponibilidad ocupada/vencida y conservacion del nombre.
- [x] Completar regresiones de abandono, confirmaciones inactivas y nuevas gestiones.
- [x] Ejecutar suite completa, revisar cambios y reiniciar/verificar el runtime.
