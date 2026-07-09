# Performance points (pp)

Use {class}`~parsecore.Performance.api.Performance` to compute pp. Unset hit counts are
generated automatically from the accuracy and miss count.

## From accuracy

```python
from parsecore.Performance import Beatmap, Performance

bm = Beatmap.from_path("path/to/map.osu")

result = Performance(bm).mods(64).accuracy(98.5).misses(2).calculate()
print(result.pp)
```

## From an explicit lazer score

```python
result = (
    Performance(bm)
    .lazer(True)
    .n300(194).n100(0).n50(0).misses(0)
    .combo(277)
    .slider_end_hits(68)
    .large_tick_hits(15)
    .calculate()
)
print(result.pp, result.pp_aim, result.pp_speed, result.pp_acc, result.pp_reading)
```

## From an osu!(stable) / classic score

Stable scores estimate slider breaks from the legacy total score:

```python
result = (
    Performance(bm)
    .lazer(False)
    .n300(2020).n100(27).misses(4)
    .combo(1699)
    .legacy_total_score(31_546_804)
    .calculate()
)
print(result.pp, result.effective_miss_count)
```

:::{seealso}
The difference between the two scoring systems is explained in
{doc}`../guide/lazer-vs-stable`.
:::
