"""把参考图投影成顶点色（快速上色，非正式纹理烘焙）。

用法: blender -b -P colorize_glb.py -- <in.glb> <cutout.png> <out_prefix>
产出: <out_prefix>_front/side/q45.png, <out_prefix>_colored.glb, <out_prefix>.blend
"""
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB, CUTOUT, PREFIX = argv[0], argv[1], argv[2]

# ---- 导入 ----
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=GLB)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
obj = meshes[0]
me = obj.data
print(f"IMPORTED faces={len(me.polygons)} verts={len(me.vertices)}")

# ---- 清理重建伪影：删掉细长/极小的孤立碎块（胡须针、悬浮毛球） ----
import bmesh

bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
seen: set[int] = set()
islands: list[list] = []
for f in bm.faces:
    if f.index in seen:
        continue
    stack, comp = [f], []
    seen.add(f.index)
    while stack:
        cur = stack.pop()
        comp.append(cur)
        for e in cur.edges:
            for nf in e.link_faces:
                if nf.index not in seen:
                    seen.add(nf.index)
                    stack.append(nf)
    islands.append(comp)
islands.sort(key=len, reverse=True)
total_f = len(bm.faces)
to_del = []
for comp in islands[1:]:  # 保留最大主体
    if len(comp) >= total_f * 0.003:
        continue
    pts = np.array([[v.co.x, v.co.y, v.co.z] for f in comp for v in f.verts])
    ext = pts.max(axis=0) - pts.min(axis=0)
    if ext.min() < 0.035:  # 细长 = 胡须针
        to_del.extend(comp)
if to_del:
    bmesh.ops.delete(bm, geom=to_del, context="FACES")
bm.to_mesh(me)
bm.free()
me.update()
print(f"CLEANED islands={len(islands)} removed_faces={len(to_del)} faces_now={len(me.polygons)}")

# ---- 顶点世界坐标 ----
n = len(me.vertices)
co = np.empty(n * 3, dtype=np.float64)
me.vertices.foreach_get("co", co)
co = co.reshape(n, 3)
mw = np.array([list(row) for row in obj.matrix_world.to_4x4()])
world = co @ mw[:3, :3].T + mw[:3, 3]
mn, mx = world.min(axis=0), world.max(axis=0)
print("BOUNDS", np.round(mn, 3), np.round(mx, 3))

# ---- 参考图（抠图后）：优先 .npy（Blender 内置 Python 无 PIL） ----
img = np.load(CUTOUT)
ih, iw = img.shape[:2]
alpha = img[..., 3]
ys, xs = np.where(alpha > 20)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
print(f"IMAGE bbox x[{x0},{x1}] y[{y0},{y1}]")

# ---- 投影：x->u, z->v；背面顶点镜像 u ----
span = np.maximum(mx - mn, 1e-9)
u = (world[:, 0] - mn[0]) / span[0]
v = (world[:, 2] - mn[2]) / span[2]
u = np.where(world[:, 1] > (mn[1] + mx[1]) / 2, 1.0 - u, u)
px = (x0 + np.clip(u, 0, 1) * (x1 - x0)).astype(np.int32).clip(0, iw - 1)
py = (y1 - np.clip(v, 0, 1) * (y1 - y0)).astype(np.int32).clip(0, ih - 1)

rgb = img[py, px, :3].astype(np.float32) / 255.0
a = (img[py, px, 3].astype(np.float32) / 255.0)[:, None]

# 落在透明区的顶点（轮廓噪声）用邻域近似：整体提亮到奶油色，避免黑边
fallback = np.array([0.92, 0.85, 0.78], dtype=np.float32)
rgb = rgb * a + fallback * (1 - a)

# sRGB -> 线性（Blender FLOAT_COLOR 是线性的）
lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)

# ---- 写顶点色 ----
attr = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
rgba = np.concatenate([lin, np.ones((n, 1), dtype=np.float32)], axis=1).astype(np.float32)
attr.data.foreach_set("color", rgba.ravel())
me.color_attributes.active_color = attr

# ---- 材质：顶点色 -> Base Color ----
mat = bpy.data.materials.new("VColor")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.55
attr_node = nt.nodes.new("ShaderNodeVertexColor")
attr_node.layer_name = "Col"
nt.links.new(attr_node.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.clear()
me.materials.append(mat)
me.update()

# ---- 导出带顶点色的 glb ----
out_glb = f"{PREFIX}_colored.glb"
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=True,
                          export_colors=True)
print("EXPORTED", out_glb)

# ---- 渲染三视图 ----
scn = bpy.context.scene
scn.render.engine = "BLENDER_EEVEE"
scn.render.resolution_x = 900
scn.render.resolution_y = 900
scn.view_settings.view_transform = "Standard"
scn.world = bpy.data.worlds.new("W")
scn.world.use_nodes = True
scn.world.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.05, 0.08, 1)
scn.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

center = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
size = float(span.max())
for i, (pos, energy) in enumerate([((2.5, -2.5, 3.0), 800), ((-3.0, -1.5, 1.5), 350),
                                  ((0.0, 3.0, 2.0), 300)]):
    ld = bpy.data.lights.new(f"L{i}", type="AREA")
    ld.energy = energy
    ld.size = 4
    lo = bpy.data.objects.new(f"L{i}", ld)
    lo.location = Vector(pos) * size / 2
    scn.collection.objects.link(lo)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 60
cam = bpy.data.objects.new("Cam", cam_data)
scn.collection.objects.link(cam)
scn.camera = cam

dist = size * 2.4
for name, off in {"front": (0, -dist, 0.05 * size), "side": (dist, 0, 0.05 * size),
                  "q45": (dist * 0.7, -dist * 0.7, 0.1 * size)}.items():
    cam.location = center + Vector(off)
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scn.render.filepath = f"{PREFIX}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)

bpy.ops.wm.save_as_mainfile(filepath=f"{PREFIX}.blend")
print("COLORIZE_OK")
