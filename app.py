"""MoMask as a service — ITCS 6166, Team 2.
Text in, 3D motion out."""

import spaces  # must be imported before anything touches CUDA (ZeroGPU)

import os
import time
from os.path import join as pjoin

import gradio as gr
import numpy as np
import torch
import torch.nn.functional as F
from huggingface_hub import snapshot_download
from torch.distributions.categorical import Categorical

from gen_t2m import load_len_estimator, load_res_model, load_trans_model, load_vq_model
from options.eval_option import EvalT2MOptions
from utils.fixseed import fixseed
from utils.get_opt import get_opt
from utils.motion_process import recover_from_ric
from utils.paramUtil import t2m_kinematic_chain
from utils.plot_script import plot_3d_motion
from visualization.joints2bvh import Joint2BVHConvertor


CHECKPOINT_REPO = "pgarces/momask-checkpoints"
OUTPUT_DIR = "outputs"
HUMANML3D_POSE_DIM = 263  # features per frame in the HumanML3D representation
NUM_JOINTS = 22
FPS = 20


# --- 1. Checkpoints ----------------------------------------------------------
# Downloaded from our own Hugging Face model repo, so the Space does not
# depend on the authors' Google Drive link.

if not os.path.exists("checkpoints/t2m"):
    snapshot_download(CHECKPOINT_REPO, local_dir="checkpoints")


# --- 2. Load the four models once -------------------------------------------
# Same steps as gen_t2m.py: the residual VQ-VAE (tokenizer/decoder), the
# residual transformer, the masked transformer, and the length estimator.

opt = EvalT2MOptions().parse()
opt.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

root_dir = pjoin(opt.checkpoints_dir, opt.dataset_name, opt.name)
model_opt = get_opt(pjoin(root_dir, "opt.txt"), device=opt.device)

vq_opt_path = pjoin(opt.checkpoints_dir, opt.dataset_name, model_opt.vq_name, "opt.txt")
vq_opt = get_opt(vq_opt_path, device=opt.device)
vq_opt.dim_pose = HUMANML3D_POSE_DIM
vq_model, vq_opt = load_vq_model(vq_opt)

model_opt.num_tokens = vq_opt.nb_code
model_opt.num_quantizers = vq_opt.num_quantizers
model_opt.code_dim = vq_opt.code_dim

res_opt_path = pjoin(opt.checkpoints_dir, opt.dataset_name, opt.res_name, "opt.txt")
res_opt = get_opt(res_opt_path, device=opt.device)
res_model = load_res_model(res_opt, vq_opt, opt)

t2m_transformer = load_trans_model(model_opt, opt, "latest.tar")
length_estimator = load_len_estimator(model_opt)

for model in (vq_model, res_model, t2m_transformer, length_estimator):
    model.eval()
    model.to(opt.device)

# Statistics used to undo the dataset normalisation on the generated motion.
meta_dir = pjoin(opt.checkpoints_dir, opt.dataset_name, model_opt.vq_name, "meta")
mean = np.load(pjoin(meta_dir, "mean.npy"))
std = np.load(pjoin(meta_dir, "std.npy"))

converter = Joint2BVHConvertor()


# --- 3. One request = one motion --------------------------------------------


@spaces.GPU
def generate(text, length_frames, seed):
    """Generate one motion for `text`. length_frames = 0 lets the model pick the length."""
    start = time.time()
    fixseed(int(seed))

    with torch.no_grad():
        if int(length_frames) == 0:
            text_embedding = t2m_transformer.encode_text([text])
            probs = F.softmax(length_estimator(text_embedding), dim=-1)
            token_lens = Categorical(probs).sample()
        else:
            # The VQ-VAE downsamples time by 4: one token covers 4 frames.
            token_lens = torch.LongTensor([int(length_frames) // 4]).to(opt.device)

        # Base tokens from the masked transformer, detail tokens from the residual one.
        tokens = t2m_transformer.generate(
            [text],
            token_lens,
            timesteps=opt.time_steps,
            cond_scale=opt.cond_scale,
            temperature=opt.temperature,
            topk_filter_thres=opt.topkr,
            gsample=opt.gumbel_sample,
        )
        tokens = res_model.generate(
            tokens, [text], token_lens, temperature=1, cond_scale=5
        )
        motion = vq_model.forward_decoder(tokens).detach().cpu().numpy()

    num_frames = int(token_lens[0]) * 4
    features = (motion * std + mean)[0][:num_frames]
    joints = recover_from_ric(torch.from_numpy(features).float(), NUM_JOINTS).numpy()
    generation_seconds = time.time() - start

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bvh_path = pjoin(OUTPUT_DIR, "motion.bvh")
    mp4_path = pjoin(OUTPUT_DIR, "motion.mp4")

    # BVH = joint positions fitted to a skeleton as bone rotations (with foot IK).
    _, ik_joints = converter.convert(joints, filename=bvh_path, iterations=100)
    plot_3d_motion(mp4_path, t2m_kinematic_chain, ik_joints, title=text, fps=FPS)

    stats = {
        "frames": num_frames,
        "generation_seconds": round(generation_seconds, 2),
        "bvh_bytes": os.path.getsize(bvh_path),
        "mp4_bytes": os.path.getsize(mp4_path),
    }
    return bvh_path, mp4_path, stats


# --- 4. Web interface (also exposes the /generate API) ----------------------

with gr.Blocks(title="MoMask Team 2") as demo:
    gr.Markdown("# MoMask: text → 3D motion (ITCS 6166, Team 2)")

    text_input = gr.Textbox(label="Action", value="a person walks forward")
    with gr.Row():
        length_input = gr.Number(label="Frames (0 = automatic)", value=100)
        seed_input = gr.Number(label="Seed", value=42)
    generate_button = gr.Button("Generate", variant="primary")

    bvh_output = gr.File(label="BVH (motion)")
    video_output = gr.Video(label="Preview")
    stats_output = gr.JSON(label="Network measurements")

    generate_button.click(
        generate,
        inputs=[text_input, length_input, seed_input],
        outputs=[bvh_output, video_output, stats_output],
        api_name="generate",
    )


if __name__ == "__main__":
    demo.launch()
