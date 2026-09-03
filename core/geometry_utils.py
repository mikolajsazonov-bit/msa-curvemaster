#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Moduł geometrii 2D i algorytmów łukowych.
Autor: Mikołaj Sazonov
"""

import math
from enum import Enum
from typing import List, Tuple, Optional, Union

Point2D = Tuple[float, float]
MAX_RADIUS_LIMIT = 10000.0  # Limit promienia na 10 000 metrów
MIN_RADIUS_LIMIT = 0.05


class SamplingMode(Enum):
    """Tryby dyskretyzacji (próbkowania) łuku."""
    LINEAR_STEP = "linear"      # Krok liniowy (długość cięciwy/odcinka w metrach)
    ANGULAR_STEP = "angular"    # Krok kątowy (w stopniach)
    MAX_SAGITTA = "sagitta"     # Maksymalna strzałka ugięcia / tolerancja odchyłki (w metrach)

    @classmethod
    def from_index(cls, index: int) -> 'SamplingMode':
        mapping = {
            0: cls.LINEAR_STEP,
            1: cls.ANGULAR_STEP,
            2: cls.MAX_SAGITTA
        }
        return mapping.get(index, cls.LINEAR_STEP)


def distance(p1: Point2D, p2: Point2D) -> float:
    """Oblicza odległość euklidesową między dwoma punktami 2D."""
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def normalize_angle(angle: float) -> float:
    """Normalizuje kąt do zakresu [0, 2*pi)."""
    two_pi = 2.0 * math.pi
    angle = angle % two_pi
    if angle < 0:
        angle += two_pi
    return angle


def arc_from_3_points(p1: Point2D, p2: Point2D, p3: Point2D) -> Optional[Tuple[Point2D, float, float, float, bool]]:
    """
    Wyznacza okrąg i parametry łuku przechodzącego przez 3 punkty w kolejności p1 -> p2 -> p3.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3

    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return None

    sq1 = x1 * x1 + y1 * y1
    sq2 = x2 * x2 + y2 * y2
    sq3 = x3 * x3 + y3 * y3

    cx = (sq1 * (y2 - y3) + sq2 * (y3 - y1) + sq3 * (y1 - y2)) / d
    cy = (sq1 * (x3 - x2) + sq2 * (x1 - x3) + sq3 * (x2 - x1)) / d
    center = (cx, cy)
    radius = math.hypot(x1 - cx, y1 - cy)

    if radius < 1e-9:
        return None

    radius = min(radius, MAX_RADIUS_LIMIT)

    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    a3 = math.atan2(y3 - cy, x3 - cx)

    a1_n = normalize_angle(a1)
    a2_n = normalize_angle(a2)
    a3_n = normalize_angle(a3)

    sweep_12 = normalize_angle(a2_n - a1_n)
    sweep_13 = normalize_angle(a3_n - a1_n)

    if sweep_12 < sweep_13:
        is_ccw = True
    else:
        is_ccw = False

    return center, radius, a1, a3, is_ccw


def calculate_segment_count(radius: float, sweep_angle: float, mode: SamplingMode, step_value: float, min_segments: int = 4) -> int:
    """
    Oblicza wymaganą liczbę segmentów podziału łuku w zależności od wybranego trybu próbkowania.
    """
    if sweep_angle <= 1e-9:
        return 1

    if mode == SamplingMode.LINEAR_STEP:
        step = max(step_value, 1e-4)
        arc_len = radius * sweep_angle
        n = math.ceil(arc_len / step)
        return max(min_segments, n)

    elif mode == SamplingMode.ANGULAR_STEP:
        step_deg = max(step_value, 0.01)
        step_rad = math.radians(step_deg)
        n = math.ceil(sweep_angle / step_rad)
        return max(2, n)

    elif mode == SamplingMode.MAX_SAGITTA:
        h = max(step_value, 1e-5)
        if h >= radius:
            max_phi = math.pi
        else:
            cos_half = max(-1.0, min(1.0, 1.0 - h / radius))
            max_phi = 2.0 * math.acos(cos_half)
            max_phi = max(max_phi, 1e-4)

        n = math.ceil(sweep_angle / max_phi)
        return max(2, n)

    return max(min_segments, 4)


def sample_arc(
    center: Point2D,
    radius: float,
    start_angle: float,
    end_angle: float,
    is_ccw: bool,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    min_segments: int = 4,
    exact_endpoints: Optional[Tuple[Point2D, Point2D]] = None
) -> List[Point2D]:
    """
    Generuje listę punktów (x, y) wzdłuż łuku okręgu zgodnie z zadanym trybem próbkowania.
    """
    cx, cy = center
    a_start = normalize_angle(start_angle)
    a_end = normalize_angle(end_angle)

    if is_ccw:
        sweep = normalize_angle(a_end - a_start)
        if abs(sweep) < 1e-9 and abs(start_angle - end_angle) > 1e-9:
            sweep = 2.0 * math.pi
    else:
        sweep = -normalize_angle(a_start - a_end)
        if abs(sweep) < 1e-9 and abs(start_angle - end_angle) > 1e-9:
            sweep = -2.0 * math.pi

    total_sweep_rad = abs(sweep)
    num_segments = calculate_segment_count(radius, total_sweep_rad, mode, step_value, min_segments=min_segments)

    points: List[Point2D] = []

    for i in range(num_segments + 1):
        if i == 0 and exact_endpoints is not None:
            points.append(exact_endpoints[0])
            continue
        if i == num_segments and exact_endpoints is not None:
            points.append(exact_endpoints[1])
            continue

        t = i / float(num_segments)
        current_angle = a_start + t * sweep
        px = cx + radius * math.cos(current_angle)
        py = cy + radius * math.sin(current_angle)
        points.append((px, py))

    return points


def generate_bend_arc(
    p_start: Point2D,
    p_mid: Point2D,
    p_end: Point2D,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    min_segments: int = 4
) -> List[Point2D]:
    """
    Tworzy łuk przechodzący przez p_start, p_mid, p_end i dyskretyzuje go do serii punktów.
    """
    arc_data = arc_from_3_points(p_start, p_mid, p_end)
    if arc_data is None:
        return [p_start, p_end]

    center, radius, start_angle, end_angle, is_ccw = arc_data
    return sample_arc(
        center=center,
        radius=radius,
        start_angle=start_angle,
        end_angle=end_angle,
        is_ccw=is_ccw,
        mode=mode,
        step_value=step_value,
        min_segments=min_segments,
        exact_endpoints=(p_start, p_end)
    )


def line_intersection(p1: Point2D, p2: Point2D, p3: Point2D, p4: Point2D) -> Optional[Point2D]:
    """
    Oblicza punkt przecięcia prostej p1->p2 z prostą p3->p4.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def cyclic_range(start: int, end: int, n: int) -> List[int]:
    """
    Zwraca listę indeksów od start do end włącznie w pierścieniu o n elementach (0 do n-1).
    """
    if n <= 0:
        return []
    indices: List[int] = []
    curr = start % n
    target = end % n
    for _ in range(n + 1):
        indices.append(curr)
        if curr == target:
            break
        curr = (curr + 1) % n
    return indices


def fillet_between_segments(
    points: List[Point2D],
    a: int,
    b: int,
    radius: float,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    min_segments: int = 4,
    is_closed: bool = False
) -> Optional[Tuple[Point2D, List[Point2D], Point2D, List[int], float]]:
    """
    Oblicza łuk styczny o zadanym promieniu dla konkretnej pary segmentów wejścia (points[a]->points[a+1])
    oraz wyjścia (points[b]->points[b+1]), połykając wszystkie wierzchołki od a+1 do b.
    Wspiera zarówno linie otwarte, jak i zamknięte pierścienie (poligony).
    """
    n = len(points)
    if n < 3:
        return None

    if is_closed:
        m = n - 1 if (n > 1 and points[0] == points[-1]) else n
        if m < 3:
            return None
        # Przesunięcie cykliczne tak, aby a znalazło się w bezpiecznej pozycji
        shift = (m // 2 - (a % m)) % m
        shifted_unique = [points[(i - shift) % m] for i in range(m)]
        shifted_ring = shifted_unique + [shifted_unique[0]]
        s_a = (a + shift) % m
        s_b = (b + shift) % m
        if s_b < s_a:
            s_b += m

        # Uruchomienie na rozwiniętym pierścieniu
        res = _fillet_between_segments_open(
            shifted_ring, s_a, s_b, radius, mode, step_value, min_segments
        )
        if res is None:
            return None
        t1, arc_points, t2, shifted_consumed, eff_radius = res
        orig_consumed = [(idx - shift) % m for idx in shifted_consumed]
        return t1, arc_points, t2, orig_consumed, eff_radius

    return _fillet_between_segments_open(
        points, a, b, radius, mode, step_value, min_segments
    )


def _fillet_between_segments_open(
    points: List[Point2D],
    a: int,
    b: int,
    radius: float,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    min_segments: int = 4
) -> Optional[Tuple[Point2D, List[Point2D], Point2D, List[int], float]]:
    n = len(points)
    if a < 0 or a >= n - 1 or b < a or b >= n - 1:
        return None

    apex = line_intersection(points[a], points[a + 1], points[b + 1], points[b])
    if apex is None:
        return None

    u = (points[a][0] - apex[0], points[a][1] - apex[1])
    len_u = math.hypot(u[0], u[1])
    if len_u < 1e-6:
        return None
    u = (u[0] / len_u, u[1] / len_u)

    v = (points[b + 1][0] - apex[0], points[b + 1][1] - apex[1])
    len_v = math.hypot(v[0], v[1])
    if len_v < 1e-6:
        return None
    v = (v[0] / len_v, v[1] / len_v)

    dot = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
    alpha = math.acos(dot)
    if alpha < math.radians(0.5) or alpha > math.radians(179.5):
        return None

    half_alpha = alpha / 2.0
    sin_half = math.sin(half_alpha)
    tan_half = math.tan(half_alpha)

    eff_radius = min(max(MIN_RADIUS_LIMIT, radius), MAX_RADIUS_LIMIT)
    d_apex = eff_radius / tan_half

    t1 = (apex[0] + d_apex * u[0], apex[1] + d_apex * u[1])
    t2 = (apex[0] + d_apex * v[0], apex[1] + d_apex * v[1])

    bisector = (u[0] + v[0], u[1] + v[1])
    len_bis = math.hypot(bisector[0], bisector[1])
    if len_bis < 1e-6:
        return None
    w = (bisector[0] / len_bis, bisector[1] / len_bis)
    center = (apex[0] + (eff_radius / sin_half) * w[0], apex[1] + (eff_radius / sin_half) * w[1])

    a_t1 = math.atan2(t1[1] - center[1], t1[0] - center[0])
    a_t2 = math.atan2(t2[1] - center[1], t2[0] - center[0])
    d_ccw = normalize_angle(a_t2 - a_t1)
    is_ccw = (d_ccw < math.pi)

    consumed = list(range(a + 1, b + 1))
    arc_points = sample_arc(
        center=center,
        radius=eff_radius,
        start_angle=a_t1,
        end_angle=a_t2,
        is_ccw=is_ccw,
        mode=mode,
        step_value=step_value,
        min_segments=min_segments,
        exact_endpoints=(t1, t2)
    )

    return t1, arc_points, t2, consumed, eff_radius


def fillet_corner(
    p_prev: Point2D,
    p_curr: Point2D,
    p_next: Point2D,
    radius: Optional[float] = None,
    drag_point: Optional[Point2D] = None,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    min_segments: int = 4
) -> Optional[Tuple[Point2D, List[Point2D], Point2D, Point2D, float, float]]:
    """
    Oblicza precyzyjny łuk STYCZNY (true tangent fillet) w pojedynczym narożniku p_curr.
    """
    vx, vy = p_curr
    d_prev = distance(p_prev, p_curr)
    d_next = distance(p_next, p_curr)

    if d_prev < 1e-6 or d_next < 1e-6:
        return None

    u = ((p_prev[0] - vx) / d_prev, (p_prev[1] - vy) / d_prev)
    v = ((p_next[0] - vx) / d_next, (p_next[1] - vy) / d_next)

    dot = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
    alpha = math.acos(dot)

    if alpha < math.radians(0.5) or alpha > math.radians(179.5):
        return None

    half_alpha = alpha / 2.0
    sin_half = math.sin(half_alpha)
    tan_half = math.tan(half_alpha)

    bisector = (u[0] + v[0], u[1] + v[1])
    len_bisector = math.hypot(bisector[0], bisector[1])
    if len_bisector < 1e-9:
        return None
    w = (bisector[0] / len_bisector, bisector[1] / len_bisector)

    if radius is not None and radius > 0:
        eff_radius = min(float(radius), MAX_RADIUS_LIMIT)
        eff_d = eff_radius / tan_half
    elif drag_point is not None:
        d_mouse = distance(p_curr, drag_point)
        eff_d = max(0.1, d_mouse)
        eff_radius = min(eff_d * tan_half, MAX_RADIUS_LIMIT)
        eff_d = eff_radius / tan_half
    else:
        return None

    t1 = (vx + eff_d * u[0], vy + eff_d * u[1])
    t2 = (vx + eff_d * v[0], vy + eff_d * v[1])

    dist_vo = eff_radius / sin_half
    center = (vx + dist_vo * w[0], vy + dist_vo * w[1])

    a_t1 = math.atan2(t1[1] - center[1], t1[0] - center[0])
    a_t2 = math.atan2(t2[1] - center[1], t2[0] - center[0])

    d_ccw = normalize_angle(a_t2 - a_t1)
    is_ccw = (d_ccw < math.pi)

    arc_points = sample_arc(
        center=center,
        radius=eff_radius,
        start_angle=a_t1,
        end_angle=a_t2,
        is_ccw=is_ccw,
        mode=mode,
        step_value=step_value,
        min_segments=min_segments,
        exact_endpoints=(t1, t2)
    )

    return t1, arc_points, t2, center, eff_radius, eff_d


def multi_vertex_fillet(
    points: List[Point2D],
    vertex_idx: int,
    drag_pt_or_radius: Union[Point2D, float],
    is_radius: bool = False,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    is_closed: bool = False,
    max_search_nodes: int = 20
) -> Optional[Tuple[Point2D, List[Point2D], Point2D, List[int], float, Tuple[int, int]]]:
    """
    Zaawansowany algorytm wieloodcinkowego zaokrąglenia stycznego (Multi-Segment Bi-Tangent Fillet).
    Wspiera linie otwarte oraz zamknięte pierścienie (poligony), w tym zaokrąglanie wierzchołka 0.
    Zwraca: (T1, arc_points, T2, consumed_indices, eff_radius, (seg_a, seg_b))
    """
    n = len(points)
    if n < 3:
        return None

    if is_closed:
        m = n - 1 if (n > 1 and points[0] == points[-1]) else n
        if m < 3:
            return None
        v_idx = vertex_idx % m
        shift = (m // 2 - v_idx) % m
        shifted_unique = [points[(i - shift) % m] for i in range(m)]
        shifted_ring = shifted_unique + [shifted_unique[0]]
        shifted_target_idx = m // 2

        res = _multi_vertex_fillet_open(
            points=shifted_ring,
            vertex_idx=shifted_target_idx,
            drag_pt_or_radius=drag_pt_or_radius,
            is_radius=is_radius,
            mode=mode,
            step_value=step_value,
            max_search_nodes=min(max_search_nodes, m // 2)
        )
        if res is None:
            return None
        t1, arc_points, t2, shifted_consumed, eff_radius, (s_a, s_b) = res
        orig_consumed = [(idx - shift) % m for idx in shifted_consumed]
        orig_segs = ((s_a - shift) % m, (s_b - shift) % m)
        return t1, arc_points, t2, orig_consumed, eff_radius, orig_segs

    return _multi_vertex_fillet_open(
        points=points,
        vertex_idx=vertex_idx,
        drag_pt_or_radius=drag_pt_or_radius,
        is_radius=is_radius,
        mode=mode,
        step_value=step_value,
        max_search_nodes=max_search_nodes
    )


def _multi_vertex_fillet_open(
    points: List[Point2D],
    vertex_idx: int,
    drag_pt_or_radius: Union[Point2D, float],
    is_radius: bool = False,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    max_search_nodes: int = 20
) -> Optional[Tuple[Point2D, List[Point2D], Point2D, List[int], float, Tuple[int, int]]]:
    n = len(points)
    if vertex_idx <= 0 or vertex_idx >= n - 1:
        return None

    a = vertex_idx - 1
    b = vertex_idx

    min_a = max(0, vertex_idx - max_search_nodes)
    max_b = min(n - 2, vertex_idx + max_search_nodes)

    if not is_radius:
        d_mouse = distance(points[vertex_idx], drag_pt_or_radius)
        target_span = max(0.1, d_mouse)

    for step in range(max_search_nodes):
        apex = line_intersection(points[a], points[a + 1], points[b + 1], points[b])
        if apex is None:
            break

        u = (points[a][0] - apex[0], points[a][1] - apex[1])
        len_u = math.hypot(u[0], u[1])
        if len_u < 1e-6:
            break
        u = (u[0] / len_u, u[1] / len_u)

        v = (points[b + 1][0] - apex[0], points[b + 1][1] - apex[1])
        len_v = math.hypot(v[0], v[1])
        if len_v < 1e-6:
            break
        v = (v[0] / len_v, v[1] / len_v)

        dot = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
        alpha = math.acos(dot)
        if alpha < math.radians(0.5) or alpha > math.radians(179.5):
            break

        half_alpha = alpha / 2.0
        sin_half = math.sin(half_alpha)
        tan_half = math.tan(half_alpha)

        if is_radius:
            eff_radius = min(float(drag_pt_or_radius), MAX_RADIUS_LIMIT)
            d_apex = eff_radius / tan_half
        else:
            d_apex = target_span
            eff_radius = min(target_span * tan_half, MAX_RADIUS_LIMIT)

        t1 = (apex[0] + d_apex * u[0], apex[1] + d_apex * u[1])
        t2 = (apex[0] + d_apex * v[0], apex[1] + d_apex * v[1])

        # Sprawdzenie czy T1 wykracza poza wierzchołek points[a] (overflow w lewo)
        seg_a_len = distance(points[a], points[a + 1])
        dist_a1_t1 = distance(points[a + 1], t1)
        overflow_left = (dist_a1_t1 > seg_a_len and a > min_a)

        # Sprawdzenie czy T2 wykracza poza wierzchołek points[b+1] (overflow w prawo)
        seg_b_len = distance(points[b], points[b + 1])
        dist_b_t2 = distance(points[b], t2)
        overflow_right = (dist_b_t2 > seg_b_len and b < max_b)

        if not overflow_left and not overflow_right:
            bisector = (u[0] + v[0], u[1] + v[1])
            len_bis = math.hypot(bisector[0], bisector[1])
            if len_bis < 1e-6:
                break
            w = (bisector[0] / len_bis, bisector[1] / len_bis)
            center = (apex[0] + (eff_radius / sin_half) * w[0], apex[1] + (eff_radius / sin_half) * w[1])

            a_t1 = math.atan2(t1[1] - center[1], t1[0] - center[0])
            a_t2 = math.atan2(t2[1] - center[1], t2[0] - center[0])
            d_ccw = normalize_angle(a_t2 - a_t1)
            is_ccw = (d_ccw < math.pi)

            consumed = list(range(a + 1, b + 1))
            arc_points = sample_arc(
                center=center,
                radius=eff_radius,
                start_angle=a_t1,
                end_angle=a_t2,
                is_ccw=is_ccw,
                mode=mode,
                step_value=step_value,
                exact_endpoints=(t1, t2)
            )
            return t1, arc_points, t2, consumed, eff_radius, (a, b)

        if overflow_left:
            a -= 1
        if overflow_right:
            b += 1

    # Fallback na pojedynczy narożnik
    res_single = fillet_corner(
        points[vertex_idx - 1], points[vertex_idx], points[vertex_idx + 1],
        radius=(float(drag_pt_or_radius) if is_radius else None),
        drag_point=(drag_pt_or_radius if not is_radius else None),
        mode=mode, step_value=step_value
    )
    if res_single:
        t1_s, arc_s, t2_s, center_s, r_s, d_s = res_single
        return t1_s, arc_s, t2_s, [vertex_idx], r_s, (vertex_idx - 1, vertex_idx)

    return None


def replace_segment_in_points(
    points: List[Point2D],
    seg_index: int,
    replacement: List[Point2D],
    is_closed: bool = False
) -> List[Point2D]:
    """
    Zastępuje odcinek między points[seg_index] i points[seg_index + 1] ciągiem punktów replacement.
    """
    n = len(points)
    if n < 2 or seg_index < 0 or seg_index >= n - 1:
        return list(points)

    prefix = points[:seg_index]
    suffix = points[seg_index + 2:] if (seg_index + 2 <= n) else []

    new_points = prefix + replacement + suffix

    if is_closed and len(new_points) > 1:
        new_points[-1] = new_points[0]

    return new_points


def replace_vertex_in_points(
    points: List[Point2D],
    vertex_index: int,
    fillet_points: List[Point2D],
    is_closed: bool = False
) -> List[Point2D]:
    """
    Zastępuje pojedynczy wierzchołek points[vertex_index] ciągiem punktów łuku zaokrąglenia.
    """
    return replace_vertex_range_in_points(
        points=points,
        consumed_indices=[vertex_index],
        replacement_points=fillet_points,
        is_closed=is_closed
    )


def replace_vertex_range_in_points(
    points: List[Point2D],
    consumed_indices: List[int],
    replacement_points: List[Point2D],
    is_closed: bool = False
) -> List[Point2D]:
    """
    Zastępuje zakres wierzchołków o indeksach w consumed_indices nowym ciągiem punktów replacement_points.
    Wspiera zarówno linie otwarte, jak i zamknięte pierścienie (poligony), gwarantując domknięcie.
    """
    n = len(points)
    if not consumed_indices or n == 0:
        return list(points)

    if is_closed:
        m = n - 1 if (n > 1 and points[0] == points[-1]) else n
        if m < 3:
            new_pts = list(replacement_points)
            if len(new_pts) > 1 and new_pts[0] != new_pts[-1]:
                new_pts.append(new_pts[0])
            return new_pts

        ref_idx = consumed_indices[0] % m
        shift = (m // 2 - ref_idx) % m
        shifted_unique = [points[(i - shift) % m] for i in range(m)]
        shifted_ring = shifted_unique + [shifted_unique[0]]
        shifted_consumed = [(idx + shift) % m for idx in consumed_indices]

        min_s = min(shifted_consumed)
        max_s = max(shifted_consumed)

        prefix = shifted_ring[:min_s]
        suffix = shifted_ring[max_s + 1 : -1]
        new_shifted_unique = prefix + replacement_points + suffix

        # Unshift z zachowaniem wierzchołka startowego (jeśli nie był połykany)
        v0_pos_in_shifted = shift
        if v0_pos_in_shifted not in shifted_consumed:
            if v0_pos_in_shifted < min_s:
                v0_new_idx = v0_pos_in_shifted
            else:
                v0_new_idx = min_s + len(replacement_points) + (v0_pos_in_shifted - max_s - 1)
            new_unique = new_shifted_unique[v0_new_idx:] + new_shifted_unique[:v0_new_idx]
        else:
            # Gdy wierzchołek 0 został połknięty, zaczynamy od początku łuku
            arc_start_idx = min_s
            new_unique = new_shifted_unique[arc_start_idx:] + new_shifted_unique[:arc_start_idx]

        new_pts = new_unique + [new_unique[0]]
        return new_pts

    else:
        min_idx = max(0, min(consumed_indices))
        max_idx = min(n - 1, max(consumed_indices))
        prefix = points[:min_idx]
        suffix = points[max_idx + 1:]
        return prefix + replacement_points + suffix


def offset_segment(p1: Point2D, p2: Point2D, dist: float) -> Tuple[Point2D, Point2D]:
    """
    Równolegle odsuwa pojedynczy odcinek p1->p2 o zadaną odległość (dodatnia = w lewo od wektora).
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return p1, p2
    # Wektor normalny jednostkowy w lewo
    nx = -dy / length
    ny = dx / length
    return (p1[0] + dist * nx, p1[1] + dist * ny), (p2[0] + dist * nx, p2[1] + dist * ny)


def normalize_angle_deg(angle_deg: float) -> float:
    """Normalizuje kąt w stopniach do zakresu [0, 360)."""
    angle = angle_deg % 360.0
    if angle < 0:
        angle += 360.0
    return angle


def vector_angle_deg(p1: Point2D, p2: Point2D) -> float:
    """Oblicza kąt wektora p1 -> p2 w stopniach w zakresie [0, 360)."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    rad = math.atan2(dy, dx)
    return normalize_angle_deg(math.degrees(rad))


def find_polar_snap_angle(
    current_angle_deg: float,
    base_angle_deg: float = 0.0,
    increment_deg: float = 15.0,
    additional_angles: Optional[List[float]] = None,
    tolerance_deg: float = 4.0
) -> Optional[Tuple[float, float]]:
    """
    Sprawdza, czy kąt kursora (current_angle_deg) przyciąga się do któregoś z kątów polarnych.
    Kąty polarne wyznaczane są jako wielokrotności increment_deg względem base_angle_deg
    oraz opcjonalne kąty dodatkowe (additional_angles) względem base_angle_deg.

    Zwraca: (snapped_map_angle_deg, snapped_relative_angle_deg) lub None jeśli brak przyciągania.
    """
    rel_angle = normalize_angle_deg(current_angle_deg - base_angle_deg)

    best_diff = float('inf')
    best_target_rel = None

    # 1. Sprawdzenie wielokrotności kroku kątowego
    if increment_deg > 0:
        n_steps = max(1, int(round(360.0 / increment_deg)))
        for i in range(n_steps):
            target = normalize_angle_deg(i * increment_deg)
            diff = abs(rel_angle - target)
            diff = min(diff, 360.0 - diff)
            if diff < best_diff:
                best_diff = diff
                best_target_rel = target

    # 2. Sprawdzenie kątów dodatkowych
    if additional_angles:
        for add_angle in additional_angles:
            target = normalize_angle_deg(add_angle)
            diff = abs(rel_angle - target)
            diff = min(diff, 360.0 - diff)
            if diff < best_diff:
                best_diff = diff
                best_target_rel = target

    if best_diff <= tolerance_deg and best_target_rel is not None:
        snapped_map_angle = normalize_angle_deg(base_angle_deg + best_target_rel)
        return snapped_map_angle, best_target_rel

    return None


def project_point_on_ray_2d(origin: Point2D, dist: float, angle_deg: float) -> Point2D:
    """Rzutuje punkt od punktu bazowego origin na zadaną odległość wzdłuż kąta w stopniach."""
    rad = math.radians(angle_deg)
    return origin[0] + dist * math.cos(rad), origin[1] + dist * math.sin(rad)


def ray_segment_intersection_2d(
    origin: Point2D,
    angle_deg: float,
    seg_p1: Point2D,
    seg_p2: Point2D
) -> Optional[Tuple[float, Point2D]]:
    """
    Oblicza punkt przecięcia promienia wychodzącego z 'origin' pod kątem 'angle_deg' (w stopniach)
    z odcinkiem [seg_p1, seg_p2].
    Zwraca: (odległość_wzdłuż_promienia_t, (x_przecięcia, y_przecięcia)) lub None.
    """
    rad = math.radians(angle_deg)
    dx = math.cos(rad)
    dy = math.sin(rad)

    x0, y0 = origin
    x1, y1 = seg_p1
    x2, y2 = seg_p2

    vx = x2 - x1
    vy = y2 - y1

    D = vx * dy - vy * dx
    if abs(D) < 1e-11:
        return None

    delta_x = x1 - x0
    delta_y = y1 - y0

    t = (vx * delta_y - vy * delta_x) / D
    u = (dx * delta_y - dy * delta_x) / D

    if t > 1e-7 and -1e-7 <= u <= 1.0 + 1e-7:
        ix = x0 + t * dx
        iy = y0 + t * dy
        return t, (ix, iy)
    return None


def project_point_on_ray_t(
    origin: Point2D,
    angle_deg: float,
    pt: Point2D
) -> Tuple[float, float, Point2D]:
    """
    Rzutuje punkt 'pt' na promień (origin, angle_deg).
    Zwraca: (odległość_wzdłuż_promienia_t, odległość_prostopadła_perp_dist, rzutowany_punkt).
    """
    rad = math.radians(angle_deg)
    dx = math.cos(rad)
    dy = math.sin(rad)

    x0, y0 = origin
    xv, yv = pt

    t = (xv - x0) * dx + (yv - y0) * dy
    proj_x = x0 + t * dx
    proj_y = y0 + t * dy

    perp_dist = math.hypot(xv - proj_x, yv - proj_y)
    return t, perp_dist, (proj_x, proj_y)

