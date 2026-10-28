# 011 - Notificaciones al doctor

## Estado

Verificado. Los cortes 1 a 5 estan implementados y el corte 6 fue cerrado con la
suite local, la suite de Raspberry Pi y la verificacion HTTP documentadas en
`docs/verification/2026-09-22-doctor-notifications-webhook.md`. La entrega al doctor
se ejecuta desde el webhook despues de confirmar la respuesta al paciente.

Ampliacion del 22 de octubre de 2026: chat y voz/texto de `/lab` comparten el
disparador, el compositor y la entrega. Las verificaciones y limites operativos se
registran en `docs/verification/2026-10-22-shared-doctor-notifications.md`.

El corte de configuracion de plantilla separa la captura de la disponibilidad del
envio y esta verificado con 506 pruebas en Raspberry; evidencia en
`docs/verification/2026-10-22-doctor-template-configuration.md`.
El adaptador de plantillas esta implementado para un mapeo explicito de componentes
de texto y verificado con 519 pruebas en Raspberry; evidencia en
`docs/verification/2026-10-22-doctor-template-delivery.md`.
La plantilla `aviso_cita_medico` en `es_MX` esta configurada con nueve parametros
posicionales. Su estado `APPROVED` y el contrato exacto se confirmaron por API el
25/10/2026. Una prueba directa al doctor con datos de ejemplo obtuvo el callback
real `delivered`; contrato en `approved-template.md` y evidencia en
`docs/verification/2026-10-25-approved-template-delivered.md`. No se modifico la
agenda ni se marco un aviso historico como entregado. El bloqueo `132001` del
23/10 es un antecedente resuelto para el emisor actual; `docs/whatsapp-meta-accounts.md`
conserva las comprobaciones y las incertidumbres sobre otros activos del panel.

El corte de recuperacion y reintentos durables esta verificado con 533 pruebas en
Raspberry; evidencia en `docs/verification/2026-10-22-doctor-notification-retries.md`.
El seguimiento de callbacks esta implementado mediante una bandeja durable y
proyeccion correlacionada en chat/voz, verificado con 553 pruebas en Raspberry;
evidencia en `docs/verification/2026-10-22-meta-delivery-statuses.md`.
La entrega de una prueba con la plantilla real esta confirmada por Meta. La
recuperacion de avisos historicos y cualquier prueba de una nueva operacion de
agenda son verificaciones distintas de ese diagnostico de transporte.

## Objetivo

Enviar a los doctores configurados una notificacion interna cuando una cita del
paciente de prueba sea agendada, modificada o cancelada desde la conversacion de
WhatsApp o desde voz/texto del laboratorio `/lab`.

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
- Disparador reutilizable por texto y voz: un cambio de formato, resumen,
  prioridad, destinatarios o entrega se aplica a ambas entradas.
- Registro atomico del aviso junto al resultado exitoso de laboratorio y
  recuperacion de pendientes tras reiniciar, sin repetir la operacion de agenda.

La modificacion de una cita corresponde inicialmente a una operacion exitosa de
`reschedule_appointment`.

## Requisitos funcionales

### RF-1101 - Destinatarios configurados

Uno o varios destinatarios deben ser resueltos por el backend mediante configuracion
del entorno. El LLM, el paciente y el contenido de la conversacion no pueden elegir
ni modificar esos destinatarios.

Los destinatarios deben ser validos, no repetirse y conservar el formato de numero
de WhatsApp aceptado por el canal.

La confirmacion al paciente usa su numero y el aviso interno usa exclusivamente
los doctores configurados. Si el paciente de prueba usa tambien un numero de
doctor, ambos mensajes llegan a la misma cuenta de WhatsApp, aunque su contenido
y registro sean independientes. Verificar conversaciones distintas requiere
numeros distintos para los dos roles, comparados despues de normalizarlos.

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
  El perfil ficticio de laboratorio muestra `Telefono: No informado`, sin inventar
  un numero a partir del identificador del perfil.
- Resumen de la conversacion del paciente.
- Senales de prioridad, si fueron detectadas.

El mensaje no debe incluir identificadores internos de SQLite, IDs de Google
Calendar ni credenciales.

### RF-1105 - Resumen conversacional

El resumen debe construirse con la informacion persistida de la conversacion y
debe conservar los datos relevantes para la atencion del doctor. No debe presentar
un diagnostico, una recomendacion clinica ni una transcripcion completa como si
fuera una nota clinica.

Debe sintetizar lo que el paciente conto: motivo de consulta, molestias, dudas y
detalles relevantes expresados para su atencion. No debe repetir la fecha, el
horario, la zona horaria, el estado ni la confirmacion de la cita, incluso si esos
datos aparecen en el historial. Si solo se expreso un motivo general, basta con
resumir esa solicitud sin inventar sintomas ni informacion adicional.

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

El estado de control `status=sent` significa que Cloud API acepto la solicitud y
devolvio un ID; no acredita entrega al telefono. `delivery_status` distingue
`accepted`, `sent`, `delivered`, `read` y `failed`, y `api_accepted_at` conserva la
aceptacion incluso ante un rechazo posterior. Los callbacks y su proyeccion se
persisten como define RF-1115. La activacion real espera nombre, idioma y mapeo
aprobados y credenciales vigentes.

### RF-1108 - Idempotencia

Cada entrega debe relacionarse con una identidad estable del evento de agenda y con
su destinatario. El reenvio del webhook o la repeticion del ciclo de respuesta no
debe enviar dos veces la misma notificacion al mismo doctor.

### RF-1109 - Configuracion segura

La funcionalidad debe poder permanecer deshabilitada durante el desarrollo. Cuando
se habilite, el backend debe validar que exista al menos un destinatario configurado
y no debe guardar credenciales en la base ni en el repositorio.

### RF-1111 - Disparador compartido entre texto y voz

Ambas entradas convierten el resultado tipado exitoso con la misma funcion de
dominio y usan `DoctorNotificationTrigger`, `DoctorNotificationComposer` y
`DoctorNotificationDeliveryService`. El canal solo adapta el contexto y la
persistencia de origen; no mantiene otra plantilla ni reglas de destinatarios.

En `/lab`, el resultado y el evento pendiente se guardan en la misma transaccion
de la SQLite exclusiva de voz. El nombre y los limites de historial se conservan
por evento; solo se usa texto disponible de esa sesion y gestion hasta la
confirmacion, sin incluir respuestas incompletas del asistente. Iniciar
explicitamente otra gestion establece un nuevo limite persistido y excluye los
sintomas de la solicitud abandonada. El envio ocurre
en una tarea del lifespan independiente del audio, al guardar una mutacion, al
arrancar el proceso y cada 60 segundos mientras haya pendientes. Fallar o reintentar
el aviso nunca vuelve a invocar la herramienta de agenda.

Se reutiliza el cuerpo preparado cuando WhatsApp fallo. Si fallo la composicion,
se vuelve a componer antes de enviar: el marcador de fallo no se entrega al doctor.
Una entrega `sending` cuyo resultado es incierto permanece para conciliacion y
no se reenvia automaticamente, incluidos errores de lectura/escritura posteriores
al despacho y respuestas perdidas. Los rechazos HTTP y fallos conocidos previos
al despacho se pueden reintentar con la espera definida en RF-1114. Una bandera o
lista de doctores invalida deja el evento en su fuente persistida, sin elegir
destinatarios ni bloquear la conversacion; solo una bandera explicitamente falsa
desactiva la captura. Los
errores del transporte o de los datos de plantilla conservan la captura habilitada
y retienen los avisos como se define en RF-1112. Las credenciales
de Meta y las restricciones de mensajeria siguen siendo requisitos independientes
de la integracion del disparador.

### RF-1112 - Captura independiente de la configuracion de plantilla

`DOCTOR_NOTIFICATION_TRANSPORT` acepta `text` o `template`. Su ausencia conserva
`text` para las instalaciones existentes; el archivo de ejemplo selecciona
`template`. `DOCTOR_WHATSAPP_TEMPLATE_NAME` y `DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE`
pueden permanecer vacios durante la revision de Meta. La bandera y los numeros de
doctores conservan su contrato anterior.

Con captura habilitada y datos incompletos se persiste una entrega `pending` por
evento y doctor, con `Configuración de plantilla incompleta.` y cero intentos de
envio. El aviso se conserva antes de intentar componerlo, incluso si falta o falla
el proveedor de resumen. Un transporte desconocido o datos invalidos tambien
retienen el evento con su motivo, sin usar texto libre como respaldo.

La validacion local comprueba un nombre de 1 a 512 caracteres minusculos ASCII,
digitos o guiones bajos y un idioma de dos o tres letras minusculas, opcionalmente
seguido de `_` y dos letras mayusculas. Esta validacion es sintactica, no comprueba
que Meta admita el idioma ni que haya aprobado la plantilla o sus componentes.
Con nombre e idioma completos pero sin componentes, el estado sigue pendiente con
`Mapeo de plantilla pendiente.`. Un mapeo invalido tambien retiene el aviso.

Una retencion no cambia una entrega `sent` o `sending` incierta, no aumenta los
intentos y conserva cualquier cuerpo ya preparado. Los marcadores de composicion
pendiente o fallida nunca se consideran un cuerpo listo para enviar.

El chat conserva su evento en `reply_outbox` y solo completa las notificaciones
cuando todas se aceptan o la captura esta explicitamente deshabilitada. Un
webhook duplicado puede recuperar el aviso tras reabrir la aplicacion sin repetir
la confirmacion ni la mutacion. El laboratorio mantiene su evento pendiente para
el ciclo compartido con chat. La verificacion de entrega con la plantilla real
sigue pendiente.

### RF-1113 - Envio por plantilla con mapeo explicito

La configuracion adoptada usa el contrato de `approved-template.md`: un componente
`body` con nueve parametros de texto en orden evento, fecha, horario, motivo,
estado, nombre, telefono, resumen y prioridad. El encabezado es fijo y no requiere
un componente dinamico. Los ejemplos proporcionados por el usuario verifican el
mapeo, pero nunca sustituyen el contenido de un evento real.

`WhatsAppClient.send_template()` envia a la Cloud API el destinatario, `type=template`,
nombre, codigo de idioma y componentes proporcionados, preservando su orden y
metadatos. Comparte autenticacion, version, timeout y manejo de errores HTTP con
el envio de texto. El modo plantilla no usa texto libre como respaldo.

`DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS` contiene un arreglo JSON explicito de
componentes de texto `header`, `body` o botones `url`. Los parametros conservan su
orden y `parameter_name` opcional. `text` puede referenciar y agrupar estos datos:
`event_type`, `status`, `date`, `time`, `reason`, `patient_name`, `patient_phone`,
`summary` y `priority_signals`. `notification_body` permite referenciar el aviso
completo. Se exige cobertura de todos los datos, individualmente o mediante ese
cuerpo completo. La cantidad de componentes y variables no se deduce ni se fija
antes de conocer la plantilla aprobada. Otros tipos de componentes requieren
un contrato explicito posterior.

Solo se resuelven los campos del catalogo, sin atributos, conversiones ni
expresiones. Los parametros de texto compactan espacios, saltos y tabuladores sin
recortar los datos. El nombre y telefono, resumen y prioridad usan los mismos
valores saneados del mensaje actual; un perfil ficticio conserva `No informado`.
Ningun campo del mapeo elige el destinatario ni incorpora IDs internos.

Los datos estructurados se persisten junto al cuerpo. Nombre, idioma y componentes
concretos se congelan atomicamente al reclamar la entrega. Un reintento recupera
ese payload sin resumir ni reinterpretar el historial y sin repetir la cita,
incluso si cambia la configuracion. Un aviso historico sin datos estructurados
solo puede mapear su cuerpo completo; no se extraen campos mediante heuristicas.
Si falta un campo requerido, queda pendiente sin intentar el envio.

Una aceptacion de plantilla requiere un ID de Meta para marcar `sent`; una
respuesta sin ID o perdida conserva `sending` incierto y exige conciliacion.
Los callbacks se correlacionan segun RF-1115. La aceptacion de la API no acredita
entrega al telefono.

### RF-1114 - Recuperacion durable y control de reintentos

Chat y laboratorio recuperan avisos al arrancar y cada 60 s. El chat inicia su
bandeja de forma diferida si aun no existe SQLite, para no crear identidades o
datos por consultar salud/webhooks vacios. La recuperacion usa solo eventos
registrados en `reply_outbox`, `voice_notification_events` o las entregas, sin
volver a invocar herramientas de agenda ni responder otra vez al paciente.

Cada evento congela sus destinatarios al registrarse. Cambiar la lista de doctores
no agrega entregas retroactivas; retirar un destinatario detiene la suya. La clave
unica `(event_key, recipient_number)` y la reclamacion atomica evitan duplicados
incluso con recuperacion concurrente o un webhook repetido.

Se conservan `event_json` y un contexto acotado y congelado antes de componer. Un
perfil o historial actualizado despues no reemplaza el contexto del aviso. La
bandeja por destinatario se puede recuperar aunque la fuente ya este completada.
Los eventos sin destinatario valido permanecen en la fuente hasta corregir la
configuracion. No se reconstruyen eventos faltantes desde citas actuales.

`next_attempt_at`, `retry_kind`, `blocked_configuration_key` y `failure_count`
persisten el control. Conexion previa al despacho, 429/5xx y codigos transitorios
de Meta usan espera exponencial de 60 s hasta 3600 s, respetando `Retry-After`
hasta 24 h. La composicion fallida tambien espera, conservando cero intentos de
WhatsApp mientras no se despache. Un rechazo de configuracion/autenticacion
detiene los intentos hasta cambiar los datos relevantes o conciliar una correccion
externa. Se compara una huella no reversible sin persistir credenciales literales.

Una respuesta perdida, sin ID o un proceso interrumpido durante el despacho queda
`sending` incierto y nunca se libera por tiempo. La conciliacion explicita exige
numero de intento y referencia a una comprobacion externa: `accepted` requiere ID
de Meta; `not_delivered` habilita el reintento tras comprobar que no hubo entrega.
`configuration_fixed` permite liberar un bloqueo cuya correccion fue externa.
Los resultados tardios de un intento anterior no reemplazan la conciliacion ni
el estado de un intento posterior.

`doctor_notification_attempts` conserva cada despacho, su contenido, payload,
revision local de plantilla, ID del proveedor, clasificacion y conciliacion. Un
reintento transitorio conserva su payload. Tras un rechazo conocido de configuracion,
una correccion puede preparar otro payload, sin perder el intento anterior.
La revision local no representa una revision de Meta no proporcionada. Los
fallos historicos sin clasificacion quedan detenidos para revision; las
migraciones no inventan intentos pasados ni cambian sus resultados.

### RF-1115 - Confirmaciones asincronas de Meta

El webhook reconoce `statuses` en todas las entradas/cambios, incluidos eventos
mixtos con mensajes. Un callback valido requiere ID del mensaje, destinatario,
estado soportado y timestamp Unix valido. Los numeros mexicanos se normalizan
igual que los destinatarios. Se guardan estados `sent`, `delivered`, `read` y
`failed`; `accepted` solo se genera al obtener o conciliar un ID de la API.

La bandeja central `whatsapp_delivery_receipts` persiste el callback antes del
ACK: identidad canonica, ID, destinatario, estado, fecha, cuenta emisora cuando
exista y codigos numericos. No guarda texto crudo de errores ni dispara el LLM o
WhatsApp. Un fallo de persistencia devuelve HTTP 503; si el almacenamiento fue
correcto pero la proyeccion esta pendiente, la recepcion puede responder 200.

La proyeccion correlaciona ID **y** destinatario en el historial de intentos de
chat/voz. Un aviso historico con ID y sin auditoria tambien se puede actualizar,
sin inventar intentos. Un match ambiguo o desconocido permanece pendiente; no se
deduce el aviso por telefono. Los callbacks de respuestas al paciente se reconocen
como ajenos al aviso interno, aunque paciente y doctor usen el mismo numero.

El procesamiento posterior a la respuesta y un ciclo de lifespan al arrancar y
cada 5 s reintentan la proyeccion. La bandeja sobrevive a reinicios y a que el
callback se adelante al guardado del ID. Si la respuesta se perdio definitivamente,
espera el ID recuperado mediante conciliacion. La base de voz se abre sin crear
tablas de pacientes ni activar/inicializar sesiones de voz.

La clave de evento evita duplicados exactos. El estado efectivo tiene este orden
de evidencia: `read`, `delivered`, `failed`, `sent`, `accepted`. Un callback tardio
no retrocede el estado ni su timestamp del mismo nivel; todos los hechos permanecen
en el historial. Cada intento conserva su propia proyeccion y solo el intento
actual modifica el control y `delivery_status` del aviso. El ACK de proyeccion
solo marca las entradas del snapshot procesado, no otras llegadas concurrentes.

Un `failed` del intento actual conserva aceptacion e ID y activa una sola vez la
espera transitoria o el bloqueo de configuracion con los datos de ese intento.
Los errores repetidos no duplican el contador ni desplazan la espera. Una
confirmacion `delivered`/`read` cancela el reintento del intento actual y reinicia
el contador; una mera aceptacion de API no reinicia la espera acumulada de fallos
asincronos. Los callbacks de intentos antiguos no reprograman el actual.

La migracion solo asigna `accepted` a historicos con ID ya aceptados localmente;
no deriva entrega o lectura de un HTTP 200 ni inventa callbacks.

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
15. Para una revision de los ojos, el resumen describe la solicitud del paciente sin
    repetir `19/10/2026, de 14:00 a 14:30 (UTC−06:00)` ni confirmar otra vez la cita;
     los datos operativos se presentan en los bloques correspondientes del mensaje.
16. Crear, reprogramar y cancelar por voz producen automaticamente el mismo formato
    de aviso usado por el chat; propuestas, rechazos y fallos de agenda no lo producen.
17. Un reinicio recupera avisos pendientes de laboratorio y reintenta solo la entrega;
    un resumen fallido nunca termina enviando el marcador de error como aviso.
18. Dos intentos concurrentes no envian una fila ya reclamada por otro intento.
19. Con numeros distintos, el paciente recibe su confirmacion sin resumen ni
    señales internas y el doctor recibe el aviso completo. Con un numero compartido,
    los dos cuerpos siguen separados y se dirigen a la misma cuenta configurada;
    un webhook duplicado no repite ninguno de los dos envios.
20. En modo plantilla con nombre o idioma vacios, el paciente recibe su confirmacion
    y el aviso queda pendiente con su motivo y cero intentos, incluso sin resumidor.
21. La retencion sobrevive a reabrir la aplicacion y a los duplicados del webhook;
    recuperar el aviso no repite la cita ni la respuesta al paciente.
22. Datos mal formados o un transporte desconocido conservan el aviso; los datos
    completos no causan un envio de texto libre ni se presentan como aprobacion de Meta.
23. Crear, reprogramar y cancelar entregan la plantilla al doctor con todos los
    datos disponibles y mantienen la confirmacion al paciente en su propia ruta.
24. Reintentar tras reiniciar reutiliza datos y componentes congelados, incluso
    sin resumidor y con otra configuracion, sin duplicar avisos ni operaciones.
25. La migracion de las bases de chat y voz agrega snapshots opcionales sin cambiar
    el contenido, destinatario o estado de los avisos historicos.
26. El chat recupera un aviso sin otro mensaje del paciente y preserva el nombre y
    contexto originales tras reiniciar, sin repetir la cita ni su confirmacion.
27. Un fallo recuperable no se reintenta antes de su fecha persistida; un rechazo
    de configuracion no se reintenta con la misma configuracion, aunque pase el tiempo.
28. Un resultado incierto solo puede volver a despacharse tras una conciliacion de
    no entrega comprobada; una aceptacion conciliada nunca se reenvia.
29. La auditoria conserva el payload de cada intento, incluida una plantilla rechazada
    y la configuracion corregida, y rechaza conciliaciones de intentos obsoletos.
30. Un HTTP 200 queda como `accepted`; un callback `failed/131047` puede registrar
    fallo y bloqueo conservando la aceptacion y sin repetir el envio automaticamente.
31. Callbacks duplicados, fuera de orden o simultaneos no pierden eventos ni
    retroceden lectura, entrega o timestamp del mismo estado.
32. Un callback temprano o temporalmente no correlacionable se aplica despues de
    guardar el ID o recuperar el destino, sin exigir otra entrega del webhook.
33. El webhook actualiza un aviso de voz sin crear conversaciones ni ejecutar
    herramientas, y la conciliacion preserva el esquema exclusivo de voz.

## Fuera del alcance

- Enviar un resumen independiente despues de cada mensaje.
- Disparar notificaciones por cierre automatico o inactividad de la conversacion.
- Canales para el doctor distintos de WhatsApp Cloud API.
- Enrutamiento de notificaciones por especialidad, paciente o tipo de doctor.
- Un sistema de colas distribuido o multiples trabajadores.
- Uso con pacientes reales antes de definir privacidad, consentimiento y limites
  para informacion medica.
