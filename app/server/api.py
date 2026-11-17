"""What each endpoint does. Formats: README.md, docs/STORY-API.md and docs/SHOW-API.md.

Everything runs on the CPU. ZeroGPU gives visitors without a Hugging Face login about
two minutes of GPU a day, which one show can use up, and MoMask is small enough for the
CPU. start() loads the models once and the endpoints read them from there.
"""

import spaces

import os
import time
from dataclasses import dataclass

import gradio as gr
import torch

from server import APP_DIR
from story import beats, narration
from story.ik import Converter
from story.motion import FPS, Models, generate_features, join
from story.orchestrator import StoryError
from story.outputs import new_dir
from story.pipeline import run_story
from story.retarget import TargetSkeleton
from story.show import run_show
from utils.motion_process import recover_from_ric
from utils.paramUtil import t2m_kinematic_chain
from utils.plot_script import plot_3d_motion

OUTPUT_DIR = "outputs"
XBOT_SKELETON = os.path.join(APP_DIR, "story", "xbot_skeleton.json")
XBOT_GLB = os.path.join(APP_DIR, "client", "docs", "assets", "character", "Xbot.glb")
NUM_JOINTS = 22


@dataclass
class Loaded:
    models: Models
    converter: Converter
    xbot: TargetSkeleton


@spaces.GPU
def gpu_stub():
    """Never called. ZeroGPU won't start a Space unless a @spaces.GPU function is wired
    to a Gradio event, so ui.build() wires this one to a hidden button."""


_loaded = None


def start():
    global _loaded
    from server.models import inside_momask, load_models  # heavy, only at startup

    with inside_momask():
        _loaded = Loaded(load_models(), Converter(), TargetSkeleton.load(XBOT_SKELETON))
    narration.voice()


def loaded():
    if _loaded is None:
        raise RuntimeError("server.api.start() has not run")
    return _loaded


def generate_joints(text, length_frames, seed):
    start_time = time.time()
    features = generate_features(loaded().models, text, length_frames, seed)
    joints = recover_from_ric(torch.from_numpy(features).float(), NUM_JOINTS).numpy()
    return joints, time.time() - start_time


def generate(text, length_frames, seed):
    """/generate -> [BVH, MP4 preview, stats]. length_frames = 0: the model picks."""
    joints, generation_seconds = generate_joints(text, length_frames, seed)

    out_dir = new_dir(OUTPUT_DIR, "generate")
    bvh_path = os.path.join(out_dir, "motion.bvh")
    mp4_path = os.path.join(out_dir, "motion.mp4")

    _, ik_joints = loaded().converter.convert(joints, bvh_path)
    plot_3d_motion(mp4_path, t2m_kinematic_chain, ik_joints, title=text, fps=FPS)

    stats = {
        "frames": len(joints),
        "generation_seconds": round(generation_seconds, 2),
        "bvh_bytes": os.path.getsize(bvh_path),
        "mp4_bytes": os.path.getsize(mp4_path),
    }
    return bvh_path, mp4_path, stats


def story_motion(captions, frames, seed, smooth, seam_captions=None, seam_mask=None):
    models = loaded().models
    clips = [
        generate_features(models, c, f, seed + i)
        for i, (c, f) in enumerate(zip(captions, frames))
    ]
    extra = {"seam_mask": seam_mask} if seam_mask else {}
    return join(models, clips, captions, seed, smooth, seam_captions, **extra)


def tell_story(story, seed, smooth, preview=False):
    """[motion .glb, narration .mp3, timeline, Xbot preview .glb or None]."""
    run = loaded()
    try:
        return run_story(
            story,
            seed,
            smooth,
            story_motion,
            run.converter,
            run.xbot,
            OUTPUT_DIR,
            XBOT_GLB if preview else None,
        )
    except StoryError as error:
        raise gr.Error(str(error)) from None


def story_api(story, seed, smooth):
    """/story -> [motion .glb, narration .mp3, timeline]. See docs/STORY-API.md."""
    motion, voice, timeline, _ = tell_story(story, seed, smooth)
    return motion, voice, timeline


def show_motion(jobs):
    """Every character's motion."""
    models = loaded().models
    results = []
    for job in jobs:
        clips = [
            generate_features(models, c, f, job["seed"] + i)
            for i, (c, f) in enumerate(zip(job["captions"], job["frames"]))
        ]
        results.append(
            join(
                models,
                clips,
                job["captions"],
                job["seed"],
                True,
                job["seam_captions"],
                seam_mask=beats.SEAM_MASK,
            )
        )
    return results


def show_api(story, seed):
    """/show -> [one motion .glb per character, voices .mp3, timeline]. See
    docs/SHOW-API.md."""
    try:
        return run_show(story, seed, show_motion, loaded().converter, OUTPUT_DIR)
    except StoryError as error:
        raise gr.Error(str(error)) from None
