/* Núcleo JARVIS en WebGL (three.js local, sin CDN). Código y diseño originales, inspirados en el estilo de HUD
   holográfico del laboratorio Stark: anillos concéntricos cian/blanco-azul con acentos ámbar, marcas finas
   densas, arcos de datos que giran, lecturas numéricas, capas con profundidad y paralaje, reactor central con
   brillo volumétrico, triángulos, rayos como tubos luminosos, bloom HDR a media resolución, aberración
   cromática, grano, líneas de barrido y rejilla hexagonal. No usa fotogramas ni recursos de las películas.
   Un solo bucle: nucleo.js llama a JarvisNucleo.paso() en su requestAnimationFrame. Sin WebGL queda el 2D. */
import * as THREE from "./vendor/three/three.module.js";
import { EffectComposer } from "./vendor/three/postprocessing/EffectComposer.js";
import { RenderPass } from "./vendor/three/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "./vendor/three/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "./vendor/three/postprocessing/ShaderPass.js";
import { OutputPass } from "./vendor/three/postprocessing/OutputPass.js";

const N = window.JarvisNucleo, old = document.getElementById("nucleo");
function webglOk() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; }
}
if (N && old && webglOk() && !/[?&]gl=0\b/.test(location.search)) {
  try { arrancar(); } catch (e) { N.gl = false; old.style.display = ""; const failed = document.getElementById("nucleo-gl"); if (failed) failed.remove(); console.warn("núcleo WebGL no disponible, uso 2D", e); }
}

function arrancar() {
  const DPR_MAX = 2;   // resolución nativa (3840×1080 a DPR 1, Retina hasta 2); solo baja si el frame > 18 ms
  const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance", alpha: false });
  renderer.setClearColor(0x010509, 1);
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.95;
  const cv = renderer.domElement; cv.id = "nucleo-gl"; cv.className = old.className;
  cv.setAttribute("aria-label", old.getAttribute("aria-label") || "Núcleo de JARVIS");
  cv.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;display:block;z-index:0";
  old.parentNode.insertBefore(cv, old); old.style.display = "none";
  cv.addEventListener("webglcontextlost", function (e) { e.preventDefault(); N.gl = false; cv.style.display = "none"; old.style.display = ""; });
  cv.addEventListener("webglcontextrestored", function () { old.style.display = "none"; cv.style.display = "block"; N.gl = true; });

  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(38, 1, 0.1, 100); cam.position.set(0, 0, 9.5);
  const rig = new THREE.Group(); scene.add(rig);               // inclinación 3D sutil + paralaje
  const CYAN = new THREE.Color(0.02, 0.75, 1.6), ICE = new THREE.Color(0.75, 1.15, 1.5), AMBER = new THREE.Color(1.5, 0.65, 0.12);
  const add = (m) => new THREE.MeshBasicMaterial({ color: m.c, transparent: true, opacity: m.o, blending: THREE.AdditiveBlending,
    depthWrite: false, side: THREE.DoubleSide, toneMapped: false });

  // --- geometría reutilizable ---
  function band(r0, r1, segs, gap, sub) {          // anillo segmentado en UNA geometría
    const pos = [], step = Math.PI * 2 / segs;
    for (let i = 0; i < segs; i++) {
      const a0 = i * step, a1 = (i + 1 - gap) * step, k = sub || 6;
      for (let j = 0; j < k; j++) {
        const u0 = a0 + (a1 - a0) * j / k, u1 = a0 + (a1 - a0) * (j + 1) / k;
        const p = (r, a) => [Math.cos(a) * r, Math.sin(a) * r, 0];
        pos.push(...p(r0, u0), ...p(r1, u0), ...p(r1, u1), ...p(r0, u0), ...p(r1, u1), ...p(r0, u1));
      }
    }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); return g;
  }
  function ticks(r, n, lMinor, lMajor, every) {
    const pos = [];
    for (let i = 0; i < n; i++) { const a = i * Math.PI * 2 / n, l = i % every ? lMinor : lMajor;
      pos.push(Math.cos(a) * r, Math.sin(a) * r, 0, Math.cos(a) * (r + l), Math.sin(a) * (r + l), 0); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); return g;
  }
  const layers = [];
  function layer(z, speed, obj) { obj.position.z = z; obj.userData.speed = speed; rig.add(obj); layers.push(obj); return obj; }

  // carcasa metálica real (iluminada por el núcleo): da volumen y profundidad
  // entorno para reflejos reales: mini "laboratorio" con paneles de luz, horneado UNA vez a PMREM (sin coste por frame)
  const pmrem = new THREE.PMREMGenerator(renderer), envScene = new THREE.Scene();
  envScene.add(new THREE.Mesh(new THREE.SphereGeometry(20, 32, 16), new THREE.MeshBasicMaterial({ color: 0x020812, side: THREE.BackSide })));
  [[0, 9, 0, 14, 2, 0x9fdcff, 3], [-9, 2, 4, 2, 8, 0x3aa8ff, 2.2], [9, -1, 3, 2, 10, 0xffb070, 1.1], [0, -8, 6, 16, 1.2, 0x2a8cff, 1.4], [3, 3, 12, 6, 3, 0xffffff, 1.6]]
    .forEach((q) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(q[3], q[4]), new THREE.MeshBasicMaterial({ color: new THREE.Color(q[5]).multiplyScalar(q[6]), side: THREE.DoubleSide }));
      m.position.set(q[0], q[1], q[2]); m.lookAt(0, 0, 0); envScene.add(m); });
  scene.environment = pmrem.fromScene(envScene, 0.03).texture; scene.environmentIntensity = 0.9;
  // textura de metal cepillado circular (radial) generada en canvas: rugosidad + relieve finos
  const brushC = document.createElement("canvas"); brushC.width = brushC.height = 512;
  { const g = brushC.getContext("2d"); g.fillStyle = "#808080"; g.fillRect(0, 0, 512, 512);
    for (let i = 0; i < 2600; i++) { const r = Math.random() * 256, a0 = Math.random() * 6.283, v = 90 + Math.random() * 90;
      g.strokeStyle = "rgba(" + v + "," + v + "," + v + ",0.35)"; g.lineWidth = 0.6 + Math.random();
      g.beginPath(); g.arc(256, 256, r, a0, a0 + 0.3 + Math.random() * 1.6); g.stroke(); } }
  const brushT = new THREE.CanvasTexture(brushC); brushT.anisotropy = renderer.capabilities.getMaxAnisotropy();
  // MeshPhysicalMaterial (extiende MeshStandardMaterial): metal anisótropo cepillado con barniz y reflejos especulares
  const metal = new THREE.MeshPhysicalMaterial({ color: 0x8fa3b4, metalness: 1, roughness: 0.34, roughnessMap: brushT, bumpMap: brushT, bumpScale: 0.6,
    anisotropy: 0.75, clearcoat: 0.55, clearcoatRoughness: 0.12, emissive: 0x020a12 });
  const metalDark = new THREE.MeshPhysicalMaterial({ color: 0x2a3540, metalness: 1, roughness: 0.42, roughnessMap: brushT, anisotropy: 0.6, clearcoat: 0.3 });
  // bisel exterior y aros mecanizados con aletas (instanciadas) que dan volumen y profundidad real
  const bezel = new THREE.Mesh(new THREE.TorusGeometry(1.62, 0.09, 24, 160), metal); bezel.scale.z = 0.55; bezel.position.z = -0.35; rig.add(bezel);
  const outerRim = new THREE.Mesh(new THREE.TorusGeometry(3.12, 0.035, 12, 240), metalDark); outerRim.position.z = -0.7; rig.add(outerRim);
  const fins = new THREE.InstancedMesh(new THREE.BoxGeometry(0.05, 0.26, 0.12), metalDark, 36), fm = new THREE.Object3D();
  for (let i = 0; i < 36; i++) { const a = i * Math.PI / 18; fm.position.set(Math.cos(a) * 1.82, Math.sin(a) * 1.82, -0.45); fm.rotation.set(0, 0, a); fm.updateMatrix(); fins.setMatrixAt(i, fm.matrix); }
  rig.add(fins);
  const housing = new THREE.Mesh(new THREE.TorusGeometry(1.32, 0.16, 24, 96), metal); housing.position.z = -0.2; rig.add(housing);
  const housing2 = new THREE.Mesh(new THREE.TorusGeometry(0.78, 0.07, 16, 72), metal); housing2.position.z = 0.05; rig.add(housing2);
  // reactor de arco (diseño original): 10 bobinas de cobre bobinado sobre núcleo de hierro, separadores de metal
  const copperC = document.createElement("canvas"); copperC.width = 64; copperC.height = 256;
  { const g = copperC.getContext("2d"); for (let y = 0; y < 256; y += 4) { const v = 150 + ((y * 37) % 60);
      g.fillStyle = "rgb(" + v + "," + (v * 0.55 | 0) + "," + (v * 0.32 | 0) + ")"; g.fillRect(0, y, 64, 3); g.fillStyle = "#2a160c"; g.fillRect(0, y + 3, 64, 1); } }
  const copperT = new THREE.CanvasTexture(copperC); copperT.colorSpace = THREE.SRGBColorSpace;
  const copper = new THREE.MeshPhysicalMaterial({ map: copperT, bumpMap: copperT, bumpScale: 1.2, metalness: 1, roughness: 0.28, clearcoat: 0.6, clearcoatRoughness: 0.1, color: 0xffc7a0 });
  const coilGeo = new THREE.CylinderGeometry(0.11, 0.11, 0.34, 20, 1);
  for (let i = 0; i < 10; i++) {
    const a = i * Math.PI / 5 + Math.PI / 10, coil = new THREE.Mesh(coilGeo, copper);
    coil.position.set(Math.cos(a) * 1.05, Math.sin(a) * 1.05, -0.02); coil.rotation.z = a; rig.add(coil);
    const sep = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.4, 0.2), metal), b = i * Math.PI / 5;
    sep.position.set(Math.cos(b) * 1.05, Math.sin(b) * 1.05, -0.02); sep.rotation.z = b; rig.add(sep);
  }
  // anillos mecánicos con dientes de engranaje que giran en sentidos opuestos (encajan con "clic" al arrancar)
  function gear(r0, r1, teeth, depth) {
    const sh = new THREE.Shape(), n = teeth * 4;
    for (let i = 0; i <= n; i++) { const a = i / n * Math.PI * 2, out = (i % 4 === 1 || i % 4 === 2) ? depth : 0;
      const x = Math.cos(a) * (r1 + out), y = Math.sin(a) * (r1 + out); i ? sh.lineTo(x, y) : sh.moveTo(x, y); }
    const hole = new THREE.Path(); hole.absarc(0, 0, r0, 0, Math.PI * 2, true); sh.holes.push(hole);
    return new THREE.ExtrudeGeometry(sh, { depth: 0.08, bevelEnabled: true, bevelThickness: 0.015, bevelSize: 0.012, bevelSegments: 2, curveSegments: 96 });
  }
  const gears = [[1.98, 2.1, 72, 0.05, -0.55, 0.09], [2.42, 2.5, 96, 0.04, -0.75, -0.06], [1.38, 1.46, 40, 0.05, -0.15, 0.14]].map((q) => {
    const m = new THREE.Mesh(gear(q[0], q[1], q[2], q[3]), q[2] > 80 ? metalDark : metal); m.position.z = q[4]; m.userData.spin = q[5]; rig.add(m); return m; });
  const coreLight = new THREE.PointLight(0x7fd8ff, 40, 9, 2); coreLight.position.z = 0.6; rig.add(coreLight);
  scene.add(new THREE.AmbientLight(0x0b1c2a, 1.2));
  const rim = new THREE.DirectionalLight(0x9fd0ff, 1.4); rim.position.set(-3, 4, 5); scene.add(rim);
  const key = new THREE.DirectionalLight(0xffc890, 0.55); key.position.set(5, -2, 4); scene.add(key);   // contraluz cálido: especular dorado en el metal

  // humo volumétrico de fondo iluminado por el núcleo (fbm lento): da aire y profundidad; octavas según calidad
  const hazeMat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    uniforms: { uT: { value: 0 }, uLv: { value: 0 }, uQ: { value: 2 } },
    vertexShader: "varying vec2 vP; void main(){ vP=position.xy; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }",
    fragmentShader: `uniform float uT; uniform float uLv; uniform float uQ; varying vec2 vP;
      float h(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
      float n(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
        return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y); }
      void main(){ vec2 p=vP*.32; float r=length(vP); float a=0., w=.5;
        for(int i=0;i<5;i++){ if(float(i)>=uQ*2.+1.) break; a+=w*n(p+vec2(uT*.035*(1.+float(i)),-uT*.02)); p=p*2.03+vec2(1.7,9.2); w*=.5; }
        float light=exp(-r*.42)*(1.+.9*uLv) + .25*exp(-r*.12);
        vec3 c=vec3(.02,.13,.30)*a*a*a*light*.9 + vec3(.0,.012,.03)*exp(-r*.3);
        gl_FragColor=vec4(c,1.); }` });
  const haze = new THREE.Mesh(new THREE.PlaneGeometry(40, 24), hazeMat); haze.position.z = -3.2; scene.add(haze);

  // anillos HUD (mismo orden/proporciones que el 2D: radio, grosor, segmentos, hueco, velocidad)
  const RINGS = [[3.3, 0.012, 64, 0.35, 0.03, 0.4, ICE, -0.9], [2.98, 0.07, 24, 0.25, -0.35, 0.55, CYAN, -0.6],
    [2.64, 0.02, 120, 0.5, 0.6, 0.5, ICE, -0.4], [2.36, 0.10, 10, 0.12, -0.12, 0.7, CYAN, -0.25],
    [2.0, 0.04, 36, 0.4, -0.55, 0.7, CYAN, 0.0], [1.72, 0.08, 6, 0.2, 1.1, 0.8, CYAN, 0.2]];
  const ringMats = RINGS.map((r) => {
    const m = add({ c: r[6], o: r[5] }); layer(r[7], r[4], new THREE.Mesh(band(r[0], r[0] + r[1], r[2], r[3], r[2] > 60 ? 2 : 6), m)); return m; });
  const tickMat = new THREE.LineBasicMaterial({ color: ICE, transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
  [[3.45, 360, 0.04, 0.12, 10, -0.03, -1.0], [2.78, 180, 0.05, 0.13, 5, 0.07, -0.5], [2.15, 120, 0.04, 0.1, 6, -0.15, -0.1], [3.9, 72, 0.03, 0.18, 9, 0.02, -1.4]]
    .forEach((t) => layer(t[6], t[5], new THREE.LineSegments(ticks(t[0], t[1], t[2], t[3], t[4]), tickMat)));
  const arcs = [];                                 // arcos de datos largos que barren
  [[3.65, 0.025, 0.7, ICE, -1.1], [3.8, 0.04, 1.2, CYAN, -1.2], [2.5, 0.03, 0.9, ICE, -0.3], [4.15, 0.015, 2.2, CYAN, -1.6]].forEach((a, i) => {
    const g = new THREE.RingGeometry(a[0], a[0] + a[1], 64, 1, 0, a[2]);
    const m = layer(a[4], 0, new THREE.Mesh(g, add({ c: a[3], o: 0.85 }))); m.userData.arc = i; arcs.push(m); });

  // --- HUD procedural en GPU (un solo quad + shader): decenas de anillos finos, arcos segmentados que giran a
  //     distintas velocidades, marcas densas, radios, barrido de radar y onda de voz alrededor del centro.
  //     Coste fijo por píxel, cero asignaciones por fotograma; nítido a cualquier devicePixelRatio (fwidth).
  const hudMat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    extensions: { derivatives: true }, uniforms: { uT: { value: 0 }, uLv: { value: 0 }, uLi: { value: 0 }, uPh: { value: 0 }, uSw: { value: 0 } },
    vertexShader: "varying vec2 vP; void main(){ vP=position.xy; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }",
    fragmentShader: `uniform float uT; uniform float uLv; uniform float uLi; uniform float uPh; uniform float uSw; varying vec2 vP;
      #define TAU 6.2831853
      float line(float d,float w){ float f=fwidth(d); return 1.-smoothstep(w,w+f*1.2,abs(d)); }
      float seg(float a,float n,float gap,float rot){ float u=fract((a+rot)/TAU*n); return step(gap,u); }
      void main(){
        float r=length(vP), a=atan(vP.y,vP.x)+3.14159265; vec3 cy=vec3(.02,.8,1.7), ic=vec3(.7,1.1,1.5); vec3 c=vec3(0.);
        float t=uT;   // uPh/uSw: fases integradas en CPU con dt (cambiar la velocidad nunca hace saltar el ángulo)
        // anillos finos de fondo (cada uno con su propio giro y segmentación)
        for(int i=0;i<14;i++){ float fi=float(i), rr=1.55+fi*.205, dir=mod(fi,2.)<1.?1.:-1.;
          float n=floor(8.+mod(fi*37.,90.)), g=.08+.5*fract(fi*.618);
          float k=line(r-rr,.004+.006*fract(fi*.37))*seg(a,n,g,dir*uPh*(.03+.22*fract(fi*.91)*fract(fi*.91)));
          c+=mix(cy,ic,fract(fi*.43))*k*(.35+.35*fract(fi*.71)); }
        // marcas densas (360 y 72) con rotación lenta
        float tk1=step(.86,fract((a+t*.02)/TAU*360.))*step(abs(r-4.32),.035);
        float tk2=step(.8,fract((a-t*.035)/TAU*72.))*step(abs(r-1.62),.06);
        c+=ic*(tk1*.55+tk2*.7);
        // arcos gruesos de datos que barren con aceleración
        for(int j=0;j<4;j++){ float fj=float(j), rr=1.9+fj*.62, ph=uPh*(.11+fj*.05)*(mod(fj,2.)<1.?1.:-1.), len=.6+fj*.35;
          float da=mod(a-ph*TAU*.4,TAU); c+=cy*line(r-rr,.018)*step(da,len)*(1.-.6*da/len)*1.2; }
        // radios finos y barrido de radar
        c+=ic*.12*line(fract(a/TAU*24.)-.5,.0015*24./max(r,.5))*step(1.6,r)*step(r,4.4);
        float sw=mod(a-uSw,TAU); c+=cy*.22*exp(-sw*3.)*step(1.55,r)*step(r,4.4);
        // onda de voz alrededor del núcleo
        float wv=.95+(.06+.45*uLv+.06*uLi)*sin(a*12.+t*6.)*sin(a*5.-t*3.7);
        c+=ic*line(r-wv,.012)*(.7+2.6*uLv) + cy*line(r-1.18,.006)*.7;
        c*=smoothstep(4.9,4.4,r);
        // holograma: líneas de barrido finas que derivan despacio, banda de refresco que sube suave y borde fresnel
        float sl=.82+.18*sin(vP.y*95.-uT*1.3); float band=.85+.3*exp(-pow(mod(vP.y*.5-uT*.35,3.)-1.5,2.)*9.);
        float fr=1.+.55*smoothstep(3.6,4.5,r)+.35*(1.-smoothstep(.0,1.3,r));
        c*=sl*band*fr*(.97+.03*sin(uT*1.7+vP.x*.8));
        gl_FragColor=vec4(c,1.); }` });
  layer(-0.45, 0, new THREE.Mesh(new THREE.PlaneGeometry(10, 10), hudMat));

  // triángulos (dos, girando en contra) como tubos luminosos
  const triMats = [], tris = [];
  [[1.42, 0.035], [1.28, 0.014]].forEach((t, q) => {
    const pts = []; for (let j = 0; j <= 3; j++) { const a = j * Math.PI * 2 / 3 - Math.PI / 2; pts.push(new THREE.Vector3(Math.cos(a) * t[0], Math.sin(a) * t[0], 0)); }
    const path = new THREE.CurvePath(); for (let j = 0; j < 3; j++) path.add(new THREE.LineCurve3(pts[j], pts[j + 1]));
    const m = add({ c: ICE, o: 1 }); triMats.push(m);
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(path, 48, t[1], 6, true), m); mesh.position.z = 0.25 + q * 0.05; rig.add(mesh); tris.push(mesh);
  });

  // reactor: núcleo blanco, halo volumétrico (shader fresnel) y destello
  const coreMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(1.8, 2.4, 3.2), toneMapped: false });
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.3, 48, 32), coreMat); core.position.z = 0.3; rig.add(core);
  const volMat = new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uI: { value: 1 }, uT: { value: 0 } },
    vertexShader: "varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); vN=normalize(normalMatrix*normal); vV=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }",
    fragmentShader: "uniform float uI; uniform float uT; varying vec3 vN; varying vec3 vV; void main(){ float f=pow(max(dot(vN,vV),0.),2.2); float n=.85+.15*sin(uT*7.+vN.x*9.+vN.y*7.); gl_FragColor=vec4(vec3(.06,.32,.9)*f*f*uI*n,1.); }" });
  const vol = new THREE.Mesh(new THREE.SphereGeometry(0.75, 48, 32), volMat); vol.position.z = 0.2; rig.add(vol);
  const flare = new THREE.Mesh(new THREE.PlaneGeometry(9, 0.03), add({ c: ICE, o: 0.35 })); flare.position.z = 0.4; rig.add(flare);

  // partículas reutilizadas (un solo Points)
  const PN = 260, ppos = new Float32Array(PN * 3), pdat = [];
  for (let i = 0; i < PN; i++) pdat.push({ a: Math.random() * 7, r: 0.6 + Math.random() * 3.6, s: (Math.random() - 0.5) * 0.3, z: (Math.random() - 0.5) * 1.6 });
  const pgeo = new THREE.BufferGeometry(); pgeo.setAttribute("position", new THREE.BufferAttribute(ppos, 3));
  rig.add(new THREE.Points(pgeo, new THREE.PointsMaterial({ color: ICE, size: 0.025, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false })));

  // lecturas numéricas alrededor de los anillos (canvas 2D -> textura, se actualizan 2 veces por segundo)
  const reads = [];
  [[-5.4, 2.2, "VISUAL PWR"], [5.4, 2.2, "VISUAL SYNC"], [-5.4, -2.2, "VISUAL FLUX"], [5.4, -2.2, "VISUAL CORE"]].forEach((r) => {
    const c = document.createElement("canvas"); c.width = 256; c.height = 64;
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
    const sp = new THREE.Mesh(new THREE.PlaneGeometry(2.0, 0.5), new THREE.MeshBasicMaterial({ map: tex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    sp.position.set(r[0], r[1], -0.8); rig.add(sp); reads.push({ c, tex, label: r[2] });
  });
  let nextRead = 0;
  function readouts(t, lv) {
    reads.forEach((r, i) => {
      const g = r.c.getContext("2d"); g.clearRect(0, 0, 256, 64);
      g.font = "600 18px 'Helvetica Neue',Arial,sans-serif"; g.fillStyle = i % 2 ? "#5fe0ff" : "#9fe6ff"; g.fillText(r.label, 6, 22);
      const v = i === 4 ? "JARVIS" : (i === 3 ? (3000 + 400 * lv + 20 * Math.sin(t)).toFixed(0) : (60 + 35 * lv + 4 * Math.sin(t * (i + 1))).toFixed(1) + "%");
      g.font = "300 30px 'Helvetica Neue',Arial,sans-serif"; g.fillStyle = "#e6f8ff"; g.fillText(v, 6, 56);
      g.fillStyle = "rgba(120,220,255,.6)"; g.fillRect(150, 44, 100 * (0.3 + 0.7 * Math.abs(Math.sin(t * 0.7 + i))), 4);
      r.tex.needsUpdate = true;
    });
  }

  // rayos: pool fijo creado una sola vez; cada disparo solo gira/muestra mallas existentes (sin asignar ni liberar)
  const BOLT_C = new THREE.Color(1.2, 1.9, 2.8); const bolts = []; let nextBolt = 0;
  function jag(a, b, d, out) {
    if (d <= 0) { out.push(b); return; }
    const m = a.clone().lerp(b, 0.5), len = a.distanceTo(b), o = (Math.random() - 0.5) * len * 0.35;
    m.x += -(b.y - a.y) / len * o; m.y += (b.x - a.x) / len * o; m.z += (Math.random() - 0.5) * 0.15;
    jag(a, m, d - 1, out); jag(m, b, d - 1, out);
  }
  for (let i = 0; i < 12; i++) {
    const r1 = 1.6 + Math.random() * 1.5, a = new THREE.Vector3(0.45, 0, 0.3), bb = (Math.random() - 0.5),
      b = new THREE.Vector3(Math.cos(bb) * r1, Math.sin(bb) * r1, -0.3), pts = [a];
    jag(a, b, 5, pts);
    const path = new THREE.CurvePath(); for (let j = 0; j < pts.length - 1; j++) path.add(new THREE.LineCurve3(pts[j], pts[j + 1]));
    const bm = add({ c: BOLT_C, o: 0 });             // un material por rayo (creado aquí, una sola vez) para fundir su opacidad
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(path, pts.length * 2, 0.018, 4, false), bm);
    mesh.visible = false; rig.add(mesh); bolts.push({ mesh, mat: bm, born: -1e9, life: 1, peak: 1 });
  }
  function spawnBolts(now, lv) {                   // solo reutiliza rayos ya apagados: nunca corta uno que se está viendo
    let nb = 1 + Math.floor(Math.random() * (2 + lv * 5));
    for (let i = 0; i < bolts.length && nb > 0; i++) { const b = bolts[(i + ((Math.random() * bolts.length) | 0)) % bolts.length];
      if (now - b.born < b.life) continue;
      b.mesh.rotation.z = Math.random() * Math.PI * 2; b.born = now; b.life = 380 + Math.random() * 520; b.peak = 0.55 + Math.random() * 0.45; nb--; }
    nextBolt = now + (260 + Math.random() * 640) * (1 - lv * 0.6);
  }
  function boltEnv(x) {                             // 0..1 → entrada suave (smoothstep 18%) y salida exponencial suave
    if (x <= 0 || x >= 1) return 0; const a = Math.min(1, x / 0.18), up = a * a * (3 - 2 * a), d = (1 - x);
    return up * d * d * (3 - 2 * d) * (0.85 + 0.15 * Math.cos(x * 9.0));
  }

  // --- postproceso: bloom HDR a media resolución + lente (aberración, grano, barrido, hex, caída de luz) ---
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, cam));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.72, 0.3, 0.9);
  let bloomRes = 0.5; const bloomSize = bloom.setSize.bind(bloom);   // arranca a media resolución (GPU débil: MacBook Pro 2015); sube si sobra margen
  bloom.setSize = (w, h) => bloomSize(Math.max(1, Math.round(w * bloomRes)), Math.max(1, Math.round(h * bloomRes)));
  const rays = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, uL: { value: new THREE.Vector2(0.5, 0.5) }, uN: { value: 56 }, uI: { value: 0.5 }, uAsp: { value: 1 }, uR: { value: 0.05 } },
    vertexShader: "varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }",
    fragmentShader: `uniform sampler2D tDiffuse; uniform vec2 uL; uniform float uN; uniform float uI; uniform float uAsp; uniform float uR; varying vec2 vUv;
      void main(){
        // refracción: cúpula de cristal sobre el reactor (desvía la imagen según la normal de una esfera + brillo fresnel en el borde)
        vec2 dl=(vUv-uL)*vec2(uAsp,1.); float rr=length(dl)/uR; vec2 uv=vUv; float rim=0.;
        if(rr<1.){ float z=sqrt(1.-rr*rr); uv-= (dl/vec2(uAsp,1.))*(1.-z)*.55; rim=pow(1.-z,3.); }
        vec3 col=texture2D(tDiffuse,uv).rgb + vec3(.35,.75,1.)*rim*.6;
        // dispersión volumétrica: muestras hacia la luz, solo de lo brillante, con caída
        vec2 st=(vUv-uL)/uN*.9; vec2 p=vUv; float dec=1.; vec3 acc=vec3(0.);
        for(int i=0;i<64;i++){ if(float(i)>=uN) break; p-=st; vec3 s=texture2D(tDiffuse,p).rgb; acc+=max(s-vec3(1.),0.)*dec; dec*=.955; }
        col+=acc/uN*uI*vec3(.55,.85,1.15)*.7;
        gl_FragColor=vec4(col,1.); }` });
  composer.addPass(rays);
  composer.addPass(bloom);
  const lens = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, uT: { value: 0 }, uRes: { value: new THREE.Vector2(1, 1) }, uCA: { value: 1 }, uDof: { value: /[?&]dof=1\b/.test(location.search) ? 1 : 0 } },
    vertexShader: "varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }",
    fragmentShader: `uniform sampler2D tDiffuse; uniform float uT; uniform vec2 uRes; uniform float uCA; uniform float uDof; varying vec2 vUv;
      float h(vec2 p){ return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453); }
      float hex(vec2 p){ p.x*=1.1547; p.y+=mod(floor(p.x),2.)*.5; p=abs(fract(p)-.5); return abs(max(p.x*1.5+p.y,p.y*2.)-1.); }
      void main(){
        vec2 c=vUv-.5; float d=length(c*vec2(uRes.x/uRes.y,1.));
        vec2 off=c*.0022*uCA*(.3+d);
        vec3 col=vec3(texture2D(tDiffuse,vUv+off).r, texture2D(tDiffuse,vUv).g, texture2D(tDiffuse,vUv-off).b);
        // profundidad de campo suave: lo lejano al foco (capas de fondo/bordes) se desenfoca con 8 muestras en disco
        float coc=smoothstep(.32,.95,d)*3.5*uDof; vec3 bl=col*8.;
        if(uDof>.5){ bl=vec3(0.); for(int k=0;k<8;k++){ float an=float(k)*.785398+.39; bl+=texture2D(tDiffuse,vUv+vec2(cos(an),sin(an))*coc/uRes*1.6).rgb; } }
        col=mix(col,bl*.125,smoothstep(0.,1.,coc/3.5)*.85);
        vec2 px=vUv*uRes; float scan=.95+.05*sin(px.y*1.6+uT*2.);
        float hx=smoothstep(.06,0.,hex(px/38.))*.05*smoothstep(.15,.6,d);
        col+=vec3(.2,.6,1.)*hx;
        col*=scan*mix(1.,.25,smoothstep(.35,1.05,d));
        col=max(col-vec3(.018,.03,.05),0.)*1.06;   // negros de cine: quita el velo azul (más contraste y profundidad)
        col+=(h(px+fract(uT)*91.)-.5)*.018;   // grano de película fino
        gl_FragColor=vec4(col,1.); }` });
  composer.addPass(lens); composer.addPass(new OutputPass());

  // --- tamaño adaptativo y calidad según FPS ---
  let scale = 0.75, W = 0, H = 0, cnt = 0, quality = 1,   // arranque en calidad baja; el auto-escalado sube con margen
      good = 0, coolUntil = 0;
  const FT = new Float32Array(120), FS = new Float32Array(120);   // ventana de frame-times (prealocada)
  function fit() {
    W = innerWidth; H = innerHeight; const pr = Math.min(DPR_MAX, devicePixelRatio || 1) * scale;
    renderer.setPixelRatio(pr); composer.setPixelRatio(pr); renderer.setSize(W, H, false); composer.setSize(W, H);
    cam.aspect = W / H; cam.fov = 38; cam.position.z = 4.5 / Math.tan(THREE.MathUtils.degToRad(19)) / Math.min(1, cam.aspect / 1.15); cam.updateProjectionMatrix();
    lens.uniforms.uRes.value.set(W * pr, H * pr); rays.uniforms.uAsp.value = W / H;   // el HUD cabe en alto (ultrawide 3840×1080) y en ancho
  }
  rays.uniforms.uN.value = 28; hazeMat.uniforms.uQ.value = 1;   // coherente con quality = 1
  addEventListener("resize", fit); fit();
  let p95 = 16.7, avgMs = 16.7;
  function adapt(dt, now) {                         // escala dinámica por p95 (no por promedio), con histéresis y enfriamiento
    FT[cnt++] = dt; if (cnt < FT.length) return;
    cnt = 0; FS.set(FT); FS.sort(); p95 = FS[Math.floor(FS.length * 0.95)];
    let sum = 0; for (let i = 0; i < FT.length; i++) sum += FT[i]; avgMs = sum / FT.length;
    window.JarvisNucleoFrameMs = avgMs; window.JarvisNucleoP95 = p95;
    if (now < coolUntil || document.hidden) return;
    if (p95 > 18) { good = 0;                       // primero baja el bloom, luego la resolución
      if (quality > 1) { quality = 1; bloomRes = 0.5; rays.uniforms.uN.value = 28; hazeMat.uniforms.uQ.value = 1; } else if (scale > 0.5) scale = Math.max(0.5, scale - 0.15); else return;
      fit(); coolUntil = now + 2500; }
    else if (p95 < 13 && (scale < 1 || quality < 2) && ++good >= 3) { good = 0;   // sube solo con margen sostenido (~6 s)
      if (scale < 1) scale = Math.min(1, scale + 0.1); else { quality = 2; bloomRes = 1; rays.uniforms.uN.value = 56; hazeMat.uniforms.uQ.value = 2; }
      fit(); coolUntil = now + 4000; }
  }
  // overlay ?fps=1: texto actualizado a 4 Hz, fuera del render
  const fpsBox = /[?&]fps=1\b/.test(location.search) ? document.body.appendChild(document.createElement("div")) : null;
  if (fpsBox) { fpsBox.style.cssText = "position:fixed;top:8px;left:8px;z-index:9;font:12px ui-monospace,monospace;color:#7fe6ff;background:rgba(0,10,20,.6);padding:4px 8px;pointer-events:none;white-space:pre";
    setInterval(() => { fpsBox.textContent = (1000 / avgMs).toFixed(0) + " fps  p95 " + p95.toFixed(1) + " ms\nres " + (renderer.getPixelRatio()).toFixed(2) + "x  bloom " + (bloomRes === 1 ? "full" : "1/2") + "  dof " + lens.uniforms.uDof.value; }, 250); }

  let mx = 0, my = 0, env = 0, envV = 0, nextLab = 0, ph = 0, sw = 0, smx = 0, smy = 0; const coreW = new THREE.Vector3(); addEventListener("pointermove", (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });
  const lab = document.getElementById("estado");   // cacheado: sin consultas al DOM en el bucle
  // latido "lub-dub" a 66 ppm, siempre visible (también en reposo); más fuerte al hablar (hbAmp sigue al nivel de voz)
  const HB = 66 / 60, gs = (x) => Math.exp(-(x * x) / 0.0022);
  const heart = (tt) => { const p = (tt * HB) % 1; return gs(p) + gs(p - 1) + 0.6 * gs(p - 0.2); };
  let t0 = -1; const easeBack = (x) => { const c = 1.9; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  N.paso = function (now, dt, st) {
    dt = Math.min(Math.max(dt, 0), 50);              // dt acotado: sin saltos tras pestaña oculta o tirón
    const t = now / 1000, raw = st.level || 0, li = st.listen || 0;
    { // resorte críticamente amortiguado, solución exacta (estable con cualquier dt): sube ya (~35 ms) sin escalón, baja suave (~160 ms)
      const w = raw > env ? 0.045 : 0.012, x0 = env - raw, k = Math.exp(-w * dt), q = (envV + w * x0) * dt;
      env = raw + (x0 + q) * k; envV = (envV - w * q) * k; if (env < 0) { env = 0; envV = 0; } }
    const lv = Math.min(1, env * 1.6), hbAmp = 1 + 1.6 * lv, breath = Math.min(1.6, heart(t) * hbAmp), boost = 1 + lv * 0.55 + li * 0.25;
    if (t0 < 0) t0 = now;
    { const ts = (now - t0) / 1000;                      // arranque: los anillos llegan girando y encajan con un pequeño rebote
      for (let i = 0; i < gears.length; i++) { const g = gears[i], x = Math.min(1, Math.max(0, (ts - 0.2 - i * 0.35) / 0.7)), e = x < 1 ? easeBack(x) : 1;
        g.scale.setScalar(0.001 + 0.999 * e); g.rotation.z += g.userData.spin * dt * 0.001 * (1 + 1.5 * env) + (x < 1 ? (1 - x) * dt * 0.006 * (i % 2 ? -1 : 1) : 0); }
      for (let i = 0; i < layers.length; i++) { const x = Math.min(1, Math.max(0, (ts - 0.1 - i * 0.12) / 0.6)); layers[i].scale.setScalar((0.001 + 0.999 * (x < 1 ? easeBack(x) : 1)) * (1 + 0.035 * hbAmp * heart(t - 0.05 * i))); } }   // onda del latido hacia fuera
    adapt(dt, now); const kr = 1 - Math.exp(-dt / 300), km = 1 - Math.exp(-dt / 140);
    smx += (mx - smx) * km; smy += (my - smy) * km;                 // ratón doblemente suavizado: el paralaje nunca da tirones
    rig.rotation.x += ((-smy * 0.32 + Math.sin(t * 0.21) * 0.06 + 0.12) - rig.rotation.x) * kr;   // inclinación + paralaje
    rig.rotation.y += ((smx * 0.45 + Math.sin(t * 0.17) * 0.08) - rig.rotation.y) * kr;
    layers.forEach((o) => { if (o.userData.speed) o.rotation.z += o.userData.speed * dt * 0.001 * (1 + 2.2 * lv); });
    arcs.forEach((o, i) => { const ph = (t * (0.15 + i * 0.07)) % 1, e = ph < 0.5 ? 4 * ph ** 3 : 1 - Math.pow(-2 * ph + 2, 3) / 2; o.rotation.z = e * Math.PI * 2 * (i % 2 ? -1 : 1) + i * 2; });
    ringMats.forEach((m, k) => { m.opacity = Math.min(1, RINGS[k][5] * (0.8 + 0.2 * breath) * boost); });
    tris[0].rotation.z = t * 0.25; tris[1].rotation.z = -t * 0.25;
    triMats.forEach((m) => { m.opacity = Math.min(1, 0.85 * boost); });
    const s = 1 + 0.12 * breath + 0.2 * lv + 0.05 * li, flick = 0.97 + 0.03 * Math.sin(t * 5.1) * Math.sin(t * 2.3);   // parpadeo suave, sin ruido por frame
    core.scale.setScalar(s); vol.scale.setScalar(1 + 0.08 * breath + 0.35 * lv);
    volMat.uniforms.uI.value = (0.5 + 0.35 * breath + 0.45 * lv) * flick; volMat.uniforms.uT.value = t;
    coreLight.intensity = (14 + 16 * breath + 18 * lv) * flick;
    flare.material.opacity = (0.1 + 0.2 * lv) * boost;
    bloom.strength = (quality > 1 ? 0.72 : 0.62) + breath * 0.22 + lv * 0.25 + li * 0.06;
    for (let i = 0; i < PN; i++) { const p = pdat[i]; p.a += p.s * dt / 1000 * (1 + lv * 3);
      ppos[i * 3] = Math.cos(p.a) * p.r; ppos[i * 3 + 1] = Math.sin(p.a) * p.r; ppos[i * 3 + 2] = p.z; }
    pgeo.attributes.position.needsUpdate = true;
    if (now > nextBolt) spawnBolts(now, lv);
    for (let i = 0; i < bolts.length; i++) { const b = bolts[i], e = boltEnv((now - b.born) / b.life) * b.peak;
      b.mat.opacity = Math.min(1, e * (0.75 + 0.6 * lv)); b.mesh.visible = e > 0.003; }
    if (now > nextRead) { readouts(t, lv); nextRead = now + 500; }
    hudMat.uniforms.uT.value = t; ph += dt * 0.001 * (1 + 2.5 * lv); sw += dt * 0.001 * (1.4 + 2 * lv);
    hudMat.uniforms.uPh.value = ph; hudMat.uniforms.uSw.value = sw % 6.2831853; hudMat.uniforms.uLv.value = lv; hudMat.uniforms.uLi.value = li;
    lens.uniforms.uT.value = t; lens.uniforms.uCA.value = 1 + lv * 1.5; hazeMat.uniforms.uT.value = t; hazeMat.uniforms.uLv.value = lv;
    core.getWorldPosition(coreW).project(cam); rays.uniforms.uL.value.set(coreW.x * 0.5 + 0.5, coreW.y * 0.5 + 0.5);
    rays.uniforms.uI.value = 0.42 + 0.3 * breath + 0.55 * lv; rays.uniforms.uR.value = 0.036 * s;
    composer.render();
    if (lab && now > nextLab) { nextLab = now + 100; const txt = lv > 0.05 ? "HABLANDO" : li > 0.5 ? "ESCUCHANDO" : "EN LÍNEA"; if (lab.textContent !== txt) lab.textContent = txt; }
  };
  N.gl = true;
}
