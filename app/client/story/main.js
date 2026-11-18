// Three-screen storyteller for /show: write → curtain/loading → play.
// ?demo=1 uses locally saved versions of the three example ideas (no Space request).
// ?space=<id|url> overrides the backend for development; never exposed in the UI.
// ?show=<folder> opens a local saved show; ?capture=1 keeps frame-capture compatibility.

import { ShowPlayer, COLORS } from './player.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const capture = params.has('capture');
const demo = params.get('demo') === '1';
const space = params.get('space') || 'pgarces/MoMask-Team2';
const seed = 42;
const player = new ShowPlayer($('view'));
const audio = $('voices');
let timeline = null;
let examples = [];
let playing = false;
let clockStart = 0, clockOffset = 0, lastSync = 0;
let loadingTimer = null;
let loadingStarted = 0;
let loadingMessage = 0;
let locked = false;

const loadingLines = [
  'Writing the script…',
  'Casting the characters…',
  'Moving the characters…',
  'Recording the voices…',
  'Getting the stage ready…',
];

if (capture) document.body.classList.add('capture');

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const escapeHTML = (text) => String(text ?? '').replace(/[&<>\"]/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
}[c]));

function showStep(which) {
  // Keep the player laid out underneath the loading curtain, so three.js can size its canvas.
  $('write-step').hidden = which !== 'write';
  $('watch-step').hidden = which === 'write';
  $('loading-step').hidden = which !== 'loading';
  $('watch-step').inert = which === 'loading';
  if (which === 'watch' || which === 'loading') {
    requestAnimationFrame(() => {
      player.resize();
      if (timeline) player.renderAt(Math.min(clockOffset, timeline.duration));
    });
  }
}

function status(message, error = false) {
  const el = $('status');
  el.textContent = message;
  el.classList.toggle('error', error);
}

function tickLoading() {
  const seconds = Math.floor((performance.now() - loadingStarted) / 1000);
  $('elapsed').textContent = `${seconds} ${seconds === 1 ? 'second' : 'seconds'} elapsed`;
  const nextMessage = Math.floor(seconds / 7) % loadingLines.length;
  if (loadingMessage !== nextMessage) {
    loadingMessage = nextMessage;
    $('loading-line').textContent = loadingLines[loadingMessage];
  }
}

function beginLoading() {
  loadingStarted = performance.now();
  loadingMessage = 0;
  $('loading-line').textContent = loadingLines[0];
  $('elapsed').textContent = '0 seconds elapsed';
  showStep('loading');
  clearInterval(loadingTimer);
  loadingTimer = setInterval(tickLoading, 1000);
}

function endLoading() {
  clearInterval(loadingTimer);
  loadingTimer = null;
}

function setLoadingMessage(message) {
  $('loading-line').textContent = message;
  // The normal rotating messages are paused during the final local asset load.
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => {
    const seconds = Math.floor((performance.now() - loadingStarted) / 1000);
    $('elapsed').textContent = `${seconds} ${seconds === 1 ? 'second' : 'seconds'} elapsed`;
  }, 1000);
}

// The 3D show runs on a page clock; the audio follows without stopping the picture.
function now() { return playing ? clockOffset + (performance.now() - clockStart) / 1000 : clockOffset; }

function keepVoicesInStep(t) {
  if (audio.paused || audio.ended || audio.readyState < 3 || t >= (audio.duration || Infinity)) return;
  const at = performance.now();
  if (Math.abs(audio.currentTime - t) > 0.25 && at - lastSync > 1000) {
    audio.currentTime = t;
    lastSync = at;
  }
}

function play(from = now()) {
  if (!timeline) return;
  if (from >= timeline.duration - 0.05) from = 0;
  clockOffset = from;
  clockStart = performance.now();
  lastSync = performance.now();
  playing = true;
  audio.currentTime = Math.min(from, audio.duration || from);
  audio.play().catch(() => {
    // After a long generation some browsers require a fresh click for sound.
    // Pause the picture rather than silently presenting a voiceless show.
    if (!playing) return;
    pause();
    $('watch-note').textContent += ' Tap Play to begin with sound.';
  });
  document.body.classList.add('playing');
  $('play').setAttribute('aria-label', 'Pause');
}

function pause() {
  clockOffset = now();
  playing = false;
  audio.pause();
  document.body.classList.remove('playing');
  $('play').setAttribute('aria-label', 'Play');
}

function seek(t) {
  const was = playing;
  pause();
  clockOffset = t;
  if (was) play(t);
}

function overlay(t) {
  const fade = t < 1.6 ? 1 : Math.max(0, 1 - (t - 1.6) / 0.6);
  $('titlecard').style.opacity = timeline ? fade : 0;
  const html = player.linesAt(t).map((l) => {
    const name = l.who === 'narrator' ? '' :
      `<span class="who" style="--c:${COLORS[l.who] || '#555'}">${escapeHTML(l.who)}</span>`;
    return `<p class="${l.who === 'narrator' ? 'narrator' : 'character'}">${name}${escapeHTML(l.text)}</p>`;
  }).join('');
  if ($('subtitles').innerHTML !== html) $('subtitles').innerHTML = html;
}

function loop() {
  requestAnimationFrame(loop);
  if (!timeline || capture || $('watch-step').hidden || !$('loading-step').hidden) return;
  let t = now();
  if (playing && t >= timeline.duration) { pause(); clockOffset = t = timeline.duration; }
  if (playing) keepVoicesInStep(t);
  player.renderAt(t);
  overlay(t);
  $('scrub').value = Math.round((t / timeline.duration) * 1000);
  $('clock').textContent = `${mmss(t)} / ${mmss(timeline.duration)}`;
}

async function start(newTimeline, files) {
  pause();
  timeline = null;
  setLoadingMessage('Opening the curtains…');
  await player.load(newTimeline, files);
  timeline = newTimeline;
  audio.src = files.voices;
  $('title-text').textContent = newTimeline.title;
  $('show-title').textContent = newTimeline.title;
  $('play').disabled = $('scrub').disabled = false;
  clockOffset = 0;
  player.renderAt(0);
  overlay(0);
}

async function fromFolder(folder) {
  const base = new URL(folder.endsWith('/') ? folder : `${folder}/`, location.href);
  const response = await fetch(new URL('timeline.json', base));
  if (!response.ok) throw new Error(`Could not load the saved show (${response.status}).`);
  const t = await response.json();
  const motion = Object.fromEntries(t.cast.map((c) => [c.name, new URL(c.motion, base).href]));
  await start(t, { motion, voices: new URL('voices.mp3', base).href });
}

let client = null;
async function live(story) {
  if (!client) {
    const { Client } = await import('https://cdn.jsdelivr.net/npm/@gradio/client@2.7.2/dist/index.min.js');
    client = await Client.connect(space);
  }
  const result = await client.predict('/show', { story, seed });
  const [motions, voices, t] = result.data;
  const motion = {};
  for (const file of motions) {
    const name = (file.orig_name || file.path || file.url).split(/[\\/]/).pop().replace(/\.glb$/, '');
    motion[name] = file.url;
  }
  await start(t, { motion, voices: voices.url });
}

function selectedIdeaIndex(story) {
  return [...document.querySelectorAll('[data-idea]')].findIndex((button) =>
    button.dataset.story === story.trim());
}

function finishShow(note = '') {
  $('watch-note').textContent = note;
  endLoading();
  showStep('watch');
  player.resize();
  play(0);
}

async function makeShow() {
  if (locked) return;
  const story = $('story').value.trim();
  if (!story) { status('First, tell us what your story is about.', true); $('story').focus(); return; }
  const idea = selectedIdeaIndex(story);
  if (demo && idea < 0) {
    status('Demo mode has prerecorded shows for the three example ideas. Tap an idea to try one.', true);
    return;
  }
  locked = true;
  $('make').disabled = true;
  status('');
  pause();
  timeline = null;
  beginLoading();
  try {
    if (demo) {
      await fromFolder(`demo/${examples[idea].slug}`);
      finishShow('This is a ready-made example show for the demo.');
      return;
    }
    try {
      await live(story);
      finishShow();
    } catch (error) {
      // The three sentence ideas have matching structured, locally recorded demos.
      // If free-text planning fails, try the structured API without the LLM first.
      if (idea < 0 || !examples[idea]) throw error;
      try {
        setLoadingMessage('Trying our backup script…');
        if (!client) throw error;
        await live(JSON.stringify(examples[idea].show));
        finishShow('Made using the ready-made example script.');
      } catch (_backupError) {
        setLoadingMessage('Bringing out the saved show…');
        await fromFolder(`demo/${examples[idea].slug}`);
        finishShow('The live service was unavailable, so this is a prerecorded example show.');
      }
    }
  } catch (error) {
    endLoading();
    showStep('write');
    status(`We couldn't make your show this time. ${error?.message || 'Please try again.'} You can also tap an example idea.`, true);
  } finally {
    endLoading();
    locked = false;
    $('make').disabled = false;
  }
}

async function init() {
  const response = await fetch('examples.json');
  if (!response.ok) throw new Error('The saved example list could not load.');
  examples = await response.json();
  // The writing prompts are plain English. The JSON show data stays internal.
  const ideaButtons = [...document.querySelectorAll('[data-idea]')];
  ideaButtons.forEach((button) => {
    button.dataset.story = button.querySelector('.idea-text').textContent.trim();
    button.addEventListener('click', () => {
      $('story').value = button.dataset.story;
      $('story').dispatchEvent(new Event('input'));
      status('');
      $('story').focus();
    });
  });
  $('story').addEventListener('input', () => {
    $('char-count').textContent = `${$('story').value.length} / 3000`;
    if ($('status').classList.contains('error')) status('');
  });
  $('make').addEventListener('click', makeShow);
  $('another').addEventListener('click', () => {
    pause();
    $('watch-note').textContent = '';
    $('story').value = '';
    $('story').dispatchEvent(new Event('input'));
    showStep('write');
    $('story').focus();
  });
  $('again').addEventListener('click', () => { play(0); });
  $('play').addEventListener('click', () => (playing ? pause() : play()));
  $('scrub').addEventListener('input', () => timeline && seek((Number($('scrub').value) / 1000) * timeline.duration));
  addEventListener('keydown', (event) => {
    if (event.code === 'Space' && event.target === document.body && !$('watch-step').hidden && $('loading-step').hidden) {
      event.preventDefault();
      playing ? pause() : play();
    }
  });
  new ResizeObserver(() => {
    if (!$('watch-step').hidden) {
      player.resize();
      if (timeline && !playing) player.renderAt(clockOffset);
    }
  }).observe($('screen'));
  requestAnimationFrame(loop);

  if (params.has('show')) {
    beginLoading();
    try {
      await fromFolder(params.get('show'));
      if (capture) { endLoading(); showStep('watch'); document.body.dataset.ready = '1'; }
      else finishShow('Playing a saved example show.');
    } catch (error) {
      endLoading();
      if (capture) document.body.dataset.error = error.message;
      else { showStep('write'); status(error.message, true); }
      console.error('[MoMask show]', error);
    }
  }
}

// Existing capture tools call renderAt(t) and duration() to record deterministic frames.
if (capture) {
  window.renderAt = (t) => { player.renderAt(t); overlay(t); };
  window.duration = () => timeline?.duration || 0;
  window.player = player;
}
init().catch((error) => status(`Couldn't load the show page: ${error.message}`, true));
