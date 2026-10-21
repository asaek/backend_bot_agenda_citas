# 0054 - Llamadas entrantes con autorizacion ligada al origen

## Estado

Propuesta el 18 de octubre de 2026. Asociada al
[corte 021](../specs/021-whatsapp-inbound-calling/spec.md). Calling y autorizaciones
siguen sin implementacion. El laboratorio A-E se implementa por separado y adopta
su biblioteca de medios en la [ADR 0055](./0055-isolated-aiortc-audio-laboratory.md).

Actualizacion del 19 de octubre: la cadena de voz propuesta aqui se reemplaza
por audio nativo OpenAI Realtime en la [ADR 0056](./0056-native-realtime-voice-laboratory.md).
Las autorizaciones operativas y continuidad entre canales de esta ADR siguen
propuestas; las confirmaciones de laboratorio tienen identidad y agenda de prueba.

## Contexto y propuesta

Se quiere preparar llamadas iniciadas por el paciente dentro de WhatsApp antes
de comprar un numero. El proyecto ya usa Meta directa y una sola conversacion
activa por paciente con gestion persistida, pero esa gestion no distingue origen.
Reutilizarla sin esa distincion permitiria consumir una confirmacion desde otro
canal. Ademas, hoy aceptar el motivo puede ejecutar la reserva inmediatamente.

Se propone mantener Meta directa, separar control de llamada y transporte de
audio, y conectar transcripcion -> flujo conversacional existente -> sintesis.
La simulacion y el laboratorio usan las mismas fronteras antes del corte real.
Identidad, herramientas y fuente de verdad de agenda siguen en el backend.

La continuidad usa una gestion unica con propietario de canal/sesion y version.
Retomar transfiere los datos, revalida la agenda y exige otra pregunta; ninguna
autorizacion se transfiere. La voz requiere confirmacion contextual para las tres
mutaciones, incluida creacion, y registra por separado el resultado de agenda y
el de reproduccion o entrega escrita.

## Alternativas y consecuencias

- Migrar a un proveedor gestionado simplificaria parte de los medios, pero
  requiere revisar remitente, mensajeria y costos; queda fuera de este incremento.
- Un agente de voz que sustituya el flujo de texto exigiria volver a integrar las
  reglas existentes. La cadena propuesta las reutiliza, a costa de coordinar
  transcripcion, latencia, sintesis e interrupciones.
- Separar conversaciones por canal evitaria algunas colisiones, pero fragmentaria
  identidad y gestion y cambiaria el invariante de conversacion activa unica.
  La propuesta conserva ese invariante y hace explicita la transferencia.
- `aiortc` fue candidato en esta propuesta. Tras comprobar su compatibilidad en la
  Raspberry se adopto solo para laboratorio en la ADR 0055; Meta sigue pendiente.
- Una simulacion no prueba elegibilidad o medios de Meta. Las mutaciones externas
  inciertas necesitan conciliacion, no una promesa de ejecucion exactamente una vez.

La [especificacion](../specs/021-whatsapp-inbound-calling/spec.md), el
[diseno](../specs/021-whatsapp-inbound-calling/design.md) y las
[tareas](../specs/021-whatsapp-inbound-calling/tasks.md) delimitan las verificaciones
necesarias antes de adoptar esta propuesta en el runtime.
