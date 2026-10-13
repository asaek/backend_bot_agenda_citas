# Diseno - Seleccion hibrida de horarios

## Estado

Implementado. ADR 0050 registra la frontera del modelo.

## Flujo

`ConversationService` carga el snapshot activo o pausado al comenzar el turno y
obtiene un unico resultado de interpretacion. Primero aplica el reconocimiento
local y las interrupciones existentes. Las expresiones claras continúan sin IA;
las gestiones nuevas, abandonos y preguntas informativas mantienen sus rutas.

Un modulo `appointment_slot_selection.py` interpreta las expresiones restantes.
Recibe mensaje, flujo, snapshot y zona horaria. Rechaza localmente condiciones,
negaciones, varias horas y referencias incompatibles antes de consultar el modelo.
El proveedor existente genera texto sin publicar herramientas de calendario.

El JSON contiene una intencion (`select`, `clarify`, `abandon` o `switch`), una
referencia efimera a un slot y evidencia literal del mensaje. El backend valida
el esquema, la evidencia y la pertenencia a la lista; un resultado no fiable
conserva el snapshot y solicita aclaracion. La confianza declarada por el modelo
no sustituye estas comprobaciones.

La validacion rechaza una hora numerica no parseable, periodos incompletos y
afirmaciones sin referencia a una opcion. Las menciones de horas escritas con
palabras se distinguen de cantidades como `dos horarios`; una representacion
redundante `las nueve (9 am)` no se cuenta como dos opciones. Los fallos del
proveedor llevan tipo y codigo HTTP al registro existente, sin contenido sensible.
`time_selection_references()` comparte el patron de horas existente; las referencias
se comparan con minutos y periodo completos. `nueve en punto` y `9:30`, o `nueve
de la mañana` y `nueve de la noche`, no se deduplican como una misma opcion.

El resultado se pasa explicitamente a pausa, enrutamiento y resolucion de la
disponibilidad. No se guarda en el servicio como estado mutable compartido entre
pacientes. Solo el backend prepara la confirmacion o la captura de nombre/motivo.
La disponibilidad se revalida al ejecutar y la confirmacion de cambios sigue local.

## Dependencias y persistencia

Se reutiliza `LLMProvider` y su modo texto. No se agregan paquetes, variables de
configuracion, migraciones ni un proveedor externo nuevo. Los slots conservan su
representacion ISO y su vigencia de diez minutos. Las referencias del evaluador
solo son validas dentro de una solicitud; no se aceptan IDs de citas del modelo.
