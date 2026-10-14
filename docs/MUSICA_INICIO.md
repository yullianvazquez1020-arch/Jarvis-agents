# Música de inicio de Jarvis

La música de inicio está **encendida por defecto** al abrir el display (el botón del pie la silencia y
la preferencia se guarda).

- **Tu tema de Iron Man:** pon tu archivo comprado en `~/.jarvis-desktop/musica/inicio.mp3`
  (también vale `inicio.m4a`, `inicio.ogg` o `inicio.wav`; máx. 40 MB). Se sirve solo localmente en
  `/api/startup-music`. Este archivo **nunca** va al repositorio ni se descarga de internet.
- **Sin archivo:** suena el acorde ambiental original sintetizado en el navegador.
- **Autoplay sin clic:** Chrome bloquea el audio hasta el primer clic/tecla. Para que suene sola,
  abre Chrome con `--autoplay-policy=no-user-gesture-required`.
- Mientras Jarvis habla, la música baja de volumen automáticamente.
