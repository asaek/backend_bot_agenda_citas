# Contrato aprobado - aviso_cita_medico

## Estado

Aprobacion reportada por el usuario el 23 de octubre de 2026. Configuracion adoptada
en `.env.example` y `.env` local. El token renovado autentica correctamente, pero
la prueba real devuelve `132001`: la cuenta del emisor configurado es
`Test WhatsApp Business Account` (`1047483564765260`) y su catalogo solo
incluye `hello_world` en `en_US`. La URL del panel proporcionada por el usuario
contiene `asset_id=2157628355165252`, candidato a WABA cuyo tipo y acceso aun no
se confirmaron por API. Ese ID no aparecia en los targets del token inspeccionado
el 23/10/2026; sus consultas devuelven `100/33`, que por si solo no distingue
ID incorrecto, falta de acceso u operacion incompatible. Falta validar el activo
en la misma cartera del panel y despues confirmar su numero emisor. La
[guia de diagnostico](../../whatsapp-meta-accounts.md) conserva los criterios.
Evidencia en
`../../verification/2026-10-23-approved-doctor-template.md`.

- Nombre exacto: `aviso_cita_medico`.
- Idioma: Español de Mexico, codigo `es_MX`.
- Encabezado fijo: `NOTIFICACION INTERNA DE CITA`.
- Parametros: nueve variables posicionales de texto en el componente `body`.
- Pie y botones: no informados como parte de la plantilla.

El encabezado y el texto fijo se renderizan en Meta. El request solo proporciona
el componente `body`, sin `parameter_name`, respetando el orden siguiente:

| Variable Meta | Campo del compositor | Ejemplo aprobado proporcionado |
| --- | --- | --- |
| `{{1}}` | `event_type` | Cita cancelada |
| `{{2}}` | `date` | 2026-10-23 |
| `{{3}}` | `time` | 10:00-10:30 |
| `{{4}}` | `reason` | Revisión general |
| `{{5}}` | `status` | cancelada |
| `{{6}}` | `patient_name` | Paciente de prueba |
| `{{7}}` | `patient_phone` | No informado |
| `{{8}}` | `summary` | El paciente solicita una revisión general de los ojos. |
| `{{9}}` | `priority_signals` | Ninguna detectada. |

Los ejemplos no son valores fijos: cada aviso usa sus propios datos saneados.
`No informado` corresponde a una identidad de laboratorio sin numero vinculado;
un paciente de chat conserva la presentacion actual de su telefono.

## Cuerpo reportado como aprobado

```text
Tipo de evento: {{1}}

CITA
Fecha: {{2}}
Hora: {{3}}
Motivo: {{4}}
Estado: {{5}}

PACIENTE
Nombre: {{6}}
Telefono: {{7}}

RESUMEN DE LA CONVERSACION
{{8}}

SENALES DE PRIORIDAD
{{9}}

Aviso automatico de la gestion de citas del consultorio.
```

## Configuracion adoptada

```dotenv
DOCTOR_NOTIFICATION_TRANSPORT=template
DOCTOR_WHATSAPP_TEMPLATE_NAME=aviso_cita_medico
DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE=es_MX
DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS='[{"type":"body","parameters":[{"type":"text","text":"{event_type}"},{"type":"text","text":"{date}"},{"type":"text","text":"{time}"},{"type":"text","text":"{reason}"},{"type":"text","text":"{status}"},{"type":"text","text":"{patient_name}"},{"type":"text","text":"{patient_phone}"},{"type":"text","text":"{summary}"},{"type":"text","text":"{priority_signals}"}]}]'
```

El destinatario se conserva en `DOCTOR_WHATSAPP_NUMBERS`. Este contrato no crea
citas ni sustituye datos del paciente por los ejemplos. La prueba automatizada
compara los nueve valores del ejemplo con el JSON real construido por el cliente
HTTP, utilizando el compositor y un transporte de Meta simulado.
