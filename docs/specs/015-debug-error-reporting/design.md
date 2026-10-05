# Diseno - Diagnostico seguro de errores en modo debug

## Componentes

`main.py` conserva el manejo central de fallos del webhook. `debug_reporting.py` decide si
el remitente esta autorizado y construye un texto con campos seguros. El modulo recibe la
configuracion como entorno inyectable para poder probar el limite sin acceder a secretos.

## Configuracion

- `DEBUG_MODE`: bandera booleana, predeterminada a `false`.
- `DEBUG_WHATSAPP_NUMBERS`: lista separada por comas de numeros de prueba autorizados,
  predeterminada vacia.

Ambas condiciones son necesarias. Los numeros se normalizan conservando solo digitos.

## Flujo

1. `main.py` captura un `LLMProviderError` o una respuesta `ToolCall` no manejada.
2. El fallo se persiste y se registra con el tipo y codigo HTTP ya existentes.
3. `debug_reporting.py` valida bandera y remitente.
4. Si esta autorizado, devuelve proveedor, tipo de error y codigo HTTP disponible; los
   errores de agenda pueden incluir su codigo publico estable. En otro caso se conserva
   la respuesta controlada o publica normal.
5. El webhook envia y persiste la respuesta con el flujo habitual.

El diagnostico nunca usa `str(error)` ni lee el cuerpo o encabezados de la respuesta HTTP.

## Pruebas

Las pruebas de `main.py` usan `FakeLLMProvider`, `FakeWhatsAppClient`, configuracion
temporal y SQLite temporal. Cubren modo apagado, remitente permitido y remitente no
permitido; no acceden a APIs externas.
