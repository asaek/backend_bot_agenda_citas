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
