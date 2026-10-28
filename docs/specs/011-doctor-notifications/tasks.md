# Tareas - Notificaciones al doctor

## Corte 0 - SDD y contrato funcional

- [x] Confirmar que las tres operaciones de cita son los unicos disparadores.
- [x] Definir el resumen como contenido obligatorio de cada notificacion.
- [x] Registrar criterios de aceptacion, privacidad y limites de alcance.
- [x] Dejar el diseno tecnico en estado borrador hasta implementarlo.

## Corte 1 - Eventos de agenda

- [x] Definir los tipos de evento de notificacion.
- [x] Exponer los resultados exitosos de create, reschedule y cancel al flujo de
  notificacion.
- [x] Relacionar cada evento con el mensaje entrante y la llamada de herramienta.
- [x] Probar que los errores de agenda no generan eventos exitosos.

## Corte 2 - Persistencia e idempotencia

- [x] Crear la tabla `doctor_notifications` y sus restricciones.
- [x] Implementar el repositorio de estados, errores e IDs del proveedor.
- [x] Implementar la clave unica `(event_key, recipient_number)` para evitar
  duplicados por destinatario.
- [x] Probar reintentos de encolado y recuperacion de estados pendientes o fallidos.
- [x] Probar entregas independientes para varios numeros configurados.

## Corte 3 - Composicion del mensaje y resumen

- [x] Implementar el formato unico para agendamiento, modificacion y cancelacion.
- [x] Implementar el resumen con el historial persistido y el contexto de la cita.
- [x] Incluir paciente, sus ultimos 10 digitos de telefono y senales de prioridad
  disponibles.
- [x] Evitar diagnosticos, transcripciones completas e identificadores internos.
- [x] Probar la composicion con un proveedor LLM falso y con nombre de paciente
  ausente.

## Corte 4 - Entrega por WhatsApp

- [x] Agregar la configuracion de varios doctores y la bandera de habilitacion.
- [x] Reutilizar `WhatsAppClient` para cada destinatario configurado.
- [x] Persistir correctamente estados `pending`, `sending`, `sent` y `failed` por
  destinatario.
- [x] Normalizar errores de configuracion y de la API externa.
- [x] Probar envios multiples, fallo aislado y reintento con un cliente WhatsApp
  falso.

## Corte 5 - Integracion del webhook

- [x] Componer `DoctorNotificationService` desde `main.py`.
- [x] Integrar la notificacion despues de cada operacion de cita confirmada.
- [x] Garantizar que un fallo al doctor no impida la respuesta al paciente.
- [x] Probar los tres eventos desde el ciclo completo del webhook.
- [x] Probar que un webhook duplicado no envia dos mensajes al mismo doctor.

## Corte 6 - Verificacion y cierre documental

- [x] Actualizar README y `.env.example` con la configuracion implementada.
- [x] Cambiar la especificacion y el ADR a estado implementado cuando corresponda.
- [x] Ejecutar la suite completa en la Raspberry Pi.
- [x] Verificar health check y ambos metodos del webhook con los comandos del
  README.
- [x] Registrar la evidencia en `docs/verification/`.

La evidencia de cierre esta en
`docs/verification/2026-09-22-doctor-notifications-webhook.md` e incluye la suite
local, la suite del mirror de Raspberry Pi y la verificacion HTTP operativa.

## Ampliacion - Señales razonadas del motivo e historial actual

- [x] Reproducir en Raspberry Pi la ausencia de señal con lagañas amarillentas y grandes.
- [x] Compartir catalogo e instrucciones semanticas entre evaluador y resumidor.
- [x] Añadir `ocular_discharge` y reconocer `laga;as` sin modificar el motivo.
- [x] Conservar interpretaciones del LLM con evidencia literal sin exigir palabras clave.
- [x] Incorporar sintomas del historial actual y separar citas anteriores y mensajes futuros.
- [x] Rechazar evidencia inventada o del asistente y excluir negaciones explicitas.
- [x] Ejecutar suite completa, reiniciar backend y verificar health check y ambos webhooks
      en Raspberry Pi; registrar evidencia.

Evidencia de la ampliacion:
`docs/verification/2026-10-07-semantic-priority-signals.md`.

## Ajuste - Resumen de la charla sin repetir la agenda (17 de octubre de 2026)

- [x] Centrar el prompt en lo expresado por el paciente y excluir los datos de agenda
      y la confirmacion del resumen, incluso si aparecen en el historial.
- [x] Enviar al resumidor solo el motivo y el historial como contexto, sin campos
      estructurados de fecha, horas, zona, estado ni tipo de evento.
- [x] Verificar la composicion y el webhook en Raspberry Pi y comprobar un resumen
      generado con el proveedor configurado usando datos de prueba.

Evidencia: `docs/verification/2026-10-17-conversation-only-notification-summary.md`.

## Ampliacion - Disparador compartido de texto y voz (22 de octubre de 2026)

- [x] Reutilizar la conversion de resultados exitosos para los tres eventos.
- [x] Extraer `DoctorNotificationTrigger` y usarlo desde el chat y `/lab`.
- [x] Mantener un solo compositor, formato, configuracion de destinatarios y entregador.
- [x] Registrar evento y resultado de voz atomicamente y recuperar avisos tras reinicios.
- [x] Separar el envio del audio y reintentar fallos sin repetir herramientas de agenda.
- [x] Evitar duplicados concurrentes y el envio de marcadores de resumen fallido.
- [x] Verificar con dobles crear, reprogramar, cancelar, rechazo, fallo y reintentos en la Pi.
- [x] Cerrar la suite completa, recarga y comprobaciones HTTP en la Pi; registrar
      autenticacion Meta y su bloqueo independiente por token vencido.

Evidencia: `docs/verification/2026-10-22-shared-doctor-notifications.md`.

## Hallazgo operativo - Ventana de mensajeria del doctor (22 de octubre de 2026)

- [x] Correlacionar la cancelacion exitosa con su aviso aceptado por Meta.
- [x] Reproducir aceptacion inicial seguida del callback `failed` con codigo `131047`.
- [x] Documentar que el `sent` local actual no acredita recepcion en el telefono.
- [x] Implementar el adaptador de envio mediante plantilla y mapeo explicito.
- [x] Configurar `aviso_cita_medico` en `es_MX` con las nueve variables aprobadas.
- [x] Verificar su entrega real con callback `delivered` (prueba controlada del 25/10).
- [ ] Acreditar explicitamente el caso fuera de la ventana de 24 h del destinatario.
- [x] Persistir callbacks de estado para avisos de chat y voz, distinguir aceptacion
      de entrega y conservar codigos seguros de rechazos asincronos.
- [ ] Recuperar el aviso original con ventana abierta o plantilla utilizable y
      comprobar entrega sin volver a ejecutar la cancelacion.

Evidencia: `docs/verification/2026-10-22-whatsapp-doctor-delivery-window.md`.

## Verificacion - Separacion de destinatarios (22 de octubre de 2026)

- [x] Comparar `.env` local y remoto sin imprimir valores y comprobar modo `600`.
- [x] Comparar la configuracion heredada de los procesos de chat y laboratorio con `.env`.
- [x] Contrastar los 47 avisos de chat y el aviso de voz con los doctores configurados.
- [x] Reproducir que el ultimo paciente de prueba y el doctor usan el mismo numero.
- [x] Distinguir la confirmacion persistida del paciente y el aviso interno del doctor.
- [x] Verificar en Raspberry los cuerpos separados con numeros distintos y compartidos,
      incluyendo normalizacion mexicana y un webhook duplicado.
- [x] Registrar las verificaciones HTTP y cerrar la evidencia de la auditoria.

Evidencia: `docs/verification/2026-10-22-doctor-notification-routing.md`.

## Corte - Configuracion de plantilla y captura diferida

- [x] Agregar las tres variables y conservar el contrato de destinatarios.
- [x] Separar captura habilitada de errores de transporte y datos de plantilla.
- [x] Retener entregas pendientes con motivo sin componer ni reclamar intentos.
- [x] Conservar cuerpos preparados y estados enviados o inciertos.
- [x] Mantener el snapshot de chat sin completar y recuperar eventos sin repetir citas.
- [x] Probar configuracion incompleta/invalida, varios doctores y ausencia de respaldo por texto.
- [x] Verificar con dobles el webhook y la recuperacion de laboratorio tras reiniciar.
- [x] Ejecutar la suite completa en Raspberry, recargar ambos procesos y verificar HTTP/configuracion.
- [x] Registrar evidencia de ejecucion y limites del corte.

Ese corte de preparacion no incorporo el adaptador de envio. El siguiente corte
implementa el transporte y deja pendiente el mapeo aprobado real y los callbacks.

Evidencia: `docs/verification/2026-10-22-doctor-template-configuration.md`.

## Corte - Envio mediante Meta y mapeo explicito

- [x] Agregar `send_template()` reutilizando autenticacion, version y transporte HTTP.
- [x] Conservar tipo de evento, estado, fecha, hora, motivo, paciente, resumen y prioridad como datos saneados.
- [x] Configurar componentes explicitamente, sin asumir cantidad u orden de variables reales.
- [x] Retener avisos con mapeo ausente/invalido o campos no disponibles, sin respaldo por texto.
- [x] Persistir datos y payload congelados para reintentos sin volver a resumir.
- [x] Migrar bases de chat y voz preservando avisos historicos.
- [x] Probar crear, reprogramar y cancelar por webhook y recuperar avisos de voz tras reiniciar.
- [x] Probar errores HTTP, respuesta perdida/sin ID y reutilizacion del payload original.
- [x] Ejecutar suite completa, recargar runtime y verificar configuracion y HTTP en Raspberry.
- [x] Registrar evidencia y dejar los datos de la plantilla real pendientes.

Evidencia: `docs/verification/2026-10-22-doctor-template-delivery.md`.

## Corte - Pendientes y reintentos durables

- [x] Recuperar eventos registrados de chat y laboratorio al arrancar y periodicamente.
- [x] Guardar evento y contexto acotado, conservando contenido y destinatarios originales.
- [x] Persistir espera exponencial y respetar Retry-After sin saltos desde otro consumidor.
- [x] Detener rechazos de configuracion hasta corregir datos relevantes o conciliar una correccion externa.
- [x] Auditar version local de plantilla, parametros y resultado de cada intento.
- [x] Conciliar envios inciertos con evidencia y numero de intento, sin liberacion automatica por tiempo.
- [x] Verificar recuperacion sin otro mensaje y sin repetir citas, concurrencia y preservacion del contexto.
- [x] Ejecutar suite completa y recargar/verificar ambos procesos en Raspberry.
- [x] Registrar evidencia de migracion, runtime y limites de envio real.

Evidencia: `docs/verification/2026-10-22-doctor-notification-retries.md`.

## Corte - Entrega real informada por Meta

- [x] Separar aceptacion HTTP de los estados `sent`, `delivered`, `read` y `failed`.
- [x] Persistir callbacks seguros antes del ACK, con deduplicacion y correlacion por ID/destinatario.
- [x] Proyectar en chat/voz sin iniciar conversaciones, sesiones ni envios.
- [x] Conservar y recuperar callbacks tempranos, destinos indisponibles y asociaciones ambiguas.
- [x] Resolver desorden y carreras de proyeccion sin perder eventos ni retroceder evidencia.
- [x] Aplicar fallos asincronos al control de reintentos una sola vez y proteger intentos posteriores.
- [x] Preservar historicos sin inventar entregas y corregir la conciliacion sobre la base de voz.
- [x] Ejecutar suite completa, recargar ambos procesos y verificar runtime y rutas en Raspberry.
- [x] Registrar evidencia y limites de la comprobacion con Meta real.

Evidencia: `docs/verification/2026-10-22-meta-delivery-statuses.md`.

## Configuracion de la plantilla aprobada - 23 de octubre de 2026

- [x] Registrar nombre, idioma, texto aprobado y nueve variables en `approved-template.md`.
- [x] Configurar `.env.example` y `.env` sin cambiar el destinatario del doctor.
- [x] Probar con compositor y HTTP simulado los nueve valores y el orden exacto.
- [x] Sincronizar configuracion, arrancar ambos procesos y verificar el runtime.
- [x] Transferir solo el token renovado, conservar otras variables y verificar autenticacion HTTP 200.
- [x] Acreditar entrega real con token vigente y un callback `delivered` o `read`.
- [x] Comparar el activo candidato del panel (`2157628355165252`) con la WABA comprobada (`1047483564765260`).
- [ ] Validar tipo y acceso del activo del panel; `100/33` no distingue por si solo la causa.
- [x] Resolver `132001` para el emisor actual con WABA, numero y plantilla confirmados por API.

El activo del panel sigue siendo una investigacion separada: no bloquea el envio
actual verificado. La prueba diagnostica no reejecuta ni concilia avisos historicos.

Evidencia de resolucion: `docs/verification/2026-10-25-approved-template-delivered.md`.

Evidencia: `docs/verification/2026-10-23-approved-doctor-template.md`.

## Fuera de este corte

- [ ] Agregar procesamiento distribuido de notificaciones.
- [ ] Agregar canales diferentes de WhatsApp.
- [ ] Generar resumenes por inactividad o cierre automatico de la conversacion.
