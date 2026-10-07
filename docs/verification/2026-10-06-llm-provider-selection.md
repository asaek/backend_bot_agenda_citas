# Verificacion de seleccion del proveedor LLM

## Resultado

`LLM_PROVIDER` selecciona Groq, OpenAI u OpenRouter y resuelve las credenciales,
el modelo y el endpoint del proveedor elegido. OpenAI usa Responses API con la
URL oficial `https://api.openai.com/v1` y `max_output_tokens`; Groq y OpenRouter
conservan Chat Completions y `max_tokens`.

Para alternar entre Groq y OpenAI sin editar otras variables, deben estar
configurados previamente `GROQ_API_KEY`, `GROQ_MODEL`, `OPENAI_API_KEY` y
`OPENAI_MODEL`; despues se cambia `LLM_PROVIDER` y se reinicia el backend.
Tambien se admite `LLM_API_KEY` y `LLM_MODEL` como valores del proveedor activo;
en ese modo se actualizan junto con `LLM_PROVIDER`.

## Verificacion

Las pruebas se ejecutaron en la Raspberry Pi con el transporte HTTP simulado:

- `python -m unittest discover -s tests -p test_llm_provider.py`: 26 pruebas OK.
- `python -m unittest discover -s tests`: 242 pruebas OK.
- `GET /`: `{"status":"ok"}`.
- `GET /webhook/whatsapp` con el token configurado: devolvio el challenge `12345`.
- `POST /webhook/whatsapp` con un evento vacio: `{"status":"ok"}`; no genero
  mensajes ni llamadas a proveedores externos.

No se hizo una llamada real a OpenAI. La prueba del adaptador verifica su request
y su respuesta simulada sin credenciales ni consumo de API.

## Compatibilidad del modelo configurado en runtime

La configuracion previa seleccionaba `openai` con `openai/gpt-oss-20b`, un nombre
usado por Groq. Se ajusto el modelo al ID oficial `gpt-oss-20b` y el adaptador
OpenAI ahora usa Responses API, el endpoint documentado para este modelo. La
suite verifica el request y el ciclo de tool calling con transporte simulado;
no se hizo una generacion real ni se consumio la API.
