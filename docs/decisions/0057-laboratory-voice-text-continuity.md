# 0057 - Continuidad de voz y texto para el paciente ficticio

## Estado

Aceptada e implementada el 19 de octubre de 2026. Verificada con 445 tests,
Chromium/WebRTC con doble y Chrome/Mac con OpenAI real, voz y texto antes/despues
de colgar. [Evidencia](../verification/2026-10-19-voice-text-controls.md).
El usuario eligio un paciente ficticio, sin vincular el navegador a un paciente
operativo de WhatsApp.

## Decision

La pagina `/lab` agrega mensajes de texto. Desde el 20 de octubre el acceso al
laboratorio es directo, sin token, conforme a la actualizacion de ADR 0055.
Voz y texto comparten el
perfil fijado por el servidor, el historial y la agenda falsa. Ambos entran en el
modelo Realtime y sus solicitudes pasan por las mismas reglas del backend. La
voz conserva entrada de audio directa y transcripcion paralela.

Cada entrada identifica canal, turno global y secuencia del canal. Una pregunta
emitida por voz no puede confirmarse mediante un `si` escrito, ni viceversa. El
traspaso explicito conserva datos, revalida agenda y genera otra propuesta,
pregunta e identidad de accion en el canal nuevo. Otra llamada tampoco hereda
autorizaciones. Los mensajes de otro canal no consumen la secuencia del propietario.

Si existe una llamada activa, el texto usa su sesion y ejecutor. Sin llamada se
crea una sesion Realtime temporal de texto, reutilizada entre mensajes hasta
inactividad, duracion maxima, transicion a voz o apagado.
La exclusion mutua de creacion/mensajeria evita restaurar dos agendas falsas
divergentes. El historial persiste origen, generacion y emision por separado;
el texto publicado en el laboratorio no representa entrega de WhatsApp.

Los IDs de mensajes son idempotentes por perfil. Una transcripcion tardia modifica
el turno original y su contenido de historial; nunca ejecuta una herramienta,
renueva una confirmacion ni se agrega como otra intervencion.

La generacion de texto no arma una confirmacion: se publica primero el cuerpo
HTTP completo y despues se registra la pregunta como emitida. Las respuestas
pendientes de escritura se conservan para reintentar el mismo mensaje sin ejecutar
otra vez el modelo o sus herramientas. Una gestion nueva marca propuestas previas
como reemplazadas; retomar no puede recuperarlas como si estuvieran pausadas.

Una solicitud de cancelacion no prueba que la generacion se cancelara. Su estado
final se toma del proveedor; si falta el resultado se conserva `unknown`. Al
colgar se guardan tambien duraciones generadas/emitidas y la emision interrumpida.

La continuidad entre el bot de WhatsApp y pacientes operativos conserva su corte
propio. Este laboratorio prueba las reglas de canal con una identidad sintetica.

### Recuperacion de una pregunta interrumpida (20 de octubre de 2026)

Al empezar a responder antes del fin de la pregunta, se invalida su autorizacion
pero se conservan en la llamada los datos de esa propuesta interrumpida. Si el
modelo intenta confirmar su identificador en el mismo canal, el backend revalida
la agenda y devuelve `confirmation_required` con otra accion y otra pregunta. Ese
intento no ejecuta la reserva; hace falta emitir la nueva pregunta completa y
recibir otra afirmacion en el turno posterior. No se comunica perdida de sesion
ni se vuelven a pedir nombre y motivo por esa interrupcion.

Un identificador ajeno u otro canal no recuperan automaticamente la propuesta.
Rechazar, corregir, iniciar otra gestion o cerrar descartan la recuperacion local;
el cambio de canal o llamada conserva el mecanismo explicito de retomar existente.
Se mantiene el contrato de CA-11 sin tolerancias temporales para aceptar audio
incompleto. Ver [diagnostico y regresion](../verification/2026-10-20-interrupted-booking-confirmation.md).

### Recuperacion ante turnos de voz intermedios cancelados (20 de octubre de 2026)

Realtime puede consolidar un turno VAD breve y cancelar su respuesta cuando llega
la afirmacion del paciente como un turno posterior. Si la pregunta de cita ya fue
emitida completa y la propuesta aun vive en la misma llamada/canal, el salto de
secuencia no autoriza ejecutar ni debe dejar al paciente en un bucle de error:
se revalidan datos y disponibilidad, se reemplaza la accion y se emite una pregunta
nueva. Solo una afirmacion en el turno siguiente a esa nueva pregunta ejecuta.
Una accion ausente, un ID ajeno o un canal diferente no acceden a esta recuperacion.
El plazo maximo de la sesion no relaja la autorizacion ligada al turno inmediato.

## Consecuencias

Los mensajes sin llamada pueden consumir una sesion de OpenAI y cuentan en la
cuota por perfil/base. Texto e historial usan el mismo acceso loopback/SSH. No
se introduce otro proveedor de IA ni una cadena STT/agente/TTS para la voz.
