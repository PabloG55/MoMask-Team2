---
title: MoMask Team2
emoji: 🕺
colorFrom: pink
colorTo: indigo
sdk: gradio
sdk_version: 6.30.0
python_version: '3.12'
app_file: app.py
pinned: false
license: mit
---

# MoMask as a service

ITCS 6166 (Computer Communication and Networks), Topic 2: Generative AI as a Service. Team 2:

- **Pablo Garces**: server (model, hosting, network measurements). This repository.
- **Ramisha Mahiyat**: client (Three.js character, story player).

The idea: instead of streaming video of a person moving, send a short text description and let the server generate the motion. This repository serves [MoMask](https://github.com/EricGuo5513/momask-codes), a text-to-3D-motion model, as an API. Send an action such as `a person walks forward` and get back:

| Output | What it is | Typical size (100 frames, 5 s) |
|---|---|---|
| BVH | the skeleton animation (22 joints, 20 fps). The client plays this on a character. | ~70 KB (~27 KB gzipped) |
| MP4 | a stick-figure preview video | ~40 KB |
| JSON | network measurements: frames, generation time, payload sizes | under 100 bytes |

It runs as a Hugging Face Space, on the CPU: the Space is on ZeroGPU hardware, but visitors without a Hugging Face login get about two minutes of GPU a day, and MoMask is small enough for the CPU. On first start, the pretrained checkpoints are downloaded from [`pgarces/momask-checkpoints`](https://huggingface.co/pgarces/momask-checkpoints).

## Run it locally

Tested on macOS (Apple silicon, CPU only) with Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt gradio
python app.py
```

Then open http://127.0.0.1:7860. The first start downloads the MoMask checkpoints into `momask/checkpoints/` and the Kokoro voice (~340 MB) into `app/checkpoints/kokoro`; later starts reuse them. `ffmpeg` has to be installed.

For story mode from free text, copy `.env.example` to `.env` and put an OpenAI key in it. `.env` is git-ignored; on the Space the same key is a secret named `OPENAI_API_KEY`. Without a key, story mode still takes a JSON list of steps.

Tests (no model download needed, a few seconds):

```bash
pip install pytest
python -m pytest app/tests -q
```

## Call the API

```python
from gradio_client import Client

client = Client("http://127.0.0.1:7860/")   # or "pgarces/MoMask-Team2" once the Space is up
bvh_path, mp4, stats = client.predict(
    "a person walks forward",  # action
    100,                       # frames (0 = let the model choose the length)
    42,                        # seed
    api_name="/generate",
)
print(stats)
# {"frames": 100, "generation_seconds": 2.62, "bvh_bytes": 70515, "mp4_bytes": 43364}
```

`generation_seconds` measures the model only (the example is from a Mac CPU). Converting to BVH and rendering the MP4 add a few seconds to the round trip.

## Story mode

Send a short story instead of one action. The server:

1. splits it into 2–6 actions with GPT-6 Luna (OpenAI Responses API, structured output), or takes a hand-written JSON list of steps as is;
2. narrates each step with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (English or Spanish), so it knows how long each line lasts and makes each action long enough for it;
3. generates one MoMask motion per action and regenerates the 1.6 s around each change of action with MoMask's own temporal editing (`MaskTransformer.edit`, as in `momask/edit_t2m.py`), so one action flows into the next instead of jumping;
4. retargets the result onto the client's Mixamo Xbot and sends it as an animation-only `.glb`, with one `.mp3` and a timeline that ties the two together.

```python
motion_glb, narration_mp3, timeline = client.predict(
    "Max wakes up late, stretches, and runs to catch the bus.",  # or a JSON list of steps
    42,     # seed
    True,   # smooth transitions
    api_name="/story",
)
```

The response format, and how the client plays it, are in [`app/docs/STORY-API.md`](app/docs/STORY-API.md).

Measured on a Mac CPU with a 3-step JSON story (10.2 s of motion):

| | |
|---|---|
| Story text sent | 359 bytes |
| Motion `.glb` (Xbot, int16 rotations) | 52.8 KB (31.6 KB gzipped) |
| Same motion as BVH | 138.2 KB (53.4 KB gzipped) |
| Narration `.mp3` (64 kbit/s) | 82.2 KB |
| Server time | 4.7 s (narration 1.5, MoMask 1.4, IK 1.6, retarget + audio 0.2) |
| Jump at the first change of action | 12.9 cm/frame raw → 1.3 cm/frame regenerated (0.9 typical) |

Every `/story` response carries the same numbers for that request in `timeline.stats`.

Code: `app/story/orchestrator.py` (story → steps), `app/story/narration.py` (Kokoro), `app/story/motion.py` (MoMask + transitions), `app/story/retarget.py` and `app/story/gltf.py` (Xbot), `app/story/pipeline.py` (puts it together). `app/tools/preview.html` renders a `.glb` on Xbot next to the MoMask skeleton for checking a retarget by eye.

## Show mode

A Pocoyo-style show instead of one Xbot: up to three of ten characters take turns on a set,
each in their own voice, while a narrator talks to them and the camera cuts between shots.

```python
motions, voices_mp3, timeline = client.predict(story, 42, api_name="/show")
```

`story` is free text, which GPT-6 Luna turns into a show (cast, set, light, actions, camera
shots, lines), or a show written as JSON, which needs no LLM. Three examples are in
`app/client/story/examples.json`. The server returns one animation-only `.glb` per character, one
`.mp3` and a timeline with the subtitles, the camera plan and a mouth track per character.
The format is in [`app/docs/SHOW-API.md`](app/docs/SHOW-API.md).

**The player** is `app/client/story/`, a static page (three.js + three-vrm, no build step):

```bash
python3 -m http.server 8831 --directory app/client/story
# http://127.0.0.1:8831/                      pick a story, "Play saved show" or "Make it live"
# http://127.0.0.1:8831/?space=http://127.0.0.1:7860   use a local app.py instead of the Space
```

It loads the set and the characters, plays the motion and the voices in sync, moves each
mouth, follows the camera plan, and shows what was sent next to the size of the same show as
a 720p video (about 20× less). "Free camera" lets you look around. `app/client/story/demo/` has
the three examples already made, so the page works with no server at all.

**Assets.** Every character and set model is CC0:

- Characters: 10 avatars from 100Avatars by Polygonal Mind (`app/client/story/characters/*.vrm`). Their skeletons, which the server retargets onto, are in `app/story/characters/*.json` (`app/tools/character_skeletons.py`).
- Sets: models from Kenney's Nature, Furniture, Pirate and Space kits (https://kenney.nl), built by `app/tools/build_sets.py`. Credits per model are in `app/client/story/sets/CREDITS.md`.

**Deploying.** The Space needs `app.py`, `momask/`, `app/server/`, `app/story/` (with
`app/story/characters/*.json`), `app/client/story/examples.json`, which the page reads, and
`app/client/docs/assets/character/Xbot.glb`, which the Story tab shows. It does not need the
VRMs, set models or saved shows; only the player uses those. If
`app/client/story/` goes to the Space as well, first
add `*.vrm`, `*.glb` and `*.mp3` to `.gitattributes` as LFS, because Hugging Face wants binary
files in LFS/Xet. Free text needs the Space secret `OPENAI_API_KEY`.

Code: `app/story/director.py` (story → show, and the checks on it), `app/story/show.py` (voices,
mouths, camera plan, puts it together), `app/story/collide.py` (keeps each character's arms out of
its own head and body), `app/client/story/player.js` (the 3D show) and `app/client/story/main.js` (the
page). `app/tests/test_show.py` covers the director's cleaning, the camera plan, the voices and the
sets, and `app/tests/test_beats_collide.py` the timing, the arms and the head nods, all without
needing MoMask.

## What we changed from upstream

This repository started as a copy of [EricGuo5513/momask-codes](https://github.com/EricGuo5513/momask-codes) at commit `94a6636`.

- `momask/`: their code. The model, training and inference code are unchanged, and their scripts still run from inside it, as in their README (`cd momask && python gen_t2m.py --gpu_id -1 --text_prompt "a person walks forward"`).
- `app/`: ours. `app/server/` is the Gradio service (`models.py` loads MoMask, `api.py` is what `/generate`, `/story` and `/show` do, `ui.py` is the page); `app/story/` is story and show mode; `app/client/docs/` is the Xbot client and `app/client/story/` the show player; `app/tests/` covers all of it without loading MoMask; `app/tools/` rebuilds the skeletons and sets; `app/docs/` has the two API formats.
- `app.py`: starts the service. It puts `app/` and `momask/` on the import path, and the server enters `momask/` only while loading the models, because MoMask opens `./checkpoints` and `./visualization/data` from its own folder.
- `requirements.txt`: rewritten for torch 2.11 / numpy 2.1.3. The original pins torch 1.12, which ZeroGPU does not accept. Story mode adds `openai`, `python-dotenv` and `kokoro-onnx`.
- `packages.txt`: `ffmpeg`, for the MP4 preview

And made compatibility fixes so the original code runs on current libraries:

- `momask/visualization/Animation.py`, `momask/visualization/Quaternions.py`: `numpy.core.umath_tests.matrix_multiply` → `np.matmul` (removed in NumPy 2)
- `momask/visualization/remove_fs.py`, `momask/utils/motion_process.py`, `momask/common/quaternion.py`: `np.float` → `float` (alias removed from NumPy)
- `momask/utils/plot_script.py`: `Axes3D(fig)` → `fig.add_subplot(111, projection="3d")`, and frame clearing with `artist.remove()` (both required by newer Matplotlib)

Training, evaluation and dataset scripts from upstream are still in `momask/` but untested with these dependencies. For those, follow the [upstream README](https://github.com/EricGuo5513/momask-codes#readme).

## Credit

MoMask is the work of Chuan Guo, Yuxuan Mu, Muhammad Gohar Javed, Sen Wang and Li Cheng (University of Alberta):

> *MoMask: Generative Masked Modeling of 3D Human Motions.* CVPR 2024. [Paper](https://arxiv.org/abs/2312.00063) · [Project page](https://ericguo5513.github.io/momask/) · [Code](https://github.com/EricGuo5513/momask-codes)

```bibtex
@inproceedings{guo2024momask,
  title={Momask: Generative masked modeling of 3d human motions},
  author={Guo, Chuan and Mu, Yuxuan and Javed, Muhammad Gohar and Wang, Sen and Cheng, Li},
  booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition},
  pages={1900--1910},
  year={2024}
}
```

The original code is MIT-licensed; its copyright notice is kept in [`LICENSE`](LICENSE).
