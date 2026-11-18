# MoMask Team 2 — Show Client

The show client is a static browser app that turns a short story or structured show JSON into a narrated 3D scene. It uses Three.js and `three-vrm` to render characters, sets, motion, camera cuts, subtitles, and synced audio. The browser renders the show locally; the server does **not** stream a video.

## Run the frontend

From the **repository root**:

```bash
python3 -m http.server 8831 --directory app/client/story
```

Then open <http://127.0.0.1:8831/>.

No frontend build step or Python model installation is required. An internet connection is needed for CDN JavaScript dependencies and for live generation via the Hugging Face Space. Saved shows can be played without calling the Space, although the browser still needs to load the JavaScript dependencies.

## Try the saved demo first

1. Select one of the examples in the **Story** dropdown.
2. Click **Play saved show**. The player loads `demo/<example-slug>/timeline.json`, the character motion `.glb` files, and `voices.mp3` from the local folder.
3. Test play/pause, the seek bar, subtitles, and the free camera.

The three example show definitions are also in `examples.json`. These structured JSON stories bypass LLM planning when sent to the live API.

## Generate a live show

1. Open the [Space](https://huggingface.co/spaces/pgarces/MoMask-Team2) first to wake it up.
2. In the client, leave **Space** set to `pgarces/MoMask-Team2` and **Seed** set to `42`.
3. Choose an example JSON story, or select **Write my own…** and type a short natural-language story.
4. Click **Make it live**. A loading overlay stays visible while generation runs; it can take around 30 seconds or longer when the Space is cold.
5. The browser loads the returned animations and voice track, then plays the show.

For a locally running Gradio backend, start the frontend with `?space=http://127.0.0.1:7860`, e.g. <http://127.0.0.1:8831/?space=http://127.0.0.1:7860>.

## API contract

`main.js` imports `@gradio/client` dynamically, connects to the Space, and calls:

```js
const app = await Client.connect("pgarces/MoMask-Team2");
const result = await app.predict("/show", { story, seed: 42 });
const [motions, voices, timeline] = result.data;
```

- `motions`: one animation-only `.glb` file per character, loaded onto its matching local VRM character.
- `voices`: a single mixed narration/dialogue `.mp3` file.
- `timeline`: show duration, cast, steps, camera shots, captions, mouth movements, and network/statistics data.

The frontend maps character names to motion-file URLs, loads the assets with `ShowPlayer` from `player.js`, and synchronizes the animation, camera, captions, and audio on the browser playback clock. The page displays round-trip timing and network size information after generation.

Full API definition: [`app/docs/SHOW-API.md`](../../docs/SHOW-API.md). The older one-character Xbot mode is at `/story` and documented in [`app/docs/STORY-API.md`](../../docs/STORY-API.md).

## Failure modes and demo backup

- **Space slow / cold start:** open it before the presentation, then allow extra time for the first generation.
- **Free-text planning fails:** select a JSON example from `examples.json` and use **Make it live**; structured JSON skips the OpenAI director.
- **Space or Wi-Fi unavailable:** use **Play saved show** with files in `demo/` to show a pre-generated result. Note that the page uses CDN JavaScript imports; if completely offline, use a previously recorded demo video rather than relying on a fresh browser load.
- **Missing models / blank canvas:** check the browser developer console and confirm `characters/`, `sets/`, and `demo/` were pulled from `main`.
- **Unexpected 404:** serve from the repository root with the command above, then visit the root URL `/`, **not** `/docs/`.

Before class, record a short screen-capture video that shows a selected example, the rendered 3D animation, captions, and audio. Keep a copy locally. Also test one live show with JSON before relying on free-text planning.

## Main frontend files

- `index.html` — layout, story input, play controls, loading message.
- `main.js` — Gradio API connection, UI events, demo loading, playback/audio timing.
- `player.js` — Three.js and VRM rendering, motion, camera, and expressions.
- `style.css` — visual styling.
- `examples.json` — prewritten JSON story definitions.
- `characters/`, `sets/`, `demo/` — static 3D assets and saved example outputs.
