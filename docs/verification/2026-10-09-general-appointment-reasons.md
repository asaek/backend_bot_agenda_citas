# Verificacion - Motivos generales y aclaraciones diferenciadas

## Fecha y estado

9 de octubre de 2026. Implementado y verificado en el mirror
`/home/asaek/Downloads/chatbot_test_repo` de Raspberry Pi.
SDD: RF-1314, RF-1315 y RF-1316 de la especificacion 013; ADR 0048.

## Comportamiento comprobado

- `Tengo problemas en el ojo izquierdo` crea una unica cita con el texto del
  paciente, incluso si el evaluador pide detalle, devuelve baja confianza o falla
  con una respuesta que no es JSON. El respaldo local queda registrado como regla,
  sin presentar su confianza como confianza del modelo. El fallo sigue en `llm_failures`.
- Una categoria oftalmologica reconocida con confianza basta aunque el modelo
  responda `needs_clarification`; no se exige diagnostico ni detalle clinico.
- Un fallo de formato o llamada sin respaldo local responde como problema tecnico,
  conserva el horario y permite que el mismo motivo complete una cita tras recuperarse
  el evaluador y reconstruir `ConversationService`.
- Baja confianza expresa incertidumbre de la evaluacion. No se afirma que un motivo
  sea ajeno a la consulta cuando su clasificacion tiene baja confianza.
- Las aclaraciones citan el texto legible recibido o reconocen la referencia a una
  consulta anterior. Desde el segundo intento ofrecen opciones y desde el tercero
  explican que basta un motivo general; conservan revision, seguimiento y molestia.
- `ok` y `Si` se reconocen como respuestas legibles que todavia no dan un motivo.
- `Tengo molestias en la vista, como siempre` conserva el motivo completo y se acepta.
  Referencias solas como `Es por lo de siempre` y `Lo de siempre, por favor` siguen
  pidiendo aclaracion, tambien con el evaluador LLM desactivado.
- Motivos negados, ajenos o con instrucciones añadidas no obtienen aceptacion local
  por contener palabras del respaldo. Las respuestas rechazadas no emiten eventos
  de cita; un motivo suficiente posterior crea una sola cita en el horario original.

## Pruebas

Se sincronizo el codigo antes de cada ejecucion. Se añadieron quince pruebas del
flujo en `tests/test_appointment_reason_collection.py` y una regresion del validador,
ademas de actualizar las expectativas de aclaracion existentes.

Desde la raiz del mirror, con notificaciones desactivadas solamente en el proceso
de pruebas para aislar la configuracion real del consultorio:

```text
DOCTOR_NOTIFICATIONS_ENABLED=false .venv/bin/python -m unittest discover -s tests
Ran 324 tests
OK
```

Las pruebas que requieren notificaciones las habilitan explicitamente en sus dobles.
La configuracion del backend desplegado conserva los valores completos de `.env`.
La compilacion de los modulos afectados tambien paso. La revision de estandares no
encontro incumplimientos; los casos de borde encontrados en la revision de especificacion
se corrigieron y tienen regresiones ejecutables.

## Sincronizacion, configuracion y runtime

Se copio el proyecto y se reemplazo el `.env` completo con el archivo local. La
comparacion byte a byte en memoria confirmo igualdad y modo `600`, sin imprimir
valores ni hashes. Durante la verificacion hubo cortes de conexion SSH; se
recupero el acceso y se repitio la sincronizacion final.

La primera comprobacion de autenticacion detecto un token de WhatsApp vencido
(`401`, codigo `190`, subcodigo `463`). El usuario actualizo la configuracion local.
Posteriormente se detecto `LLM_MAX_HISTORY_MESSAGES` invalido; el usuario lo corrigio
en el archivo local y se volvio a copiar el `.env` completo.
La validacion final de configuracion LLM paso y la autenticacion de Meta devolvio `200`.

Se reexaminaron unidades systemd de sistema/usuario, puerto y procesos. No se
encontro una unidad del proyecto ni un backend activo despues de la desconexion.
Se inicio Uvicorn manualmente desde la raiz del mirror con PID `96239`, escuchando
en `127.0.0.1:8000`, y ngrok con PID `96317`. La configuracion efectiva del backend
coincidio con `.env` en memoria. Las recargas posteriores apuntan solo al PID
verificado, comprueban su directorio y comando, y esperan que el puerto quede libre.

## Rutas y autenticacion

```text
local  GET /                 -> 200, {"status":"ok"}
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, {"status":"ok"}
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
Meta   GET phone resource    -> 200, autenticacion valida
```

Los POST usaron eventos vacios. La consulta de Meta fue de solo lectura con
`fields=id` y la version de Graph API del cliente. Las pruebas de agendamiento
usaron proveedores falsos y SQLite temporal, sin crear citas reales ni enviar
mensajes a pacientes o doctores.
