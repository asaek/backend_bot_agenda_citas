# Consulta de historial de voz y texto — 2026-10-21

## Alcance implementado

Paso 4 de ADR 0061 y CA-26 del corte 021: `search_conversation_history` para el
perfil ficticio de `/lab`. Solo admite tema, fechas y canal; la identidad, zona
horaria y sesion actual excluida provienen del servidor. La busqueda literal AND
normaliza acentos/mayusculas, admite hasta ocho palabras/120 caracteres y devuelve
seis fragmentos de 600 caracteres como maximo, con `has_more` si existen otros.

Las fechas `YYYY-MM-DD` son inclusivas e interpretadas en la zona de agenda.
Se filtra el inicio de sesion, con `date_basis=session_started_at` y
`date_precision=session`, sin inventar fecha por turno. Los fragmentos incluyen
sesion/estado/fecha, item/orden, canal/rol y estados de generacion/transcripcion/
emision. No establecen el resultado ni la vigencia actual de una cita.

La lectura SQL es parametrizada y `query_only`. El ejecutor conserva la auditoria
idempotente de herramientas, sin invocar agenda ni activar/cambiar propuestas.
Un turno exclusivo de busqueda no invalida una propuesta al finalizar y no puede
vincular una pregunta historica a la autorizacion actual. Vencimientos,
interrupciones, cierre y turnos con otras herramientas conservan sus controles.

## Reproduccion y pruebas focalizadas

Cambios locales sincronizados antes de ejecutar en la Raspberry:

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice_history_search.py -v
```

Antes de implementar, el primer caso fallo por ausencia de `search_history` y el
ejecutor rechazo la herramienta como no permitida. La prueba de flujo completo
detecto despues que citar una pregunta antigua volvia a vincular `item_id` de la
propuesta actual; se corrigio el enlace para turnos exclusivos de historial.

**13 pruebas focalizadas correctas** cubren:

- Consulta fuera de los ultimos 12 mensajes, con tema/fecha local/canal combinados.
- Aislamiento entre perfiles y exclusion de la sesion actual.
- Limite, orden, truncado cerca de coincidencia y `has_more`.
- `%`, `_` y comillas literales, ausencia de coincidencias y filtros invalidos.
- Transcripcion ausente y salida interrumpida con emision parcial.
- Preservacion de propuesta/pregunta/vencimiento y rechazo de identidad inyectada.
- Reintento idempotente y consulta sin crear una gestion.
- Turnos mixtos que mantienen la invalidacion previa.
- Cita de una pregunta antigua por voz o texto publicado sin volver a vincularla.
- Cita emitida antes de invocar la herramienta, ligada solo al turno/canal que
  preparo la propuesta; una respuesta posterior no puede reemplazar su `item_id`.
- Fechas en el limite de medianoche con precision de microsegundos. Se sustituyo
  la comparacion `julianday()` por instantes UTC canonicos para evitar redondeos.

Las suites focales existentes de herramientas, contratos y continuidad tambien
pasaron.

## Verificacion integrada y revision

Desde la raiz del mirror de la Raspberry:

```bash
.venv/bin/python -m unittest discover -s tests
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_controls.py
```

- **489 pruebas correctas en 69.215 s**, despues de corregir los dos bordes
  detectados en revision. Ambos tuvieron reproduccion roja y regresion verde.
- Chromium/WebRTC real con proveedor falso: correcto, cero errores JavaScript
  y cero llamadas externas. Conserva voz/texto, reintentos sin duplicados,
  contexto tras colgar y microfono simulado con RTP creciente.
- **Standards:** sin hallazgos accionables.
- **Spec:** dos P2 iniciales (cita previa a invocar la herramienta y redondeo de
  medianoche), corregidos y cerrados en una segunda revision; sin pendientes.

## Sincronizacion y runtime

Se comprobaron argumentos, directorio y listener antes de recargar el laboratorio;
no habia unidades systemd del proyecto ni sesiones activas de llamada/texto. Se
recargo `main:create_lab_app --factory` en loopback 8001 desde la raiz del mirror,
PID **2105055 -> 2149568**, con la configuracion existente de la Pi cargada y
`.env` en modo `600`, sin exponer valores. La comparacion por checksum del codigo
y sus pruebas no mostro diferencias antes de la recarga.

| Comprobacion | Resultado |
| --- | --- |
| `GET /lab/health`, Pi y Mac | HTTP 200, Realtime, proveedor Google |
| `GET /lab`, Pi y Mac mediante `http://localhost:8001/lab` | HTTP 200 |
| `GET /lab/history`, Pi | HTTP 200 |
| Lectura directa de historial existente con el repositorio nuevo | Seis fragmentos acotados y con procedencia; sin imprimir su contenido |

Las comprobaciones de acceso y la lectura directa no ejecutan OpenAI ni
herramientas de agenda. El navegador usa proceso, perfil, base y agenda de prueba
temporales, separados del laboratorio recargado.

## Fronteras

Verificacion con dobles, datos sinteticos y SQLite temporal, sin consumo de APIs
ni eventos Google. La herramienta busca palabras, no similitud semantica. La
ventana reciente sigue usando su representacion anterior; el contexto enriquecido
y la correlacion de resultados de acciones del paso 2 siguen pendientes. No se
conecta la identidad ni el historial del WhatsApp operativo.
