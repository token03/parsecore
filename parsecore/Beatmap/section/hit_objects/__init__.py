"""
MIT License

Copyright (c) 2026-Present O!Lib Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from .hit_objects import (
    ParseHitObjectsError, MAX_COORDINATE_VALUE, HitObjectType, HitSampleDefaultName, SampleBankInfo, HitObjectCircle,
    HitObjectSlider, HitObjectSpinner, HitObjectHold, HitObject, is_linear, convert_points, convert_path_str,
    HitObjectsState, HitSampleInfo
)
from .slider import (
    BEZIER_TOLERANCE, CATMULL_DETAIL, CIRCULAR_ARC_TOLERANCE, PathType, PathControlPoint, Curve, SliderPath,
    SliderEventType, SliderEvent, generate_slider_events
)

__all__ = [
    "ParseHitObjectsError",
    "MAX_COORDINATE_VALUE",
    "HitObjectType",
    "HitSampleDefaultName",
    "SampleBankInfo",
    "HitObjectCircle",
    "HitObjectSlider",
    "HitObjectSpinner",
    "HitObjectHold",
    "HitObject",
    "is_linear",
    "convert_points",
    "convert_path_str",
    "HitObjectsState",
    "HitSampleInfo",
    "BEZIER_TOLERANCE",
    "CATMULL_DETAIL",
    "CIRCULAR_ARC_TOLERANCE",
    "PathType",
    "PathControlPoint",
    "Curve",
    "SliderPath",
    "SliderEventType",
    "SliderEvent",
    "generate_slider_events",
]
