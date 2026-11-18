# MoMask story experience — frontend

A simple three-screen story maker:

1. **Write a story.** The visitor types a normal-language story or taps one of three sentence ideas to fill the textbox. Click **Make my show**. No API settings or JSON appear in the UI.
2. **Wait behind the curtain.** A full-screen animated theatre curtain cycles through friendly messages and shows elapsed time (not a promise/countdown). Live generation commonly takes 30+ seconds, especially when the Hugging Face Space has been asleep.
3. **Watch the show.** A large 3D stage plays characters, camera shots, captions and voices; play/pause, seeking, **Watch it again**, and **Make another story** are available.

This renders 3D locally in the viewer using Three.js and three-vrm. It does **not** play or download a streamed video. The existing `player.js`, `characters/`, `sets/`, `demo/` and `examples.json` remain unchanged.

## Start locally

From the `MoMask-Team2` repository root:

```bash
python3 -m http.server 8831 --directory app/client/story
```

Type this exact URL in your browser: <http://localhost:8831/index.html>. The frontend needs internet access for CDN JavaScript dependencies, even when playing a local saved show from a newly loaded page.

## Space API

In `main.js` the frontend uses the existing backend:

```js
const { Client } = await import('https://cdn.jsdelivr.net/npm/@gradio/client@2.7.2/dist/index.min.js');
const app = await Client.connect('pgarces/MoMask-Team2');
const result = await app.predict('/show', { story, seed: 42 });
const [motions, voices, timeline] = result.data;
```

The frontend maps each returned character `.glb` motion to its `.vrm` character in `characters/`; `voices` is the mixed `.mp3` audio track; `timeline` drives camera cuts, captions, and animation. `player.js` handles 3D rendering. The API is described in `app/docs/SHOW-API.md`.

The server needs its OpenAI key for free-text planning. The client doesn't need API keys. Open the [Hugging Face Space](https://huggingface.co/spaces/pgarces/MoMask-Team2) before class to wake it up. The optional query parameter `?space=<id-or-url>` can target a different development backend without adding a visible Space field.

## Fallback and recording

The three example sentence buttons map internally to the three existing entries in `examples.json` and saved output folders in `demo/`. For a selected example, if live free-text generation fails, the client first tries its structured show definition via `/show` (this bypasses OpenAI), then automatically uses the locally saved output if the Space still cannot make it. A note identifies when the result is a structured or prerecorded example rather than the requested free-text show. Custom stories are **not** silently replaced with unrelated examples; a helpful error appears instead.

**Fast demo mode:** open <http://localhost:8831/index.html?demo=1>, tap one of the three example sentences, then press **Make my show**. This goes straight to the matching prerecorded show without calling the Space, while preserving the same three-screen experience. It still relies on the frontend's CDN dependencies, so keep a screen-recording backup if Wi-Fi might fail.

For frame capture, the former `?capture=1&show=demo/dino-s-big-jump` interface is still supported and exposes `window.renderAt(t)` and `window.duration()`.

Before Thursday: verify the live story generation path, the demo path, replay/pause/subtitles, and the audio in your backup recording. A Mac screen recording does not always include system audio by default: verify sound before class or use a capture tool configured for audio.

## Files changed for this UI

- `index.html`: three-step markup, three example sentence buttons, animated curtain, large player.
- `style.css`: responsive, playful styles and CSS loading animation.
- `main.js`: frontend state and API/fallback orchestration, playback controls.
- `README.md`: this guide.
