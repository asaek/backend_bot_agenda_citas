# Saludo aislado de la continuacion — 2026-10-21

## Alcance implementado

Paso 3 de la ADR 0061 y CA-22 del corte 021: voz y mensajes del perfil ficticio de
`/lab`. El historial reciente se prepara al conectar. El saludo usa una respuesta
Realtime fuera de banda con `conversation=none`, `input=[]`, `tools=[]` y
`tool_choice=none`, con instrucciones exclusivas de presentacion. Los turnos
posteriores usan la conversacion predeterminada con historial y entrada actual.

Interrumpir cancela por ID y corta audio local, sin recortar/eliminar items del
saludo en la conversacion remota. Se rechazan audio/herramientas obsoletos y el
despacho de herramientas del turno 0. El ACK tardio se cancela antes de atender
la intervencion pendiente; hablar antes del evento de conexion evita un saludo
tardio. La salida y su emision parcial se conservan localmente para el historial.

## Reproduccion y pruebas focalizadas en la Raspberry

Los cambios se hicieron localmente y se sincronizaron antes de cada ejecucion.
Desde la raiz del mirror:

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice_greeting.py -v
.venv/bin/python -m unittest discover -s tests -p test_realtime_provider.py -v
.venv/bin/python -m unittest discover -s tests -p test_lab_continuity.py -v
```

- Primer escenario antes del cambio: fallo porque la solicitud inicial no
  establecia `conversation=none` ni contexto vacio. Tras la implementacion pasa
  conservando los antecedentes de voz/texto para la intervencion actual.
- Interrupcion antes del ajuste: fallo porque se enviaba `conversation.item.truncate`
  para un item del saludo fuera de banda. Tras el ajuste se cancela sin editar
  la conversacion remota y el audio tardio no se reactiva.
- Herramienta inesperada durante el saludo: inicialmente se despachaba; ahora el
  backend la ignora antes de parsear argumentos o ejecutar herramientas.
- **6 pruebas de apertura correctas**: saludo sin historial/herramientas, memoria
  conservada, interrupcion por voz/texto, ACK tardio y habla antes de conexion.
- **4 pruebas de proveedor correctas**, incluido WebSocket local real que verifica
  los eventos enviados, historial previo y contexto vacio del saludo.
- **11 pruebas de continuidad correctas**, con idempotencia, publicacion textual
  y autorizaciones de voz/texto conservadas.

## Verificacion integrada y runtime

Desde la raiz del mirror de la Raspberry:

```bash
.venv/bin/python -m unittest discover -s tests -v
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_controls.py
```

- Regresion completa: **476 pruebas correctas en 66.753 s**.
- Chromium/WebRTC real con proveedor Realtime falso: **correcto**, sin errores
  JavaScript y con cero llamadas externas. Comprueba voz/texto, reintento de
  respuesta perdida sin duplicar, contexto tras colgar y microfono simulado con
  RTP creciente (26 paquetes enviados/recibidos, 6 frames no silenciosos).
- Revision independiente: **Standards: 0 hallazgos; Spec: 0 hallazgos** dentro
  del alcance de apertura independiente; la memoria enriquecida sigue pendiente.
- Comparacion por checksum de los archivos del incremento entre checkout y Pi:
  sin diferencias antes de recargar el laboratorio.

Se comprobaron argumentos, directorio y listener del laboratorio; no habia unidades
systemd del proyecto ni sesiones de llamada/texto activas. Se recargo el proceso
de `main:create_lab_app --factory` en loopback 8001, PID **1820114 -> 2105055**,
desde `/home/asaek/Downloads/chatbot_test_repo`. El nuevo listener cargo la
configuracion existente de la Pi, con `.env` en modo `600`, sin exponer valores.

| Comprobacion | Resultado |
| --- | --- |
| `GET /lab/health` desde Pi y Mac | HTTP 200, Realtime, proveedor Google |
| `GET /lab` desde Pi y `http://localhost:8001/lab` desde Mac | HTTP 200 |
| `GET /lab/history` desde Pi | HTTP 200 |

Estas consultas de acceso no abren una conexion de pago ni ejecutan herramientas
de agenda. La prueba de navegador usa su propio proceso/base temporales y agenda
falsa, separados del laboratorio recargado.

## Fronteras

Las pruebas usan dobles y un WebSocket local; no consumen OpenAI ni crean citas
Google. No acreditan una escucha humana ni una nueva conversacion con el modelo
real. La representacion enriquecida con fecha/sesion/resultados y la busqueda de
antecedentes antiguos siguen pendientes (pasos 2 y 4 de la ADR 0061). La ventana
de 12 mensajes mantiene su representacion previa. El WhatsApp operativo conserva
su integracion separada.

Referencia del protocolo: [respuestas fuera de la conversacion y contexto
personalizado](https://developers.openai.com/api/docs/guides/realtime-conversations#create-responses-outside-the-default-conversation).
