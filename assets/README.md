# Audio de laboratorio

`lab-greeting.wav` es un recurso fijo de prueba, PCM mono de 16 bits a 16 kHz.
Dice: «Hola, soy el asistente virtual del consultorio. Esta es una prueba de audio.»

Fue preparado localmente con la voz sintetica Paulina (`es_MX`) de macOS:

```sh
say -v Paulina --file-format=WAVE --data-format=LEI16@16000 \
  -o assets/lab-greeting.wav \
  'Hola, soy el asistente virtual del consultorio. Esta es una prueba de audio.'
```

El laboratorio lee ese archivo; no utiliza un proveedor TTS durante las sesiones.

`voice-user-sample.wav` es una entrada conocida para probar el modelo Realtime:
«Hola, ¿puedes decirme en qué me puedes ayudar con mis citas?» Se genero localmente
con Paulina, PCM16 mono a 16 kHz. El probe envia esta muestra al modelo como audio;
la respuesta del modelo se genera en directo. Ninguno de estos WAV contiene
audio capturado de una persona.

`voice-availability-sample.wav` pregunta «Hola, ¿que horarios disponibles tienes
para mañana?» con el mismo formato/voz sintetica. Se usa para verificar audio
nativo y una consulta real del modelo a las herramientas de agenda falsa.
No contiene voz de pacientes. Las muestras recibidas se descartan en memoria.
