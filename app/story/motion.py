"""MoMask generation for story mode: one motion per action, then each seam regenerated
with MoMask's own temporal editing (MaskTransformer.edit, as in edit_t2m.py)."""

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions.categorical import Categorical

from utils.fixseed import fixseed
from utils.motion_process import recover_from_ric

FPS = 20
TOKEN_FRAMES = 4  # the VQ-VAE turns 4 frames into one token
MAX_FRAMES = 196  # the longest motion the model was trained on (9.8 s)
MIN_FRAMES = 48  # 2.4 s, so every action has room for its seams
NUM_JOINTS = 22

# Around each seam: 2 s of context on each side, and the middle 1.6 s regenerated.
SEAM_CONTEXT = 40
SEAM_MASK = 16
# Frames blended with the original at the edges, because re-encoding changes them
# slightly.
SEAM_BLEND = 8


@dataclass
class Models:
    vq: torch.nn.Module
    res: torch.nn.Module
    transformer: torch.nn.Module
    length_estimator: torch.nn.Module
    opt: object
    mean: np.ndarray
    std: np.ndarray

    @property
    def device(self):
        return self.opt.device


def to_frames(seconds):
    """Seconds -> a frame count the model accepts (a multiple of 4, in its range)."""
    frames = int(round(seconds * FPS / TOKEN_FRAMES)) * TOKEN_FRAMES
    return max(MIN_FRAMES, min(MAX_FRAMES, frames))


def generate_features(models, text, frames, seed):
    """One motion (frames, 263) for `text`. frames = 0: the length estimator picks."""
    fixseed(int(seed))
    with torch.no_grad():
        if int(frames) == 0:
            text_embedding = models.transformer.encode_text([text])
            probs = F.softmax(models.length_estimator(text_embedding), dim=-1)
            token_lens = Categorical(probs).sample()
        else:
            token_lens = torch.LongTensor([int(frames) // TOKEN_FRAMES]).to(
                models.device
            )

        # Base tokens from the masked transformer, detail tokens from the residual one.
        tokens = models.transformer.generate(
            [text],
            token_lens,
            timesteps=models.opt.time_steps,
            cond_scale=models.opt.cond_scale,
            temperature=models.opt.temperature,
            topk_filter_thres=models.opt.topkr,
            gsample=models.opt.gumbel_sample,
        )
        tokens = models.res.generate(
            tokens, [text], token_lens, temperature=1, cond_scale=5
        )
        motion = models.vq.forward_decoder(tokens).detach().cpu().numpy()

    num_frames = int(token_lens[0]) * TOKEN_FRAMES
    return (motion * models.std + models.mean)[0][:num_frames]


def edit_window(models, window, caption, mask_start, mask_end, seed):
    """Regenerate frames [mask_start, mask_end) of `window` (frames, 263) from
    `caption`."""
    fixseed(int(seed))
    normalized = (
        torch.from_numpy((window - models.mean) / models.std)
        .float()[None]
        .to(models.device)
    )
    token_count = len(window) // TOKEN_FRAMES
    token_lens = torch.LongTensor([token_count]).to(models.device)
    with torch.no_grad():
        tokens, _ = models.vq.encode(normalized)
        edit_mask = torch.zeros_like(tokens[..., 0]).bool()
        edit_mask[:, mask_start // TOKEN_FRAMES : mask_end // TOKEN_FRAMES] = True
        base = models.transformer.edit(
            [caption],
            tokens[..., 0].clone(),
            token_lens,
            timesteps=models.opt.time_steps,
            cond_scale=models.opt.cond_scale,
            temperature=models.opt.temperature,
            topk_filter_thres=models.opt.topkr,
            gsample=models.opt.gumbel_sample,
            force_mask=models.opt.force_mask,
            edit_mask=edit_mask,
        )
        # Same residual settings as edit_t2m.py.
        tokens = models.res.generate(
            base, [caption], token_lens, temperature=1, cond_scale=2
        )
        edited = models.vq.forward_decoder(tokens).detach().cpu().numpy()
    return (edited * models.std + models.mean)[0][: len(window)]


def seam_caption(first, second):
    """'a person walks' + 'a person waves' -> 'a person walks and then waves'."""
    second = second.strip().rstrip(".")
    for start in ("a person ", "the person ", "someone "):
        if second.lower().startswith(start):
            second = second[len(start) :]
            break
    return f"{first.strip().rstrip('.')} and then {second}"


def blend(original, edited, frames):
    """Fade from `original` into `edited` over `frames` frames, and back at the end."""
    out = edited.copy()
    for i in range(min(frames, len(out) // 2)):
        w = (i + 1) / (frames + 1)
        out[i] = (1 - w) * original[i] + w * edited[i]
        out[-1 - i] = (1 - w) * original[-1 - i] + w * edited[-1 - i]
    return out


def join(
    models, clips, captions, seed, smooth=True, seam_captions=None, seam_mask=SEAM_MASK
):
    """Join the clips. Returns (features, (start, end) frames per clip, transitions).

    Each seam is regenerated from "<first> and then <second>" unless seam_captions gives
    its text. seam_mask is half the regenerated stretch, in frames.
    """
    bounds, cursor = [], 0
    for clip in clips:
        bounds.append((cursor, cursor + len(clip)))
        cursor += len(clip)
    features = np.concatenate(clips, axis=0)
    raw_joints = to_joints(features)
    transitions = []
    if not smooth:
        return features, bounds, transitions

    for k in range(len(clips) - 1):
        seam = bounds[k][1]
        # Keep each window inside the two clips it joins, so windows never overlap.
        context = min(SEAM_CONTEXT, len(clips[k]) // 2, len(clips[k + 1]) // 2)
        context -= context % TOKEN_FRAMES
        half_mask = min(seam_mask, context - TOKEN_FRAMES)
        half_mask -= half_mask % TOKEN_FRAMES
        if half_mask <= 0:
            continue
        start, end = seam - context, seam + context
        window = features[start:end]
        edited = edit_window(
            models,
            window,
            (
                seam_captions[k]
                if seam_captions
                else seam_caption(captions[k], captions[k + 1])
            ),
            context - half_mask,
            context + half_mask,
            seed + 1000 + k,
        )
        features[start:end] = blend(window, edited, SEAM_BLEND)
        transitions.append(
            {"between": [k, k + 1], "start": seam - half_mask, "end": seam + half_mask}
        )

    # How sharply the motion changes at each seam, before and after the edit.
    joints = to_joints(features)
    for t in transitions:
        seam = bounds[t["between"][0]][1]
        t["kick_cm_before"] = round(100 * seam_kick(raw_joints, seam), 2)
        t["kick_cm_after"] = round(100 * seam_kick(joints, seam), 2)
    return features, bounds, transitions


def to_joints(features):
    """HumanML3D features -> joint positions (frames, 22, 3), in metres."""
    return recover_from_ric(torch.from_numpy(features).float(), NUM_JOINTS).numpy()


def speed_changes(joints):
    """Per frame, how much the joints' movement changes (metres); a cut is a spike."""
    step = np.diff(joints, axis=0)
    return np.linalg.norm(np.diff(step, axis=0), axis=-1).mean(axis=-1)


def seam_kick(joints, seam):
    """The spike at a seam: the larger speed change around the cut, in metres."""
    changes = speed_changes(joints)
    # changes[i] compares the steps (i -> i+1) and (i+1 -> i+2); the cut is the step
    # seam-1 -> seam.
    return float(changes[max(0, seam - 2) : seam].max())
