# 0010 - Frontera interna del ejecutor de herramientas

## Estado

Aceptada para el incremento del ejecutor del contrato de herramientas.

## Contexto

El contrato de herramientas ya define solicitudes, reglas, proveedores falsos y
errores publicos, pero todavia faltaba un punto unico que coordinara esas capas.
El tool calling del LLM no esta implementado y no debe decidir el paciente, la
conversacion ni los calendarios.

## Decision

Se implementa `ToolExecutor.execute()` como frontera interna que recibe un
`ToolRequest`. El request contiene el `PatientScope` resuelto por el backend. El
ejecutor parsea y normaliza argumentos, aplica primero validaciones locales y
obtiene una fotografia de citas con ese alcance cuando necesita verificar
conflictos, pertenencia o estado.

Despues despacha exactamente una operacion del protocolo `CalendarProvider` y
envuelve el resultado en el output tipado de la herramienta. Tanto los exitos
como los fallos se devuelven como `ToolResult`; las excepciones se convierten con
`tool_result_from_exception()` y no se propagan al agente.

Los calendarios siguen siendo responsabilidad de la configuracion del proveedor.
Los argumentos reservados se rechazan antes de ejecutar y no existe una ruta
publica para sustituir el `PatientScope`.

## Consecuencias

- Las cinco herramientas pueden probarse directamente con `ToolRequest`.
- La integracion futura del LLM solo tendra que construir requests validables.
- Las reglas locales se mantienen separadas de la implementacion de Google.
- La fotografia de citas no reemplaza el conflicto atomico que debe comprobar el
  proveedor durante la escritura.

## Alternativas descartadas

- Ejecutar proveedores directamente desde `main.py`.
- Dejar que el LLM llame metodos del proveedor con diccionarios libres.
- Integrar tool calling antes de disponer de un ejecutor probado.
