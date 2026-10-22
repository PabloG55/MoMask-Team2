# MoMask Team 2 — browser client

Static two-viewer application for the ITCS 6166 Progress 2 demonstration. Written for GitHub Pages under `docs/`; no bundler or secrets needed.

## What it does

- Loads `assets/character/Xbot.glb` with `GLTFLoader` and plays its built-in **walk** animation using `THREE.AnimationMixer`.
- Loads offline `assets/motions/walk.bvh` and `wave.bvh` using `BVHLoader` and visualizes bones with `THREE.SkeletonHelper`.
- Prompts the live Hugging Face Space `pgarces/MoMask-Team2`, endpoint `/generate`, sending `text`, `length_frames` (0 = automatic), and `seed`.
- Receives `[BVH file, MP4 preview, stats]`, fetches and parses the BVH, then replaces the skeleton animation. Shows returned stats and a link to the MP4.
- Displays a visible **Generating…** state, with a running request duration and error messages.
- Measures the **API round trip** with `performance.now()` around `await app.predict('/generate', ...)`, a separate BVH fetch+parse+playback time, and an end-to-end click-to-play time. Saves successful runs to local browser storage and exports CSV.

**IMPORTANT:** BVH skeleton animation and Xbot walk are **independent**. Motion-to-Xbot retargeting is Pablo's separate future server work, not part of this client.

## Run locally

From repository root:

```bash
python3 -m http.server 8000
```

Open `http://localhost:8000/docs/`. You **must not** open `docs/index.html` as a `file://` URL. If serving from `docs/`, run the server there and open `http://localhost:8000/` instead.

An internet connection is required for three.js (pinned to `0.179.1` using a jsDelivr import map), Google Fonts and live API generation (`@gradio/client` is loaded from jsDelivr on first request). Offline BVH samples **do not call** the generation endpoint but still require the three.js library CDN on first load.

## Publish to GitHub Pages

In the repository's **Settings → Pages**, choose **Deploy from a branch**, branch `main` (or the chosen default branch), folder `/docs`, then save. No `build` directory or npm install is required. Asset URLs are relative to `docs/main.js`, so the page works under the repository subpath.

## Browser timing experiment

1. Open the client in Chrome or Safari, allow Xbot and the offline walk skeleton to load, then run one live request.
2. Set **Frames: 100** and **Seed: 42**; prompt: `a person walks forward`. Click **Generate motion**. Repeat 3–5 times (note first/cold vs warm).
3. Repeat 3–5 times with prompt: `a person waves his hand` and the same frames/seed.
4. Select **Export CSV ↓**. Use the rows on slide 17 of the Progress 2 deck.

**Timings:** `API RTT` starts **immediately before** calling `app.predict()` and ends on resolution with all Gradio response metadata. It excludes initial `Client.connect()` setup, later standalone BVH-file download, parsing and playback. The separate end-to-end field includes initial connection and that additional download. Browser timings differ from the service's reported model-generation time and cannot be inferred from it. A successful run is logged only after a returned BVH is fetched, parsed and played. Network and ZeroGPU queue conditions vary.

## Screen recording and slide evidence

- Slide 13: use `client-architecture.svg` or exported `client-architecture.png`.
- Slide 14: screenshot the page's **Xbot / Walking** panel once it reads `Playing · built-in walk`.
- Slide 15: after a successful live request, screenshot the skeleton alongside the visible stats and round-trip timer.
- Slide 16: record 20–30 s of browser screen showing typed prompt → **Generating…** → animated skeleton and Xbot walking. On macOS use Cmd+Shift+5 for a screen recording.
- Slide 17: export CSV after running each prompt repeatedly. The app does not invent timings.

## Contents

```text
docs/
├── index.html
├── style.css
├── main.js
├── client-architecture.svg
└── assets/
    ├── character/Xbot.glb
    └── motions/{walk,wave}.bvh
```

**Troubleshooting:** If the models do not appear, open browser DevTools → Console and check CDN/network requests. If generated files cannot be fetched in the browser, inspect CORS or any temporary expiry of the Gradio returned file URL. Make sure the Space is awake. There is deliberately no silent switch from a failed live request to a local sample.

## Included preview images are not runtime evidence

`screenshots/client-architecture.png` is a slide-ready architecture diagram. `screenshots/ui-layout-preview-not-live.png` is a design/layout preview captured **without WebGL or live API access** and must **not** be presented as evidence of successful playback or measured latency. Replace it with an actual browser screenshot after testing locally.
