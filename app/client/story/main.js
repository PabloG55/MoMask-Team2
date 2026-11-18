// Test page for the /show API: play a saved show or ask the Space for a new one.
//   ?show=<folder>  play the timeline.json, <Name>.glb and voices.mp3 in that folder
//   ?space=<id|url> the Gradio Space (default pgarces/MoMask-Team2), e.g. http://127.0.0.1:7860
//   ?capture=1      just the picture, for recording frames with window.renderAt(t)

import { ShowPlayer, COLORS } from './player.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const capture = params.has('capture');
const player = new ShowPlayer($('view'));
const audio = $('voices');
let timeline = null, examples = [], playing = false, clockStart = 0, clockOffset = 0, lastSync = 0;

if (capture) document.body.classList.add('capture');
if (params.get('space')) $('space').value = params.get('space');

const slug = (name) => name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const kb = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(2)} MB` : `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`);
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

function status(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}

// Live requests can take 30+ seconds, especially after the Space wakes up.
// Show elapsed time rather than a countdown we cannot promise.
let busyMessage = '';
let requestStarted = null;
function drawBusy() {
  if (!busyMessage) return;
  const elapsed = requestStarted == null ? '' :
    ` · ${Math.floor((performance.now() - requestStarted) / 1000)}s elapsed`;
  $('busy-text').textContent = `${busyMessage}${elapsed}`;
}
function busy(text) {
  busyMessage = text;
  $('busy').hidden = !text;
  drawBusy();
}


// The picture runs on the page's clock and the voices follow it, so a stalled mp3 can't freeze it.
function now() {
  if (!playing) return clockOffset;
  return clockOffset + (performance.now() - clockStart) / 1000;
}

function keepVoicesInStep(t) {
  if (audio.paused || audio.ended || audio.readyState < 3 || t >= (audio.duration || Infinity)) return;
  const at = performance.now();
  if (Math.abs(audio.currentTime - t) > 0.25 && at - lastSync > 1000) { audio.currentTime = t; lastSync = at; }
}

function play(from = now()) {
  if (!timeline) return;
  if (from >= timeline.duration - 0.05) from = 0;
  clockOffset = from;
  clockStart = performance.now();
  playing = true;
  lastSync = performance.now();
  audio.currentTime = Math.min(from, audio.duration || from);
  audio.play().catch(() => {}); // a browser that blocks sound still plays the picture
  document.body.classList.add('playing');
}

function pause() {
  clockOffset = now();
  playing = false;
  audio.pause();
  document.body.classList.remove('playing');
}

function seek(t) {
  const was = playing;
  pause();
  clockOffset = t;
  if (was) play(t);
}


function overlay(t) {
  const card = $('titlecard');
  const fade = t < 1.6 ? 1 : Math.max(0, 1 - (t - 1.6) / 0.6);
  card.style.opacity = timeline ? fade : 0;

  const lines = player.linesAt(t);
  const html = lines.map((l) => {
    const name = l.who === 'narrator' ? '' :
      `<span class="who" style="--c:${COLORS[l.who] || '#555'}">${escape(l.who)}</span>`;
    return `<p class="${l.who === 'narrator' ? 'narrator' : 'character'}">${name}${escape(l.text)}</p>`;
  }).join('');
  if ($('subtitles').innerHTML !== html) $('subtitles').innerHTML = html;
}

function escape(text) {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function loop() {
  requestAnimationFrame(loop); // first, so one bad frame can't stop the show
  if (timeline && !capture) {
    let t = now();
    if (playing && t >= timeline.duration) { pause(); clockOffset = t = timeline.duration; }
    if (playing) keepVoicesInStep(t);
    player.renderAt(t);
    overlay(t);
    $('scrub').value = Math.round((t / timeline.duration) * 1000);
    $('clock').textContent = `${mmss(t)} / ${mmss(timeline.duration)}`;
  }
}


async function start(newTimeline, files) {
  pause();
  busy('Loading the set and the cast…');
  timeline = newTimeline;
  await player.load(timeline, files);
  audio.src = files.voices;
  $('title-text').textContent = timeline.title;
  $('empty').hidden = true;
  $('play').disabled = $('scrub').disabled = false;
  clockOffset = 0;
  player.renderAt(0);
  overlay(0);
  describe(timeline);
  busy('');
}

async function fromFolder(folder) {
  const base = new URL(folder.endsWith('/') ? folder : `${folder}/`, location.href);
  const response = await fetch(new URL('timeline.json', base));
  if (!response.ok) throw new Error(`No saved show at ${base.pathname}`);
  const t = await response.json();
  const motion = Object.fromEntries(t.cast.map((c) => [c.name, new URL(c.motion, base).href]));
  await start(t, { motion, voices: new URL('voices.mp3', base).href });
}

let client = null, clientFor = null;
async function live(story, seed) {
  const space = $('space').value.trim();
  if (!client || clientFor !== space) {
    busy('Connecting to the Space…');
    const { Client } = await import('https://cdn.jsdelivr.net/npm/@gradio/client@2.7.2/dist/index.min.js');
    client = await Client.connect(space);
    clientFor = space;
  }
  busy('MoMask is moving the characters…');
  const t0 = performance.now();
  const result = await client.predict('/show', { story, seed: Number(seed) || 0 });
  const [motions, voices, t] = result.data;
  const roundTrip = (performance.now() - t0) / 1000;
  const motion = {};
  for (const file of motions) {
    const name = (file.orig_name || file.path || file.url).split(/[\\/]/).pop().replace(/\.glb$/, '');
    motion[name] = file.url;
  }
  t.stats = { ...(t.stats || {}), round_trip_seconds: roundTrip };
  await start(t, { motion, voices: voices.url });
}

function describe(t) {
  const b = t.stats?.bytes || {};
  const sent = (b.motion_glb_gzip || 0) + (b.voices_mp3 || 0) + (b.timeline_json || 0);
  // The same show as 720p H.264 at 2.5 Mbit/s, for comparison.
  const video = (t.duration * 2.5e6) / 8;
  const rows = [
    ['Story in', b.story_text, 'what the user typed'],
    ['Motion, all characters', b.motion_glb_gzip, `.glb, gzip (${kb(b.motion_glb || 0)} raw)`],
    ['Voices', b.voices_mp3, 'mp3'],
    ['Timeline', b.timeline_json, 'lines, shots, mouths'],
  ];
  $('net').innerHTML = rows.map(([k, v, note]) =>
    `<div class="netrow"><span>${k}<small>${note}</small></span><b>${v ? kb(v) : '—'}</b></div>`).join('') +
    `<div class="netrow total"><span>Sent to the viewer</span><b>${kb(sent)}</b></div>` +
    `<div class="netrow video"><span>Same show as 720p video<small>H.264 at 2.5 Mbit/s</small></span><b>${kb(video)}</b></div>`;
  const s = t.stats?.seconds || {};
  const parts = [`planned by ${t.stats?.planner || '—'}`];
  if (s.total) parts.push(`made in ${s.total.toFixed(1)} s on the server`);
  if (t.stats?.round_trip_seconds) parts.push(`${t.stats.round_trip_seconds.toFixed(1)} s round trip`);
  $('net-note').textContent = `${(video / Math.max(sent, 1)).toFixed(0)}× less than the video. ${parts.join(', ')}.`;
  $('netcard').hidden = false;

  const steps = t.steps.map((s) =>
    `<li><span class="who" style="--c:${COLORS[s.actor] || '#555'}">${escape(s.actor)}</span>${escape(s.action.replace(/^a person /, ''))}<em>${escape(s.shot)}</em></li>`);
  const cast = t.cast.map((c) => escape(c.name)).join(', ');
  $('castlist').innerHTML = `<p class="where">${escape(t.set)} · ${escape(t.light)} light · ${cast}</p><ol>${steps.join('')}</ol>`;
  $('castcard').hidden = false;
}


function current() { return examples[Number($('example').value)] || null; }

async function init() {
  examples = await (await fetch('examples.json')).json();
  $('example').innerHTML = examples.map((e, i) => `<option value="${i}">${escape(e.name)}</option>`).join('') +
    '<option value="-1">Write my own…</option>';
  const fill = () => {
    const e = current();
    $('story').value = e ? JSON.stringify(e.show, null, 1) : '';
    $('saved').disabled = !e;
  };
  $('example').addEventListener('change', fill);
  fill();

  // Avoid concurrent asset loads: an in-flight live show and a saved one
  // should never both mutate the same player and scene.
  function lockLoading(locked) {
    $('make').disabled = locked;
    $('saved').disabled = locked || !current();
    $('example').disabled = locked;
  }
  $('saved').addEventListener('click', async () => {
    const e = current();
    if (!e) return;
    lockLoading(true);
    try {
      status('');
      await fromFolder(`demo/${e.slug || slug(e.name)}`);
      play(0);
      status('Saved show ready. This does not call the Space.');
    } catch (error) {
      status(error?.message || String(error), true);
    } finally {
      busy('');
      lockLoading(false);
    }
  });
  $('make').addEventListener('click', async () => {
    const story = $('story').value.trim();
    if (!story) { status('Write a story first.', true); return; }
    lockLoading(true);
    requestStarted = performance.now();
    const ticker = setInterval(drawBusy, 1000);
    try {
      status('');
      await live(story, $('seed').value);
      play(0);
      status('Made live by the Space.');
    } catch (error) {
      status(`${error?.message || String(error)} — You can still play a saved show.`, true);
    } finally {
      clearInterval(ticker);
      requestStarted = null;
      busy('');
      lockLoading(false);
    }
  });
  $('play').addEventListener('click', () => (playing ? pause() : play()));
  $('scrub').addEventListener('input', () => timeline && seek((($('scrub').value) / 1000) * timeline.duration));
  $('free').addEventListener('change', () => player.setFreeCamera($('free').checked));
  addEventListener('keydown', (e) => {
    if (e.code === 'Space' && e.target === document.body) { e.preventDefault(); playing ? pause() : play(); }
  });
  new ResizeObserver(() => { player.resize(); if (timeline && !playing) player.renderAt(clockOffset); }).observe($('screen'));
  requestAnimationFrame(loop);
}

if (capture) {
  window.renderAt = (t) => { player.renderAt(t); overlay(t); };
  window.duration = () => timeline?.duration || 0;
  window.player = player; // for checking a capture from the outside
  fromFolder(params.get('show'))
    .then(() => { document.body.dataset.ready = '1'; })
    .catch((error) => { document.body.dataset.error = error.message; console.error('[player]', error); });
} else {
  init().then(() => (params.get('show') ? fromFolder(params.get('show')) : null))
    .catch((error) => status(error.message, true));
}
