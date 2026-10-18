# Llamadas entrantes de WhatsApp

## Estado

Borrador para revision, preparado el 18 de octubre de 2026. El usuario solicito
comenzar por la especificacion, el diseno y las tareas. Esta entrega es documental:
no implementa Calling, no instala dependencias de audio y no acredita una llamada real.
Los cortes de implementacion permanecen pendientes en [tasks.md](./tasks.md).

## Problema y objetivo

Un paciente de prueba debe poder iniciar una llamada desde WhatsApp y conversar
en español con el bot para gestionar sus citas. Hoy el backend procesa mensajes
de texto; no recibe sesiones de llamada ni transporta audio continuo.

Se necesita avanzar sin comprar todavia una linea ni habilitar otro numero en
Meta. Primero se verificaran el control de llamadas con dobles, el audio en un
laboratorio y la integracion con la agenda falsa. La conexion con Meta sera un
corte posterior con su propia evidencia.

## Alcance

- Llamadas de voz iniciadas por el paciente dentro de WhatsApp.
- Aceptar, rechazar y terminar llamadas; registrar su resultado y liberar recursos.
- Simular el ciclo completo sin numero, credenciales de Calling o consumo de APIs.
- Probar audio bidireccional en laboratorio y despues conversar mediante
  transcripcion, bot existente y sintesis de voz.
- Reutilizar identidad, reglas y herramientas de agenda, agregando confirmacion
  verbal antes de crear, reprogramar o cancelar una cita.
- Continuar una gestion entre chat y llamadas sin transferir su autorizacion.
- Confirmacion hablada del resultado y seguimiento escrito por WhatsApp en el
  corte conectado, conforme a las reglas de mensajeria vigentes.

El piloto sigue usando pacientes y datos de prueba. Las credenciales y servicios
reales solo son necesarios para los cortes que los ejercitan.

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
- **CA-08 — Intervencion final e interrupcion.** Solo una transcripcion final
  valida puede avanzar la gestion. Recibir varias revisiones del mismo turno no
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
  La pregunta debe haberse emitido completa antes de aceptar la autorizacion.
  Una afirmacion durante una pregunta interrumpida solicita una nueva confirmacion.
- **CA-12 — Vigencia contextual.** La autorizacion expira a los 10 minutos como
  maximo, y antes si cambia un dato, se pausa o reemplaza la gestion, se cambia de
  canal, termina la llamada o se reinicia el backend. Un `Si` de otra llamada,
  del chat o de una transcripcion tardia no ejecuta la accion. Una correccion
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

Antes del corte de audio se verificaran biblioteca, codecs y compatibilidad de la
Raspberry. Antes de probar voz de pago se seleccionaran proveedor y modelos y se
documentaran sus credenciales y consumo. Antes del corte conectado se verificaran
version de API, eventos y limites vigentes, elegibilidad del numero, configuracion
de Calling y conectividad de medios. Estas dependencias no bloquean la simulacion
ni convierten una tecnologia candidata en una decision adoptada.
