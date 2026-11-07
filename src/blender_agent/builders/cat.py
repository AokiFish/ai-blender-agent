"""猫形口播角色 —— 确定性参数化构建器（在 Blender 内执行的 bpy 代码）。

设计原则：几何、材质、控制器、UV、绑定全部由代码精确计算，
不依赖 LLM 即兴写建模代码，因此每次运行结果一致、可复现。

坐标系：角色面朝 -Y（Blender 前视图方向），Z 向上。
"""

SCRIPT = r'''
import bpy, math, os
from mathutils import Vector

WS = "D:/Mydata/WorkBuddy/AI-blender-agent/workspace"

# ---------------- 清场 ----------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.lights, bpy.data.cameras):
    for b in list(block):
        if b.users == 0:
            block.remove(b)

# ---------------- 材质 ----------------
def _bsdf(nt):
    """按类型取 Principled 节点（Blender 中文界面下节点名被本地化，不能按名字取）。"""
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    raise RuntimeError("no principled node")

def _sock(node, names, idx):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return node.inputs[idx]

def mat(name, color, rough=0.55, stripes=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = _bsdf(nt)
    _sock(bsdf, ("Base Color", "基础色"), 0).default_value = (*color, 1)
    _sock(bsdf, ("Roughness", "粗糙度"), 9).default_value = rough
    try:
        _sock(bsdf, ("Emission Strength", "自发光强度"), 26).default_value = 0.0
    except Exception:
        pass
    if stripes:
        tex = nt.nodes.new("ShaderNodeTexWave")
        tex.wave_type = 'BANDS'
        tex.bands_direction = 'Z'
        tex.inputs["Scale"].default_value = 3.0
        tex.inputs["Distortion"].default_value = 2.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.45
        ramp.color_ramp.elements[0].color = (*color, 1)
        ramp.color_ramp.elements[1].position = 0.55
        dark = tuple(c * 0.62 for c in color)
        ramp.color_ramp.elements[1].color = (*dark, 1)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], _sock(bsdf, ("Base Color", "基础色"), 0))
    m.diffuse_color = (*color, 1)
    return m

M_FUR   = mat("Cat_Fur", (0.92, 0.50, 0.16), 0.60, stripes=True)
M_WHITE = mat("Cat_White", (0.92, 0.87, 0.80), 0.6)
M_PINK  = mat("Cat_Pink", (0.95, 0.55, 0.62), 0.45)
M_DARK  = mat("Cat_Dark", (0.10, 0.07, 0.07), 0.9)
M_IRIS  = mat("Cat_Iris", (0.55, 0.30, 0.06), 0.25)
M_GOLD  = mat("Cat_Gold", (0.90, 0.72, 0.20), 0.25)

# ---------------- 几何工具 ----------------
def sphere(name, loc, scale, material, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o

def cone(name, loc, scale, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=1.0, radius2=0.0, depth=2.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    o.rotation_euler = rot
    bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o

def torus(name, loc, major, minor, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(location=loc, major_radius=major, minor_radius=minor,
                                     major_segments=48, minor_segments=12)
    o = bpy.context.active_object
    o.name = name
    o.rotation_euler = rot
    bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o

def cylinder(name, loc, radius, depth, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=depth, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.rotation_euler = rot
    o.data.materials.append(material)
    return o

parts = {}

# ---------------- 头部 ----------------
HEAD_C = Vector((0.0, 0.0, 1.80))
HEAD_R = Vector((1.02, 0.94, 0.92))          # 椭球半轴
parts["head"] = sphere("Cat_Head", HEAD_C, HEAD_R, M_FUR, 64, 32)

def surf_y(x, z, inset=0.0):
    """头椭球正面（-Y 侧）在 (x,z) 处的 y 值。"""
    tx = 1.0 - (x / HEAD_R.x) ** 2 - ((z - HEAD_C.z) / HEAD_R.z) ** 2
    return HEAD_C.y - HEAD_R.y * math.sqrt(max(tx, 0.0)) + inset

# ---------------- 吻部 / 鼻 / 嘴 ----------------
parts["muzzle"] = sphere("Cat_Muzzle", (0, surf_y(0, 1.48, 0.15), 1.48),
                         (0.31, 0.23, 0.19), M_WHITE)
parts["nose"] = sphere("Cat_Nose", (0, surf_y(0, 1.66, 0.02), 1.66),
                       (0.115, 0.075, 0.085), M_PINK)
parts["mouth"] = sphere("Cat_Mouth", (0, surf_y(0, 1.38, -0.16), 1.38),
                        (0.115, 0.045, 0.042), M_DARK)
parts["tongue"] = sphere("Cat_Tongue", (0, surf_y(0, 1.35, -0.19), 1.35),
                         (0.075, 0.03, 0.035), M_PINK)

# 笑线：两段小圆弧（用压扁的球体近似嘴角）
for side, sx in (("L", -1), ("R", 1)):
    parts[f"mouth_corner_{side}"] = sphere(
        f"Cat_MouthCorner_{side}", (0.17 * sx, surf_y(0.17 * sx, 1.47, 0.06), 1.47),
        (0.10, 0.05, 0.05), M_DARK)

# ---------------- 眼睛（巩膜 + 虹膜 + 瞳孔） ----------------
EYE_X, EYE_Z = 0.40, 1.94
for side, sx in (("L", -1), ("R", 1)):
    ex = EYE_X * sx
    ey = surf_y(ex, EYE_Z, 0.06)
    parts[f"eye_{side}"] = sphere(f"Cat_Eye_{side}", (ex, ey, EYE_Z), (0.205, 0.205, 0.215), M_WHITE)
    parts[f"iris_{side}"] = sphere(f"Cat_Iris_{side}", (ex, ey - 0.185, EYE_Z),
                                   (0.185, 0.075, 0.190), M_IRIS)
    parts[f"pupil_{side}"] = sphere(f"Cat_Pupil_{side}", (ex, ey - 0.235, EYE_Z),
                                    (0.095, 0.045, 0.110), M_DARK)
    parts[f"glint_{side}"] = sphere(f"Cat_Glint_{side}",
        (ex - 0.055 * sx, ey - 0.28, EYE_Z + 0.075), (0.032, 0.020, 0.032), M_WHITE)

# ---------------- 耳朵 ----------------
for side, sx in (("L", -1), ("R", 1)):
    parts[f"ear_{side}"] = cone(f"Cat_Ear_{side}", (0.60 * sx, HEAD_C.y + 0.02, 2.62),
                                (0.30, 0.17, 0.36), M_FUR, rot=(math.radians(-8), math.radians(14) * sx, 0))
    parts[f"ear_in_{side}"] = cone(f"Cat_EarInner_{side}", (0.60 * sx, HEAD_C.y - 0.10, 2.56),
                                   (0.18, 0.10, 0.26), M_PINK, rot=(math.radians(-8), math.radians(14) * sx, 0))

# ---------------- 胡须 ----------------
for side, sx in (("L", -1), ("R", 1)):
    for i, (dz, tilt) in enumerate([(0.10, 8), (0.0, 0), (-0.09, -8)], start=1):
        base_x = 0.42 * sx
        parts[f"whisker_{side}{i}"] = cylinder(
            f"Cat_Whisker_{side}{i}",
            (base_x + 0.28 * sx, surf_y(0.30 * sx, 1.52) - 0.06, 1.52 + dz),
            0.011, 0.62, M_WHITE,
            rot=(0, math.radians(tilt + 78) * sx, 0))

# ---------------- 身体 / 前爪 / 尾 ----------------
parts["body"] = sphere("Cat_Body", (0, 0.08, 0.68), (0.92, 0.80, 0.72), M_FUR, 48, 24)
for side, sx in (("L", -1), ("R", 1)):
    parts[f"paw_{side}"] = sphere(f"Cat_Paw_{side}", (0.30 * sx, -0.56, 0.42),
                                  (0.175, 0.26, 0.16), M_WHITE)
    parts[f"paw_toe_{side}"] = sphere(f"Cat_PawToe_{side}", (0.30 * sx, -0.74, 0.40),
                                      (0.15, 0.10, 0.11), M_PINK)

tail_pts = [Vector((0.62, 0.62, 0.55)), Vector((0.86, 0.90, 0.95)), Vector((0.92, 1.02, 1.42))]
for i, p in enumerate(tail_pts, start=1):
    parts[f"tail{i}"] = sphere(f"Cat_Tail{i}", p, (0.13, 0.13, 0.22), M_FUR, 24, 12)

# ---------------- 项圈 / 铃铛 / 蝴蝶结 ----------------
parts["collar"] = torus("Cat_Collar", (0, 0.06, 1.12), 0.66, 0.065, M_PINK, rot=(math.radians(8), 0, 0))
parts["bell"] = sphere("Cat_Bell", (0, -0.58, 1.02), (0.115, 0.10, 0.12), M_GOLD)
for side, sx in (("L", -1), ("R", 1)):
    parts[f"bow_{side}"] = sphere(f"Cat_Bow_{side}", (0.17 * sx, -0.62, 1.16),
                                  (0.17, 0.07, 0.11), M_PINK)
parts["bow_c"] = sphere("Cat_BowCenter", (0, -0.66, 1.16), (0.06, 0.05, 0.06), M_PINK)

# ---------------- Shape Keys：眨眼 / 口型 ----------------
def add_blink(objs, name="Blink"):
    for o in objs:
        if o.data.shape_keys is None:
            o.shape_key_add(name="Base", from_mix=False)
        key = o.shape_key_add(name=name, from_mix=False)
        cz = sum(v.co.z for v in o.data.vertices) / len(o.data.vertices)
        cx = sum(v.co.x for v in o.data.vertices) / len(o.data.vertices)
        for i, v in enumerate(o.data.vertices):
            key.data[i].co = Vector((v.co.x, v.co.y, cz + (v.co.z - cz) * 0.08))
        key.slider_min, key.slider_max = 0.0, 1.0

add_blink([parts["eye_L"], parts["eye_R"], parts["iris_L"], parts["iris_R"],
           parts["pupil_L"], parts["pupil_R"],
           parts["glint_L"], parts["glint_R"]])

mouth = parts["mouth"]
mouth.shape_key_add(name="Base", from_mix=False)
open_k = mouth.shape_key_add(name="MouthOpen", from_mix=False)
mz = sum(v.co.z for v in mouth.data.vertices) / len(mouth.data.vertices)
for i, v in enumerate(mouth.data.vertices):
    # 绕嘴中心把 Z 方向放大 -> 明显张口；略微前移避免被吻部遮住
    open_k.data[i].co = Vector((v.co.x * 1.25, v.co.y - 0.02,
                                mz + (v.co.z - mz) * 2.6 - 0.015))
corner_k = mouth.shape_key_add(name="MouthCorner", from_mix=False)
mx_max = max(abs(vv.co.x) for vv in mouth.data.vertices)
for i, v in enumerate(mouth.data.vertices):
    ratio = abs(v.co.x) / mx_max
    corner_k.data[i].co = Vector((v.co.x * 1.45, v.co.y, v.co.z + 0.045 * ratio))

# ---------------- 骨架 ----------------
arm_data = bpy.data.armatures.new("Cat_Armature")
arm = bpy.data.objects.new("Cat_Armature", arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm_data.edit_bones

def bone(name, head, tail, parent=None):
    b = eb.new(name)
    b.head, b.tail = Vector(head), Vector(tail)
    if parent:
        b.parent = parent
    return b

b_root = bone("Root", (0, 0, 0.0), (0, 0, 0.25))
b_spine = bone("Spine", (0, 0, 0.25), (0, 0, 1.15), b_root)
b_head = bone("Head", (0, 0, 1.15), (0, 0, 2.55), b_spine)
b_mouth = bone("Mouth", (0, surf_y(0, 1.44), 1.44), (0, surf_y(0, 1.44) - 0.35, 1.44), b_head)
bone("Eye_L", (EYE_X * -1, surf_y(-EYE_X, EYE_Z), EYE_Z),
     (EYE_X * -1, surf_y(-EYE_X, EYE_Z) - 0.35, EYE_Z), b_head)
bone("Eye_R", (EYE_X, surf_y(EYE_X, EYE_Z), EYE_Z),
     (EYE_X, surf_y(EYE_X, EYE_Z) - 0.35, EYE_Z), b_head)
bone("Ear_L", (-0.60, 0, 2.30), (-0.75, 0, 2.95), b_head)
bone("Ear_R", (0.60, 0, 2.30), (0.75, 0, 2.95), b_head)
bone("Tail1", (0.55, 0.55, 0.55), (0.80, 0.80, 0.85), b_spine)
bone("Tail2", (0.80, 0.80, 0.85), (0.90, 0.95, 1.15), eb["Tail1"])
bone("Tail3", (0.90, 0.95, 1.15), (0.92, 1.02, 1.45), eb["Tail2"])
bpy.ops.object.mode_set(mode='OBJECT')

# ---------------- 刚性蒙皮绑定 ----------------
BIND = {
    "head": "Head", "muzzle": "Head", "nose": "Head", "mouth": "Mouth", "tongue": "Mouth",
    "mouth_corner_L": "Mouth", "mouth_corner_R": "Mouth",
    "ear_L": "Ear_L", "ear_R": "Ear_R", "ear_in_L": "Ear_L", "ear_in_R": "Ear_R",
    "eye_L": "Eye_L", "eye_R": "Eye_R", "iris_L": "Eye_L", "iris_R": "Eye_R",
    "pupil_L": "Eye_L", "pupil_R": "Eye_R",
    "glint_L": "Eye_L", "glint_R": "Eye_R",
    "body": "Spine", "paw_L": "Spine", "paw_R": "Spine",
    "paw_toe_L": "Spine", "paw_toe_R": "Spine", "collar": "Spine",
    "bell": "Spine", "bow_L": "Spine", "bow_R": "Spine", "bow_c": "Spine",
    "tail1": "Tail1", "tail2": "Tail2", "tail3": "Tail3",
}
for key, obj in parts.items():
    if key.startswith("whisker"):
        bone_name = "Head"
    else:
        bone_name = BIND.get(key, "Head")
    vg = obj.vertex_groups.new(name=bone_name)
    vg.add(range(len(obj.data.vertices)), 1.0, 'REPLACE')
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    obj.parent = arm

# ---------------- UV 展开 ----------------
for obj in parts.values():
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)

# ---------------- 灯光 / 相机 ----------------
for o in [x for x in bpy.data.objects if x.type == 'LIGHT']:
    bpy.data.objects.remove(o, do_unlink=True)

def area(name, loc, energy, size=4.0, rot=(math.radians(55), 0, 0)):
    d = bpy.data.lights.new(name, 'AREA'); d.energy = energy; d.size = size
    o = bpy.data.objects.new(name, d); bpy.context.scene.collection.objects.link(o)
    o.location, o.rotation_euler = loc, rot
    return o

area("Key", (3.2, -4.5, 4.2), 320)
area("Fill", (-4.2, -3.6, 2.2), 130, 5.0, (math.radians(75), 0, math.radians(-35)))
area("Rim", (0, 4.0, 3.6), 160, 4.0, (math.radians(120), 0, math.radians(180)))

scn = bpy.context.scene
if scn.world is None:
    scn.world = bpy.data.worlds.new("World")
scn.view_settings.view_transform = "Standard"
scn.world.use_nodes = True
_bg = next((n for n in scn.world.node_tree.nodes if n.type == 'BACKGROUND'), None)
if _bg:
    _bg.inputs[1].default_value = 0.18
    _bg.inputs[0].default_value = (0.55, 0.58, 0.62, 1)

cam_d = bpy.data.cameras.new("Camera_Portrait"); cam_d.lens = 65
cam = bpy.data.objects.new("Camera_Portrait", cam_d)
scn.collection.objects.link(cam)
cam.location = (0, -6.6, 1.90)
cam.rotation_euler = (math.radians(90), 0, 0)
scn.camera = cam

# ---------------- 渲染 + 导出 ----------------
scn.render.engine = 'BLENDER_EEVEE'
scn.render.resolution_x = 800
scn.render.resolution_y = 800
scn.render.filepath = os.path.join(WS, "cat_build.png")
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WS, "cat.blend").replace("\\", "/"))
bpy.ops.export_scene.fbx(filepath=os.path.join(WS, "cat.fbx").replace("\\", "/"), use_selection=False)
bpy.ops.export_scene.gltf(filepath=os.path.join(WS, "cat.glb").replace("\\", "/"), export_format='GLB')

print("BUILD_OK parts=%d bones=%d" % (len(parts), len(arm_data.bones)))
'''
