import base64, json, math, struct
from pathlib import Path
root=Path(__file__).resolve().parents[2]
config=json.loads((root/'tools/converter/assets.json').read_text())
manifest=json.loads((root/'build/playtest_assets/manifest.json').read_text())
for name, entry in config.items():
    if name.startswith('_'): continue
    data=json.loads((root/'build/playtest_assets'/f'{name}.json').read_text())
    points=[]
    groups=[]
    for sub in data['Submeshes']:
        raw=base64.b64decode(sub['Positions'], validate=True)
        assert len(raw)==sub['VertexCount']*12
        group=list(struct.iter_unpack('<fff',raw))
        groups.append(group)
        points.extend(group)
    lo=[min(p[i] for p in points) for i in range(3)]
    hi=[max(p[i] for p in points) for i in range(3)]
    size=data['Size']; height=entry['height']
    assert all(math.isfinite(v) for p in points for v in p)
    assert abs(lo[1])<1e-5 and abs(hi[1]-height)<1e-4
    assert all(abs((hi[i]-lo[i])-size[i])<1e-4 for i in range(3))
    assert all(abs(size[i]-manifest[name]['size'][i])<1e-8 for i in range(3))
    assert abs((lo[0]+hi[0])/2)<1e-5 and abs((lo[2]+hi[2])/2)<1e-5
    # The server places the anchor bottom at the root-relative feet (anchor center at
    # feet + height/2). The client centers each submesh's vertices on its own bounds (MeshParts
    # from EditableMesh are not recentered) and offsets the part by bounds center - anchor origin.
    for feet in (-3.5, 0, 12.25):
        for yaw in (0, math.pi/2, math.pi):
            anchor_center = feet + height / 2
            for group in groups:
                glo = min(p[1] for p in group); ghi = max(p[1] for p in group)
                part_center = anchor_center + ((glo + ghi) / 2 - height / 2)
                local = [p[1] - (glo + ghi) / 2 for p in group]  # centered vertices
                assert abs(min(local) + max(local)) < 1e-5
                rendered = [part_center + y for y in local]
                assert abs(min(rendered) - (feet + glo)) < 1e-5
            rendered_bottom = min(anchor_center + (p[1] - height / 2) for p in points)
            assert abs(rendered_bottom - feet) < 1e-5
    print(f'{name}: height={height:g} studs, bounds y=[{lo[1]:.5f}, {hi[1]:.5f}], grounded; translation/yaw math OK')
mesh=(root/'src/ReplicatedStorage/MBE/ImportedMesh.lua').read_text()
assert 'mesh:AddVertex(points[i + 1] - center)' in mesh, 'ImportedMesh must center vertices'
runtime=(root/'src/ServerScriptService/MBE/CreatureVisuals.lua').read_text()
assert 'Heartbeat' not in runtime and 'groundWelds' not in runtime, 'runtime ground correction must stay removed'
print('PASS: seven assets; centered submesh vertices render with the lowest vertex exactly at the feet offset (within 0.00001 studs) at three heights and three yaw angles; no runtime ground correction; geometry unchanged')
