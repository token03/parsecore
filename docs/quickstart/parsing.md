# Beatmap parsing

Parse any `.osu` file into a fully typed {class}`~parsecore.Beatmap.beatmap.Beatmap`.

```python
from parsecore.Beatmap import Beatmap

beatmap = Beatmap.from_path("path/to/map.osu")

print(beatmap.metadata.title)
print(beatmap.metadata.version)      # difficulty name
print(beatmap.difficulty.approach_rate)
print(beatmap.difficulty.circle_size)

for obj in beatmap.hit_objects.hit_objects:
    print(obj)

for tp in beatmap.timing_points.control_points.timing_points:
    print(tp.time, 60000 / tp.beat_len)  # start time, BPM
```

Every section is parsed: **General**, **Metadata**, **Difficulty**, **Events**,
**Timing Points**, **Hit Objects**, **Colours** and **Editor**. Slider paths are
sampled exactly like osu!-stable (bezier, catmull and perfect-circle segments), so
distances and tick placement match the game.

## Re-encoding

A parsed beatmap can be written back out to `.osu` text:

```python
text = beatmap.encode_to_string()
beatmap.encode_to_path("out.osu")
```

See the {doc}`../api/beatmap` reference for every field.
