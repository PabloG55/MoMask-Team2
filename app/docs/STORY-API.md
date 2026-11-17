# Story API (`/story`)

The client sends a story and gets back everything it needs to play it on the Xbot
character: one animation, one narration track and a timeline that ties them together.

## Request

```js
import { Client } from "@gradio/client";

const app = await Client.connect("pgarces/MoMask-Team2");
const result = await app.predict("/story", {
  story: "A girl wakes up, stretches, walks to the window and waves at her friend.",
  seed: 42,        // same story + same seed = same motion
  smooth: true,    // false = clips back to back, with a jump at each change of action
});
const [motion, narration, timeline] = result.data;
```

`story` can be free text (the server turns it into steps with GPT-6 Luna) or a JSON list of
steps written by hand, which skips the LLM:

```json
[
  {"action": "a person walks forward", "narration": "She left home at dawn.", "seconds": 4},
  {"action": "a person waves with the right hand", "narration": "And waved at her friend."}
]
```

`{"title": "...", "steps": [...]}` works too. Up to 6 steps; `seconds` is kept between 2.4
and 9.8 (default 4), and the server makes an action longer if its narration needs more time.
Free text can be English or Spanish: the narration comes back in the story's language, while
the actions stay in English for MoMask.

## Response

`result.data` has three items, in this order:

| # | What | Format |
|---|------|--------|
| 0 | `motion` | File (`.glb`). One animation clip, already retargeted onto Xbot. It has no mesh: you keep the Xbot you already loaded and play this clip on it. |
| 1 | `narration` | File (`.mp3`). The whole narration as one track. Second 0 of the audio is second 0 of the clip. |
| 2 | `timeline` | JSON, below. |

Files come back as Gradio file objects, so use `motion.url` and `narration.url`.

```json
{
  "version": 1,
  "fps": 20,
  "duration": 13.6,
  "motion_duration": 13.6,
  "title": "Good morning",
  "language": "en",
  "actions": [
    {
      "index": 0,
      "action": "a person wakes up and stretches both arms",
      "narration": "She woke up and stretched.",
      "start": 0.0,
      "end": 4.4,
      "speech_start": 0.3,
      "speech_end": 2.1
    }
  ],
  "transitions": [{"between": [0, 1], "start": 3.6, "end": 5.2}],
  "stats": {}
}
```

- `duration` is the audio's length and `motion_duration` the clip's. They are the same unless
  the last line runs past the motion; then the clip holds its last pose (see "Playing it").
- `start` and `end` (seconds) are where each action sits in the clip.
- `speech_start` and `speech_end` are where its narration line sits in the audio. Use them
  for subtitles. Both are `null` for a step with no narration.
- `transitions` are the stretches the server regenerated so one action flows into the next.
  They are empty when `smooth` is false.
- `stats` is for the network slides:
  - `seconds`: time per stage (`plan` = GPT-6 Luna, `narration` = Kokoro, `motion` = MoMask,
    `ik`, `retarget`, `audio`, `total`).
  - `bytes`: the story text, the plan, the `.glb` (and gzipped), the same motion as BVH
    (and gzipped), the `.mp3`.
  - `seams.kick_cm`: how sharply the motion changes at each seam, raw cut vs regenerated, in
    cm per frame, next to `typical_cm` for the whole story. A visible cut is ~10 cm; after the
    transition it is close to the typical value.
  - `planner` (`gpt-6-luna` or `json`) and `llm_tokens`.

## Playing it

```js
// xbot = the scene from Xbot.glb, loaded once at startup.
const clip = (await new GLTFLoader().loadAsync(motion.url)).animations[0];
const mixer = new THREE.AnimationMixer(xbot);
mixer.clipAction(clip).play();

const audio = new Audio(narration.url);
await audio.play();

// Every frame: follow the audio clock so the motion and the voice never drift apart.
// Capping the time at the clip's end holds the last pose while the audio finishes.
function tick() {
  mixer.setTime(Math.min(audio.currentTime, clip.duration - 0.001));
  renderer.render(scene, camera);
  if (!audio.ended) requestAnimationFrame(tick);
}
tick();
```

- Stop Xbot's own clips (walk, idle, …) before playing, or they mix with the story.
- Don't use `LoopOnce` + `clampWhenFinished` here: once the clip ends three.js pauses the
  action, and `mixer.setTime()` can't move a paused action, so a replay stays frozen on the
  first frame. The time cap above does the same job without that trap.
- The clip's tracks are named after Xbot's bones (`mixamorig:Hips`, …), so it only fits
  `app/client/docs/assets/character/Xbot.glb`. Hips move in centimetres, like Mixamo's clips.
- Phones only play audio after a tap, so start the story from a button.

## Errors

The call fails with a readable message (the `message` of the error `@gradio/client` throws)
when the story is empty, when it starts like JSON but isn't valid, when GPT-6 Luna can't be
reached, or when the server has no `OPENAI_API_KEY`. A JSON list of steps still works
without the key, so keep one ready for the live demo.

A story takes about 3–6 s on a laptop CPU. The Space runs everything on its CPU too (see
README.md).
