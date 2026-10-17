"""Структурные признаки момента времени из людей/поз (данные ml/extract_pose.py).

Признаки нормированы на размер кадра и рост человека, чтобы меньше зависеть от ракурса:
число людей, их взаимное расстояние, высота рук относительно плеч/бёдер, скорость рук и корпуса,
яркость и общая энергия движения, а также «окно» вокруг момента (среднее/максимум/размах).
"""
import numpy as np

# COCO keypoints
NOSE, LSH, RSH, LEL, REL, LWR, RWR, LHIP, RHIP = 0, 5, 6, 7, 8, 9, 10, 11, 12


def _person_vec(box, kps, h, w):
    """Вектор одного человека, нормированный на высоту рамки."""
    bh = max(box[3] - box[1], 1.0)
    cx, cy = (box[0] + box[2]) / 2 / w, (box[1] + box[3]) / 2 / h
    sh_y = (kps[LSH, 1] + kps[RSH, 1]) / 2
    hip_y = (kps[LHIP, 1] + kps[RHIP, 1]) / 2
    lw_rel = (kps[LWR, 1] - sh_y) / bh
    rw_rel = (kps[RWR, 1] - sh_y) / bh
    wr_dist = abs(kps[LWR, 0] - kps[RWR, 0]) / bh
    wr_hip = min(abs(kps[LWR, 1] - hip_y), abs(kps[RWR, 1] - hip_y)) / bh
    torso_lean = (kps[NOSE, 0] - (kps[LHIP, 0] + kps[RHIP, 0]) / 2) / bh
    return np.array([cx, cy, bh / h, lw_rel, rw_rel, wr_dist, wr_hip, torso_lean,
                     (box[2] - box[0]) / bh], dtype=np.float32)


def frame_vector(det, h, w):
    """Фиксированный вектор кадра: [n_persons, 2 крупнейших человека (по площади) + их расстояние]."""
    n = len(det["boxes"])
    dim = 9
    vec = np.zeros(1 + 2 * dim + 3, dtype=np.float32)
    vec[0] = n
    if n == 0:
        return vec
    areas = (det["boxes"][:, 2] - det["boxes"][:, 0]) * (det["boxes"][:, 3] - det["boxes"][:, 1])
    order = np.argsort(-areas)[:2]
    pv = [_person_vec(det["boxes"][i], det["kps"][i], h, w) for i in order]
    # сортируем слева-направо, чтобы порядок был устойчивым
    pv.sort(key=lambda v: v[0])
    for k, v in enumerate(pv):
        vec[1 + k * dim:1 + (k + 1) * dim] = v
    if len(pv) == 2:
        vec[-3] = abs(pv[0][0] - pv[1][0])
        vec[-2] = abs(pv[0][1] - pv[1][1])
        vec[-1] = float(np.hypot(vec[-3], vec[-2]))
    return vec


def video_matrix(pose: dict) -> np.ndarray:
    """(T, F) признаки по кадрам: позы + скорости + яркость/движение."""
    h, w = pose["hw"]
    base = np.stack([frame_vector(d, h, w) for d in pose["dets"]])
    vel = np.vstack([np.zeros((1, base.shape[1]), np.float32), np.abs(np.diff(base, axis=0))])
    bright = pose["bright"][:, None]
    motion = pose["motion"][:, None]
    bright_d = np.vstack([[0.0], np.abs(np.diff(pose["bright"]))[:, None]]).astype(np.float32)
    return np.hstack([base, vel, bright / 255.0, motion / 50.0, bright_d / 50.0]).astype(np.float32)


def window_features(mat: np.ndarray, times: np.ndarray, half_window: float) -> np.ndarray:
    """Для каждого момента: среднее, максимум и размах признаков в окне ±half_window."""
    out = np.zeros((len(times), mat.shape[1] * 3), dtype=np.float32)
    for i, t in enumerate(times):
        m = (times >= t - half_window) & (times <= t + half_window)
        seg = mat[m]
        out[i] = np.concatenate([seg.mean(0), seg.max(0), seg.max(0) - seg.min(0)])
    return out
