# Memoria operativa: cuentas, numeros y acceso de Meta WhatsApp

## Uso y procedencia

Consultar esta guia al diagnosticar IDs de Meta, acceso a cuentas, disponibilidad
de plantillas o errores `100/33` y `132001`, antes de cambiar configuracion.
Resume la conversacion aportada por el usuario y la
[evidencia del 23/10/2026](verification/2026-10-23-approved-doctor-template.md).
Las observaciones fechadas son antecedentes; verificar de nuevo los activos y el
acceso efectivos cuando cambien el token o la configuracion.

## Estado mas reciente comprobado: 25/10/2026

El token actualizado autentica con HTTP 200 y el catalogo de la WABA comprobada
`1047483564765260` ahora devuelve `aviso_cita_medico`, `es_MX`, `APPROVED`, junto a
`hello_world`. Encabezado, cuerpo y nueve variables coinciden con el contrato.
El emisor configurado pertenece a esa cuenta y es distinto del doctor.

Una prueba controlada al doctor terminado en `3338` fue aceptada y Meta confirmo
`delivered` el 25/10/2026 a las **19:58:57 UTC**, correlacionando el ID completo
de la respuesta y el destinatario. Evidencia en
[la prueba real](verification/2026-10-25-approved-template-delivered.md).
No se cambiaron los IDs del emisor ni se modifico la agenda.

El activo candidato `2157628355165252` sigue sin estar confirmado por API con
este token (`100/33`), pero ya no bloquea el envio verificado desde la cuenta
actual. Los hechos del 23/10 se conservan como historia, no como estado vigente.

## Distinciones que hay que conservar

| Dato | Que representa | Uso en el proyecto |
| --- | --- | --- |
| `business_id` del panel | Contexto de la cartera empresarial seleccionada | Revisar que las pantallas usen la misma cartera |
| WABA ID | Cuenta de WhatsApp Business | Consultar sus numeros y plantillas |
| Phone Number ID | ID de un numero registrado en una WABA | Valor de `WHATSAPP_PHONE_NUMBER_ID` |
| Numero visible de WhatsApp | Telefono con codigo de pais | Identificar al emisor o destinatario, no sustituir IDs de Meta |
| `asset_id` de la URL | Activo seleccionado por la interfaz | Pista para localizar la cuenta; su tipo requiere confirmacion |
| Access Token | Credencial con permisos sobre determinados activos | `WHATSAPP_ACCESS_TOKEN` en `.env`, tratado como secreto |

`asset_id` es un **parametro de consulta** de la URL, no un segmento del path.
Que un ID figure en la URL no demuestra que sea un WABA accesible por el token.
Los nombres visibles, incluida `hello_world`, tampoco identifican univocamente
una cuenta. Una pantalla que solo muestra `Test Number` no identifica por si sola
la cuenta que contiene una plantilla.

## Hechos y pistas registrados el 23/10/2026

| Observacion | Valor | Respaldo y limite |
| --- | --- | --- |
| WABA de pruebas consultado | `1047483564765260` | API: nombre `Test WhatsApp Business Account`; `phone_numbers` incluye el emisor configurado |
| Catalogo accesible en esa WABA | `hello_world`, `en_US`, `APPROVED` | Listado completo consultado con el token de esa comprobacion |
| Cartera en la URL del usuario | `2156006571926745` | Parametro `business_id`; contexto de la interfaz |
| Activo en la URL del usuario | `2157628355165252` | Parametro `asset_id`; candidato a WABA, tipo y acceso aun sin confirmar por API |
| ID candidato presente en los targets de los scopes inspeccionados | No | Diferencia observable; no prueba por si sola la naturaleza o existencia del activo |
| Consultas del ID candidato | HTTP 400, `100/33` | Cuenta, numeros y plantillas no se pudieron inspeccionar |
| Plantilla requerida | `aviso_cita_medico`, `es_MX` | Aprobacion reportada por el usuario y contrato local configurado; disponibilidad para el emisor pendiente |
| Prueba con el emisor configurado | HTTP 404, `132001` | Meta no acepto el mensaje; no hay evidencia de entrega |

El contrato y los nueve parametros de la plantilla se mantienen en
[approved-template.md](specs/011-doctor-notifications/approved-template.md).
Esta guia no duplica ese mapeo ni guarda credenciales.

## Interpretar los errores sin saltar a conclusiones

- **`100/33`**: el objeto puede no existir, no ser accesible con ese token o no
  admitir la operacion solicitada. El codigo aislado no decide cual de esas causas
  corresponde y no demuestra que la plantilla no exista en el panel del usuario.
- **`132001`**: revisar nombre, idioma y cuenta del emisor donde se busca la
  plantilla. Una aprobacion en el panel no acredita disponibilidad para cualquier
  numero de otra cuenta.
- **HTTP 200 en una consulta autenticada**: acredita acceso a ese recurso concreto,
  no acceso a todas las WABA ni permisos de envio sobre otros activos.
- **HTTP 200 al enviar con un ID devuelto**: acredita aceptacion de API. La entrega
  se comprueba con callbacks `delivered` o `read`, segun la
  [especificacion de notificaciones](specs/011-doctor-notifications/spec.md).

## Secuencia de comprobacion

### 1. Alinear la vista del panel

Abrir la pantalla donde aparece la plantilla y anotar la cartera empresarial,
la cuenta seleccionada, su URL y el idioma exacto. Revisar esa misma cartera en
Configuracion del negocio → Cuentas → Cuentas de WhatsApp. Los campos visibles
cambian entre versiones del panel; pedir URL o captura cuando el ID no aparezca.

**Completado cuando:** se puede relacionar la vista de plantillas con su cartera y
un identificador candidato, sin confundir nombre de cuenta, telefono e ID.

### 2. Comprobar permisos y asignacion del activo

El token necesita los permisos `whatsapp_business_management` y
`whatsapp_business_messaging` y acceso al activo correspondiente. Si se usa un
usuario del sistema, revisar Usuarios → Usuarios del sistema → Activos asignados.
Para otro tipo de token, revisar la autorizacion e integracion empresarial de
la aplicacion que lo emite, sin asumir que siempre es un usuario del sistema.
El resultado de `debug_token` ayuda a contrastar scopes y targets cuando esten
disponibles. Cambiar asignaciones o renovar el token segun el resultado, no como
conclusion automatica de `100/33`.

**Completado cuando:** la asignacion y las consultas autorizadas permiten comprobar
el activo, o el bloqueo queda registrado como acceso/tipo de objeto sin resolver.

### 3. Confirmar cuenta, numeros y plantilla mediante API

Usar la version de Graph que tenga configurada el cliente y credenciales en memoria:

```text
GET /{candidate_waba_id}?fields=id,name
GET /{candidate_waba_id}/phone_numbers?fields=id,display_phone_number,verified_name
GET /{candidate_waba_id}/message_templates?name=aviso_cita_medico&fields=name,language,status,components
```

Una respuesta autorizada de `phone_numbers` permite confirmar el objeto de cuenta
y obtener el `id` del numero que requiere el bot. El ID candidato no se convierte
en Phone Number ID por aparecer en la URL. Si la cuenta no tiene numeros o tiene
varios, identificar el emisor esperado antes de elegir uno. Si las consultas
siguen devolviendo `100/33`, conservar el tipo/acceso como pendientes.

**Completado cuando:** estan confirmados la WABA, el numero emisor y su Phone Number
ID, y el catalogo de esa misma cuenta devuelve la plantilla/idioma esperados.

### 4. Aplicar configuracion y verificar

Actualizar `WHATSAPP_PHONE_NUMBER_ID` solo con el `id` del numero emisor confirmado.
Mantener `DOCTOR_WHATSAPP_NUMBERS` como configuracion independiente del destinatario.
Aplicar cambios localmente y seguir el flujo de transferencia y recarga de
`AGENTS.md`; el alcance de una rotacion de token conserva las otras variables.
Comprobar configuracion efectiva y autenticacion antes de la prueba controlada.

**Completado cuando:** el proceso usa la configuracion confirmada y una solicitud
controlada obtiene evidencia de Meta correlacionada con ID y destinatario. Un
rechazo o una aceptacion sin callback de entrega se documentan como tales.

## Si se retoma el activo del panel

Para una investigacion o cambio de cuenta posterior, confirmar el tipo y acceso
del activo `2157628355165252` en la misma cartera del panel. La aprobacion y el
envio de la plantilla para el emisor actual ya estan verificados; consultar ese
otro activo solo corresponde si vuelve a ser necesario para el objetivo pedido.
