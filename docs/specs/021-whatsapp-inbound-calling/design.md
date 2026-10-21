# Diseno - Llamadas entrantes de WhatsApp

## Estado

El alcance de laboratorio A-E fue aprobado e implementado el 18 de octubre de
2026. El 19 de octubre se implemento tambien voz nativa OpenAI Realtime y
herramientas de laboratorio (ADR 0056). Calling y continuidad operativa siguen propuestos.
La [ADR 0054](../../decisions/0054-inbound-calling-with-scoped-confirmation.md)
permanece propuesta para Calling y autorizaciones; la ADR 0055 adopta los medios
del laboratorio. La seccion siguiente distingue las interfaces disponibles de
las propuestas para los cortes posteriores.

## Laboratorio implementado (A-E)

- `main:create_lab_app --factory` crea una aplicacion independiente de `main:app`.
  Requiere `LAB_CALLS_ENABLED=true`, sin `LAB_ACCESS_TOKEN` ni cabecera Bearer.
  Escucha en loopback y se accede mediante SSH; no se publica el laboratorio en ngrok.
- `GET /lab` sirve `assets/lab-client.html`; permite tono de 440 Hz o microfono.
- `GET /lab/health` devuelve estado/modo sin crear medios ni pedir token.
  **Conectar e iniciar llamada** comprueba senalizacion automaticamente antes de
  crear la llamada, sin boton separado. El cliente muestra contexto seguro,
  estados ICE/conexion, tipos/protocolo del par seleccionado, contadores RTP y
  reproduccion. No muestra direcciones de candidatos ni persiste SDP/credenciales.
  `getUserMedia` se valida antes de pedir permiso; un origen HTTP de LAN recibe
  instrucciones para usar HTTPS o localhost mediante SSH. Cliente/API comparten
  origen y el tunel solo lleva HTTP; el audio usa UDP directo entre los equipos.
- La skill [lab-tunnel](../../../.agents/skills/lab-tunnel/SKILL.md) prepara el
  acceso Mac/Pi: comprueba o inicia el proceso de laboratorio, reutiliza o abre
  SSH y verifica pagina y salud sin token desde ambos equipos.
  La preparacion no crea llamadas ni invoca OpenAI; escucha e interrupcion se
  comprueban despues desde el cliente. Los PID se descubren en cada ejecucion.
- `POST /lab/calls` recibe `{type: "offer", sdp}` con candidatos ICE completos y
  devuelve HTTP 201 con `session_id`, `type: "answer"`, `sdp` y modo `laboratory`.
  GET/DELETE `/lab/calls/{session_id}` consultan/cerran; errores seguros:
  400 entrada invalida, 404 sesion ausente, 409 capacidad y
  422 negociacion fallida y 503 persistencia no disponible; cuerpo limitado a 128 KiB.
- `calling_service.py` supervisa negociacion, eventos y cierre con plazos de
  20 s de negociacion, 60 s sin frames recibidos y 600 s de duracion maxima.
  Una llamada global por base/proceso; otra se rechaza antes de crear medios.
  No resuelve identidad de paciente ni accede a la agenda.
- `calling_repository.py` administra exclusivamente `lab_call_sessions` y
  `lab_call_events`. Rechaza una base con tablas ajenas y usa bloqueo de proceso.
  Recupera sesiones no terminales como `interrupted`; las terminales mantienen
  metricas y resultados. No persiste SDP, audio ni credenciales.
- `call_media.py` usa aiortc 1.14.0, PyAV 16.1.0 y Opus del extra opcional
  `audio`. Importacion diferida, una pista `sendrecv`, sin STUN/TURN. Consume
  frames continuamente; mantiene metricas escalares, cola de eventos acotada y
  lee el WAV en bloques de 20 ms. El archivo esta limitado a 30 s.
- El saludo comienza al detectar senal de entrada con pico PCM16 superior a 500.
  Sus estados son `prepared`, `playing`, `completed`, `interrupted`, `failed`.
  Tras consumir la fuente se emiten 300 ms de silencio para drenaje. `completed`
  representa emision local, no escucha humana; el navegador verifica recepcion.
- Cierre idempotente y concurrente: marca `ending`, cancela y espera tareas,
  cierra pistas/peer, persiste metricas y libera capacidad. Fallar al limpiar
  bloquea nuevas sesiones y deja `resources_released=false`.
  Un fallo de SQLite no impide cerrar medios: se conserva `ending` en memoria,
  con `persistence_status=pending`, y se bloquea capacidad hasta reintentar DELETE
  y guardar el resultado. No se cierra el mismo medio dos veces al recuperarse.
  Si falla POST despues de asignar sesion, el 503 incluye `session_id` para poder
  reintentar ese cierre desde el cliente.
- El lifespan de texto compone la agenda al arrancar `main:app`, no al importar
  `main.py`; iniciar el laboratorio no abre la base operativa. `LAB_DATABASE_PATH`
  es independiente de `DATABASE_PATH` y por defecto usa `data/calling-lab.sqlite3`.

La [evidencia](../../verification/2026-10-18-aiortc-audio-laboratory.md) corresponde
a dos peers y a Chromium/backend en la misma Pi. La escucha fisica desde otro
equipo, ICE hacia Meta y los cortes de integracion operativa siguen pendientes.
El verificador admite un navegador remoto por CDP y un puerto HTTP fijo reenviado
por SSH, para ejecutar el driver/backend en la Pi y el cliente en la computadora.
Puede exigir que el candidato remoto pertenezca a la LAN esperada; comprueba
tambien el local cuando el navegador expone su direccion en vez de ocultarla.
La evidencia de esa ruta se registra por separado de la prueba en la misma Pi.
La [prueba LAN](../../verification/2026-10-18-webrtc-client-lan.md) paso con Chrome
en macOS y candidato remoto en la LAN, sin STUN/TURN; escucha y microfono fisicos
siguen pendientes.

## Voz nativa implementada en laboratorio

- `LAB_AUDIO_MODE=greeting|realtime` selecciona saludo o conversacion. El modo
  Realtime carga los extras `audio` y `voice` y mantiene la clave solo en la Pi.
- `openai_realtime_provider.py` configura Realtime GA sobre WebSocket con PCM16
  mono a 24 kHz, VAD del proveedor y transcripcion en paralelo. Las respuestas se
  solicitan desde el backend para correlacionar generacion y turno consolidado.
- `VoiceSession` puentea Opus/PCM, limita entrada a 50 frames y salida a 30 s,
  completa huecos RTP con silencio y separa generacion de emision. Interrumpir
  vacia primero el audio local, cancela la respuesta y trunca el contexto emitido.
  El estado `listening` exige que todos los elementos de salida hayan drenado.
- `VoiceTools` comparte instrucciones, esquemas, validadores y ejecucion con chat.
  El nombre y motivo se validan antes de proponer; el modelo no elige identidad.
    Una pregunta debe coincidir con el texto backend y haberse emitido completa.
    Confirmar requiere la misma propuesta, sesion/canal y generacion vigente. La
    secuencia normal es el turno siguiente; si VAD cancela una respuesta intermedia,
    el backend liga la transcripcion al turno actual y espera hasta 1 s. Solo una
    afirmacion inequivoca de ese turno permite la secuencia posterior; sin ella se
    renueva la pregunta.
- Si se interrumpe una pregunta sin armar, `VoiceTools` invalida durablemente su
  accion y conserva aparte sus datos en memoria. Un intento de confirmarla en esa
  llamada/canal prepara otra accion revalidada y devuelve su pregunta, sin ejecutar.
  Identificador incorrecto/canal ajeno no recuperan datos automaticamente; rechazo,
  correccion, nueva gestion o cierre descartan esta recuperacion local. La nueva
  pregunta debe emitirse completa y confirmarse en otro turno.
- Si una pregunta ya emitida precede a un turno VAD cuya respuesta se cancela antes
  de completar, `VoiceSession` correlaciona la transcripcion eventual con su turno
  original. El ID correcto, la decision del modelo y una afirmacion inequivoca en
  esa transcripcion permiten ejecutar la misma accion, sin volver a pedir los datos.
  La espera de transcripcion se limita a 1 s. Una transcripcion ausente, ambigua o
  de otro turno renueva la pregunta; una pregunta no emitida completa nunca autoriza.
- La autorizacion se revoca al comenzar otro audio o colgar. El hilo SQLite toma
  el escritor antes de comprobar la autorizacion y conserva esta hasta el commit.
  Las operaciones reclamadas se finalizan; las obsoletas no reclamadas se rechazan.
- `VoiceRepository` usa base/perfil de laboratorio exclusivos y bloqueo de
  proceso. Conserva turnos, acciones, resultados de agenda falsa y consumo por
  modelo. Un reinicio invalida propuestas y bloquea perfiles con operaciones
  inciertas. La historia incompleta usa marcadores; una transcripcion tardia no
  ejecuta nada.
- Al cerrar se detienen ambos transportes y se espera hasta 1 s por transcripciones
  pendientes. Si falla el cierre durable, la API conserva `ending`, informa medios
  liberados y permite reintentar DELETE sin reabrir audio ni liberar capacidad antes.
- Valores iniciales: 300 s maximos, 30 s de inactividad real (excluye habla,
  procesamiento y reproduccion), cinco sesiones por perfil/base por defecto.
  `VOICE_MAX_SESSIONS=unlimited` desactiva solo esa cuota total para pruebas. Se
  guardan tokens de audio, texto, cache y transcripcion, sin credenciales ni cuerpos
  de proveedor. Al alcanzar un maximo numerico, `VoiceRepository.begin` eleva un
  error tipado con uso y limite. `CallingService` finaliza la negociacion y
  `/lab/calls` responde HTTP 429 sin atribuir la cuota al microfono ni al SDP. El
  conteo sobrevive reinicios. La cuota diaria queda pendiente antes de uso operativo.

La agenda falsa es el valor predeterminado. `VOICE_CALENDAR_PROVIDER=google`
compone el proveedor REST con `GOOGLE_CALENDAR_IDS`, autenticacion y zona horaria
existentes. Sus eventos usan `managed_by=whatsapp_voice_lab`; `GoogleCalendarProvider`
acepta un valor de propietario configurable y sigue exigiendo coincidencia de
propietario e `patient_id` al listar/modificar. El adaptador operativo conserva
`managed_by=whatsapp_chatbot`, por lo que no encuentra las citas del laboratorio
aunque comparta calendario e ID ficticio.

`VoiceTools` persiste snapshots solo cuando el adaptador ofrece la coleccion en
memoria del fake. Con Google, la agenda externa es la fuente de verdad y el resultado
de la mutacion se guarda sin una segunda lectura externa obligatoria. La pagina y
`/lab/health` exponen el proveedor activo. Los eventos Google creados son reales;
el perfil continua siendo ficticio y no se comparte con pacientes/chat operativos.
La continuidad entre esos canales sigue en C4. Meta Calling sigue en C5.

## Punto de partida comprobado

El incremento de continuidad de laboratorio (ADR 0057) agrega entradas de texto
para el mismo perfil ficticio y conserva el modelo de voz nativa. Los mensajes se
deduplican y usan acceso directo sin token. Las propuestas quedan ligadas al canal y a su secuencia;
retomar crea otra pregunta y ninguna transcripcion puede ejecutar una accion.
Se registran por separado generacion, duracion generada y duracion emitida. Esta
prueba no resuelve la identidad de un paciente de WhatsApp desde el navegador.

### Medicion del hito Realtime (20 de octubre)

`voice_metrics.py` concentra medidas escalares, sin otra dependencia. El resultado
se incluye en `metrics.voice_performance` y `metrics.voice_cost` y queda persistido
con la sesion. Los eventos con `event_id` repetido se descartan antes de procesar
VAD/audio/herramientas; el registro se limita a 65536 eventos por sesion.

- `speech_stopped` fija una referencia monotona por item de entrada; `committed`
  la liga al turno. Si falta, la referencia explicita es recepcion del commit.
  Primer PCM recibido y primer frame consumido por la pista se miden aparte.
  El segundo usa un evento acotado de `AiortcCallMedia`, no la llegada de PCM a la
  cola. Ni uno ni otro incluyen el VAD/red anterior a la referencia ni acreditan
  escucha en el Mac. Los turnos de saludo/texto no se agregan como latencias de voz.
- `without_tools` informa muestras, mediana y p95 nearest-rank por sesion, excluye
  turnos con herramientas y deja ausentes como `null`. Las herramientas conservan
  tiempo de validacion/ejecucion completo, sin guardar argumentos ni resultados.
- `local_interruptions_ms` va desde iniciar la interrupcion hasta vaciar la cola,
  antes de esperar red/SQLite; no mide el jitter ni el corte acustico remoto.
- CPU es del proceso durante la sesion (100% = un nucleo). RSS es el pico del
  proceso durante su vida, no memoria atribuida exclusivamente a la llamada.
  Se informa tambien cola de entrada y cola/pico de salida; los limites se conservan.
- Para archivo de muestra, WebAudio observa cada 20 ms la primera señal remota
  posterior al final de la fuente. El navegador muestra
  `sample_end_to_browser_playback_signal_ms`: aproximacion del renderizador, no
  medicion del altavoz fisico. Las latencias del backend no validan por si solas
  las metas end-to-end p50 <= 1.5 s / p95 <= 3 s.
- El estimador usa solo tarifas verificadas el 20 de octubre para
  `gpt-realtime-2.1` y `gpt-4o-mini-transcribe`. Realtime separa texto/audio/cache;
  transcripcion se suma aparte. Modelo diferente, desglose insuficiente o eventos
  finales ausentes dejan `total_usd=null`, `complete=false` y subtotal conocido.
  No es una factura ni un corte monetario automatico. Cinco conexiones por perfil
  y sesiones de 300 s siguen siendo los limites iniciales de laboratorio.

`POST /lab/messages` acepta un ID idempotente y texto, no datos de identidad. El
servidor elige la llamada Realtime activa o su sesion de texto de laboratorio.
`GET /lab/history` expone solo el perfil configurado y ambos endpoints exigen el
token. Crear llamada y enviar mensajes se coordinan para no restaurar dos agendas
divergentes. La sesion textual se conserva entre mensajes y se cierra al pasar a
voz, agotar plazos o apagar. Su cierre invalida permisos, no borra datos de retomar.

Las propuestas incluyen canal y secuencia de ese canal. Una entrada de otra via
no consume el turno esperado de confirmacion. `manage_appointment_workflow`
retoma o inicia una gestion nueva; la via escrita exige que el texto real lo pida.
La confirmacion textual se compara con la entrada real, no solo con la decision
del modelo. El inicio de otra gestion reemplaza durablemente los datos anteriores.

`response.output_text.done` indica texto generado, no publicado. El cuerpo HTTP
completo precede a `publish_text`, que registra la emision y habilita la pregunta.
Una interrupcion previa impide armarla. Un resultado que no pudo guardarse permanece
en memoria y se finaliza al reintentar el mismo ID/cuerpo, sin otra llamada al modelo.
Al cerrar se persisten el progreso conocido y generacion `unknown` si falta un
evento final; una cancelacion solicitada no reemplaza el resultado del proveedor.

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
VoiceSession <-> OpenAI Realtime (audio nativo; WebSocket)
       |
       v
VoiceTools / politica compartida -> ToolExecutor -> CalendarProvider
       |
       v
Audio del modelo -> reproduccion cancelable -> CallMedia
       |
       +-- resultado exitoso de agenda -> entregas escritas y al doctor
```

La ruta de voz aprobada es audio nativo -> OpenAI Realtime -> audio, con
herramientas ejecutadas en el backend y transcripcion asincrona de historial.
La Raspberry conecta por WebSocket; el transporte de audio queda separado del
proveedor de voz (ADR 0056). Para el
laboratorio, `aiortc` se adopto tras la prueba en la Raspberry (ADR 0055).
No se presupone una conexion directa Meta-OpenAI
ni se aplican los limites de archivos de notas de voz al transporte WebRTC.

## Fronteras de responsabilidad

| Componente propuesto | Responsabilidad |
| --- | --- |
| `main.py` | Despachar mensajes y eventos de llamadas, validar la entrada y componer dependencias y tareas. |
| `calling_service.py` | Ocultar ciclo de llamada, capacidad, transiciones, reclamacion de eventos y cierre idempotente. |
| `whatsapp_calling_client.py` | Encapsular operaciones Calling sobre HTTP con cliente inyectable; ofrecer un doble sin red. |
| `calling_repository.py` | Encapsular sesiones, eventos, turnos y reclamaciones persistentes sin guardar audio o SDP. |
| `call_media.py` | Negociar y transportar audio, exponer conexion/cierre y cancelar reproduccion; implementacion falsa primero. |
| `voice_session.py` | Coordinar audio nativo, turnos consolidados, proveedor Realtime, historial asincrono e interrupciones. |
| `openai_realtime_provider.py` | Encapsular el protocolo GA sobre WebSocket, autenticacion y configuracion de audio/herramientas. |
| `voice_tools.py` | Validar solicitudes estructuradas y ligar propuestas/confirmaciones a sesion, turno y audio emitido. |
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

El webhook registra el evento y devuelve el ACK sin esperar negociacion ni al
modelo Realtime. Una tarea supervisada del ciclo de vida de FastAPI procesa el evento;
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

La entrada comun debe transportar origen tipado, turno de audio consolidado,
solicitud estructurada y `PatientScope`. `IncomingTextMessage` sigue siendo el adaptador de chat;
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
invalida la autorizacion y exige presentar otra version. La decision estructurada
debe pertenecer a un turno de audio posterior a la pregunta, en la misma sesion
activa. Si VAD introduce turnos intermedios cancelados, solo una transcripcion
afirmativa ligada al turno actual puede salvar la secuencia; se espera hasta 1 s y,
de no llegar una afirmacion clara, se presenta una pregunta nueva. La transcripcion
asincrona por si sola no dispara herramientas ni autoriza acciones.

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
detectar voz del paciente detiene la reproduccion; al consolidar el turno de
audio responde el modelo directamente. Descarta resultados tardios de generaciones
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
| C3 - Conversacion de voz | Dobles Realtime, WebSocket/WebRTC y muestra real con OpenAI; CA-08 y CA-09 en laboratorio. |
| C4 - Agenda y continuidad | Agenda falsa, pruebas de todos los origenes y fallos en herramientas; CA-10 a CA-14, sin efectos en Google real. |
| C5 - Meta | Numero elegible, fixtures contrastados, firma, limites y medios reales; CA-03, CA-16 y CA-17, mas escenario integrado. |

Cada implementacion se modifica localmente, se sincroniza y se ejecuta en la
Raspberry conforme a [AGENTS.md](../../../AGENTS.md). La suite existente se ejecuta
con `uv run python -m unittest discover -s tests -v`. Las pruebas de medios o
proveedores reales se ejecutan por separado y declaran su consumo y frontera.

Para el laboratorio de C2 se decidio la biblioteca y se comprobaron codecs,
arquitectura y recursos de la Pi. C3 usa OpenAI Realtime y transcripcion asincrona; se documentan
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
