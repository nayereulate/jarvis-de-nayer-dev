# Jarvis

Asistente personal para Windows que se maneja **con la voz, con las manos y desde el celular**.
El cerebro es [Claude Code](https://claude.com/claude-code). La voz, el oído, la visión de la webcam
y el control de la PC corren en tu propio equipo.

> Proyecto personal hecho por hobby. No está afiliado a Anthropic, Marvel ni Disney.

## Qué hace

**Con la voz:** dices «Hey Jarvis» y hablas. Puede:
- Abrir apps y webs, controlar la música y el volumen.
- Escribir por ti o hacer un dictado completo.
- Buscar en internet y responder preguntas sobre lo que hay en tu pantalla.
- Poner recordatorios y alarmas, y recordar cosas sobre ti.
- Ejecutar rutinas («modo trabajo»), darte el informe del día y grabar la pantalla.

Puedes interrumpirlo diciendo «Hey Jarvis» mientras habla.

**Con las manos (modo holograma):** tu cámara queda de fondo y, con las manos, puedes:
- Mover el cursor y hacer clic, doble clic y clic derecho.
- Mover, estirar, acoplar, maximizar y minimizar ventanas.
- Hacer scroll, cambiar de ventana o de pestaña, e ir atrás y adelante.
- Subir el volumen girando la mano.
- Dibujar en el aire y girar una esfera holográfica en 3D.

**Presencia:** al sentarte, te reconoce por tu cara y te saluda con el informe del día. Si te vas, bloquea la PC. En modo guardia, también la bloquea si se sienta alguien que no conoce.

**En el escritorio:**
- Un orbe flotante que muestra si Jarvis escucha, piensa o habla.
- Una animación de arranque.
- Subtítulos grandes, útiles para grabar videos.

**Desde el celular (app web instalable):**
- Chatear y hablarle.
- Ver la pantalla de la PC en vivo y tocar para hacer clic.
- Pasar archivos entre el celular y la PC.
- Recibir notificaciones de recordatorios.

## Seguridad
- **Claude solo propone acciones; las ejecuta Jarvis.** Apagar, reiniciar o eliminar archivos siempre requiere que pulses **Aprobar**. Todo lo que hace queda en `data/audit.log`.
- **Acceso con token.** La página y la API piden un token que se crea en `data/token.txt`. El servidor solo escucha en tu propia PC (`127.0.0.1`). Para el celular se usa [Tailscale](https://tailscale.com), que crea una red privada entre tus dispositivos.
- **Visión aislada.** Las capturas de pantalla y las búsquedas web se analizan en un Claude aparte, sin acceso a tus archivos.
- **Tus datos se quedan en tu PC.** Tus caras, recuerdos y recordatorios se guardan en `data/`, que no se sube al repositorio.

## Requisitos
- Windows 10 u 11 y [Python 3.13](https://www.python.org/downloads/).
- **Claude Code con una suscripción de Claude** (Pro o superior), con la sesión iniciada: ejecuta `claude` una vez.
- Micrófono y webcam. Probado con una Logitech C920.
- Opcionales:
  - Tarjeta NVIDIA: transcribe tu voz mucho más rápido.
  - [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (`winget install Gyan.FFmpeg`): para grabar la pantalla.
  - Tailscale: para usar Jarvis desde el celular.

## Instalación
1. Descarga el proyecto, por ejemplo con `git clone`.
2. Doble clic en **`instalar.bat`**. Crea el entorno, instala todo (unos 4 GB) y descarga la voz.
3. Doble clic en **`iniciar.bat`**. Se abre la página de Jarvis en `http://127.0.0.1:8765`.
4. Pega el token de `data\token.txt` cuando la página te lo pida.

Para que arranque solo con Windows: doble clic en `arranque-con-windows.bat` (y `arranque-con-windows.bat quitar` para deshacerlo).

### En el celular
1. Instala Tailscale en la PC y en el celular, con la misma cuenta.
2. En la PC, ejecuta `tailscale serve --bg --https=443 http://127.0.0.1:8765`.
3. Ejecuta `.venv\Scripts\python crear_qr_celular.py` y escanea el QR que crea en `data\conectar-celular.png`.
4. En el navegador del celular, elige «Agregar a pantalla de inicio».

## Primeros pasos
| Di… | Y Jarvis… |
|---|---|
| «Hey Jarvis, aprende mi cara, me llamo Ana» | Te reconoce y te saluda por tu nombre |
| «Hey Jarvis, activa el modo holograma» | Te pone de fondo y te da control con las manos |
| «Hey Jarvis, muestra la esfera» / «modo dibujo» | Muestra la esfera holográfica o activa el dibujo en el aire |
| «Hey Jarvis, ¿qué hay en mi pantalla?» | Mira tu pantalla y te la explica |
| «Hey Jarvis, busca las noticias de hoy» | Busca en internet |
| «Hey Jarvis, recuérdame en 20 minutos sacar la comida» | Te avisa por voz y en el celular |
| «Hey Jarvis, empieza a grabar» / «deja de grabar» | Graba en `Videos\Jarvis` |
| «Hey Jarvis, activa los subtítulos» | Muestra lo que se dice en grande, ideal para videos |
| «Hey Jarvis, modo dictado» … «fin del dictado» | Escribe todo lo que digas |

## Gestos (modo holograma)
| Gesto | Acción |
|---|---|
| Mover la mano | Mover el cursor |
| Pellizco pulgar-índice rápido | Clic (dos seguidos: doble clic) |
| Pellizco pulgar-medio | Clic derecho |
| Pellizcar y mantener sobre una ventana | Moverla; si la sueltas en un borde, se acopla |
| Ventana agarrada + pellizco con la otra mano | Estirarla o encogerla |
| Dos dedos (índice y medio) arriba o abajo | Scroll tipo joystick |
| Dos dedos, barrido de lado | Atrás o adelante |
| Tres dedos, barrido de lado | Cambiar de pestaña |
| Mano abierta, barrido de lado | Cambiar de ventana (Alt+Tab) |
| Puño 0,6 s | Minimizar la ventana |
| Puño corto y abrir la palma | Maximizar o restaurar; fuera de las ventanas, devuelve la última minimizada |
| Dos palmas abiertas 1 s | Minimizar todo o devolverlo |
| 🤙 Pulgar y meñique, girar la mano | Perilla de volumen |
| Modo dibujo: pellizcar y mover / puño | Dibujar trazos de luz / borrar |
| Modo esfera: pellizcar y arrastrar / dos manos | Girar la esfera / agrandarla |

## Configuración opcional (variables de entorno)
| Variable | Para qué |
|---|---|
| `JARVIS_CAMERA` | Elegir la webcam por nombre |
| `JARVIS_MIC` | Elegir el micrófono por nombre |
| `JARVIS_REC_MIC` | Elegir el micrófono que se usa al grabar |
| `JARVIS_CITY` | Ciudad del clima del informe |
| `JARVIS_WHISPER` | Modelo de reconocimiento de voz: `small`, `medium`, `large-v3-turbo` |
| `JARVIS_AWAY_MINUTES` | Minutos sin verte antes de bloquear la PC (por defecto 3) |
| `JARVIS_PRESENCE=0`, `JARVIS_GUARD=0`, `JARVIS_ORB=0`, `JARVIS_WAKE=0` | Apagar la presencia, el modo guardia, el orbe o el «Hey Jarvis» |

## Cómo está hecho
- **Servidor:** Python, FastAPI. **Cerebro:** Claude Code en modo `-p`, con salida JSON estructurada.
- **Oído:** openWakeWord («Hey Jarvis») y faster-whisper. **Voz:** Piper.
- **Visión:**
  - MediaPipe: manos.
  - OpenCV YuNet y SFace: caras.
  - PySide6: ventanas del holograma y del orbe.
- **Celular:** página web instalable (PWA) con notificaciones Web Push.

Para correr las pruebas: `set JARVIS_WAKE=0 && .venv\Scripts\python -m pytest`

## Licencia
[MIT](LICENSE) © 2026 Nayer Dev. Puedes usarlo, modificarlo y compartirlo, manteniendo el aviso de copyright.
