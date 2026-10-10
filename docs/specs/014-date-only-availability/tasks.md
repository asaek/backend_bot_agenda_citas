# Tareas - Horarios libres antes de elegir una cita

## Implementacion

- [x] Detectar una solicitud de agenda con dia y sin hora exacta.
- [x] Consultar `check_availability` para el dia completo.
- [x] Mostrar slots unicos sin exponer calendarios internos.
- [x] Persistir fecha, slots y expiracion despues de consultar disponibilidad.
- [x] Validar la seleccion del paciente contra los slots persistidos.
- [x] Transferir una seleccion valida al flujo backend de nombre y motivo sin LLM.
- [x] Mantener el flujo existente para solicitudes con hora.
- [x] Reforzar las instrucciones del LLM para casos no detectados.
- [x] Cubrir variantes frecuentes como `sacar cita` en el detector determinista.
- [x] Guardar la intencion de agendar sin fecha y resolver una respuesta relativa posterior
      directamente contra disponibilidad.

## Pruebas y verificacion

- [x] Probar una solicitud para manana sin invocar al LLM.
- [x] Probar que una hora exacta no entra en la ruta de disponibilidad general.
- [x] Probar la deduplicacion de horarios de varios calendarios.
- [x] Probar el texto real `y para hoy quisiera sacar cita que tienes para hoy` sin
      invocar al LLM.
- [x] Probar la persistencia y reconstruccion del estado de disponibilidad.
- [x] Probar `damela a las 10 am` y el transcript completo sin una segunda pregunta
      por el motivo ni una segunda cita.
- [x] Ejecutar la suite completa en la Raspberry Pi.
- [x] Verificar health check y ambos metodos del webhook en la Raspberry Pi.
- [x] Probar `Quisiera agendar una` seguido de `hoy` sin llamadas al LLM.

## Ampliacion - Listas en 12 horas con AM/PM

- [x] Compartir formato de 12 horas para disponibilidad y opciones de cita.
- [x] Mostrar AM/PM en ambos extremos y ajustar ejemplos de seleccion.
- [x] Actualizar las expectativas de las pruebas existentes de disponibilidad y reprogramacion.
- [x] Verificar mañana, mediodia, tarde, medianoche y seleccion con PM en Raspberry Pi.
- [x] Ejecutar suite completa, reiniciar backend y verificar las rutas HTTP.

Evidencia: `docs/verification/2026-10-07-twelve-hour-lists.md`.

## Ampliacion - Seleccion natural de una reserva

- [x] Reproducir `quisiera una cita a las 9 am` despues de la disponibilidad del lunes.
- [x] Conservar el dia y transferir la seleccion al flujo backend de nombre y motivo.
- [x] Ajustar la instruccion de la lista al flujo real y a reservas con nombre ya recibido.
- [x] Cubrir la fecha 12/10/2026, reinicios, nombre persistido y motivo original.
- [x] Completar revision, suite de 346 pruebas y verificaciones del runtime en
      Raspberry Pi; evidencia en `docs/verification/2026-10-10-booking-name-continuity.md`.

## Ampliacion - Puntuacion, cierres de seleccion y no disponibilidad

- [x] Reproducir las dos selecciones de las 10 AM despues de una cita a las 9 AM.
- [x] Aceptar puntuacion entre palabras y `esta bien`, conservando horas y AM/PM.
- [x] Distinguir no disponibilidad de una hora no reconocida o ambigua en reserva.
- [x] Conservar la lista activa/pausada y permitir una eleccion valida tras reiniciar.
- [x] Reproducir y corregir el hallazgo de revision: conservar el periodo en
      `10 de.la.noche` con solo 10 AM ofrecidas o ambos periodos, incluso tras una pausa.
- [x] Verificar el webhook hasta dos citas distintas y una notificacion por cita,
      incluso al reintentar el motivo de la segunda reserva.
- [x] Completar revision, suite de 353 pruebas y despliegue verificado en Raspberry Pi;
      evidencia en `docs/verification/2026-10-10-booking-slot-selection.md`.
