# Mods API

Model osu! mods as a ruleset-bound set, the classic legacy bitfield, or ruleset-agnostic
(intermode) identities.

## Core types

```{eval-rst}
.. autoclass:: parsecore.Mods.GameMode
   :members:

.. autoclass:: parsecore.Mods.GameModKind
   :members:

.. autoclass:: parsecore.Mods.Acronym
   :members:
```

## Single mod

```{eval-rst}
.. autoclass:: parsecore.Mods.GameMod
   :members:

.. autoclass:: parsecore.Mods.GameModIntermode
   :members:

.. autoclass:: parsecore.Mods.GameModSimple
   :members:

.. autoclass:: parsecore.Mods.SettingSimple
   :members:
```

## Mod collections

```{eval-rst}
.. autoclass:: parsecore.Mods.GameMods
   :members:

.. autoclass:: parsecore.Mods.GameModsIntermode
   :members:

.. autoclass:: parsecore.Mods.GameModsLegacy
   :members:
```

## All concrete mods

Every mod has a concrete, ruleset-specific class. They share the interface of
``_ModBase`` (acronym, description, kind, legacy bit).

```{eval-rst}
.. currentmodule:: parsecore.Mods.generated_mods

.. autosummary::

   EasyOsu
   NoFailOsu
   HalfTimeOsu
   HardRockOsu
   SuddenDeathOsu
   PerfectOsu
   DoubleTimeOsu
   NightcoreOsu
   HiddenOsu
   FlashlightOsu
   RelaxOsu
   AutopilotOsu
   SpunOutOsu
   ClassicOsu
```

:::{tip}
The catch, taiko and mania variants follow the same naming pattern, e.g.
``DoubleTimeCatch``, ``HardRockMania``, ``HiddenTaiko``.
:::
