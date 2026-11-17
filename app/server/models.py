"""Loading MoMask: the checkpoints, then the four models, as in gen_t2m.py."""

import os
from contextlib import contextmanager
from os.path import join as pjoin

import numpy as np
import torch
from huggingface_hub import snapshot_download

from gen_t2m import load_len_estimator, load_res_model, load_trans_model, load_vq_model
from options.eval_option import EvalT2MOptions
from server import MOMASK_DIR
from story.motion import Models
from utils.get_opt import get_opt

CHECKPOINT_REPO = "pgarces/momask-checkpoints"
HUMANML3D_POSE_DIM = 263  # features per frame in the HumanML3D representation


@contextmanager
def inside_momask():
    """MoMask opens ./checkpoints and ./visualization/data relative to its own folder."""
    previous = os.getcwd()
    os.chdir(MOMASK_DIR)
    try:
        yield
    finally:
        os.chdir(previous)


def options():
    parser = EvalT2MOptions()
    parser.initialize()
    # Not parse(): it reads sys.argv, so a server or pytest flag would break it.
    opt = parser.parser.parse_args([])
    opt.is_train = parser.is_train
    opt.device = torch.device("cpu")  # see server/api.py
    return opt


def download_checkpoints(checkpoints_dir):
    """Our copy on Hugging Face, so we don't depend on the authors' Google Drive."""
    if not os.path.exists(pjoin(checkpoints_dir, "t2m")):
        snapshot_download(CHECKPOINT_REPO, local_dir=checkpoints_dir)


def load_models():
    opt = options()
    download_checkpoints(opt.checkpoints_dir)

    root_dir = pjoin(opt.checkpoints_dir, opt.dataset_name, opt.name)
    model_opt = get_opt(pjoin(root_dir, "opt.txt"), device=opt.device)

    vq_opt = get_opt(
        pjoin(opt.checkpoints_dir, opt.dataset_name, model_opt.vq_name, "opt.txt"),
        device=opt.device,
    )
    vq_opt.dim_pose = HUMANML3D_POSE_DIM
    vq_model, vq_opt = load_vq_model(vq_opt)

    model_opt.num_tokens = vq_opt.nb_code
    model_opt.num_quantizers = vq_opt.num_quantizers
    model_opt.code_dim = vq_opt.code_dim

    res_opt = get_opt(
        pjoin(opt.checkpoints_dir, opt.dataset_name, opt.res_name, "opt.txt"),
        device=opt.device,
    )
    res_model = load_res_model(res_opt, vq_opt, opt)

    transformer = load_trans_model(model_opt, opt, "latest.tar")
    length_estimator = load_len_estimator(model_opt)

    for model in (vq_model, res_model, transformer, length_estimator):
        model.eval()
        model.to(opt.device)

    meta_dir = pjoin(opt.checkpoints_dir, opt.dataset_name, model_opt.vq_name, "meta")
    mean = np.load(pjoin(meta_dir, "mean.npy"))
    std = np.load(pjoin(meta_dir, "std.npy"))

    return Models(vq_model, res_model, transformer, length_estimator, opt, mean, std)
