# ADR 0050 - Interpretacion hibrida de la seleccion pendiente

## Estado

Aceptada. Implementada en `appointment_slot_selection.py` y `ConversationService`.

## Contexto y decision

El reconocimiento completo de seleccion rechaza `a las 9 am estaria bien` y
`si a las 9 am esta bien`, aunque la intencion sea clara. Ampliar indefinidamente
las expresiones no cubre el lenguaje natural; entregar el control al agente
general permitiria reconstruir una gestion sin usar el snapshot autoritativo.

Se conserva una via local rapida y se agrega interpretacion estructurada de IA
solo para selecciones no reconocidas sobre la disponibilidad pendiente. El modelo
recibe referencias efimeras a los slots y evidencia del mensaje, sin herramientas
ni IDs de paciente/cita. El backend valida el resultado y usa una unica
interpretacion en enrutamiento y seleccion. El resultado nunca autoriza una
mutacion, sustituye la disponibilidad real ni cambia la vigencia.

Amplia ADR 0029 y ADR 0044 en la interpretacion del lenguaje; conserva su control
de estado y las confirmaciones locales de ADR 0049. Un fallo del modelo conserva
la gestion y pide aclaracion. La llamada adicional aporta flexibilidad a cambio
de latencia solo en expresiones no resueltas localmente.
