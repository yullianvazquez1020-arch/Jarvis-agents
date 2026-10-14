# Three.js r180 — copia local (sin CDN)

El panel del Mac no carga librerías de internet: el holograma de `/avatar/ironman` usa esta copia,
servida por `desktop/app.py` desde `127.0.0.1`. Así la vista funciona sin conexión y nada sale del equipo.

## Procedencia

| Archivo | Origen |
| --- | --- |
| `three.module.js` | `build/three.module.js` de three.js r180 |
| `three.core.js` | `build/three.core.js` de three.js r180 |
| `controls/OrbitControls.js` | `examples/jsm/controls/OrbitControls.js` de three.js r180 |
| `LICENSE` | licencia MIT de three.js |

Etiqueta upstream: `r180` (commit `0af9729d0c143a86a1d725d6e2c3ad83301f3f34`, repositorio `mrdoob/three.js`).
`three.core.js` declara `REVISION = '180'`.

## Único cambio sobre el original

`controls/OrbitControls.js` importaba el especificador desnudo `'three'`, que en el navegador
necesitaría un `<script type="importmap">` en línea. La política de contenido del panel
(`script-src 'self'`) no permite scripts en línea, así que esa línea quedó como ruta relativa:

```js
} from '../three.module.js';   // Jarvis: ruta local (sin importmap: la CSP no permite scripts en línea)
```

SHA256 del archivo original antes del cambio:
`b97879c748170baadeb3fb84cea1ffdf4674e283dc06042f34e2acb95a76042c`

Los demás archivos están tal cual vienen de upstream, sin minificar, para que se puedan auditar.
Las direcciones `https://` que aparecen dentro son enlaces de documentación en comentarios: el código
no descarga nada por su cuenta, y esta vista no carga texturas ni modelos externos.

## Cómo actualizar

1. Clonar la etiqueta nueva de `mrdoob/three.js` y copiar los mismos tres archivos.
2. Repetir el único cambio de `OrbitControls.js`.
3. Anotar aquí la etiqueta, el commit y el SHA256 original.
4. Actualizar `SHA256SUMS.txt` y volver a correr `scripts/check_avatar_ironman.cjs` y
   `tests/test_avatar_ironman.py`.

## Posproceso para la Torre de Aincrad (`/torre`, `torre-cine.js`)

Copiados de `three@0.180.0` (npm, `examples/jsm/`), sin minificar: `postprocessing/{EffectComposer,RenderPass,
ShaderPass,MaskPass,Pass,UnrealBloomPass,BokehPass,OutputPass}.js` y `shaders/{CopyShader,LuminosityHighPassShader,
BokehShader,OutputShader}.js`. Único cambio: `from 'three'` -> `from '../three.module.js'` (misma razón de CSP).
Se sirven solo con `JARVIS_AVATAR_IRONMAN=1`; si no, `/torre` usa la escena 2D.
