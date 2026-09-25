# Tareas - Confirmacion de cambios de citas

## Corte 1 - Estado pendiente

- [x] Definir la accion pendiente para cancelacion y reprogramacion.
- [x] Persistir la accion en el contexto de la conversacion.
- [x] Agregar expiracion de 10 minutos.

## Corte 2 - Ejecucion segura

- [x] Interceptar mutaciones destructivas antes del proveedor.
- [x] Ejecutar solo la accion almacenada despues de una confirmacion afirmativa.
- [x] Descartar la accion ante una respuesta negativa o vencida.
- [x] Conservar la emision de eventos solo para operaciones exitosas.

## Corte 3 - Verificacion

- [x] Probar cancelacion afirmada y rechazada.
- [x] Probar reprogramacion afirmada.
- [x] Probar el flujo completo del webhook con los mensajes de confirmacion.
- [x] Ejecutar la suite completa en la Raspberry Pi.
- [x] Mostrar fecha, horario y motivo en la confirmacion de cancelacion sin exponer
  el ID interno.
- [x] Obtener los datos mostrados mediante una consulta de solo lectura antes de
  guardar la accion pendiente.
