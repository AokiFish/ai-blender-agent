"""通用绑定器：把任意网格（参数化构建的、或 image-to-3D 导入的）变成口播骨架。

不依赖具体建模方式，全部由 bpy 代码确定性地完成：
1) 按包围盒推算出 脊柱/头/下颌/左右眼球 的位置，建 TalkingRig 骨架；
2) 自动权重绑定（ARMATURE_AUTO）；
3) 补 Blink / MouthOpen 两个形态键，按顶点与五官区域的距离做形变，
   这样即使导入的网格没有口型通道，也能直接做口播动画。

坐标系约定与 Blender 一致：-Y 为正面，Z 向上。
"""

SCRIPT = r"""
import bpy
from mathutils import Vector

TARGET = __TARGET__
RIG_NAME = "TalkingRig"

meshes = [o for o in bpy.data.objects if o.type == 'MESH']
if TARGET:
    hit = [o for o in meshes if o.name == TARGET or TARGET in o.name]
    if hit:
        meshes = hit

if not meshes:
    print("TALKING_RIG_FAIL no mesh in scene")
else:
    # 多部件角色（如参数化猫的 38 个部件）必须整体绑定，不能只绑最大的那个
    world = []
    for o in meshes:
        world += [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(v.x for v in world), min(v.y for v in world), min(v.z for v in world)))
    mx = Vector((max(v.x for v in world), max(v.y for v in world), max(v.z for v in world)))
    size = mx - mn
    ctr = (mn + mx) / 2.0
    H, W, D = size.z, size.x, size.y
    fy = mn.y

    # ---------- 骨架 ----------
    if RIG_NAME in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[RIG_NAME], do_unlink=True)
    arm = bpy.data.armatures.new(RIG_NAME)
    rig = bpy.data.objects.new(RIG_NAME, arm)
    bpy.context.collection.objects.link(rig)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')

    def mk(name, head, tail, parent=None):
        b = arm.edit_bones.new(name)
        b.head = Vector(head)
        b.tail = Vector(tail)
        if parent and parent in arm.edit_bones:
            b.parent = arm.edit_bones[parent]
        return b

    mk("Root", (ctr.x, ctr.y, mn.z), (ctr.x, ctr.y, mn.z + H * 0.35))
    mk("Spine", (ctr.x, ctr.y, mn.z + H * 0.35), (ctr.x, ctr.y, mn.z + H * 0.62), "Root")
    mk("Head", (ctr.x, ctr.y, mn.z + H * 0.62), (ctr.x, ctr.y, mx.z), "Spine")
    mk("Jaw", (ctr.x, fy + D * 0.35, mn.z + H * 0.60), (ctr.x, fy, mn.z + H * 0.54), "Head")
    for side, sx in (("L", -1), ("R", 1)):
        ex = ctr.x + sx * W * 0.18
        ename = "Eye_L" if sx < 0 else "Eye_R"
        mk(ename, (ex, fy + D * 0.22, mn.z + H * 0.80), (ex, fy, mn.z + H * 0.80), "Head")
    bpy.ops.object.mode_set(mode='OBJECT')

    # ---------- 自动权重（全部网格一起绑） ----------
    bound = 0
    for m in meshes:
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        try:
            bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            bound += 1
        except Exception as e:
            print("ARMATURE_AUTO_FAIL", m.name, e)
            m.parent = rig
            mod = m.modifiers.new("Armature", 'ARMATURE')
            mod.object = rig
    print("ARMATURE_AUTO bound=%d" % bound)

    # ---------- 形态键：挂在头部网格（上半部区域里面数最多的那个） ----------
    def _center_z(o):
        return (o.matrix_world @ Vector((
            sum(c[i] for c in o.bound_box) / 8.0 for i in range(3)))).z

    upper = [o for o in meshes if _center_z(o) > mn.z + H * 0.55] or meshes
    obj = max(upper, key=lambda o: len(o.data.vertices))
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    have = {k.name for k in obj.data.shape_keys.key_blocks}

    eye_z = mn.z + H * 0.80
    mouth_z = mn.z + H * 0.56

    def add_key(name, predicate, delta):
        if name in have:
            return False
        key = obj.shape_key_add(name=name, from_mix=False)
        for i, v in enumerate(obj.data.vertices):
            p = obj.matrix_world @ v.co
            if predicate(p):
                key.data[i].co = v.co + Vector(delta)
        return True

    add_key("Blink",
            lambda p: abs(p.z - eye_z) < H * 0.06 and p.y < ctr.y and abs(p.x - ctr.x) < W * 0.42,
            (0.0, 0.0, -H * 0.018))
    add_key("MouthOpen",
            lambda p: abs(p.z - mouth_z) < H * 0.05 and p.y < ctr.y and abs(p.x - ctr.x) < W * 0.14,
            (0.0, 0.0, -H * 0.030))

    keys = [k.name for k in obj.data.shape_keys.key_blocks]
    print("TALKING_RIG_OK bones=%d keys=%s target=%s" % (len(arm.bones), keys, obj.name))
"""


def rig_script(target: str = "") -> str:
    """生成绑定脚本；target 为空时自动挑顶点最多的网格。"""
    return SCRIPT.replace("__TARGET__", repr(target))
