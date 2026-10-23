# Tareas - Llamadas entrantes de WhatsApp

## Estado y orden

Definicion documental preparada el 18 de octubre de 2026. C0 corresponde a esta
entrega. El usuario aprobo despues el laboratorio A-E, implementado con control
local, medios y API separados. Se permite ese laboratorio antes del cliente y los
eventos Calling de C1, que siguen pendientes; no se declara C1 completo.
La compra del numero solo bloquea C5.

### Correspondencia con las etapas finales 9–15

| Etapa | Corte / entrega actual | Salida pendiente |
| --- | --- | --- |
| 9. Actualizar diseño | C0 + ADR 0055/0056/0057; contratos/estados de laboratorio adoptados | Mantener coherencia con cada incremento |
| 10. Puente con proveedor falso | C3; WebRTC/PCM, reproduccion, interrupciones, errores/cierre, duplicados y metricas verificados | Escenarios nuevos si cambian contratos |
| 11. Conversacion real | C3; OpenAI y Chrome/Mac comprobados con muestras | Escucha, microfono e interrupciones humanos |
| 12. Consultas de agenda | C3; herramientas validadas con identidad fija y agenda falsa | Ampliar escenarios reales del modelo |
| 13. Gestion completa | Continuidad ficticia y mutaciones confirmadas con dobles (ADR 0057) | Mayor prueba con modelo real; integracion operativa C4 |
| 14. Integracion Meta | C1/C5 pendientes; requiere numero elegible | Eventos oficiales, firma, aceptacion/cierre, medios y llamada real |
| 15. Modelo/rendimiento/presupuesto | Modelo configurable y limites; CA-18 agrega telemetria/costo | Distribuciones end-to-end y evaluacion humana |

El siguiente hito humano sigue siendo hablar desde el Mac, escuchar respuesta
generada e interrumpirla. Una muestra automatizada no marca ese criterio completo.

### Incremento de medicion (20 de octubre)

- [x] Especificar referencias de latencia, percentiles, recursos, costo y fronteras.
- [x] Agregar primer PCM/primera emision real de pista, herramientas y corte local.
- [x] Agregar CPU/memoria/colas y estimacion de costo con transcripcion separada.
- [x] Descartar eventos Realtime repetidos por `event_id`, incluido audio/VAD.
- [x] Verificar contratos/deduplicacion y WebRTC con dobles en la Raspberry.
- [x] Verificar una sesion OpenAI acotada y documentar consumo, sin acreditar escucha.
- [x] Dejar laboratorio y acceso Mac disponibles para la prueba humana.
- [ ] Conversar con microfono/altavoces e interrupciones humanos.

Ver [mediciones y resultado del hito](../../verification/2026-10-20-realtime-milestone.md):
453 tests, navegador Mac/Pi/OpenAI y panel de rendimiento. El token WhatsApp
actual fallo la comprobacion de autenticacion (190/463); debe renovarse para el
ramal conectado. La escucha humana permanece pendiente.

### Acceso directo al laboratorio (20 de octubre)

- [x] Quitar el token de acceso del cliente y la API, incluidos texto e historial.
- [x] Unificar comprobacion HTTP e inicio de llamada en **Conectar e iniciar llamada**.
- [x] Mantener habilitacion explicita, proceso/base separados y acceso loopback/SSH.
- [x] Verificar conexion, cierre y continuidad sin token en la Raspberry y recargar `/lab`.

Ver [acceso directo y verificacion](../../verification/2026-10-20-token-free-laboratory.md).

### Reserva interrumpida durante la pregunta (20 de octubre)

- [x] Contrastar historial/accion de la llamada reportada y reproducir el error
      `No hay una propuesta vigente en esta llamada` mediante eventos de voz.
- [x] Conservar datos de la pregunta cortada y preparar otra pregunta/accion al
      confirmar, revalidando agenda y sin reutilizar la autorizacion invalidada.
- [x] Probar respuesta repetida, canal/ID ajenos, rechazo/correccion/nueva gestion
      y horario que deja de estar libre; 37 pruebas focalizadas correctas en la Pi.
- [x] Ejecutar regresion completa: 458 tests correctos y cliente Chromium/WebRTC
      con continuidad/reintentos correctos, sin llamadas a APIs externas.
- [x] Recargar backend y laboratorio, comprobar `.env` completo/modo/configuracion,
      salud/historial/acceso Mac y ambos webhooks locales/publicos. La autenticacion
      WhatsApp sigue bloqueada por token vencido (190/463), independiente de `/lab`.

Ver [diagnostico y evidencia](../../verification/2026-10-20-interrupted-booking-confirmation.md).

### Aumentar maximo de llamada Realtime a cinco minutos (20 de octubre)

- [x] Elevar default y ejemplo de `VOICE_MAXIMUM_SECONDS` de 120 a 300 s.
- [x] Mantener por separado inactividad real de 30 s y cuota de cinco sesiones.
- [x] Sincronizar y reiniciar solo el laboratorio (PID 270508 -> 563829); verificar
      maximo efectivo 300 s, inactividad 30 s y salud/pagina/historial HTTP 200
      desde la Pi, con la pagina y salud accesibles por el forwarding Mac.

Ver [cambio de duracion](../../verification/2026-10-20-realtime-five-minute-limit.md).

### Confirmacion tras respuesta de voz intermedia cancelada (20 de octubre)

- [x] Reproducir tres rechazos consecutivos de confirmacion sin errores del
      proveedor, con preguntas completas y sin mutar la agenda.
- [x] Aislar el salto de secuencia de turnos VAD con pregunta armada y vigente.
- [x] Al rechazar una confirmacion fuera de secuencia inmediata, revalidar y
      preparar una pregunta/accion nueva; conservar ejecucion solo tras otro si.
- [x] Ejecutar 459 pruebas y navegador Chromium/WebRTC; 0 errores JavaScript y
      0 llamadas externas.
- [x] Reiniciar solo laboratorio (PID 563829 -> 633510), sin sesiones activas;
      health/page/history 200 en Pi y pagina/salud 200 por forwarding Mac.

Ver [diagnostico y correccion](../../verification/2026-10-20-voice-confirmation-turn-sequence.md).

### Confirmacion tras VAD intermedio con afirmacion transcrita (20 de octubre)

- [x] Reproducir en el flujo completo de reprogramacion el ciclo que devolvia
      repetidamente `confirmation_required` tras una afirmacion clara.
- [x] Correlacionar la transcripcion con el turno de voz actual y esperarla hasta
      1 s cuando VAD cancele una respuesta intermedia.
- [x] Permitir la accion exacta solo si su pregunta se emitio completa y la
      transcripcion actual confirma explicitamente; conservar rechazo seguro para
      transcripcion ausente/ambigua, pregunta interrumpida, canal/ID ajenos.
- [x] Ejecutar pruebas focalizadas y regresion completa en la Raspberry Pi; verificar
      que la llamada de prueba reprograma una sola vez y no repite la pregunta.

La nueva politica de secuencia sustituye el requisito de turno inmediato para
confirmaciones con saltos VAD; la autorizacion sigue ligada a la pregunta completa,
accion, llamada, canal y afirmacion del turno actual (ADR 0060).

## C0 - Especificacion y diseno

- [x] Describir alcance entrante, exclusiones y criterios CA-01 a CA-17 en `spec.md`.
- [x] Definir control, medios, persistencia, turnos y autorizaciones en `design.md`.
- [x] Distinguir conversacion, sesion y turno de voz en el vocabulario del proyecto.
- [x] Registrar la ADR 0054 como propuesta y actualizar alcance, arquitectura e indices.

Salida: paquete documental para revision; ninguna capacidad Calling implementada.

## C1 - Control simulado de llamadas

- [ ] Aprobar el diseno de este corte y contrastar fixtures con el contrato oficial
      de eventos/acciones de la version de API seleccionada.
- [ ] Introducir configuracion deshabilitada por defecto, origenes tipados y
      dependencias falsas sin cargar librerias de audio o exigir credenciales nuevas.
- [ ] Agregar migracion aditiva y repositorio para sesiones y eventos, con claves
      separadas para llamada WhatsApp, sesion interna y llamada a herramienta.
- [ ] Implementar recepcion, reclamacion de capacidad, estados y cierre idempotente.
- [ ] Implementar cliente Calling con transporte HTTP inyectable y doble sin red;
      probar solicitudes, respuestas y errores sin hacer llamadas reales.
- [ ] Despachar eventos en el webhook, registrar antes del ACK y supervisar trabajo
      mediante el ciclo de vida de FastAPI; sin un endpoint publico de simulacion.
- [ ] Implementar plazos controlables, cierre al apagar y recuperacion a
      `interrupted` tras reinicio, sin reaceptar una llamada persistida.
- [ ] Verificar llamada completa simulada, rechazos por capacidad, duplicados,
      terminacion adelantada, evento tardio, fallo de escritura y tarea bloqueada
      que no retiene el ACK; comprobar limpieza ante excepciones y reinicio.
- [ ] Sincronizar y verificar en la Pi regresion de texto, salud y webhook, y la
      suite sin APIs; registrar evidencia como simulacion.

Salida: CA-01 a CA-06, CA-15 y CA-17 verificados con dobles. La validacion de firma
y metadatos conectados de CA-03 queda implementada y contrastada en C5.

## C2 - Saludo y audio en laboratorio

- [x] Probar `aiortc` como candidato en la Raspberry con las versiones reales de
      Python/arquitectura y codecs; registrar resultado y decision antes de adoptarlo.
- [x] Definir el contrato de medios con doble y transporte real, negociacion,
      eventos de conexion y fin de reproduccion, buffers acotados y cierre.
- [x] Preparar interlocutor WebRTC de laboratorio y audio de prueba en proceso/base
      aislados; documentar como reproducir la prueba sin un numero de WhatsApp.
- [x] Recibir una muestra y emitir saludo en español que identifique al asistente.
- [x] Verificar audio en ambos sentidos, saludo completo, cierre durante saludo,
      desconexion y expiracion; comprobar liberacion de conexiones y tareas.
- [x] Sincronizar, ejecutar en la Pi y registrar codecs y conectividad probados
      como laboratorio; actualizar ADR/arquitectura con la tecnologia adoptada.

- [x] Implementar control local: capacidad unica, persistencia exclusiva, plazos,
      cierre idempotente/concurrente, reinicio y supervision en lifespan.
- [x] Implementar API POST/GET/DELETE y cliente en `/lab`, sin token desde el 20 de octubre;
      comprobar ausencia de rutas en `main:app` e importacion sin agenda/audio.
- [ ] Escuchar fisicamente el saludo y probar microfono real desde otro equipo.
- [x] Separar prueba HTTP sin sesion de ICE, RTP y reproduccion en el cliente;
      explicar el contexto seguro para microfono y la frontera de los tuneles HTTP.
- [x] Verificar navegador en la computadora y backend en la Pi, candidatos host/UDP
      en la misma LAN sin STUN/TURN; conservar pendiente la escucha humana.
- [x] Documentar la skill `lab-tunnel` para preparar servidor, forwarding SSH,
      acceso directo sin token, con recuperacion tras reinicios.

Salida tecnica: CA-06, CA-07, CA-15 y CA-17 comprobados automaticamente para
medios y navegador en la misma Pi. La evidencia distingue reproduccion headless
de escucha humana. Ver [resultado](../../verification/2026-10-18-aiortc-audio-laboratory.md).
La [prueba LAN](../../verification/2026-10-18-webrtc-client-lan.md) acredita tambien
Chrome en la computadora, medios UDP directos y diagnosticos HTTP/ICE/RTP.

## C3 - Conversacion de voz

- [x] Elegir OpenAI Realtime con audio nativo y transcripcion asincrona para historial;
      presupuesto de referencia de 5 USD y pruebas limitadas, ADR 0056.
- [x] Implementar puente PCM24k/WebRTC, adaptador WebSocket GA y doble sin consumo.
- [x] Implementar turnos, cancelacion, truncado del contexto y fin de emision real.
- [x] Agregar historial exclusivo y herramientas de laboratorio con propuestas
      durables, confirmacion posterior a la pregunta y agenda falsa persistente por
      defecto.
- [x] Persistir turnos de voz y transcripciones asincronas, con marcadores si faltan;
      no usarlas como paso de entrada al agente de texto ni como autorizacion.
- [x] Separar presentacion oral, generacion y emision; usar agenda falsa por defecto
      y permitir Google explicito para el perfil de laboratorio. La identidad
      operativa permanece en C4.
- [x] Implementar interrupcion, descarte de resultados tardios, reintentos del mismo
      turno, tiempos de silencio y errores controlados de Realtime/transcripcion.
- [x] Verificar parciales repetidos, transcripcion vacia, fallo de cada proveedor,
      correccion del paciente, audio interrumpido e historial que no afirme haber
      emitido completa una respuesta incompleta.
- [x] Sincronizar y probar conversacion de laboratorio en español; registrar
      latencia observada y separar evidencia falsa de consumo real de voz.
- [x] Permitir seleccion explicita del proveedor Google en laboratorio sin cambiar
      el default fake; usar propietario `whatsapp_voice_lab` para aislar los eventos.
- [x] Mostrar en health y pagina HTML si las citas son simuladas o se escriben en
      Google Calendar operativo; conservar la interfaz de pruebas.
- [x] No requerir el atributo `.appointments` del proveedor fake para completar una
      mutacion remota; conservar la fuente Google como autoridad.
- [x] Distinguir la cuota de sesiones agotada de un fallo de negociacion y devolver
      el conteo/limite sin aumentar la cuota automaticamente.
- [x] Aceptar `VOICE_MAX_SESSIONS=unlimited` para la fase de pruebas manteniendo 5
      como default en `.env.example` y tests.

Salida: CA-08/CA-09 para laboratorio nativo, con pruebas de herramientas sobre
agenda falsa y proveedor Google aislado por propietario. CA-09 integrado con
pacientes y chat operativos sigue en C4.
Ver [evidencia de voz nativa](../../verification/2026-10-19-native-realtime-voice.md).
La agenda Google opcional, la regresion de mutaciones remotas y el estado del
laboratorio estan en [la verificacion del 20 de octubre](../../verification/2026-10-20-voice-google-calendar.md).
La [verificacion del limite de sesiones](../../verification/2026-10-20-voice-session-quota.md)
documenta el 429 accionable y el conteo persistente del perfil.

### Formato de fecha en confirmaciones habladas (21 de octubre)

- [x] Presentar primero la hora de inicio en 12 horas con AM/PM y despues la
      fecha `DD/MM/YYYY` en español de México.
- [x] Agregar regresion de formato para crear, reprogramar y cancelar.
- [x] Sincronizar y verificar la regresion y suite de voz en la Raspberry Pi.

Ver [causa y verificacion del formato](../../verification/2026-10-21-voice-mexican-date-format.md).

## C4 - Agenda, continuidad y autorizacion de voz

### Continuidad de laboratorio aprobada (ADR 0057)

- [x] Agregar texto al mismo paciente ficticio de `/lab`, con historial ordenado
      por turno y canal e idempotencia de mensajes.
- [x] Distinguir generacion completada de emision completada/interrumpida y guardar
      duracion generada/emitida; descartar eventos tardios de generaciones anteriores.
- [x] Ligar autorizacion al canal y secuencia de origen; un `si` cruzado no ejecuta.
- [x] Retomar explicitamente en otro canal conserva datos y exige nueva pregunta
      y autorizacion, tambien despues de colgar y volver a conversar.
- [x] Verificar canales, interrupciones, correcciones e historial tardio con agenda
      falsa; registrar evidencia separada de pacientes y mensajes WhatsApp reales.

Ver [resultado de controles y continuidad ficticia](../../verification/2026-10-19-voice-text-controls.md).

### Contexto historico y apertura independiente de `/lab` (21 de octubre)

Contrato y alcance aprobados por el usuario. Se completaron el paso 1 documental
y, por solicitud explicita posterior, el paso 3 de apertura independiente antes
del contexto enriquecido del paso 2. La consulta historica del paso 4 tambien esta
implementada; los pasos 2 y 5 mantienen trabajo pendiente.
Corresponde a CA-22 a CA-26 y a la ADR 0061, exclusivamente para voz y mensajes
del perfil ficticio de `/lab`.

- [x] **Paso 1 — Contrato y SDD:** documentar saludo propio por llamada, historial
      con fecha/canal/sesion/resultado conocido, recuperacion solo informativa y
      retomar con revalidacion y pregunta nueva. Alinear especificacion, diseno,
      alcance, arquitectura, vocabulario e indices, manteniendo el runtime pendiente.
- [ ] **Paso 2 — Contexto historico:** construir antecedentes con procedencia y
      resultado de herramientas/acciones, separados del estado vigente. Acotar la
      ventana reciente y representar registros antiguos, emision interrumpida,
      transcripcion ausente y resultado desconocido sin inferencias.
- [x] **Paso 3 — Apertura de llamada:** aislar la generacion del saludo, deshabilitar
      sus herramientas e incorporar los antecedentes al atender al paciente.
      Comprobar interrupcion y ausencia de respuestas tardias del saludo cancelado.
- [x] **Paso 4 — Consulta de historial:** concretar interfaz/limites e implementar
      busqueda acotada por tema, fecha y canal dentro del perfil. Consultar no
      activa, reemplaza ni retoma gestiones y no reutiliza autorizaciones.
- [ ] **Paso 5 — Verificacion:** probar llamadas consecutivas tras gestion terminada
      o pendiente, recuperacion texto/voz y fuera de ventana, resultado incierto,
      interrupcion del saludo y retomar con pregunta nueva/disponibilidad cambiada.
      Inspeccionar contexto enviado al proveedor y ausencia de mutaciones por leer
      historial; sincronizar y ejecutar regresiones en la Pi antes de registrar
      adopcion del contrato y evidencia de comportamiento.

Salida actual: contrato aprobado y apertura independiente implementada (CA-22),
con pruebas de memoria preparada, contexto vacio/sin herramientas, continuidad de
voz/texto e interrupcion antes/despues del ACK y del evento de conexion. La ventana
existente de 12 mensajes conserva su representacion previa. La consulta CA-26 ya
busca fuera de esa ventana con aislamiento, filtros y fragmentos de procedencia;
preserva propuestas incluso al terminar el turno o citar preguntas antiguas por
voz/texto. El contexto reciente enriquecido y la correlacion de resultados siguen
pendientes. Ver [apertura](../../verification/2026-10-21-isolated-voice-greeting.md)
y [consulta historica](../../verification/2026-10-21-voice-history-search.md).

### Integracion operativa posterior

Notificaciones de laboratorio, 22 de octubre de 2026:

- [x] Compartir conversion de eventos, disparador, compositor y entregador con chat.
- [x] Registrar avisos de crear/reprogramar/cancelar con el resultado de la accion.
- [x] Recuperar avisos tras reinicios y reintentar solo la entrega fuera del audio.
- [x] Pasar el mismo adaptador y proveedor de agenda a voz y texto de `/lab`.
- [x] Verificar los tres eventos y fallos/reintentos con dobles en la Raspberry.

Este avance parcial de entregas no completa las autorizaciones ni identidades
operativas de C4. Evidencia: `2026-10-22-shared-doctor-notifications.md`.

- [ ] Antes de uso operativo, diseñar e implementar una cuota diaria por perfil,
      con zona horaria y conteo persistente; `unlimited` queda reservado al entorno
      de pruebas y no satisface este requisito futuro.

- [ ] Agregar propietario/version a la gestion unica y compatibilidad de estados
      historicos como chat; incluir pausa, retomar, nueva gestion y fin de llamada.
- [ ] Integrar transferencia explicita entre canales con revalidacion de agenda
      y bloqueo por turno, sin crear otra conversacion activa para el paciente.
- [ ] Agregar confirmacion de voz para crear, reprogramar y cancelar, tambien en
      rutas locales como la aceptacion del motivo; conservar el flujo de texto.
- [ ] Ligar autorizacion a sesion, version, datos y pregunta emitida completa,
      con vigencia maxima de 10 minutos y anulacion por interrupcion o cambio.
- [ ] Implementar reclamacion durable de operaciones y coordinacion con cierre;
      representar resultado incierto y conciliacion antes de permitir otra ejecucion.
- [ ] Reutilizar resultados definitivos y eventos de citas para confirmacion
      hablada, seguimiento escrito y notificacion idempotente al doctor.
- [ ] Verificar cada escenario de continuidad de `spec.md`: chat -> voz,
      voz -> chat, otra llamada, origen tardio y pregunta interrumpida.
- [ ] Verificar continuidad operativa con identidad real y la agenda vigente:
      conflictos, cambios de datos, expiracion, duplicados, cierre antes/despues de
      reclamar, fallo externo incierto y reinicio entre ejecucion externa y registro
      local. La integracion Google del perfil ficticio no completa este requisito.
- [ ] Sincronizar y ejecutar suite en la Pi; verificar una gestion completa por
      voz en laboratorio y documentar el estado final de la agenda falsa.

Salida: CA-10 a CA-14 verificados con identidad operativa y regresion de chat/voz.

## C5 - Conexion real con Meta (requiere numero)

- [ ] Obtener y registrar linea del consultorio, verificar elegibilidad y habilitar
      Calling; comprobar coexistencia solo si se quiere usar tambien la app movil.
- [ ] Contrastar y fijar version de API, fixtures, permisos, acciones entrantes,
      eventos, codigos de error y plazos vigentes; documentar cualquier diferencia.
- [ ] Configurar numero/token/App Secret sin exponer valores; implementar y verificar
      firma del cuerpo original, destino y llamante antes de crear efectos.
- [ ] Verificar que firmas invalidas, otro numero empresarial, identidad ausente o
      intentos de simulacion sobre el entorno conectado no crean paciente ni llamada.
- [ ] Suscribir los eventos y resolver negociacion y conectividad real de medios
      desde la Pi, incluidas necesidades de ICE/STUN/TURN; ajustar plazos propios.
- [ ] Verificar primero saludo y cierre en una llamada desde otro WhatsApp, y
      despues conversacion y gestion de cita con identidad y datos de prueba.
- [ ] Comprobar reglas de seguimiento escrito y plantilla cuando corresponda;
      registrar entrega pendiente si falta, sin reejecutar la agenda.
- [ ] Probar desconexion, nueva llamada, duplicados y continuidad real con chat;
      registrar salud, webhooks y resultados de medios, voz, agenda y entregas.
- [ ] Actualizar estados de especificacion/ADR solo con comportamiento adoptado y
      evidencia real; documentar restricciones que sigan pendientes.

Salida: CA-03, CA-16 y CA-17 y escenario integrado verificados contra Meta. Hasta
cerrar este corte, el proyecto no se declara integrado con WhatsApp Calling.
