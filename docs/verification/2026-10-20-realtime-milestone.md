# Hito Realtime: mediciones y laboratorio disponible — 2026-10-20

## Entrega y frontera

Se continuo desde el laboratorio/continuidad existentes del 19 de octubre, sin
atribuirles una nueva implementacion. Se actualizaron spec 021, arquitectura,
alcance, ADR 0056 y tareas para reflejar las etapas finales 9–15 y CA-18.

El incremento agrega `voice_metrics.py`, instrumentacion del primer PCM/primer
frame de pista, herramientas, corte de cola, CPU/RSS, estimacion USD y un panel
en `/lab`. Descarta eventos Realtime repetidos por `event_id`, incluido VAD/audio.
La cola de primera emision es acotada y se cancela con las demas tareas al cerrar.

Implementacion/documentacion locales, sincronizadas antes de ejecutar en la Pi:
`asaek@192.168.1.12:~/Downloads/chatbot_test_repo`. Python 3.13.5, aiortc 1.14.0,
PyAV 16.1.0 y websockets 16.1.1. `uv sync --locked --extra audio --extra voice`
correcto; sin nuevas dependencias.

## Verificacion sin consumo de APIs

- **453 tests correctos en 58.598 s**, suite completa en la Raspberry.
- Pruebas focalizadas de voz: 32 correctas tras las correcciones de revision.
- WebRTC/Opus real con proveedor falso: audio bidireccional, interrupcion,
  fragmentos tardios descartados, silencio remoto y liberacion de recursos.
- Duplicar `speech_started`, `speech_stopped`, commit y fragmento PCM conserva
  un turno/una generacion/un fragmento. Los duplicados no aumentan uso o herramientas.
- Primer PCM y primer frame emitido se contabilizan una vez; saludo y texto no
  se mezclan con latencias de respuesta a voz. Turnos con herramientas se separan.
- Un turno sin salida no cuenta como latencia cero. Si no hay evento VAD, el
  inicio es recepcion del commit, anterior a esperar cancelacion/red/SQLite.
- Costos con cache, audio/texto y transcripcion; modelo o desglose desconocidos
  dejan total `null`. Una solicitud enviada sin ACK o sin uso final conserva costo
  incompleto, tambien al cerrar.
- `scripts/verify_lab_controls.py`: Chromium y WebRTC reales con Realtime falso,
  historial voz/texto, reintento de respuesta perdida y contexto tras colgar;
  correcto, cero errores JavaScript y cero llamadas externas.

### Revision

Se reviso el incremento en dos ejes independientes, estandares y especificacion.
Se corrigieron: costo completo con cache omitido/solicitud sin ACK, desglose de
transcripcion insuficiente y referencia del commit posterior a esperar red.
Las regresiones tienen pruebas especificas. La segunda revision estatica no
dejo hallazgos pendientes en ninguno de los dos ejes. Las tarifas se contrastaron
con las fuentes primarias actuales; no se sustituyeron por valores recordados.

## OpenAI real, peer WebRTC en la Pi

`scripts/probe_realtime_voice.py`: modelo `gpt-realtime-2.1`, voz `marin` y
`gpt-4o-mini-transcribe`. Una muestra hablada conocida; dos respuestas de audio
(saludo y contestacion). Sin dispositivos fisicos.

| Medida | Observado |
| --- | --- |
| Fin del archivo -> primer audio de respuesta recibido por el peer | 1589 ms |
| VAD recibido -> primer PCM en la Pi | 723.517 ms |
| VAD recibido -> primer frame emitido por la Pi | 724.388 ms |
| Entrada / salida / transcripcion (tokens) | 2669 / 482 / 65 |
| Costo estimado de esta sesion con transcripcion | USD 0.03335275 |
| CPU del proceso / porcentaje medio de un nucleo | 12.286 s / 43.56% |
| Pico RSS del proceso | 116.004 MiB |
| Pico de salida en cola | 9840 ms |
| Liberacion de recursos | Correcta |

## Chrome en el Mac -> Pi -> OpenAI

`scripts/verify_realtime_browser.py`, Chrome 155.0.8059.85 remoto por CDP y HTTP
reenviados por SSH; medios host/UDP directos en LAN. Muestra conocida de consulta
de disponibilidad. Se verifico que el candidato remoto pertenece a alguna de las
direcciones **IPv4/IPv6** actuales de la Pi, sin asumir que ICE elige IPv4.

| Medida / escenario | Observado |
| --- | --- |
| Modelo / turnos de voz / herramienta | gpt-realtime-2.1 / 1 / check_availability |
| VAD recibido -> primer PCM / primer frame local | 485.159 / 497.273 ms |
| Fin de muestra -> primera señal en renderizador del navegador | 1411 ms |
| Duracion de la consulta de agenda falsa | 12.959 ms |
| Paquetes / bytes recibidos por Chrome | 1240 / 192362 |
| Reproduccion | paused=false; 24.845091 s |
| CPU media de un nucleo / pico RSS de backend | 21.45% / 115.988 MiB |
| Texto durante llamada / texto despues de colgar | Correctos, historial compartido |
| Recursos liberados / errores JavaScript | Correcto / 0 |

El primer audio puede preceder a completar una herramienta; el turno se etiqueta
`with_tools=true` y no se incluye entre latencias sin herramientas. La medicion
de WebAudio observa señal cada 20 ms, no el instante del altavoz fisico. Backend
VAD recibido excluye deteccion/red previas, por eso difiere del fin del archivo.

Consumo de la sesion de voz **incluido su mensaje escrito**: 6060 tokens de
entrada, 699 de salida y 52 de transcripcion. Estimacion: **USD 0.048934**, de los
cuales USD 0.00011 corresponden a transcripcion. El subtotal anterior al texto
(4846/657/52) no se suma otra vez. La sesion textual posterior tuvo 472 tokens de
entrada y 70 de salida (USD 0.003568 estimados), sin audio ni transcripcion.

Una ejecucion previa llego a conversar pero fallo una comprobacion que solo
admitia la IPv4 de la Pi: ICE habia elegido su IPv6. Ese intento tambien consume
API; no se recupero su uso al salir el verificador anterior. Por eso las cifras
anteriores son **por ejecucion identificada, no el gasto total de esta jornada**.
Se mejoro la salida de fallo del verificador para cerrar y conservar uso/metricas
si vuelve a fallar la comprobacion del peer. Revisar gasto acumulado en OpenAI.

## Tarifas y objetivos

Fuentes consultadas el 20 de octubre:

- [Modelo Realtime 2.1](https://developers.openai.com/api/docs/models/gpt-realtime-2.1).
- [Modelo Mini Transcribe](https://developers.openai.com/api/docs/models/gpt-4o-mini-transcribe).
- [Tarifas](https://developers.openai.com/api/docs/pricing).
- [Desglose y facturacion Realtime](https://developers.openai.com/api/docs/guides/realtime-costs).
- [VAD](https://developers.openai.com/api/docs/guides/realtime-vad).

Realtime: texto entrada/cache/salida USD 4/0.40/24 por millon; audio
USD 32/0.40/64. Mini Transcribe publica entrada USD 1.25 y salida USD 5 por millon;
se exige y conserva desglose de audio/texto de entrada. La estimacion no representa
factura ni controla el presupuesto del proveedor. Un modelo configurado diferente
requiere su tarifa verificada antes de poder informar total completo.

Las metas iniciales end-to-end sin herramientas son mediana <= 1500 ms y p95
<= 3000 ms. Estas observaciones puntuales no acreditan distribuciones ni SLA.
Los percentiles mostrados por backend son por sesion, sobre su referencia parcial,
con numero de muestras; no se comparan automaticamente como si fueran end-to-end.

## Runtime preparado

Al comenzar, la Pi estaba accesible pero no habia backend, laboratorio ni ngrok
activos. Se sincronizo el proyecto y se copio `.env` completo, con igualdad
byte a byte comprobada en memoria y permisos `600`, sin mostrar secretos.

- Backend operativo desde la raiz del mirror, loopback 8000 y ngrok existente
  iniciado de nuevo. Configuracion efectiva contrastada con `.env`.
- Salud `GET /`: 200 y `{"status":"ok"}`.
- Verificacion GET y evento POST vacio de webhook, locales y publicos: 200 y
  cuerpo esperado, sin invocar LLM ni enviar mensajes.
- Autenticacion WhatsApp de solo lectura: **401, codigo 190, subcodigo 463**
  (token expirado). Requiere credencial renovada para el ramal WhatsApp.
- Laboratorio Realtime en loopback 8001, token privado generado solo para este
  proceso. Overrides explicitos: `LAB_CALLS_ENABLED`, `LAB_AUDIO_MODE` y
  `LAB_ACCESS_TOKEN`. El resto de la configuracion coincide con el `.env` copiado.
- Salud de laboratorio autorizada: 200 y modo `realtime`; sin token: 401.
- Perfil persistente disponible: cero sesiones usadas de cinco al prepararlo;
  sesiones de hasta 120 s. Ninguna conexion OpenAI se inicia solo por abrir la pagina.
- Acceso desde Mac en `http://localhost:8001/lab` mediante SSH; token entregado
  por portapapeles local sin imprimirlo ni guardarlo en documentos. El laboratorio
  sigue necesitando que Mac/Pi tengan ruta UDP directa.

## Siguiente comprobacion humana

1. Abrir `http://localhost:8001/lab` y pegar el token de acceso.
2. Comprobar senalizacion, seleccionar **Microfono**, conectar y conceder permiso.
3. Escuchar el saludo; preguntar en español y escuchar la respuesta generada.
4. Hablar mientras responde: verificar que deja de escucharse la salida anterior
   y atiende la nueva intervencion. Revisar historial y panel de rendimiento.
5. Consultar disponibilidad/listado de la agenda falsa, colgar y comprobar que el
   texto del mismo perfil conserva contexto. Para retomar una gestion en otro
   canal se requiere solicitud explicita y nueva pregunta/confirmacion.

**Pendiente:** resultado humano con microfono/altavoces, distribuciones de latencia,
mas escenarios de gestion con modelo real, continuidad del paciente operativo
C4 y conexion Meta C1/C5 con numero elegible/habilitado. No se declara una llamada
WhatsApp real ni gestion operativa completa a partir del laboratorio.
