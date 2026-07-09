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

from .colors import Color, Colors, ColorsState, CustomColor, ParseColorsError, parse_u8
from .difficulty import Difficulty, DifficultyKey, DifficultyState, ParseDifficultyError
from .editor import Editor, EditorKey, EditorState, ParseEditorError
from .enums import (
    CountdownType,
    GameMode,
    HitSoundType,
    ParseCountdownTypeError,
    ParseGameModeError,
    SampleBank,
    Section,
    SplineType,
)
from .events import BreakPeriod, Events, EventsState, EventType, ParseEventsError
from .general import General, GeneralKey, GeneralState, ParseGeneralError
from .metadata import Metadata, MetadataKey, MetadataState, ParseMetadataError
from .timing_points import (
    ControlPoints,
    DifficultyPoint,
    EffectFlags,
    EffectPoint,
    ParseTimingPointsError,
    SamplePoint,
    TimingPoint,
    TimingPointsState,
)

__all__ = [
    "ParseTimingPointsError",
    "EffectFlags",
    "TimingPoint",
    "DifficultyPoint",
    "SamplePoint",
    "EffectPoint",
    "ControlPoints",
    "TimingPointsState",
    "ParseMetadataError",
    "MetadataKey",
    "Metadata",
    "MetadataState",
    "ParseGeneralError",
    "GeneralKey",
    "General",
    "GeneralState",
    "ParseEventsError",
    "EventType",
    "BreakPeriod",
    "Events",
    "EventsState",
    "ParseGameModeError",
    "GameMode",
    "ParseCountdownTypeError",
    "CountdownType",
    "SampleBank",
    "HitSoundType",
    "SplineType",
    "Section",
    "ParseEditorError",
    "EditorKey",
    "Editor",
    "EditorState",
    "ParseDifficultyError",
    "DifficultyKey",
    "Difficulty",
    "DifficultyState",
    "ParseColorsError",
    "parse_u8",
    "Color",
    "CustomColor",
    "Colors",
    "ColorsState",
]
