# SimpleMusicStation
Easy-to-use music software.

## Ejecutar

Requiere Python 3.10 o superior:

```bash
python app.py
```

La aplicación crea automáticamente la carpeta `projects/`. Cada proyecto
contiene su `project.json` y una carpeta `assets/` para sus archivos de audio.

Para habilitar reproducción WAV/MP3 y grabación desde el micrófono:

```bash
pip install -r requirements.txt
```

* Multiple audio track recording
* Audio import
* MIDI tracks / MIDI controller support / Virtual Instruments (SF2)
* Rhythm loop track
* Export to different audio formats
