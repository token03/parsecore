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

from __future__ import annotations

from dataclasses import dataclass

def _round_ties_even(x: float) -> int:
    return int(round(x))

@dataclass(slots=True)
class CatchHitResults:
    fruits: int = 0
    droplets: int = 0
    tiny_droplets: int = 0
    tiny_droplet_misses: int = 0
    misses: int = 0

    def total_hits(self) -> int:
        return (
                self.fruits + self.droplets + self.tiny_droplets
                + self.tiny_droplet_misses + self.misses
        )

    def total_successful_hits(self) -> int:
        return self.fruits + self.droplets + self.tiny_droplets

    def accuracy(self) -> float:
        total_hits = self.total_hits()
        if total_hits == 0:
            return 0.0
        return self.total_successful_hits() / total_hits

def _sat_sub(a: int, b: int) -> int:
    return a - b if a > b else 0

def _enforce_fruit_droplet_pool(
        fruits: int, droplets: int, misses: int,
        n_fruits: int, n_droplets: int,
) -> tuple[int, int]:
    pool_total = n_fruits + n_droplets
    current_sum = fruits + droplets + misses

    if current_sum < pool_total:
        needed = pool_total - current_sum
        new_droplets = min(droplets + needed, n_droplets)
        still_needed = _sat_sub(pool_total, fruits + new_droplets + misses)
        new_fruits = min(fruits + still_needed, n_fruits)
        return new_fruits, new_droplets

    if current_sum > pool_total:
        excess = current_sum - pool_total
        new_droplets = _sat_sub(droplets, excess)
        still_excess = _sat_sub(fruits + new_droplets + misses, pool_total)
        new_fruits = _sat_sub(fruits, still_excess)
        return new_fruits, new_droplets

    return fruits, droplets

def _enforce_tiny_droplet_pool(
        tiny_droplets: int, tiny_droplet_misses: int, n_tiny_droplets: int,
) -> tuple[int, int]:
    tiny_current_sum = tiny_droplets + tiny_droplet_misses

    if tiny_current_sum < n_tiny_droplets:
        needed = n_tiny_droplets - tiny_current_sum
        new_tiny_droplets = min(tiny_droplets + needed, n_tiny_droplets)
        still_needed = _sat_sub(n_tiny_droplets, new_tiny_droplets)
        return new_tiny_droplets, still_needed

    if tiny_current_sum > n_tiny_droplets:
        excess = tiny_current_sum - n_tiny_droplets
        new_tiny_droplet_misses = _sat_sub(tiny_droplet_misses, excess)
        still_excess = _sat_sub(
            tiny_droplets + new_tiny_droplet_misses, n_tiny_droplets,
        )
        new_tiny_droplets = _sat_sub(tiny_droplets, still_excess)
        return new_tiny_droplets, new_tiny_droplet_misses

    return tiny_droplets, tiny_droplet_misses

def generate_hitresults(
        *,
        n_fruits: int,
        n_droplets: int,
        n_tiny_droplets: int,
        acc: float | None,
        fruits: int | None,
        droplets: int | None,
        tiny_droplets: int | None,
        tiny_droplet_misses: int | None,
        misses: int | None,
) -> CatchHitResults:
    clamped_misses = min(misses, n_fruits + n_droplets) if misses is not None else 0

    if acc is None:
        return _generate_ignore_acc(
            n_fruits, n_droplets, n_tiny_droplets,
            fruits, droplets, tiny_droplets, tiny_droplet_misses,
            clamped_misses,
        )

    return _generate_fast(
        n_fruits, n_droplets, n_tiny_droplets, acc,
        fruits, droplets, tiny_droplets, tiny_droplet_misses,
        clamped_misses,
    )

def _generate_ignore_acc(
        n_fruits: int,
        n_droplets: int,
        n_tiny_droplets: int,
        in_fruits: int | None,
        in_droplets: int | None,
        in_tiny_droplets: int | None,
        in_tiny_droplet_misses: int | None,
        misses: int,
) -> CatchHitResults:
    fruit_droplet_remain = _sat_sub(n_fruits + n_droplets, misses)
    tiny_droplet_remain = n_tiny_droplets

    fruits: int | None = None
    droplets: int | None = None
    if in_fruits is not None:
        fruits = min(min(in_fruits, n_fruits), fruit_droplet_remain)
        fruit_droplet_remain = _sat_sub(fruit_droplet_remain, fruits)
    if in_droplets is not None:
        droplets = min(min(in_droplets, n_droplets), fruit_droplet_remain)
        fruit_droplet_remain = _sat_sub(fruit_droplet_remain, droplets)

    tiny_droplets: int | None = None
    tiny_droplet_misses: int | None = None
    if in_tiny_droplets is not None:
        tiny_droplets = min(in_tiny_droplets, tiny_droplet_remain)
        tiny_droplet_remain = _sat_sub(tiny_droplet_remain, tiny_droplets)
    if in_tiny_droplet_misses is not None:
        tiny_droplet_misses = min(in_tiny_droplet_misses, tiny_droplet_remain)
        tiny_droplet_remain = _sat_sub(tiny_droplet_remain, tiny_droplet_misses)

    if fruits is None:
        fruits = min(fruit_droplet_remain, n_fruits)
        fruit_droplet_remain = _sat_sub(fruit_droplet_remain, fruits)

    if droplets is None:
        droplets = min(fruit_droplet_remain, n_droplets)
        fruit_droplet_remain = _sat_sub(fruit_droplet_remain, droplets)

    if tiny_droplets is None:
        tiny_droplets = tiny_droplet_remain
        tiny_droplet_remain = 0

    if tiny_droplet_misses is None:
        tiny_droplet_misses = tiny_droplet_remain

    fruits, droplets = _enforce_fruit_droplet_pool(
        fruits, droplets, misses, n_fruits, n_droplets,
    )
    tiny_droplets, tiny_droplet_misses = _enforce_tiny_droplet_pool(
        tiny_droplets, tiny_droplet_misses, n_tiny_droplets,
    )

    return CatchHitResults(
        fruits=fruits,
        droplets=droplets,
        tiny_droplets=tiny_droplets,
        tiny_droplet_misses=tiny_droplet_misses,
        misses=misses,
    )

def _generate_fast(
        n_fruits: int,
        n_droplets: int,
        n_tiny_droplets: int,
        acc: float,
        in_fruits: int | None,
        in_droplets: int | None,
        in_tiny_droplets: int | None,
        in_tiny_droplet_misses: int | None,
        misses: int,
) -> CatchHitResults:
    total_objects = n_fruits + n_droplets + n_tiny_droplets

    if total_objects == 0:
        return CatchHitResults()

    catches_needed = _round_ties_even(acc * float(total_objects))

    max_fruit_droplet_catches = _sat_sub(n_fruits + n_droplets, misses)

    provided_fruits = min(in_fruits, n_fruits) if in_fruits is not None else 0
    provided_droplets = min(in_droplets, n_droplets) if in_droplets is not None else 0
    provided_tiny_droplets = (
        min(in_tiny_droplets, n_tiny_droplets) if in_tiny_droplets is not None else 0
    )
    provided_tiny_droplet_misses = (
        in_tiny_droplet_misses if in_tiny_droplet_misses is not None else 0
    )

    clamped_fruits = min(provided_fruits, max_fruit_droplet_catches)
    clamped_droplets = min(
        provided_droplets, _sat_sub(max_fruit_droplet_catches, clamped_fruits),
    )

    has_f = in_fruits is not None
    has_d = in_droplets is not None
    has_t = in_tiny_droplets is not None
    has_tm = in_tiny_droplet_misses is not None

    if has_f and has_d and has_t and has_tm:
        final_fruits, final_droplets = _enforce_fruit_droplet_pool(
            clamped_fruits, clamped_droplets, misses, n_fruits, n_droplets,
        )
        final_tiny_droplets, final_tiny_droplet_misses = _enforce_tiny_droplet_pool(
            provided_tiny_droplets, provided_tiny_droplet_misses, n_tiny_droplets,
        )
        return CatchHitResults(
            fruits=final_fruits,
            droplets=final_droplets,
            tiny_droplets=final_tiny_droplets,
            tiny_droplet_misses=final_tiny_droplet_misses,
            misses=misses,
        )

    if has_f and has_d and has_t and not has_tm:
        tiny_droplet_misses = _sat_sub(n_tiny_droplets, provided_tiny_droplets)
        return CatchHitResults(
            fruits=clamped_fruits,
            droplets=clamped_droplets,
            tiny_droplets=provided_tiny_droplets,
            tiny_droplet_misses=tiny_droplet_misses,
            misses=misses,
        )

    if has_f and has_d and not has_t and has_tm:
        current_catches = clamped_fruits + clamped_droplets
        remaining_catches = _sat_sub(catches_needed, current_catches)
        tiny_droplets = min(remaining_catches, n_tiny_droplets)
        return CatchHitResults(
            fruits=clamped_fruits,
            droplets=clamped_droplets,
            tiny_droplets=tiny_droplets,
            tiny_droplet_misses=provided_tiny_droplet_misses,
            misses=misses,
        )

    if has_f and not has_d and has_t and has_tm:
        droplets_by_pool = _sat_sub(n_fruits + n_droplets, clamped_fruits + misses)
        droplets = min(droplets_by_pool, n_droplets)
        return CatchHitResults(
            fruits=clamped_fruits,
            droplets=droplets,
            tiny_droplets=provided_tiny_droplets,
            tiny_droplet_misses=provided_tiny_droplet_misses,
            misses=misses,
        )

    if not has_f and has_d and has_t and has_tm:
        fruits_by_pool = _sat_sub(n_fruits + n_droplets, clamped_droplets + misses)
        fruits = min(fruits_by_pool, n_fruits)
        return CatchHitResults(
            fruits=fruits,
            droplets=clamped_droplets,
            tiny_droplets=provided_tiny_droplets,
            tiny_droplet_misses=provided_tiny_droplet_misses,
            misses=misses,
        )

    provided_catches = clamped_fruits + clamped_droplets + provided_tiny_droplets
    remain_catches = _sat_sub(catches_needed, provided_catches)

    if not has_f:
        max_by_pool = _sat_sub(max_fruit_droplet_catches, clamped_droplets)
        max_fruits = min(n_fruits, max_by_pool)
        fruits = min(remain_catches, max_fruits)
        remain_catches = _sat_sub(remain_catches, fruits)
    else:
        fruits = clamped_fruits

    if has_d:
        droplets = clamped_droplets
    elif not has_f:
        max_by_pool = _sat_sub(max_fruit_droplet_catches, fruits)
        max_droplets = min(n_droplets, max_by_pool)
        droplets = min(remain_catches, max_droplets)
        remain_catches = _sat_sub(remain_catches, droplets)
    else:
        droplets_by_pool = _sat_sub(n_fruits + n_droplets, fruits + misses)
        droplets = min(droplets_by_pool, n_droplets)
        remain_catches = _sat_sub(remain_catches, droplets)

    if has_f and not has_d:
        pool_sum = fruits + droplets + misses
        expected = n_fruits + n_droplets
        if pool_sum < expected:
            adjusted = min(n_fruits, fruits + (expected - pool_sum))
            added_catches = adjusted - fruits
            remain_catches = _sat_sub(remain_catches, added_catches)
            fruits = adjusted

    if not has_t:
        tiny_droplets = min(remain_catches, n_tiny_droplets)
    else:
        tiny_droplets = provided_tiny_droplets

    if not has_tm:
        tiny_droplet_misses = _sat_sub(n_tiny_droplets, tiny_droplets)
    else:
        tiny_droplet_misses = provided_tiny_droplet_misses

    return CatchHitResults(
        fruits=fruits,
        droplets=droplets,
        tiny_droplets=tiny_droplets,
        tiny_droplet_misses=tiny_droplet_misses,
        misses=misses,
    )
