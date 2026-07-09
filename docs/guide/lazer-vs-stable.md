# Lazer vs stable scoring

osu! has two scoring systems, and pp is computed slightly differently for each. parsecore
supports both via {meth}`~parsecore.Performance.api.Performance.lazer`.

## osu!lazer

Lazer scores carry richer statistics slider **tail hits** and **large ticks** are judged
individually. Provide them for the most accurate result:

```python
result = (
    Performance(bm)
    .lazer(True)
    .n300(194).n100(0).n50(0).misses(0)
    .combo(277)
    .slider_end_hits(68)   # slider tails hit
    .large_tick_hits(15)   # large slider ticks hit
    .calculate()
)
```

## osu!(stable) / classic

Stable scores don't expose slider-tail or large-tick judgements, so misses and slider
breaks are **estimated**. Passing the legacy total score enables the score-based miss
estimator (without it, top plays can be off by a couple of percent):

```python
result = (
    Performance(bm)
    .lazer(False)
    .n300(2020).n100(27).misses(4)
    .combo(1699)
    .legacy_total_score(31_546_804)
    .calculate()
)
```

## Which should I use?

Use whichever matches the score you're evaluating. The osu! API tells you which client a
score came from; feed lazer statistics for lazer scores and the legacy total score for
stable scores.
