import bpy
import sys
import os
import math
from mathutils import Vector, Matrix

def get_args():
    argv = sys.argv
    if "--" not in argv:
        return {}
    idx = argv.index("--") + 1
    args = argv[idx:]

    output = {}
    key = None
    for a in args:
        if a.startswith("--"):
            key = a[2:]
            output[key] = True
        else:
            if key is None:
                continue
            output[key] = a
            key = None
    return output

ARGS = get_args()
IN_PATH = ARGS.get("in")
OUT_PATH = ARGS.get("out")

if not IN_PATH or not OUT_PATH:
    raise SystemExit("Error: in and out paths are required")

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def remove_non_mesh_objects():
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT", "EMPTY"}:
            bpy.data.objects.remove(obj, do_unlink=True)

def find_armature():
    arms = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not arms:
        return None
    arms.sort(key=lambda a: len(a.data.bones), reverse=True)
    return arms[0]

def find_skinned_meshes(arm):
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for m in obj.modifiers:
            if m.type == "ARMATURE" and m.object == arm:
                meshes.append(obj)
                break

    if meshes:
        return meshes

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.parent == arm]
    return meshes

def get_world_bbox(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    max_v = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return min_v, max_v

def combined_bbox(objs):
    mins = []
    maxs = []
    for o in objs:
        mn, mx = get_world_bbox(o)
        mins.append(mn)
        maxs.append(mx)
    min_v = Vector((min(m.x for m in mins), min(m.y for m in mins), min(m.z for m in mins)))
    max_v = Vector((max(m.x for m in maxs), max(m.y for m in maxs), max(m.z for m in maxs)))
    return min_v, max_v

def select_only(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0] if objs else None

def apply_transforms(objs):
    select_only(objs)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

def rename_for_consistency(arm, meshes):
    arm.name = "Avatar_Armature"
    arm.data.name = "Avatar_ArmatureData"
    if meshes:
        meshes[0].name = "Avatar_Mesh"
        meshes[0].data.name = "Avatar_MeshData"

def ensure_pose_position(arm):
    bpy.context.view_layer.objects.active = arm
    if arm and arm.type == "ARMATURE":
        arm.data.pose_position = 'POSE'

def set_facing_forward(arm, meshes, target="UNITY_Z_FORWARD"):
    """
    Unity convention: +Y up, +Z forward
    Blender: +Z up, -Y forward in viewport
    For GLB export to Unity, a common safe move is rotating around X by -90
    OR leaving as is and letting Unity import handle it.

    Here we do: rotate character so that it's +Z forward in Unity.
    Typical: rotate around X by -90 degrees (Blender Z-up -> Unity Y-up)
    But GLTF importer often handles axis conversion automatically.

    For consistency, keep Blender Z-up, export GLB, and in Unity use glTFast which handles it.
    So we do nothing by default.
    """
    if target == "NO_OP":
        return

def move_feet_to_ground(arm, meshes):
    objs = [arm] + meshes
    mn, mx = combined_bbox(meshes if meshes else objs)
    # move down/up so min Z is at 0
    dz = -mn.z
    for o in objs:
        o.location.z += dz

def move_root_to_origin(arm, meshes):
    objs = [arm] + meshes

    # current armature origin in world
    arm_world_loc = arm.matrix_world.translation.copy()
    dx, dy = -arm_world_loc.x, -arm_world_loc.y

    for o in objs:
        o.location.x += dx
        o.location.y += dy

def enforce_uniform_scale(arm, meshes, desired_height_m=1.7):
    objs = [arm] + meshes
    mn, mx = combined_bbox(meshes if meshes else objs)
    current_h = mx.z - mn.z
    if current_h <= 1e-6:
        return

    s = desired_height_m / current_h
    for o in objs:
        o.scale.x *= s

def export_glb(out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=out_path,
        export_format='GLB',
        export_apply=True,
        export_yup=True,
        export_skins=True,
        export_animations=True,
        export_materials='EXPORT',
    )