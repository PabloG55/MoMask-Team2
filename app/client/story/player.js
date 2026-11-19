// Plays a show from the /show API. Everything is a function of the time t, so any frame can be
// drawn with renderAt(t), for capture as well as in real time.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const HERE = new URL('./', import.meta.url);
const DEG = Math.PI / 180;
const FOV = 32;
const SAMPLE = 0.1; // seconds between samples of where each character's hips and head are

export const COLORS = {
  Astronaut: '#f08a24', CoolAlien: '#5e9c76', DinoKid: '#3fa34d', Froggy: '#2f9e6e', Hugo: '#8a5cc7',
  Jimmy: '#e0672f', Kyle: '#d23c3c', LilBro: '#4cae4c', Polybot: '#2d9c8a', Teddy: '#a0683a',
};

// Background (top, bottom), hemisphere light, key light, fog, and a warm spot at night.
const LIGHTS = {
  studio: { sky: ['#f4f4ef', '#f4f4ef'], hemi: ['#ffffff', '#d9d9d0', 2.3], key: ['#ffffff', 1.5, [2, 9, 7]], fog: null },
  day: { sky: ['#62b4ff', '#d9f0ff'], hemi: ['#d8efff', '#7d9b5c', 1.3], key: ['#fff3dd', 2.6, [6, 10, 7]], fog: [30, 95] },
  sunset: { sky: ['#4f62a8', '#ffb37a'], hemi: ['#ffd1a6', '#5a4262', 1.0], key: ['#ffa866', 2.8, [-9, 3.6, 6]], fog: [24, 85] },
  night: { sky: ['#040918', '#1c2b58'], hemi: ['#3b4f8c', '#0c0f1c', 0.75], key: ['#a9c0ff', 1.2, [-5, 9, 6]], fog: [20, 75],
           spot: ['#ffe4ba', 45] },
};

function gradient(top, bottom) {
  const c = document.createElement('canvas');
  c.width = 4; c.height = 256;
  const g = c.getContext('2d');
  const grad = g.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, top); grad.addColorStop(1, bottom);
  g.fillStyle = grad; g.fillRect(0, 0, 4, 256);
  const texture = new THREE.CanvasTexture(c);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function random(seed) { // small deterministic generator, so blinks and stars are the same every time
  let s = seed >>> 0 || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function hash(text) {
  let h = 2166136261;
  for (const ch of text) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
}

export class ShowPlayer {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.camera = new THREE.PerspectiveCamera(FOV, 16 / 9, 0.05, 400);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enabled = false;
    this.freeCamera = false;
    this.loader = new GLTFLoader();
    this.loader.register((parser) => new VRMLoaderPlugin(parser));
    this.vrmCache = new Map();
    this.propCache = new Map();
    this.cast = [];
    this.timeline = null;
    this.lastT = 0;
  }


  async load(timeline, files) {
    // files: { motion: {name: url}, voices: url }
    // Nothing renders until the whole show is in: a half-loaded show has no shots yet.
    this.ready = false;
    this.timeline = timeline;
    this.scene = new THREE.Scene();
    const set = await (await fetch(new URL(`sets/${timeline.set}/set.json`, HERE))).json();
    this.set = set;
    await this.buildSet(set, timeline.light || set.light);
    this.cast = [];
    for (const [i, member] of timeline.cast.entries()) {
      this.cast.push(await this.addCharacter(member, files.motion[member.name], i));
    }
    this.sampleTracks();
    this.planShots();
    this.blinks = Object.fromEntries(this.cast.map((c) => [c.name, this.blinkTimes(c.name)]));
    this.lastT = 0;
    this.ready = true;
    this.resize();
  }

  async buildSet(set, lightName) {
    const light = LIGHTS[lightName] || LIGHTS.day;
    const scene = this.scene;
    const background = set.background ? [set.background, set.background] : light.sky;
    scene.background = gradient(...background);
    if (light.fog && !set.stars) scene.fog = new THREE.Fog(background[1], ...light.fog);

    scene.add(new THREE.HemisphereLight(...light.hemi));
    const key = new THREE.DirectionalLight(light.key[0], light.key[1]);
    key.position.set(...light.key[2]);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 0.5, far: 40 });
    key.shadow.bias = -0.0004;
    key.shadow.radius = 4;
    scene.add(key);
    if (light.spot) {
      const spot = new THREE.SpotLight(light.spot[0], light.spot[1], 0, 0.75, 0.8, 1.2);
      spot.position.set(0, 6, 5);
      spot.target.position.set(0, 0.8, 0);
      scene.add(spot, spot.target);
    }

    const g = set.ground;
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(g.size, g.size),
      g.shadowOnly ? new THREE.ShadowMaterial({ opacity: 0.16 }) : new THREE.MeshLambertMaterial({ color: g.color }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    if (set.water) {
      const water = new THREE.Mesh(new THREE.PlaneGeometry(300, 150),
        new THREE.MeshPhongMaterial({ color: set.water.color, shininess: 60, specular: 0x88bbdd }));
      water.rotation.x = -Math.PI / 2;
      water.position.set(0, 0.03, set.water.z - 75);
      scene.add(water);
    }
    if (set.stars) {
      const rand = random(7), points = [];
      for (let i = 0; i < 1600; i++) {
        const a = rand() * Math.PI * 2, y = 0.04 + rand() * 0.96, r = Math.sqrt(1 - y * y);
        points.push(150 * r * Math.cos(a), 150 * y, 150 * r * Math.sin(a));
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
      scene.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xffffff, size: 0.55, fog: false })));
    }
    if (set.planet) {
      const planet = new THREE.Mesh(new THREE.SphereGeometry(set.planet.radius, 48, 32),
        new THREE.MeshLambertMaterial({ color: set.planet.color, emissive: set.planet.color, emissiveIntensity: 0.35 }));
      planet.position.set(...set.planet.position);
      scene.add(planet);
    }

    const base = new URL(`sets/${set.id}/`, HERE);
    await Promise.all(set.props.map(async (prop) => {
      const url = new URL(prop.model, base).href;
      if (!this.propCache.has(url)) this.propCache.set(url, this.loader.loadAsync(url));
      const model = (await this.propCache.get(url)).scene.clone(true);
      // Kenney's pivots sit at a corner: centre the footprint and stand it on the ground.
      const box = new THREE.Box3().setFromObject(model);
      const centre = box.getCenter(new THREE.Vector3());
      model.position.set(-centre.x, -box.min.y, -centre.z);
      model.traverse((o) => {
        if (!o.isMesh) return;
        o.castShadow = true; o.receiveShadow = true;
        // Kenney's materials say metalness 1; with nothing to reflect, metal renders black.
        for (const m of [].concat(o.material)) if ('metalness' in m) { m.metalness = 0; m.roughness = 0.9; }
      });
      const holder = new THREE.Group();
      holder.add(model);
      holder.scale.setScalar(prop.scale);
      holder.rotation.y = (prop.rotationY || 0) * DEG;
      holder.position.set(...prop.position);
      scene.add(holder);
    }));
  }

  async addCharacter(member, motionUrl, index) {
    const url = new URL(`characters/${member.name}.vrm`, HERE).href;
    // A fresh copy each time: a VRM can't be cloned, and the cache only saves the download.
    if (!this.vrmCache.has(url)) this.vrmCache.set(url, fetch(url).then((r) => r.arrayBuffer()));
    const gltf = await this.loader.parseAsync((await this.vrmCache.get(url)).slice(0), url);
    const vrm = gltf.userData.vrm;
    VRMUtils.rotateVRM0(vrm); // VRM 0.x faces -Z; turn it to face the audience
    vrm.humanoid.autoUpdateHumanBones = false; // the motion drives the raw bones directly
    vrm.scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
    vrm.scene.position.set(member.x, 0, 0);
    this.scene.add(vrm.scene);

    const height = new THREE.Box3().setFromObject(vrm.scene).getSize(new THREE.Vector3()).y;
    const motion = await this.loader.loadAsync(motionUrl);
    const mixer = new THREE.AnimationMixer(vrm.scene);
    const clip = motion.animations[0];
    const action = mixer.clipAction(clip);
    action.play();
    mixer.setTime(0);

    const names = new Set(vrm.expressionManager?.expressions.map((e) => e.expressionName) || []);
    return {
      name: member.name, index, vrm, mixer, height, names, end: clip.duration - 1e-3,
      hips: vrm.humanoid.getRawBoneNode('hips'), head: vrm.humanoid.getRawBoneNode('head'),
      mouth: this.timeline.mouth?.[member.name],
    };
  }

  // Clamped here, not with clampWhenFinished: a finished action pauses and shows frame 0.
  pose(c, t) {
    c.mixer.setTime(Math.min(Math.max(t, 0), c.end));
  }

  // Hips and head over the whole show, so the camera frames any t the same way.
  sampleTracks() {
    const n = Math.ceil(this.timeline.duration / SAMPLE) + 1;
    const v = new THREE.Vector3();
    for (const c of this.cast) { c.hipsTrack = new Float32Array(n * 3); c.headTrack = new Float32Array(n * 3); }
    for (let i = 0; i < n; i++) {
      for (const c of this.cast) {
        this.pose(c, i * SAMPLE);
        c.vrm.scene.updateMatrixWorld(true);
        c.hips.getWorldPosition(v).toArray(c.hipsTrack, i * 3);
        c.head.getWorldPosition(v).toArray(c.headTrack, i * 3);
      }
    }
    for (const c of this.cast) this.pose(c, 0);
  }

  at(track, t) {
    const n = track.length / 3 - 1;
    const x = Math.min(Math.max(t / SAMPLE, 0), n), i = Math.min(Math.floor(x), n - 1), f = x - i;
    return new THREE.Vector3(
      track[i * 3] * (1 - f) + track[i * 3 + 3] * f,
      track[i * 3 + 1] * (1 - f) + track[i * 3 + 4] * f,
      track[i * 3 + 2] * (1 - f) + track[i * 3 + 5] * f,
    );
  }

  mean(track, a, b) {
    const sum = new THREE.Vector3();
    let k = 0;
    for (let t = a; t <= b + 1e-6; t += SAMPLE / 2, k++) sum.add(this.at(track, t));
    return sum.divideScalar(Math.max(k, 1));
  }

  smooth(track, t, width = 0.6) {
    const sum = new THREE.Vector3();
    let w = 0;
    for (let d = -2 * width; d <= 2 * width + 1e-6; d += SAMPLE) {
      const k = Math.exp(-(d * d) / (2 * width * width));
      sum.addScaledVector(this.at(track, t + d), k);
      w += k;
    }
    return sum.divideScalar(w);
  }


  planShots() {
    const byName = Object.fromEntries(this.cast.map((c) => [c.name, c]));
    this.shots = (this.timeline.shots?.length ? this.timeline.shots : [{ start: 0, end: this.timeline.duration, type: 'wide' }])
      .map((shot) => {
        const actor = byName[shot.target] || null;
        const hips = actor ? this.mean(actor.hipsTrack, shot.start, shot.end) : null;
        const head = actor ? this.mean(actor.headTrack, shot.start, shot.end) : null;
        const everyone = this.cast.map((c) => this.mean(c.hipsTrack, shot.start, shot.end));
        return { ...shot, actor: shot.type === 'wide' ? null : actor, hips, head, everyone };
      });
  }

  shotAt(t) {
    return this.shots.find((s) => t >= s.start && t < s.end) || this.shots[this.shots.length - 1];
  }

  frame(centre, halfH, halfW, az, el) {
    const tanV = Math.tan((FOV / 2) * DEG), tanH = tanV * this.camera.aspect;
    const distance = Math.max(halfH / tanV, halfW / tanH);
    const dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
    const position = centre.clone().addScaledVector(dir, distance);
    position.y = Math.max(position.y, 0.12);
    return { position, target: centre };
  }

  cameraAt(t) {
    const shot = this.shotAt(t);
    const p = (t - shot.start) / Math.max(shot.end - shot.start, 0.01);
    const push = 1 - 0.05 * p; // a slow push-in, so a held shot doesn't look frozen
    const c = shot.actor;
    if (!c) {
      let minX = Infinity, maxX = -Infinity, z = 0, tall = 0;
      shot.everyone.forEach((h, i) => {
        const half = 0.3 * this.cast[i].height + 0.25;
        minX = Math.min(minX, h.x - half); maxX = Math.max(maxX, h.x + half);
        z += h.z / this.cast.length; tall = Math.max(tall, this.cast[i].height);
      });
      // Loose enough to show the set: this shot says where we are.
      return this.frame(new THREE.Vector3((minX + maxX) / 2, tall * 0.62, z),
        (tall * 0.78 + 0.45) * push, ((maxX - minX) / 2 + 1.0) * push, 0, 10 * DEG);
    }
    const H = c.height, side = shot.hips.x < 0 ? 1 : -1;
    const body = (hips) => new THREE.Vector3(hips.x, H * 0.5, hips.z);
    switch (shot.type) {
      case 'close': {
        const top = H, neck = shot.head.y;
        const centre = new THREE.Vector3(shot.head.x, (neck + top) / 2 - 0.02 * H, shot.head.z);
        return this.frame(centre, ((top - neck) / 2 + 0.18 * H + 0.1) * push, 0.3 * push, side * 18 * DEG, 3 * DEG);
      }
      case 'low':
        return this.frame(new THREE.Vector3(shot.hips.x, H * 0.55, shot.hips.z), (H * 0.66 + 0.15) * push,
          (H * 0.42 + 0.3) * push, -side * 22 * DEG, -14 * DEG);
      case 'high':
        return this.frame(new THREE.Vector3(shot.hips.x, H * 0.4, shot.hips.z), (H * 0.7 + 0.2) * push,
          (H * 0.45 + 0.3) * push, side * 10 * DEG, 38 * DEG);
      case 'orbit':
        return this.frame(body(shot.hips), H * 0.62 + 0.15, H * 0.45 + 0.35,
          (-35 + 28 * (t - shot.start)) * DEG, 7 * DEG);
      case 'follow':
        return this.frame(body(this.smooth(c.hipsTrack, t)), H * 0.62 + 0.15, H * 0.45 + 0.35, 20 * DEG, 8 * DEG);
      default: // medium
        return this.frame(body(shot.hips), (H * 0.62 + 0.12) * push, (H * 0.45 + 0.3) * push, side * 14 * DEG, 6 * DEG);
    }
  }

  setFreeCamera(on) {
    this.freeCamera = on;
    this.controls.enabled = on;
    if (on) {
      const { target } = this.cameraAt(this.lastT);
      this.controls.target.copy(target);
      this.controls.update();
    }
  }


  blinkTimes(name) {
    const rand = random(hash(name)), times = [];
    for (let t = 0.6 + rand() * 1.5; t < this.timeline.duration + 5; t += 2.2 + rand() * 2.6) times.push(t);
    return times;
  }

  face(c, t) {
    const em = c.vrm.expressionManager;
    if (!em) return;
    const m = c.mouth, i = m ? Math.floor(t * m.fps) : -1;
    for (const key of ['aa', 'ee', 'oh']) {
      if (c.names.has(key)) em.setValue(key, m && i >= 0 && i < m[key].length ? m[key][i] / 100 : 0);
    }
    let blink = 0;
    for (const b of this.blinks[c.name]) {
      if (t >= b && t < b + 0.16) { blink = Math.sin((Math.PI * (t - b)) / 0.16); break; }
      if (b > t) break;
    }
    if (c.names.has('blink')) em.setValue('blink', blink);
    else for (const key of ['blinkLeft', 'blinkRight']) if (c.names.has(key)) em.setValue(key, blink);
  }


  resize() {
    const w = this.canvas.clientWidth || this.canvas.width, h = this.canvas.clientHeight || this.canvas.height;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  renderAt(t) {
    if (!this.ready) return;
    const dt = Math.min(Math.max(t - this.lastT, 0), 0.1);
    for (const c of this.cast) {
      this.pose(c, t);
      this.face(c, t);
      c.vrm.update(dt); // expressions and the springy bits (hair, ears)
    }
    if (this.freeCamera) {
      this.controls.update();
    } else {
      const { position, target } = this.cameraAt(t);
      this.camera.position.copy(position);
      this.camera.lookAt(target);
    }
    this.renderer.render(this.scene, this.camera);
    this.lastT = t;
  }

  linesAt(t) {
    // A caption stays a moment after its line, but goes when the next line starts, so two
    // only share the screen when two voices really overlap.
    const lines = this.timeline?.lines || [];
    return lines.filter((l, i) => {
      const next = lines[i + 1];
      const until = Math.max(l.end, Math.min(l.end + 0.35, next ? next.start - 0.05 : Infinity));
      return t >= l.start - 0.05 && t < until;
    });
  }
}
