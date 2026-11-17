"""Keep a character's arms out of its own body.

MoMask moves a person with human proportions, so on these cartoon bodies the hands end
up inside the belly or the head. Each body part is a superquadric, measured from the
character's mesh by tools/body_shapes.py, and each arm a chain of capsules. When an arm
goes in, the whole arm turns at the shoulder by the smallest angle that clears every
part; the elbow and wrist stay as MoMask made them.
"""

import numpy as np
from scipy.spatial.transform import Rotation

from story.retarget import qinv, qmul

SIDES = ("Left", "Right")
MARGIN = 0.01  # metres of air between the arm and the body
SPREAD = 3  # frames a correction is held on each side, then blurred
SMOOTH_SIGMA = 2.0
MAX_DEGREES = 75  # a bigger turn at the shoulder reads as a jerk
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
        """Points along one arm at frame f, their radii, and True where it is the
        forearm or hand."""
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
        points = np.concatenate([p + t[:, None] * (q - p) for p, q, t, _, _ in parts])
        radius = np.concatenate([np.full(len(t), r) for _, _, t, r, _ in parts])
        lower = np.concatenate([np.full(len(t), low) for _, _, t, _, low in parts])
        return shoulder, points, radius, lower

    def depth(self, f, points, radius, lower):
        """How deep the deepest point is (<= 0 outside), its index and the way out."""
        best = np.full(points.shape[:-2], -np.inf)
        where = np.zeros(points.shape[:-2], int)
        normal = np.zeros(points.shape[:-2] + (3,))
        for bone, against, center, radii, across, along in self.shapes:
            r = self.matrices[f, bone]
            origin = self.positions[f, bone] + r @ center
            local = (points - origin) @ r
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
            n = grad @ r.T
            normal = np.where(better[..., None], n, normal)
        return best, where, normal

    def push(self, side, f, limit=MAX_DEGREES):
        """Rotation vector at the shoulder that takes the arm out of every shape at
        frame f.

        Tries the axis that moves the deepest point straight out and the chest's three
        axes. The smallest turn that clears wins; if none clears within `limit`, the one
        that leaves it least deep.
        """
        shoulder, points, radius, lower = self.arm(side, f)
        depth, k, normal = self.depth(f, points, radius, lower)
        if depth <= 0 or limit < 1:
            return np.zeros(3)
        lever = points[k] - shoulder
        candidates = [np.cross(lever, normal)]
        chest = self.matrices[f, self.chest]
        candidates += [sign * chest[:, i] for i in range(3) for sign in (1.0, -1.0)]
        angles = np.radians(np.arange(1, int(limit) + 1))
        axes = np.array(
            [a / np.linalg.norm(a) for a in candidates if np.linalg.norm(a) > 1e-8]
        )
        turns = _matrices(_quaternions(axes[:, None] * angles[None, :, None]))
        moved = shoulder + np.einsum("xaij,nj->xani", turns, points - shoulder)
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


def _spread(vectors):
    """Hold each correction SPREAD frames each side, then blur, so the arm eases out."""
    frames = len(vectors)
    norms = np.linalg.norm(vectors, axis=1)
    held = np.zeros_like(vectors)
    for f in range(frames):
        window = slice(max(0, f - SPREAD), min(frames, f + SPREAD + 1))
        held[f] = vectors[window][norms[window].argmax()]
    radius = int(3 * SMOOTH_SIGMA)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / SMOOTH_SIGMA) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(held, ((radius, radius), (0, 0)), mode="edge")
    return np.stack(
        [np.convolve(padded[:, i], kernel, mode="valid") for i in range(3)], axis=1
    )


def _apply(skeleton, rotations, globals_, side, vectors):
    upper = skeleton.bone(side + "Arm")
    parent = globals_[:, skeleton.parents[upper]]
    delta = _quaternions(vectors)
    local = qmul(qinv(parent), qmul(delta, qmul(parent, rotations[:, upper])))
    rotations = rotations.copy()
    rotations[:, upper] = local / np.linalg.norm(local, axis=-1, keepdims=True)
    return rotations


def avoid_self_penetration(skeleton, rotations, hips):
    """Returns (rotations with the arms kept out of the body, stats)."""
    stats = {"frames_fixed": {}, "max_degrees": {}}
    if not skeleton.body:
        return rotations, stats
    body = Body(skeleton, rotations, hips)
    for side in SIDES:
        if side not in body.arms:
            continue
        vectors = np.stack([body.push(side, f) for f in range(len(rotations))])
        touched = np.linalg.norm(vectors, axis=1) > 1e-6
        stats["frames_fixed"][side] = int(touched.sum())
        if not touched.any():
            continue
        spread = _spread(vectors)
        rotations = _apply(skeleton, rotations, body.globals, side, spread)
        # Finish the frames the blur left short of clear, within what is left of
        # MAX_DEGREES.
        body = Body(skeleton, rotations, hips)
        left = MAX_DEGREES - np.degrees(np.linalg.norm(spread, axis=1))
        rest = np.stack([body.push(side, f, left[f]) for f in range(len(rotations))])
        rotations = _apply(skeleton, rotations, body.globals, side, rest)
        body = Body(skeleton, rotations, hips)
        total = qmul(_quaternions(rest), _quaternions(spread))
        swing = 2 * np.arccos(np.clip(np.abs(total[:, 0]), 0, 1))
        stats["max_degrees"][side] = round(float(np.degrees(swing.max())), 1)
    return rotations, stats


def worst_depth(skeleton, rotations, hips):
    """Deepest any arm goes into the body over the motion (<= 0: never touches)."""
    if not skeleton.body:
        return -1.0
    body = Body(skeleton, rotations, hips)
    worst = -np.inf
    for side in SIDES:
        if side in body.arms:
            for f in range(len(rotations)):
                _, points, radius, lower = body.arm(side, f)
                worst = max(worst, float(body.depth(f, points, radius, lower)[0]))
    return worst
