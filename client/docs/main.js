/**
 * MoMask Team 2 — independent Mixamo Xbot and MoMask BVH viewers.
 * Intentional scope: generated BVH remains a SKELETON. Retargeting onto Xbot
 * is a separate server-side milestone and is NOT performed here.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { BVHLoader } from 'three/addons/loaders/BVHLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const SPACE = 'pgarces/MoMask-Team2';
const ASSET_BASE = new URL('./assets/', import.meta.url);
const $ = (id) => document.getElementById(id);
const now = () => performance.now();
const seconds = (ms) => `${(ms / 1000).toFixed(2)} s`;
const STORE_KEY = 'momask_team2_latency_v1';
let measurements = [];
try { measurements = JSON.parse(localStorage.getItem(STORE_KEY) || '[]'); if (!Array.isArray(measurements)) measurements = []; }
catch { measurements = []; }
let appPromise = null;
let busy = false;
let generationTick = null;

function state(badge, label, type = '') {
  const node = $(badge);
  node.className = `status-chip ${type}`;
  node.innerHTML = '<span class="status-dot"></span>';
  node.append(document.createTextNode(label));
}
function activity(message, isError = false, elapsed = '') {
  $('activity-text').textContent = message;
  $('activity-clock').textContent = elapsed;
  document.querySelector('.activity-dot').classList.toggle('error', isError);
}
function apiState(message, kind = '') {
  $('api-state').textContent = message;
  $('api-dot').className = `dot ${kind}`;
}
function setBusy(value) {
  busy = value;
  $('generate-button').disabled = value;
  $('button-label').textContent = value ? 'Generating…' : 'Generate motion';
  $('button-icon').textContent = value ? '◌' : '✦';
  $('button-icon').classList.toggle('spinning', value);
  $('sample-walk').disabled = value;
  $('sample-wave').disabled = value;
}
function getClient() {
  if (!appPromise) {
    apiState('Connecting to Space…');
    appPromise = import('https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js')
      .then(({ Client }) => Client.connect(SPACE))
      .then((client) => { apiState('Space connected', 'connected'); return client; })
      .catch((error) => { appPromise = null; apiState('Space unavailable', 'error'); throw error; });
  }
  return appPromise;
}

function makeViewer(id, accent) {
  const host = $(id);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.05, 70);
  camera.position.set(2.75, 1.9, 3.8);
  const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true, powerPreference:'high-performance'});
  renderer.setClearColor('#100c21', 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.4;
  host.appendChild(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xdad8ff, 0x594679, 2.15));
  const key = new THREE.DirectionalLight(0xe2d9ff, 3.2);
  key.position.set(-3,7,5); key.castShadow=true;
  key.shadow.mapSize.set(1024,1024);
  key.shadow.camera.left=-5;key.shadow.camera.right=5;key.shadow.camera.top=5;key.shadow.camera.bottom=-5;
  key.shadow.bias=-0.001; scene.add(key);
  const fill = new THREE.DirectionalLight(new THREE.Color(accent), 2.1);
  fill.position.set(3,3,-3); scene.add(fill);
  const floor = new THREE.Mesh(new THREE.CircleGeometry(2.6,90), new THREE.MeshStandardMaterial({color:0x231936,roughness:1,transparent:true,opacity:.8}));
  floor.rotation.x=-Math.PI/2;floor.position.y=-.02;floor.receiveShadow=true;scene.add(floor);
  const ring = new THREE.Mesh(new THREE.RingGeometry(1.14,1.15,100), new THREE.MeshBasicMaterial({color:new THREE.Color(accent),transparent:true,opacity:.26,side:THREE.DoubleSide}));
  ring.rotation.x=-Math.PI/2;ring.position.y=.004;scene.add(ring);
  const grid = new THREE.GridHelper(5.0, 16, new THREE.Color(accent), new THREE.Color(0x5b4b7a));
  grid.position.y=-.012;grid.material.transparent=true;grid.material.opacity=.11;scene.add(grid);
  const controls = new OrbitControls(camera,renderer.domElement);
  controls.enableDamping=true; controls.dampingFactor=.07; controls.minDistance=1.7; controls.maxDistance=12;
  controls.maxPolarAngle=Math.PI/2.07;
  controls.target.set(0,1.03,0);controls.update();
  const resize = () => { const w=host.clientWidth,h=host.clientHeight;if(w&&h){camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);} };
  const observer = new ResizeObserver(resize); observer.observe(host);resize();
  return {scene,camera,renderer,controls,resize,root:null,mixer:null,playing:true};
}

const character = makeViewer('xbot-stage','#68e8dd');
const motion = makeViewer('motion-stage','#b58bff');
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(),.065);
  for (const view of [character,motion]) {
    if (view.playing && view.mixer) view.mixer.update(dt);
    view.controls.update();
    view.renderer.render(view.scene,view.camera);
  }
}
animate();

function setCamera(view,height) {
  // 2–3 m human-scale characters, framed at their actual height.
  const h = Math.max(1,Math.min(4,height));
  view.controls.target.set(0,h*.53,0);
  const distance = Math.max(2.9,h*1.75);
  view.camera.position.set(distance*.61,h*.75,distance*.85);
  view.controls.update();
}

async function loadXbot() {
  try {
    const gltf = await new GLTFLoader().loadAsync(new URL('character/Xbot.glb',ASSET_BASE).href);
    const model = gltf.scene;
    model.traverse((child) => { if (child.isMesh) {child.castShadow=true;child.receiveShadow=true;child.frustumCulled=false;} });
    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const factor = size.y > 0 ? 2.1 / size.y : 1;
    model.scale.multiplyScalar(factor);
    const adjusted = new THREE.Box3().setFromObject(model);
    const mid = adjusted.getCenter(new THREE.Vector3());
    // Put feet on y=0, horizontally center the avatar without changing animation tracks.
    const display = new THREE.Group();
    display.position.set(-mid.x, -adjusted.min.y, -mid.z);
    display.add(model);
    character.scene.add(display);
    character.root = display;
    const walk = gltf.animations.find((c)=>c.name.toLowerCase()==='walk');
    if (!walk) throw new Error(`Xbot is missing a walk clip. Found: ${gltf.animations.map(c=>c.name).join(', ')}`);
    character.mixer = new THREE.AnimationMixer(model);
    character.mixer.clipAction(walk).setLoop(THREE.LoopRepeat,Infinity).play();
    character.mixer.update(0);
    $('xbot-clip').textContent = walk.name;
    $('xbot-duration').textContent = `${walk.duration.toFixed(1)} s`;
    setCamera(character, adjusted.getSize(new THREE.Vector3()).y);
    state('xbot-badge','Playing · built-in walk','success');
    $('xbot-boot').classList.add('hidden');
  } catch (error) {
    console.error('Xbot loading failed', error);
    $('xbot-boot').textContent=`Xbot failed to load: ${error.message}`;
    state('xbot-badge','Asset error','error');
  }
}

const bvhLoader = new BVHLoader();
// A normal BVH has one root. Both the offline files and /generate output follow this format.
function playBVH(text, description, isLive) {
  const loaded = bvhLoader.parse(text);
  if (!loaded.clip || !loaded.skeleton?.bones?.length) throw new Error('BVH has no playable clip or bones.');
  if (motion.mixer) motion.mixer.stopAllAction();
  if (motion.helper) {motion.scene.remove(motion.helper);motion.helper.dispose();motion.helper.geometry?.dispose?.();}
  if (motion.root) motion.scene.remove(motion.root);
  const skeletonRoot = loaded.skeleton.bones[0];
  const stage = new THREE.Group();
  stage.add(skeletonRoot);
  motion.scene.add(stage);
  motion.root = stage;
  motion.mixer = new THREE.AnimationMixer(skeletonRoot);
  motion.mixer.clipAction(loaded.clip).setLoop(THREE.LoopRepeat,Infinity).play();
  motion.mixer.setTime(0);
  stage.updateMatrixWorld(true);
  const bounds = new THREE.Box3();
  const world = new THREE.Vector3();
  for (const b of loaded.skeleton.bones) {b.getWorldPosition(world);bounds.expandByPoint(world);}
  if (bounds.isEmpty()) throw new Error('BVH skeleton contains no valid joint positions.');
  const dims = bounds.getSize(new THREE.Vector3());
  // Generated HumanML3D BVH is measured in meters; scale modestly only if unusually sized.
  const factor = dims.y > 0 ? 2.1/dims.y : 1;
  const center = bounds.getCenter(new THREE.Vector3());
  stage.scale.setScalar(factor);
  stage.position.set(-center.x*factor,-bounds.min.y*factor,-center.z*factor);
  stage.updateMatrixWorld(true);
  const helper = new THREE.SkeletonHelper(skeletonRoot);
  helper.setColors(0xb48dff, 0x65e5ed);
  helper.material.depthTest=false;
  helper.material.transparent=true;
  helper.material.opacity=1;
  motion.helper=helper;
  motion.scene.add(helper);
  // helper references the animated bone root, which is owned by the stage group.
  setCamera(motion,dims.y*factor);
  motion.playing=true;
  $('motion-toggle').textContent='Ⅱ';
  $('motion-toggle').setAttribute('aria-label','Pause skeleton animation');
  $('motion-boot').classList.add('hidden');
  $('motion-source').textContent=description;
  $('motion-duration').textContent=`${loaded.clip.duration.toFixed(1)} s`;
  state('motion-badge',isLive?'Playing · API result':'Playing · offline sample','success');
  return loaded;
}

async function loadSample(name) {
  if (busy) return;
  const label = name==='walk'?'Local walk.bvh':'Local wave.bvh';
  try {
    state('motion-badge','Loading sample…');
    const response=await fetch(new URL(`motions/${name}.bvh`,ASSET_BASE));
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    playBVH(await response.text(),label,false);
    activity(`${label} playing. This is an offline sample, not a live API result.`);
  }catch(error){activity(`Could not load sample: ${error.message}`,true);state('motion-badge','Sample error','error');$('motion-boot').textContent=`Cannot load ${label}. Serve with python3 -m http.server.`;}
}

function showStats(stats) {
  let content=stats;
  if(typeof content==='string') {try{content=JSON.parse(content);}catch{/* text remains */}}
  $('stats-tag').textContent='Live API output';
  const container=$('server-stats');container.replaceChildren();
  if (content && typeof content==='object' && !Array.isArray(content)) {
    const dl=document.createElement('dl');dl.className='stats-table';
    for(const [key,value] of Object.entries(content)) {
      const dt=document.createElement('dt'),dd=document.createElement('dd');
      dt.textContent=key.replaceAll('_',' ');
      dd.textContent=typeof value==='object'?JSON.stringify(value):String(value);
      dl.append(dt,dd);
    }
    container.append(dl);
  } else {container.textContent=content==null?'No stats returned.':String(content);}
}
function renderHistory() {
  const tbody=$('history-rows');tbody.replaceChildren();
  if(!measurements.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=6;td.className='empty-row';td.textContent='Generate a motion to record your first live run.';tr.append(td);tbody.append(tr);return;}
  measurements.slice().reverse().forEach((item,i)=>{
    const tr=document.createElement('tr');
    const cells=[String(measurements.length-i),item.prompt,`${item.frames} / ${item.seed}`,seconds(item.apiMs),seconds(item.bvhMs),seconds(item.totalMs)];
    cells.forEach((value,j)=>{const td=document.createElement('td');if(j===3){const s=document.createElement('span');s.className='api-time';s.textContent=value;td.append(s);}else td.textContent=value;tr.append(td);});
    tbody.append(tr);
  });
}
function logRun(record) {
  measurements.push(record);
  try {localStorage.setItem(STORE_KEY,JSON.stringify(measurements));}catch(e){console.warn('Cannot persist run history:',e);}
  renderHistory();
}
const csvEscape=(v)=>`"${String(v??'').replaceAll('"','""')}"`;
function exportCSV(){
  const headings=['ISO time','Prompt','Frames','Seed','API round trip ms','BVH download plus parse ms','End to end to playback ms','BVH bytes','MP4 URL'];
  const cols=['at','prompt','frames','seed','apiMs','bvhMs','totalMs','bvhBytes','mp4Url'];
  const csv=[headings.map(csvEscape).join(','),...measurements.map(x=>cols.map(k=>csvEscape(x[k])).join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='momask-client-roundtrips.csv';a.click();URL.revokeObjectURL(url);
}
function getFileUrl(obj) {if(typeof obj==='string')return obj;return obj?.url??obj?.path??null;}
async function generate(event) {
  event.preventDefault();if(busy)return;
  const prompt=$('prompt').value.trim();
  const frames=Number($('frames').value),seed=Number($('seed').value);
  if(!prompt){activity('Enter a motion prompt.',true);return;}
  if(!Number.isInteger(frames)||frames<0||frames>1000||!Number.isInteger(seed)||seed<0||seed>2147483647){activity('Use valid integer frames (0–1000) and seed (0–2147483647).',true);return;}
  setBusy(true);state('motion-badge','Generating…');
  $('mp4-link').hidden=true;
  const clickAt=now();
  generationTick=setInterval(()=>activity('Generating… waiting for model, conversion, render and transfer.',false,seconds(now()-clickAt)),160);
  try{
    const app=await getClient();
    // Exact /generate API round trip: do not mix one-time Client.connect overhead into it.
    const startedAt=now();
    const result=await app.predict('/generate',{text:prompt,length_frames:frames,seed});
    const apiMs=now()-startedAt;
    const data=result?.data;
    if(!Array.isArray(data)||data.length<3)throw new Error('Unexpected API response: expected [BVH, MP4, stats].');
    const [bvh,preview,stats]=data;
    const bvhUrl=getFileUrl(bvh);if(!bvhUrl)throw new Error('API did not return a BVH file URL.');
    const fileStart=now();
    const response=await fetch(bvhUrl);
    if(!response.ok)throw new Error(`BVH download failed: HTTP ${response.status}`);
    const bvhText=await response.text();
    playBVH(bvhText,`Live /generate · ${prompt.slice(0,34)}`,true);
    const bvhMs=now()-fileStart;
    const totalMs=now()-clickAt;
    showStats(stats);
    $('latency').textContent=(apiMs/1000).toFixed(2);
    $('parse-time').textContent=seconds(bvhMs);
    $('total-time').textContent=seconds(totalMs);
    const mp4Url=getFileUrl(preview);
    $('mp4-link').hidden=!mp4Url;
    if(mp4Url)$('mp4-link').href=mp4Url;
    logRun({at:new Date().toISOString(),prompt,frames,seed,apiMs,bvhMs,totalMs,bvhBytes:new Blob([bvhText]).size,mp4Url:mp4Url||''});
    activity(`Motion ready. API: ${seconds(apiMs)} · full click-to-play: ${seconds(totalMs)}.`);
  }catch(error){console.error('MoMask generation failed:',error);activity(`Generation failed: ${error.message}`,true);state('motion-badge','Request failed','error');}
  finally {clearInterval(generationTick);generationTick=null;setBusy(false);$('activity-clock').textContent='';}
}
function toggle(view,button) {
  view.playing=!view.playing;
  button.textContent=view.playing?'Ⅱ':'▶';
  button.setAttribute('aria-label',`${view.playing?'Pause':'Resume'} ${view===character?'Xbot':'skeleton'} animation`);
}
$('xbot-toggle').addEventListener('click',()=>toggle(character,$('xbot-toggle')));
$('motion-toggle').addEventListener('click',()=>toggle(motion,$('motion-toggle')));
$('sample-walk').addEventListener('click',()=>loadSample('walk'));
$('sample-wave').addEventListener('click',()=>loadSample('wave'));
$('generate-form').addEventListener('submit',generate);
for(const button of document.querySelectorAll('[data-prompt]'))button.addEventListener('click',()=>{$('prompt').value=button.dataset.prompt;$('prompt').focus();});
$('export-button').addEventListener('click',exportCSV);
$('clear-button').addEventListener('click',()=>{if(!confirm('Clear the saved measurement log?'))return;measurements=[];try{localStorage.removeItem(STORE_KEY);}catch{}renderHistory();});
renderHistory();
loadXbot();
loadSample('walk');
