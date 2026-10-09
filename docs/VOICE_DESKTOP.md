# Jarvis por voz y en tus monitores: primera entrega (4.0.4)

> **Actualización 4.0.5.** Novedades del escritorio, con el detalle en `CAMBIOS_4_0_5.md`:
> - **Pantalla 1:** barra de estado con punto cian, ámbar o rojo, y modo discreto con «Mostrar».
> - **Pantalla 2:** HUD de solo lectura en `http://127.0.0.1:8765/hud`.
> - **Alertas:** franja lateral; cada aviso sale una sola vez.
> - **Órdenes nuevas:** «enciende el micrófono» y «modo discreto».
> - **«¿Cómo estás?»:** ahora responde en local, sin saldos.
> - **Emparejamiento:** vence a los 90 días; se renueva con `/emparejar`.
> - **Auditoría:** los accesos se ven en `/dispositivos`.
> - **Más frases que no salen de la Mac:** anotar, enviar, borrar, restaurar y otras.
> - **`--check`:** ahora informa también micrófono y monitores.


Base: 4.0.3 desplegado, commit `3fc1e61`. Rama: `feature/voice-desktop`.
**No se publicó, no se integró en `main`, no se desplegó y no se activó trading real.**

Esta entrega cubre las fases 1 a 3 del plan, para **consultas de solo lectura**:

- un panel local;
- voz por turnos en la Mac;
- un acceso autenticado a Jarvis.

Los borradores por voz (fase 4), la conversación con interrupción por voz y la palabra «Jarvis» (fase 5) no están incluidos.

---

## Pantallas con diseño de centro de operaciones

El escritorio incluye tres vistas del mismo acompañante local:

| Monitor | Ruta local | Funciones |
|---|---|---|
| Conversación | `/` | Texto, voz local si está configurada, agenda y consultas de lectura |
| Operaciones | `/hud` | Núcleo azul/dorado, módulos del panel, estado de conexión, montos ocultos por defecto, actualizar y pantalla completa |
| Presencia | `/avatar` | Silueta de partículas o rostro, frase de prueba visual y pausa |

Abre primero el enlace de un solo uso que imprime `python3 desktop/app.py`.
Desde la sesión abierta, entra en `/hud` y usa los enlaces Conversación y Avatar.
Mueve cada ventana al monitor que corresponda y activa pantalla completa desde el navegador.
Los tres monitores comparten la sesión local; los detalles se abren en la ventana principal.
Los módulos disponibles proceden de `/api/hud`: el diseño no inventa agentes conectados.

Para probar el diseño sin conectar cuentas:

```bash
VOICE_DEMO=true python3 desktop/app.py
```

La demostración identifica sus datos como ejemplos. Para consultar los datos reales,
usa el emparejamiento descrito abajo y desactiva `VOICE_DEMO`.
La silueta y las partículas son animación visual, no una red neuronal nueva ni un indicador
real de actividad de la IA. «Animar frase» no genera audio ni se sincroniza con el altavoz.
La voz permanece en la ventana Conversación, con los motores que tengas configurados.
Las animaciones usan Canvas 2D sin bibliotecas ni recursos externos. La calidad
**Automática** empieza en Ligero, mide el coste de dibujar y el intervalo entre cuadros,
y pasa a Detalle cuando hay margen; si el dibujo se vuelve lento baja a Ligero o Ahorro.
La etiqueta AUTO muestra el nivel realmente elegido. También puedes fijar Ligero o Detalle.
Los objetivos máximos son unos 30 cuadros/segundo en Detalle, 24 en Ligero y 18 en Ahorro;
la frecuencia efectiva depende del equipo y del navegador. El lienzo nunca supera
1920 × 1080 píxeles internos, incluso en pantallas Retina o televisores grandes.

La geometría se reutiliza entre cuadros. La animación cancela su ciclo en pestañas ocultas
y al pausar; no mantiene un bucle de dibujo vacío. Se aplica la preferencia de reducir
movimiento, incluso si cambia mientras la ventana está abierta.

El HUD permite alternar Órbita y Mapa: los grupos multicolor corresponden a las tarjetas
que devuelve Jarvis. No son neuronas ni conexiones de agentes medidas. El avatar utiliza
contornos con volumen y conserva la prueba de frase sin audio. El estilo de Conversación
se actualiza para coincidir con los otros monitores.

Las [vistas del motor visual](previews/README.md) muestran fotogramas generados por el
mismo código Canvas. No son capturas completas del navegador ni mediciones de tu Mac.

Actualizar Render no instala estas pantallas en tu Mac: debes actualizar allí la carpeta
`desktop/` del repositorio y volver a ejecutar el acompañante.

---

## 1. Qué hay y dónde corre

```
Mac (Safari)  ──>  acompañante local  ──HTTPS + token del equipo──>  Jarvis en Render
  panel, micrófono    desktop/app.py                                   /desktop/v1 (solo lectura)
  y altavoz           127.0.0.1:8765                                   Telegram sigue igual
                      voz local (opcional)
```

| Lugar | Qué hace | Archivos |
|---|---|---|
| **Render** | Recibe consultas del equipo emparejado, solo lectura. **Apagado por defecto.** | `jarvis_desktop_api.py` y cambios mínimos en `main.py` |
| **Mac** | Panel, micrófono, voz local, órdenes de interfaz y ventanas | `desktop/` (solo Python estándar, sin `pip install`) |
| **Telegram** | Lo de siempre, más `/emparejar` y `/dispositivos`. Las aprobaciones de dinero y los envíos siguen solo aquí. | sin cambios en su comportamiento |

Render **no** importa nada de `desktop/`. Si el acompañante no existe o falla, Jarvis y Telegram funcionan igual.

---

## 2. Qué puedes decirle

Las órdenes de interfaz se resuelven en la Mac, sin internet y sin tokens.

| Frase | Qué pasa | ¿Gasta tokens? |
|---|---|---|
| «Jarvis, ¿cómo estás?» | Abre el panel Estado con la versión real del servidor y el modo cripto | No |
| «Léeme la agenda» | Abre la agenda (hoy y los próximos 7 días) y te la resume en voz | No |
| «Muéstrame los cobros» | Abre el panel de cobros con tus datos reales | No |
| «Abre práctica» | Muestra el simulador y tu cuenta de práctica. **No cambia el modo.** | No |
| «Repite» | Vuelve a reproducir la última respuesta | No |
| «Habla más despacio» / «más rápido» | Ajusta la velocidad entre 0.7 y 1.4 (queda guardada) | No |
| «Silencio» | Detiene el audio; el micrófono sigue disponible | No |
| «Apaga el micrófono» | Cierra la captura al instante | No |
| «Confirma 123456», «aprueba la orden 3», «activa modo real», «/confirmar…» | Se rechaza **en la Mac**, sin enviarse a Jarvis. Una transcripción no te identifica ni aprueba nada. | No |
| «Compra 100 dólares de bitcoin», «anota un gasto de 25» | Jarvis responde que por esta vía solo consulta y que eso va por Telegram | Sí, si pasa por la IA |
| Cualquier otra pregunta («¿cómo viene mi semana?») | La IA responde usando **solo herramientas de lectura** | **Sí** |

Debajo de cada respuesta, el panel indica si fue local (sin tokens) o si consultó a la IA.

---

## 3. Seguridad (lo que se comprobó en pruebas)

**En Render (`/desktop/v1`)**

- **Apagado por defecto.** Con `DESKTOP_API_ENABLED=false`, todo devuelve 404 y `/emparejar` no aprueba nada.
- **Emparejamiento.**
  - La Mac pide un código de 6 dígitos, que vence en 10 minutos.
  - Tú lo apruebas con `/emparejar CÓDIGO`, solo desde tu usuario en tu chat privado. Un usuario extraño se ignora y desde un grupo se rechaza.
  - Con 5 códigos incorrectos se cancela todo. Solo puede haber 3 solicitudes pendientes a la vez.
  - El token del equipo se entrega **una sola vez** y en Upstash solo queda su hash.
- **Revocar.** `/dispositivos revocar N` corta el acceso al instante.
- **Permisos por capacidad.** Solo existen `read` y `converse`. No hay capacidad para aprobar dinero, activar el modo real, enviar mensajes ni ejecutar comandos.
- **Solo lectura, impuesto en el servidor y no en el texto de instrucciones:**
  1. La IA solo **ve** 27 herramientas de lectura.
  2. Si pide otra herramienta, `run()` la rechaza **antes** de ejecutarla. Lo probé pidiendo `add_income` y `coinbase_prepare_order`.
  3. Todo lo que corre en este canal pasa por un **bloqueo de escritura** en el almacenamiento. Incluso si una herramienta "de lectura" intentara guardar algo, falla. Lo probé con una herramienta trampa.
- **Tu identidad y tu sesión las decide el servidor.**
  - El equipo no envía nombres ni identidades.
  - Cada equipo tiene su propio historial (`desk:<id>`), separado del de Telegram.
- **Idempotencia.**
  - Cada `request_id` se guarda **antes** de trabajar.
  - Un reintento devuelve la misma respuesta.
  - El mismo ID con otro texto se rechaza (409).
  - Un turno interrumpido por un reinicio se reporta como «incierto» y no se repite.
- **Límites.** Una consulta a la vez por equipo, 30 cada 10 minutos, 1,000 caracteres por texto y 16 KB por solicitud.
- **Secretos.** Se ocultan antes de llegar a la IA, al historial, al registro de turnos y a la voz.

**En la Mac (`desktop/app.py`)**

- **Dirección.** Solo escucha en `127.0.0.1`. `0.0.0.0` se rechaza siempre; otra dirección solo con `VOICE_ALLOW_LAN=true`.
- **Entrada al panel.** Se abre con un **enlace de un solo uso** (2 minutos) que crea una cookie `HttpOnly` y `SameSite=Strict`.
- **Protección contra otras páginas.** Se valida `Host` contra el truco de *DNS rebinding*, y `Origin` más la cabecera `X-Jarvis-UI` en cada POST. Otras páginas web no pueden manejar el panel.
- **Lo que nunca ve el navegador.** El token del equipo, `AGENT_API_KEY` y cualquier otra clave.
  - El token vive en `~/.jarvis-desktop/device.json` con permisos `0600`.
  - Viaja solo en la cabecera `Authorization` hacia Render, con TLS verificado, y nunca en una URL ni en los logs.
- **Lo que llega del servidor.** Se filtra: solo pasan tipos de evento conocidos y paneles de una lista fija. Todo se pinta como texto (`textContent`), nunca como HTML.
- **Ventanas.**
  - Una sola ventana usa el micrófono y el altavoz; las demás solo muestran paneles.
  - Recargar una ventana con el mismo `request_id` no repite la consulta.
- **Cancelar.** Detiene el audio, y la respuesta que llegue tarde no se muestra ni se lee. Esta vía es de solo consulta, así que no hay acciones que deshacer.
- **Audio.**
  - No se guarda (`VOICE_RETAIN_AUDIO=false`): cada archivo temporal se borra al terminar.
  - El micrófono no escucha mientras Jarvis habla.
  - El **modo discreto** no lee montos en voz alta: dice «Te lo dejé en pantalla».
- **Modo DEMO.** Muestra datos de ejemplo rotulados «DEMO» y nunca contacta a Jarvis.

---

## 4. Instalación en tu Mac (Intel 2015)

> **Compatibilidad:** **no** se probó en tu Mac. Todo lo de abajo se probó en Linux con Python 3.11 a 3.13, y la sintaxis se validó contra Python 3.8. Lo primero es medir tu equipo (paso 2).

1. **Copia la carpeta** `desktop/` del ZIP a tu Mac, por ejemplo a `~/jarvis-desktop`.
2. **Mide el equipo.** No instala nada:
   ```
   cd ~/jarvis-desktop
   python3 app.py --check
   ```
   Muestra la versión de macOS, el CPU, la memoria, Python, las **voces en español** instaladas y el estado de los motores de voz. Si `python3` no existe, macOS ofrece instalar las *Command Line Tools*: acéptalo.
3. **Prueba el panel en modo DEMO**, sin tocar Render:
   ```
   mkdir -p ~/.jarvis-desktop
   cp config.example ~/.jarvis-desktop/config.env
   # edita: VOICE_DEMO=true
   python3 app.py
   ```
   Se abre Safari con el enlace de un solo uso. Revisa el tamaño del texto y la distribución, y prueba escribiendo «abre la agenda».
4. **Voz de respuesta, la opción más sencilla.**
   - Mira las voces en español con `say -v '?' | grep es_`.
   - Pon `VOICE_TTS_BACKEND=macos_say` y `VOICE_TTS_VOICE=<la que te guste>`.
   - Funciona sin internet. Piper queda como alternativa: el adaptador existe, pero no se probó con el programa real.
5. **Reconocimiento de voz.** Es opcional; sin él escribes las consultas.
   - Según la documentación de whisper.cpp, en una Mac Intel hacen falta `xcode-select --install` y **CMake**. Luego:
     ```
     git clone https://github.com/ggml-org/whisper.cpp.git
     cd whisper.cpp
     sh ./models/download-ggml-model.sh base      # multilingüe; NUNCA base.en para español
     cmake -B build
     cmake --build build -j --config Release
     ```
   - En `config.env`:
     ```
     VOICE_STT_BACKEND=whisper_cpp
     VOICE_WHISPER_BIN=/Users/TU_USUARIO/whisper.cpp/build/bin/whisper-cli
     VOICE_STT_MODEL_PATH=/Users/TU_USUARIO/whisper.cpp/models/ggml-base.bin
     ```
   - `python3 app.py --check` confirma que tu `whisper-cli` tiene las opciones que usa el panel.
   - **Mide antes de decidir** con `python3 app.py --bench grabacion.wav` (WAV de 16 kHz, mono). Te da el RTF: menos de 1 significa más rápido que en tiempo real.
   - Prueba también `tiny` si `base` va lento.
   - Prueba voces de Puerto Rico, nombres de clientes, «quince» frente a «cincuenta» y decimales. Para lo dudoso, activa **«Revisar antes de enviar»**.
6. **Conectar con tu Jarvis.** Hazlo solo cuando decidas desplegar la 4.0.4:
   1. En Render pon `DESKTOP_API_ENABLED=true` y despliega.
   2. En `config.env` pon `VOICE_DEMO=false` y `JARVIS_SERVER_URL=https://jarvis-agents.onrender.com`.
   3. En el panel pulsa **Emparejar**. Aparece un código: escribe en Telegram `/emparejar CÓDIGO`. El panel se conecta solo.
   4. `/dispositivos` muestra el equipo y `/dispositivos revocar N` lo desconecta.

**Dos monitores:** con el panel abierto, abre la misma dirección (`http://127.0.0.1:8765/`) en otra ventana de Safari y muévela al segundo monitor. La primera ventana tiene la voz; la otra muestra paneles. Si quieres cambiarlas, pulsa «Usar esta ventana para voz». Cada ventana recuerda su panel.

**Teclado:** `Espacio` habla o detiene, `Esc` corta el audio y `Enter` envía lo escrito.

---

## 5. Variables

| Dónde | Variable | Valor inicial | Nota |
|---|---|---|---|
| **Render** | `DESKTOP_API_ENABLED` | `false` | `true` solo cuando vayas a emparejar |
| Render | `CRYPTO_PRACTICE_ONLY`, `COINBASE_TRADING_ENABLED`, límites $100/$300 | sin cambios | esta entrega no los toca |
| **Mac** | `JARVIS_SERVER_URL` | `https://jarvis-agents.onrender.com` | solo `https://` |
| Mac | `JARVIS_DEVICE_TOKEN` | vacío | normalmente lo guarda el emparejamiento en `device.json`; **no** es la clave maestra |
| Mac | `VOICE_BIND_HOST` / `VOICE_PORT` | `127.0.0.1` / `8765` | |
| Mac | `VOICE_STT_BACKEND` | `none` | `whisper_cpp` después de medir |
| Mac | `VOICE_WHISPER_BIN`, `VOICE_STT_MODEL_PATH`, `VOICE_STT_THREADS` | — | rutas de whisper.cpp |
| Mac | `VOICE_TTS_BACKEND` | `none` | `macos_say` o `piper` |
| Mac | `VOICE_TTS_VOICE` | — | nombre de voz de macOS, o ruta `.onnx` de Piper |
| Mac | `VOICE_PIPER_BIN` | `piper` | |
| Mac | `VOICE_WAKE_WORD_ENABLED` | `false` | no implementado (fase 2); se ignora |
| Mac | `VOICE_RETAIN_AUDIO` | `false` | `true` guarda las grabaciones en `~/.jarvis-desktop/audio` |
| Mac | `VOICE_DEMO` | `false` | `true` usa datos de ejemplo y no contacta a Jarvis |

---

## 6. Desactivar sin afectar Telegram

- **En Render:** `DESKTOP_API_ENABLED=false` y despliega. Todo `/desktop/v1` responde 404; Telegram, `/chat`, el dinero y los avisos siguen igual.
- **Un equipo:** `/dispositivos revocar N`.
- **En la Mac:** `Ctrl+C` en la terminal. Para olvidar el emparejamiento, borra `~/.jarvis-desktop/device.json`.
- **Volver a 4.0.3:** en Render, haz *Rollback* al deploy de `3fc1e61`. Las claves nuevas (`jarvis:desktop` y `jarvis:desktop:turns`) las ignora 4.0.3.

---

## 7. Pruebas y qué se simuló

**Resultado: 317 pruebas, 317 OK, 0 omitidas.**

| Grupo | Pruebas | Qué cubre |
|---|---|---|
| Suite anterior (4.0.3) | 263 | todas siguen pasando |
| `test_desktop_auth.py` | 10 | apagado por defecto, emparejamiento, Telegram privado, tokens, revocación, capacidades |
| `test_voice_turns.py` | 11 | dinero y comandos nunca por voz, herramienta no permitida, bloqueo de escritura, paneles, sesiones separadas, secretos, sin clave de IA |
| `test_voice_idempotency.py` | 6 | reintentos, conflicto de ID, turno interrumpido, una consulta a la vez, límite por minuto, aislamiento entre equipos |
| `test_desktop_companion.py` | 27 | cookie y enlace de un uso, Host/Origin, bind, token fuera del navegador y de los logs, ventanas, órdenes locales, reenvío con el mismo ID, eventos filtrados, cancelar, sin conexión, modo discreto, DEMO, WAV, whisper.cpp y `say` simulados, JavaScript |

**Prueba de punta a punta** (fuera de la suite): el acompañante real habló por HTTP con el `main.py` real más el adaptador, con la IA simulada. Se comprobaron:

- emparejar y aprobar con `/emparejar`;
- el token guardado solo como hash;
- la versión auténtica del servidor;
- el panel de cobros con datos reales;
- una pregunta a la IA con herramientas de solo lectura;
- un código rechazado en la Mac;
- que un equipo revocado ya no recibe datos.

**Simulado en todas las pruebas:**

- la IA de Anthropic;
- Telegram;
- Upstash (se usaron archivos locales);
- whisper.cpp y `say` (programas falsos);
- el micrófono;
- Safari.

En este entorno no hay acceso a PyPI. Para correr las pruebas de Render se usaron imitaciones mínimas de FastAPI, del SDK de Anthropic, de python-dotenv y de imageio-ffmpeg; no están en el ZIP. Fueron reales: Starlette, Pydantic, httpx 0.28.1, Redis 7 local y Node 22. **Repite la suite con `pip install -r requirements.txt`.**

---

## 8. No verificado (no lo presento como funcionando)

- **Tu Mac:** la versión de macOS, Python, las voces en español disponibles y el rendimiento. Corre `--check` y `--bench`.
- **Safari real:** que trate `127.0.0.1` como contexto seguro para el micrófono (el panel avisa si no), los permisos, la captura con Web Audio, la reproducción y las dos ventanas.
- **whisper.cpp real:** que compile en tu macOS, las opciones de tu versión (`--check` las revisa) y la precisión en español de Puerto Rico.
- **`say` y Piper reales:** la calidad de la voz y que Piper acepte las opciones clásicas (`--model`, `--output_file`, `--length_scale`).
- **Render y Upstash con la 4.0.4:** el despliegue, el emparejamiento y las consultas de punta a punta.
- **El ruido real, el eco y la latencia (p50/p95).** La detección de fin de frase es por energía, con 1.2 s de silencio; ajústala tras probar.

## 9. Riesgos que quedan

- Las preguntas que pasan por la IA **gastan tokens** de tu cuenta de Anthropic. Las órdenes locales y los paneles no.
- Si alguien en la habitación oye las respuestas, puede escuchar saldos. Usa el **modo discreto**.
- Con la tapa cerrada o la Mac apagada no hay voz ni panel. Render sigue funcionando por su cuenta.
- La lista de herramientas de lectura (27) se revisó una por una. El bloqueo de escritura cubre un error en esa revisión; aun así, revisa la lista si agregas herramientas nuevas.

## 10. Siguientes fases (no incluidas)

- **Fase 4:** borradores por voz («anota un gasto de 25»), con lectura del monto y confirmación específica, sin dinero.
- **Fase 5:** conversación continua con interrupción por voz y palabra «Jarvis», después de probar eco y ruido.
- **Fase 6:** iPhone y Quest con HTTPS, PC nuevo, IA local y enrutador entre modelos.
