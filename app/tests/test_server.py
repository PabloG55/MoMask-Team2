"""Tests for server/ and story/outputs.py. No MoMask needed."""

import os
import sys
import time

import gradio as gr
import numpy as np
import pytest

from server import api, models, ui
from story import outputs


class FakeConverter:
    """Stands in for story.ik.Converter: writes a BVH and records the frames."""

    def __init__(self):
        self.calls = []

    def convert(self, joints, filename):
        self.calls.append(len(joints))
        with open(filename, "w") as f:
            f.write("HIERARCHY\n")
        return None, joints


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    converter = FakeConverter()
    monkeypatch.setattr(
        api, "_loaded", api.Loaded(models=None, converter=converter, xbot=None)
    )
    monkeypatch.setattr(api, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        api,
        "generate_features",
        lambda _models, text, frames, seed: np.zeros(
            (int(frames), models.HUMANML3D_POSE_DIM)
        ),
    )

    def fake_plot(path, chain, joints, title, fps):
        with open(path, "wb") as f:
            f.write(b"mp4")

    monkeypatch.setattr(api, "plot_3d_motion", fake_plot)
    return converter, tmp_path


def test_page_exposes_the_three_apis():
    demo = ui.build()
    public = {fn.api_name for fn in demo.fns.values() if fn.api_visibility == "public"}
    assert public == {"generate", "story", "show"}


def test_the_gpu_stub_is_wired_but_not_public():
    """ZeroGPU looks for a @spaces.GPU function among the page's events at startup."""
    demo = ui.build()
    stub = [fn for fn in demo.fns.values() if fn.fn is api.gpu_stub]
    assert len(stub) == 1 and stub[0].api_visibility == "private"


def test_nothing_is_loaded_before_start():
    assert api._loaded is None
    with pytest.raises(RuntimeError, match="start"):
        api.loaded()


def test_generate_writes_each_request_to_its_own_folder(fake_server):
    converter, out_root = fake_server
    first = api.generate("a person walks forward", 40, 1)
    second = api.generate("a person walks forward", 40, 2)

    assert os.path.dirname(first[0]) != os.path.dirname(second[0])
    for bvh, mp4, stats in (first, second):
        assert os.path.dirname(bvh) == os.path.dirname(mp4)
        assert os.path.basename(os.path.dirname(bvh)).startswith("generate-")
        assert os.path.dirname(os.path.dirname(bvh)) == str(out_root)
        assert stats["frames"] == 40
        assert stats["bvh_bytes"] == os.path.getsize(bvh)
        assert stats["mp4_bytes"] == os.path.getsize(mp4)
    assert converter.calls == [40, 40]


def test_a_bad_story_is_a_readable_error(fake_server):
    with pytest.raises(gr.Error):
        api.show_api("", 42)
    with pytest.raises(gr.Error):
        api.story_api("", 42, True)


def test_old_output_folders_are_deleted_and_the_rest_kept(tmp_path):
    old = [tmp_path / f"{kind}-old" for kind in outputs.KINDS]
    new = tmp_path / "show-new"
    other = tmp_path / "motion.bvh"
    for folder in old + [new]:
        folder.mkdir()
    other.write_text("x")
    an_hour_ago = time.time() - outputs.KEEP_SECONDS - 60
    for folder in old:
        os.utime(folder, (an_hour_ago, an_hour_ago))

    made = outputs.new_dir(str(tmp_path), "story")

    assert not any(folder.exists() for folder in old)
    assert new.exists() and other.exists()
    assert os.path.isdir(made) and os.path.basename(made).startswith("story-")


def test_momask_options_ignore_the_command_line(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app.py", "--not-a-momask-flag"])
    opt = models.options()
    assert opt.dataset_name == "t2m" and opt.is_train is False
    assert str(opt.device) in ("cpu", "cuda")
