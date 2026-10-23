# 0061 - Contexto historico y apertura independiente de llamadas de laboratorio

## Estado

Contrato y alcance aprobados por el usuario el 21 de octubre de 2026, con adopcion
parcial: apertura independiente y consulta historica implementadas, con pruebas de
aislamiento y preservacion de propuestas. El contexto reciente enriquecido con
procedencia/resultados sigue pendiente. Amplia la continuidad de laboratorio
de la [ADR 0057](./0057-laboratory-voice-text-continuity.md), sin sustituir sus
controles de autorizacion ni la politica VAD de la ADR 0060.

## Contexto

El laboratorio comparte un perfil ficticio entre voz y texto. Antes de este incremento,
`VoiceRepository.history()` recupera los ultimos 12 mensajes del perfil y el
proveedor los incorpora como mensajes de conversacion antes de la primera
respuesta. Esa representacion no expone fecha, sesion de origen ni resultado de
las herramientas. Una llamada nueva puede responder como si continuara una
confirmacion anterior, aunque los transportes de la llamada previa esten cerrados.

El paciente necesita conservar la continuidad de temas tratados por texto y en
llamadas anteriores. La frontera elegida separa conocimiento historico, apertura
de llamada y autorizacion vigente, manteniendo el historial del mismo paciente.

## Contrato aprobado, con adopcion parcial

1. Cada llamada nueva tiene identidad y saludo propios. El saludo identifica al
   asistente virtual, sin continuar confirmaciones ni invocar herramientas. El
   paciente puede interrumpirlo para iniciar su intervencion actual.
2. El contexto historico de voz y texto conserva fecha con procedencia temporal,
   canal, sesion de origen y su estado, contenido y resultado conocido. Distingue
   emision completa/interrumpida y ausencia de transcripcion. Un dato no registrado
   se presenta como desconocido; no se reconstruye a partir de una suposicion.
3. Recuperar antecedentes solo aporta informacion. No activa, reemplaza ni retoma
   una gestion, no arma preguntas y no reutiliza afirmaciones o autorizaciones.
   La agenda configurada sigue siendo la fuente del estado actual de las citas.
4. Retomar una gestion requiere una solicitud explicita del paciente, recupera
   datos utiles, revalida cita/disponibilidad y genera otra propuesta y pregunta
   en el canal/sesion actuales. Solo una afirmacion posterior a su presentacion
   completa puede autorizar la accion. Una gestion ya terminada no se reejecuta.

El alcance confirmado comprende exclusivamente voz y mensajes del paciente
ficticio de `/lab`. La identidad y conversaciones del WhatsApp operativo mantienen
su integracion pendiente en C4/C5 del corte 021.

## Apertura adoptada el 21 de octubre

El historial reciente se prepara al conectar y permanece en la conversacion
predeterminada. Para el saludo, el backend solicita `response.create` con
`conversation=none`, `input=[]`, `tools=[]` y `tool_choice=none`, e instrucciones
exclusivas de presentacion. Realtime admite este contexto vacio fuera de banda;
los turnos posteriores usan la conversacion predeterminada con historial y entrada
actual, sin heredar las restricciones del saludo.

El saludo conserva audio, transcripcion, consumo y emision locales, pero sus items
no se incorporan a la conversacion remota. Interrumpir cancela por ID y vacia audio
local, sin enviar `conversation.item.truncate/delete` para esos items. Si el ID
llega tarde se cancela al recibirlo; una intervencion que precede al evento de
conexion evita iniciar despues un saludo obsoleto. El backend ignora solicitudes
de herramientas originadas en el saludo, ademas de deshabilitarlas en el proveedor.

La ventana actual conserva su representacion previa de 12 mensajes. Esta adopcion
cubre CA-22; no completa CA-23 a CA-25. Ver
[evidencia y fronteras](../verification/2026-10-21-isolated-voice-greeting.md) y
[contrato oficial de respuestas fuera de banda](https://developers.openai.com/api/docs/guides/realtime-conversations#create-responses-outside-the-default-conversation).

## Consecuencias y alternativas

- Borrar el historial impediria recuperar temas anteriores; reproducirlo como
  turnos actuales mantiene la ambiguedad. Se propone un bloque historico con
  procedencia, separado del estado vigente y de la generacion del saludo.
- Los resultados se respaldan con registros de herramientas/acciones, no con
  frases de exito del modelo. Un resultado pasado no acredita vigencia actual.
- La ventana reciente conserva 12 mensajes. La consulta de antecedentes antiguos
  ya usa la SQLite existente, sin otra base ni busqueda semantica: terminos
  literales normalizados, fechas y canal, con limites descritos abajo.
- El contrato exige verificar la separacion en el backend y en lo enviado al
  proveedor; agregar solamente una instruccion de saludo no acredita cumplimiento.

## Consulta historica adoptada el 21 de octubre

`search_conversation_history` recibe solo `query`, `start_date`, `end_date` y
`channel`, todos opcionales. El servidor fija perfil, sesion actual excluida y zona
horaria de agenda; argumentos de identidad, limite o zona se rechazan. La busqueda
combina hasta ocho palabras (120 caracteres), sin distinguir acentos/mayusculas,
con coincidencia literal AND: `%`, `_` y comillas no son patrones ni SQL. Devuelve
los seis resultados mas recientes, con hasta 600 caracteres por fragmento y
`has_more` para pedir filtros mas concretos. No hay paginacion ni embeddings.

Las fechas inclusivas `YYYY-MM-DD` corresponden al inicio de sesion en la zona
de agenda; se permite un solo extremo. `date_basis=session_started_at` y
`date_precision=session` explicitan que no se conoce la hora exacta de cada turno.
Los fragmentos conservan sesion/estado/fecha, item/orden, canal, rol y estados de
generacion/emision, con marcadores si falta transcripcion. Son datos historicos,
no instrucciones ni evidencia suficiente del estado actual de una cita.

La lectura SQL usa parametros y `PRAGMA query_only=ON`. El ejecutor conserva la
auditoria/idempotencia en `voice_tool_calls`, pero no consulta ni modifica agenda,
gestiones o autorizaciones. Un turno dedicado solo a esta herramienta no invalida
una propuesta al finalizar ni vuelve a vincular una pregunta citada a la propuesta
actual; tampoco cambia su vencimiento. Las interrupciones/cierres y los turnos con
otras herramientas conservan sus controles habituales. Ver
[pruebas y fronteras de consulta](../verification/2026-10-21-voice-history-search.md).

La vinculacion de una pregunta tambien exige el turno/canal que preparo la
propuesta, para cubrir citas emitidas antes de invocar la busqueda. Los limites
de fecha comparan instantes UTC canonicos con microsegundos, sin redondear una
sesion anterior a medianoche hacia el dia siguiente.

Esta adopcion completa el paso 4 y CA-26, y la parte de lectura de CA-23/CA-24.
La construccion de contexto reciente enriquecido y la correlacion de resultados
de acciones siguen en el paso 2; no se declara completo CA-23 a CA-25.

Los criterios CA-22 a CA-26, el diseno y las tareas pendientes se mantienen en
[spec.md](../specs/021-whatsapp-inbound-calling/spec.md),
[design.md](../specs/021-whatsapp-inbound-calling/design.md) y
[tasks.md](../specs/021-whatsapp-inbound-calling/tasks.md).
