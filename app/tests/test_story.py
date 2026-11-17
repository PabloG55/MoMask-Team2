"""Story mode tests. No MoMask needed: .venv/bin/python -m pytest tests -q"""

import json
import os
import struct
from types import SimpleNamespace

import numpy as np
import pytest

import visualization.Animation as Animation
import visualization.BVH_mod as BVH
from visualization.Quaternions import Quaternions

from story import narration
from story.gltf import animation_glb
from story.motion import (
    FPS,
    MAX_FRAMES,
    MIN_FRAMES,
    seam_caption,
    speed_changes,
    to_frames,
)
from story.orchestrator import StoryError, clean_action, plan_story
from story.pipeline import SPEECH_GAP, SPEECH_LEAD, schedule
from story.retarget import (
    BONE_MAP,
    DIRECTION_CHILD,
    TargetSkeleton,
    level,
    qbetween,
    qrotate,
    read_glb,
    retarget,
)


@pytest.fixture(scope="module")
def skeleton():
    return TargetSkeleton.load("story/xbot_skeleton.json")


def random_pose(frames=30, seed=0):
    """MoMask's template skeleton with random joint rotations and a moving root."""
    anim = BVH.load(os.path.join(os.path.dirname(BVH.__file__), "data", "template.bvh"))
    rng = np.random.default_rng(seed)
    joints = len(anim.parents)
    axis = rng.normal(size=(frames, joints, 3))
    angle = rng.uniform(-1.2, 1.2, size=(frames, joints))
    anim.rotations = Quaternions.from_angle_axis(
        angle, axis / np.linalg.norm(axis, axis=-1, keepdims=True)
    )
    anim.positions = np.repeat(anim.offsets[None], frames, axis=0)
    anim.positions[:, 0] = np.c_[
        np.linspace(0, 1, frames), np.full(frames, 0.95), np.zeros(frames)
    ]
    return anim


def test_qbetween_turns_u_into_v():
    rng = np.random.default_rng(1)
    for _ in range(50):
        u, v = rng.normal(size=3), rng.normal(size=3)
        q = qbetween(u, v)
        assert np.allclose(
            qrotate(q, u / np.linalg.norm(u)), v / np.linalg.norm(v), atol=1e-9
        )


def test_skeleton_json_matches_the_glb(skeleton):
    glb = "client/docs/assets/character/Xbot.glb"
    if not os.path.exists(glb):
        pytest.skip("client folder not here")
    from_glb = TargetSkeleton.from_glb(glb)
    assert from_glb.names == skeleton.names and from_glb.parents == skeleton.parents
    assert np.allclose(from_glb.offsets, skeleton.offsets, atol=1e-4)


def test_every_xbot_bone_points_where_the_momask_bone_points(skeleton):
    """All but the feet, which start from Xbot's own rest bend (see the next test)."""
    anim = random_pose()
    rotations, hips = retarget(anim, skeleton)
    source = Animation.positions_global(anim)
    target = skeleton.forward_kinematics(rotations, hips)
    names = list(anim.names)
    for bone, child in DIRECTION_CHILD.items():
        if bone.endswith("Foot"):
            continue
        s = source[:, names.index(child)] - source[:, names.index(bone)]
        t = (
            target[:, skeleton.index[BONE_MAP[child]]]
            - target[:, skeleton.index[BONE_MAP[bone]]]
        )
        cos = (
            np.sum(s * t, -1) / np.linalg.norm(s, axis=-1) / np.linalg.norm(t, axis=-1)
        )
        assert cos.min() > 0.99999, bone


def test_a_level_foot_keeps_its_toe_pitch_and_loses_its_roll():
    from story.retarget import qaxis, qmul

    rng = np.random.default_rng(0)
    n = 200
    up = np.array([0.0, 1.0, 0.0])
    toe = np.array([0.02, -0.05, 0.12])
    across = np.array([toe[2], 0.0, -toe[0]]) / np.hypot(toe[0], toe[2])
    yaw = qaxis(up, rng.uniform(-np.pi, np.pi, n))
    pitch = qaxis(across, rng.uniform(-np.radians(40), np.radians(40), n))

    # A foot that only turns and pitches is left as it is.
    flat = level(qmul(yaw, pitch), toe)
    assert np.allclose(np.abs(np.sum(flat * qmul(yaw, pitch), -1)), 1)

    # Any other tilt: the toe keeps its pitch and the sole ends up level.
    tilt = rng.uniform(0, 2 * np.pi, n)
    axes = np.stack([np.cos(tilt), np.zeros(n), np.sin(tilt)], axis=1)
    rotations = qmul(yaw, qaxis(axes, rng.uniform(-np.radians(40), np.radians(40), n)))
    flat = level(rotations, toe)
    unit = np.broadcast_to(toe / np.linalg.norm(toe), (n, 3))
    assert np.allclose(qrotate(flat, unit)[:, 1], qrotate(rotations, unit)[:, 1])
    assert np.allclose(qrotate(flat, np.broadcast_to(across, (n, 3)))[:, 1], 0)


def test_feet_end_up_on_the_floor(skeleton):
    anim = random_pose()
    rotations, hips = retarget(anim, skeleton)
    positions = skeleton.forward_kinematics(rotations, hips)
    toes = positions[
        :,
        [
            skeleton.index["mixamorig:LeftToeBase"],
            skeleton.index["mixamorig:RightToeBase"],
        ],
        1,
    ]
    assert abs(np.percentile(toes.min(axis=1), 5)) < 1e-6


def test_rotations_are_unit_and_continuous(skeleton):
    rotations, _ = retarget(random_pose(), skeleton)
    assert np.allclose(np.linalg.norm(rotations, axis=-1), 1, atol=1e-9)
    assert (np.sum(rotations[1:] * rotations[:-1], -1) >= 0).all()


def test_animation_glb_reads_back(tmp_path, skeleton):
    rotations, hips = retarget(random_pose(frames=40), skeleton)
    path = animation_glb(str(tmp_path / "m.glb"), skeleton, rotations, hips, FPS)
    data = open(path, "rb").read()
    magic, version, length = struct.unpack("<III", data[:12])
    assert (magic, version, length) == (0x46546C67, 2, len(data))

    gltf, binary = read_glb(path)
    assert len(gltf["nodes"]) == len(skeleton.names) + 1  # bones + Armature
    clip = gltf["animations"][0]
    times = gltf["accessors"][clip["samplers"][0]["input"]]
    assert times["count"] == 40 and times["max"][0] == pytest.approx(39 / FPS)

    # Decode one quantized rotation track and compare with what went in.
    for channel in clip["channels"]:
        if channel["target"]["path"] != "rotation":
            continue
        accessor = gltf["accessors"][clip["samplers"][channel["sampler"]]["output"]]
        view = gltf["bufferViews"][accessor["bufferView"]]
        raw = np.frombuffer(
            binary, np.int16, accessor["count"] * 4, view["byteOffset"]
        ).reshape(-1, 4)
        bone = skeleton.names.index(gltf["nodes"][channel["target"]["node"]]["name"])
        expected = rotations[:, bone][:, [1, 2, 3, 0]]
        assert np.abs(raw / 32767 - expected).max() < 1e-4
        break
    hips_tracks = [c for c in clip["channels"] if c["target"]["path"] == "translation"]
    assert len(hips_tracks) == 1


def test_json_story_skips_the_llm():
    story = json.dumps(
        [
            {"action": "walks forward", "narration": "Off she goes.", "seconds": 40},
            {"action": "A person waves.", "seconds": "x"},
        ]
    )
    plan, info = plan_story(story)
    assert info["planner"] == "json"
    assert [s["action"] for s in plan["steps"]] == [
        "a person walks forward",
        "a person waves",
    ]
    assert plan["steps"][0]["seconds"] == 9.8 and plan["steps"][1]["seconds"] == 4.0


def test_too_many_steps_are_dropped():
    plan, _ = plan_story(
        json.dumps([{"action": f"a person jumps {i}"} for i in range(9)])
    )
    assert len(plan["steps"]) == 6 and plan["dropped_steps"] == 3


@pytest.mark.parametrize(
    "story, message",
    [
        ("", "Write a story"),
        ('[{"action": ', "isn't valid JSON"),
        ("[]", "no steps"),
    ],
)
def test_bad_stories_say_why(story, message):
    with pytest.raises(StoryError, match=message):
        plan_story(story)


def test_prose_without_a_key_explains_the_json_option(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(StoryError, match="JSON list"):
        plan_story("A boy walks to school.")


def test_llm_answer_is_cleaned():
    answer = {
        "title": "Bus",
        "language": "en",
        "steps": [
            {"action": "She runs to the bus", "narration": "Late again.", "seconds": 1}
        ],
    }

    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["text"]["format"]["strict"] is True
            return SimpleNamespace(
                output_text=json.dumps(answer),
                usage=SimpleNamespace(input_tokens=500, output_tokens=60),
            )

    plan, info = plan_story(
        "Ana runs for the bus.", client=SimpleNamespace(responses=FakeResponses())
    )
    assert plan["steps"][0]["action"] == "a person runs to the bus"
    assert plan["steps"][0]["seconds"] == 2.4
    assert info["output_tokens"] == 60


def test_clean_action_keeps_humanml3d_style():
    assert clean_action("The person sits down.") == "the person sits down"
    assert (
        clean_action("he kicks with the left leg") == "a person kicks with the left leg"
    )


def test_seam_caption():
    assert (
        seam_caption("a person walks", "a person waves")
        == "a person walks and then waves"
    )


def test_every_line_fits_inside_its_action():
    steps = [{"seconds": 2.4}, {"seconds": 9.8}, {"seconds": 3.0}]
    frames, starts = schedule(steps, [4.0, 1.0, 0.0])
    assert all(MIN_FRAMES <= f <= MAX_FRAMES and f % 4 == 0 for f in frames)
    action_start = np.concatenate([[0], np.cumsum(frames)[:-1]]) / FPS
    assert starts[0] == pytest.approx(SPEECH_LEAD)
    assert starts[0] + 4.0 <= action_start[1]  # the first action grew to hold its line
    assert starts[1] >= starts[0] + 4.0 + SPEECH_GAP
    assert starts[2] is None


def test_to_frames_limits():
    assert (
        to_frames(0.1) == MIN_FRAMES
        and to_frames(60) == MAX_FRAMES
        and to_frames(4) == 80
    )


def test_speed_changes_spike_at_a_cut():
    smooth = np.cumsum(np.full((40, 22, 3), 0.01), axis=0)
    cut = smooth.copy()
    cut[20:] += 0.2
    assert speed_changes(smooth).max() < 1e-9
    assert speed_changes(cut)[18:20].max() > 0.1


def test_mix_and_mp3(tmp_path):
    tone = (
        np.sin(np.linspace(0, 200 * np.pi, narration.SAMPLE_RATE)).astype(np.float32)
        * 0.5
    )
    track = narration.mix([(0.5, tone), (2.0, tone)], 3.5)
    assert len(track) == int(3.5 * narration.SAMPLE_RATE)
    assert np.abs(track[: narration.SAMPLE_RATE // 4]).max() == 0
    path = narration.to_mp3(track, str(tmp_path / "n.mp3"))
    assert os.path.getsize(path) > 1000


def test_trim_cuts_silence():
    samples = np.concatenate(
        [np.zeros(24000), np.full(2400, 0.2), np.zeros(24000)]
    ).astype(np.float32)
    assert len(narration.trim(samples)) < 2400 + 2 * 0.031 * narration.SAMPLE_RATE
