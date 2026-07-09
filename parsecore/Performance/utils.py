"""Math, RNG and sort helpers reproducing osu!/Rust/C# semantics for bit-exact parity.

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

import math
from collections import deque
from typing import Generic, TypeVar

from parsecore.Beatmap.section.hit_objects import Curve
from parsecore.Beatmap.utils import Pos, f32


def lerp(value1: float, value2: float, amount: float) -> float:
    """Linear interpolation ``a*(1-t) + b*t`` (.NET ``double.Lerp`` form)."""
    return (value1 * (1.0 - amount)) + (value2 * amount)

def bpm_to_milliseconds(bpm: float, delimiter: int | None = None) -> float:
    """Convert a BPM (optionally with a beat delimiter) to a beat length in ms."""
    d = delimiter if delimiter is not None else 4
    return 60000.0 / d / bpm

def millisecods_to_bpm(ms: float, delimiter: int | None = None) -> float:
    """Convert a beat length in ms (optionally with a delimiter) to BPM."""
    d = delimiter if delimiter is not None else 4
    return 60000.0 / (ms * d)

def ieee_div(a: float, b: float) -> float:
    """IEEE-754 division like Rust: ``x/0`` is +/-inf, ``0/0`` is NaN (never raises)."""
    if b != 0.0:
        return a / b
    if a == 0.0 or math.isnan(a):
        return math.nan
    sign = math.copysign(1.0, a) * math.copysign(1.0, b)
    return math.copysign(math.inf, sign)

def ieee_pow(base: float, exp: float) -> float:
    """IEEE-754 ``powf`` like Rust for the cases where Python would raise."""
    try:
        return math.pow(base, exp)
    except ValueError:
        if base == 0.0:
            return math.inf
        return math.nan
    except OverflowError:
        return math.inf

def ieee_ln(x: float) -> float:
    """Natural log like Rust: ``ln(0)`` is -inf, ``ln(negative)`` is NaN."""
    if x > 0.0:
        return math.log(x)
    if x == 0.0:
        return -math.inf
    return math.nan

def rust_max(a: float, b: float) -> float:
    """Rust ``f64::max``: returns the non-NaN operand when one is NaN."""
    if math.isnan(a):
        return b
    if math.isnan(b):
        return a
    return max(a, b)

def rust_min(a: float, b: float) -> float:
    """Rust ``f64::min``: returns the non-NaN operand when one is NaN."""
    if math.isnan(a):
        return b
    if math.isnan(b):
        return a
    return min(a, b)

def logistic(x: float, midpoint_offset: float, multiplier: float, max_value: float | None = None) -> float:
    """Return the value of a logistic sigmoid curve."""
    m = max_value if max_value is not None else 1.0
    return m / (1.0 + math.exp(multiplier * (midpoint_offset - x)))

def logistic_exp(exp: float, max_value: float | None = None) -> float:
    """Return a logistic curve evaluated on an exponent argument."""
    m = max_value if max_value is not None else 1.0
    return m / (1.0 + math.exp(exp))

def norm(p: float, values: list[float]) -> float:
    """Return the p-norm of several values."""
    return math.pow(sum(math.pow(x, p) for x in values), 1.0 / p)

def bell_curve(x: float, mean: float, width: float, multiplier: float | None = None) -> float:
    """Return a bell-curve weight peaking at a given centre."""
    m = multiplier if multiplier is not None else 1.0
    return m * math.exp(math.e * -(math.pow(x - mean, 2.0) / math.pow(width, 2.0)))

def smoothstep_bell_curve(x: float, mean: float = 0.5, width: float = 0.5) -> float:
    """Return a smoothstep-based bell curve."""
    x -= mean
    x = width - x if x > 0 else width + x
    return smoothstep(x, 0, width)

def smoothstep(x: float, start: float, end: float) -> float:
    """Return the smoothstep interpolation of a value between two edges."""
    x = clamp((x - start) / (end - start), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)

def smootherstep(x: float, start: float, end: float) -> float:
    """Return the smootherstep interpolation of a value between two edges."""
    x = clamp((x - start) / (end - start), 0.0, 1.0)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)

def reverse_lerp(x: float, start: float, end: float) -> float:
    """Return the clamped ``0``-``1`` position of a value between two bounds."""
    return clamp((x - start) / (end - start), 0.0, 1.0)

def erf(x: float) -> float:
    """Return the Gauss error function."""
    if x == 0.0:
        return 0.0

    if math.isinf(x):
        return 1.0 if x > 0.0 else -1.0

    if math.isnan(x):
        return math.nan

    t = 1.0 / (1.0 + 0.3275911 * abs(x))
    tau = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))

    erf = 1.0 - tau * math.exp(-x * x)

    return erf if x >= 0.0 else -erf

def erf_inv(x: float) -> float:
    """Return the inverse Gauss error function."""
    if x <= -1.0:
        return -math.inf
    if x >= 1.0:
        return math.inf

    if x == 0.0:
        return 0.0

    A: float = 0.147
    sgn = math.copysign(1.0, x)
    x = math.fabs(x)

    ln: float = math.log(1.0 - x * x)
    t1: float = 2.0 / (math.pi * A) + ln / 2.0
    t2 = ln / A
    base_approx = math.sqrt(t1 * t1 - t2) - t1

    c = math.pow((x - 0.85) / 0.293, 8) if x >= 0.85 else 0.0

    return sgn * (math.sqrt(base_approx) + c)

def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value to the ``[lo, hi]`` range."""
    if value <= minimum:
        value = minimum
    elif value >= maximum:
        value = maximum

    return value

T = TypeVar("T")

class LimitedQueue(Generic[T]):
    """A fixed-capacity queue that drops the oldest element when full."""
    __slots__ = ("_queue",)

    def __init__(self, capacity: int) -> None:
        """Create the queue.

        Args:
            capacity: The maximum number of retained elements.
        """
        self._queue: deque[T] = deque(maxlen=capacity)

    def push(self, elem: T) -> None:
        """Append an element, evicting the oldest if at capacity."""
        self._queue.append(elem)

    def is_empty(self) -> bool:
        """Return whether the queue holds no elements."""
        return not self._queue

    def is_full(self) -> bool:
        """Return whether the queue is at capacity."""
        return len(self._queue) == self._queue.maxlen

    def __len__(self) -> int:
        """Return the number of retained elements."""
        return len(self._queue)

    def __getitem__(self, idx: int) -> T:
        """Return the element at an index (0 = oldest)."""
        return self._queue[idx]

    def last(self) -> T | None:
        """Return the most recently pushed element."""
        return self._queue[-1] if self._queue else None

    def as_list(self) -> list[T]:
        """Return the retained elements as a list, oldest first."""
        return list(self._queue)

U32_MASK: int = 0xFFFFFFFF
INT_MASK: int = 0x7FFFFFFF
INT_MAX: int = 2147483647
INT_TO_REAL: float = 1.0 / (float(INT_MAX) + 1.0)

class OsuRandom:
    """The osu!-stable xorshift RNG (used by the catch and mania converts)."""
    __slots__ = ("x", "y", "z", "w", "bit_buf", "bit_idx")

    def __init__(self, seed: int) -> None:
        """Seed the generator.

        Args:
            seed: The 32-bit seed.
        """
        self.x: int = seed & U32_MASK
        self.y: int = 842502087
        self.z: int = 3579807591
        self.w: int = 273326509
        self.bit_buf: int = 0
        self.bit_idx: int = 32

    def gen_unsigned(self) -> int:
        """Advance the state and return the next raw unsigned 32-bit value."""
        t = (self.x ^ ((self.x << 11) & U32_MASK)) & U32_MASK
        self.x = self.y
        self.y = self.z
        self.z = self.w
        self.w = (self.w ^ (self.w >> 19) ^ t ^ (t >> 8)) & U32_MASK

        return self.w

    def next_int(self) -> int:
        """Return the next non-negative 31-bit integer."""
        return INT_MASK & self.gen_unsigned()

    def next_double(self) -> float:
        """Return the next double in ``[0, 1)``."""
        return INT_TO_REAL * float(self.next_int())

    def next_int_range(self, minimum: int, maximum: int) -> int:
        """Return the next integer in ``[minimum, maximum)``."""
        return int(float(minimum) + self.next_double() * float(maximum - minimum))

    def next_double_range(self, minimum: float, maximum: float) -> int:
        """Return the next value in ``[minimum, maximum)``."""
        return int(minimum + self.next_double() * (maximum - minimum))

    def next_bool(self) -> bool:
        """Return the next random boolean (consuming one bit)."""
        if self.bit_idx == 32:
            self.bit_buf = self.gen_unsigned()
            self.bit_idx = 1
        else:
            self.bit_idx += 1
            self.bit_buf >>= 1

        return (self.bit_buf & 1) == 1

def _wrap_int(value: int) -> int:
    """Wrap an integer into signed 32-bit range (C# overflow semantics)."""
    value &= U32_MASK
    return value - 0x100000000 if value & 0x80000000 else value

class CSharpRandom:
    """A port of .NET ``System.Random`` (used where osu! relies on it)."""
    __slots__ = ("seed_array", "inext", "inextp")

    def __init__(self, seed: int) -> None:
        """Seed the generator like .NET ``Random``.

        Args:
            seed: The seed value.
        """
        self.seed_array: list[int] = [0] * 56
        self.inext: int = 0
        self.inextp: int = 21

        subtraction = INT_MAX if seed == -2147483648 else abs(seed)

        mj = 161803398 - subtraction
        self.seed_array[55] = mj

        mk = 1
        ii = 0

        for _ in range(1, 55):
            ii += 21
            if ii >= 55:
                ii -= 55

            self.seed_array[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += INT_MAX

            mj = self.seed_array[ii]

        for _ in range(1, 5):
            for i in range(1, 56):
                n = i + 30
                if n >= 55:
                    n -= 55

                self.seed_array[i] = _wrap_int(self.seed_array[i] - self.seed_array[1 + n])

                if self.seed_array[i] < 0:
                    self.seed_array[i] += INT_MAX

    def next(self) -> int:
        """Return the next non-negative 31-bit integer."""
        return self._internal_sample()

    def next_max(self, maximum: int) -> int:
        """Return the next integer in ``[0, max)``."""
        return int(self._sample() * float(maximum))

    def _sample(self) -> float:
        """Return the next double in ``[0, 1)`` (raw sample)."""
        return float(self._internal_sample()) * (1.0 / float(INT_MAX))

    def _internal_sample(self) -> int:
        """Advance the internal subtractive-generator state."""
        loc_inext = self.inext + 1
        if loc_inext >= 56:
            loc_inext = 1

        loc_inextp = self.inextp + 1
        if loc_inextp >= 56:
            loc_inextp = 1

        ret_val = self.seed_array[loc_inext] - self.seed_array[loc_inextp]

        if ret_val == INT_MAX:
            ret_val -= 1

        if ret_val < 0:
            ret_val += INT_MAX

        self.seed_array[loc_inext] = ret_val
        self.inext = loc_inext
        self.inextp = loc_inextp

        return ret_val

def get_precision_adjusted_beat_length(slider_velocity_multiplier: float, beat_len: float) -> float:
    """Return the beat length adjusted by slider velocity, rounded as osu! does.

    Args:
        slider_velocity_multiplier: The active slider velocity multiplier.
        beat_len: The uninherited beat length.

    Returns:
        The precision-adjusted beat length (rounds ``-100/sv`` through f32).
    """
    slider_velocity_as_beat_len = -100.0 / slider_velocity_multiplier

    if slider_velocity_as_beat_len < 0.0:
        bpm_multiplier = clamp(f32(-slider_velocity_as_beat_len), 10.0, 10000.0) / 100.0
    else:
        bpm_multiplier = 1.0

    return beat_len * bpm_multiplier

def calculate_difficulty_peppy_stars(
        object_count: int,
        drain_length: int,
        *,
        hp: float,
        od: float,
        cs: float,
) -> int:
    """Return the osu!-stable ScoreV1 difficulty multiplier ('peppy stars')."""
    if drain_length != 0:
        object_to_drain_ratio = clamp(float(object_count) / float(drain_length) * 8.0, 0.0, 16.0)
    else:
        object_to_drain_ratio = 16.0

    return int(_round_ties_even((hp + od + cs + object_to_drain_ratio) / 38.0 * 5.0))

def _round_ties_even(x: float) -> float:
    """Round half-to-even (banker's rounding), matching osu!/C#."""
    return float(round(x))

def csharp_sort_unstable(keys: list, key) -> None:
    """Sort a list in place using C#'s unstable introsort (matches .NET ordering)."""
    n = len(keys)
    if n >= 2:
        _cs_intro_sort(keys, 0, n - 1, 2 * (n.bit_length() - 1), key)


def _cs_swap(keys: list, i: int, j: int) -> None:
    """Swap two list elements (introsort helper)."""
    if i != j:
        keys[i], keys[j] = keys[j], keys[i]


def _cs_swap_if_greater(keys: list, key, a: int, b: int) -> None:
    """Swap two elements if the first compares greater (introsort helper)."""
    if a != b and key(keys[a]) > key(keys[b]):
        keys[a], keys[b] = keys[b], keys[a]


def _cs_intro_sort(keys: list, lo: int, hi: int, depth_limit: int, key) -> None:
    """The recursive introsort core (quicksort with heap-sort fallback)."""
    INTRO_SORT_SIZE_THRESHOLD = 16

    while hi > lo:
        partition_size = hi - lo + 1

        if partition_size <= INTRO_SORT_SIZE_THRESHOLD:
            if partition_size == 2:
                _cs_swap_if_greater(keys, key, lo, hi)
            elif partition_size == 3:
                _cs_swap_if_greater(keys, key, lo, hi - 1)
                _cs_swap_if_greater(keys, key, lo, hi)
                _cs_swap_if_greater(keys, key, hi - 1, hi)
            elif partition_size > 3:
                _cs_insertion_sort(keys, lo, hi, key)
            break

        if depth_limit == 0:
            _cs_heap_sort(keys, lo, hi, key)
            break

        depth_limit -= 1
        p = _cs_pick_pivot_and_partition(keys, lo, hi, key)
        _cs_intro_sort(keys, p + 1, hi, depth_limit, key)
        hi = p - 1


def _cs_pick_pivot_and_partition(keys: list, lo: int, hi: int, key) -> int:
    """Median-of-three pivot selection and partition step."""
    mid = lo + (hi - lo) // 2
    _cs_swap_if_greater(keys, key, lo, mid)
    _cs_swap_if_greater(keys, key, lo, hi)
    _cs_swap_if_greater(keys, key, mid, hi)
    _cs_swap(keys, mid, hi - 1)

    left = lo
    right = hi - 1
    pivot_key = key(keys[right])

    while left < right:
        while True:
            left += 1
            if not key(keys[left]) < pivot_key:
                break
        while True:
            right -= 1
            if not pivot_key < key(keys[right]):
                break
        if left >= right:
            break
        _cs_swap(keys, left, right)

    _cs_swap(keys, left, hi - 1)
    return left


def _cs_insertion_sort(keys: list, lo: int, hi: int, key) -> None:
    """Insertion sort for small partitions."""
    for i in range(lo, hi):
        t = keys[i + 1]
        kt = key(t)
        j = i
        while j >= lo and kt < key(keys[j]):
            keys[j + 1] = keys[j]
            j -= 1
        keys[j + 1] = t


def _cs_heap_sort(keys: list, lo: int, hi: int, key) -> None:
    """Heap sort fallback when the recursion depth limit is hit."""
    n = hi - lo + 1
    for i in range(n // 2, 0, -1):
        _cs_down_heap(keys, i, n, lo, key)
    for i in range(n, 1, -1):
        _cs_swap(keys, lo, lo + i - 1)
        _cs_down_heap(keys, 1, i - 1, lo, key)


def _cs_down_heap(keys: list, i: int, n: int, lo: int, key) -> None:
    """Sift an element down the heap (heap-sort helper)."""
    while i <= n // 2:
        child = 2 * i
        if child < n and key(keys[lo + child - 1]) < key(keys[lo + child]):
            child += 1
        if not key(keys[lo + i - 1]) < key(keys[lo + child - 1]):
            break
        keys[lo + i - 1], keys[lo + child - 1] = keys[lo + child - 1], keys[lo + i - 1]
        i = child


def _idx_of_dist(lengths: list[float], d: float) -> int:
    """Return the index of a distance along a cumulative-length table."""
    left = 0
    right = len(lengths)
    while left < right:
        mid = (left + right) // 2
        v = lengths[mid]
        if v < d:
            left = mid + 1
        elif v > d:
            right = mid
        else:
            return mid
    return left


def _interpolate_curve_position(curve: Curve, progress: float) -> Pos:
    """Interpolate a position at a distance along a sampled curve."""
    path = curve.path
    lengths = curve.lengths

    d = curve.progress_to_dist(progress)
    i = _idx_of_dist(lengths, d)

    if not path:
        return Pos(0.0, 0.0)

    if i == 0:
        return path[0]
    if i >= len(path):
        return path[-1]

    p0 = path[i - 1]
    p1 = path[i]

    d0 = lengths[i - 1]
    d1 = lengths[i]

    if abs(d0 - d1) <= EPSILON:
        return p0

    w = (d - d0) / (d1 - d0)
    return p0 + (p1 - p0) * w

EPSILON = 2.2204460492503131e-16

def almost_eq(a: float, b: float, acceptable_difference: float) -> bool:
    """Return whether two values are equal within a small margin."""
    return abs(a - b) <= acceptable_difference

def eq(a: float, b: float) -> bool:
    """Return whether two floats are exactly equal (total-order aware)."""
    return almost_eq(a, b, EPSILON)

def not_eq(a: float, b: float) -> bool:
    """Return whether two floats are not equal."""
    return abs(a - b) >= EPSILON

def cmp_key(x: float) -> tuple[int, float]:
    """Return a sort key giving floats a total order (NaN last)."""
    sign = math.copysign(1.0, x)

    if math.isnan(x):
        return (1, 0.0) if sign < 0 else (6, 0.0)

    elif x == 0.0:
        return (3, 0.0) if sign < 0 else (4, 0.0)

    elif sign < 0:
        return (2, x)

    else:
        return (5, x)

def total_cmp(a: float, b: float) -> int:
    """Compare two floats with a total order like Rust ``f64::total_cmp``."""
    key_a = cmp_key(a)
    key_b = cmp_key(b)

    if key_a < key_b:
        return -1
    if key_a > key_b:
        return 1

    return 0

def signum(x: float) -> float | int:
    """Return the sign of a value (-1, 0 or 1), with NaN handling."""
    if math.isnan(x):
        return ("nan")

    return math.copysign(1.0, x)