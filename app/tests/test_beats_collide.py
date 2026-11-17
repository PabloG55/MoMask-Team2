"""Tests for the show timing (story/beats.py) and arm collisions (story/collide.py). No
MoMask needed."""

import os

import numpy as np
import pytest

from story import beats
from story.motion import FPS, seam_caption, to_frames
from story.retarget import TargetSkeleton, qbetween, read_glb
from tools.body_shapes import body_shapes

CHARACTERS = os.path.join("client", "story", "characters")


STEPS = [
    {
        "actor": "DinoKid",
        "action": "a person waves with the right hand",
        "seconds": 3.0,
        "lines": [
            {"who": "narrator", "text": "Hello, Dino!", "when": "before"},
            {"who": "DinoKid", "text": "Hi!", "when": "during"},
        ],
    },
    {
        "actor": "DinoKid",
        "action": "a person jumps forward",
        "seconds": 2.6,
        "lines": [
            {"who": "DinoKid", "text": "Want to see me jump?", "when": "before"},
            {"who": "narrator", "text": "Yes!", "when": "before"},
            {"who": "narrator", "text": "Wow!", "when": "after"},
            {"who": "DinoKid", "text": "Ta-da!", "when": "after"},
        ],
    },
]
SECONDS_OF = {
    (0, 0): 1.0,
    (0, 1): 0.8,
    (1, 0): 1.2,
    (1, 1): 1.0,
    (1, 2): 1.3,
    (1, 3): 0.6,
}


def test_segments_alternate_talk_and_action():
    rows = beats.segments(STEPS)
    assert [r["kind"] for r in rows] == ["talk", "action", "talk", "action", "talk"]
    assert rows[0]["lines"] == [(0, 0)]
    assert rows[1]["lines"] == [(0, 1)]
    assert rows[2]["lines"] == [(1, 0), (1, 1)]
    assert rows[3]["lines"] == []
    assert rows[4]["lines"] == [(1, 2), (1, 3)]


def test_every_planned_line_fits_its_segment():
    rows = beats.segments(STEPS)
    frames, starts = beats.schedule(STEPS, rows, SECONDS_OF)
    bounds = np.concatenate([[0], np.cumsum(frames)]) / FPS
    for r, row in enumerate(rows):
        previous_end = None
        for key in row["lines"]:
            assert starts[key] >= bounds[r] + beats.SPEECH_LEAD - 1e-9
            assert starts[key] + SECONDS_OF[key] <= bounds[r + 1]
            if previous_end is not None:
                assert starts[key] >= previous_end + beats.SPEECH_GAP - 1e-9
            previous_end = starts[key] + SECONDS_OF[key]
    assert frames[3] == to_frames(2.6)


def test_captions_and_seams():
    rows = beats.segments(STEPS)
    dino = beats.captions(STEPS, rows, "DinoKid")
    assert dino == [
        beats.LISTEN,
        STEPS[0]["action"],
        beats.TALK,
        STEPS[1]["action"],
        beats.TALK,
    ]
    assert beats.captions(STEPS, rows, "Teddy") == [beats.LISTEN] * 5
    seams = beats.seam_captions(rows, dino)
    assert seams[0] == seam_caption(beats.LISTEN, STEPS[0]["action"])
    # "jumps and then talks" made MoMask jump twice.
    assert seams[1] == beats.TALK and seams[3] == beats.TALK
    assert seams[2] == seam_caption(beats.TALK, STEPS[1]["action"])


def burst(frames, start, end, step=0.05):
    """Joints that stand still, all move along x from start to end, then stop."""
    joints = np.zeros((frames, 22, 3))
    joints[..., 0] = (step * np.clip(np.arange(frames) - start, 0, end - start))[
        :, None
    ]
    return joints


def test_settle_time_is_the_end_of_the_burst():
    assert beats.settle_time(burst(60, 20, 30), 0, 60) == pytest.approx(30 / FPS)
    still = np.zeros((60, 22, 3))
    assert beats.settle_time(still, 0, 40) == pytest.approx(40 / FPS)


def test_reaction_starts_when_the_jump_lands():
    rows = beats.segments(STEPS)
    frames, planned = beats.schedule(STEPS, rows, SECONDS_OF)
    bounds = np.concatenate([[0], np.cumsum(frames)])
    jump = bounds[3]
    joints = burst(int(bounds[-1]), jump + 30, jump + 40)
    starts, settled = beats.place_reactions(
        STEPS, rows, frames, planned, SECONDS_OF, {"DinoKid": joints}
    )
    assert settled[1] == pytest.approx((jump + 40) / FPS)
    assert starts[(1, 2)] == pytest.approx(settled[1] + beats.REACTION_DELAY)
    assert starts[(1, 3)] - starts[(1, 2)] == pytest.approx(
        planned[(1, 3)] - planned[(1, 2)]
    )
    for key in [(0, 0), (0, 1), (1, 0), (1, 1)]:
        assert starts[key] == planned[key]


def from_vrm(name):
    path = os.path.join(CHARACTERS, f"{name}.vrm")
    if not os.path.exists(path):
        pytest.skip("characters not here")
    skeleton = TargetSkeleton.from_vrm(path)
    skeleton.body = body_shapes(*read_glb(path), skeleton)
    return skeleton


@pytest.fixture(scope="module")
def dino():
    return from_vrm("DinoKid")


def rest_pose(skeleton, frames=5):
    rotations = np.zeros((frames, len(skeleton.names), 4))
    rotations[..., 0] = 1
    hips = np.repeat(
        skeleton.offsets[None, skeleton.index[skeleton.hips]], frames, axis=0
    )
    return rotations, hips


def test_vrm_gets_a_head_shape_and_both_arms(dino):
    body = dino.body
    assert any(
        s["against"] == "arm" and s["bone"].endswith("Head") for s in body["shapes"]
    )
    assert any(s["against"] == "forearm" for s in body["shapes"])
    parts = {s["bone"].split(":")[-1] for s in body["shapes"]}
    assert {"Hips", "LeftUpLeg", "RightUpLeg"} <= parts
    assert set(body["arms"]) == {"Left", "Right"}
    assert all(r > 0 for s in body["shapes"] for r in s["radii"])
    assert all(s["across"] >= 2 and s["along"] >= 2 for s in body["shapes"])


def test_rest_pose_is_clear_and_left_alone(dino):
    from story.collide import avoid_self_penetration, worst_depth

    rotations, hips = rest_pose(dino)
    assert worst_depth(dino, rotations, hips) < 0
    fixed, stats = avoid_self_penetration(dino, rotations, hips)
    assert np.allclose(fixed, rotations)
    assert stats["frames_fixed"] == {"Left": 0, "Right": 0}


@pytest.mark.parametrize("aim", ["head", "up"])
def test_an_arm_through_the_head_is_pushed_out(dino, aim):
    """Arms raised through a chibi head come most of the way out, within MAX_DEGREES."""
    from story.collide import MAX_DEGREES, avoid_self_penetration, worst_depth

    rotations, hips = rest_pose(dino)
    positions = dino.forward_kinematics(rotations, hips)
    arm, forearm = dino.bone("LeftArm"), dino.bone("LeftForeArm")
    head = next(s for s in dino.body["shapes"] if s["against"] == "arm")
    if aim == "head":
        target = (
            positions[0, dino.index[head["bone"]]]
            + np.array(head["center"])
            - positions[0, arm]
        )
    else:
        target = np.array([0.0, 1.0, 0.0])
    rotations[:, arm] = qbetween(dino.offsets[forearm], target)
    before = worst_depth(dino, rotations, hips)
    assert before > 0.3

    fixed, stats = avoid_self_penetration(dino, rotations, hips)
    assert worst_depth(dino, fixed, hips) < before / 3
    assert stats["frames_fixed"]["Left"] == len(rotations)
    assert stats["max_degrees"]["Left"] <= MAX_DEGREES + 0.5
    # Only the shoulder turns: elbow, wrist and everything else keep their rotations.
    others = [b for b in range(len(dino.names)) if b != arm]
    assert np.allclose(fixed[:, others], rotations[:, others])
    assert np.allclose(np.linalg.norm(fixed, axis=-1), 1)


def test_a_hand_in_the_belly_comes_out_without_crossing():
    from story.collide import MAX_DEGREES, avoid_self_penetration, worst_depth

    astro = from_vrm("Astronaut")
    rotations, hips = rest_pose(astro)
    positions = astro.forward_kinematics(rotations, hips)
    arm, forearm = astro.bone("RightArm"), astro.bone("RightForeArm")
    belly = next(s for s in astro.body["shapes"] if s["bone"].endswith("Hips"))
    target = (
        positions[0, astro.index[belly["bone"]]]
        + np.array(belly["center"])
        - positions[0, arm]
    )
    rotations[:, arm] = qbetween(astro.offsets[forearm], target)
    assert worst_depth(astro, rotations, hips) > 0.3

    fixed, stats = avoid_self_penetration(astro, rotations, hips)
    assert worst_depth(astro, fixed, hips) <= 0.01
    assert stats["max_degrees"]["Right"] < MAX_DEGREES


def test_soften_nods_halves_a_nod_and_keeps_a_turn():
    from types import SimpleNamespace

    from story.retarget import soften_nods
    from visualization.Quaternions import Quaternions

    def about(axis, degrees):
        half = np.radians(degrees) / 2
        return np.concatenate([[np.cos(half)], np.sin(half) * np.asarray(axis, float)])

    def degrees(q):
        return np.degrees(2 * np.arccos(np.clip(abs(q[0]), 0, 1)))

    q = np.zeros((3, 3, 4))
    q[..., 0] = 1
    q[0, 2] = about([1, 0, 0], 50)  # nod back
    q[1, 2] = about([0, 1, 0], 60)  # turn to the side
    q[2, 2] = about([np.sqrt(0.5), np.sqrt(0.5), 0], 40)  # both at once
    anim = SimpleNamespace(
        names=["Hips", "Neck", "Head"],
        rotations=Quaternions(q.copy()),
        offsets=np.array([[0, 0, 0], [0, 0.1, 0], [0, 0.1, 0]], float),
    )
    out = soften_nods(anim).rotations.qs
    assert degrees(out[0, 2]) == pytest.approx(25, abs=0.1)
    assert np.allclose(out[1, 2], q[1, 2])
    assert degrees(out[2, 2]) < 40
    assert np.allclose(np.linalg.norm(out, axis=-1), 1)
