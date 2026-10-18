# Diseno - Llamadas entrantes de WhatsApp

## Estado

Propuesto el 18 de octubre de 2026; implementacion pendiente. Este documento
define el diseno para revision antes de introducir dependencias de audio.
La [ADR 0054](../../decisions/0054-inbound-calling-with-scoped-confirmation.md)
permanece propuesta. Los nombres de componentes y configuracion de este documento
son futuros; no describen interfaces ya disponibles.

## Punto de partida comprobado

- `main.py` extrae solo `type=text` y devuelve HTTP 200 para otros eventos.
  `_process_reply()` combina generacion, entrega escrita y notificaciones.
- `whatsapp_client.py` solo implementa `send_text()` y usa Graph API `v23.0`.
- `ConversationService` resuelve `PatientScope` y reutiliza una conversacion
  activa por paciente. `conversations.context_json` conserva una gestion activa
  o pausada; los estados actuales no distinguen canal ni sesion de llamada.
- La reserva se ejecuta al aceptar el motivo en
  `_resolve_pending_appointment_reason()`. Cancelacion y reprogramacion ya tienen
  una pregunta previa controlada por el backend.
- `PendingAppointmentAction.call_id` identifica una llamada a herramienta del
  LLM. **No es el identificador de una llamada de WhatsApp.**
- `patient_turn()` serializa turnos del mismo paciente dentro de un proceso.
  `ReplyDeliveryService` prepara y recupera respuestas escritas; sus estados de
  entrega no representan reproduccion de audio.

## Arquitectura propuesta

```text
Meta Calling / simulador de eventos
                  |
                  v
Webhook -> registro de evento -> ACK
                  |
                  v
CallingService <-> cliente Calling (HTTP / fake)
       |
       +-- sesiones, eventos y resultados -> SQLite
       +-- tareas supervisadas por el ciclo de vida de FastAPI
       |
       v
CallMedia (WebRTC / fake) <-> interlocutor Meta / laboratorio
       |
       v
VoiceSession: audio -> transcripcion final -> turno con origen
       |
       v
ConversationService -> AgentOrchestrator -> ToolExecutor -> CalendarProvider
       |
       v
Respuesta para voz -> sintesis -> CallMedia
       |
       +-- resultado exitoso de agenda -> entregas escritas y al doctor
```

La ruta inicial es Meta directa y una cadena transcripcion -> bot existente ->
sintesis. El transporte de audio queda separado del proveedor de voz. Para el
laboratorio, `aiortc` es candidato, sujeto a una prueba en la Raspberry; no se
adopta ni instala en este corte. No se presupone una conexion directa Meta-OpenAI
ni se aplican los limites de archivos de notas de voz al transporte WebRTC.

## Fronteras de responsabilidad

| Componente propuesto | Responsabilidad |
| --- | --- |
| `main.py` | Despachar mensajes y eventos de llamadas, validar la entrada y componer dependencias y tareas. |
| `calling_service.py` | Ocultar ciclo de llamada, capacidad, transiciones, reclamacion de eventos y cierre idempotente. |
| `whatsapp_calling_client.py` | Encapsular operaciones Calling sobre HTTP con cliente inyectable; ofrecer un doble sin red. |
| `calling_repository.py` | Encapsular sesiones, eventos, turnos y reclamaciones persistentes sin guardar audio o SDP. |
| `call_media.py` | Negociar y transportar audio, exponer conexion/cierre y cancelar reproduccion; implementacion falsa primero. |
| `voice_session.py` | Coordinar transcripcion final, turnos de voz, sintesis y reproduccion con dependencias inyectadas. |
| `ConversationService` y flujo de citas | Compartir identidad y reglas, agregar origen del turno y aplicar la autorizacion contextual antes de herramientas. |

El cliente Calling recibe identificadores y una respuesta SDP del transporte; no
decide agenda ni produce audio. `CallMedia` desconoce las citas. Los dobles
ejercitan estas mismas fronteras, sin crear otro bot ni una segunda agenda.

## Entrada y modos

Configuracion propuesta, deshabilitada por defecto:

- `WHATSAPP_CALLING_ENABLED=false`: no crea sesiones ni carga librerias de audio.
- `WHATSAPP_CALLING_MODE=simulated|laboratory|meta`: debe seleccionarse
  explicitamente al habilitar la funcionalidad; valores desconocidos fallan al
  configurar, sin recurrir silenciosamente a otro modo.
- `simulated`: clientes y medios falsos inyectados; no exige credenciales de Meta.
- `laboratory`: interlocutor controlado y audio real, con base y agenda de prueba.
- `meta`: numero y token configurados, App Secret para validar firmas y proveedor
  de medios comprobado. Una configuracion incompleta impide activar este modo.

El simulador entra por el servicio o por `TestClient` con dependencias de prueba.
No se agrega una ruta publica que permita iniciar sesiones simuladas o elegir
arbitrariamente la identidad de un paciente de la base operativa. El laboratorio
usa un proceso y base de prueba separados, y un interlocutor con acceso restringido.

En el ramal conectado se valida `X-Hub-Signature-256` sobre los bytes originales,
el numero empresarial y el remitente antes de cualquier escritura de dominio.
La verificacion GET del webhook sigue siendo el desafio existente. Los fixtures
de Calling se construiran desde ejemplos oficiales y la version de API elegida;
no se inventaran campos de Meta a partir de los estados internos de este diseno.

## Sesion, eventos y tareas

### Identificadores

- `session_id`: identidad interna de una conexion, tambien en laboratorio.
- `whatsapp_call_id`: identificador externo de la llamada; se conserva junto al
  numero empresarial y al modo para evitar colisiones con otros remitentes o dobles.
- `voice_turn_id`: identidad estable de una intervencion final dentro de la sesion.
- `tool_call_id`: identificador de la solicitud de herramienta, separado de todos
  los anteriores. No se reinterpretara `PendingAppointmentAction.call_id` como voz.

La deduplicacion usa identidad del evento documentada o una clave determinista de
sus campos estables, ademas de transiciones y acciones reclamadas. Deduplicar solo
por `whatsapp_call_id` eliminaria eventos legitimos posteriores y queda excluido.

### Estados internos

| Estado | Significado y transiciones |
| --- | --- |
| `received` | Entrada registrada; puede negociar, rechazarse, fallar o terminar remotamente. |
| `negotiating` | Preparacion del medio y aceptacion en curso; puede activarse, fallar o terminar. |
| `active` | Aceptacion confirmada y transporte conectado; admite turnos y puede terminar o fallar. |
| `ending` | Cierre local reclamado; no admite turnos ni nuevas aceptaciones. |
| `ended`, `rejected`, `failed`, `interrupted` | Terminales; no permiten volver a negociar ni ejecutar turnos. |

Son estados del backend, no nombres garantizados del webhook de Meta. Un HTTP
exitoso de aceptacion no basta para declarar audio activo. En simulacion, el medio
falso emite la conexion y el resultado queda etiquetado como tal.

Una terminacion adelantada crea o actualiza el registro terminal correlacionable;
una oferta posterior de esa llamada no lo reactiva. La capacidad se reclama
atomicamente antes de aceptar: una llamada global y una por paciente en el piloto.
Una ampliacion requiere medir recursos en la Raspberry y actualizar el diseno.

### ACK y supervision

El webhook registra el evento y devuelve el ACK sin esperar negociacion, STT,
LLM o TTS. Una tarea supervisada del ciclo de vida de FastAPI procesa el evento;
no se usa una tarea sin seguimiento ni se introduce una cola externa. Las
excepciones terminan la sesion de forma controlada y quedan observables.

Al iniciar, las sesiones no terminales del proceso anterior pasan a `interrupted`;
se invalidan autorizaciones y se intenta cerrar el extremo externo cuando sea
posible. No se reproduce audio ni se reejecutan herramientas para recuperarlas.
Un evento persistido cuyo procesamiento se perdio no deja la llamada activa
indefinidamente. Al apagar, se impiden nuevas sesiones y se cierran las existentes.

Valores iniciales propuestos para el piloto: negociacion de hasta 20 segundos,
inactividad de 60 segundos y llamada de hasta 10 minutos. Son limites propios,
con reloj y temporizadores inyectables para pruebas, no limites publicados por
Meta. El corte conectado los revisara contra los plazos vigentes del proveedor.

## Persistencia propuesta

Migracion aditiva y compatible con las bases existentes:

- `call_sessions`: modo, numero empresarial, identificador externo e interno,
  paciente/conversacion una vez resueltos, estado, tiempos y resultado seguro.
- `call_events`: clave unica del evento, sesion, tipo, tiempos y resultado de
  procesamiento. No conserva payload bruto ni SDP.
- `voice_turns`: sesion, secuencia estable, mensaje entrante asociado,
  respuesta preparada, estado de generacion y resultado de reproduccion
  (`pending`, `playing`, `completed`, `interrupted`, `failed`).
- Un registro de ejecucion de mutaciones por accion y version, con reclamacion,
  resultado conocido o `uncertain`, para impedir reejecuciones ciegas.

Las transcripciones finales pueden usar `messages` con un tipo de voz y un ID
interno con espacio de nombres propio; `voice_turns` conserva su procedencia.
No se hacen pasar por IDs `wamid` ni se usa `send_text()` para una respuesta oral.
El historial comun debe distinguir texto escrito y voz, e incluir solo lo que
corresponda al turno actual. Una respuesta interrumpida lleva esa marca; el
modelo no recibe como ya dicho todo un texto que solo se preparo.

La conversacion activa unica se conserva. La gestion en `context_json` gana
metadata de propietario: canal, `session_id` cuando corresponda y version. Los
snapshots historicos sin origen se interpretan como chat. Las operaciones sobre
ese propietario y sus autorizaciones se actualizan en transaccion.

## Integracion conversacional y continuidad

La entrada comun debe transportar origen tipado y turno estable ademas de texto
final y `PatientScope`. `IncomingTextMessage` sigue siendo el adaptador de chat;
la voz no llama a `_process_reply()` fingiendo un mensaje escrito. Se reutiliza
`ConversationService` mediante una entrada con origen explicito y una salida que
pueda presentar datos para voz o texto. No se copia su logica de agenda.

Antes de resolver cualquier paso pendiente se comprueba el propietario:

1. Entrar a una llamada crea una sesion y un saludo; no transfiere la gestion.
2. Un turno del canal propietario puede avanzar los datos de la gestion.
3. Un turno de otro origen no se usa como nombre, motivo, seleccion o afirmacion
   de esa gestion. Una pregunta informativa tampoco pausa o consume una
   autorizacion de otro canal; se responde sin avanzar su flujo.
4. Una solicitud explicita de retomar transfiere el propietario bajo el bloqueo
   del paciente, incrementa la version, invalida autorizaciones y revalida agenda.
   Siempre presenta el paso pendiente en el nuevo canal antes de consumir datos.
5. Una gestion nueva explicita reemplaza la previa conforme a las reglas
   existentes, cambia el propietario e invalida su autorizacion. Un turno tardio
   de la gestion anterior no la puede restaurar.
6. Al cerrar la llamada, sus datos pendientes quedan pausados para una futura
   recuperacion explicita. Una llamada nueva recibe otra identidad y una pregunta
   nueva; el `Si` de la llamada anterior nunca se reutiliza.

`patient_turn()` protege cada turno y la transferencia, no toda la duracion de
la llamada. El audio y los pacientes distintos no esperan un bloqueo mantenido
durante minutos. El piloto conserva un solo proceso Uvicorn; no promete
serializacion entre multiples workers con el bloqueo actual en memoria.

## Confirmacion verbal y ejecucion

Se agrega una autorizacion de voz controlada por el backend, ligada a paciente,
conversacion, canal, sesion, accion, version, datos exactos, pregunta emitida y
vencimiento de hasta 10 minutos. La pregunta queda habilitada para confirmar
solo cuando el medio termina de emitirla completa. Ese resultado no demuestra
que la persona la haya oido; impide aceptar un `Si` sobre una pregunta truncada.

La comprobacion se aplica a **todas** las rutas hacia las tres herramientas de
mutacion: solicitudes del LLM y resolutores locales, incluido el que hoy crea una
cita al aceptar el motivo. Cambiar solo el prompt no resuelve esta frontera.
La creacion por chat conserva su comportamiento actual; el requisito adicional
de confirmacion final corresponde a voz. Las autorizaciones del chat tambien
quedan marcadas con su origen para impedir que se consuman desde una llamada.

Una correccion, pausa, cambio de propietario o interrupcion de la pregunta
invalida la autorizacion y exige presentar otra version. La transcripcion final
de la afirmacion debe pertenecer a un turno posterior a la pregunta, en la misma
sesion activa. Los parciales solo pueden detener audio, no autorizar herramientas.

Antes de ejecutar, bajo el bloqueo del paciente se revalidan sesion, propietario,
version y vigencia, se consulta la agenda y se reclama la accion de forma durable.
Las comprobaciones de propiedad de la cita y disponibilidad siguen en la frontera
de agenda. Si los datos vigentes difieren de los presentados, se emite una nueva
pregunta en vez de ejecutar con otra fecha, hora o cita.

El cierre de llamada se coordina con esa reclamacion: si gana el cierre, no se
ejecuta; si ya se inicio la operacion externa, su resultado se conserva aunque se
cancele la reproduccion. Cancelar una tarea de audio no equivale a deshacer Google
Calendar. Una caida entre la escritura externa y el registro local puede dejar
`uncertain`; se concilia contra el proveedor antes de otra ejecucion. El diseno
no promete una transaccion atomica entre SQLite y Google.

## Audio, respuestas y entregas

`VoiceSession` conserva una secuencia de turnos y una generacion vigente. Al
detectar voz del paciente detiene la reproduccion; al obtener una transcripcion
final valida procesa un solo turno. Descarta resultados tardios de generaciones
reemplazadas o de sesiones cerradas, y limita los buffers de audio. El silencio,
una entrada incomprensible y un fallo del proveedor tienen respuestas controladas;
no se sustituyen nombres, motivos u horarios con valores inventados.

El presentador de voz usa los mismos resultados de dominio que el escrito:
frases breves, pocas opciones por turno y horas habladas en español. No lee tablas,
asteriscos o IDs. El paciente puede pedir mas horarios. La confirmacion de exito
usa el resultado de la herramienta, no una reconstruccion del LLM.

Generar, emitir audio completo y entregar texto por WhatsApp son resultados
distintos. `ReplyDeliveryService` sigue a cargo de los mensajes escritos; no se
marca una respuesta como mensaje entregado por haber sintetizado audio. Despues
de una operacion exitosa se registran sus eventos y entregas pendientes, incluso
si el paciente cuelga antes de escuchar el resultado.

En el corte conectado, el seguimiento escrito comprueba la ventana de atencion
segun las reglas vigentes; no se supone que cualquier llamada la haya abierto.
Usa plantilla aprobada cuando corresponda y, si no esta disponible, conserva una
entrega pendiente con error operativo. La notificacion al doctor reutiliza la
composicion y deduplicacion existentes con el historial pertinente de la gestion.
La falta de audio o mensajeria nunca vuelve a ejecutar la mutacion.

## Fronteras de verificacion y decisiones pendientes

| Corte | Evidencia y criterios |
| --- | --- |
| C0 - Documentacion | Revision cruzada de requisitos, diseno, tareas, vocabulario e indices. |
| C1 - Control simulado | Servicio/webhook con dobles, SQLite temporal, reloj controlado y sin red; CA-01 a CA-06, CA-15 y CA-17. |
| C2 - Audio de laboratorio | Compatibilidad Raspberry, saludo bidireccional y cierre; CA-06, CA-07, CA-15 y CA-17. |
| C3 - Conversacion de voz | Dobles STT/LLM/TTS y muestra de voz real con proveedor elegido; CA-08 y CA-09, con regresion de control. |
| C4 - Agenda y continuidad | Agenda falsa, pruebas de todos los origenes y fallos en herramientas; CA-10 a CA-14, sin efectos en Google real. |
| C5 - Meta | Numero elegible, fixtures contrastados, firma, limites y medios reales; CA-03, CA-16 y CA-17, mas escenario integrado. |

Cada implementacion se modifica localmente, se sincroniza y se ejecuta en la
Raspberry conforme a [AGENTS.md](../../../AGENTS.md). La suite existente se ejecuta
con `uv run python -m unittest discover -s tests -v`. Las pruebas de medios o
proveedores reales se ejecutan por separado y declaran su consumo y frontera.

Antes de C2 se decide la biblioteca y se comprueban codecs, arquitectura y recursos
de la Pi. Antes de C3 se fijan proveedor/modelos de STT y TTS y se documentan
latencia y costo observados; el contrato del LLM de texto no implica soporte de
audio. Antes de C5 se contrastan los eventos, acciones, version de API y plazos
oficiales, y se resuelve ICE/STUN/TURN o el transporte que requiera Meta. El tunel
HTTP de ngrok no acredita esa conectividad. La coexistencia con la app movil se
evalua solo si se elige esa modalidad para el numero futuro.

## Referencias

- [Spec del incremento](./spec.md) y [plan verificable](./tasks.md).
- [Investigacion previa de opciones de voz](../../research/whatsapp-voice-options.md),
  que tambien explora telefonia convencional fuera de este incremento.
- [Meta: Business Calling](https://whatsappbusiness.com/blog/whatsapp-business-calling-api/).
- [Meta: especificacion OpenAPI](https://github.com/facebook/openapi/blob/main/business-messaging-api_v23.0.yaml).
- [Arquitecturas de agentes de voz](https://developers.openai.com/api/docs/guides/voice-agents).
