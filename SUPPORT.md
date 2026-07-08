<div align="center">

# Support

**Stuck? Here's how to get help fastest route first.**

</div>

---

### Community (Discord) fastest

Join us for questions, discussions, and general help:

→ **[discord.gg/9p7whE7QxQ](https://discord.gg/9p7whE7QxQ)**

### Bug Reports & Feature Requests

Open an issue on GitHub: **[github.com/O-Lib/parsecore/issues](https://github.com/O-Lib/parsecore/issues)**

Please search existing issues before opening a new one.

### Email

| Address | Use for |
| --- | --- |
| [support@olib.dev](mailto:support@olib.dev) | General inquiries |
| [security@olib.dev](mailto:security@olib.dev) | Security vulnerabilities only see [SECURITY.md](SECURITY.md) |

### Response Times

| Channel | Expected Response |
| --- | --- |
| Discord | Within 24 hours |
| GitHub Issues | Within 3-5 business days |
| Email (support) | Within 3–5 business days |
| Email (security) | Within 48 hours |

---

### Before Asking

1. Read the [README](README.md) the quick-start sections cover the most common questions
2. Search existing issues
3. Update to the latest version pp/star rating reworks are ported quickly, old versions compute old values
4. Create a minimal reproducible example

### What to Include

- parsecore version (`pip show parsecore`)
- Python version (`python --version`)
- OS and architecture
- The `.osu` file (or beatmap ID), mods, and score statistics used
- Minimal code that reproduces the issue
- Full error traceback

### "My pp values don't match XY!"

The most common question. Checklist before reporting:

1. **Compare against the game, not other calculators.** After an official pp rework, third-party tools and bots often lag behind for weeks. ParseCore tracks the official algorithm currently the **2026 Q2 rework** (`2026.702.1`).
2. The osu! website itself recalculates millions of maps and billions of scores after a rework during that window it can display pre-rework values.
3. Make sure you pass the right score type: `lazer(True)` with slider statistics for lazer scores, `lazer(False)` (+ `legacy_total_score` if available) for stable scores.

If values still differ from the game itself, that's a bug please report it with the map and score details!

### Out of Scope

- Custom forks or heavily modified versions of parsecore
- Help with cheating, score manipulation, or private-server score submission

<p align="center">
	<img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/footers/gray0_ctp_on_line.svg?sanitize=true" />
</p>

<p align="center">
        <code>&copy 2026-Present <a href="https://github.com/O-Lib">O!Lib Team</a></code>
</p>
