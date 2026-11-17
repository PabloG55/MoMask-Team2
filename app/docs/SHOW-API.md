# Show API (`/show`)

A Pocoyo-style show: up to three characters take turns on a set while a narrator talks to
them. The client sends a story and gets back one animation per character, one voice track
and a timeline. It then plays the show itself, in three.js, with the characters, the set and
the camera. No video crosses the network.

`/story` (one Xbot, one narrator, see [`STORY-API.md`](STORY-API.md)) is unchanged.

## Request

```js
import { Client } from "@gradio/client";

const app = await Client.connect("pgarces/MoMask-Team2");
const result = await app.predict("/show", { story, seed: 42 });
const [motions, voices, timeline] = result.data;
```

`story` is free text or a show written as JSON.

**Free text** goes to GPT-6 Luna (OpenAI Responses API, strict JSON schema), acting as the
director. It picks the cast, the set, the light, each step's action and camera shot, and the
lines. This needs `OPENAI_API_KEY` on the server.

**JSON** skips the LLM. It works without a key, so keep one ready for a live demo:

```json
{
 "title": "Dino's big jump",
 "language": "en",
 "set": "stage",
 "light": "studio",
 "cast": ["DinoKid", "Teddy"],
 "steps": [
  {"actor": "DinoKid", "action": "a person waves with the right hand", "seconds": 3, "shot": "medium",
   "lines": [{"who": "narrator", "text": "Look who's here! Hello, Dino! Hello, Teddy!", "when": "before"},
             {"who": "DinoKid", "text": "Hi! Hi!", "when": "during"}]}
 ]
}
```

| Field | Values |
|---|---|
| `cast` | 1–3 of Astronaut, CoolAlien, DinoKid, Froggy, Hugo, Jimmy, Kyle, LilBro, Polybot, Teddy |
| `set` | `stage` (white, like Pocoyo), `park`, `room`, `beach`, `space` (the moon) |
| `light` | `studio`, `day`, `sunset`, `night` |
| `steps` | up to 6; `actor` is one of the cast |
| `action` | an English HumanML3D-style sentence, "a person …" (MoMask's input) |
| `seconds` | 2.4–6.0, default 3; made longer if a line spoken `during` it needs more time |
| `shot` | `wide`, `medium`, `close`, `low`, `high`, `orbit`, `follow` |
| `lines` | up to 4 per step: `who` (`narrator` or a cast member), `text`, `when` (`before`, `during`, `after`) |

The server cleans whatever it gets, from the LLM or from JSON, before running anything. Names
match ignoring case and spaces ("dino kid" → DinoKid). A cast past three is cut. A step whose
actor is not in the cast goes to the first cast member. A line from someone not in the cast
becomes the narrator's. Lines are cut to 12 words for characters and 22 for the narrator. A
missing set, light or shot gets a default (an astronaut goes to the moon). `language` is `en`
or `es`; the lines are spoken in it, while the actions stay in English for MoMask.

## Response

`result.data` has three items, in this order:

| # | What | Format |
|---|------|--------|
| 0 | One animation per character | list of files, `<Name>.glb`: animation only, no mesh |
| 1 | Every voice, mixed | one `.mp3` |
| 2 | Timeline | JSON, below |

Each `.glb` holds one clip named after the character. Its tracks are named after that
character's own bones (for example `vis_char_045:mixamorig:Head` for DinoKid), so a clip only
fits its own character, from `app/client/story/characters/<Name>.vrm`.

### Timeline (version 2)

| Key | What |
|---|---|
| `version`, `fps` | `2`, and the motion's frame rate (20) |
| `title`, `language`, `set`, `light` | as cleaned |
| `duration` | seconds; the voices and the motion both end here |
| `cast[]` | `name`, `x` (where they stand, metres), `motion` (the file name) |
| `steps[]` | `actor`, `action`, `shot`, `settled` (when the action is over) |
| `segments[]` | `kind` (`talk` or `action`), `step`, `start`, `end`, `captions` (what each character does meanwhile) |
| `lines[]` | `who`, `text`, `when`, `step`, `start`, `end`: subtitles, and who to cut to |
| `shots[]` | `start`, `end`, `type`, `target`: the camera plan |
| `transitions[]` | `start`, `end`: where MoMask regenerated the join between two segments |
| `mouth` | per character: `fps` (30) and `aa`, `ee`, `oh`, each 0–100 |
| `stats` | planner, LLM tokens, seconds per stage, frames, `arms_fixed`, `bytes` |

While one character acts or talks, the others "stand and look around", so nobody freezes.
Characters who talk get "stands and explains something with hand gestures".

### The camera

The server plans the shots. The player frames each one.

- The show opens on a `wide` shot of everyone.
- An action gets the shot the director picked for it, aimed at the actor.
- A character's line cuts to a `close` shot of the speaker, 0.2 s before they speak.
- A narrator line `after` an action shows the one who did it (`medium`), so a "Wow!" lands on the jumper.
  Any other narrator line goes `wide` (or `medium` when the cast is one character).
- A cut that would repeat the current shot is skipped. A cut less than 1 s after the last one
  is dropped too, unless it is an action's shot, which then replaces the talk shot before it.

The player frames a shot from where the target's hips and head are during it, so a jump
stays in frame. It adds a slow 5% push-in and cuts hard between shots. `follow` tracks the
target with smoothing; `orbit` circles them.

### The mouth and the voices

Kokoro reads every line in that character's voice (Polybot gets a robot filter). The mouth
track is computed from each character's own lines: loudness opens it, and the brightness of
the sound picks `ee` over `oh`. The player drives the VRM's `aa`/`ee`/`oh` expressions with
it and blinks every few seconds.

### Feet, arms and heads on a chibi body

MoMask moves a human. These characters have a head about as big as the body and short arms,
so the same motion can put a hand inside the head or the belly. Three fixes:

- **No foot IK** (`foot_ik=False`, here and in `/story` and `/generate` too). MoMask's
  converter normally pins each planted foot to the floor (`remove_fs`), but it pins the ankle
  and the toe separately, so when the ankle slides and the toe stays put the foot swings
  round. In the Dino example DinoKid's toes turned 120° inward while MoMask had them pointing
  outward, which crossed his legs. Measured on all seven characters of the three examples
  (2026-11-15): 21–86 frames each with a foot more than 45° off MoMask's direction with it,
  none without, and no foot goes into the floor without it. What is left is MoMask's own foot
  sliding, a median of 0.2 cm per frame.
- **Nods are halved** (`soften_nods` in `app/story/retarget.py`). How far the head tips forward,
  back or sideways is halved at the neck and the head; turning left and right is kept.
  MoMask's "stands and looks around" throws the head back about 55°, which on a chibi hides
  the face.
- **Arms stay out of the body** (`app/story/collide.py`). Each character's head, chest, belly and
  thighs are superquadrics fitted to its own mesh by `app/tools/character_skeletons.py`, stored in
  `app/story/characters/<Name>.json`. On a frame where an arm enters any of them, the arm turns at
  the shoulder by the smallest angle that clears all of them at once. The turn is never more
  than 75° and is eased over the neighbouring frames. The elbow and wrist stay as MoMask made
  them. `stats.arms_fixed` gives, per arm, how many frames were turned and the largest turn.

Measured against each character's real mesh on the three examples (2026-11-15, without foot
IK):

| | Hand more than 2 cm inside the body |
|---|---|
| MoMask's own skeleton | never (deepest 1 cm) |
| Astronaut, Teddy, with the earlier head-and-chest fix | 61–69% of frames |
| Same, now | 0–6% of frames, up to 4.6 cm |
| All seven characters in the examples, now | 0–6%, except one Polybot arm brushing its thigh (16%, under 3 cm) |

So the problem was the retarget onto a chibi body, not the model.

## Measured

On a Mac CPU, JSON shows (no LLM):

| Show | Length | Server time | Sent to the viewer | Same show as 720p video (2.5 Mbit/s) |
|---|---|---|---|---|
| Dino's big jump (2 characters) | 31.6 s | 27.9 s | 455 KB | 9.9 MB (22×) |
| A walk on the moon (3) | 30.0 s | 32.6 s | 525 KB | 9.4 MB (18×) |
| El baile de Froggy (2, Spanish) | 19.2 s | 11.7 s | 278 KB | 6.0 MB (22×) |

"Sent" is the motion `.glb`s gzipped, plus the `.mp3` and the timeline. The same Dino show
rendered to an actual 720p H.264 file (crf 20) is 5.5 MB. About half of the server time was
IK and retargeting; IK now runs 10 iterations instead of 100 (the authors' default, just as
close), which takes about 0.7 s off each character.
Keeping the arms out of the body is up to about 2 s per character of that. These times are
from 2026-11-15, while another program was using the same CPU heavily (load average 9–10 on
this Mac), so they move by several seconds between runs; an earlier quiet run, before the arm
fix, took 16.3, 22.1 and 9.7 s.

## Errors

The call fails with a readable message when the story is empty, when it starts like JSON
but isn't valid, when no step is left after cleaning, when the server has no
`OPENAI_API_KEY` for a free-text story, or when GPT-6 Luna can't be reached.
