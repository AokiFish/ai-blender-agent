"""本地网格导入/上色脚本的静态校验（真实 Blender 在 scripts/verify_local_mesh.py 里跑）。"""
from blender_agent.builders.local_mesh import import_local_mesh_script


def test_script_compiles_and_clears_scene():
    code = import_local_mesh_script("D:/tmp/x.glb", None)
    compile(code, "<local_mesh>", "exec")
    assert "import_scene.gltf" in code
    assert "bpy.data.objects.remove" in code
    assert "CharacterMesh" in code
    assert "color_attributes" not in code


def test_script_with_colors_uses_npy():
    code = import_local_mesh_script("D:/tmp/x.glb", "D:/tmp/x.npy")
    compile(code, "<local_mesh>", "exec")
    assert "np.load" in code
    assert "ShaderNodeVertexColor" in code
    assert "LOCAL_MESH_COLORED" in code


def test_script_joins_multiple_meshes():
    code = import_local_mesh_script("D:/tmp/x.glb", None)
    assert "bpy.ops.object.join()" in code
