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

## Corte 4 - Interpretacion de respuestas naturales

- [x] Aceptar respuestas afirmativas y negativas claras con palabras de cortesia.
- [x] Mantener las respuestas contradictorias o inciertas en estado ambiguo.
- [x] Verificar `Si, por favor` de extremo a extremo en una reprogramacion.
- [x] Ejecutar la suite completa en Raspberry Pi (210 pruebas).

## Corte 5 - Resolucion previa de la cita

- [x] No pedir confirmacion si la cita no se encuentra en el alcance del paciente.
- [x] Distinguir una cita ausente de un fallo temporal al leer la agenda.
- [x] Mostrar el codigo de agenda solo al remitente autorizado en modo debug.
- [x] Verificar que los fallos de lectura no dejan una accion pendiente ni modifican citas.
- [x] Consultar y mostrar todos los horarios libres del dia destino antes de confirmar
      una reprogramacion.
- [x] Persistir los slots de reprogramacion y limitar la seleccion a horarios ofrecidos.
- [x] Confirmar unicamente la cita y el horario seleccionados por el paciente.
- [x] Verificar la seleccion y la reprogramacion en Raspberry Pi.
- [x] Mostrar disponibilidad del dia de la cita antes de preguntar por una hora destino.
- [x] Resolver la cita desde la lista recientemente mostrada y aclarar si hay varias.
- [x] Ejecutar la suite completa y verificar los endpoints en Raspberry Pi.
