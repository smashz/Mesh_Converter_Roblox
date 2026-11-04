"""
Renders converted JSON (build/playtest_assets/<Id>.json) in headless Blender, using exactly the mesh and
texture data the game builds at runtime, so converter output can be checked without Studio.
Usage: blender -b --factory-startup --python tools/converter/preview_json.py -- <in.json> <out.png> [--face]
  --face          frames the eyes (the EyeBaked_* part, or --look) instead of the whole model.
  --look x,y,z    point to frame, in Roblox asset coordinates (lets an old build be framed like a new one).
"""
import base64, json, math, struct, sys
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst, face = argv[0], argv[1], "--face" in argv
look_arg = argv[argv.index("--look") + 1] if "--look" in argv else None
eye_pts = []
data = json.load(open(src))
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def floats(s):
    raw = base64.b64decode(s)
    return struct.unpack("<%df" % (len(raw) // 4), raw)


for sub in data["Submeshes"]:
    p, uv = floats(sub["Positions"]), floats(sub["UVs"])
    raw = base64.b64decode(sub["Indices"])
    idx = struct.unpack("<%dI" % (len(raw) // 4), raw)
    verts = [(-p[i], p[i + 2], p[i + 1]) for i in range(0, len(p), 3)]  # Roblox -> Blender axes
    if "EyeBaked" in sub["Name"]:
        eye_pts.extend(verts)
    faces = [tuple(idx[i:i + 3]) for i in range(0, len(idx), 3)]
    me = bpy.data.meshes.new(sub["Name"])
    me.from_pydata(verts, [], faces)
    layer = me.uv_layers.new()
    for loop in me.loops:
        v = loop.vertex_index
        layer.data[loop.index].uv = (uv[v * 2], 1.0 - uv[v * 2 + 1])
    obj = bpy.data.objects.new(sub["Name"], me)
    scene.collection.objects.link(obj)
    mat = bpy.data.materials.new(sub["Name"])
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    if "Texture" in sub:
        t = sub["Texture"]
        img = bpy.data.images.new(sub["Name"], t["Width"], t["Height"], alpha=True)
        px = np.frombuffer(base64.b64decode(t["Pixels"]), dtype=np.uint8).reshape(t["Height"], t["Width"], 4)
        img.pixels.foreach_set((px[::-1].astype(np.float32) / 255.0).ravel())
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])  # alpha ignored, as in Roblox
    else:
        bsdf.inputs["Base Color"].default_value = (*sub["Color"], 1)
    me.materials.append(mat)

w, h, d = data["Size"]
look = Vector((0, 0, h * 0.5))
if look_arg:
    X, Y, Z = map(float, look_arg.split(","))
    look = Vector((-X, Z, Y))
elif face and eye_pts:
    look = sum((Vector(v) for v in eye_pts), Vector()) / len(eye_pts)
print("MBE_LOOK %.4f,%.4f,%.4f" % (-look.x, look.z, look.y))
dist = (h * 0.75 if face else max(w, h) * 1.9)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
cam.location = look + Vector((dist * 0.3, -dist, dist * 0.1))  # front is Blender -Y
cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3
sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
scene.collection.objects.link(sun)
scene.world = bpy.data.worlds.new("w")
scene.world.color = (0.6, 0.75, 0.9)
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = 512
scene.render.filepath = dst
bpy.ops.render.render(write_still=True)
print("MBE_PREVIEW", dst)
