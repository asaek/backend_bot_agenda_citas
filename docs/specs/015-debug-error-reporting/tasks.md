# Tareas - Diagnostico seguro de errores en modo debug

## Implementacion

- [x] Crear un modulo de diagnostico que limite el texto a campos seguros.
- [x] Exigir bandera activa y allowlist de numeros antes de mostrar detalles.
- [x] Integrar el diagnostico con fallos LLM y respuestas de herramienta no manejadas.
- [x] Documentar las variables de entorno y su valor predeterminado.

## Verificacion

- [x] Probar HTTP 429 para remitente autorizado.
- [x] Probar modo apagado y remitente no autorizado.
- [x] Confirmar que no se filtra texto entrante ni contenido crudo del proveedor.
- [x] Probar que un error publico de agenda muestra su codigo solo al remitente permitido.
- [x] Ejecutar la suite en la Raspberry Pi y verificar health check y webhooks.
