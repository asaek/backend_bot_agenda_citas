# 0056 - Voz nativa con OpenAI Realtime en el laboratorio

## Estado

Aceptada para laboratorio el 19 de octubre de 2026, tras implementar el puente y
verificar OpenAI real con WebRTC y Chrome en la computadora. La arquitectura fue
aprobada el 18 de octubre. La decision no acredita conexion con Meta ni completa C4.

## Decision

El modelo recibe audio y produce audio mediante Realtime. La Raspberry termina
WebRTC/Opus y mantiene un WebSocket autenticado con OpenAI. Se adopta un contrato
PCM16 mono de 24 kHz para el puente, con conversion mediante PyAV, colas limitadas
y reproduccion en tiempo real. No se invoca el agente de texto por cada turno.
La entrada conserva hasta un segundo de frames y la salida hasta 30 segundos de
PCM (aproximadamente 1.44 MB); exceder el limite termina la sesion. Cuando RTP/DTX
o una muestra finalizada deja huecos, se completan con bloques de silencio de
100 ms para que el VAD pueda consolidar el turno.

El laboratorio conserva un modo de saludo reproducible sin consumo y agrega un
modo `realtime` explicito. La credencial queda en el backend. Modelo y voz son
configurables; `gpt-realtime-2.1` es el candidato inicial. La transcripcion de
entrada es asincrona y sirve al historial: su llegada no ejecuta herramientas.

La sesion coordina audio, turnos, respuestas, cancelacion y cierre. Un evento de
generacion completada no significa que el audio se haya emitido completo. Al
interrumpir se cancela la respuesta, se descarta audio pendiente y se recorta el
contexto al punto emitido. Los eventos antiguos no pueden reactivar audio.

Las herramientas usan contratos y validadores compartidos con chat. La identidad
de laboratorio se fija en el servidor; no se acepta una identidad elegida por el
modelo o navegador. Se emplea agenda falsa y SQLite exclusivo para perfiles,
historial, acciones y resultados. Las mutaciones requieren una propuesta durable,
una pregunta emitida completa y una decision en un turno de audio posterior.
Cancelar, corregir, interrumpir la pregunta o cerrar invalida la autorizacion.
Se deduplican herramientas por sesion/call_id y acciones por identidad durable.
La generacion se revoca al empezar el habla, antes de consolidar el nuevo turno.
La reclamacion obtiene primero el escritor SQL y comprueba despues una
autorizacion sincronizada con interrupcion/cierre; esa autorizacion se mantiene
hasta el commit. La espera por SQLite no impide revocar una accion no reclamada.
El cierre libera audio y WebSocket, drena transcripciones durante hasta un segundo
y reintenta su persistencia mediante DELETE si SQLite no permite finalizar.

El laboratorio no representa continuidad con pacientes del backend operativo.
La migracion de propietarios chat/voz, entregas y autorizaciones sobre la agenda
operativa permanece en C4. Se mantiene separada de la prueba de herramientas.

## Verificacion y costo

Primero se verifican contratos con dobles, WebSocket local y WebRTC real sin APIs.
Las pruebas reales requieren acceso al modelo, sesiones acotadas y contabilidad
de audio, texto y transcripcion. Presupuesto de referencia aprobado: 5 USD.
Las credenciales de WhatsApp no son necesarias para esta prueba.

### Ajuste del maximo de sesion (20 de octubre de 2026)

Se establece un maximo de cinco minutos (300 s) por sesion Realtime, reemplazando
el valor inicial de dos minutos. El usuario solicito el cambio tras revisar una
reserva cuya llamada alcanzo ese limite. Se conserva el cierre por 30 s de
inactividad real, la cuota de cinco sesiones por perfil y el limite general de
600 s del supervisor; los limites de concurrencia y costo no se amplian con esta
duracion. `VOICE_MAXIMUM_SECONDS` permite configurar un valor entre 1 y 600 s.

El incremento del 20 de octubre instrumenta el contrato adoptado: primer PCM
recibido y primer frame emitido por turno, duracion de herramientas, corte local,
colas y CPU/RSS del proceso (`voice_metrics.py`). La referencia de backend es
recepcion VAD/commit; el navegador mide aparte el fin de una muestra hasta señal
en el renderizador. Se preservan las fronteras con escucha humana y latencia total.
Se estiman USD segun tarifas publicadas para el modelo configurado y la
transcripcion, registrando fuente y fecha. Si faltan tarifa/desglose/eventos, el
total queda desconocido, con subtotal identificado. Las metas p50 1.5 s y p95 3 s
son de evaluacion end-to-end; una medicion parcial no demuestra su cumplimiento.

## Referencias

- [Realtime](https://developers.openai.com/api/docs/guides/realtime).
- [Conversaciones](https://developers.openai.com/api/docs/guides/realtime-conversations).
- [VAD](https://developers.openai.com/api/docs/guides/realtime-vad).
- [Spec 021](../specs/021-whatsapp-inbound-calling/spec.md).
