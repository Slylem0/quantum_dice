/*
  Escena 3D del dado cuántico (three.js + bloom).

  - Un dado (cubo con pips) que, mientras no se ha tirado, gira en
    "superposición": semitransparente, con un aura que pulsa y caras que
    cambian — representa que el resultado aún no está decidido.
  - Al tirar (roll), dos partículas entrelazadas salen de una fuente central,
    se separan (Alice y Bob) y, al medirlas, el dado "colapsa" a una cara.
  - El color del aura refleja si se violó Bell (turquesa = cuántico/certificado,
    ámbar = no concluyente).
  - Postprocesado con bloom para que todo lo luminoso resplandezca.

  Portable a Qollab: three.js por import map, sin assets binarios.
*/

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const COL = {
  quantum: 0x2fe0c0, // violó Bell: certificado
  neutral: 0x8a7cff, // superposición (en espera)
  warn: 0xffb454,    // no concluyente
  alice: 0x58d8ff,
  bob: 0xff7a1a,
};

// Posiciones de los pips (1..6) en una cara de cara unitaria [-1,1]^2.
const PIPS = {
  1: [[0, 0]],
  2: [[-0.5, 0.5], [0.5, -0.5]],
  3: [[-0.5, 0.5], [0, 0], [0.5, -0.5]],
  4: [[-0.5, 0.5], [0.5, 0.5], [-0.5, -0.5], [0.5, -0.5]],
  5: [[-0.5, 0.5], [0.5, 0.5], [0, 0], [-0.5, -0.5], [0.5, -0.5]],
  6: [[-0.5, 0.5], [0.5, 0.5], [-0.5, 0], [0.5, 0], [-0.5, -0.5], [0.5, -0.5]],
};

export class DiceScene {
  constructor(container) {
    this.container = container;
    this.clock = new THREE.Clock();
    this.state = "idle"; // idle | rolling | settled
    this.spin = { x: 0.4, y: 0.6 };
    this._initRenderer();
    this._initScene();
    this._initCamera();
    this._initLights();
    this._initComposer();
    this._buildDie();
    this._buildParticles();
    this._bindResize();
    this._animate();
  }

  _initRenderer() {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    this.container.appendChild(this.renderer.domElement);
  }

  _initScene() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0f1e);
    this.scene.fog = new THREE.FogExp2(0x0a0f1e, 0.04);
  }

  _initCamera() {
    const aspect = this.container.clientWidth / this.container.clientHeight;
    this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 100);
    this.camera.position.set(0, 1.4, 6.5);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 4;
    this.controls.maxDistance = 14;
    this.controls.enablePan = false;
    this.controls.target.set(0, 0.3, 0);
  }

  _initLights() {
    this.scene.add(new THREE.HemisphereLight(0xbcd0ff, 0x1a1424, 0.8));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(5, 8, 6);
    this.scene.add(key);
    const rim = new THREE.PointLight(COL.neutral, 0.8, 30);
    rim.position.set(-5, 3, -4);
    this.scene.add(rim);
  }

  _initComposer() {
    const size = new THREE.Vector2(this.container.clientWidth, this.container.clientHeight);
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    // threshold alto para que solo lo MUY brillante (aura/partículas) haga
    // bloom; los pips del dado quedan nítidos, no manchas blancas.
    this.bloom = new UnrealBloomPass(size, 0.35, 0.5, 0.95);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
  }

  _buildDie() {
    this.die = new THREE.Group();
    this.scene.add(this.die);

    // Cuerpo del dado (cubo redondeado aproximado con bisel por escala).
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(2, 2, 2),
      new THREE.MeshPhysicalMaterial({
        color: 0x2a3650,
        metalness: 0.3,
        roughness: 0.3,
        transmission: 0.15,
        thickness: 0.8,
        transparent: true,
        opacity: 0.95,
        clearcoat: 1.0,
      })
    );
    this.die.add(body);
    this.body = body;

    // Aura (wireframe) que pulsa en superposición.
    const aura = new THREE.Mesh(
      new THREE.BoxGeometry(2.15, 2.15, 2.15),
      new THREE.MeshBasicMaterial({ color: COL.neutral, wireframe: true, transparent: true, opacity: 0.35 })
    );
    this.die.add(aura);
    this.aura = aura;

    // Pips en las 6 caras.
    this.faces = {};
    const faceDefs = [
      { n: 1, pos: [0, 0, 1.01], rot: [0, 0, 0] },
      { n: 6, pos: [0, 0, -1.01], rot: [0, Math.PI, 0] },
      { n: 2, pos: [1.01, 0, 0], rot: [0, Math.PI / 2, 0] },
      { n: 5, pos: [-1.01, 0, 0], rot: [0, -Math.PI / 2, 0] },
      { n: 3, pos: [0, 1.01, 0], rot: [-Math.PI / 2, 0, 0] },
      { n: 4, pos: [0, -1.01, 0], rot: [Math.PI / 2, 0, 0] },
    ];
    const pipGeo = new THREE.CircleGeometry(0.17, 20);
    for (const f of faceDefs) {
      const g = new THREE.Group();
      g.position.set(...f.pos);
      g.rotation.set(...f.rot);
      for (const [px, py] of PIPS[f.n]) {
        const pip = new THREE.Mesh(
          pipGeo,
          new THREE.MeshStandardMaterial({ color: 0xf4f6fb, emissive: 0x223044, emissiveIntensity: 0.25, roughness: 0.5 })
        );
        pip.position.set(px, py, 0.01);
        g.add(pip);
      }
      this.die.add(g);
      this.faces[f.n] = g;
    }
  }

  _buildParticles() {
    // Dos "fotones" entrelazados que salen de la fuente al tirar.
    const geo = new THREE.SphereGeometry(0.12, 16, 16);
    this.pAlice = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: COL.alice }));
    this.pBob = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: COL.bob }));
    this.pAlice.visible = false;
    this.pBob.visible = false;
    this.scene.add(this.pAlice, this.pBob);
  }

  // Cambia el color del aura según el veredicto.
  setVerdict(violates) {
    const c = violates ? COL.quantum : COL.warn;
    this.aura.material.color.setHex(c);
  }

  /**
   * Anima una tirada: lanza las partículas, hace girar fuerte el dado y lo
   * asienta mostrando ``face`` (1..6). Devuelve una promesa que resuelve al
   * terminar la animación.
   */
  roll(face = 1, violates = true) {
    this.state = "rolling";
    this.setVerdict(violates);
    this._rollTarget = face;
    this._rollStart = this.clock.elapsedTime;
    this._rollDur = 1.6;
    this.pAlice.visible = true;
    this.pBob.visible = true;
    return new Promise((resolve) => {
      this._rollResolve = resolve;
    });
  }

  _faceToEuler(face) {
    // Rotación que deja la cara 'face' mirando a la cámara (+Z).
    const map = {
      1: [0, 0, 0],
      6: [0, Math.PI, 0],
      2: [0, -Math.PI / 2, 0],
      5: [0, Math.PI / 2, 0],
      3: [Math.PI / 2, 0, 0],
      4: [-Math.PI / 2, 0, 0],
    };
    return map[face] || [0, 0, 0];
  }

  _bindResize() {
    this._onResize = () => {
      const w = this.container.clientWidth;
      const h = this.container.clientHeight;
      if (!w || !h) return;
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h);
      this.composer.setSize(w, h);
    };
    window.addEventListener("resize", this._onResize);
  }

  _animate = () => {
    this._raf = requestAnimationFrame(this._animate);
    const dt = this.clock.getDelta();
    const t = this.clock.elapsedTime;

    // Aura pulsante (más intensa en superposición).
    const pulse = 0.3 + 0.25 * Math.sin(t * 3);
    this.aura.material.opacity = this.state === "idle" ? pulse + 0.15 : 0.3;
    this.aura.scale.setScalar(1 + 0.02 * Math.sin(t * 3));

    if (this.state === "idle") {
      // Superposición: gira suave, cuerpo semitransparente.
      this.die.rotation.x += dt * this.spin.x;
      this.die.rotation.y += dt * this.spin.y;
      this.body.material.opacity = 0.88 + 0.06 * Math.sin(t * 2);
    } else if (this.state === "rolling") {
      const p = Math.min(1, (t - this._rollStart) / this._rollDur);
      // Ease-out: gira muy rápido y frena hasta la cara objetivo.
      const ease = 1 - Math.pow(1 - p, 3);
      const spins = 4; // vueltas antes de asentar
      const [ex, ey, ez] = this._faceToEuler(this._rollTarget);
      this.die.rotation.x = ex + (1 - ease) * spins * Math.PI * 2 * this.spin.x;
      this.die.rotation.y = ey + (1 - ease) * spins * Math.PI * 2 * this.spin.y;
      this.die.rotation.z = ez;
      this.body.material.opacity = 0.78 + 0.17 * ease; // se vuelve sólido al colapsar

      // Partículas separándose de la fuente.
      const d = ease * 3.2;
      this.pAlice.position.set(-d, 0.3 + 0.2 * Math.sin(p * 6), 0.5);
      this.pBob.position.set(d, 0.3 + 0.2 * Math.sin(p * 6 + 1), 0.5);
      this.pAlice.scale.setScalar(1 - 0.5 * ease);
      this.pBob.scale.setScalar(1 - 0.5 * ease);

      if (p >= 1) {
        this.state = "settled";
        this.pAlice.visible = false;
        this.pBob.visible = false;
        if (this._rollResolve) this._rollResolve();
      }
    } else if (this.state === "settled") {
      // Quieto, sólido, con un leve balanceo.
      this.die.rotation.y += dt * 0.08;
    }

    this.controls.update();
    this.composer.render();
  };

  reset() {
    this.state = "idle";
    this.body.material.opacity = 0.85;
  }

  dispose() {
    cancelAnimationFrame(this._raf);
    window.removeEventListener("resize", this._onResize);
    this.renderer.dispose();
    if (this.renderer.domElement.parentNode) {
      this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
    }
  }
}
