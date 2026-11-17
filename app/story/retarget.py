"""Retarget a MoMask motion onto a character: the Mixamo Xbot, or a VRM avatar.

Both are T-poses with Y up. For each bone, world rotation on the character = world
rotation in MoMask * C, where C turns the character's rest bone direction into MoMask's.
VRM 0.x avatars look down -Z, so they are turned 180 degrees for the maths and back at
the end.
"""

import json
import struct

import numpy as np

# MoMask BVH joint -> Xbot bone (the authors' assets/mapping.json, plus the toes).
BONE_MAP = {
    "Hips": "mixamorig:Hips",
    "LeftUpLeg": "mixamorig:LeftUpLeg",
    "LeftLeg": "mixamorig:LeftLeg",
    "LeftFoot": "mixamorig:LeftFoot",
    "LeftToe": "mixamorig:LeftToeBase",
    "RightUpLeg": "mixamorig:RightUpLeg",
    "RightLeg": "mixamorig:RightLeg",
    "RightFoot": "mixamorig:RightFoot",
    "RightToe": "mixamorig:RightToeBase",
    "Spine": "mixamorig:Spine",
    "Spine1": "mixamorig:Spine1",
    "Spine2": "mixamorig:Spine2",
    "Neck": "mixamorig:Neck",
    "Head": "mixamorig:Head",
    "LeftShoulder": "mixamorig:LeftShoulder",
    "LeftArm": "mixamorig:LeftArm",
    "LeftForeArm": "mixamorig:LeftForeArm",
    "LeftHand": "mixamorig:LeftHand",
    "RightShoulder": "mixamorig:RightShoulder",
    "RightArm": "mixamorig:RightArm",
    "RightForeArm": "mixamorig:RightForeArm",
    "RightHand": "mixamorig:RightHand",
}

# The child that gives each bone its direction. Bones left out keep C = 1.
DIRECTION_CHILD = {
    "LeftUpLeg": "LeftLeg",
    "LeftLeg": "LeftFoot",
    "LeftFoot": "LeftToe",
    "RightUpLeg": "RightLeg",
    "RightLeg": "RightFoot",
    "RightFoot": "RightToe",
    "Spine": "Spine1",
    "Spine1": "Spine2",
    "Spine2": "Neck",
    "Neck": "Head",
    "LeftShoulder": "LeftArm",
    "LeftArm": "LeftForeArm",
    "LeftForeArm": "LeftHand",
    "RightShoulder": "RightArm",
    "RightArm": "RightForeArm",
    "RightForeArm": "RightHand",
}

# MoMask BVH joint -> VRM humanoid bone, for the story characters (VRM 0.x).
VRM_BONES = {
    "Hips": "hips",
    "LeftUpLeg": "leftUpperLeg",
    "LeftLeg": "leftLowerLeg",
    "LeftFoot": "leftFoot",
    "LeftToe": "leftToes",
    "RightUpLeg": "rightUpperLeg",
    "RightLeg": "rightLowerLeg",
    "RightFoot": "rightFoot",
    "RightToe": "rightToes",
    "Spine": "spine",
    "Spine1": "chest",
    "Spine2": "upperChest",
    "Neck": "neck",
    "Head": "head",
    "LeftShoulder": "leftShoulder",
    "LeftArm": "leftUpperArm",
    "LeftForeArm": "leftLowerArm",
    "LeftHand": "leftHand",
    "RightShoulder": "rightShoulder",
    "RightArm": "rightUpperArm",
    "RightForeArm": "rightLowerArm",
    "RightHand": "rightHand",
}

LEG = ("LeftUpLeg", "LeftLeg", "LeftFoot")


# Quaternions are (w, x, y, z), like visualization/Quaternions.py.


def qmul(a, b):
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ],
        axis=-1,
    )


def qinv(q):
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def qrotate(q, v):
    qv = np.concatenate([np.zeros(v.shape[:-1] + (1,)), v], axis=-1)
    return qmul(qmul(q, qv), qinv(q))[..., 1:]


def qbetween(u, v):
    """The shortest rotation that turns direction u into direction v."""
    u = u / np.linalg.norm(u)
    v = v / np.linalg.norm(v)
    d = float(np.dot(u, v))
    if d < -0.999999:
        # Opposite directions: any axis perpendicular to u works.
        axis = np.cross(u, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(u, [0.0, 1.0, 0.0])
        axis /= np.linalg.norm(axis)
        return np.array([0.0, *axis])
    q = np.array([1.0 + d, *np.cross(u, v)])
    return q / np.linalg.norm(q)


def qaxis(axis, angles):
    """Rotations by `angles` (radians) about one axis."""
    half = np.asarray(angles)[..., None] / 2
    return np.concatenate([np.cos(half), np.sin(half) * axis], axis=-1)


def level(rotations, toe):
    """Foot rotations (from MoMask's rest pose) with the roll taken out: the same turn
    around Y and the same toe pitch, the sole level from side to side.

    The IK only knows where the toe is, so it leaves the foot's roll to chance; on the
    floor that shows as a foot standing on its edge. The turn around Y comes from the
    rotation, not from where the toe points, because a toe pointing down (a kick, a
    dance step) says nothing about which way the foot faces.
    """
    yaw = 2 * np.arctan2(rotations[:, 2], rotations[:, 0])
    toe = toe / np.linalg.norm(toe)
    now = qrotate(rotations, np.broadcast_to(toe, rotations.shape[:-1] + (3,)))
    pitch = np.arcsin(np.clip(now[:, 1], -1, 1)) - np.arcsin(toe[1])
    heading = np.arctan2(toe[0], toe[2])
    across = np.array([np.cos(heading), 0.0, -np.sin(heading)])
    return qmul(qaxis(np.array([0.0, 1.0, 0.0]), yaw), qaxis(across, -pitch))


def turn_around(q):
    """The same rotation seen from a frame turned 180 degrees about Y."""
    return q * np.array([1.0, -1.0, 1.0, -1.0])


def continuous(q):
    """Flip signs so consecutive frames never jump between q and -q."""
    q = q.copy()
    for t in range(1, len(q)):
        flip = np.sum(q[t] * q[t - 1], axis=-1) < 0
        q[t][flip] *= -1
    return q


def read_glb(path):
    """Return (json, binary chunk) of a .glb file."""
    data = open(path, "rb").read()
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + json_len])
    binary = data[20 + json_len + 8 :] if len(data) > 20 + json_len else b""
    return gltf, binary


class TargetSkeleton:
    """A character's bones in their rest pose. faces_back: a VRM 0.x avatar (-Z)."""

    def __init__(
        self,
        names,
        parents,
        offsets,
        rest_rotations,
        armature_scale=1.0,
        bone_map=None,
        faces_back=False,
    ):
        self.names = list(names)
        self.parents = list(parents)
        self.offsets = np.asarray(offsets, dtype=float)
        self.rest_rotations = np.asarray(rest_rotations, dtype=float)  # (w, x, y, z)
        self.armature_scale = float(armature_scale)
        self.index = {name: k for k, name in enumerate(self.names)}
        self.bone_map = {
            j: b for j, b in (bone_map or BONE_MAP).items() if b in self.index
        }
        self.faces_back = bool(faces_back)
        self.hips = self.bone_map["Hips"]
        self.body = None  # see story/collide.py

    @classmethod
    def load(cls, path):
        if path.endswith(".glb"):
            return cls.from_glb(path)
        if path.endswith(".vrm"):
            return cls.from_vrm(path)
        with open(path) as f:
            data = json.load(f)
        skeleton = cls(
            data["names"],
            data["parents"],
            data["offsets"],
            data["rest_rotations"],
            data["armature_scale"],
            data.get("bone_map"),
            data.get("faces_back", False),
        )
        skeleton.body = data.get("body")
        return skeleton

    @classmethod
    def from_vrm(cls, vrm_path):
        """A VRM 0.x avatar: the bones under its hips, named by its humanoid table."""
        gltf, _ = read_glb(vrm_path)
        nodes = gltf["nodes"]
        humanoid = {
            b["bone"]: b["node"]
            for b in gltf["extensions"]["VRM"]["humanoid"]["humanBones"]
        }

        order, parents = [], []

        def visit(i, parent):
            if "mesh" in nodes[i]:
                return
            order.append(i)
            parents.append(parent)
            here = len(order) - 1
            for c in nodes[i].get("children", []):
                visit(c, here)

        visit(humanoid["hips"], -1)
        name_of = {i: nodes[i].get("name", f"node{i}") for i in order}
        bone_map = {
            j: name_of[humanoid[h]]
            for j, h in VRM_BONES.items()
            if humanoid.get(h) in name_of
        }
        rest = [nodes[i].get("rotation", [0.0, 0.0, 0.0, 1.0]) for i in order]
        skeleton = cls(
            names=[name_of[i] for i in order],
            parents=parents,
            offsets=[nodes[i].get("translation", [0.0, 0.0, 0.0]) for i in order],
            rest_rotations=[[r[3], r[0], r[1], r[2]] for r in rest],
            bone_map=bone_map,
        )
        # Facing: in a T-pose looking down +Z the left arm points to +X.
        positions = skeleton.forward_kinematics(
            np.tile(skeleton.rest_rotations, (1, 1, 1)), skeleton.offsets[None, 0]
        )[0]
        arm = (
            positions[skeleton.index[bone_map["LeftArm"]]]
            - positions[skeleton.index[bone_map["RightArm"]]]
        )
        skeleton.faces_back = bool(arm[0] < 0)
        return skeleton

    @classmethod
    def from_glb(cls, glb_path):
        gltf, _ = read_glb(glb_path)
        nodes = gltf["nodes"]
        joints = gltf["skins"][0]["joints"]
        parent_of = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

        # Parents before children, so one pass computes the global transforms.
        order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            if parent_of.get(i) in joints:
                visit(parent_of[i])
            seen.add(i)
            order.append(i)

        for j in joints:
            visit(j)

        index = {node: k for k, node in enumerate(order)}
        rest = [nodes[i].get("rotation", [0.0, 0.0, 0.0, 1.0]) for i in order]
        # The Armature node above the hips scales centimetres to metres.
        root_parent = parent_of.get(order[0])
        scale = (
            nodes[root_parent].get("scale", [1.0])[0]
            if root_parent is not None
            else 1.0
        )
        return cls(
            names=[nodes[i]["name"] for i in order],
            parents=[index.get(parent_of.get(i), -1) for i in order],
            offsets=[nodes[i].get("translation", [0.0, 0.0, 0.0]) for i in order],
            # glTF stores (x, y, z, w)
            rest_rotations=[[r[3], r[0], r[1], r[2]] for r in rest],
            armature_scale=scale,
        )

    def save(
        self, path, source="app/client/docs/assets/character/Xbot.glb (Mixamo X Bot)"
    ):
        data = {
            "source": source,
            "names": self.names,
            "parents": self.parents,
            "offsets": np.round(self.offsets, 5).tolist(),
            "rest_rotations": np.round(self.rest_rotations, 7).tolist(),
            "armature_scale": self.armature_scale,
        }
        if self.bone_map != {j: b for j, b in BONE_MAP.items() if b in self.index}:
            data["bone_map"] = self.bone_map
        if self.faces_back:
            data["faces_back"] = True
        if self.body:
            data["body"] = self.body
        with open(path, "w") as f:
            json.dump(data, f, indent=1)

    def bone(self, joint):
        """Index of the bone that plays this MoMask joint, or None."""
        name = self.bone_map.get(joint)
        return None if name is None else self.index[name]

    def leg_length(self):
        """Hips to ankle, in the skeleton's own units."""
        return sum(np.linalg.norm(self.offsets[self.bone(j)]) for j in LEG)

    def feet(self):
        """The lowest bone on each side: the toes, or the foot if there are none."""
        return [
            self.bone(toe) if self.bone(toe) is not None else self.bone(foot)
            for toe, foot in (("LeftToe", "LeftFoot"), ("RightToe", "RightFoot"))
        ]

    def forward_kinematics(
        self, local_rotations, hips_positions, offsets=None, with_rotations=False
    ):
        """Global positions (frames, bones, 3), plus rotations if with_rotations."""
        offsets = self.offsets if offsets is None else offsets
        frames, bones = local_rotations.shape[:2]
        rotations = np.zeros((frames, bones, 4))
        positions = np.zeros((frames, bones, 3))
        for b in range(bones):
            p = self.parents[b]
            if p < 0:
                rotations[:, b] = local_rotations[:, b]
                positions[:, b] = hips_positions
            else:
                rotations[:, b] = qmul(rotations[:, p], local_rotations[:, b])
                positions[:, b] = positions[:, p] + qrotate(rotations[:, p], offsets[b])
        return (positions, rotations) if with_rotations else positions


NOD_JOINTS = ("Neck", "Head")


def soften_nods(anim, keep=0.5, joints=NOD_JOINTS):
    """Scale MoMask's head nods and tips by `keep` and keep its left/right turns (in
    place).

    On a chibi head, MoMask's look at the sky shows the underside of the hood.
    """
    names = list(anim.names)
    if "Head" not in names:
        return anim
    axis = anim.offsets[names.index("Head")]
    axis = axis / np.linalg.norm(axis)
    q = anim.rotations.qs.copy()
    for joint in joints:
        if joint not in names:
            continue
        j = names.index(joint)
        # w >= 0: the short way round
        r = q[:, j] * np.where(q[:, j, :1] < 0, -1.0, 1.0)
        along = r[:, 1:] @ axis
        twist = np.concatenate([r[:, :1], along[:, None] * axis], axis=1)
        twist /= np.maximum(np.linalg.norm(twist, axis=1, keepdims=True), 1e-12)
        swing = qmul(r, qinv(twist))
        swing *= np.where(swing[:, :1] < 0, -1.0, 1.0)
        half = np.arccos(np.clip(swing[:, 0], -1.0, 1.0))
        sin = np.sin(half)
        unit = np.where(
            sin[:, None] > 1e-9, swing[:, 1:] / np.maximum(sin, 1e-12)[:, None], 0.0
        )
        softer = np.concatenate(
            [np.cos(keep * half)[:, None], np.sin(keep * half)[:, None] * unit], axis=1
        )
        q[:, j] = qmul(softer, twist)
    anim.rotations = type(anim.rotations)(q)
    return anim


def source_rest_direction(anim, names, joint):
    child = DIRECTION_CHILD.get(joint)
    if child is None:
        return None
    return anim.offsets[names.index(child)]


def retarget(anim, skeleton):
    """MoMask Animation -> (local rotations (frames, bones, 4), hips positions (frames,
    3)), in the character's own frame and units."""
    names = list(anim.names)
    frames = anim.rotations.shape[0]
    # Work on the character turned to look down +Z, like MoMask.
    flip = np.array([-1.0, 1.0, -1.0]) if skeleton.faces_back else np.ones(3)
    offsets = skeleton.offsets * flip
    rest_rotations = (
        turn_around(skeleton.rest_rotations)
        if skeleton.faces_back
        else skeleton.rest_rotations
    )
    source_of = {b: j for j, b in skeleton.bone_map.items()}

    # 1. Global rotations of the MoMask skeleton.
    local = anim.rotations.qs
    source_global = np.zeros_like(local)
    for j, p in enumerate(anim.parents):
        source_global[:, j] = (
            local[:, j] if p < 0 else qmul(source_global[:, p], local[:, j])
        )

    # 2. Global rotations on Xbot.
    bones = len(skeleton.names)
    target_global = np.zeros((frames, bones, 4))
    for b, name in enumerate(skeleton.names):
        p = skeleton.parents[b]
        parent_global = np.array([1.0, 0.0, 0.0, 0.0]) if p < 0 else target_global[:, p]
        source = source_of.get(name)
        if source is None:
            # Not in MoMask: keep the rest pose relative to the parent.
            target_global[:, b] = qmul(parent_global, rest_rotations[b])
            continue

        correction = np.array([1.0, 0.0, 0.0, 0.0])
        source_dir = source_rest_direction(anim, names, source)
        child = skeleton.bone(DIRECTION_CHILD.get(source))
        if source_dir is not None and child is not None:
            correction = qbetween(offsets[child], source_dir)
        target_global[:, b] = qmul(source_global[:, names.index(source)], correction)

    # 3. Feet flat from side to side, starting from the character's own rest pose; the
    # toes keep their rest bend.
    _, rest_global = skeleton.forward_kinematics(
        rest_rotations[None], np.zeros((1, 3)), offsets, with_rotations=True
    )
    rest_global = rest_global[0]
    for side in ("Left", "Right"):
        foot, toe = skeleton.bone(side + "Foot"), skeleton.bone(side + "Toe")
        if foot is None:
            continue
        source = source_global[:, names.index(side + "Foot")]
        toe_offset = anim.offsets[names.index(side + "Toe")]
        target_global[:, foot] = qmul(level(source, toe_offset), rest_global[foot])
        if toe is not None:
            toe_rest = qmul(qinv(rest_global[foot]), rest_global[toe])
            target_global[:, toe] = qmul(target_global[:, foot], toe_rest)

    # 4. Back to local rotations, which is what the animation stores.
    target_local = np.zeros_like(target_global)
    for b, p in enumerate(skeleton.parents):
        target_local[:, b] = (
            target_global[:, b]
            if p < 0
            else qmul(qinv(target_global[:, p]), target_global[:, b])
        )
    target_local = continuous(
        target_local / np.linalg.norm(target_local, axis=-1, keepdims=True)
    )

    # 5. Hips: MoMask's metres scaled to the character's leg length, feet on the floor.
    source_leg = sum(np.linalg.norm(anim.offsets[names.index(j)]) for j in LEG)
    scale = skeleton.leg_length() / source_leg
    hips = anim.positions[:, 0] * scale

    positions = skeleton.forward_kinematics(target_local, hips, offsets)
    feet_y = positions[:, skeleton.feet(), 1].min(axis=1)
    # The 5th percentile instead of the minimum, so one stray frame can't lift the whole
    # clip.
    hips[:, 1] -= np.percentile(feet_y, 5)

    if skeleton.faces_back:
        target_local, hips = turn_around(target_local), hips * flip
    return target_local, hips
