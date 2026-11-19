"""MoMask's joint positions -> rotations (BVH), with the authors' IK.

Their converter starts every frame's IK from zero rotations and nudges each joint toward
its children. Once the body has turned more than about 90 degrees, the hips can settle
either way round, so the arms and legs twist from one frame to the next. Starting the
hips from the way the body faces keeps every frame close to the answer.

MoMask places every joint on its own, with no fixed bone lengths. In a fast move the head
point can sink into the neck (10 cm apart becomes 1 cm), its direction from the neck
flips, and the IK turns the head right over in one frame. repair_head rebuilds those
frames from the good ones around them first.
"""

import numpy as np
import visualization.Animation as Animation
import visualization.BVH_mod as BVH
from visualization.InverseKinematics import BasicInverseKinematics
from visualization.joints2bvh import Joint2BVHConvertor
from visualization.Quaternions import Quaternions

ITERATIONS = 10  # the authors' default; more land no closer
# SMPL joints that give the body's left-right line, as in HumanML3D.
HIPS = (2, 1)
SHOULDERS = (17, 16)
CHEST, NECK, HEAD = 9, 12, 15
SHORT = 0.5  # a head closer to the neck than this share of its usual distance is lost


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def _slerp(p, q, t):
    """Unit vector a share t of the way from unit vector p to q, along the sphere."""
    angle = np.arccos(np.clip(p @ q, -1.0, 1.0))
    if angle < 1e-6:
        return p
    return (np.sin((1 - t) * angle) * p + np.sin(t * angle) * q) / np.sin(angle)


def chest_axes(joints):
    """Per frame, the chest's axes as rows: x across the shoulders, y up the neck, z
    forward."""
    up = _unit(joints[:, NECK] - joints[:, CHEST])
    across = joints[:, SHOULDERS[1]] - joints[:, SHOULDERS[0]]
    across = _unit(across - (across * up).sum(-1, keepdims=True) * up)
    return np.stack([across, up, np.cross(across, up)], axis=-2)


def repair_head(joints):
    """Joints with every lost head point (see SHORT) rebuilt from the nearest good frames
    on each side: its direction from the neck, as the chest sees it, turns smoothly from
    one to the other, and it moves with the chest in between."""
    offset = joints[:, HEAD] - joints[:, NECK]
    length = np.linalg.norm(offset, axis=-1)
    lost = length < SHORT * np.median(length)
    if not lost.any() or lost.all():
        return joints
    joints = joints.copy()
    axes = chest_axes(joints)
    local = _unit(np.einsum("fij,fj->fi", axes, offset))
    good = np.flatnonzero(~lost)
    for f in np.flatnonzero(lost):
        i = np.searchsorted(good, f)
        a, b = good[max(i - 1, 0)], good[min(i, len(good) - 1)]
        t = 0.0 if a == b else (f - a) / (b - a)
        size = (1 - t) * length[a] + t * length[b]
        joints[f, HEAD] = joints[f, NECK] + axes[f].T @ (_slerp(local[a], local[b], t) * size)
    return joints


def facing(joints):
    """The way the body faces at each frame, as an angle around Y (0 = +Z)."""
    across = (
        joints[:, HIPS[0]]
        - joints[:, HIPS[1]]
        + joints[:, SHOULDERS[0]]
        - joints[:, SHOULDERS[1]]
    )
    forward = np.cross([0.0, 1.0, 0.0], across)
    return np.unwrap(np.arctan2(forward[:, 0], forward[:, 2]))


class Converter(Joint2BVHConvertor):

    def convert(self, joints, filename):
        """Returns (Animation, its joint positions); writes the BVH to `filename`."""
        joints = repair_head(joints)
        positions = joints[:, self.re_order]
        anim = self.template.copy()
        anim.rotations = Quaternions.id(positions.shape[:-1])
        up = np.tile([0.0, 1.0, 0.0], (len(joints), 1))
        anim.rotations[:, 0] = Quaternions.from_angle_axis(facing(joints), up)
        anim.positions = anim.positions[0:1].repeat(len(joints), axis=0)
        anim.positions[:, 0] = positions[:, 0]
        anim = BasicInverseKinematics(anim, positions, ITERATIONS, silent=True)()
        BVH.save(filename, anim, names=anim.names, frametime=1 / 20, quater=True)
        return anim, Animation.positions_global(anim)[:, self.re_order_inv]
