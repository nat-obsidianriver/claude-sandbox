"""
Turn the photo-derived GLB of the kitten into a printable STL.

The generated mesh is a good likeness but not a solid: vertices are split along
texture seams, the underside has holes, and the whiskers are modelled as
sub-millimetre spikes. Printing needs a single closed manifold, so this
rebuilds the surface through a voxel pass:

    weld -> orient Z-up -> voxelise -> seal -> fill solid -> strip whiskers
         -> largest component -> smooth -> flat base -> marching cubes

The voxel round trip is what guarantees the result is manifold and
non-self-intersecting, which hole-filling a broken surface in place does not.
"""

import argparse

import numpy as np
import trimesh
from scipy import ndimage


def weld(path):
    """Load the GLB and merge vertices that texture seams left split apart."""
    scene = trimesh.load(path, process=False)
    geoms = scene.geometry.values() if isinstance(scene, trimesh.Scene) else [scene]
    m = trimesh.util.concatenate(list(geoms))

    v = np.asarray(m.vertices, dtype=np.float64)
    f = np.asarray(m.faces)
    tol = np.ptp(v, axis=0).max() * 1e-5
    _, inv = np.unique(np.round(v / tol).astype(np.int64), axis=0, return_inverse=True)

    verts = np.zeros((inv.max() + 1, 3))
    counts = np.zeros(inv.max() + 1)
    np.add.at(verts, inv, v)
    np.add.at(counts, inv, 1)
    verts /= counts[:, None]

    faces = inv[f]
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return trimesh.Trimesh(vertices=verts, faces=faces[ok], process=False)


def largest_blob(mask):
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def solidify(mesh, resolution, seal, despeckle, base_trim, smooth):
    """Voxelise the surface and rebuild it as a closed solid."""
    pitch = mesh.extents.max() / resolution
    vox = mesh.voxelized(pitch=pitch)
    occ = np.asarray(vox.matrix, dtype=bool)
    origin = vox.transform[:3, 3]
    print(f"  voxel grid      : {occ.shape}, pitch {pitch:.5f}")

    # Closing alone does not seal this surface: at a fine pitch the gaps reopen
    # and the flood fill escapes, leaving a shell instead of a solid. Dilate
    # first, fill, then erode by the same amount - the dilation bridges holes up
    # to about 2*seal voxels across, and the erosion restores the true surface.
    # The radius has to scale with resolution, since a finer pitch reopens gaps
    # that a coarse grid bridged for free.
    struct = ndimage.generate_binary_structure(3, 1)
    if seal:
        occ = ndimage.binary_dilation(occ, struct, iterations=seal)

    # The reconstruction is open underneath, where the kitten met the blanket.
    # Trim past the ragged edge and seal the exposed cross-section in 2D so the
    # fill cannot pour out of the bottom.
    zs = np.where(occ.any(axis=(0, 1)))[0]
    cut = zs.min() + max(int(round(base_trim / pitch)), 1)
    occ[:, :, :cut] = False
    occ[:, :, cut] = ndimage.binary_fill_holes(occ[:, :, cut])
    print(f"  base sealed at  : voxel layer {cut} ({cut - zs.min()} in from the bottom)")

    occ = ndimage.binary_fill_holes(occ)
    print(f"  filled          : {occ.sum():,} voxels")
    if seal:
        occ = ndimage.binary_erosion(occ, struct, iterations=seal)
    print(f"  solid           : {occ.sum():,} voxels")

    # Opening erodes then dilates, which deletes structures thinner than the
    # kernel - exactly the whiskers - while leaving the solid body untouched.
    if despeckle:
        occ = ndimage.binary_opening(
            occ, ndimage.generate_binary_structure(3, 1), iterations=despeckle
        )
        print(f"  after despeckle : {occ.sum():,} voxels")

    occ = largest_blob(occ)

    # Pad so the surface always closes, then smooth off the voxel stair-stepping.
    pad = 3
    field = np.pad(occ.astype(np.float32), pad)
    origin = origin - pad * pitch
    if smooth:
        field = ndimage.gaussian_filter(field, sigma=smooth)

    # Re-cut the base after smoothing so the bottom face is crisp rather than
    # rounded off by the blur. Sit it a couple of layers inside the sealed
    # cross-section, where the field is solidly 1.
    flat = cut + pad + 2
    field[:, :, :flat] = 0.0

    from skimage import measure

    verts, faces, _, _ = measure.marching_cubes(field, level=0.5, spacing=(pitch,) * 3)
    out = trimesh.Trimesh(vertices=verts + origin, faces=faces, process=True)
    out.remove_unreferenced_vertices()

    parts = out.split(only_watertight=False)
    if len(parts) > 1:
        out = max(parts, key=lambda p: len(p.faces))
    out.fix_normals()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("--out", default="kitten_scan.stl")
    ap.add_argument("--height", type=float, default=70.0,
                    help="longest horizontal dimension in mm")
    ap.add_argument("--resolution", type=int, default=320)
    ap.add_argument("--seal", type=int, default=3,
                    help="dilate/erode radius in voxels used to bridge holes before filling")
    ap.add_argument("--despeckle", type=int, default=1, help="opening iterations to strip whiskers")
    ap.add_argument("--base-trim", type=float, default=0.02,
                    help="slice this much off the bottom, in model units, for a flat base")
    ap.add_argument("--smooth", type=float, default=0.8)
    ap.add_argument("--max-faces", type=int, default=150000)
    args = ap.parse_args()

    mesh = weld(args.glb)
    print(f"welded            : {len(mesh.vertices):,} verts, {len(mesh.faces):,} faces")

    # glTF is Y-up; 3D printing is Z-up.
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))

    mesh = solidify(mesh, args.resolution, args.seal, args.despeckle, args.base_trim, args.smooth)

    if args.max_faces:
        for target in (args.max_faces, args.max_faces * 2, args.max_faces * 4):
            if len(mesh.faces) <= target:
                break
            reduced = mesh.simplify_quadric_decimation(face_count=target)
            if reduced.is_watertight and reduced.is_winding_consistent:
                reduced.fix_normals()
                mesh = reduced
                break
            print(f"  decimation to {target:,} broke the solid, backing off")

    mesh.apply_scale(args.height / max(mesh.extents[0], mesh.extents[1]))
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    mesh.export(args.out)

    ext = mesh.extents
    print(f"\nwrote {args.out}")
    print(f"  triangles : {len(mesh.faces):,}")
    print(f"  watertight: {mesh.is_watertight}")
    print(f"  winding   : {mesh.is_winding_consistent}")
    print(f"  euler     : {mesh.euler_number}")
    print(f"  volume    : {mesh.volume / 1000:.1f} cm^3")
    print(f"  bbox (mm) : {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f}")


if __name__ == "__main__":
    main()
