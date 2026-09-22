# 011 - Notificaciones al doctor

## Estado

Aprobado en alcance funcional. Pendiente de implementacion y verificacion.

## Objetivo

Enviar al doctor una notificacion interna cuando una cita del paciente de prueba
sea agendada, modificada o cancelada desde la conversacion de WhatsApp.

Cada evento debe producir un unico mensaje para el doctor. El resumen de la
conversacion es contenido obligatorio de ese mensaje y no tiene un disparador
independiente.

## Alcance

La funcionalidad cubre:

- Notificacion de una cita agendada correctamente.
- Notificacion de una cita modificada correctamente.
- Notificacion de una cita cancelada correctamente.
- Resumen de la conversacion asociado a cada una de las tres notificaciones.
- Senales de prioridad detectadas en la conversacion, cuando existan.
- Registro del resultado de la entrega al doctor.
- Proteccion contra notificaciones duplicadas por reintentos del webhook.

La modificacion de una cita corresponde inicialmente a una operacion exitosa de
`reschedule_appointment`.

## Requisitos funcionales

### RF-1101 - Destinatario configurado

El destinatario del doctor debe ser resuelto por el backend mediante configuracion
del entorno. El LLM, el paciente y el contenido de la conversacion no pueden elegir
ni modificar ese destinatario.

### RF-1102 - Eventos que generan notificacion

El backend debe generar una notificacion solamente despues de confirmar una de
estas operaciones:

- `create_appointment`.
- `reschedule_appointment`.
- `cancel_appointment`.

Una operacion rechazada, fallida o no confirmada no debe producir una notificacion
de exito para el doctor.

### RF-1103 - Un mensaje por evento

Cada operacion confirmada debe generar como maximo un mensaje para el doctor. Un
reintento del mismo evento no debe crear otro mensaje.

### RF-1104 - Contenido del mensaje

Cada mensaje debe incluir, como minimo:

- Tipo de evento: cita agendada, modificada o cancelada.
- Fecha, hora, zona horaria, motivo y estado de la cita.
- Nombre del paciente cuando este disponible y su numero de telefono.
- Resumen de la conversacion del paciente.
- Senales de prioridad, si fueron detectadas.

El mensaje no debe incluir identificadores internos de SQLite, IDs de Google
Calendar ni credenciales.

### RF-1105 - Resumen conversacional

El resumen debe construirse con la informacion persistida de la conversacion y
debe conservar los datos relevantes para la atencion del doctor. No debe presentar
un diagnostico, una recomendacion clinica ni una transcripcion completa como si
fuera una nota clinica.

El resumen se genera como parte de la notificacion del evento de cita. No se envia
un resumen despues de cada mensaje ni se crea una notificacion independiente de
resumen.

### RF-1106 - Aislamiento de la respuesta al paciente

Un fallo al construir, persistir o enviar la notificacion al doctor no debe
convertir en fallida una cita ya confirmada ni impedir que el paciente reciba la
respuesta conversacional. El fallo debe quedar registrado para su observacion o
reintento.

### RF-1107 - Estado de entrega

El backend debe conservar si la notificacion esta pendiente, en envio, enviada o
fallida. Cuando el proveedor devuelva un identificador, debe conservarse junto con
el resultado de la entrega.

### RF-1108 - Idempotencia

La notificacion debe relacionarse con una identidad estable del evento de agenda.
El reenvio del webhook o la repeticion del ciclo de respuesta no debe enviar dos
veces la misma notificacion al doctor.

### RF-1109 - Configuracion segura

La funcionalidad debe poder permanecer deshabilitada durante el desarrollo. Cuando
se habilite, el backend debe validar que exista un destinatario configurado y no
debe guardar credenciales en la base ni en el repositorio.

## Criterios de aceptacion

1. Una cita creada correctamente produce una notificacion de agendamiento con el
   resumen conversacional.
2. Una cita reprogramada correctamente produce una notificacion de modificacion
   con la nueva fecha y hora.
3. Una cita cancelada correctamente produce una notificacion de cancelacion y
   conserva los datos historicos de la cita.
4. Una operacion de agenda fallida no produce una notificacion enviada como exitosa.
5. Cada mensaje contiene el tipo de evento, los datos de la cita, el paciente, el
   telefono, el resumen y las senales de prioridad disponibles.
6. Un webhook duplicado no envia dos notificaciones para el mismo evento.
7. Un fallo de WhatsApp para el doctor no impide registrar y responder la
   conversacion del paciente.
8. Los estados y errores de entrega pueden consultarse en la persistencia local.
9. Las pruebas usan dobles locales y no requieren enviar mensajes reales.
10. La suite completa se ejecuta en el mirror de Raspberry Pi despues de
    sincronizar los cambios locales.

## Fuera del alcance

- Enviar un resumen independiente despues de cada mensaje.
- Disparar notificaciones por cierre automatico o inactividad de la conversacion.
- Canales para el doctor distintos de WhatsApp Cloud API.
- Un sistema de colas distribuido o multiples trabajadores.
- Uso con pacientes reales antes de definir privacidad, consentimiento y limites
  para informacion medica.
