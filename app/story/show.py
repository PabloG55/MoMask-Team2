"""Show mode end to end: story -> director's plan -> voices -> one motion per character
-> the files the player in client/story/ plays."""

import json
import os
import subprocess
import time

import numpy as np

from story import beats, narration
from story.collide import avoid_self_penetration
from story.director import plan_show
from story.gltf import animation_glb
from story.motion import FPS, IK_ITERATIONS, to_joints
from story.outputs import gzip_size, new_dir
from story.retarget import TargetSkeleton, retarget, soften_nods

# <Name>.json, from tools/character_skeletons.py
SKELETONS = os.path.join(os.path.dirname(__file__), "characters")
SR = narration.SAMPLE_RATE
LINE_GAP_AT_END = 0.4

# (English voice, pitch, Spanish voice, pitch, effect). Kokoro has only three Spanish
# voices, so the pitch tells the characters apart.
VOICES = {
    "narrator": ("bm_george", 1.0, "em_alex", 1.0, None),
    "Astronaut": ("am_echo", 1.18, "em_alex", 1.25, None),
    "CoolAlien": ("am_fenrir", 1.35, "em_santa", 1.4, None),
    "DinoKid": ("am_puck", 1.3, "em_alex", 1.35, None),
    "Froggy": ("am_santa", 1.15, "em_santa", 1.15, None),
    "Hugo": ("am_onyx", 0.85, "em_santa", 0.85, None),
    "Jimmy": ("am_liam", 1.05, "em_alex", 1.05, None),
    "Kyle": ("am_michael", 1.0, "em_alex", 0.95, None),
    "LilBro": ("af_bella", 1.35, "ef_dora", 1.35, None),
    "Polybot": ("am_eric", 1.05, "em_alex", 1.05, "robot"),
    "Teddy": ("bm_lewis", 0.92, "em_santa", 0.92, None),
}
LANG_CODE = {"a": "en-us", "b": "en-gb", "e": "es"}
EFFECTS = {
    "robot": "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75"
}

# How much room each character takes side by side (metres, body width plus a little).
WIDTH = {
    "Astronaut": 0.85,
    "CoolAlien": 1.0,
    "DinoKid": 0.85,
    "Froggy": 1.15,
    "Hugo": 1.1,
    "Jimmy": 0.95,
    "Kyle": 0.95,
    "LilBro": 0.7,
    "Polybot": 1.05,
    "Teddy": 1.25,
}
SLOT_GAP = 0.7

MIN_SHOT = 1.0  # seconds; a cut sooner than this after the last one is skipped
CUT_LEAD = 0.2  # cut to a speaker this long before the line starts
NOD_KEEP = 0.5  # share of MoMask's head nods the characters keep (soften_nods)


def say(text, who, language="en"):
    """One line in `who`'s voice -> float32 samples at 24 kHz."""
    en, en_pitch, es, es_pitch, effect = VOICES.get(who, VOICES["narrator"])
    name, pitch = (es, es_pitch) if language == "es" else (en, en_pitch)
    samples, rate = narration.voice().create(
        text, voice=name, speed=narration.SPEED, lang=LANG_CODE[name[0]]
    )
    assert rate == SR, rate
    samples = narration.trim(np.asarray(samples, np.float32))
    filters = []
    if pitch != 1.0:  # higher or lower voice, same length
        filters.append(
            f"asetrate={int(SR * pitch)},aresample={SR},atempo={1 / pitch:.5f}"
        )
    if effect:
        filters.append(EFFECTS[effect])
    if filters and len(samples):
        out = subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-f",
                "f32le",
                "-ar",
                str(SR),
                "-ac",
                "1",
                "-i",
                "pipe:0",
                "-af",
                ",".join(filters),
                "-f",
                "f32le",
                "pipe:1",
            ],
            input=samples.tobytes(),
            capture_output=True,
            check=True,
        ).stdout
        samples = np.frombuffer(out, np.float32).copy()
    return samples


MOUTH_FPS = 30


def mouth(track):
    """A character's voice track -> how open its mouth is, 30 times a second, as aa / ee
    / oh (0-100)."""
    hop = SR // MOUTH_FPS
    n = len(track) // hop
    if n == 0:
        return {"fps": MOUTH_FPS, "aa": [], "ee": [], "oh": []}
    win = track[: n * hop].reshape(n, hop)
    rms = np.sqrt((win**2).mean(axis=1))
    spec = np.abs(np.fft.rfft(win * np.hanning(hop), axis=1))
    freqs = np.fft.rfftfreq(hop, 1 / SR)
    centroid = (spec * freqs).sum(1) / (spec.sum(1) + 1e-9)
    loud = rms > 0.01
    ref = np.percentile(rms[loud], 90) if loud.any() else 1.0
    opened = np.clip((rms / ref - 0.08) / 0.92, 0, 1) ** 0.7
    smooth = np.zeros_like(opened)
    for i in range(n):  # opens at once, closes over ~3 frames
        smooth[i] = max(opened[i], (smooth[i - 1] if i else 0) * 0.55)
    lo, hi = np.percentile(centroid[loud], [20, 80]) if loud.any() else (1000.0, 3000.0)
    bright = np.clip((centroid - lo) / (hi - lo + 1e-9), 0, 1)
    as_int = lambda x: np.round(x * 100).astype(int).tolist()  # noqa: E731
    return {
        "fps": MOUTH_FPS,
        "aa": as_int(smooth * (1 - 0.6 * bright) * (1 - 0.5 * (1 - bright))),
        "ee": as_int(smooth * bright * 0.8),
        "oh": as_int(smooth * (1 - bright) * 0.7),
    }


def slots(cast):
    """Where each character stands (x, metres), side by side and centred on 0."""
    xs = [0.0]
    for a, b in zip(cast, cast[1:]):
        xs.append(xs[-1] + (WIDTH[a] + WIDTH[b]) / 2 + SLOT_GAP)
    middle = (xs[0] + xs[-1]) / 2
    return [round(x - middle, 3) for x in xs]


def plan_shots(show, rows, frames, starts):
    """The camera: the director's shot for each action, a close-up of whoever speaks
    around it. Returns [{"start", "end", "type", "target"}]; target None is a wide shot.
    """
    steps, cast = show["steps"], show["cast"]
    bounds = np.concatenate([[0], np.cumsum(frames)]) / FPS
    cuts = [(0.0, "wide", None, False)]
    for r, row in enumerate(rows):
        step = steps[row["step"]]
        if row["kind"] == "action":
            cuts.append((bounds[r], step["shot"], step["actor"], True))
            continue
        for i, k in row["lines"]:
            line, actor = steps[i]["lines"][k], steps[i]["actor"]
            at = max(0.0, starts[(i, k)] - CUT_LEAD)
            if line["who"] != "narrator":
                cuts.append((at, "close", line["who"], False))
            elif line["when"] == "after" or len(cast) == 1:
                cuts.append((at, "medium", actor, False))
            else:
                cuts.append((at, "wide", None, False))
    cuts.sort(key=lambda c: c[0])

    kept = []
    for at, kind, target, is_action in cuts:
        if kept and (kind, target) == kept[-1][1:3]:
            continue
        if kept and at - kept[-1][0] < MIN_SHOT:
            # The action's shot matters more than a talk cut just before it.
            if is_action:
                kept[-1] = (kept[-1][0], kind, target, True)
            continue
        kept.append((at, kind, target, is_action))
    end = float(bounds[-1])
    return [
        {
            "start": round(a, 2),
            "end": round(kept[i + 1][0] if i + 1 < len(kept) else end, 2),
            "type": kind,
            "target": target,
        }
        for i, (a, kind, target, _) in enumerate(kept)
    ]


def load_skeleton(name, folder=SKELETONS):
    return TargetSkeleton.load(os.path.join(folder, f"{name}.json"))


def run_show(
    story,
    seed,
    make_motion,
    converter,
    out_root="outputs",
    llm_client=None,
    skeletons=SKELETONS,
):
    """Returns (motion .glb per cast member, voices .mp3, timeline).

    make_motion(jobs) runs MoMask, one job per character:
    {"captions", "frames", "seam_captions", "seed"}.
    """
    timings, started = {}, time.time()

    # 1. Story -> show (GPT-6 Luna, or the JSON as given).
    show, planner = plan_show(story, llm_client)
    steps, cast, language = show["steps"], show["cast"], show["language"]
    timings["plan"] = planner["seconds"]

    out_dir = new_dir(out_root, "show")

    # 2. Every line, in its speaker's voice, so its length is known.
    t = time.time()
    audio = {
        (i, k): say(line["text"], line["who"], language)
        for i, step in enumerate(steps)
        for k, line in enumerate(step["lines"])
    }
    seconds_of = {key: len(a) / SR for key, a in audio.items()}
    timings["voices"] = round(time.time() - t, 2)

    # 3. Talk / action segments, and what every character does in each one.
    rows = beats.segments(steps)
    frames, planned = beats.schedule(steps, rows, seconds_of)
    jobs = []
    for c, name in enumerate(cast):
        captions = beats.captions(steps, rows, name)
        # A different seed per character, so two characters listening don't move in
        # step.
        jobs.append(
            {
                "captions": captions,
                "frames": frames,
                "seam_captions": beats.seam_captions(rows, captions),
                "seed": int(seed) + 1000 * c,
            }
        )

    t = time.time()
    results = make_motion(jobs)
    timings["motion"] = round(time.time() - t, 2)
    joints = {
        name: to_joints(features) for name, (features, _, _) in zip(cast, results)
    }

    # 4. Reactions start where their action lands.
    starts, settled = beats.place_reactions(
        steps, rows, frames, planned, seconds_of, joints
    )

    # 5. Each character: joints -> BVH -> softer nods -> its skeleton, arms out of its
    # body -> .glb
    t = time.time()
    motions, cast_info, collide_stats, bvh_bytes = [], [], {}, 0
    for name, x in zip(cast, slots(cast)):
        bvh_path = os.path.join(out_dir, f"{name}.bvh")
        # No foot IK: remove_fs pins the ankle and the toe separately and can swing a
        # foot round.
        anim, _ = converter.convert(
            joints[name], filename=bvh_path, iterations=IK_ITERATIONS, foot_ik=False
        )
        bvh_bytes += os.path.getsize(bvh_path)
        skeleton = load_skeleton(name, skeletons)
        rotations, hips = retarget(soften_nods(anim, NOD_KEEP), skeleton)
        rotations, collide_stats[name] = avoid_self_penetration(
            skeleton, rotations, hips
        )
        path = animation_glb(
            os.path.join(out_dir, f"{name}.glb"),
            skeleton,
            rotations,
            hips,
            FPS,
            name=name,
        )
        motions.append(path)
        cast_info.append({"name": name, "x": x, "motion": os.path.basename(path)})
    timings["ik_retarget"] = round(time.time() - t, 2)

    # 6. One audio track (second 0 = frame 0), and each character's mouth from its own
    # lines.
    t = time.time()
    motion_seconds = len(results[0][0]) / FPS
    placed = [(starts[key], a) for key, a in audio.items() if len(a)]
    duration = max(
        [motion_seconds] + [s + len(a) / SR + LINE_GAP_AT_END for s, a in placed]
    )
    mp3_path = narration.to_mp3(
        narration.mix(placed, duration), os.path.join(out_dir, "voices.mp3")
    )
    mouths = {}
    for name in cast:
        own = [
            (starts[(i, k)], audio[(i, k)])
            for i, s in enumerate(steps)
            for k, line in enumerate(s["lines"])
            if line["who"] == name and len(audio[(i, k)])
        ]
        mouths[name] = mouth(narration.mix(own, duration))
    timings["audio"] = round(time.time() - t, 2)
    timings["total"] = round(time.time() - started, 2)

    bounds = np.concatenate([[0], np.cumsum(frames)]) / FPS
    timeline = {
        "version": 2,
        "fps": FPS,
        "title": show["title"],
        "language": language,
        "set": show["set"],
        "light": show["light"],
        "duration": round(duration, 2),
        "motion_duration": round(motion_seconds, 2),
        "cast": cast_info,
        "steps": [
            {
                "actor": s["actor"],
                "action": s["action"],
                "shot": s["shot"],
                "settled": round(float(settled[i]), 2) if i in settled else None,
            }
            for i, s in enumerate(steps)
        ],
        "segments": [
            {
                "kind": row["kind"],
                "step": row["step"],
                "start": round(bounds[r], 2),
                "end": round(bounds[r + 1], 2),
                "captions": {name: job["captions"][r] for name, job in zip(cast, jobs)},
            }
            for r, row in enumerate(rows)
        ],
        "lines": sorted(
            [
                {
                    "who": line["who"],
                    "text": line["text"],
                    "when": line["when"],
                    "step": i,
                    "start": round(starts[(i, k)], 2),
                    "end": round(starts[(i, k)] + seconds_of[(i, k)], 2),
                }
                for i, s in enumerate(steps)
                for k, line in enumerate(s["lines"])
            ],
            key=lambda line: line["start"],
        ),
        "shots": plan_shots(show, rows, frames, starts),
        "transitions": [
            {"start": round(tr["start"] / FPS, 2), "end": round(tr["end"] / FPS, 2)}
            for tr in results[0][2]
        ],
        "mouth": mouths,
    }
    plan_json = json.dumps(
        {k: show[k] for k in ("title", "language", "set", "light", "cast", "steps")}
    ).encode()
    timeline["stats"] = {
        "planner": planner["planner"],
        "llm_tokens": {
            "input": planner.get("input_tokens"),
            "output": planner.get("output_tokens"),
        },
        "seconds": timings,
        "frames": int(len(results[0][0])),
        "arms_fixed": collide_stats,
        "bytes": {
            "story_text": len(story.encode()),
            "plan_json": len(plan_json),
            "motion_glb": sum(os.path.getsize(p) for p in motions),
            "motion_glb_gzip": sum(gzip_size(p) for p in motions),
            "bvh": bvh_bytes,
            "voices_mp3": os.path.getsize(mp3_path),
            "timeline_json": 0,
        },
        "dropped_steps": show["dropped_steps"],
    }
    timeline["stats"]["bytes"]["timeline_json"] = len(json.dumps(timeline).encode())
    with open(os.path.join(out_dir, "timeline.json"), "w") as f:
        json.dump(timeline, f)
    return motions, mp3_path, timeline
