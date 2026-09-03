#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MSA: CurveMaster - Moduł core.
"""

from .geometry_utils import (
    SamplingMode,
    arc_from_3_points,
    sample_arc,
    generate_bend_arc,
    fillet_corner,
    replace_segment_in_points,
    replace_vertex_in_points,
    distance,
    distance,
    offset_segment,
    normalize_angle_deg,
    vector_angle_deg,
    find_polar_snap_angle,
    project_point_on_ray_2d,
    ray_segment_intersection_2d,
    project_point_on_ray_t
)
from .layer_modifier import LayerModifier
from .offset_utils import (
    compute_line_offset,
    compute_polygon_offset,
    extract_rings_as_line
)
from .polar_state import (
    PolarState,
    PolarAngleMeasurement,
    POLAR_INCREMENT_PRESETS,
    format_preset_label
)
from .polar_background_manager import PolarBackgroundManager
