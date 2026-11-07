"""分析 glb 的连通块（loose parts）：找出细碎伪影（胡须针、悬浮小球）。"""
import sys

import bmesh
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = argv[0]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=GLB)
obj = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]

bm = bmesh.new()
bm.from_mesh(obj.data)
bm.verts.ensure_lookup_table()
bm.faces.ensure_lookup_table()

total = len(bm.faces)
# 连通块（面级）
seen = set()
islands = []
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

print(f"TOTAL faces={total} islands={len(islands)}")
islands.sort(key=len, reverse=True)
for i, comp in enumerate(islands[:12]):
    co = np.array([[v.co.x, v.co.y, v.co.z] for f in comp for v in f.verts])
    ext = co.max(axis=0) - co.min(axis=0)
    print(f"ISLAND {i} faces={len(comp)} ({len(comp)/total*100:.2f}%) extent={np.round(ext,3)}")
small = [c for c in islands[1:] if len(c) < total * 0.002]
print(f"SMALL_ISLANDS(<0.2%)={len(small)} faces_total={sum(len(c) for c in small)}")
bm.free()
