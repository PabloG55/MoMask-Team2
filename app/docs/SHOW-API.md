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
so the same motion can put a hand inside the head or the belly. These are the fixes:

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
- **Hips start from where the body faces** (`app/story/ik.py`). MoMask's converter starts every
  frame's IK from zero rotations. Once the body has turned more than about 90°, the hips can
  settle either way round, so an arm or a leg twists half a turn from one frame to the next.
  Starting the hips from the way the shoulders and hips face keeps every frame close.
- **Feet stay flat** (`level` in `app/story/retarget.py`). The IK only knows where the toe is,
  so it leaves the roll of the foot to chance, and on the floor that shows as a foot standing
  on its edge. Each foot keeps MoMask's turn around Y and its toe pitch (heel and toe lifts
  stay) and loses the roll.
- **Arms stay out of the body** (`app/story/collide.py`). Each character's head, chest, belly and
  thighs are superquadrics fitted to its own mesh by `app/tools/character_skeletons.py`, stored in
  `app/story/characters/<Name>.json`. On a frame where an arm enters any of them, the arm turns at
  the shoulder by the smallest angle that clears all of them at once, and at the elbow when the
  shoulder is not enough (a hand on a big helmet). The turns ease in and out over the
  neighbouring frames. Each frame only keeps as much of its turn as leaves the arm no deeper
  than before and no jumpier than MoMask made it (25° a frame, or MoMask's own step if that
  is bigger). The shoulder turns at most 75° and the elbow 90°. `stats.arms_fixed` gives, per
  arm, how many frames had it inside the body and the largest turn at the shoulder.

Measured on 15 actions × 2 seeds × all 10 characters (300 motions, 2026-11-17), before and
after the last three fixes:

| | Before | After |
|---|---|---|
| Arm surface inside the body, worst motion | 19.1 cm | 9.3 cm |
| Same, 90% of motions under | 1.5 cm | 0.3 cm |
| Motions with an arm more than 2 cm in | 25 | 16 |
| Biggest arm jump between two frames | 77.7° | 45.1° (the same as with no arm fix at all) |
| Most the arm fix adds to a jump | 43.1° | 10.3° |
| Biggest foot jump between two frames | 103° | 28.7° |
| Foot roll on the floor, 90% of motions under (median per motion) | 26.1° | 14.4° |
| Deepest a foot goes under the floor | 3.7 cm | 2.8 cm |

What is left: 14 of the 16 are Astronaut and DinoKid, the two biggest heads, mostly with a hand
on or over the head (scratching, clapping, waving), where clearing it would take more than the
75° the shoulder may turn, or a jump the rule above does not allow. The feet still slide as much
as on MoMask's own skeleton (median 3.6 cm/s).

So the problem was the retarget onto a chibi body, not the model.

## Measured

On a Mac CPU, JSON shows (no LLM):

| Show | Length | Server time | Sent to the viewer | Same show as 720p video (2.5 Mbit/s) |
|---|---|---|---|---|
| Dino's big jump (2 characters) | 31.6 s | 13.5 s | 470 KB | 9.9 MB (21×) |
| A walk on the moon (3) | 30.0 s | 16.3 s | 545 KB | 9.4 MB (17×) |
| El baile de Froggy (2, Spanish) | 19.2 s | 6.6 s | 288 KB | 6.0 MB (21×) |

"Sent" is the motion `.glb`s gzipped, plus the `.mp3` and the timeline. The same Dino show
rendered to an actual 720p H.264 file (crf 20) is 5.5 MB. About a third of the server time is
IK and retargeting; IK now runs 10 iterations instead of 100 (the authors' default, just as
close), which takes about 0.7 s off each character.
Keeping the arms out of the body adds about 0.2 s per character, because it checks every
frame at once. These times are from 2026-11-17; on 2026-11-15, with another program using the
same CPU heavily, the same shows took 27.9, 32.6 and 11.7 s.

## Errors

The call fails with a readable message when the story is empty, when it starts like JSON
but isn't valid, when no step is left after cleaning, when the server has no
`OPENAI_API_KEY` for a free-text story, or when GPT-6 Luna can't be reached.
