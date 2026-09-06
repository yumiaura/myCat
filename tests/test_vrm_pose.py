"""Unit tests for the pure-stdlib VRM pose maths (no Qt, no rendering)."""

import math

import pytest

from mycat import vrm_pose


def make_glb_bytes():
    """A minimal but valid glb with a VRM 1.0 humanoid and a real BIN chunk.

    Nodes: 0=hips, 1=leftUpperArm, 2=rightUpperArm, 3=head. Node 3 carries a
    non-identity authored rotation so we can prove pose composition preserves it.
    """
    authored_head = list(vrm_pose.euler_to_quaternion(0.0, 20.0, 0.0))
    gltf = {
        "asset": {"version": "2.0"},
        "nodes": [
            {"name": "hips"},
            {"name": "leftUpperArm"},
            {"name": "rightUpperArm"},
            {"name": "head", "rotation": authored_head},
        ],
        "extensions": {
            "VRMC_vrm": {
                "specVersion": "1.0",
                "humanoid": {
                    "humanBones": {
                        "hips": {"node": 0},
                        "leftUpperArm": {"node": 1},
                        "rightUpperArm": {"node": 2},
                        "head": {"node": 3},
                    }
                },
            }
        },
    }
    bin_data = b"binary-buffer-payload-123"  # arbitrary; must survive a round-trip
    glb = vrm_pose.Glb(gltf=gltf, chunks=[(vrm_pose.JSON_CHUNK, b"{}"), (vrm_pose.BIN_CHUNK, bin_data)])
    return vrm_pose.write_glb(glb), bin_data, authored_head


def quats_close(a, b, tol=1e-6):
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b))


def test_euler_identity_and_known_rotations():
    assert quats_close(vrm_pose.euler_to_quaternion(0, 0, 0), vrm_pose.IDENTITY_QUAT)
    # 90° about Z → (0, 0, sin45, cos45)
    s = math.sin(math.radians(45))
    assert quats_close(vrm_pose.euler_to_quaternion(0, 0, 90), (0.0, 0.0, s, s))
    # 180° about Y → (0, 1, 0, 0)
    assert quats_close(vrm_pose.euler_to_quaternion(0, 180, 0), (0.0, 1.0, 0.0, 0.0), tol=1e-6)


def test_quaternion_multiply_identity():
    q = vrm_pose.euler_to_quaternion(10, 20, 30)
    assert quats_close(vrm_pose.quaternion_multiply(q, vrm_pose.IDENTITY_QUAT), q)
    assert quats_close(vrm_pose.quaternion_multiply(vrm_pose.IDENTITY_QUAT, q), q)


def test_normalize_unit_and_zero():
    assert quats_close(vrm_pose.quaternion_normalize((0, 0, 0, 2)), (0, 0, 0, 1))
    assert vrm_pose.quaternion_normalize((0, 0, 0, 0)) == vrm_pose.IDENTITY_QUAT


def test_glb_roundtrip_preserves_json_and_bin():
    data, bin_data, _ = make_glb_bytes()
    glb = vrm_pose.read_glb(data)
    assert glb.gltf["asset"]["version"] == "2.0"
    assert [n["name"] for n in glb.gltf["nodes"]] == ["hips", "leftUpperArm", "rightUpperArm", "head"]
    bin_chunks = [body for ctype, body in glb.chunks if ctype == vrm_pose.BIN_CHUNK]
    assert len(bin_chunks) == 1
    assert bin_chunks[0].startswith(bin_data)  # padded to 4 bytes, payload intact


def test_read_glb_rejects_non_glb():
    with pytest.raises(ValueError):
        vrm_pose.read_glb(b"not-a-glb-file-at-all")


def test_humanoid_bone_nodes_vrm1():
    data, _, _ = make_glb_bytes()
    glb = vrm_pose.read_glb(data)
    assert vrm_pose.humanoid_bone_nodes(glb.gltf) == {
        "hips": 0,
        "leftUpperArm": 1,
        "rightUpperArm": 2,
        "head": 3,
    }


def test_humanoid_bone_nodes_vrm0_fallback():
    gltf = {
        "extensions": {
            "VRM": {"humanoid": {"humanBones": [
                {"bone": "hips", "node": 5},
                {"bone": "head", "node": 9},
            ]}}
        }
    }
    assert vrm_pose.humanoid_bone_nodes(gltf) == {"hips": 5, "head": 9}


def test_apply_pose_lowers_arms_and_reports_applied():
    data, _, _ = make_glb_bytes()
    glb = vrm_pose.read_glb(data)
    applied = vrm_pose.apply_pose(glb.gltf, {
        "leftUpperArm": ((0.0, 0.0, -55.0), "pre"),
        "rightUpperArm": ((0.0, 0.0, 55.0), "pre"),
    })
    assert set(applied) == {"leftUpperArm", "rightUpperArm"}
    # left arm now carries exactly the -55° about-Z delta (existing was identity)
    left = glb.gltf["nodes"][1]["rotation"]
    assert quats_close(left, vrm_pose.euler_to_quaternion(0, 0, -55))
    # hips (not in deltas) stays unrotated
    assert "rotation" not in glb.gltf["nodes"][0]


def test_apply_pose_composes_onto_authored_rotation():
    data, _, authored_head = make_glb_bytes()
    glb = vrm_pose.read_glb(data)
    vrm_pose.apply_pose(glb.gltf, {"head": ((10.0, 0.0, 0.0), "pre")})
    head = glb.gltf["nodes"][3]["rotation"]
    expected = vrm_pose.quaternion_normalize(
        vrm_pose.quaternion_multiply(vrm_pose.euler_to_quaternion(10, 0, 0), tuple(authored_head))
    )
    assert quats_close(head, expected)
    # composition is not a plain overwrite: the authored tilt still contributes
    assert not quats_close(head, vrm_pose.euler_to_quaternion(10, 0, 0))


def test_apply_pose_skips_missing_bone():
    data, _, _ = make_glb_bytes()
    glb = vrm_pose.read_glb(data)
    applied = vrm_pose.apply_pose(glb.gltf, {"leftToes": ((0.0, 0.0, 10.0), "pre")})
    assert applied == []


def test_apply_pose_rejects_bad_mode():
    data, _, _ = make_glb_bytes()
    glb = vrm_pose.read_glb(data)
    with pytest.raises(ValueError):
        vrm_pose.apply_pose(glb.gltf, {"head": ((0.0, 0.0, 10.0), "sideways")})


def test_idle_motion_frame_zero_is_rest():
    frame = vrm_pose.idle_motion(0, 10)
    # sin(0) == 0, so the arms sit at the plain relaxed A-pose angles
    assert frame["leftUpperArm"] == ((0.0, 0.0, -55.0), "pre")
    assert frame["rightUpperArm"] == ((0.0, 0.0, 55.0), "pre")
    assert frame["spine"] == ((0.0, 0.0, 0.0), "pre")


def test_idle_motion_moves_mid_loop():
    mid = vrm_pose.idle_motion(3, 10)
    # partway through the loop the arms have swung off the rest angle
    assert mid["leftUpperArm"][0][2] != -55.0


def test_wave_motion_endpoints_are_rest():
    total = 10
    for frame_index in (0, total - 1):
        frame = vrm_pose.wave_motion(frame_index, total)
        # arm back down at both ends (sin envelope ~0; allow float epsilon at p=1)
        assert math.isclose(frame["rightUpperArm"][0][2], 55.0, abs_tol=1e-6)


def test_wave_motion_lifts_arm_at_peak():
    frame = vrm_pose.wave_motion(5, 10)  # near the envelope peak
    assert frame["rightUpperArm"][0][2] < 0.0  # arm raised well above the resting +55


def test_motions_registry():
    assert vrm_pose.MOTIONS["idle"] is vrm_pose.idle_motion
    assert vrm_pose.MOTIONS["wave"] is vrm_pose.wave_motion


def test_pose_glb_bytes_end_to_end():
    data, bin_data, _ = make_glb_bytes()
    posed = vrm_pose.pose_glb_bytes(data, vrm_pose.RELAXED_A_POSE)
    glb = vrm_pose.read_glb(posed)  # still a valid, re-readable glb
    # arms moved
    assert "rotation" in glb.gltf["nodes"][1]
    assert "rotation" in glb.gltf["nodes"][2]
    # binary buffer preserved through the pose+rewrite
    bin_chunks = [body for ctype, body in glb.chunks if ctype == vrm_pose.BIN_CHUNK]
    assert bin_chunks[0].startswith(bin_data)
