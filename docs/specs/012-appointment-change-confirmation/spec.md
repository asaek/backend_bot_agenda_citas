# 012 - Confirmacion de cambios destructivos de citas

## Estado

Verificado en Raspberry Pi. La cancelacion y la reprogramacion requieren una confirmacion explicita
antes de modificar la fuente de verdad de agenda; la cita debe resolverse antes de pedir
confirmacion. Para reprogramar, el backend consulta y presenta los horarios libres del dia
destino incluso si el paciente aun no propone una hora, y solicita elegir uno antes de
pedir confirmacion. La evidencia del inicio de reprogramacion sin hora esta en
`docs/verification/2026-10-05-reschedule-before-time-selection.md`. La clasificacion acepta
expresiones naturales claras y conserva la aclaracion para respuestas contradictorias o
inciertas. El enrutamiento de intenciones nuevas y abandono durante una confirmacion se
define en `specs/016-conversation-intent-routing/`.
El inicio backend de cancelacion esta implementado y verificado con 359 pruebas;
el runtime esta recargado y las rutas responden 200. La autenticacion de envio
quedo restablecida el 11/10/2026 con Meta 200 tras actualizar la configuracion local;
evidencia del bloqueo inicial y su recuperacion en
`docs/verification/2026-10-10-single-cancellation-confirmation.md`.
La confirmacion contextual de ADR 0049 esta implementada; su verificacion y el
alcance de sincronizacion sin recarga del backend se registran en
`docs/verification/2026-10-11-contextual-cancellation-confirmation.md`.
Activada en el backend el 12/10/2026 mediante `local to raspberry`, con configuracion
completa, 370 pruebas correctas y HTTP 200 en rutas locales/publicas y Meta; evidencia
en `docs/verification/2026-10-12-contextual-cancellation-deployment.md`.
La etapa 1 de afirmaciones naturales y aclaracion contextual de reprogramacion esta
verificada con 377 pruebas, backend recargado y rutas/autenticacion HTTP 200;
evidencia en `docs/verification/2026-10-12-natural-reschedule-stage-one.md`.

## Objetivo

Evitar que una solicitud ambigua, un error del LLM o una interpretacion incorrecta
cancele o modifique una cita sin que el paciente confirme la operacion exacta.

## Alcance

La funcionalidad cubre:

- Confirmacion previa para cancelar una cita.
- Confirmacion previa para reprogramar una cita a un horario concreto.
- Consulta y presentacion de los horarios libres de todo el dia destino antes de confirmar
  una reprogramacion.
- Presentacion de los horarios libres antes de preguntar una hora preferida cuando el
  paciente solicita cambiar solo la hora de una cita existente.
- Seleccion de un horario ofrecido y validacion de esa seleccion antes de crear la
  confirmacion pendiente.
- Respuesta negativa sin cambios en la agenda.
- Expiracion de una confirmacion pendiente despues de 10 minutos.
- Emision de notificaciones al doctor solamente despues de la operacion confirmada.

La creacion de una cita no requiere esta confirmacion dentro de este alcance.

## Requisitos funcionales

### RF-1201 - Confirmacion previa

Una solicitud de `cancel_appointment` o `reschedule_appointment` no debe ejecutar
la mutacion del proveedor de calendario hasta recibir una confirmacion afirmativa
del paciente. Antes de formular la pregunta, el backend debe resolver la cita dentro
del alcance del paciente. Si no existe, debe devolver el error publico correspondiente
sin guardar una accion pendiente. Si la lectura falla, debe devolver el error publico
del proveedor sin presentar una confirmacion.

### RF-1202 - Operacion exacta

La confirmacion debe estar vinculada a una sola operacion, cita y horario nuevo
cuando corresponda. Una confirmacion no puede autorizar otra mutacion distinta.

La pregunta de confirmacion debe mostrar los datos de la cita que se modificara:
fecha, horario y motivo. No debe mostrar el ID interno de la cita.
El horario presenta solo el inicio como `Hora: h:mm AM/PM`, sin hora de fin ni
rango. Para reprogramar, la nueva fecha y hora tambien usa el inicio con AM/PM.
Las opciones para aclarar cual cita desea modificar siguen la misma regla.

### RF-1203 - Respuesta negativa

Una respuesta negativa debe descartar la accion pendiente y conservar la cita sin
modificaciones. La respuesta debe indicar que no hubo cambios y que la cita sigue
agendada, incluyendo fecha y hora originales cuando estan guardadas.

### RF-1204 - Confirmacion ambigua o vencida

La clasificacion debe basarse en una intencion afirmativa o negativa clara, no en la
coincidencia exacta con `Si` o `No`. Se permiten palabras de cortesia y variantes
afirmativas directas como `Si, por favor`, `Claro` y `Adelante`. Una respuesta
contradictoria, incierta o sin una intencion reconocible debe solicitar aclaracion.
Una confirmacion vencida debe descartarse y no ejecutar la accion.
Se reconocen tambien `Si es correcto`, `Si esta bien` y `Correcto, por favor`, con
mayusculas, acentos y puntuacion. La respuesta completa debe referirse a la accion
pendiente. Una condicion como `Si, si esta bien` o `Correcto, si es correcto` no
autoriza la mutacion: un `si` sin acento despues de otra clausula se trata de forma
conservadora como posible condicion; un `sí` afirmativo explicito conserva su significado.

Ante una respuesta incierta, el backend pregunta por la operacion guardada, incluyendo
la fecha/hora de la cita original y el destino de reprogramacion. Por ejemplo:
`No me quedo claro. ¿Confirmas cambiar tu cita de hoy a las 11:00 AM para las 4:00 PM?`
La aclaracion permite confirmar o conservar la cita y no renueva la vigencia.

### RF-1205 - Notificacion posterior

La notificacion al doctor y cualquier evento de cita deben producirse solamente
despues de que el proveedor confirme una cancelacion o reprogramacion exitosa.

### RF-1206 - Cita resuelta antes de confirmar

El backend no debe pedir confirmacion si la cita no se pudo recuperar. Una cita ausente
debe producir `appointment_not_found`; un fallo de lectura debe conservar su categoria
publica de agenda. Ninguno de esos casos debe crear una accion pendiente ni permitir una
mutacion al recibir un `Si` posterior.

### RF-1207 - Disponibilidad antes de confirmar una reprogramacion

Despues de resolver la cita y antes de solicitar confirmacion, el backend debe consultar
`check_availability` para el dia de destino completo y mostrar los horarios libres. Si el
paciente no indico otro dia, se usa la fecha de la cita seleccionada. Si el paciente
solicita cambiar solo la hora sin proponer una hora nueva, el backend debe mostrar primero
la lista en lugar de preguntarle una hora libre. El paciente debe elegir un horario de la
lista; una hora no ofrecida no puede crear una accion pendiente ni modificar la agenda.
La cita objetivo se resuelve usando la lista recientemente mostrada y la hora mencionada.
Si quedan varias citas candidatas, el backend pregunta cual desea cambiar antes de
consultar disponibilidad. El horario elegido queda vinculado a la misma cita y llamada
que originaron la consulta. La lista vence a los 10 minutos.

### RF-1208 - Una confirmacion de cancelacion controlada por el backend

Una peticion directa como `quisiera cancelar la de las 10 am` debe consultar las
citas vigentes del paciente, resolver una sola cita y guardar la accion exacta antes
de mostrar la primera pregunta de confirmacion. Si no hay un dia explicito, puede
usar el ultimo listado mostrado; un dia expresado en la solicitud tiene prioridad.
Se admiten `hoy`, `mañana`, `pasado mañana`, dias de la semana y fechas `DD/MM/YYYY` o `YYYY-MM-DD`, junto
con una hora que conserva minutos y AM/PM. Una referencia reconocida que no coincide, contiene
varios objetivos o sigue siendo ambigua pide aclarar la cita sin elegir otra por defecto.

Despues de esa primera pregunta, `si por favor` ejecuta la cancelacion guardada
sin solicitar una segunda confirmacion, incluso tras reiniciar con historial acotado.
Una pregunta textual reconocible del LLM que imite la confirmacion sin una accion
pendiente debe sustituirse por una solicitud de dia/horario; no cuenta como estado
de cancelacion. Una afirmacion aislada sin accion pendiente no permite al LLM iniciar
una cancelacion usando el historial. Las preguntas informativas, negativas y abandono
mantienen su enrutamiento; la pausa o expiracion siguen exigiendo una confirmacion nueva.

### RF-1209 - Respuesta contextual a la accion pendiente

Tras mostrar una cancelacion concreta, `Si cancelala`, `Cancela la cita por favor`,
`Si, quiero cancelar la cita` y `Si, cancelar` autorizan esa misma accion sin
reiniciar la solicitud. El reconocimiento es local, completo y dependiente de la
herramienta; una instruccion de cancelacion no confirma una reprogramacion.

Otras citas, fechas, horas o instrucciones adicionales requieren aclaracion o una
nueva solicitud, nunca autorizan la accion anterior por contener `Si`. Las
condiciones no reconocidas, respuestas truncadas como `Si, pero...`, contradicciones
y preguntas tentativas no modifican la agenda. La contradiccion reconocida conserva
la accion para una respuesta clara posterior, incluso tras reiniciar.

Una respuesta contextual no renueva una accion vencida ni reactiva una pausada.
Durante una cancelacion activa, `cancela` aislado solo pregunta si desea cancelar
esa cita, con respuestas explicitas `Si, cancelar` o `No, mantenerla`; mantiene el
estado y no ejecuta por si solo. Rechazar o abandonar la solicitud conserva la cita.

## Criterios de aceptacion

1. `Deseo cancelarla` solicita confirmacion y no cambia el estado de la cita.
2. `Si`, `Si por favor` y `Claro, adelante` despues de una solicitud de cancelacion
   ejecutan una unica cancelacion.
3. `No` y `No, gracias` conservan la cita y eliminan la accion pendiente.
4. Una solicitud de reprogramacion consulta y muestra los horarios disponibles del dia
   destino antes de pedir confirmacion.
5. La reprogramacion solo pide confirmacion despues de que el paciente elige un horario
   ofrecido; una hora no disponible no crea una accion pendiente.
6. Una confirmacion no puede reutilizarse para otra cita u operacion.
7. Una accion vencida no modifica la agenda.
8. Ninguna solicitud pendiente genera una notificacion al doctor.
9. Una operacion confirmada genera la notificacion existente una sola vez.
10. La confirmacion de cancelacion muestra fecha, horario y motivo de la cita sin
   exponer su ID interno; la hora es solo el inicio con AM/PM, sin rango. La
   confirmacion de reprogramacion aplica el mismo formato a la cita y al inicio nuevo.
11. Una respuesta contradictoria como `Si, pero mejor no` o incierta como `No estoy
    seguro` solicita aclaracion y no modifica la agenda.
12. Una cita no encontrada o una lectura fallida no genera una pregunta de confirmacion,
     no crea estado pendiente y no cambia ni notifica la agenda.
13. `Quisiera modificar esa cita y cambiar su hora` despues de listar una cita muestra
     inmediatamente los horarios disponibles de esa cita y no pregunta primero la hora
     preferida.
14. Si el listado reciente contiene varias citas, el backend identifica la mencionada; si
    no puede resolver una sola, pregunta cuál antes de mostrar horarios o cambiarla.
15. Listar las citas del lunes a las 10 AM y 12 PM, pedir cancelar la de las 10 AM y
    responder una vez `si por favor` cancela solo la de las 10 AM, con una sola pregunta.
16. Reintentar la solicitud o la afirmacion en el webhook no repite la pregunta,
    la cancelacion ni la notificacion y no vuelve a abrir la gestion terminada.
17. Una fecha/hora no coincidente, minutos distintos o varios objetivos no preparan
    la cancelacion de una cita diferente. Un dia explicito prevalece sobre el contexto
    de listado, y una negativa conserva todas las citas.
18. Una pregunta textual de confirmacion sin accion pendiente y un `Si` aislado no
     permiten reconstruir una cancelacion desde el historial del LLM.
19. Las frases de RF-1209 cancelan la cita mostrada una sola vez y sin llamadas al LLM,
    tambien con historial corto y despues de recrear el servicio.
20. `Si, pero mejor no`, `Tal vez quiero cancelarla` y `¿Si cancelala?` piden aclarar,
    no descartan ni ejecutan la accion y permiten confirmar claramente despues.
21. Otra fecha/cita exige una confirmacion nueva; una accion pausada o vencida no
    se ejecuta con las nuevas variantes. Una respuesta condicionada no autoriza la accion.
22. Una negativa informa que la cita original sigue agendada; `cancela` aislado no
    mezcla abandonar la solicitud con cancelar la reserva en una pregunta de dos opciones.
23. Tras elegir las 4 PM para una cita de hoy a las 11 AM, `Si es correcto` modifica
    la cita en la primera respuesta, una sola vez y con una sola notificacion.
24. Las tres afirmaciones de RF-1204 funcionan con variantes de mayusculas, acentos y
    puntuacion. Dudas, contradicciones, condiciones y referencias a otra fecha/cita
    no ejecutan la accion anterior y reciben su aclaracion o enrutamiento correspondiente.
25. La aclaracion de un cambio pendiente muestra la cita original y el destino guardado,
    sobrevive al reinicio y permite continuar sin repetir una lista generica de frases.

## Fuera del alcance

- Confirmacion de la creacion de una cita.
- Botones interactivos o plantillas especiales de WhatsApp.
- Confirmaciones por voz o por un canal diferente de WhatsApp.
