# Tareas - Llamadas entrantes de WhatsApp

## Estado y orden

Definicion documental preparada el 18 de octubre de 2026. C0 corresponde a esta
entrega; C1-C5 son trabajo pendiente. Especificacion y diseno deben revisarse y
aprobarse antes de implementar. Cada corte requiere cerrar su verificacion antes
de comenzar el siguiente; la compra del numero solo bloquea C5.

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

- [ ] Probar `aiortc` como candidato en la Raspberry con las versiones reales de
      Python/arquitectura y codecs; registrar resultado y decision antes de adoptarlo.
- [ ] Definir el contrato de medios con doble y transporte real, negociacion,
      eventos de conexion y fin de reproduccion, buffers acotados y cierre.
- [ ] Preparar interlocutor WebRTC de laboratorio y audio de prueba en proceso/base
      aislados; documentar como reproducir la prueba sin un numero de WhatsApp.
- [ ] Recibir una muestra y emitir saludo en español que identifique al asistente.
- [ ] Verificar audio en ambos sentidos, saludo completo, cierre durante saludo,
      desconexion y expiracion; comprobar liberacion de conexiones y tareas.
- [ ] Sincronizar, ejecutar en la Pi y registrar codecs y conectividad probados
      como laboratorio; actualizar ADR/arquitectura con la tecnologia adoptada.

Salida: CA-06, CA-07, CA-15 y CA-17 verificados para medios de laboratorio.

## C3 - Conversacion de voz

- [ ] Elegir y documentar proveedor/modelos de STT y TTS para español, configuracion
      y costo; conservar dobles para las pruebas sin consumo.
- [ ] Agregar persistencia de turnos y procedencia e integrar transcripciones
      finales con una entrada conversacional que distinga voz y chat.
- [ ] Separar presentacion oral de formato WhatsApp, y generacion de respuesta de
      reproduccion; mantener las mutaciones de voz bloqueadas hasta cerrar C4.
- [ ] Implementar interrupcion, descarte de resultados tardios, reintentos del mismo
      turno, tiempos de silencio y errores controlados de STT/LLM/TTS.
- [ ] Verificar parciales repetidos, transcripcion vacia, fallo de cada proveedor,
      correccion del paciente, audio interrumpido e historial que no afirme haber
      emitido completa una respuesta incompleta.
- [ ] Sincronizar y probar conversacion de laboratorio en español; registrar
      latencia observada y separar evidencia falsa de consumo real de voz.

Salida: CA-08 y CA-09 verificados con controles previos vigentes; sin mutaciones
de agenda habilitadas para voz.

## C4 - Agenda, continuidad y autorizacion de voz

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
- [ ] Verificar con agenda falsa conflictos, cambios de datos, expiracion,
      duplicados, cierre antes/despues de reclamar, fallo externo incierto y
      reinicio entre ejecucion externa y registro local.
- [ ] Sincronizar y ejecutar suite en la Pi; verificar una gestion completa por
      voz en laboratorio y documentar el estado final de la agenda falsa.

Salida: CA-10 a CA-14 verificados, con regresion de chat y sin escribir Google real.

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
