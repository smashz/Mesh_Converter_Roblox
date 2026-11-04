"""
Blender (headless) converter: FBX / OBJ / glTF -> JSON mesh + texture data. tools/push_assets.js turns
it into ModuleScripts that ReplicatedStorage.MBE.ImportedMesh builds at runtime with EditableMesh /
EditableImage.
Nothing is uploaded to Roblox: the data lives inside the place, for private playtests only.

Usage (from the project folder):
  blender -b --factory-startup --python tools/converter/convert_model.py -- \
      <input.fbx> <output.json> [--name Pipkit] [--height 5] [--tex 512] [--pose idle|rest]

What it does:
  1. Imports the file into an empty scene. Animated rigs are frozen on the first frame of the clip the
     importer assigned (Pokemon GO rigs: the "wait" idle); unanimated rigs use their rest pose, and
     `--pose rest` forces the rest pose (GO bind poses are stretched, so idle is the default).
  2. Triangulates every visible mesh, bakes world transforms, converts Blender's Z-up axes to Roblox
     Y-up (the model's front, Blender -Y, becomes Roblox -Z, the LookVector), and scales the model so
     it is `--height` studs tall with its feet at y = 0 and centered on x/z.
  3. Groups triangles by the image texture of their material and splits vertices by position/normal/UV.
  4. Eyes: GO rigs draw eyes from a mostly transparent eye atlas that a custom shader blends over the
     body, either through a separate Eye/Face material or through body triangles whose UVs sit in the
     second tile (V > 1) with the atlas in a sibling *Eye*.png. Roblox does not blend those transparent
     texels, so bake_eyes() composites every eye texel over the body colour right behind it into one
     opaque texture per atlas (cropped to the cells the model uses).
  5. Downscales each texture to at most `--tex` pixels, packs them all into one atlas (max 1024 px) and
     merges every triangle into one mesh, because a Roblox client can hold only 8 EditableMeshes at a
     time. Pixels are raw RGBA8, top row first.
  6. Writes JSON whose binary buffers are base64 strings (little-endian f32 positions/normals/UVs,
     u32 triangle indices, RGBA8 pixels).
"""

import base64
import json
import os
import struct
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

MAX_VERTS = 60000   # Roblox EditableMesh vertex limit
MAX_TRIS = 20000    # Roblox EditableMesh triangle limit
MAX_TEX = 1024      # Roblox EditableImage size limit


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 2:
        raise SystemExit("usage: ... -- <input> <output.json> [--name N] [--height H] [--tex T]")
    opts = {"input": os.path.abspath(argv[0]), "output": os.path.abspath(argv[1]),
            "name": None, "height": 5.0, "tex": 512, "pose": "idle"}
    i = 2
    while i < len(argv):
        key = argv[i].lstrip("-")
        if key not in ("name", "height", "tex", "pose"):
            raise SystemExit("unknown option " + argv[i])
        opts[key] = argv[i + 1]
        i += 2
    opts["height"] = float(opts["height"])
    opts["tex"] = min(int(opts["tex"]), MAX_TEX)
    opts["name"] = opts["name"] or os.path.splitext(os.path.basename(opts["input"]))[0]
    return opts


def import_file(path, pose):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise SystemExit("unsupported format " + ext)
    start = None
    for obj in bpy.data.objects:
        ad = obj.animation_data
        if pose != "rest" and ad and ad.action:
            start = int(ad.action.frame_range[0]) if start is None else min(start, int(ad.action.frame_range[0]))
    if start is None:
        for arm in bpy.data.armatures:
            arm.pose_position = "REST"
    else:
        bpy.context.scene.frame_set(start)
    bpy.context.view_layer.update()
    return "rest" if start is None else "idle"


def material_image(mat):
    """First image texture feeding the material (prefers one linked to Base Color)."""
    if not (mat and mat.node_tree):
        return None
    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.type == "BSDF_PRINCIPLED":
            link = node.inputs["Base Color"].links
            if link and link[0].from_node.type == "TEX_IMAGE" and link[0].from_node.image:
                return link[0].from_node.image
    for node in nodes:
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
    return None


def material_color(mat):
    if mat:
        for node in (mat.node_tree.nodes if mat.node_tree else []):
            if node.type == "BSDF_PRINCIPLED":
                return tuple(node.inputs["Base Color"].default_value)[:3]
        return tuple(mat.diffuse_color)[:3]
    return (0.8, 0.8, 0.8)


def to_roblox(v):
    # Blender (x, y, z) Z-up, front -Y  ->  Roblox (X, Y, Z) Y-up, front -Z  (a proper rotation)
    return (-v[0], v[2], v[1])


def is_eye_image(img):
    return img is not None and any(k in img.name.lower() for k in ("eye", "face"))


def sibling_eye_image(path):
    """Eye atlas next to the source file that no material references (pm0001/0002/0003 style)."""
    folder = os.path.dirname(path)
    for f in sorted(os.listdir(folder)):
        low = f.lower()
        if low.endswith(".png") and ("eye" in low or "face" in low):
            return bpy.data.images.load(os.path.join(folder, f), check_existing=True)
    return None


def collect_triangles(src_path):
    """Returns (groups, eye_tris).
    groups: {key: {"image", "color", "tris": [(pos, nrm, uv) * 3] Roblox space, "raw": Blender space}}.
    eye_tris: [{"image", "pos": [Vector] * 3 Blender space, "uv": eye atlas UVs (v up), "tri": Roblox corners}].
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    groups, eye_tris = {}, []
    sibling = None
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.hide_render or obj.hide_get():
            continue
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        bm.free()
        mesh.calc_loop_triangles() if hasattr(mesh, "calc_loop_triangles") else None
        mw = ev.matrix_world
        nmat = mw.to_3x3().inverted_safe().transposed()
        uv_layer = mesh.uv_layers.active
        corner_normals = mesh.corner_normals if hasattr(mesh, "corner_normals") else None
        for tri in mesh.loop_triangles:
            mat = obj.material_slots[tri.material_index].material if obj.material_slots else None
            img = material_image(mat)
            raw = []
            for li in tri.loops:
                vi = mesh.loops[li].vertex_index
                p = mw @ mesh.vertices[vi].co
                n = corner_normals[li].vector if corner_normals is not None else mesh.loops[li].normal
                n = (nmat @ Vector(n)).normalized()
                uv = tuple(uv_layer.data[li].uv) if uv_layer else (0.0, 0.0)
                raw.append((p.copy(), n, uv))
            eye_img = None
            if is_eye_image(img):
                eye_img = img
            elif all(c[2][1] > 1.0 for c in raw):
                # Body triangle sampling the second UV tile: its eye atlas is a sibling file.
                if sibling is None:
                    sibling = sibling_eye_image(src_path) or False
                if sibling:
                    eye_img = sibling
                    raw = [(p, n, (uv[0], uv[1] - 1.0)) for p, n, uv in raw]
            corners = [(to_roblox(p), to_roblox(n), (uv[0], 1.0 - uv[1])) for p, n, uv in raw]
            if eye_img is not None:
                eye_tris.append({"image": eye_img, "pos": [c[0] for c in raw], "uv": [c[2] for c in raw],
                                 "tri": corners})
                continue
            key = img.name if img else ("color:" + (mat.name if mat else "none"))
            g = groups.setdefault(key, {"image": img, "color": material_color(mat), "tris": [], "raw": []})
            g["tris"].append(corners)
            g["raw"].append(raw)
        ev.to_mesh_clear()
    return groups, eye_tris


def image_array(img):
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)  # bottom row first, matching Blender UVs


def sample(arr, u, v):
    h, w = arr.shape[:2]
    return arr[min(h - 1, max(0, int((v % 1.0) * h))), min(w - 1, max(0, int((u % 1.0) * w)))]


def bake_eyes(groups, eye_tris, max_size):
    """Composites each eye atlas over the body colour right behind it into one opaque texture.
    Each texel covered by an eye triangle is mapped back to 3D, the nearest body surface point is found,
    and that point's body texel is the background. Texels no eye triangle uses are never displayed; they
    get the average background so bilinear filtering at triangle edges does not bleed a foreign colour."""
    body, arrays = [], {}
    for g in groups.values():
        if g["image"] is None:
            continue
        if g["image"].name not in arrays:
            arrays[g["image"].name] = image_array(g["image"])
        body.extend((raw, g["image"].name) for raw in g["raw"])
    if not body or not eye_tris:
        return {}
    verts = [c[0] for raw, _ in body for c in raw]
    bvh = BVHTree.FromPolygons(verts, [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(body))])

    by_image = {}
    for t in eye_tris:
        by_image.setdefault(t["image"].name, (t["image"], []))[1].append(t)
    out = {}
    for name, (img, tris) in by_image.items():
        eye = image_array(img)
        h, w = eye.shape[:2]
        scale = min(1.0, max_size / max(w, h))
        tw, th = max(1, int(w * scale)), max(1, int(h * scale))
        result = np.zeros((th, tw, 4), dtype=np.float32)
        covered = np.zeros((th, tw), dtype=bool)
        bg_sum, bg_n = np.zeros(3), 0
        for t in tris:
            a, b, c = [Vector((u * tw, v * th, 0.0)) for u, v in t["uv"]]
            area = (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)
            if abs(area) < 1e-9:
                continue
            x0, x1 = max(0, int(min(a.x, b.x, c.x)) - 1), min(tw - 1, int(max(a.x, b.x, c.x)) + 1)
            y0, y1 = max(0, int(min(a.y, b.y, c.y)) - 1), min(th - 1, int(max(a.y, b.y, c.y)) + 1)
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    q = Vector((x + 0.5, y + 0.5, 0.0))
                    l1 = ((b.x - q.x) * (c.y - q.y) - (c.x - q.x) * (b.y - q.y)) / area
                    l2 = ((c.x - q.x) * (a.y - q.y) - (a.x - q.x) * (c.y - q.y)) / area
                    inside = min(l1, l2, 1.0 - l1 - l2) >= -0.02
                    if covered[y, x] and not inside:
                        continue  # edge padding never overwrites a texel another triangle owns
                    p3 = barycentric_transform(q, a, b, c, *t["pos"])
                    loc, _n, fi, _d = bvh.find_nearest(p3)
                    if fi is None:
                        bg = np.array([0.5, 0.5, 0.5])
                    else:
                        raw, img_name = body[fi]
                        buv = barycentric_transform(loc, raw[0][0], raw[1][0], raw[2][0],
                                                    *[Vector((cr[2][0], cr[2][1], 0.0)) for cr in raw])
                        bg = sample(arrays[img_name], buv.x, buv.y)[:3]
                    src = sample(eye, (x + 0.5) / tw, (y + 0.5) / th)
                    al = float(src[3])
                    result[y, x, :3] = src[:3] * al + bg * (1.0 - al)
                    result[y, x, 3] = 1.0
                    if inside:
                        covered[y, x] = True
                        bg_sum += bg
                        bg_n += 1
        if bg_n:
            result[result[..., 3] == 0, :3] = bg_sum / bg_n
        result[..., 3] = 1.0
        # Keep only the atlas cells the model uses (the other expressions are never shown): Roblox caps
        # EditableImage/EditableMesh memory per client, and a full atlas costs as much as a body texture.
        ys, xs = np.nonzero(covered)
        if len(xs) == 0:
            continue
        x0, x1 = max(0, xs.min() - 2), min(tw, xs.max() + 3)
        y0, y1 = max(0, ys.min() - 2), min(th, ys.max() + 3)
        crop = np.ascontiguousarray(result[y0:y1, x0:x1])
        cw, ch = x1 - x0, y1 - y0
        remapped = [[(p, n, ((uv[0] * tw - x0) / cw, 1.0 - ((1.0 - uv[1]) * th - y0) / ch)) for p, n, uv in tri]
                    for tri in (t["tri"] for t in tris)]
        out[name] = {"array": crop, "tris": remapped, "covered": int(covered.sum())}
    return out


def normalize(groups, height):
    pts = [c[0] for g in groups.values() for t in g["tris"] for c in t]
    if not pts:
        raise SystemExit("no visible mesh triangles found")
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    size_y = hi[1] - lo[1] or 1.0
    s = height / size_y
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    for g in groups.values():
        g["tris"] = [[(((p[0] - cx) * s, (p[1] - lo[1]) * s, (p[2] - cz) * s), n, uv) for p, n, uv in t]
                     for t in g["tris"]]
    return [(hi[0] - lo[0]) * s, height, (hi[2] - lo[2]) * s]


def build_buffers(tris):
    index_of, pos, nrm, uvs, idx = {}, [], [], [], []
    for t in tris:
        for p, n, uv in t:
            key = (round(p[0], 5), round(p[1], 5), round(p[2], 5), round(n[0], 3), round(n[1], 3),
                   round(n[2], 3), round(uv[0], 5), round(uv[1], 5))
            i = index_of.get(key)
            if i is None:
                i = len(pos) // 3
                index_of[key] = i
                pos.extend(p)
                nrm.extend(n)
                uvs.extend(uv)
            idx.append(i)
    return pos, nrm, uvs, idx


def b64(fmt, values):
    return base64.b64encode(struct.pack("<%d%s" % (len(values), fmt), *values)).decode("ascii")


def group_pixels(g, max_size):
    """The group's texture as top-down uint8 RGBA (H, W, 4), or a small solid tile for colour-only groups."""
    if g.get("baked") is not None:
        arr = g["baked"]
    elif g["image"] is not None and g["image"].size[0] and g["image"].size[1]:
        img = g["image"]
        w, h = img.size
        scale = min(1.0, max_size / max(w, h))
        copy = img.copy()
        if scale < 1.0:
            copy.scale(max(1, int(w * scale)), max(1, int(h * scale)))
        arr = image_array(copy)
        bpy.data.images.remove(copy)
    else:
        arr = np.ones((4, 4, 4), dtype=np.float32)
        arr[..., :3] = g["color"]
    return np.clip(arr[::-1] * 255.0 + 0.5, 0, 255).astype(np.uint8)


ATLAS_PAD = 2


def pack_atlas(tiles):
    """Shelf-packs top-down RGBA tiles (each padded with copies of its edge texels, so bilinear filtering
    never mixes neighbours) into one image of at most MAX_TEX x MAX_TEX, shrinking everything if needed.
    Returns (atlas, [(x, y, w, h) inner rect per tile])."""
    scale = 1.0
    while True:
        sized = []
        for t in tiles:
            h, w = t.shape[:2]
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            if (nw, nh) != (w, h):
                ys = (np.arange(nh) * h // nh).clip(0, h - 1)
                xs = (np.arange(nw) * w // nw).clip(0, w - 1)
                t = t[ys][:, xs]
            sized.append(np.pad(t, ((ATLAS_PAD, ATLAS_PAD), (ATLAS_PAD, ATLAS_PAD), (0, 0)), mode="edge"))
        width = min(MAX_TEX, max(max(t.shape[1] for t in sized), sum(t.shape[1] for t in sized)))
        order = sorted(range(len(sized)), key=lambda i: -sized[i].shape[0])
        places, x, y, row_h = [None] * len(sized), 0, 0, 0
        for i in order:
            th, tw = sized[i].shape[:2]
            if x + tw > width:
                x, y, row_h = 0, y + row_h, 0
            places[i] = (x, y)
            x, row_h = x + tw, max(row_h, th)
        height = y + row_h
        if width <= MAX_TEX and height <= MAX_TEX:
            break
        scale *= 0.85
    atlas = np.zeros((height, width, 4), dtype=np.uint8)
    rects = []
    for t, (px, py) in zip(sized, places):
        th, tw = t.shape[:2]
        atlas[py:py + th, px:px + tw] = t
        rects.append((px + ATLAS_PAD, py + ATLAS_PAD, tw - 2 * ATLAS_PAD, th - 2 * ATLAS_PAD))
    return atlas, rects


def main():
    o = parse_args()
    pose = import_file(o["input"], o["pose"])
    groups, eye_tris = collect_triangles(o["input"])
    eyes = bake_eyes(groups, eye_tris, o["tex"])
    for name, e in eyes.items():
        groups["EyeBaked_" + os.path.splitext(name)[0]] = {
            "image": None, "baked": e["array"], "color": (1, 1, 1), "tris": e["tris"]}
    size = normalize(groups, o["height"])
    # One mesh + one texture per model: a Roblox client holds at most 8 EditableMeshes at a time
    # (measured in a Studio playtest), so every texture group goes into a shared atlas and all
    # triangles into one submesh (split only past the EditableMesh triangle limit).
    keys = sorted(groups)
    atlas, rects = pack_atlas([group_pixels(groups[k], o["tex"]) for k in keys])
    ah, aw = atlas.shape[:2]
    merged = []
    for k, (rx, ry, rw, rh) in zip(keys, rects):
        for t in groups[k]["tris"]:
            merged.append([(p, n, ((rx + min(1.0, max(0.0, uv[0])) * rw) / aw,
                                   (ry + min(1.0, max(0.0, uv[1])) * rh) / ah)) for p, n, uv in t])
    texture = {"Width": aw, "Height": ah, "Pixels": base64.b64encode(atlas.tobytes()).decode("ascii")}
    out = {"Version": 1, "Name": o["name"], "Source": os.path.basename(o["input"]), "Size": size, "Submeshes": []}
    total_v = total_t = 0
    for start in range(0, len(merged), MAX_TRIS):
        pos, nrm, uvs, idx = build_buffers(merged[start:start + MAX_TRIS])
        if len(pos) // 3 > MAX_VERTS:
            raise SystemExit("mesh has too many vertices")
        out["Submeshes"].append({
            "Name": "Part%d_Merged" % (len(out["Submeshes"]) + 1),
            "VertexCount": len(pos) // 3, "TriangleCount": len(idx) // 3,
            "Positions": b64("f", pos), "Normals": b64("f", nrm), "UVs": b64("f", uvs), "Indices": b64("I", idx),
            "Color": [1, 1, 1], "Texture": texture})
        total_v += len(pos) // 3
        total_t += len(idx) // 3
    os.makedirs(os.path.dirname(o["output"]), exist_ok=True)
    with open(o["output"], "w", encoding="ascii") as f:
        json.dump(out, f)
    report = {"name": o["name"], "output": o["output"], "pose": pose, "size": [round(v, 3) for v in size],
              "submeshes": len(out["Submeshes"]), "vertices": total_v, "triangles": total_t,
              "eye_triangles": len(eye_tris), "eye_texels": sum(e["covered"] for e in eyes.values()),
              "atlas": [aw, ah], "groups": keys, "bytes": os.path.getsize(o["output"])}
    print("MBE_CONVERT " + json.dumps(report))


main()
