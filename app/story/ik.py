"""MoMask's joint positions -> rotations (BVH), with the authors' IK.

Their converter starts every frame's IK from zero rotations and nudges each joint toward
its children. Once the body has turned more than about 90 degrees, the hips can settle
either way round, so the arms and legs twist from one frame to the next. Starting the
hips from the way the body faces keeps every frame close to the answer.
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
