"""把本地生成的 glb 接进 Blender：清场 -> 导入 -> 归一化尺寸 -> 可选顶点色投影。

只生成 bpy 代码字符串（由 mcp provider 执行），不在本进程 import bpy。
"""
from __future__ import annotations


def import_local_mesh_script(glb_path: str, npy_path: str | None = None,
                             target_height: float = 2.0) -> str:
    """返回 bpy 代码：导入 glb，缩放到 target_height 高、底面贴 z=0、水平居中。"""
    parts = [
        "import bpy, numpy as np",
        "# 清场：默认立方体/相机/灯全部移除，避免和生成网格叠在一起",
        "for o in list(bpy.data.objects):",
        "    bpy.data.objects.remove(o, do_unlink=True)",
        f"bpy.ops.import_scene.gltf(filepath={glb_path!r})",
        "meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']",
        "if not meshes:",
        "    raise RuntimeError('glb imported no mesh')",
        "for o in meshes:",
        "    o.select_set(True)",
        "bpy.context.view_layer.objects.active = meshes[0]",
        "if len(meshes) > 1:",
        "    bpy.ops.object.join()",
        "obj = bpy.context.view_layer.objects.active",
        "bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)",
        "# 归一化：高度 target、底面 z=0、xy 居中",
        "co = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)",
        "obj.data.vertices.foreach_get('co', co)",
        "co = co.reshape(-1, 3)",
        "mn, mx = co.min(axis=0), co.max(axis=0)",
        "span = np.maximum(mx - mn, 1e-9)",
        f"scale = {target_height} / span.max()",
        "obj.scale = (scale, scale, scale)",
        "bpy.ops.object.transform_apply(scale=True)",
        "co = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)",
        "obj.data.vertices.foreach_get('co', co)",
        "co = co.reshape(-1, 3)",
        "mn, mx = co.min(axis=0), co.max(axis=0)",
        "obj.location = (-(mn[0] + mx[0]) / 2, -(mn[1] + mx[1]) / 2, -mn[2])",
        "bpy.ops.object.transform_apply(location=True)",
        "obj.name = 'CharacterMesh'",
        "print('LOCAL_MESH_IMPORTED faces=%d verts=%d' % (len(obj.data.polygons), len(obj.data.vertices)))",
    ]

    if npy_path:
        parts += [
            f"img = np.load({npy_path!r})",
            "# 顶点色投影：x->u, z->v；后半部顶点镜像 u，避免背面全糊成一片",
            "n = len(obj.data.vertices)",
            "co = np.empty(n * 3, dtype=np.float64)",
            "obj.data.vertices.foreach_get('co', co)",
            "co = co.reshape(n, 3)",
            "mn, mx = co.min(axis=0), co.max(axis=0)",
            "span = np.maximum(mx - mn, 1e-9)",
            "ih, iw = img.shape[:2]",
            "alpha = img[..., 3]",
            "ys, xs = np.where(alpha > 20)",
            "x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()",
            "u = (co[:, 0] - mn[0]) / span[0]",
            "v = (co[:, 2] - mn[2]) / span[2]",
            "u = np.where(co[:, 1] > (mn[1] + mx[1]) / 2, 1.0 - u, u)",
            "px = (x0 + np.clip(u, 0, 1) * (x1 - x0)).astype(np.int32).clip(0, iw - 1)",
            "py = (y1 - np.clip(v, 0, 1) * (y1 - y0)).astype(np.int32).clip(0, ih - 1)",
            "rgb = img[py, px, :3].astype(np.float32) / 255.0",
            "a = (img[py, px, 3].astype(np.float32) / 255.0)[:, None]",
            "fallback = np.array([0.92, 0.85, 0.78], dtype=np.float32)",
            "rgb = rgb * a + fallback * (1 - a)",
            "lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)",
            "attr = obj.data.color_attributes.new(name='Col', type='FLOAT_COLOR', domain='POINT')",
            "rgba = np.concatenate([lin, np.ones((n, 1), dtype=np.float32)], axis=1).astype(np.float32)",
            "attr.data.foreach_set('color', rgba.ravel())",
            "obj.data.color_attributes.active_color = attr",
            "mat = bpy.data.materials.new('VColor')",
            "mat.use_nodes = True",
            "nt = mat.node_tree",
            "bsdf = nt.nodes['Principled BSDF']",
            "bsdf.inputs['Roughness'].default_value = 0.55",
            "vc = nt.nodes.new('ShaderNodeVertexColor')",
            "vc.layer_name = 'Col'",
            "nt.links.new(vc.outputs['Color'], bsdf.inputs['Base Color'])",
            "obj.data.materials.clear()",
            "obj.data.materials.append(mat)",
            "print('LOCAL_MESH_COLORED')",
        ]

    parts.append("print('LOCAL_MESH_OK')")
    return "\n".join(parts) + "\n"
