"""Story mode end to end: story -> steps -> narration -> motion -> the files the client
plays.

The narration comes first, because each action has to last at least as long as its line.
"""

import json
import os
import time

import numpy as np

from story import narration
from story.gltf import animation_glb, character_glb
from story.motion import FPS, speed_changes, to_frames, to_joints
from story.outputs import gzip_size, new_dir
from story.orchestrator import plan_story
from story.retarget import retarget

SPEECH_LEAD = 0.3  # the line starts this long after its action does
SPEECH_GAP = 0.2  # silence between two lines, at least
SPEECH_TAIL = 0.6  # the action goes on this long after its line ends


def schedule(steps, speech_seconds):
    """Each action's length so its line fits, and when each line starts (or None)."""
    frames, starts = [], []
    action_start, last_speech_end = 0.0, -SPEECH_GAP
    for step, speech in zip(steps, speech_seconds):
        seconds = step["seconds"]
        start = None
        if speech > 0:
            start = max(action_start + SPEECH_LEAD, last_speech_end + SPEECH_GAP)
            # Long enough to cover the line, counting any wait behind the previous one.
            seconds = max(seconds, start - action_start + speech + SPEECH_TAIL)
            last_speech_end = start + speech
        n = to_frames(seconds)
        frames.append(n)
        starts.append(start)
        action_start += n / FPS
    return frames, starts


def run_story(
    story,
    seed,
    smooth,
    make_motion,
    converter,
    skeleton,
    out_root="outputs",
    character_glb_path=None,
    llm_client=None,
):
    """Returns (motion .glb, narration .mp3, timeline, preview .glb or None).

    make_motion(captions, frames, seed, smooth) -> (features, bounds, transitions) runs
    MoMask.
    """
    timings = {}
    started = time.time()

    # 1. Story -> steps (GPT-6 Luna, or the JSON list as given).
    plan, planner = plan_story(story, llm_client)
    steps = plan["steps"]
    timings["plan"] = planner["seconds"]

    out_dir = new_dir(out_root, "story")

    # 2. Narration, one line per step, so each line's length is known.
    t = time.time()
    lines = [narration.speak(s["narration"], plan["language"]) for s in steps]
    speech_seconds = [len(line) / narration.SAMPLE_RATE for line in lines]
    timings["narration"] = round(time.time() - t, 2)

    # 3. Motion: one clip per action, joined with smooth transitions.
    frames, speech_starts = schedule(steps, speech_seconds)
    t = time.time()
    features, bounds, transitions = make_motion(
        [s["action"] for s in steps], frames, int(seed), bool(smooth)
    )
    timings["motion"] = round(time.time() - t, 2)

    # 4. Joints -> BVH -> Xbot. No foot IK (see story/show.py).
    t = time.time()
    joints = to_joints(features)
    bvh_path = os.path.join(out_dir, "story.bvh")
    anim, _ = converter.convert(joints, bvh_path)
    timings["ik"] = round(time.time() - t, 2)

    t = time.time()
    rotations, hips = retarget(anim, skeleton)
    glb_path = animation_glb(
        os.path.join(out_dir, "motion.glb"),
        skeleton,
        rotations,
        hips,
        FPS,
        name=plan["title"],
    )
    preview_path = None
    if character_glb_path and os.path.exists(character_glb_path):
        preview_path = character_glb(
            os.path.join(out_dir, "preview.glb"),
            character_glb_path,
            skeleton,
            rotations,
            hips,
            FPS,
            name=plan["title"],
        )
    timings["retarget"] = round(time.time() - t, 2)

    # 5. One narration track, second 0 = frame 0.
    t = time.time()
    duration = len(features) / FPS
    placed = [
        (s, line)
        for s, line in zip(speech_starts, lines)
        if s is not None and len(line)
    ]
    audio_seconds = max(
        [duration] + [s + len(line) / narration.SAMPLE_RATE + 0.3 for s, line in placed]
    )
    mp3_path = narration.to_mp3(
        narration.mix(placed, audio_seconds), os.path.join(out_dir, "narration.mp3")
    )
    timings["audio"] = round(time.time() - t, 2)
    timings["total"] = round(time.time() - started, 2)

    actions = []
    for i, (step, (a, b), start, speech) in enumerate(
        zip(steps, bounds, speech_starts, speech_seconds)
    ):
        actions.append(
            {
                "index": i,
                "action": step["action"],
                "narration": step["narration"],
                "start": round(a / FPS, 2),
                "end": round(b / FPS, 2),
                "speech_start": round(start, 2) if start is not None else None,
                "speech_end": round(start + speech, 2) if start is not None else None,
            }
        )

    plan_json = json.dumps({"title": plan["title"], "steps": steps}).encode()
    stats = {
        "planner": planner["planner"],
        "llm_tokens": {
            "input": planner.get("input_tokens"),
            "output": planner.get("output_tokens"),
        },
        "seconds": timings,
        "frames": int(len(features)),
        "bytes": {
            "story_text": len(story.encode()),
            "plan_json": len(plan_json),
            "narration_text": sum(len(s["narration"].encode()) for s in steps),
            "motion_glb": os.path.getsize(glb_path),
            "motion_glb_gzip": gzip_size(glb_path),
            "bvh": os.path.getsize(bvh_path),
            "bvh_gzip": gzip_size(bvh_path),
            "narration_mp3": os.path.getsize(mp3_path),
        },
        "dropped_steps": plan["dropped_steps"],
    }
    if transitions:
        # Speed change at each seam (cm per frame), raw cut vs regenerated, and the
        # story's median.
        stats["seams"] = {
            "kick_cm": [
                {"before": t["kick_cm_before"], "after": t["kick_cm_after"]}
                for t in transitions
            ],
            "typical_cm": round(100 * float(np.median(speed_changes(joints))), 2),
        }

    timeline = {
        "version": 1,
        "fps": FPS,
        "duration": round(audio_seconds, 2),
        "motion_duration": round(duration, 2),
        "title": plan["title"],
        "language": plan["language"],
        "actions": actions,
        "transitions": [
            {
                "between": t["between"],
                "start": round(t["start"] / FPS, 2),
                "end": round(t["end"] / FPS, 2),
            }
            for t in transitions
        ],
        "stats": stats,
    }
    with open(os.path.join(out_dir, "timeline.json"), "w") as f:
        json.dump(timeline, f, indent=1)
    return glb_path, mp3_path, timeline, preview_path
