# Verificacion de aclaracion conservadora del nombre completo

## Fecha y alcance

8 de octubre de 2026. Captura del nombre completo previa al motivo, aclaracion de
partes sospechosas sin recortarlas y uso del nombre aceptado en la notificacion al
doctor. Cambios locales y ejecucion en el mirror Raspberry Pi.

## Reproduccion y causa

La regresion inicial del servicio fallo con los dos textos reportados. El primer
`Asael Ponce jhbashkda` recibia `Gracias. Ahora, ¿cuál es el motivo de la consulta?`
y avanzaba al motivo sin aclarar el nombre. En esa secuencia, el segundo texto
`Asael Ponce junajusndqwd` se interpretaba como motivo y creaba una cita.
La ruta determinista actual no reprodujo el agradecimiento parcial `Gracias, Asael
Ponce`; respondia sin mostrar el nombre guardado. Por ello se verifica el dato
persistido y el campo `Nombre` del mensaje al doctor, ademas de la respuesta.

La causa comprobada fue la validacion local limitada a longitud y presencia de
letras, junto con el cambio prematuro de paso. Se reemplazo por un validador
conservador, un candidato pendiente y una respuesta de aceptacion con el nombre
completo realmente guardado.

## Pruebas automatizadas

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
Ran 295 tests in 8.820s
OK
```

`tests/test_patient_name_collection.py` agrega 13 pruebas del servicio:

- Los dos nombres reportados conservan todas sus partes y piden aclaracion.
- No se reemplaza el nombre previo, no se crea una cita ni se emiten eventos
  mientras se espera aclarar el nombre.
- Un nombre corregido conserva el horario de las 11:00 y se muestra completo.
- Un apellido inusual como `Chrząszcz` se acepta tras confirmacion explicita,
  incluso despues de reiniciar el servicio con un historial limitado a dos mensajes.
- Repetir el candidato no lo confirma automaticamente.
- Respuestas invalidas, vacias, de puntuacion o `Sí, 123` no lo aceptan ni sustituyen.
- Una negativa solicita el nombre completo corregido sin abandonar la reserva.
- Reintentos de nombres, aclaraciones y negativas no se convierten en motivos
  ni sustituyen el candidato mas reciente.
- Se conservan acentos, apostrofos, guiones, apellidos cortos y nombres en alfabetos
  no latinos, sin aplicarles reglas de vocales latinas.
- Una pausa conserva el candidato, retomar lo vuelve a citar y un `Sí` durante la
  pausa no lo acepta.

La nueva prueba integrada en `tests/test_main.py` recorre el webhook, persistencia,
calendario y entrega a un doctor falso: los dos nombres sospechosos no guardan un
nombre ni emiten notificaciones. Tras `Asael Ponce Silva` y `Revisión general` se
crea una sola cita en el horario original y se envia una sola notificacion con
`Nombre: Asael Ponce Silva`, sin los textos de prueba.

Las pruebas usan SQLite temporal y proveedores falsos; el flujo integrado verifica
el contenido enviado sin consumir APIs externas. `git diff --check` paso.

## Runtime y HTTP

Se inspeccionaron unidades systemd de sistema y usuario, procesos y puerto 8000.
No habia unidades coincidentes, backend escuchando ni proceso ngrok. Tras sincronizar
los cambios se inicio Uvicorn desde `/home/asaek/Downloads/chatbot_test_repo` con el
comando estandar y se comprobo su PID, directorio y propiedad del puerto. Se inicio
el tunel ngrok configurado y se verificaron los cuerpos esperados con `curl`:

```text
local  GET /                 -> 200, {"status":"ok"}
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, {"status":"ok"}
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
```

El token se leyo en memoria y se paso a `curl` por entrada estandar sin imprimirlo.
Los POST usaron eventos vacios, sin invocar al LLM ni enviar mensajes de WhatsApp.
