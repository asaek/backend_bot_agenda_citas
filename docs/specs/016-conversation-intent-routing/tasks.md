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

## Respuesta comprensible para una hora de reprogramacion no disponible

- [x] Reproducir el caso de cita a las 9 AM y seleccion de las 10 AM ocupadas.
- [x] Distinguir una hora reconocida sin disponibilidad de una hora no reconocida.
- [x] Conservar la lista, la cita original y la confirmacion obligatoria.
- [x] Cubrir falta de hora valida y ambiguedad AM/PM sin respuestas de ocupacion falsas.
- [x] Ejecutar las regresiones y la suite completa en Raspberry Pi: 327 pruebas correctas.
- [x] Sincronizar, recargar y verificar las rutas del backend; evidencia en
      `docs/verification/2026-10-09-unavailable-reschedule-time.md`.

## Seleccion natural de horarios de reprogramacion

- [x] Reproducir en Raspberry Pi el bucle de la cita de hoy a las 10 y seleccion de las 12 PM.
- [x] Confirmar que la hora se extrae bien y la frase se clasifica incorrectamente como nueva gestion.
- [x] Reconocer selecciones naturales, preferencias, peticiones corteses y puntuacion.
- [x] Aceptar expresiones de mediodia sin volver a iniciar la disponibilidad.
- [x] Aclarar `12 p,` y conservar la seleccion hasta recibir AM/PM completo.
- [x] Cubrir cambio confirmado, rechazo, reinicio, ocupacion, ambiguedad y enrutamiento de otra tarea.
- [x] Actualizar especificacion, diseno, arquitectura, alcance y ADR 0044.
- [x] Reproducir y corregir los hallazgos de revision: prioridad del flujo, saludo interrogativo,
      aclaracion pausada, nuevos verbos para otra tarea y ambiguedad medianoche/mediodia.
- [x] Completar revision y ejecutar la suite completa y compilacion en Raspberry Pi: 337 pruebas correctas.
- [x] Copiar configuracion completa y verificar igualdad byte a byte y modo 600.
- [x] Reiniciar el backend y verificar configuracion efectiva, salud y webhooks locales/publicos.
- [x] Completar autenticacion de WhatsApp: Meta devuelve 200 despues de actualizar el token local.
- [x] Registrar pruebas, despliegue y recuperacion de autenticacion en
      `docs/verification/2026-10-09-natural-reschedule-selection.md`.

## Seleccion natural de horarios para una reserva nueva

- [x] Reproducir la perdida del flujo al elegir `quisiera una cita a las 9 am`.
- [x] Ampliar las selecciones completas conservando la fecha de la disponibilidad.
- [x] Mantener otra cita/fecha, cancelacion, pregunta informativa y abandono fuera de la seleccion.
- [x] Verificar la conversacion completa con nombre unico, motivo y reinicios del servicio.
- [x] Reproducir y corregir el hallazgo de revision: alinear `deseo/me gustaria` para
      otra cita o fecha, incluyendo una disponibilidad pausada tras reiniciar.
- [x] Reproducir y corregir preguntas de costo con verbos de agenda conservando
      la reserva y su nombre aceptado durante una pausa y despues de reiniciar.
- [x] Completar revision, suite de 346 pruebas y despliegue verificado en Raspberry Pi;
      evidencia en `docs/verification/2026-10-10-booking-name-continuity.md`.
