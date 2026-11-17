"""Keep a character's arms out of its own body.

MoMask moves a person with human proportions, so on these cartoon bodies the hands end
up inside the belly or the head. Each body part is a superquadric, measured from the
character's mesh by tools/body_shapes.py, and each arm a chain of capsules. When an arm
goes in, it turns at the shoulder by the smallest angle that clears every part, and at
the elbow when that is not enough (a hand on a big helmet). The turns ease in and out
over the frames around, and never push the arm deeper or make it jump (see _turn).
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.ndimage import gaussian_filter1d, minimum_filter1d
from scipy.spatial.transform import Rotation

from story.retarget import qinv, qmul

SIDES = ("Left", "Right")
MARGIN = 0.01  # metres of air between the arm and the body
SPREAD = 3  # frames a turn is held on each side before the blur
SMOOTH_SIGMA = 2.0  # frames
MAX_DEGREES = 75  # the most the shoulder turns; more reads as a jerk
ELBOW_DEGREES = 90  # the most the elbow turns
MAX_STEP = 25  # degrees an arm may turn from one frame to the next, unless MoMask does
SHARES = (0.25, 0.5, 0.75, 1.0)  # of a blurred turn, tried on each frame
# (joint, frames held, blur) per pass: smooth turns at the shoulder twice (the blur
# leaves some frames short), at the elbow, then quicker ones at the shoulder for
# whatever is still in.
PASSES = (
    [("Arm", SPREAD, SMOOTH_SIGMA)] * 2
    + [("ForeArm", SPREAD, SMOOTH_SIGMA)]
    + [("Arm", 0, 1.0)] * 4
)
SINK = 0.5  # share of a sleeve's thickness allowed into the trunk or a thigh


def level(u, across, along):
    """Superquadric equation at u = |local / radii|: < 1 inside, 1 on the surface."""
    flat = (u[..., 0] ** across + u[..., 2] ** across) ** (1 / across)
    return (flat**along + u[..., 1] ** along) ** (1 / along)


def _matrices(q):
    """(..., 4) w-x-y-z quaternions -> (..., 3, 3) rotation matrices."""
    q = np.asarray(q)
    flat = Rotation.from_quat(q.reshape(-1, 4), scalar_first=True).as_matrix()
    return flat.reshape(q.shape[:-1] + (3, 3))


def _quaternions(vectors):
    """(..., 3) rotation vectors (axis * angle) -> (..., 4) w-x-y-z quaternions."""
    v = np.asarray(vectors)
    flat = Rotation.from_rotvec(v.reshape(-1, 3)).as_quat(scalar_first=True)
    return flat.reshape(v.shape[:-1] + (4,))


class Body:

    def __init__(self, skeleton, rotations, hips, body=None):
        body = body or skeleton.body
        self.skeleton = skeleton
        self.positions, self.globals = skeleton.forward_kinematics(
            rotations, hips, with_rotations=True
        )
        self.matrices = _matrices(self.globals)
        self.shapes = [
            (
                skeleton.index[s["bone"]],
                s["against"],
                np.array(s["center"]),
                np.array(s["radii"]),
                s.get("across", 2.0),
                s.get("along", 2.0),
            )
            for s in body["shapes"]
            if s["bone"] in skeleton.index
        ]
        self.arms = body["arms"]
        self.chest = (
            skeleton.bone("Spine2")
            if skeleton.bone("Spine2") is not None
            else skeleton.bone("Spine")
        )

    def arm(self, side, f):
        """Points along one arm at frame f (or frames, as a slice), their radii, and
        True where it is the forearm or hand."""
        sk, a = self.skeleton, self.arms[side]
        shoulder, elbow, wrist = (
            self.positions[f, sk.bone(side + j)] for j in ("Arm", "ForeArm", "Hand")
        )
        tip = wrist + self.matrices[f, sk.bone(side + "Hand")] @ np.array(a["hand_tip"])
        parts = [
            (shoulder, elbow, np.linspace(0.45, 1.0, 4), a["upper_radius"], False),
            (elbow, wrist, np.linspace(0.0, 1.0, 6), a["fore_radius"], True),
            (wrist, tip, np.linspace(0.0, 1.0, 4), a["hand_radius"], True),
        ]
        points = np.concatenate(
            [
                p[..., None, :] + t[:, None] * (q - p)[..., None, :]
                for p, q, t, *_ in parts
            ],
            axis=-2,
        )
        radius = np.concatenate([np.full(len(t), r) for _, _, t, r, _ in parts])
        lower = np.concatenate([np.full(len(t), low) for _, _, t, _, low in parts])
        return shoulder, points, radius, lower

    def depth(self, f, points, radius, lower):
        """How deep the deepest point is (<= 0 outside), its index and the way out.
        `f` is a frame, or a slice of frames with points for each."""
        best = np.full(points.shape[:-2], -np.inf)
        where = np.zeros(points.shape[:-2], int)
        normal = np.zeros(points.shape[:-2] + (3,))
        for bone, against, center, radii, across, along in self.shapes:
            r = self.matrices[f, bone]
            origin = self.positions[f, bone] + r @ center
            local = (points - origin[..., None, :]) @ r
            # A sleeve may brush the trunk or a thigh (half its thickness), never the
            # head.
            sink = SINK if against == "forearm" else 0.0
            size = radii + radius[:, None] * (1 - sink) + MARGIN
            d = 1 - level(np.abs(local / size), across, along)
            if against == "forearm":
                d = np.where(lower, d, -np.inf)
            k = d.argmax(axis=-1)
            dk = np.take_along_axis(d, k[..., None], -1)[..., 0]
            better = dk > best
            best = np.where(better, dk, best)
            where = np.where(better, k, where)
            lk = np.take_along_axis(local, k[..., None, None], -2)[..., 0, :]
            sk = size[k]
            # The gradient of the shape's equation points straight out of it.
            u = np.abs(lk) / sk
            flat = np.maximum(
                (u[..., 0] ** across + u[..., 2] ** across) ** (1 / across), 1e-9
            )
            grad = (
                np.sign(lk)
                / sk
                * np.stack(
                    [
                        flat ** (along - across) * u[..., 0] ** (across - 1),
                        u[..., 1] ** (along - 1),
                        flat ** (along - across) * u[..., 2] ** (across - 1),
                    ],
                    axis=-1,
                )
            )
            n = np.einsum("...j,...ij->...i", grad, r)
            normal = np.where(better[..., None], n, normal)
        return best, where, normal

    def push(self, side, f, limit=MAX_DEGREES, joint="Arm"):
        """Rotation vector at the shoulder (joint="Arm") or the elbow ("ForeArm") that
        takes the arm out of every shape at frame f.

        Tries the axis that moves the deepest point straight out and the chest's three
        axes. The smallest turn that clears wins; if none clears within `limit`, the one
        that leaves it least deep.
        """
        _, points, radius, lower = self.arm(side, f)
        depth, k, normal = self.depth(f, points, radius, lower)
        moves = lower if joint == "ForeArm" else np.ones(len(points), bool)
        if depth <= 0 or limit < 1 or not moves[k]:
            return np.zeros(3)
        pivot = self.positions[f, self.skeleton.bone(side + joint)]
        candidates = [np.cross(points[k] - pivot, normal)]
        chest = self.matrices[f, self.chest]
        candidates += [sign * chest[:, i] for i in range(3) for sign in (1.0, -1.0)]
        angles = np.radians(np.arange(1, int(limit) + 1))
        axes = np.array(
            [a / np.linalg.norm(a) for a in candidates if np.linalg.norm(a) > 1e-8]
        )
        turns = _matrices(_quaternions(axes[:, None] * angles[None, :, None]))
        moved = pivot + np.einsum("xaij,nj->xani", turns, points - pivot)
        moved = np.where(moves[:, None], moved, points)
        all_depths = self.depth(f, moved, radius, lower)[0]
        best = None  # (cleared, angle or residual depth, rotation vector)
        for axis, depths in zip(axes, all_depths):
            clear = np.flatnonzero(depths <= 0)
            if len(clear):
                option = (0, angles[clear[0]], axis * angles[clear[0]])
            else:
                i = int(depths.argmin())
                option = (1, depths[i], axis * angles[i])
            if best is None or option[:2] < best[:2]:
                best = option
        return best[2]

    def depths(self, side):
        """How deep one arm is at every frame (<= 0 outside)."""
        every = slice(None)
        return self.depth(every, *self.arm(side, every)[1:])[0]

    def steps(self, side):
        """Degrees the upper arm or forearm turns into or out of each frame, the most."""
        steps = np.zeros(len(self.positions))
        for joint in ("Arm", "ForeArm"):
            m = self.matrices[:, self.skeleton.bone(side + joint)]
            cos = (np.einsum("fij,fij->f", m[1:], m[:-1]) - 1) / 2
            turn = np.degrees(np.arccos(np.clip(cos, -1, 1)))
            steps = np.maximum(
                steps, np.maximum(np.append(turn, 0), np.append(0, turn))
            )
        return steps


def _degrees(q):
    """How far each quaternion turns, in degrees."""
    return np.degrees(2 * np.arccos(np.clip(np.abs(q[..., 0]), 0, 1)))


def _blur(values, sigma):
    return gaussian_filter1d(values, sigma, axis=0, mode="nearest", truncate=3)


def _spread(vectors, hold, sigma):
    """Hold each turn `hold` frames each side, then blur, so the arm eases in and out."""
    norms = np.pad(np.linalg.norm(vectors, axis=1), hold, constant_values=-1)
    biggest = sliding_window_view(norms, 2 * hold + 1).argmax(axis=1)
    return _blur(vectors[np.arange(len(vectors)) + biggest - hold], sigma)


def _apply(skeleton, rotations, globals_, side, vectors, joint):
    bone = skeleton.bone(side + joint)
    parent = globals_[:, skeleton.parents[bone]]
    delta = _quaternions(vectors)
    local = qmul(qinv(parent), qmul(delta, qmul(parent, rotations[:, bone])))
    rotations = rotations.copy()
    rotations[:, bone] = local / np.linalg.norm(local, axis=-1, keepdims=True)
    return rotations


def _turn(body, rotations, hips, side, joint, limits, hold, sigma):
    """Turns one arm at `joint` out of the body, within `limits` degrees per frame.
    Returns (rotations, their Body, the turns as rotation vectors).

    The turns are spread over the frames around so the arm doesn't jump. That can carry
    a turn onto a frame where it pushes the arm deeper: an arm swinging through the body
    is pushed forward on one frame and back on the next. So each frame keeps the biggest
    share of its turn that leaves it no deeper than before and doesn't make the arm jump
    (MAX_STEP), and the shares are blurred too, never above what any frame nearby allows.
    """
    skeleton = body.skeleton
    depths = body.depths(side)
    vectors = np.zeros((len(rotations), 3))
    for f in np.flatnonzero(depths > 0):
        vectors[f] = body.push(side, f, limits[f], joint)
    if not vectors.any():
        return rotations, body, vectors
    vectors = _spread(vectors, hold, sigma)
    size = np.linalg.norm(vectors, axis=1)
    room = np.radians(np.maximum(limits, 0))
    vectors *= (np.minimum(size, room) / np.maximum(size, 1e-9))[:, None]
    deepest = np.maximum(depths, 0) + 1e-3
    quickest = np.maximum(body.steps(side), MAX_STEP)
    share = np.zeros(len(rotations))
    for part in SHARES:
        moved = _apply(skeleton, rotations, body.globals, side, part * vectors, joint)
        moved = Body(skeleton, moved, hips)
        fine = (moved.depths(side) <= deepest) & (moved.steps(side) <= quickest)
        share[fine] = part
    reach = 2 * int(3 * sigma + 0.5) + 1  # as wide as the blur
    share = _blur(minimum_filter1d(share, reach, mode="nearest"), sigma)
    vectors = share[:, None] * vectors
    rotations = _apply(skeleton, rotations, body.globals, side, vectors, joint)
    return rotations, Body(skeleton, rotations, hips), vectors


def avoid_self_penetration(skeleton, rotations, hips):
    """Returns (rotations with the arms kept out of the body, stats)."""
    stats = {"frames_fixed": {}, "max_degrees": {}}
    if not skeleton.body:
        return rotations, stats
    body = Body(skeleton, rotations, hips)
    frames = len(rotations)
    for side in SIDES:
        if side not in body.arms:
            continue
        stats["frames_fixed"][side] = int((body.depths(side) > 0).sum())
        if not stats["frames_fixed"][side]:
            continue
        shoulder = _quaternions(np.zeros((frames, 3)))  # all the shoulder turns so far
        for joint, hold, sigma in PASSES:
            if joint == "Arm":
                limits = MAX_DEGREES - _degrees(shoulder)
            else:
                limits = np.full(frames, ELBOW_DEGREES)
            rotations, body, vectors = _turn(
                body, rotations, hips, side, joint, limits, hold, sigma
            )
            if joint == "Arm":
                shoulder = qmul(_quaternions(vectors), shoulder)
        stats["max_degrees"][side] = round(float(_degrees(shoulder).max()), 1)
    return rotations, stats


def worst_depth(skeleton, rotations, hips):
    """Deepest any arm goes into the body over the motion (<= 0: never touches)."""
    if not skeleton.body:
        return -1.0
    body = Body(skeleton, rotations, hips)
    arms = [side for side in SIDES if side in body.arms]
    return max((float(body.depths(side).max()) for side in arms), default=-np.inf)
