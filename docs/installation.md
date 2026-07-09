# Installation

parsecore is published on [PyPI](https://pypi.org/project/parsecore/) and requires
**Python 3.10+**.

## pip

```bash
pip install parsecore
```

## uv

```bash
uv add parsecore
```

## Verify

```python
import parsecore
from parsecore.Performance import Beatmap, Difficulty

attrs = Difficulty().calculate(Beatmap.from_path("map.osu"))
print(attrs.stars)
```

If that prints a star rating, you're ready head to the {doc}`quickstart/pp`.

:::{tip}
After a new osu! pp rework deploys, third-party tools and websites can lag behind for
a while. parsecore tracks the **official in-game algorithm**, so make sure you're on
the latest version to get current values.
:::
