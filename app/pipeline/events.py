"""Из покадровой вероятности — список событий (таймкод = пик вероятности внутри участка)."""
from dataclasses import dataclass

import numpy as np


@dataclass
class Event:
    peak_time: float
    start: float
    end: float
    score: float
    peak_idx: int
    lo_idx: int
    hi_idx: int


def smooth(scores: np.ndarray, k: int = 3) -> np.ndarray:
    if len(scores) < k:
        return scores
    kernel = np.ones(k) / k
    return np.convolve(np.pad(scores, (k // 2, k // 2), mode="edge"), kernel, mode="valid")


def find_events(times: np.ndarray, scores: np.ndarray, thr: float, merge_gap_sec: float = 3.0,
                min_len_sec: float = 0.0, max_events: int = 5) -> list[Event]:
    s = smooth(scores)
    above = s >= thr
    events: list[Event] = []
    i = 0
    while i < len(s):
        if not above[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(s) and above[j + 1]:
            j += 1
        if times[j] - times[i] >= min_len_sec:
            p = i + int(np.argmax(s[i:j + 1]))
            events.append(Event(float(times[p]), float(times[i]), float(times[j]), float(s[p]), p, i, j))
        i = j + 1

    merged: list[Event] = []
    for e in events:
        if merged and e.start - merged[-1].end <= merge_gap_sec:
            prev = merged[-1]
            best = e if e.score > prev.score else prev
            merged[-1] = Event(best.peak_time, prev.start, e.end, best.score, best.peak_idx, prev.lo_idx, e.hi_idx)
        else:
            merged.append(e)
    merged.sort(key=lambda e: -e.score)
    return sorted(merged[:max_events], key=lambda e: e.peak_time)
