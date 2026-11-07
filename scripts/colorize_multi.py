"""多向投影上色 + 细长伪影清理。

与 colorize_glb.py 的区别：
1) 不再把正面图镜像铺到背面（那是侧面"拉色带"的根因），改为正面/背面两张图按法线混合；
2) 删除"投影落在参考图透明区且自身很薄"的面 —— 这些是重建出的胡须针，参考图里根本没有几何。

用法: blender -b -P colorize_multi.py -- <in.glb> <front.npy> <back.npy|-> <out_prefix>
"""
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB, FRONT_NPY, BACK_NPY, PREFIX = argv[0], argv[1], argv[2], argv[3]

THIN_MAX = 0.018      # 局部厚度阈值（模型高 2.0 归一化后，约等于 1% 高度）
ALPHA_VISIBLE = 40    # 抠图 alpha 低于此值视为"参考图里没有东西"

# ---------------- 导入 ----------------
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=GLB)
obj = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
me = obj.data
print(f"IMPORTED faces={len(me.polygons)} verts={len(me.vertices)}")

# glTF 里带着 Hunyuan 导出的自定义法线，会在身上压出一块块平面色块。
# 清掉自定义法线并统一平滑着色，曲面的明暗才会连续。
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
try:
    if me.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        print("CLEARED custom normals")
except Exception as exc:  # noqa: BLE001
    print("custom normal clear failed:", type(exc).__name__)
bpy.ops.object.shade_smooth()

# ---------------- 基础数据 ----------------
nv = len(me.vertices)
co = np.empty(nv * 3, dtype=np.float64)
me.vertices.foreach_get("co", co)
co = co.reshape(nv, 3)
vn = np.empty(nv * 3, dtype=np.float64)
me.vertices.foreach_get("normal", vn)
vn = vn.reshape(nv, 3)
mw = np.array([list(r) for r in obj.matrix_world.to_4x4()])
rot = mw[:3, :3]
world = co @ rot.T + mw[:3, 3]
world_n = vn @ rot.T
span = np.maximum(world.max(axis=0) - world.min(axis=0), 1e-9)
mn, mx = world.min(axis=0), world.max(axis=0)
print("BOUNDS", np.round(mn, 3), np.round(mx, 3))


def load_view(path):
    img = np.load(path)
    ys, xs = np.where(img[..., 3] > ALPHA_VISIBLE)
    box = (xs.min(), xs.max(), ys.min(), ys.max())
    rgb, a = edge_extend(img)
    return (rgb, a), box


def edge_extend(img, iters: int = 28):
    """把轮廓外的透明像素填成最邻近的可见颜色。

    不做这一步，投影落在外侧一两个像素时会取到 (0,0,0,0)，
    在模型上表现为一条条黑裂缝。
    """
    rgb = img[..., :3].astype(np.float32).copy()
    a = img[..., 3].astype(np.float32)
    known = a > ALPHA_VISIBLE
    h, w = known.shape
    for _ in range(iters):
        if known.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros((h, w), dtype=np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ys = slice(max(dy, 0), h + min(dy, 0))
            xs = slice(max(dx, 0), w + min(dx, 0))
            ys2 = slice(max(-dy, 0), h + min(-dy, 0))
            xs2 = slice(max(-dx, 0), w + min(-dx, 0))
            k = known[ys, xs]
            acc[ys2, xs2] += rgb[ys, xs] * k[..., None]
            cnt[ys2, xs2] += k
        fill = (~known) & (cnt > 0)
        rgb[fill] = acc[fill] / cnt[fill][..., None]
        known = known | fill
    return rgb / 255.0, a / 255.0


INSET = 0.022  # 采样内缩：避开剪影上抗锯齿的亮边/黑边像素


def sample(view, box, u, v):
    """u,v in [0,1] over the visible bbox -> rgb[0..1] + alpha[0..1]."""
    rgb, a = view
    x0, x1, y0, y1 = box
    ih, iw = rgb.shape[:2]
    uu = INSET + (1 - 2 * INSET) * np.clip(u, 0, 1)
    vv = INSET + (1 - 2 * INSET) * np.clip(v, 0, 1)
    fx = np.clip(x0 + uu * (x1 - x0), 0, iw - 1.001)
    fy = np.clip(y1 - vv * (y1 - y0), 0, ih - 1.001)
    ix, iy = fx.astype(np.int32), fy.astype(np.int32)
    dx, dy = (fx - ix)[:, None], (fy - iy)[:, None]
    # 双线性：低频底色是块平均的，最近邻采样会露出方块台阶
    c00, c10 = rgb[iy, ix], rgb[iy, ix + 1]
    c01, c11 = rgb[iy + 1, ix], rgb[iy + 1, ix + 1]
    col = (c00 * (1 - dx) + c10 * dx) * (1 - dy) + (c01 * (1 - dx) + c11 * dx) * dy
    a00, a10 = a[iy, ix], a[iy, ix + 1]
    a01, a11 = a[iy + 1, ix], a[iy + 1, ix + 1]
    al = ((a00 * (1 - dx[:, 0]) + a10 * dx[:, 0]) * (1 - dy[:, 0])
          + (a01 * (1 - dx[:, 0]) + a11 * dx[:, 0]) * dy[:, 0])
    return col, al


front, fb = load_view(FRONT_NPY)
print("FRONT bbox", fb)
back = None
if BACK_NPY != "-":
    back, bb = load_view(BACK_NPY)
    print("BACK bbox", bb)


# ---------------- 1) 删胡须针：局部厚度远小于体高的面 ----------------
me.calc_loop_triangles()
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
bvh = BVHTree.FromBMesh(bm)

# 对每个面沿 -normal 打一条短线：命中距离 = 该处局部厚度。
# 胡须这种细管厚度只有体高的千分之几，实心部位（耳朵、蝴蝶结、脚掌）远大于阈值。
thin = []
for f in bm.faces:
    c = np.array(f.calc_center_median()) @ rot.T + mw[:3, 3]
    nrm = Vector(world_n[f.verts[0].index])
    if nrm.length < 0.5:
        continue
    nrm.normalize()
    hit = bvh.ray_cast(Vector(c) - nrm * 0.002, -nrm, THIN_MAX)
    if hit[0] is not None:
        thin.append(f)

if thin:
    bmesh.ops.delete(bm, geom=thin, context="FACES")
    loose_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    if loose_edges:
        bmesh.ops.holes_fill(bm, edges=loose_edges, sides=24)

# 删胡须后常留下几块碎片，扫一遍连通块，清掉主体之外的小碎屑
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
debris = []
for comp in islands[1:]:
    if len(comp) >= len(bm.faces) * 0.004:
        continue
    pts = np.array([[v.co.x, v.co.y, v.co.z] for f in comp for v in f.verts])
    if (pts.max(axis=0) - pts.min(axis=0)).max() < 0.06:
        debris.extend(comp)
if debris:
    bmesh.ops.delete(bm, geom=debris, context="FACES")

bm.to_mesh(me)
bm.free()
me.update()
me.calc_loop_triangles()
print(f"WHISKERS removed={len(thin)} debris_islands={len(debris)} faces_now={len(me.polygons)}")

# ---------------- 2) 多向混合投影 ----------------
nv = len(me.vertices)
co = np.empty(nv * 3, dtype=np.float64)
me.vertices.foreach_get("co", co)
co = co.reshape(nv, 3)
vn = np.empty(nv * 3, dtype=np.float64)
me.vertices.foreach_get("normal", vn)
vn = vn.reshape(nv, 3)
world = co @ rot.T + mw[:3, 3]
wn = vn @ rot.T
wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)

u = np.clip((world[:, 0] - mn[0]) / span[0], 0, 1)
v = np.clip((world[:, 2] - mn[2]) / span[2], 0, 1)

def box1(a, r: int, axis: int):
    """一维盒式模糊（累积和实现，可分离调用两次近似高斯）。"""
    padw = [(0, 0)] * a.ndim
    padw[axis] = (r, r)
    ap = np.pad(a, padw, mode="edge")
    c = np.cumsum(ap, axis=axis, dtype=np.float64)
    zshape = list(c.shape)
    zshape[axis] = 1
    c = np.concatenate([np.zeros(zshape, dtype=np.float64), c], axis=axis)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def blur_view(view, k: int):
    """块平均降采样再放大：只保留大色块（毛色、项圈），抹掉对不齐的细节。"""
    rgb, a = view
    h, w = rgb.shape[:2]
    hh, ww = (h // k) * k, (w // k) * k
    core = rgb[:hh, :ww].reshape(hh // k, k, ww // k, k, 3)
    ac = a[:hh, :ww].reshape(hh // k, k, ww // k, k, 1)
    wsum = ac.sum(axis=(1, 3))
    brgb = (core * ac).sum(axis=(1, 3)) / np.maximum(wsum, 1e-6)
    ba = wsum[..., 0] / (k * k)
    out_rgb = np.repeat(np.repeat(brgb, k, axis=0), k, axis=1)
    out_a = np.repeat(np.repeat(ba, k, axis=0), k, axis=1)
    # 放大后是块状常量，必须再做一次真正的模糊，
    # 否则采样到模型上就是一块块硬边色斑。
    r = max(2, k // 3)
    out_rgb = box1(box1(out_rgb, r, 0), r, 1)
    out_a = box1(box1(out_a[..., None], r, 0), r, 1)[..., 0]
    pad_rgb = np.pad(out_rgb, ((0, h - out_rgb.shape[0]), (0, w - out_rgb.shape[1]), (0, 0)),
                     mode="edge")
    pad_a = np.pad(out_a, ((0, h - out_a.shape[0]), (0, w - out_a.shape[1])), mode="edge")
    return pad_rgb, pad_a


# 正面细节 + 侧后低频色。
# 顶点投影的固有毛病是"细节在侧后面对不齐"，所以侧后只用低频部分做底色，
# 高频细节仅在法线朝前的区域启用；过渡由法线连续保证，不会出现硬缝。
f_rgb, f_a = sample(front, fb, u, v)
f_lo, f_lo_a = sample(blur_view(front, 128), fb, u, v)

if back is not None:
    b_lo, b_lo_a = sample(blur_view(back, 128), bb, 1.0 - u, v)
    y_mid = (mn[1] + mx[1]) / 2
    bias = np.tanh((world[:, 1] - y_mid) / (0.18 * span[1]))
    w_back = np.clip(0.5 * (1.0 + wn[:, 1]) + 0.45 * bias, 0.0, 1.0).reshape(-1, 1)
    base = f_lo * (1 - w_back) + b_lo * w_back
    base_a = (f_lo_a.reshape(-1) * (1 - w_back.reshape(-1))
              + b_lo_a.reshape(-1) * w_back.reshape(-1))
else:
    base, base_a = f_lo, f_lo_a

detail = (np.clip(-wn[:, 1], 0.0, 1.0) ** 1.4)[:, None]
rgb = f_rgb * detail + base * (1 - detail)
# 配准外的顶点退到低频底色，不填黑也不填平涂色
rgb = np.where((base_a < 0.05)[:, None], base, rgb)
rgb = np.clip(rgb, 0.0, 1.0)

lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
attr = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
rgba = np.concatenate([lin, np.ones((nv, 1), dtype=np.float32)], axis=1).astype(np.float32)
attr.data.foreach_set("color", rgba.ravel())
me.color_attributes.active_color = attr

mat = bpy.data.materials.new("VColor")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.6
vc = nt.nodes.new("ShaderNodeVertexColor")
vc.layer_name = "Col"
nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.clear()
me.materials.append(mat)
me.update()

# ---------------- 3) 加一层绒毛感（细微位移 + 高粗糙度即可） ----------------
out_glb = f"{PREFIX}_colored.glb"
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB", use_selection=True,
                          export_colors=True)
print("EXPORTED", out_glb)

# ---------------- 4) 渲染 ----------------
scn = bpy.context.scene
scn.render.engine = "BLENDER_EEVEE"
scn.render.resolution_x = 900
scn.render.resolution_y = 900
scn.view_settings.view_transform = "Standard"
scn.world = bpy.data.worlds.new("W")
scn.world.use_nodes = True
scn.world.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.05, 0.08, 1)

center = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
size = float(span.max())
for i, (pos, energy) in enumerate([((2.5, -2.5, 3.0), 900), ((-3.0, -1.5, 1.5), 400),
                                  ((0.0, 3.0, 2.0), 350)]):
    ld = bpy.data.lights.new(f"L{i}", type="AREA")
    ld.energy, ld.size = energy, 4
    ld.use_shadow = False  # 预览图：EEVEE 阴影贴图分辨率低，会在身上留下块状阴影
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
                  "q45": (dist * 0.7, -dist * 0.7, 0.1 * size),
                  "back": (0, dist, 0.05 * size)}.items():
    cam.location = center + Vector(off)
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scn.render.filepath = f"{PREFIX}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)

bpy.ops.wm.save_as_mainfile(filepath=f"{PREFIX}.blend")
print("COLORIZE_OK")
