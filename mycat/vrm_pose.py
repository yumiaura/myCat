"""Pose a VRM/glb humanoid by composing delta rotations onto its bones.

A VRM file is a glTF-binary (``.glb``) container. Its ``VRMC_vrm`` extension maps
the standard humanoid bones (hips, spine, upperArm, ...) to glTF node indices,
and every VRM rest pose is a T-pose (arms straight out). To turn that into a
pleasant idle for the desktop pet we compose a small rotation onto a few bones —
chiefly lowering the arms into a relaxed A-pose — and write the glb back out.

This module is deliberately pure stdlib: it parses the glb, edits node rotations
and re-serialises, with **no Qt and no 3D rendering**, so the pose maths is fully
unit-testable in CI. The actual image is produced later by the baker, which feeds
the posed glb returned here to a headless renderer.

Conventions:
- Quaternions use glTF order ``(x, y, z, w)``.
- Euler angles are degrees, applied intrinsically in X, then Y, then Z.
- A delta is ``((x_deg, y_deg, z_deg), mode)`` where ``mode`` is ``"pre"`` to add
  the rotation in the parent/world frame (``delta ∘ existing``) or ``"post"`` to
  add it in the bone's own local frame (``existing ∘ delta``).
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = b"JSON"
BIN_CHUNK = b"BIN\x00"
IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)

# The default relaxed A-pose: drop both T-pose arms ~55° about their local Z axis
# (sign is opposite per side). Verified by rendering N00.vrm — this is the axis
# and sign that bring the arms cleanly down along the body.
RELAXED_A_POSE = {
    "leftUpperArm": ((0.0, 0.0, -55.0), "pre"),
    "rightUpperArm": ((0.0, 0.0, 55.0), "pre"),
    "head": ((3.0, 0.0, 0.0), "pre"),
}


@dataclass
class Glb:
    """A parsed glb: its glTF JSON as a dict plus every raw chunk (JSON + BIN)."""

    gltf: dict
    chunks: list  # list[(chunk_type: bytes, body: bytes)], in file order


def quaternion_multiply(a, b):
    """Hamilton product of two ``(x, y, z, w)`` quaternions."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quaternion_normalize(q):
    x, y, z, w = q
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length == 0.0:
        return IDENTITY_QUAT
    return (x / length, y / length, z / length, w / length)


def euler_to_quaternion(x_deg, y_deg, z_deg):
    """Intrinsic X→Y→Z Euler angles (degrees) to an ``(x, y, z, w)`` quaternion."""
    hx = math.radians(x_deg) / 2.0
    hy = math.radians(y_deg) / 2.0
    hz = math.radians(z_deg) / 2.0
    qx = (math.sin(hx), 0.0, 0.0, math.cos(hx))
    qy = (0.0, math.sin(hy), 0.0, math.cos(hy))
    qz = (0.0, 0.0, math.sin(hz), math.cos(hz))
    return quaternion_multiply(qz, quaternion_multiply(qy, qx))


def read_glb(source) -> Glb:
    """Parse a glb from a path (str/Path) or raw bytes."""
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        data = Path(source).read_bytes()

    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError(f"not a glb container (magic={magic!r})")

    offset = 12
    chunks = []
    gltf = None
    while offset < total:
        length, chunk_type = struct.unpack_from("<I4s", data, offset)
        body = data[offset + 8 : offset + 8 + length]
        chunks.append((chunk_type, body))
        if chunk_type == JSON_CHUNK:
            gltf = json.loads(body)
        offset += 8 + length

    if gltf is None:
        raise ValueError("glb has no JSON chunk")
    return Glb(gltf=gltf, chunks=chunks)


def write_glb(glb: Glb) -> bytes:
    """Serialise a :class:`Glb` back to glb bytes.

    The JSON chunk is regenerated from ``glb.gltf`` (so pose edits are picked up);
    all other chunks (the binary buffer) are copied through untouched.
    """
    payload = json.dumps(glb.gltf, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)  # pad JSON with spaces

    out = bytearray(struct.pack("<4sII", GLB_MAGIC, GLB_VERSION, 0))
    out += struct.pack("<I4s", len(payload), JSON_CHUNK) + payload
    for chunk_type, body in glb.chunks:
        if chunk_type == JSON_CHUNK:
            continue
        pad = (4 - len(body) % 4) % 4
        filler = b"\x00" if chunk_type == BIN_CHUNK else b" "
        body = bytes(body) + filler * pad
        out += struct.pack("<I4s", len(body), chunk_type) + body

    struct.pack_into("<I", out, 8, len(out))  # patch total length
    return bytes(out)


def humanoid_bone_nodes(gltf: dict) -> dict:
    """Map humanoid bone name → glTF node index for VRM 1.0 or VRM 0.x."""
    extensions = gltf.get("extensions", {})

    vrm1 = extensions.get("VRMC_vrm")
    if vrm1 is not None:
        human_bones = vrm1.get("humanoid", {}).get("humanBones", {})
        return {
            name: entry["node"]
            for name, entry in human_bones.items()
            if isinstance(entry, dict) and "node" in entry
        }

    vrm0 = extensions.get("VRM")
    if vrm0 is not None:
        result = {}
        for entry in vrm0.get("humanoid", {}).get("humanBones", []):
            if "bone" in entry and "node" in entry:
                result[entry["bone"]] = entry["node"]
        return result

    return {}


def apply_pose(gltf: dict, deltas: dict) -> list:
    """Compose each delta onto its bone's local rotation, in place.

    Returns the list of bone names that were actually applied (bones absent from
    the model are skipped silently). Existing authored rotations are preserved —
    the delta is *composed onto* them, never replaced — so finger curls and neck
    tilt from the source model survive.
    """
    bone_nodes = humanoid_bone_nodes(gltf)
    nodes = gltf.get("nodes", [])
    applied = []
    for bone_name, (euler, mode) in deltas.items():
        node_index = bone_nodes.get(bone_name)
        if node_index is None:
            continue
        node = nodes[node_index]
        existing = tuple(node.get("rotation", IDENTITY_QUAT))
        delta = euler_to_quaternion(*euler)
        if mode == "pre":
            combined = quaternion_multiply(delta, existing)
        elif mode == "post":
            combined = quaternion_multiply(existing, delta)
        else:
            raise ValueError(f"unknown compose mode {mode!r} (want 'pre' or 'post')")
        node["rotation"] = list(quaternion_normalize(combined))
        applied.append(bone_name)
    return applied


def pose_glb_bytes(data, deltas: dict = RELAXED_A_POSE) -> bytes:
    """Read glb ``data``, apply ``deltas``, return the posed glb as bytes."""
    glb = read_glb(data)
    apply_pose(glb.gltf, deltas)
    return write_glb(glb)


def pose_glb_file(src, dst, deltas: dict = RELAXED_A_POSE) -> list:
    """Pose the glb at ``src`` and write the result to ``dst``. Returns applied bones."""
    glb = read_glb(src)
    applied = apply_pose(glb.gltf, deltas)
    Path(dst).write_bytes(write_glb(glb))
    return applied


__all__ = [
    "Glb",
    "IDENTITY_QUAT",
    "RELAXED_A_POSE",
    "quaternion_multiply",
    "quaternion_normalize",
    "euler_to_quaternion",
    "read_glb",
    "write_glb",
    "humanoid_bone_nodes",
    "apply_pose",
    "pose_glb_bytes",
    "pose_glb_file",
]
