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


def segment_intersection_2d(
    p1: Point2D,
    p2: Point2D,
    p3: Point2D,
    p4: Point2D
) -> Optional[Tuple[float, float, Point2D]]:
    """
    Oblicza punkt przecięcia dwóch odcinków [p1, p2] i [p3, p4].
    Zwraca (t, u, punkt_przecięcia) gdzie t in [0, 1] wzdłuż p1->p2, u in [0, 1] wzdłuż p3->p4,
    lub None jeśli odcinki się nie przecinają.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    dx1 = x2 - x1
    dy1 = y2 - y1
    dx2 = x4 - x3
    dy2 = y4 - y3

    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-11:
        return None

    delta_x = x3 - x1
    delta_y = y3 - y1

    t = (delta_x * dy2 - delta_y * dx2) / denom
    u = (delta_x * dy1 - delta_y * dx1) / denom

    tol = 1e-7
    if -tol <= t <= 1.0 + tol and -tol <= u <= 1.0 + tol:
        t_clamped = max(0.0, min(1.0, t))
        ix = x1 + t_clamped * dx1
        iy = y1 + t_clamped * dy1
        return t_clamped, max(0.0, min(1.0, u)), (ix, iy)

    return None


def ray_polyline_intersection(
    origin: Point2D,
    ray_dir: Point2D,
    polyline: List[Point2D],
    min_t: float = 1e-4
) -> Optional[Tuple[float, Point2D]]:
    """
    Oblicza najbliższy punkt przecięcia promienia (origin, ray_dir) z dowolnym odcinkiem polilinii.
    Zwraca (odległość_t, punkt_przecięcia) lub None.
    """
    n = len(polyline)
    if n < 2:
        return None

    len_dir = math.hypot(ray_dir[0], ray_dir[1])
    if len_dir < 1e-9:
        return None

    dx = ray_dir[0] / len_dir
    dy = ray_dir[1] / len_dir
    x0, y0 = origin

    best_t = float('inf')
    best_pt = None

    for i in range(n - 1):
        x1, y1 = polyline[i]
        x2, y2 = polyline[i + 1]

        vx = x2 - x1
        vy = y2 - y1

        D = vx * dy - vy * dx
        if abs(D) < 1e-11:
            continue

        delta_x = x1 - x0
        delta_y = y1 - y0

        t = (vx * delta_y - vy * delta_x) / D
        u = (dx * delta_y - dy * delta_x) / D

        if t > min_t and -1e-7 <= u <= 1.0 + 1e-7:
            if t < best_t:
                best_t = t
                best_pt = (x0 + t * dx, y0 + t * dy)

    if best_pt is not None:
        return best_t, best_pt
    return None


def trim_polyline_with_boundaries(
    polyline: List[Point2D],
    boundary_lines: List[List[Point2D]],
    click_pt: Point2D
) -> Optional[Tuple[List[Point2D], List[List[Point2D]]]]:
    """
    Dzieli polilinię 'polyline' wszystkimi punktami przecięcia z krawędziami tnącymi 'boundary_lines'.
    Wyszukuje fragment polilinii znajdujący się najbliżej 'click_pt' (kliknięty fragment do usunięcia).
    Zwraca: (usunięty_fragment, lista_pozostałych_fragmentów) lub None jeśli brak przecięć.
    """
    n = len(polyline)
    if n < 2 or not boundary_lines:
        return None

    # 1. Obliczenie odległości skumulowanej wzdłuż polilinii dla każdego wierzchołka
    cum_dist = [0.0]
    for i in range(n - 1):
        d = distance(polyline[i], polyline[i + 1])
        cum_dist.append(cum_dist[-1] + d)
    total_len = cum_dist[-1]
    if total_len < 1e-6:
        return None

    # 2. Wyszukanie wszystkich unikalnych przecięć z krawędziami tnącymi
    intersections: List[Tuple[float, Point2D]] = []

    for seg_idx in range(n - 1):
        p1 = polyline[seg_idx]
        p2 = polyline[seg_idx + 1]
        seg_len = cum_dist[seg_idx + 1] - cum_dist[seg_idx]
        if seg_len < 1e-9:
            continue

        for b_line in boundary_lines:
            nb = len(b_line)
            if nb < 2:
                continue
            for b_idx in range(nb - 1):
                b1 = b_line[b_idx]
                b2 = b_line[b_idx + 1]
                res = segment_intersection_2d(p1, p2, b1, b2)
                if res is not None:
                    t, u, ipt = res
                    dist_along = cum_dist[seg_idx] + t * seg_len
                    # Ignorujemy przecięcia zbyt blisko już zarejestrowanych
                    is_dup = False
                    for existing_s, _ in intersections:
                        if abs(existing_s - dist_along) < 1e-4:
                            is_dup = True
                            break
                    if not is_dup:
                        intersections.append((dist_along, ipt))

    if not intersections:
        return None

    # 3. Sortowanie przecięć wzdłuż linii
    intersections.sort(key=lambda item: item[0])

    # Punkty podziału z początkiem i końcem
    split_points: List[Tuple[float, Point2D]] = [(0.0, polyline[0])]
    for s, pt in intersections:
        if s > 1e-4 and s < total_len - 1e-4:
            split_points.append((s, pt))
    split_points.append((total_len, polyline[-1]))

    if len(split_points) < 3:
        # Tylko początek i koniec (przecięcia były na samych końcach linii)
        return None

    # 4. Podział polilinii na podfragmenty
    sub_pieces: List[List[Point2D]] = []
    for k in range(len(split_points) - 1):
        s_start, p_start = split_points[k]
        s_end, p_end = split_points[k + 1]

        piece: List[Point2D] = [p_start]
        # Dodaj oryginalne wierzchołki leżące wewnątrz przedziału (s_start, s_end)
        for v_idx in range(n):
            sv = cum_dist[v_idx]
            if s_start + 1e-4 < sv < s_end - 1e-4:
                piece.append(polyline[v_idx])
        piece.append(p_end)

        # Oczyszczenie z duplikatów sąsiednich punktów
        cleaned_piece: List[Point2D] = [piece[0]]
        for pt in piece[1:]:
            if distance(cleaned_piece[-1], pt) > 1e-5:
                cleaned_piece.append(pt)
        if len(cleaned_piece) >= 2:
            sub_pieces.append(cleaned_piece)

    if not sub_pieces:
        return None

    # 5. Wyznaczenie, który fragment znajduje się pod kursorem click_pt
    best_piece_idx = 0
    best_dist = float('inf')

    for p_idx, piece in enumerate(sub_pieces):
        # Odległość punktu click_pt do odcinków fragmentu
        for i in range(len(piece) - 1):
            sqr_d, min_pt, after_v, left_of = _point_segment_dist_2d(click_pt, piece[i], piece[i + 1])
            d = math.sqrt(sqr_d)
            if d < best_dist:
                best_dist = d
                best_piece_idx = p_idx

    trimmed_piece = sub_pieces[best_piece_idx]
    remaining_pieces: List[List[Point2D]] = []

    # Łączenie sąsiadujących pozostałych części w spójne polilinie
    current_run: List[Point2D] = []
    for p_idx, piece in enumerate(sub_pieces):
        if p_idx == best_piece_idx:
            if current_run:
                remaining_pieces.append(current_run)
                current_run = []
        else:
            if not current_run:
                current_run = list(piece)
            else:
                # Jeśli koniec obecnego odcinka pokrywa się z początkiem kolejnego
                if distance(current_run[-1], piece[0]) < 1e-4:
                    current_run.extend(piece[1:])
                else:
                    remaining_pieces.append(current_run)
                    current_run = list(piece)
    if current_run:
        remaining_pieces.append(current_run)

    return trimmed_piece, remaining_pieces


def _point_segment_dist_2d(pt: Point2D, p1: Point2D, p2: Point2D) -> Tuple[float, Point2D, int, bool]:
    """Oblicza kwadrat odległości punktu pt do odcinka [p1, p2]."""
    x0, y0 = pt
    x1, y1 = p1
    x2, y2 = p2

    dx = x2 - x1
    dy = y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return (x0 - x1)**2 + (y0 - y1)**2, p1, 1, False

    t = max(0.0, min(1.0, ((x0 - x1) * dx + (y0 - y1) * dy) / len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    sqr_dist = (x0 - proj_x)**2 + (y0 - proj_y)**2
    left_of = (dx * (y0 - y1) - dy * (x0 - x1)) > 0
    return sqr_dist, (proj_x, proj_y), 1, left_of


class FilletTwoLinesResult:
    """Wynik operacji zaokrąglenia (fillet) dwóch linii."""

    def __init__(
        self,
        apex: Point2D,
        radius: float,
        t1: Point2D,
        t2: Point2D,
        center: Point2D,
        arc_points: List[Point2D],
        line1_kept: List[Point2D],
        line1_continuation: Optional[List[Point2D]],
        line1_continues: bool,
        line2_kept: List[Point2D],
        line2_continuation: Optional[List[Point2D]],
        line2_continues: bool,
        joined_corner: Optional[List[Point2D]]
    ):
        self.apex = apex
        self.radius = radius
        self.t1 = t1
        self.t2 = t2
        self.center = center
        self.arc_points = arc_points
        self.line1_kept = line1_kept
        self.line1_continuation = line1_continuation
        self.line1_continues = line1_continues
        self.line2_kept = line2_kept
        self.line2_continuation = line2_continuation
        self.line2_continues = line2_continues
        self.joined_corner = joined_corner


def fillet_two_lines_2d(
    pts1: List[Point2D],
    click1: Point2D,
    pts2: List[Point2D],
    click2: Point2D,
    radius: float,
    mode: SamplingMode = SamplingMode.LINEAR_STEP,
    step_value: float = 1.0,
    min_segments: int = 4,
    is_same_line: bool = False
) -> Optional[FilletTwoLinesResult]:
    """
    Oblicza łuk styczny (fillet) o zadanym promieniu między dwoma liniami pts1 i pts2 (lub dwoma segmentami tej samej linii).
    Wskazane punkty click1 i click2 decydują, które ramiona linii mają zostać zachowane.
    Dokonuje automatycznego trimu:
    - Dla dwóch różnych linii: przycina ramiona do punktów styczności i scala w jedną polilinię (joined_corner).
    - Dla linii przelotowych: zachowuje kontynuację za skrzyżowaniem.
    - Dla tej samej linii (pętla/wyspa lub narożnik): domyka pętlę łukiem lub zaokrągla narożnik bez utraty wierzchołków.
    """
    if len(pts1) < 2 or len(pts2) < 2:
        return None

    is_same = is_same_line or (pts1 is pts2) or (pts1 == pts2)

    # 1. Wyznaczenie segmentów narożnych (lub najbliższych kliknięciom)
    seg1_idx, seg2_idx = _resolve_fillet_segments(pts1, click1, pts2, click2, is_same)

    if is_same and seg1_idx == seg2_idx:
        return None

    a1, b1 = pts1[seg1_idx], pts1[seg1_idx + 1]
    a2, b2 = pts2[seg2_idx], pts2[seg2_idx + 1]

    # 2. Punkt przecięcia prostych nośnych segmentów (apex)
    apex = line_intersection(a1, b1, a2, b2)
    if apex is None:
        return None

    # 3. Wektory kierunkowe ramion w stronę punktów kliknięcia
    u1 = _get_direction_towards_click(a1, b1, apex, click1)
    u2 = _get_direction_towards_click(a2, b2, apex, click2)
    if u1 is None or u2 is None:
        return None

    # Kąt między ramionami
    dot = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
    alpha = math.acos(dot)
    if alpha < math.radians(0.5) or alpha > math.radians(179.5):
        return None

    half_alpha = alpha / 2.0
    sin_half = math.sin(half_alpha)
    tan_half = math.tan(half_alpha)

    eff_radius = min(max(MIN_RADIUS_LIMIT, radius), MAX_RADIUS_LIMIT)
    d_tangent = eff_radius / tan_half

    # Punkty styczności
    t1 = (apex[0] + d_tangent * u1[0], apex[1] + d_tangent * u1[1])
    t2 = (apex[0] + d_tangent * u2[0], apex[1] + d_tangent * u2[1])

    # Środek okręgu
    bisector = (u1[0] + u2[0], u1[1] + u2[1])
    len_bis = math.hypot(bisector[0], bisector[1])
    if len_bis < 1e-6:
        return None
    w = (bisector[0] / len_bis, bisector[1] / len_bis)
    center = (apex[0] + (eff_radius / sin_half) * w[0], apex[1] + (eff_radius / sin_half) * w[1])

    # Próbkowanie łuku
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

    # 4. Obsługa przypadku tej samej linii (pętla/wyspa lub narożnik wewnętrzny)
    if is_same:
        joined_same = _fillet_same_line(
            pts=pts1,
            seg1_idx=seg1_idx,
            u1=u1,
            t1=t1,
            seg2_idx=seg2_idx,
            u2=u2,
            t2=t2,
            arc_points=arc_points,
            apex=apex
        )
        return FilletTwoLinesResult(
            apex=apex,
            radius=eff_radius,
            t1=t1,
            t2=t2,
            center=center,
            arc_points=arc_points,
            line1_kept=joined_same,
            line1_continuation=None,
            line1_continues=False,
            line2_kept=[],
            line2_continuation=None,
            line2_continues=False,
            joined_corner=joined_same
        )

    # 5. Analiza geometrii dwóch oddzielnych linii 1 i 2 (trim / split)
    line1_kept, line1_cont, line1_continues = _trim_or_split_line(pts1, seg1_idx, apex, u1, t1)
    line2_kept, line2_cont, line2_continues = _trim_or_split_line(pts2, seg2_idx, apex, u2, t2)

    # 6. Scalanie narożnika w jedną polilinię (gdy żadna z linii nie kontynuuje się za przecięcie)
    joined_corner = None
    if not line1_continues and not line2_continues and line1_kept and line2_kept:
        # Upewniamy się, że line1_kept biegnie w stronę t1
        p1_oriented = list(line1_kept)
        if distance(p1_oriented[0], t1) < distance(p1_oriented[-1], t1):
            p1_oriented.reverse()

        # Upewniamy się, że line2_kept zaczyna się przy t2 i biegnie ku końcowi
        p2_oriented = list(line2_kept)
        if distance(p2_oriented[-1], t2) < distance(p2_oriented[0], t2):
            p2_oriented.reverse()

        # Składamy: p1_oriented (do t1) + arc_points (od t1 do t2) + p2_oriented (od t2 dalej)
        combined: List[Point2D] = list(p1_oriented)
        for pt in arc_points:
            if distance(combined[-1], pt) > 1e-5:
                combined.append(pt)
        for pt in p2_oriented:
            if distance(combined[-1], pt) > 1e-5:
                combined.append(pt)

        joined_corner = combined

    return FilletTwoLinesResult(
        apex=apex,
        radius=eff_radius,
        t1=t1,
        t2=t2,
        center=center,
        arc_points=arc_points,
        line1_kept=line1_kept,
        line1_continuation=line1_cont,
        line1_continues=line1_continues,
        line2_kept=line2_kept,
        line2_continuation=line2_cont,
        line2_continues=line2_continues,
        joined_corner=joined_corner
    )


def _resolve_fillet_segments(
    pts1: List[Point2D],
    click1: Point2D,
    pts2: List[Point2D],
    click2: Point2D,
    is_same: bool
) -> Tuple[int, int]:
    """
    Wybiera indeksy segmentów do wyznaczenia punktu przecięcia (apex).
    Dla dwóch różnych linii: jeśli linie stykają się lub zbliżają końcami, wybiera segmenty narożne.
    W przeciwnym wypadku (lub dla tej samej linii) używa segmentów najbliższych kliknięciom myszy.
    """
    n1 = len(pts1)
    n2 = len(pts2)
    if is_same or n1 < 2 or n2 < 2:
        return _find_closest_segment_idx(pts1, click1), _find_closest_segment_idx(pts2, click2)

    # Sprawdzenie czy końce linii stykają się w narożniku
    d_0_0 = distance(pts1[0], pts2[0])
    d_0_end = distance(pts1[0], pts2[-1])
    d_end_0 = distance(pts1[-1], pts2[0])
    d_end_end = distance(pts1[-1], pts2[-1])

    min_end_dist = min(d_0_0, d_0_end, d_end_0, d_end_end)
    if min_end_dist < 5.0:
        if min_end_dist == d_0_0:
            return 0, 0
        elif min_end_dist == d_0_end:
            return 0, n2 - 2
        elif min_end_dist == d_end_0:
            return n1 - 2, 0
        else:
            return n1 - 2, n2 - 2

    return _find_closest_segment_idx(pts1, click1), _find_closest_segment_idx(pts2, click2)


def _fillet_same_line(
    pts: List[Point2D],
    seg1_idx: int,
    u1: Point2D,
    t1: Point2D,
    seg2_idx: int,
    u2: Point2D,
    t2: Point2D,
    arc_points: List[Point2D],
    apex: Optional[Point2D] = None
) -> List[Point2D]:
    """
    Łączy dwa segmenty tej samej linii/pętli łukiem zaokrąglenia.
    - Jeśli to pętla (zamknięcie wyspy): zachowuje całe ciało pętli i domyka łukiem bez cięciw.
    - Jeśli to narożnik wewnętrzny na polilinii: łączy początek -> t1 -> łuk -> t2 -> koniec.
    """
    n = len(pts)
    if seg1_idx == seg2_idx or n < 2:
        return list(pts)

    if seg1_idx < seg2_idx:
        k_low, u_low, t_low = seg1_idx, u1, t1
        k_high, u_high, t_high = seg2_idx, u2, t2
        arc_low_to_high = list(arc_points)
    else:
        k_low, u_low, t_low = seg2_idx, u2, t2
        k_high, u_high, t_high = seg1_idx, u1, t1
        arc_low_to_high = list(reversed(arc_points))

    v_low = (pts[k_low + 1][0] - pts[k_low][0], pts[k_low + 1][1] - pts[k_low][1])
    low_fwd = (v_low[0] * u_low[0] + v_low[1] * u_low[1] > 0)

    v_high = (pts[k_high + 1][0] - pts[k_high][0], pts[k_high + 1][1] - pts[k_high][1])
    high_fwd = (v_high[0] * u_high[0] + v_high[1] * u_high[1] > 0)

    if low_fwd and not high_fwd:
        # Pętla / Wyspa (Loop / Island closing): zachowujemy środek między k_low a k_high
        mid_raw = pts[k_low + 1 : k_high + 1]
        mid = []
        d_t_low = distance(t_low, apex) if apex else 0.0
        d_t_high = distance(t_high, apex) if apex else 0.0
        for p in mid_raw:
            if distance(p, t_low) > 1e-4 and distance(p, t_high) > 1e-4:
                if apex and distance(p, apex) < min(d_t_low, d_t_high) - 1e-4:
                    continue
                mid.append(p)

        path_island = [t_low] + mid + [t_high]
        arc_high_to_low = list(reversed(arc_low_to_high))
        combined = list(path_island)
        for pt in arc_high_to_low[1:]:
            if distance(combined[-1], pt) > 1e-4:
                combined.append(pt)
        if distance(combined[-1], combined[0]) > 1e-4:
            combined.append(combined[0])
        return combined

    elif not low_fwd and high_fwd:
        # Narożnik wewnętrzny na polilinii (Internal corner)
        part1 = [P for P in pts[: k_low + 1] if distance(P, t_low) > 1e-4] + [t_low]
        arc_mid = [P for P in arc_low_to_high if distance(P, t_low) > 1e-4 and distance(P, t_high) > 1e-4]
        part2 = [t_high] + [P for P in pts[k_high + 1 :] if distance(P, t_high) > 1e-4]
        return part1 + arc_mid + part2

    else:
        # Fallback: zachowaj środek i domknij jeśli pętla
        mid = [P for P in pts[k_low + 1 : k_high + 1] if distance(P, t_low) > 1e-4 and distance(P, t_high) > 1e-4]
        path_island = [t_low] + mid + [t_high]
        arc_high_to_low = list(reversed(arc_low_to_high))
        combined = list(path_island)
        for pt in arc_high_to_low[1:]:
            if distance(combined[-1], pt) > 1e-4:
                combined.append(pt)
        if len(combined) > 2 and distance(pts[0], pts[-1]) < 1e-2 and distance(combined[-1], combined[0]) > 1e-4:
            combined.append(combined[0])
        return combined


def _find_closest_segment_idx(pts: List[Point2D], pt: Point2D) -> int:
    best_idx = 0
    best_dist = float('inf')
    for i in range(len(pts) - 1):
        sqr_d, min_pt, after_v, left_of = _point_segment_dist_2d(pt, pts[i], pts[i + 1])
        if sqr_d < best_dist:
            best_dist = sqr_d
            best_idx = i
    return best_idx


def _get_direction_towards_click(p1: Point2D, p2: Point2D, apex: Point2D, click_pt: Point2D) -> Optional[Point2D]:
    """Zwraca jednostkowy wektor wzdłuż prostej p1->p2 skierowany od apex w stronę punktu click_pt."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    len_seg = math.hypot(dx, dy)
    if len_seg < 1e-9:
        return None
    ux = dx / len_seg
    uy = dy / len_seg

    # Rzut punktu click na wektor (apex -> click_pt)
    vx = click_pt[0] - apex[0]
    vy = click_pt[1] - apex[1]
    dot = vx * ux + vy * uy

    if dot < 0:
        return (-ux, -uy)
    elif dot > 0:
        return (ux, uy)
    else:
        # Kursor dokładnie na apex - użyj wektora ku środkowi segmentu
        mid_x = (p1[0] + p2[0]) / 2.0 - apex[0]
        mid_y = (p1[1] + p2[1]) / 2.0 - apex[1]
        dot_mid = mid_x * ux + mid_y * uy
        return (ux, uy) if dot_mid >= 0 else (-ux, -uy)


def _trim_or_split_line(
    pts: List[Point2D],
    clicked_seg_idx: int,
    apex: Point2D,
    u_dir: Point2D,
    tangent_pt: Point2D
) -> Tuple[List[Point2D], Optional[List[Point2D]], bool]:
    """
    Przycinanie lub rozcinanie linii wzdłuż wektora u_dir:
    - Wyznacza kierunek wzdłuż polilinii od narożnika ku dalekiemu końcowi.
    - Odrzuca wierzchołki leżące wewnątrz odcinanego narożnika (przed punktem styczności tangent_pt).
    - Zachowuje 100% wierzchołków leżących za punktem styczności tangent_pt (eliminacja powstawania cięciw).
    - Sprawdza, czy linia ma rzeczywistą kontynuację przelotową za skrzyżowaniem (apex).
    """
    n = len(pts)
    if n < 2:
        return list(pts), None, False

    k = clicked_seg_idx
    if k < 0 or k >= n - 1:
        k = 0

    p_k = pts[k]
    p_next = pts[k + 1]
    dx = p_next[0] - p_k[0]
    dy = p_next[1] - p_k[1]
    dot = dx * u_dir[0] + dy * u_dir[1]
    keep_forward = (dot > 0)

    d_tangent = distance(tangent_pt, apex)
    min_cont_threshold = max(1.0, 0.05 * d_tangent)

    d0 = distance(pts[0], apex)
    d_end = distance(pts[-1], apex)

    # Rzut końców na u_dir (od apex)
    proj_0 = (pts[0][0] - apex[0]) * u_dir[0] + (pts[0][1] - apex[1]) * u_dir[1]
    proj_end = (pts[-1][0] - apex[0]) * u_dir[0] + (pts[-1][1] - apex[1]) * u_dir[1]

    # Sprawdzenie czy linia kończy się w narożniku
    is_term_0 = (d0 <= max(3.0, d_tangent + 1.0) and d0 < d_end and proj_0 >= -1.0)
    is_term_end = (d_end <= max(3.0, d_tangent + 1.0) and d_end < d0 and proj_end >= -1.0)

    if is_term_0:
        is_forward = True
        start_j = 0
    elif is_term_end:
        is_forward = False
        start_j = n - 1
    else:
        is_forward = keep_forward
        start_j = k + 1 if keep_forward else k

    if is_forward:
        # Idziemy w stronę końca polilinii (n-1): linia zaczyna się od tangent_pt ku pts[-1]
        kept_body: List[Point2D] = []
        found_tangent = False
        for j in range(start_j, n):
            p = pts[j]
            s_j = (p[0] - apex[0]) * u_dir[0] + (p[1] - apex[1]) * u_dir[1]
            dist_apex = distance(p, apex)
            if not found_tangent:
                # Pomijamy punkty leżące wewnątrz odcinanego narożnika (przed punktem styczności)
                if s_j >= d_tangent - 1e-4 or (dist_apex >= d_tangent - 1e-4 and s_j > 0):
                    found_tangent = True
                    kept_body.append(p)
            else:
                kept_body.append(p)

        if not kept_body:
            kept_body = [pts[-1]]

        line_kept = [tangent_pt] + [p for p in kept_body if distance(p, tangent_pt) > 1e-4]
    else:
        # Idziemy wstecz ku początkowi polilinii (0): linia zaczyna się od pts[0] ku tangent_pt
        kept_body = []
        found_tangent = False
        for j in range(start_j, -1, -1):
            p = pts[j]
            s_j = (p[0] - apex[0]) * u_dir[0] + (p[1] - apex[1]) * u_dir[1]
            dist_apex = distance(p, apex)
            if not found_tangent:
                # Pomijamy punkty leżące wewnątrz odcinanego narożnika (przed punktem styczności)
                if s_j >= d_tangent - 1e-4 or (dist_apex >= d_tangent - 1e-4 and s_j > 0):
                    found_tangent = True
                    kept_body.append(p)
            else:
                kept_body.append(p)

        if not kept_body:
            kept_body = [pts[0]]

        kept_body.reverse()
        line_kept = [p for p in kept_body if distance(p, tangent_pt) > 1e-4] + [tangent_pt]

    # Sprawdzenie kontynuacji wyłącznie dla linii przelotowych (linie kończące się w narożniku jej nie mają)
    has_cont = False
    cont_pts = None
    if not is_term_0 and not is_term_end:
        raw_cont = []
        if is_forward:
            for j in range(k, -1, -1):
                p = pts[j]
                s_p = (p[0] - apex[0]) * u_dir[0] + (p[1] - apex[1]) * u_dir[1]
                perp_p = abs((p[0] - apex[0]) * (-u_dir[1]) + (p[1] - apex[1]) * u_dir[0])
                if s_p < -min_cont_threshold and perp_p < 2.0:
                    raw_cont.append(p)
        else:
            for j in range(k + 1, n):
                p = pts[j]
                s_p = (p[0] - apex[0]) * u_dir[0] + (p[1] - apex[1]) * u_dir[1]
                perp_p = abs((p[0] - apex[0]) * (-u_dir[1]) + (p[1] - apex[1]) * u_dir[0])
                if s_p < -min_cont_threshold and perp_p < 2.0:
                    raw_cont.append(p)

        if len(raw_cont) >= 1:
            has_cont = True
            if distance(raw_cont[0], apex) > distance(raw_cont[-1], apex):
                raw_cont.reverse()
            cont_pts = [apex] + [p for p in raw_cont if distance(p, apex) > 1e-4]

    return line_kept, cont_pts, (has_cont and cont_pts is not None and len(cont_pts) >= 2)

