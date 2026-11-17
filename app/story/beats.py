"""Pocoyo-style timing: the narrator and the characters talk, and the characters act in
turns.

The story becomes one row of segments, talk / action / talk / ... Every character gets a
motion for every segment: its action in its own, standing or talking everywhere else.
"""

import numpy as np

from story.motion import FPS, seam_caption, to_frames

SPEECH_LEAD = 0.3  # a segment's first line starts this long after the segment does
SPEECH_GAP = 0.25  # silence between two lines
SPEECH_TAIL = 0.5  # a segment goes on this long after its last line
REACTION_DELAY = 0.15  # a reaction starts this long after the action settles
ACTION_SECONDS = 3.0
# Half of each seam's regenerated stretch, in frames (16 let MoMask jump twice).
SEAM_MASK = 8

# Measured: "stands still" comes out as a T-pose and "talks and gestures" squats.
LISTEN = "a person stands and looks around"
TALK = "a person stands and explains something with hand gestures"


def segments(steps):
    """Talk and action segments: {"kind", "step", "lines" as (step, line) in order}."""
    out, talk = [], []
    for i, step in enumerate(steps):
        lines = step.get("lines", [])
        talk += [
            (i, k)
            for k, line in enumerate(lines)
            if line.get("when", "during") == "before"
        ]
        if talk:
            out.append({"kind": "talk", "step": i, "lines": talk})
        out.append(
            {
                "kind": "action",
                "step": i,
                "lines": [
                    (i, k)
                    for k, line in enumerate(lines)
                    if line.get("when", "during") == "during"
                ],
            }
        )
        talk = [
            (i, k)
            for k, line in enumerate(lines)
            if line.get("when", "during") == "after"
        ]
    if talk:
        out.append({"kind": "talk", "step": len(steps) - 1, "lines": talk})
    return out


def schedule(steps, rows, seconds_of):
    """(frames per segment, start in seconds of each (step, line))."""
    frames, starts = [], {}
    t = 0.0
    for row in rows:
        cursor = t + SPEECH_LEAD
        for key in row["lines"]:
            starts[key] = cursor
            cursor += seconds_of[key] + SPEECH_GAP
        spoken = cursor - SPEECH_GAP - t + SPEECH_TAIL if row["lines"] else 0.0
        if row["kind"] == "action":
            wanted = max(steps[row["step"]].get("seconds", ACTION_SECONDS), spoken)
        else:
            wanted = spoken
        n = to_frames(wanted)
        frames.append(n)
        t += n / FPS
    return frames, starts


def captions(steps, rows, character):
    """What `character` does in each segment."""
    out = []
    for row in rows:
        step = steps[row["step"]]
        if row["kind"] == "action" and step["actor"] == character:
            out.append(step["action"])
            continue
        speaks = any(steps[i]["lines"][k]["who"] == character for i, k in row["lines"])
        out.append(TALK if speaks else LISTEN)
    return out


def seam_captions(rows, caps):
    """The text each seam is regenerated from: "<before> and then <action>" going into
    an action, the talk caption alone going into talk ("jumps and then talks" made
    MoMask jump twice)."""
    out = []
    for k in range(len(rows) - 1):
        if rows[k + 1]["kind"] == "talk":
            out.append(caps[k + 1])
        else:
            out.append(seam_caption(caps[k], caps[k + 1]))
    return out


def settle_time(joints, start, end):
    """When the main movement between frames start and end is over, in seconds: the
    first frame after the peak joint speed where it drops below half of it."""
    speed = np.linalg.norm(np.diff(joints, axis=0), axis=-1).mean(axis=-1) * FPS
    speed = np.convolve(speed, np.ones(3) / 3, mode="same")
    window = speed[start:end]
    if not len(window) or window.max() <= 0:
        return end / FPS
    peak = int(window.argmax())
    calm = np.flatnonzero(window[peak:] < window[peak] / 2)
    return (start + peak + (calm[0] if len(calm) else len(window) - peak)) / FPS


def place_reactions(steps, rows, frames, starts, seconds_of, joints_of):
    """Move each reaction to just after its action settles, inside its own segment."""
    starts = dict(starts)
    bounds = np.concatenate([[0], np.cumsum(frames)])
    settled = {}
    for r, row in enumerate(rows):
        if row["kind"] != "action":
            continue
        actor = steps[row["step"]]["actor"]
        a, b = bounds[r], bounds[r + 1]
        # Look a little past the segment: the seam with the next one is regenerated.
        settled[row["step"]] = settle_time(
            joints_of[actor], a, min(b + FPS // 2, len(joints_of[actor]))
        )
    for r, row in enumerate(rows):
        reactions = [
            key
            for key in row["lines"]
            if steps[key[0]]["lines"][key[1]].get("when") == "after"
        ]
        if row["kind"] != "talk" or not reactions or reactions[0][0] not in settled:
            continue
        first = starts[row["lines"][0]]
        last_end = max(starts[k] + seconds_of[k] for k in row["lines"])
        segment_end = bounds[r + 1] / FPS
        want = settled[reactions[0][0]] + REACTION_DELAY
        # Not before the previous segment's last line ends, not past this segment's end.
        previous = [starts[k] + seconds_of[k] for k in starts if starts[k] < first]
        earliest = (max(previous) + SPEECH_GAP) if previous else 0.0
        shift = min(max(want, earliest) - first, segment_end - 0.1 - last_end)
        for key in row["lines"]:
            starts[key] += shift
    return starts, settled
