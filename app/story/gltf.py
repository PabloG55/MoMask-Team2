"""The retargeted motion as .glb: bones and clips only, the client has the mesh."""

import json
import struct

import numpy as np

from story.retarget import read_glb

FLOAT, SHORT = 5126, 5122  # glTF componentType codes


def _pad(data, fill=b"\x00"):
    return data + fill * (-len(data) % 4)


class _Buffer:

    def __init__(self, gltf, binary=b""):
        self.gltf = gltf
        self.data = bytearray(_pad(binary))
        gltf.setdefault("bufferViews", [])
        gltf.setdefault("accessors", [])

    def add(
        self, array, accessor_type, component=FLOAT, normalized=False, minmax=False
    ):
        array = np.ascontiguousarray(array)
        raw = array.astype(np.float32 if component == FLOAT else np.int16).tobytes()
        self.gltf["bufferViews"].append(
            {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(raw)}
        )
        self.data += _pad(raw)
        accessor = {
            "bufferView": len(self.gltf["bufferViews"]) - 1,
            "componentType": component,
            "count": len(array),
            "type": accessor_type,
        }
        if normalized:
            accessor["normalized"] = True
        if minmax:
            flat = array.reshape(len(array), -1)
            accessor["min"] = flat.min(axis=0).tolist()
            accessor["max"] = flat.max(axis=0).tolist()
        self.gltf["accessors"].append(accessor)
        return len(self.gltf["accessors"]) - 1


def _add_clip(
    buffer,
    node_of,
    local_rotations,
    hips_positions,
    fps,
    bone_names,
    hips,
    name,
    quantize,
):
    frames = len(local_rotations)
    times = buffer.add(np.arange(frames) / fps, "SCALAR", minmax=True)
    samplers, channels = [], []

    def track(node, path, values, **kwargs):
        samplers.append(
            {
                "input": times,
                "output": buffer.add(values, **kwargs),
                "interpolation": "LINEAR",
            }
        )
        channels.append(
            {"sampler": len(samplers) - 1, "target": {"node": node, "path": path}}
        )

    for b, bone in enumerate(bone_names):
        q = local_rotations[:, b]
        # Bones that never leave their rest pose don't need a track.
        if np.allclose(q, q[0], atol=1e-6) and np.allclose(
            q[0], [1, 0, 0, 0], atol=1e-6
        ):
            continue
        xyzw = q[:, [1, 2, 3, 0]]
        if quantize:
            # glTF allows normalized shorts for rotations: half the bytes, ~0.00003
            # error.
            track(
                node_of[bone],
                "rotation",
                np.round(xyzw * 32767),
                accessor_type="VEC4",
                component=SHORT,
                normalized=True,
            )
        else:
            track(node_of[bone], "rotation", xyzw, accessor_type="VEC4")
    track(node_of[hips], "translation", hips_positions, accessor_type="VEC3")

    return {"name": name, "samplers": samplers, "channels": channels}


def _write(path, gltf, data):
    gltf["buffers"] = [{"byteLength": len(data)}]
    text = _pad(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
    data = _pad(bytes(data))
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(data)))
        f.write(struct.pack("<II", len(text), 0x4E4F534A) + text)
        f.write(struct.pack("<II", len(data), 0x004E4942) + data)
    return path


def animation_glb(
    path, skeleton, local_rotations, hips_positions, fps, name="story", quantize=True
):
    """Xbot's bone hierarchy (rest pose, no mesh) plus one clip."""
    nodes = []
    for b, bone in enumerate(skeleton.names):
        r = skeleton.rest_rotations[b]
        nodes.append(
            {
                "name": bone,
                "translation": skeleton.offsets[b].tolist(),
                "rotation": [r[1], r[2], r[3], r[0]],
                "children": [],
            }
        )
    for b, p in enumerate(skeleton.parents):
        if p >= 0:
            nodes[p]["children"].append(b)
    for n in nodes:
        if not n["children"]:
            del n["children"]
    armature = len(nodes)
    s = skeleton.armature_scale
    nodes.append({"name": "Armature", "scale": [s, s, s], "children": [0]})

    gltf = {
        "asset": {"version": "2.0", "generator": "MoMask Team 2 (ITCS 6166)"},
        "scene": 0,
        "scenes": [{"nodes": [armature]}],
        "nodes": nodes,
    }
    buffer = _Buffer(gltf)
    node_of = {bone: b for b, bone in enumerate(skeleton.names)}
    gltf["animations"] = [
        _add_clip(
            buffer,
            node_of,
            local_rotations,
            hips_positions,
            fps,
            skeleton.names,
            skeleton.hips,
            name,
            quantize,
        )
    ]
    return _write(path, gltf, buffer.data)


def character_glb(
    path, character_path, skeleton, local_rotations, hips_positions, fps, name="story"
):
    """The character's own .glb with its clips replaced by this one."""
    gltf, binary = read_glb(character_path)
    gltf.pop("animations", None)
    buffer = _Buffer(gltf, binary)
    gltf["buffers"] = [{"byteLength": len(buffer.data)}]
    node_of = {n["name"]: i for i, n in enumerate(gltf["nodes"]) if "name" in n}
    gltf["animations"] = [
        _add_clip(
            buffer,
            node_of,
            local_rotations,
            hips_positions,
            fps,
            skeleton.names,
            skeleton.hips,
            name,
            False,
        )
    ]
    return _write(path, gltf, buffer.data)
