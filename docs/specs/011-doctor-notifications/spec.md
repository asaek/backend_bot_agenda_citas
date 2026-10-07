# 011 - Notificaciones al doctor

## Estado

Verificado. Los cortes 1 a 5 estan implementados y el corte 6 fue cerrado con la
suite local, la suite de Raspberry Pi y la verificacion HTTP documentadas en
`docs/verification/2026-09-22-doctor-notifications-webhook.md`. La entrega al doctor
se ejecuta desde el webhook despues de confirmar la respuesta al paciente.

## Objetivo

Enviar a los doctores configurados una notificacion interna cuando una cita del
paciente de prueba sea agendada, modificada o cancelada desde la conversacion de
WhatsApp.

Cada evento debe producir un unico mensaje para cada doctor configurado. Todos los
destinatarios reciben el mismo contenido. El resumen de la conversacion es
contenido obligatorio de ese mensaje y no tiene un disparador independiente.

## Alcance

La funcionalidad cubre:

- Notificacion de una cita agendada correctamente.
- Notificacion de una cita modificada correctamente.
- Notificacion de una cita cancelada correctamente.
- Resumen de la conversacion asociado a cada una de las tres notificaciones.
- Senales de prioridad detectadas en la conversacion, cuando existan.
- Registro del resultado de cada entrega a cada doctor.
- Proteccion contra notificaciones duplicadas por reintentos del webhook.

La modificacion de una cita corresponde inicialmente a una operacion exitosa de
`reschedule_appointment`.

## Requisitos funcionales

### RF-1101 - Destinatarios configurados

Uno o varios destinatarios deben ser resueltos por el backend mediante configuracion
del entorno. El LLM, el paciente y el contenido de la conversacion no pueden elegir
ni modificar esos destinatarios.

Los destinatarios deben ser validos, no repetirse y conservar el formato de numero
de WhatsApp aceptado por el canal.

### RF-1102 - Eventos que generan notificacion

El backend debe generar una notificacion solamente despues de confirmar una de
estas operaciones:

- `create_appointment`.
- `reschedule_appointment`.
- `cancel_appointment`.

Una operacion rechazada, fallida o no confirmada no debe producir una notificacion
de exito para el doctor.

### RF-1103 - Un mensaje por destinatario y evento

Cada operacion confirmada debe generar como maximo un mensaje para cada doctor
configurado. Un reintento del mismo evento no debe crear otro mensaje para el mismo
destinatario.

### RF-1104 - Contenido del mensaje

Cada mensaje debe incluir, como minimo:

- Tipo de evento: cita agendada, modificada o cancelada.
- Fecha, hora, motivo y estado de la cita.
- Nombre del paciente cuando este disponible y su numero de telefono mostrado con
  sus ultimos 10 digitos.
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

### RF-1110 - Prioridad razonada con evidencia de la gestion actual

La composicion debe interpretar el motivo y los mensajes del paciente de la gestion
actual, incluyendo sinonimos, errores de escritura, intensidad e inicio de los sintomas.
El motivo final no tiene que repetir todos los sintomas del historial. La interpretacion
del LLM usa codigos del catalogo compartido y `priority_signal_evidence` con objetos
`{signal, quote}`; el backend exige evidencia literal del paciente sin exigir ademas
coincidencia con palabras clave. El respaldo local se conserva si el modelo omite señales.

La secrecion ocular amarillenta, verdosa o abundante, incluido el motivo
`Tengo laga;as muy amarillentas y grandes en los ojos`, debe producir `ocular_discharge`
y su descripcion aprobada. Pocas lagañas al despertar, una revision rutinaria o sintomas
negados no deben forzar una señal. Una negacion posterior explicita del mismo sintoma
debe actualizar el respaldo local.

El historial se acota al evento actual y se separa en el ultimo evento anterior
persistido o respuesta fija de exito del backend. No se heredan sintomas de citas
anteriores, ni se acepta como evidencia texto del asistente, de otro paciente o de
mensajes posteriores al evento. Las citas literales son datos de validacion, no una
transcripcion agregada a la notificacion.

### RF-1106 - Aislamiento de la respuesta al paciente

Un fallo al construir, persistir o enviar una notificacion no debe convertir en
fallida una cita ya confirmada ni impedir que el paciente reciba la respuesta
conversacional. Un fallo para un doctor no debe impedir el intento de entrega a los
demas. Cada fallo debe quedar registrado para su observacion o reintento.

### RF-1107 - Estado de entrega

El backend debe conservar, por destinatario, si la notificacion esta pendiente, en
envio, enviada o fallida. Cuando el proveedor devuelva un identificador, debe
conservarse junto con el resultado de esa entrega.

### RF-1108 - Idempotencia

Cada entrega debe relacionarse con una identidad estable del evento de agenda y con
su destinatario. El reenvio del webhook o la repeticion del ciclo de respuesta no
debe enviar dos veces la misma notificacion al mismo doctor.

### RF-1109 - Configuracion segura

La funcionalidad debe poder permanecer deshabilitada durante el desarrollo. Cuando
se habilite, el backend debe validar que exista al menos un destinatario configurado
y no debe guardar credenciales en la base ni en el repositorio.

## Criterios de aceptacion

1. Una cita creada correctamente produce una notificacion de agendamiento con el
   resumen conversacional para cada doctor configurado.
2. Una cita reprogramada correctamente produce una notificacion de modificacion
   con la nueva fecha y hora.
3. Una cita cancelada correctamente produce una notificacion de cancelacion y
   conserva los datos historicos de la cita.
4. Una operacion de agenda fallida no produce una notificacion enviada como exitosa.
5. Cada mensaje contiene el tipo de evento, los datos de la cita, el paciente, el
   telefono, el resumen y las senales de prioridad disponibles.
6. Todos los doctores configurados reciben como maximo una copia por evento.
7. Un webhook duplicado no envia dos notificaciones al mismo doctor para el mismo
   evento.
8. Un fallo de WhatsApp para un doctor no impide intentar la entrega a los demas ni
   registrar y responder la conversacion del paciente.
9. Los estados y errores de entrega pueden consultarse por destinatario en la
   persistencia local.
10. Las pruebas usan dobles locales y no requieren enviar mensajes reales.
11. La suite completa se ejecuta en el mirror de Raspberry Pi despues de
    sincronizar los cambios locales.
12. El ejemplo de lagañas amarillentas y grandes incluye la descripcion aprobada de
    secrecion ocular y no muestra `Ninguna detectada` aunque el LLM omita la señal.
13. Una dificultad visual descrita sin las palabras clave de las reglas puede conservar
    `sudden_vision_loss` cuando el LLM aporta evidencia literal del motivo o historial actual.
14. Un motivo rutinario puede incorporar un sintoma del historial actual; evidencia
    inventada, negada, de una cita anterior, del asistente o posterior al evento se descarta.

## Fuera del alcance

- Enviar un resumen independiente despues de cada mensaje.
- Disparar notificaciones por cierre automatico o inactividad de la conversacion.
- Canales para el doctor distintos de WhatsApp Cloud API.
- Enrutamiento de notificaciones por especialidad, paciente o tipo de doctor.
- Un sistema de colas distribuido o multiples trabajadores.
- Uso con pacientes reales antes de definir privacidad, consentimiento y limites
  para informacion medica.
