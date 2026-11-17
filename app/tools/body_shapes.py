"""Measure each character's body from its VRM mesh, for story/collide.py.

Runs once per character, from tools/character_skeletons.py; the server reads the result
from story/characters/<Name>.json and never opens a mesh.
"""

import numpy as np
from scipy.spatial import Delaunay
from scipy.spatial.transform import Rotation

from story.collide import SIDES, Body, level

ACROSS = (2.0, 3.0, 4.0)  # seen from above: 2 round, 4 boxy
ALONG = (2.0, 3.0, 4.0, 6.0)  # along the bone: 2 egg-like, 6 flat-ended
SCALES = np.linspace(0.8, 1.4, 13)
MISS_WEIGHT = 3  # body left outside a shape costs 3x the air inside it

_COMPONENT = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _accessor(gltf, binary, index):
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    dtype = np.dtype(_COMPONENT[accessor["componentType"]])
    width = _WIDTH[accessor["type"]]
    count = accessor["count"]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or dtype.itemsize * width
    if stride == dtype.itemsize * width:
        return np.frombuffer(binary, dtype, count * width, start).reshape(count, width)
    rows = [
        np.frombuffer(binary, dtype, width, start + k * stride) for k in range(count)
    ]
    return np.stack(rows)


def _node_matrix(node):
    if "matrix" in node:
        # glTF is column-major
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    rotation = Rotation.from_quat(node.get("rotation", [0.0, 0.0, 0.0, 1.0]))
    m = np.eye(4)
    m[:3, :3] = rotation.as_matrix() * np.array(node.get("scale", [1.0, 1.0, 1.0]))
    m[:3, 3] = node.get("translation", [0.0, 0.0, 0.0])
    return m


def _world_matrices(gltf):
    nodes = gltf["nodes"]
    world = [None] * len(nodes)

    def visit(i, parent):
        world[i] = parent @ _node_matrix(nodes[i])
        for c in nodes[i].get("children", []):
            visit(c, world[i])

    children = {c for n in nodes for c in n.get("children", [])}
    for root in range(len(nodes)):
        if root not in children:
            visit(root, np.eye(4))
    return world


def _rest_vertices(gltf, binary):
    """Rest-pose world position of every skinned vertex, with its main bone's node."""
    world = _world_matrices(gltf)
    points, owners = [], []
    for node in gltf["nodes"]:
        if "mesh" not in node or "skin" not in node:
            continue
        skin = gltf["skins"][node["skin"]]
        inverse_bind = _accessor(gltf, binary, skin["inverseBindMatrices"]).reshape(
            -1, 4, 4
        )
        inverse_bind = np.transpose(inverse_bind, (0, 2, 1))  # column-major
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            attributes = primitive["attributes"]
            if not {"POSITION", "JOINTS_0", "WEIGHTS_0"} <= set(attributes):
                continue
            position = _accessor(gltf, binary, attributes["POSITION"]).astype(float)
            joints = _accessor(gltf, binary, attributes["JOINTS_0"]).astype(int)
            weights = _accessor(gltf, binary, attributes["WEIGHTS_0"]).astype(float)
            main = joints[np.arange(len(joints)), weights.argmax(axis=1)]
            for j in np.unique(main):
                matrix = world[skin["joints"][j]] @ inverse_bind[j]
                chosen = position[main == j]
                # Accelerate's matmul warns spuriously on macOS
                with np.errstate(all="ignore"):
                    points.append(chosen @ matrix[:3, :3].T + matrix[:3, 3])
                owners.extend([skin["joints"][j]] * len(chosen))
    points = np.concatenate(points)
    if not np.isfinite(points).all():
        raise ValueError("mesh has non-finite vertices")
    return points, np.array(owners)


def _descendants(skeleton, bone):
    out = {bone}
    for b in range(len(skeleton.names)):
        p = skeleton.parents[b]
        if p in out:
            out.add(b)
    return out


def _segment_distance(points, a, b):
    ab = b - a
    t = np.clip(((points - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(points - (a + t[:, None] * ab), axis=1)


def _fit(local, seed=0):
    """The superquadric (center, radii, across, along) that best fits the points."""
    low, high = np.percentile(local, 2, axis=0), np.percentile(local, 98, axis=0)
    center, half = (low + high) / 2, np.maximum((high - low) / 2, 1e-3)
    reach = np.maximum(np.abs(local - center).max(axis=0), half * SCALES[-1])
    samples = center + np.random.default_rng(seed).uniform(-reach, reach, (30000, 3))
    in_hull = Delaunay(local).find_simplex(samples) >= 0
    u = np.abs((samples - center) / half)
    best = None
    for across in ACROSS:
        for along in ALONG:
            fit = level(u, across, along)
            for scale in SCALES:
                inside = fit <= scale
                air = (inside & ~in_hull).sum() / max(inside.sum(), 1)
                miss = (in_hull & ~inside).sum() / max(in_hull.sum(), 1)
                cost = air + MISS_WEIGHT * miss
                if best is None or cost < best[0]:
                    best = (cost, half * scale, across, along)
    return center, best[1], best[2], best[3]


def body_shapes(gltf, binary, skeleton):
    """Body parts and arm sizes from a VRM mesh, in bone frames; None if unreadable."""
    try:
        vertices, owner_nodes = _rest_vertices(gltf, binary)
    except (KeyError, ValueError, IndexError):
        return None
    node_index = {n.get("name"): i for i, n in enumerate(gltf["nodes"])}
    rest = np.tile(skeleton.rest_rotations, (1, 1, 1))
    hips = skeleton.index[skeleton.hips]
    positions, rotations = skeleton.forward_kinematics(
        rest, skeleton.offsets[None, hips], with_rotations=True
    )
    positions, rotations = positions[0], rotations[0]
    owner = np.full(len(vertices), -1)
    for b, name in enumerate(skeleton.names):
        owner[owner_nodes == node_index.get(name, -2)] = b

    def to_local(bone, points):
        r = Rotation.from_quat(rotations[bone], scalar_first=True).as_matrix()
        return (points - positions[bone]) @ r

    def bones_of(*joints):
        return {skeleton.bone(j) for j in joints if skeleton.bone(j) is not None}

    # (bone it moves with, bones whose vertices make it, arm part tested against it).
    # The upper arm starts at the chest, so only the forearm and hand are tested against
    # the trunk.
    head = skeleton.bone("Head")
    groups = []
    if head is not None:
        groups.append((head, _descendants(skeleton, head), "arm"))
    chest = (
        skeleton.bone("Spine2")
        if skeleton.bone("Spine2") is not None
        else skeleton.bone("Spine1")
    )
    belly = bones_of("Hips", "Spine")
    if chest is not None:
        groups.append((chest, bones_of("Spine1", "Spine2"), "forearm"))
    if skeleton.bone("Hips") is not None:
        groups.append((skeleton.bone("Hips"), belly, "forearm"))
    # A round belly that bends with the spine (Teddy) gets its own shape.
    if skeleton.bone("Spine") is not None:
        groups.append((skeleton.bone("Spine"), bones_of("Spine"), "forearm"))
    for side in SIDES:
        if skeleton.bone(side + "UpLeg") is not None:
            groups.append(
                (skeleton.bone(side + "UpLeg"), bones_of(side + "UpLeg"), "forearm")
            )

    shapes = []
    for frame, bones, against in groups:
        local = to_local(frame, vertices[np.isin(owner, list(bones))])
        if len(local) < 20:
            continue
        center, radii, across, along = _fit(local)
        shapes.append(
            {
                "bone": skeleton.names[frame],
                "against": against,
                "across": across,
                "along": along,
                "center": np.round(center, 5).tolist(),
                "radii": np.round(radii, 5).tolist(),
            }
        )

    arms = {}
    for side in SIDES:
        upper, fore, hand = (
            skeleton.bone(side + j) for j in ("Arm", "ForeArm", "Hand")
        )
        if None in (upper, fore, hand):
            continue
        shoulder, elbow, wrist = positions[upper], positions[fore], positions[hand]

        def thickness(bones, a, b):
            chosen = vertices[np.isin(owner, list(bones))]
            return (
                float(np.percentile(_segment_distance(chosen, a, b), 80))
                if len(chosen)
                else 0.03
            )

        hand_bones = _descendants(skeleton, hand)
        hand_points = vertices[np.isin(owner, list(hand_bones))]
        along = (elbow - wrist) * -1
        along /= np.linalg.norm(along)
        reach = (
            float(((hand_points - wrist) @ along).max()) if len(hand_points) else 0.08
        )
        tip = wrist + along * max(reach, 0.02)
        arms[side] = {
            "upper_radius": round(thickness({upper}, shoulder, elbow), 4),
            "fore_radius": round(thickness({fore}, elbow, wrist), 4),
            "hand_radius": round(thickness(hand_bones, wrist, tip), 4),
            "hand_tip": np.round(to_local(hand, tip[None])[0], 5).tolist(),
        }
    if not shapes or not arms:
        return None
    # The rest pose doesn't touch itself, so shrink any part that reaches an arm there.
    for shape in shapes:
        radii = np.array(shape["radii"])
        for scale in np.linspace(1.0, 0.6, 41):
            shape["radii"] = np.round(radii * scale, 5).tolist()
            body = Body(
                skeleton, rest, positions[None, hips], {"shapes": [shape], "arms": arms}
            )
            if all(body.depth(0, *body.arm(side, 0)[1:])[0] <= 0 for side in arms):
                break
    return {"shapes": shapes, "arms": arms}
