# 0007 - Validacion de herramientas antes del proveedor

## Estado

Aceptada para el tercer incremento del contrato de herramientas.

## Contexto

Los contratos tipados evitan argumentos desconocidos, pero algunas reglas
dependen del reloj, el horario laboral y las citas existentes. Esas reglas no
deben quedar delegadas a Google Calendar ni a una respuesta del LLM.

## Decision

Se implementa `validate_tool_input()` como una validacion pura previa al
proveedor. Recibe `BusinessHours`, el instante actual y las citas existentes
conocidas. Comprueba fechas futuras, horario laboral, duracion fija, conflictos,
pertenencia del paciente y transiciones de estado.

Los errores se exponen mediante `ToolValidationError` con un
`ToolErrorCode`. El futuro `ToolExecutor` ejecutara el proveedor solo despues de
que esta validacion termine correctamente.

## Consecuencias

- Las reglas de negocio se prueban sin red ni credenciales.
- Un proveedor no recibe solicitudes obviamente invalidas.
- El ejecutor debe disponer de una fotografia de citas para detectar conflictos.
- La disponibilidad definitiva de calendarios externos seguira requiriendo una
  verificacion del proveedor durante la ejecucion.

## Limite

La validacion previa no reemplaza la comprobacion atomica del proveedor. Entre
la validacion y la creacion real puede aparecer un conflicto, que el proveedor
debe rechazar y el ejecutor debe traducir.
