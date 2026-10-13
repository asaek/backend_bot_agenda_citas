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

## Corte 6 - Una confirmacion de cancelacion desde la primera pregunta

- [x] Reproducir el listado del lunes a las 10 y 12 y la segunda pregunta tras el primer `si por favor`.
- [x] Confirmar que la afirmacion se reconoce y la primera pregunta del LLM carecia de estado backend.
- [x] Resolver la cancelacion directa en agenda y guardar la accion antes de preguntar.
- [x] Filtrar fecha, hora, minutos y periodo sin elegir otra cita si la referencia no coincide.
- [x] Mantener la aclaracion de identidad para varios objetivos y las negativas sin mutacion.
- [x] Sustituir preguntas textuales reconocibles sin estado y bloquear afirmaciones aisladas del LLM.
- [x] Verificar reinicio, cancelacion de una sola cita y una notificacion en reintentos del webhook.
- [x] Completar revision directa, suite de 359 pruebas y compilacion en Raspberry Pi.
- [x] Sincronizar proyecto/configuracion y verificar recarga, igualdad de `.env`, modo 600 y rutas HTTP.
- [x] Actualizar el token local expirado y completar autenticacion de WhatsApp:
      Meta responde 200 el 11/10/2026 tras copiar y verificar el `.env` completo.

Evidencia: `docs/verification/2026-10-10-single-cancellation-confirmation.md`.

## Corte 7 - Confirmacion contextual sin bucles

- [x] Reproducir la conversacion reportada con agenda simulada en Raspberry Pi.
- [x] Probar primero `Si cancelala` y la instruccion directa despues de mostrar la cita.
- [x] Coordinar enrutamiento, resolucion y pausa con una clasificacion contextual completa.
- [x] Conservar contradicciones para aclaracion y rechazar condiciones o datos adicionales.
- [x] Mantener otra cita, otra operacion, pausa y expiracion fuera de la autorizacion anterior.
- [x] Separar abandono de solicitud y cancelacion; comunicar la cita aun agendada al rechazar.
- [x] Cubrir recreacion del servicio y una sola cancelacion/notificacion en reintentos del webhook.
- [x] Actualizar ADR, especificaciones, diseno, arquitectura y alcance.
- [x] Completar revision, suite final de 370 pruebas, compilacion y comprobaciones HTTP en Raspberry Pi.

Este corte sincroniza codigo, pruebas y documentacion; no solicita reemplazar `.env`
ni reiniciar el backend en ejecucion. Evidencia:
`docs/verification/2026-10-11-contextual-cancellation-confirmation.md`.

## Activacion del corte 7 - 12/10/2026

- [x] Ejecutar el `local to raspberry` solicitado, copiando el `.env` completo con modo 600.
- [x] Verificar igualdad byte por byte y configuracion efectiva sin mostrar secretos.
- [x] Activar Uvicorn y ngrok despues de confirmar que ambos estaban detenidos.
- [x] Verificar salud, ambos webhooks locales/publicos y autenticacion Meta con HTTP 200.
- [x] Ejecutar nuevamente las 370 pruebas en Raspberry Pi.

Evidencia: `docs/verification/2026-10-12-contextual-cancellation-deployment.md`.

## Corte 8 - Etapa 1: afirmaciones claras y aclaracion contextual de reprogramacion

- [x] Reproducir con agenda simulada el bucle de `Si es correcto` antes de corregirlo.
- [x] Reconocer las afirmaciones del plan con mayusculas, acentos y puntuacion.
- [x] Evitar que `Si, si esta bien` y condiciones similares autoricen la accion anterior.
- [x] Preguntar por el cambio guardado en vez de repetir solamente frases permitidas.
- [x] Verificar dudas, negativa, expiracion, reinicio y referencias a otras fechas/citas.
- [x] Verificar las tres afirmaciones y un unico cambio/notificacion ante duplicados del webhook.
- [x] Completar revision directa, suite de 377 pruebas y despliegue en Raspberry Pi;
      evidencia en `docs/verification/2026-10-12-natural-reschedule-stage-one.md`.

Esta etapa corresponde a los puntos 1 y 2 del plan aprobado. La unificacion general
de fechas, intervalos antes/despues y cierre con datos definitivos pertenece a la etapa 2.
