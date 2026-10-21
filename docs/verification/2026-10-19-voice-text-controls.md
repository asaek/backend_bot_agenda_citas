# Interrupciones, confirmaciones e historial voz/texto - 2026-10-19

## Estado y frontera

Implementado y verificado para el mismo paciente ficticio de `/lab`, elegido
explicitamente por el usuario. ADR 0057. Voz y texto comparten perfil, historial,
modelo Realtime, validacion y agenda falsa; no se vinculo el navegador con un
paciente operativo ni se enviaron mensajes WhatsApp o escrituras Google Calendar.

Codigo/documentacion editados localmente y sincronizados al mirror
`asaek@192.168.1.12:~/Downloads/chatbot_test_repo` antes de ejecutar pruebas.
Python 3.13.5, extras `audio`/`voice` y dependencias de `uv.lock` en la Pi.

## Regresion completa

**445 tests correctos en 56.478 s** en la Pi. Incluyen las reglas de chat
existentes y los nuevos escenarios de continuidad y persistencia.

### Audio y estados

- WebRTC/Opus real: se genera una salida conocida de 3 s, se interrumpe tras
  recibir parte de ella, se inyectan fragmentos tardios y se verifica que el
  receptor decodifica silencio despues del drenaje del encoder/jitter.
- El historial conserva `generated_ms > emitted_ms`, emision `interrupted` y
  generacion `completed` cuando el proveedor termino antes de interrumpir.
- Una cancelacion solicitada no cambia por si sola la generacion a `cancelled`.
  Un resultado final posterior del proveedor puede confirmar `completed`; si
  falta ese resultado al cerrar se registra `unknown`.
- Colgar conserva el progreso parcial conocido incluso antes de `response.done`.
  El cierre durable se reintenta sin volver a cerrar transportes.
- Fragmentos PCM que dividen una muestra se ensamblan; los eventos de otra
  generacion no reactivan audio. Una entrada textual demorada no reemplaza otra
  intervencion de voz mas reciente al reanudarse una escritura/cancelacion.

### Herramientas y confirmacion

- Un `si` escrito no confirma la pregunta de voz y no consume la secuencia de
  confirmacion de ese canal. La afirmacion hablada posterior puede continuar
  solo su propuesta vigente, en el turno esperado.
- Retomar por texto revalida los datos, genera otro ID/propuesta y exige otra
  pregunta completa y una respuesta posterior. Funciona tambien en una sesion
  nueva despues de colgar; ninguna autorizacion de la llamada anterior se copia.
- El texto real se contrasta con la decision del modelo: `Si, pero mejor a las
  once` no autoriza ejecutar los datos anteriores aunque el modelo solicite
  `decision=confirm`.
- `response.output_text.done` solo prepara texto. La propuesta textual se arma
  despues de emitir el cuerpo HTTP completo. Interrumpir antes de publicarlo no
  deja una autorizacion habilitada.
- Una gestion nueva marca las propuestas previas como `superseded`. Retomar no
  resucita la gestion reemplazada mientras se recaban los nuevos datos.
- `BookingDetails` comparte la validacion final de nombre/motivo con el flujo
  de chat de `ConversationService`, ademas de los contratos y `ToolExecutor` comunes.

### Historial e idempotencia

- Transcripciones tardias actualizan su clave y posicion originales, sin otro
  turno ni herramientas. Una actualizacion tardia no promueve una emision
  interrumpida a completada.
- Se distinguen `channel`, `generation_state`, `state`, `generated_ms` y
  `emitted_ms`. Una respuesta generada pero no emitida no se repite como ya dicha.
- Texto e historial requieren token; no aceptan identidad/canal del cliente y
  no existen en `main:app`.
- Repetir ID/cuerpo devuelve el resultado guardado. Reutilizarlo con otro texto
  se rechaza. Una escritura final fallida conserva el resultado para recuperarlo
  con el mismo ID sin otra respuesta del modelo ni efectos de herramientas.

La revision independiente detecto publicacion prematura, recuperacion de mensajes,
perdida de progreso al cerrar, cancelacion confundida con resultado y propuestas
reemplazadas recuperables. Las correcciones tienen pruebas de regresion especificas.

## Interfaz real con proveedor falso, sin consumo de API

`scripts/verify_lab_controls.py`, ejecutado en la Pi con Chromium real y WebRTC:

| Escenario | Resultado |
| --- | --- |
| Voz y texto comparten perfil/historial | Correcto |
| Respuesta HTTP perdida y reintento sin duplicar mensaje | Correcto |
| Texto despues de colgar recupera contexto | Correcto |
| Audio con emision registrada en historial | Correcto |
| Errores JavaScript / llamadas externas | 0 / 0 |

## OpenAI real desde Chrome en el Mac

Se extendio `scripts/verify_realtime_browser.py` para comprobar el recorrido de
voz, un mensaje escrito durante la llamada y otro despues de colgar. Backend y
driver corrieron en la Pi; Chrome 155.0.8059.85 corrio en macOS en un perfil
aislado, headless y silenciado. Entrada de voz sintetica conocida; no microfono
fisico. El peer remoto se verifico contra las direcciones de la Pi.

| Resultado | Observado |
| --- | --- |
| Modelo | `gpt-realtime-2.1` |
| Turnos de voz / consulta de disponibilidad | 1 / 1 |
| Reproduccion en Chrome | `paused=false`, `currentTime=27.701542 s` |
| RTP recibido | 1380 paquetes / 210685 bytes |
| Texto durante la llamada | Respuesta completa por la misma sesion |
| Texto despues de colgar | Respuesta completa con contexto recuperado |
| Recursos liberados / errores JavaScript | Correcto / 0 |

Consumo acumulado de la primera sesion, incluyendo voz y su mensaje escrito:
**6043 tokens de entrada, 713 de salida y 52 de transcripcion**. La sesion textual
posterior uso **475 de entrada y 38 de salida**, sin transcripcion. Los 4828/666
tokens observados antes del mensaje son un subtotal de la primera sesion y no
se suman otra vez. Se conserva desglose de audio/texto/cache por ID de respuesta.
El presupuesto inicial de referencia es 5 USD; no se infiere costo facturado
exacto a partir de un subtotal ni se cuentan otra vez reintentos de transporte.

## Como reproducir

Desde el mirror de la Pi tras sincronizar:

```sh
.venv/bin/python -m unittest discover -s tests -v
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_controls.py
```

La prueba siguiente consume API real y crea sus bases/backend temporales:

```sh
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_realtime_browser.py
```

Para Chrome remoto se usan los reenvios HTTP/CDP y las opciones documentadas en
la [verificacion de voz nativa](./2026-10-19-native-realtime-voice.md). En uso manual
basta iniciar el laboratorio `realtime`, abrir localhost mediante SSH e introducir
el token. El panel de texto usa al mismo paciente ficticio y permite escribir
durante la llamada o despues de pulsar Colgar.

## Pendientes delimitados

- Escucha humana y microfono real, con mediciones perceptuales de interrupcion.
- Mayor cobertura con el modelo real de preguntas/confirmaciones de cita; el
  control de mutaciones se verifico con dobles sobre agenda falsa.
- Vincular identidad y gestiones con el bot/paciente operativo y Meta Calling:
  no forman parte del perfil ficticio aprobado para esta prueba.
