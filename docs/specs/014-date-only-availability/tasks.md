# Tareas - Horarios libres antes de elegir una cita

## Implementacion

- [x] Detectar una solicitud de agenda con dia y sin hora exacta.
- [x] Consultar `check_availability` para el dia completo.
- [x] Mostrar slots unicos sin exponer calendarios internos.
- [x] Mantener el flujo existente para solicitudes con hora.
- [x] Reforzar las instrucciones del LLM para casos no detectados.
- [x] Cubrir variantes frecuentes como `sacar cita` en el detector determinista.

## Pruebas y verificacion

- [x] Probar una solicitud para manana sin invocar al LLM.
- [x] Probar que una hora exacta no entra en la ruta de disponibilidad general.
- [x] Probar la deduplicacion de horarios de varios calendarios.
- [x] Probar el texto real `y para hoy quisiera sacar cita que tienes para hoy` sin
      invocar al LLM.
- [x] Ejecutar la suite completa en la Raspberry Pi.
- [x] Verificar health check y ambos metodos del webhook en la Raspberry Pi.
