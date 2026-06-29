"""
A3 (3D 경로) — GLB 3D 모델 → 정면 깊이맵 → 계약 H(0..15).

VARCO image-to-3D 가 만든 GLB의 '정면'에서 정사영 레이캐스트로 깊이를 떠서 H로 만든다.
사진 추정이 아니라 실제 기하학이므로 형태가 정확하다(검증 문제 없음).
CPU로 동작(1,536 레이) — GPU 불필요.
"""
from __future__ import annotations
import numpy as np
import trimesh

from . import contract as C


def _load_mesh(glb_path: str) -> trimesh.Trimesh:
    m = trimesh.load(glb_path, force="mesh")
    if isinstance(m, trimesh.Scene):
        m = trimesh.util.concatenate(tuple(m.geometry.values()))
    return m


def glb_to_h(glb_path: str, *, front_axis: str = "+z", pad: float = 0.06) -> np.ndarray:
    """
    GLB → 정면 깊이 → H.
      front_axis: 카메라가 바라보는 방향에서 '앞면'으로 둘 축 (기본 +z 가 화면 앞).
      반환: (ROWS, COLS) 정수 H. 가까운(앞으로 튀어나온) 표면일수록 값이 큼.
    """
    mesh = _load_mesh(glb_path)
    mesh.apply_translation(-mesh.bounding_box.centroid)      # 원점 정렬
    ext = mesh.bounding_box.extents
    scale = 1.0 / max(ext)                                   # 단위 박스로 정규화
    mesh.apply_scale(scale)

    rows, cols = C.GRID_ROWS, C.GRID_COLS
    bb = mesh.bounds                                         # [[minx,miny,minz],[max...]]
    # 정면 평면(x,y) 그리드 생성, z축 -방향으로 레이 발사
    xs = np.linspace(bb[0][0] * (1 - pad), bb[1][0] * (1 - pad), cols)
    ys = np.linspace(bb[1][1] * (1 - pad), bb[0][1] * (1 - pad), rows)  # 위→아래
    gx, gy = np.meshgrid(xs, ys)
    origins = np.column_stack([gx.ravel(), gy.ravel(),
                               np.full(gx.size, bb[1][2] + 1.0)])       # 앞쪽에서
    dirs = np.tile([0.0, 0.0, -1.0], (origins.shape[0], 1))

    locs, ray_idx, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    depth = np.full(rows * cols, np.nan)
    if len(ray_idx):
        depth[ray_idx] = locs[:, 2]                          # 맞은 지점의 z (클수록 앞)

    hit = ~np.isnan(depth)
    H = np.zeros(rows * cols)
    if hit.any():
        d = depth[hit]
        H[hit] = (d - d.min()) / (np.ptp(d) + 1e-6)          # 앞면=1, 뒤=0
    H = H.reshape(rows, cols)
    return C.validate(C.quantize(H))


if __name__ == "__main__":
    # 자가 테스트: 구 + 원기둥 합쳐 GLB로 저장 → H 추출
    import tempfile, os
    s = trimesh.creation.icosphere(subdivisions=3, radius=0.5)
    s.apply_translation([0, 0.2, 0])
    c = trimesh.creation.cylinder(radius=0.15, height=0.8)
    c.apply_translation([0, -0.4, 0.1])
    scene = trimesh.util.concatenate([s, c])
    p = os.path.join(tempfile.gettempdir(), "selftest.glb")
    scene.export(p)
    H = glb_to_h(p)
    print("H shape", H.shape, "| min/max", int(H.min()), int(H.max()),
          "| 솟은 핀", int((H > 0).sum()), "/", H.size)
    # 중앙(구)이 모서리보다 높아야 정상
    print("중앙 H", int(H[14, 24]), "| 모서리 H", int(H[1, 1]))
