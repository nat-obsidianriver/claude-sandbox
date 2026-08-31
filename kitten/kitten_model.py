"""
Parametric 3D model of a sitting kitten, built as a signed distance field (SDF)
and surfaced with marching cubes.

Working units are millimetres of the final print. The model is authored around a
nominal 80 mm tall figurine and is scaled to whatever --height asks for.

Everything is unioned with a polynomial smooth-min so the joins are organic
rather than faceted, and the solid is intersected with the z >= 0 half-space to
give a flat, raft-free base.
"""

import argparse

import numpy as np


# ---------------------------------------------------------------- SDF helpers

def smin(a, b, k):
    """Polynomial smooth minimum. k is the blend radius in model units."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def carve(d, tool, k):
    """Smoothly subtract `tool` from `d` - used for engraved detail."""
    return smax(d, -tool, k)


def sd_sphere(p, centre, r):
    return np.linalg.norm(p - np.asarray(centre), axis=-1) - r


def sd_ellipsoid(p, centre, radii):
    """Exact-ish ellipsoid bound (IQ's approximation); zero level set is correct."""
    r = np.asarray(radii, dtype=np.float64)
    q = p - np.asarray(centre)
    k0 = np.linalg.norm(q / r, axis=-1)
    k1 = np.linalg.norm(q / (r * r), axis=-1)
    return np.where(k0 == 0.0, -r.min(), k0 * (k0 - 1.0) / np.maximum(k1, 1e-9))


def sd_round_cone(p, a, b, r1, r2):
    """Capsule with different end radii - a tapered limb or ear."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ba = b - a
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2

    pa = p - a
    y = pa @ ba
    z = y - l2
    w = pa * l2 - np.outer(y, ba).reshape(pa.shape)
    x2 = np.einsum("...i,...i->...", w, w)
    y2 = y * y * l2
    z2 = z * z * l2

    k = np.sign(rr) * rr * rr * x2
    out = np.empty(x2.shape, dtype=np.float64)

    cap_b = (np.sign(z) * a2 * z2) > k
    cap_a = (~cap_b) & ((np.sign(y) * a2 * y2) < k)
    body = ~(cap_b | cap_a)

    out[cap_b] = np.sqrt(x2[cap_b] + z2[cap_b]) * il2 - r2
    out[cap_a] = np.sqrt(x2[cap_a] + y2[cap_a]) * il2 - r1
    out[body] = (np.sqrt(x2[body] * a2 * il2) + y[body] * rr) * il2 - r1
    return out


def sd_flat_round_cone(p, a, b, r1, r2, flatten):
    """Round cone evaluated in y-compressed space, giving a flattened ear.

    Endpoints are given in real space and mapped into the scaled space; the
    result is rescaled by the smallest axis factor so the zero level set - the
    only thing marching cubes reads - stays exactly where it should.
    """
    s = np.array([1.0, flatten, 1.0])
    a = np.asarray(a, dtype=np.float64) / s
    b = np.asarray(b, dtype=np.float64) / s
    return sd_round_cone(p / s, a, b, r1, r2) * s.min()


# ------------------------------------------------------------------ the kitten

def kitten_sdf(p):
    """Signed distance to the kitten, for an (N, 3) array of points."""
    # Haunches and rump - the mass the pose sits on.
    d = sd_ellipsoid(p, (0, -8.0, 22.0), (26.0, 30.0, 23.0))

    # Chest rising to the shoulders, tapering as it goes up.
    d = smin(d, sd_round_cone(p, (0, -2.0, 24.0), (0, 7.0, 57.0), 22.0, 15.5), 9.0)

    # Head: a touch wider than deep, as a kitten's is.
    head = sd_ellipsoid(p, (0, 10.0, 74.0), (20.0, 19.5, 18.5))
    d = smin(d, head, 5.5)

    # Cheeks / ruff.
    for sx in (-1.0, 1.0):
        d = smin(d, sd_sphere(p, (sx * 9.5, 12.0, 68.0), 9.5), 5.0)

    # Muzzle and nose, sitting proud of the head's front surface.
    d = smin(d, sd_ellipsoid(p, (0, 24.5, 67.0), (10.0, 8.5, 7.0)), 4.0)
    d = smin(d, sd_sphere(p, (0, 31.0, 69.5), 2.8), 1.8)

    # Chin.
    d = smin(d, sd_ellipsoid(p, (0, 24.0, 61.0), (6.5, 6.0, 4.5)), 4.0)

    # Eyes: domes standing ~2 mm off the face, each with a pupil dimple so the
    # feature survives at print scale instead of sanding away to a bump.
    for sx in (-1.0, 1.0):
        d = smin(d, sd_sphere(p, (sx * 8.2, 24.5, 75.0), 5.4), 2.2)
    for sx in (-1.0, 1.0):
        d = carve(d, sd_sphere(p, (sx * 8.2, 30.6, 75.6), 2.3), 1.0)

    # Brow crease above each eye, to keep the muzzle and forehead distinct.
    for sx in (-1.0, 1.0):
        d = carve(d, sd_ellipsoid(p, (sx * 8.8, 27.5, 81.5), (5.5, 2.2, 1.5)), 2.6)

    # Ears: tapered cones, flattened front-to-back.
    for sx in (-1.0, 1.0):
        ear = sd_flat_round_cone(
            p, (sx * 11.0, 8.0, 84.0), (sx * 16.5, 5.5, 103.0), 8.0, 1.4, 0.55
        )
        d = smin(d, ear, 4.0)

    # Front legs and paws.
    for sx in (-1.0, 1.0):
        d = smin(d, sd_round_cone(p, (sx * 8.5, 13.0, 34.0), (sx * 9.5, 23.0, 6.0), 6.5, 5.0), 6.0)
        d = smin(d, sd_ellipsoid(p, (sx * 9.5, 26.5, 4.5), (6.2, 7.5, 4.5)), 3.0)

    # Hind feet peeking out at the sides.
    for sx in (-1.0, 1.0):
        d = smin(d, sd_ellipsoid(p, (sx * 15.0, 6.0, 5.0), (7.0, 12.0, 5.0)), 5.0)

    # Tail sweeping behind and round the right flank.
    prev = None
    for i in range(25):
        t = i / 24.0
        th = np.radians(252.0 + 143.0 * t)
        rad = 25.0 + 6.0 * np.sin(np.pi * t) - 8.0 * t * t
        pt = (rad * np.cos(th), -6.0 + rad * np.sin(th), 5.0 + 3.5 * t * t)
        r = 6.0 * (1.0 - t) + 3.0 * t
        if prev is not None:
            d = smin(d, sd_round_cone(p, prev[0], pt, prev[1], r), 3.5)
        prev = (pt, r)

    # Flat bottom: intersect with the z >= 0 half-space.
    return np.maximum(d, -p[..., 2])


# ------------------------------------------------------------------- surfacing

def build_mesh(resolution, height_mm, max_faces=None):
    from skimage import measure

    lo = np.array([-40.0, -45.0, -2.0])
    hi = np.array([40.0, 40.0, 108.0])
    span = hi - lo
    # Uniform voxel pitch so marching cubes gets isotropic spacing.
    pitch = span.max() / resolution
    # Nudge the grid off z = 0. The flat-base cut puts a kink exactly on that
    # plane, and samples landing precisely on the level set make marching cubes
    # emit degenerate, non-manifold triangles there.
    lo = lo + np.array([0.0, 0.0, 0.317 * pitch])
    dims = np.maximum(np.ceil(span / pitch).astype(int) + 1, 2)

    axes = [lo[i] + np.arange(dims[i]) * pitch for i in range(3)]
    field = np.empty(tuple(dims), dtype=np.float32)

    # Evaluate slab by slab to keep peak memory modest.
    gx, gy = np.meshgrid(axes[0], axes[1], indexing="ij")
    flat_xy = np.stack([gx.ravel(), gy.ravel()], axis=-1)
    for k, z in enumerate(axes[2]):
        pts = np.concatenate([flat_xy, np.full((flat_xy.shape[0], 1), z)], axis=-1)
        field[:, :, k] = kitten_sdf(pts).reshape(dims[0], dims[1]).astype(np.float32)

    # Pad with solidly-outside values so the surface is always closed, whatever
    # the domain clips.
    field = np.pad(field, 1, mode="constant", constant_values=1e3)
    lo = lo - pitch

    verts, faces, _, _ = measure.marching_cubes(field, level=0.0, spacing=(pitch, pitch, pitch))
    verts = verts + lo

    import trimesh

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()

    # Keep only the largest connected body, in case of stray specks.
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        mesh = max(parts, key=lambda m: m.area)
        mesh.fix_normals()

    if max_faces and len(mesh.faces) > max_faces:
        reduced = mesh.simplify_quadric_decimation(face_count=max_faces)
        # Only accept the decimation if it kept the solid printable.
        if reduced.is_watertight and reduced.is_winding_consistent:
            mesh = reduced
            mesh.fix_normals()

    # Scale to the requested print height and sit it exactly on z = 0.
    current_h = mesh.bounds[1][2] - mesh.bounds[0][2]
    mesh.apply_scale(height_mm / current_h)
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    return mesh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolution", type=int, default=320, help="voxels along the longest axis")
    ap.add_argument("--height", type=float, default=80.0, help="print height in mm")
    ap.add_argument("--max-faces", type=int, default=140000,
                    help="decimate to at most this many triangles (0 to keep all)")
    ap.add_argument("--out", default="kitten.stl")
    args = ap.parse_args()

    mesh = build_mesh(args.resolution, args.height, args.max_faces or None)
    mesh.export(args.out)

    ext = mesh.bounds[1] - mesh.bounds[0]
    print(f"wrote {args.out}")
    print(f"  triangles : {len(mesh.faces)}")
    print(f"  watertight: {mesh.is_watertight}")
    print(f"  winding   : {mesh.is_winding_consistent}")
    print(f"  volume    : {mesh.volume / 1000.0:.1f} cm^3")
    print(f"  bbox (mm) : {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f}")


if __name__ == "__main__":
    main()
