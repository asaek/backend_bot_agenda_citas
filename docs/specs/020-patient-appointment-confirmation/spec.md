# 020 - Confirmacion de cita para el paciente

## Estado

Implementado y verificado en Raspberry Pi con 392 pruebas correctas y runtime
recargado. Evidencia: `docs/verification/2026-10-14-patient-appointment-confirmation.md`.

## Objetivo y alcance

Presentar el resultado exitoso de agendar, reprogramar o cancelar una cita con los
bloques de cita y paciente usados en la notificacion del doctor. El usuario eligio
compartir solo esos datos: el resumen conversacional y las señales de prioridad
siguen siendo contenido interno del doctor.

## Requisitos

1. La respuesta posterior al exito contiene `CONFIRMACION DE CITA`, tipo de evento,
   `CITA` con fecha, hora de inicio, motivo y estado, y `PACIENTE` con nombre y telefono.
2. La fecha se muestra como `DD/MM/YYYY` y la hora solo como `h:mm AM/PM`, en la zona
   horaria de agenda. Se conserva el motivo y el nombre completo aceptado.
3. El telefono usa los ultimos 10 digitos, igual que el mensaje del doctor. Un nombre
   ausente se muestra como `No informado`, sin inventar identidad.
4. Se muestran los datos y el estado devueltos por la operacion exitosa: al reprogramar,
   el destino definitivo; al cancelar, la cita cancelada. Una pregunta previa,
   rechazo o fallo no muestra esta confirmacion de exito.
5. La confirmacion funciona con notificaciones al doctor deshabilitadas y no requiere
   una llamada de resumen ni otra generacion de texto con IA.
6. Los datos de cita y paciente se renderizan con una implementacion compartida para
   paciente y doctor. El doctor conserva su encabezado interno, fecha ISO, intervalo
   horario y contenido interno adicional.
7. Se conserva la entrega preparada e idempotente del webhook: un fallo de envio
   reutiliza la respuesta guardada sin repetir la mutacion ni duplicar notificaciones.
8. El nuevo formato cierra una gestion para delimitar el historial del resumidor;
   no deben heredarse sintomas de una cita anterior.

## Criterios de aceptacion

- `tengo vision borrosa` despues de nombre y horario produce los dos bloques con
  los datos persistidos del paciente y la cita confirmada.
- Cancelar y reprogramar despues de un `Si` explicito muestran evento y estado
  correctos, y la reprogramacion muestra la nueva fecha/hora.
- No aparecen resumen, prioridad, IDs de cita/calendario/herramienta ni encabezado
  interno en la respuesta al paciente.
- Se conserva la zona horaria, medianoche/mediodia, nombre completo y motivo.
- La notificacion del doctor conserva su formato y aislamiento ante fallos.
- Un reintento de la confirmacion ya preparada reenvia exactamente el cuerpo
  persistido, con una sola cita y una sola notificacion por doctor.
