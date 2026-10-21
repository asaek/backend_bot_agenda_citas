# Llamadas entrantes de WhatsApp

## Estado

El 18 de octubre de 2026 se aprobo implementar la compatibilidad de `aiortc`,
control de sesiones, medios, saludo preparado y senalizacion HTTP de laboratorio
(A-E). Ese alcance esta implementado y tiene verificacion automatizada de medios
y navegador en la Pi y entre computadora/Pi en LAN; la escucha fisica y el
microfono real siguen pendientes.
El resto de Calling conserva estado
de propuesta; no se acredita una llamada Meta. El avance y las verificaciones
se registran en [tasks.md](./tasks.md).

El 19 de octubre se implemento conversacion de laboratorio con OpenAI Realtime:
audio nativo, transcripcion asincrona, herramientas controladas y agenda falsa
persistente por defecto. Se verificaron audio real y una consulta desde Chrome en
macOS. Desde el 20 de octubre, `VOICE_CALENDAR_PROVIDER=google` permite que la
misma pagina HTML escriba en Google Calendar con un propietario de laboratorio
separado (ADR 0058). La identidad sigue siendo ficticia; no es continuidad ni
atencion de pacientes operativos. Dobles HTTP verifican crear, listar, reprogramar
y cancelar; en la Pi se comprobo salud y disponibilidad Google de solo lectura, sin
crear un evento operativo. Ver
[`2026-10-20-voice-google-calendar.md`](../../verification/2026-10-20-voice-google-calendar.md).
La conexion Calling sigue pendiente.

La continuidad de laboratorio aprobada en ADR 0057 permite mensajes escritos en
`/lab` con el mismo perfil ficticio. Canal y secuencia los fija el servidor. Un
`si` cruzado no confirma otra via; retomar conserva datos y revalida, pero crea
otra propuesta/pregunta/autorizacion. Texto, voz e historial asincrono comparten
el contexto sin convertir una transcripcion en otro turno ni en una herramienta.

El laboratorio se implementa como aplicacion FastAPI separada, con SQLite de
prueba, habilitacion explicita y acceso por loopback/SSH sin token. Puede verificar
el control y los medios sin completar
antes el cliente o los eventos simulados de Meta de C1; no declara C1 completo.
Su API expone `POST /lab/calls`, `GET /lab/calls/{session_id}` y
`DELETE /lab/calls/{session_id}` solo en ese proceso. El backend de texto no
publica esas rutas. La muestra de entrada debe decodificarse y contener senal;
el saludo distingue preparado, reproduciendo, completado, interrumpido y fallido.

El cliente distingue senalizacion HTTP, conectividad ICE, paquetes
RTP y reproduccion. `GET /lab/health` permite comprobar HTTP sin crear una llamada.
Desde el 20 de octubre no se pide token en el cliente ni en la API de laboratorio,
incluidos mensajes e historial. **Conectar e iniciar llamada** comprueba HTTP
automaticamente y establece la llamada; **Colgar** cierra la sesion y permite
volver a conectar. El microfono exige HTTPS o localhost y
presenta un error explicativo en un origen no confiable. La primera ruta entre
equipos usa la misma LAN y un tunel SSH para servir el cliente en localhost;
los medios viajan directamente, sin STUN/TURN. El tunel HTTP de ngrok no prueba
conectividad de audio. La escucha humana sigue siendo un criterio separado.

## Problema y objetivo

Un paciente de prueba debe poder iniciar una llamada desde WhatsApp y conversar
en español con el bot para gestionar sus citas. El backend operativo procesa
mensajes de texto. El laboratorio separado ya transporta audio continuo con
Realtime, sin recibir todavia sesiones de llamada de Meta.

Se necesita avanzar sin comprar todavia una linea ni habilitar otro numero en
Meta. Primero se verificaran el control de llamadas con dobles, el audio en un
laboratorio y la integracion con la agenda falsa. La conexion con Meta sera un
corte posterior con su propia evidencia.

## Alcance

- Llamadas de voz iniciadas por el paciente dentro de WhatsApp.
- Aceptar, rechazar y terminar llamadas; registrar su resultado y liberar recursos.
- Simular el ciclo completo sin numero, credenciales de Calling o consumo de APIs.
- Probar audio bidireccional en laboratorio y despues conversar mediante
  un modelo de voz nativa que recibe audio y genera audio en tiempo real.
- Reutilizar identidad, reglas y herramientas de agenda, agregando confirmacion
  verbal antes de crear, reprogramar o cancelar una cita.
- Continuar una gestion entre chat y llamadas sin transferir su autorizacion.
- Confirmacion hablada del resultado y seguimiento escrito por WhatsApp en el
  corte conectado, conforme a las reglas de mensajeria vigentes.

El piloto sigue usando pacientes y datos de prueba. Las credenciales y servicios
reales solo son necesarios para los cortes que los ejercitan.

La arquitectura de voz aprobada usa OpenAI Realtime desde la Raspberry, audio
nativo bidireccional y herramientas controladas por el backend (ADR 0056). El
alcance inicial conserva identidad falsa, historial propio y agenda falsa por
defecto. El modo Google escribe eventos de laboratorio reales en los calendarios
configurados, con `managed_by=whatsapp_voice_lab`; el adaptador de WhatsApp usa su
propietario distinto y no los presenta a pacientes. La continuidad y las entregas
sobre pacientes operativos siguen en C4/C5.

## Fuera de este incremento

- Llamadas salientes, devoluciones de llamada y permisos para iniciarlas.
- Llamadas de la aplicacion Telefono, red telefonica convencional o portabilidad.
- Notas de voz, video, grabacion permanente y transferencia en vivo al doctor.
- Migracion del remitente a Twilio u otro proveedor de mensajeria.
- Habilitar el numero de prueba de Meta por suposicion, comprar una linea o cambiar
  el estado de una cuenta Meta durante la especificacion.
- Atencion de pacientes reales, diagnostico y despliegue de produccion.

## Conceptos e invariantes

El vocabulario propuesto esta en [CONTEXT.md](../../../CONTEXT.md).

1. Una **conversacion del paciente** conserva la continuidad de su atencion y
   puede abarcar varios mensajes y sesiones de llamada.
2. Una **sesion de llamada** representa una conexion concreta; volver a llamar
   crea otra sesion. Terminarla no cierra por si solo la conversacion.
3. Un **turno de voz** contiene una intervencion finalizada y su respuesta.
   Los fragmentos y revisiones parciales de transcripcion no son turnos nuevos.
4. Una **gestion pendiente** sigue siendo unica por conversacion, activa o pausada.
   Sus datos pueden retomarse; su autorizacion queda ligada al canal, a la sesion
   si es voz y a la version exacta de la accion presentada.
5. La identidad se resuelve desde el origen confiable de la comunicacion. El nombre
   dicho, un telefono dictado o los argumentos del LLM no cambian el paciente.

## Requisitos y criterios de aceptacion

### Control de llamadas

- **CA-01 — Activacion incremental.** Calling esta deshabilitado por defecto.
  En ese estado, la salud, la verificacion del webhook y los flujos actuales de
  texto y agenda conservan su comportamiento, sin requerir dependencias de audio.
- **CA-02 — Simulacion independiente.** Con persistencia temporal y clientes
  falsos se completa recepcion, aceptacion y finalizacion sin acceder a Meta,
  Google o proveedores de IA. La evidencia identifica el modo simulado.
- **CA-03 — Entrada confiable y capacidad.** El modo conectado valida firma,
  numero empresarial destinatario e identidad del llamante antes de crear efectos.
  Un evento invalido no crea paciente ni sesion. El piloto admite una llamada
  activa por paciente y una global; una segunda llamada se rechaza sin afectar la
  primera. Los mensajes de otros pacientes pueden seguir procesandose.
- **CA-04 — Reintentos y orden.** Duplicar eventos no duplica aceptaciones,
  sesiones, respuestas o herramientas. Una terminacion recibida antes de la
  conexion impide activar despues esa llamada. Distintos eventos de una misma
  llamada se procesan individualmente: su identificador no descarta todo el ciclo.
- **CA-05 — Recepcion y trabajo supervisado.** El webhook confirma la recepcion
  despues de registrar o reconocer el evento, sin esperar el audio ni una respuesta
  de IA. Si no puede registrar el evento, no devuelve una recepcion exitosa.
  Tras reiniciar, las llamadas no terminales quedan interrumpidas y no se reanudan
  ni repiten sus operaciones automaticamente.
- **CA-06 — Finalizacion.** Colgar, rechazar, agotar el tiempo de negociacion o
  perder audio deja un estado terminal y libera tareas, conexiones y buffers.
  Los turnos tardios no reactivan la llamada. Finalizar dos veces es inocuo.

### Audio y turnos

- **CA-07 — Saludo de laboratorio.** Un interlocutor de laboratorio establece
  audio en ambos sentidos, envia una muestra y recibe un saludo completo en
  español que identifica al asistente virtual. Desconectarse durante el saludo
  libera la sesion. Esta prueba se registra como laboratorio, no como Meta.
- **CA-08 — Intervencion final e interrupcion.** Solo un turno de audio consolidado
  y una solicitud estructurada validada pueden avanzar la gestion. La transcripcion
  asincrona completa el historial, no autoriza acciones. Varias revisiones del turno no
  lo ejecuta otra vez. Al interrumpir al bot, se detiene el audio pendiente; una
  respuesta generada para un turno reemplazado no se reproduce mas tarde.
- **CA-09 — Identidad e historial.** Texto y voz reconocen al mismo paciente de
  prueba y conservan el origen de sus turnos. Una respuesta generada, una
  reproducida parcialmente y una emitida completa tienen resultados distinguibles.
  Ninguna se registra como un mensaje de WhatsApp entregado por el hecho de hablar.

### Continuidad y autorizaciones

- **CA-10 — Cambio de canal.** Iniciar una llamada no consume ni confirma la
  gestion del chat. `Retomemos la cita` puede transferir sus datos al nuevo canal,
  previa revalidacion de agenda; invalida cualquier autorizacion anterior y emite
  la pregunta que corresponda. Un `Si`, nombre, motivo u horario aislado de otro
  canal no avanza la gestion pendiente. Una gestion nueva explicita puede
  reemplazarla, invalidando la anterior.
- **CA-11 — Confirmacion verbal.** Crear, reprogramar o cancelar requiere
  presentar la operacion y sus datos, y recibir una afirmacion explicita posterior
  en la misma llamada. Para reservar se repiten nombre completo, fecha, hora y
  motivo; para cambios se identifica la cita y, al reprogramar, el nuevo horario.
  Las preguntas expresan primero la hora de inicio en formato de 12 horas con
  AM/PM y despues la fecha en orden dia/mes/año (`DD/MM/YYYY`), conforme al
  español de México; por ejemplo: `a las 10:00 AM del 19/10/2026`.
  La pregunta debe haberse emitido completa antes de aceptar la autorizacion.
   Una afirmacion durante una pregunta interrumpida solicita una nueva confirmacion.
   En laboratorio, intentar confirmar esa propuesta en la misma llamada y canal
   conserva nombre, motivo y horario, revalida la agenda y devuelve una pregunta
   con identificador nuevo; no responde que se perdio la sesion ni exige recapturar
    los datos. Solo la afirmacion posterior a la nueva emision completa ejecuta.
    Si Realtime divide una afirmacion y cancela una respuesta intermedia, el
    backend asocia la transcripcion a la intervencion de voz vigente. Puede aceptar
    una secuencia VAD posterior solo si esa transcripcion confirma inequivocamente
    la accion pendiente y la pregunta original se emitio completa. Espera hasta un
    segundo por la transcripcion; si falta, falla o es ambigua, renueva la pregunta
    sin mutar la agenda. Una transcripcion de otro turno nunca autoriza la accion.
- **CA-12 — Vigencia contextual.** La autorizacion expira a los 10 minutos como
  maximo, y antes si cambia un dato, se pausa o reemplaza la gestion, se cambia de
  canal, termina la llamada o se reinicia el backend. Un `Si` de otra llamada,
  del chat o de una transcripcion de otro turno no ejecuta la accion. Una correccion
  genera una version nueva que debe presentarse y confirmarse de nuevo.
- **CA-13 — Resultado de agenda.** La operacion se reclama una sola vez y se
  revalida contra la agenda antes de ejecutarse. Si la llamada termina antes de
  reclamarla, no se ejecuta. Si ya se inicio, se conserva su resultado, incluso
  si el paciente cuelga. Un resultado externo incierto no se reintenta a ciegas:
  se consulta o concilia el estado antes de permitir otra ejecucion.
- **CA-14 — Resultado comunicado.** El bot solo anuncia una cita creada,
  reprogramada o cancelada tras el exito de la herramienta. Un fallo de voz o de
  entrega posterior no deshace la cita ni vuelve a ejecutarla. Los eventos para
  notificar al doctor corresponden solo a operaciones exitosas y no se duplican.

### Configuracion y verificaciones

- **CA-18 — Rendimiento y presupuesto del laboratorio.** Cada sesion conserva
  latencia hasta primer audio recibido y emitido localmente, corte de cola local,
  duracion de herramientas, CPU/memoria del proceso y acumulacion de audio. Se
  explicita el punto inicial: evento VAD recibido, o commit si falta aquel. La
  primera emision local no se presenta como reproduccion en el Mac. Con muestras
  conocidas se mide por separado fin del archivo -> primera señal en el reproductor
  del navegador. Los percentiles incluyen numero de muestras y separan turnos con
  herramientas; las metas fin de habla -> audio son p50 <= 1500 ms y p95 <= 3000 ms,
  objetivos de evaluacion, no garantias inferidas de una muestra. El costo estimado
  incluye audio, texto, cache y transcripcion con tarifa/modelo/fecha identificados;
  si falta desglose o tarifa no se inventa un total ni se interpreta como gratuito.
  El presupuesto inicial de referencia es 5 USD; las cuotas de sesiones no son un
  limite monetario del proveedor. La escucha/microfono humanos requieren su propia
  comprobacion y no se deducen de la reproduccion automatizada.

- **CA-19 — Proveedor de agenda del laboratorio.** `VOICE_CALENDAR_PROVIDER`
  acepta `fake` o `google` y usa `fake` si se omite. En modo Google, disponibilidad,
  creacion, listado, reprogramacion y cancelacion usan los calendarios y credenciales
  configurados. Los eventos tienen propietario `whatsapp_voice_lab`, por lo que el
  backend de WhatsApp no puede listarlos ni modificarlos como citas de un paciente,
  incluso si ambos usan el mismo calendario. `/lab/health` y la pagina HTML indican
  el proveedor activo y si las confirmaciones escriben eventos reales. El perfil
  sigue siendo ficticio y las citas falsas anteriores no se importan.

- **CA-20 — Cuota configurable y visible.** `VOICE_MAX_SESSIONS` acepta 1-100 o
  `unlimited`, con default 5. Al alcanzar un maximo numerico, la API rechaza la
  llamada con HTTP 429 y el limite utilizado/permitido. El error no se etiqueta
  como fallo de microfono o SDP; no abre Realtime ni una cita y reiniciar no
  reinicia el contador durable. `unlimited` desactiva solo la cuota total de
  sesiones; no cambia los topes por duracion/inactividad. No hay cuota diaria aun.

- **CA-21 — Cuota diaria antes de uso operativo (pendiente).** Antes de usar voz
  con pacientes operativos se debe definir e implementar un limite diario por
  perfil, su zona horaria y su persistencia. `VOICE_MAX_SESSIONS=unlimited` no
  satisface este criterio y queda restringido al laboratorio de pruebas.

- **CA-15 — Datos de la prueba.** Los dobles usan identidades y audio de prueba.
  El audio permanece en buffers temporales y se descarta al cerrar. Los logs no
  contienen audio, transcripciones, SDP, credenciales ni cuerpos de proveedores;
  registran modo, correlacion y resultados operativos seguros.
- **CA-16 — Conexion real posterior.** El cierre con Meta exige numero
  registrado y Calling habilitado, una llamada iniciada desde otro WhatsApp,
  saludo, audio bidireccional, conversacion y una gestion de cita verificable.
  El seguimiento escrito respeta la ventana de atencion o usa una plantilla
  aprobada. Si falta la plantilla necesaria, queda una entrega pendiente sin
  repetir la operacion de agenda ni afirmar que se envio el mensaje.
- **CA-17 — Evidencia por frontera.** Cada corte declara si verifico simulacion,
  transporte de laboratorio, proveedor de voz real o Meta. La suite existente
  sigue pasando. No se declara el incremento integrado con WhatsApp a partir
  de eventos falsos o de un HTTP 200 del webhook.

## Escenarios minimos de continuidad

| Situacion | Resultado esperado |
| --- | --- |
| El chat espera confirmar una cancelacion y entra una llamada | Saludo sin cancelar; un `Si` hablado no consume la confirmacion del chat. |
| El paciente retoma esa cancelacion por voz | Se identifica otra vez la cita y se emite una pregunta nueva en esa llamada. |
| La llamada espera confirmar una reserva y llega `Si` por chat | No se reserva; se pide continuar en el canal propietario o retomar explicitamente. |
| El paciente cuelga y vuelve a llamar | Nueva sesion; puede retomar datos, pero necesita otra pregunta y autorizacion. |
| Corrige la hora mientras escucha la confirmacion | Se detiene la pregunta anterior, se revalida el horario y se presenta una version nueva. |
| Cuelga despues de iniciar una reserva confirmada | Se conserva el resultado real; volver a llamar no dispara otra reserva. |
| Reinicia el servidor con una mutacion en curso | La llamada queda interrumpida y la operacion incierta requiere conciliacion. |

## Dependencias y pendientes delimitados

La especificacion usa las fronteras de persistencia, agenda, identidad y reintentos
existentes. [design.md](./design.md) define su evolucion y la
[ADR 0054](../../decisions/0054-inbound-calling-with-scoped-confirmation.md)
registra la propuesta arquitectonica.

La compatibilidad de biblioteca, codecs y Raspberry del laboratorio se verifico
en la [evidencia del 18 de octubre](../../verification/2026-10-18-aiortc-audio-laboratory.md)
y se adopto en la ADR 0055. Antes de probar voz de pago se seleccionaran proveedor y modelos y se
documentaran sus credenciales y consumo. Antes del corte conectado se verificaran
version de API, eventos y limites vigentes, elegibilidad del numero, configuracion
de Calling y conectividad de medios. Estas dependencias no bloquean la simulacion
ni convierten una tecnologia candidata en una decision adoptada.
