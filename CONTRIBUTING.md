<div align="center">

# Contributing to ParseCore

**Thank you for taking the time to contribute!** These guidelines keep the codebase consistent, the results bit-exact, and review cycles short.

</div>

---

### Table of Contents

- [Code of Conduct](#code-of-conduct)
- [The Golden Rule: Bit-Exactness](#the-golden-rule-bit-exactness)
- [What We Accept](#what-we-accept)
- [What We Do Not Accept](#what-we-do-not-accept)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Commit Guidelines](#commit-guidelines)
- [Review Process](#review-process)

---

### Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold it.

Report unacceptable behavior to **[conduct@olib.dev](mailto:conduct@olib.dev)**.

---

### The Golden Rule: Bit-Exactness

ParseCore's star ratings and pp values are **bit-for-bit identical** to the official osu! implementation. This is the project's core promise, and every contribution must preserve it.

What this means in practice:

- **Never "simplify" float math.** Seemingly harmless rewrites break parity:
  - `x * x * x` is **not** the same as `x ** 3` or `math.pow(x, 3)` the reference uses explicit multiplication for small integer exponents
  - f32 intermediate values (`f32(...)` helpers) are intentional, not accidental osu! computes positions and several constants in 32-bit floats
  - `ieee_div`, `rust_min`, `rust_max`, `ieee_pow` etc. replicate Rust/C# semantics where Python would raise or return different values (division by zero, NaN handling, negative bases)
- **RNG call order is sacred.** The legacy converters consume the osu!stable RNG in an exact order; reordering two calls silently corrupts every subsequent value.
- **Match the reference, not your intuition.** When porting from `ppy/osu` (C#) or rosu-pp (Rust), reproduce the exact operations, including "bugs" that are part of the live algorithm (integer truncations, banker's rounding, unstable sorts).

Any PR touching `parsecore/Performance/` must state which reference code it mirrors and show that the parity suite still passes with **zero differences**.

---

### What We Accept

| Type | Description |
| --- | --- |
| Bug fixes | Incorrect behavior, crashes, unexpected results, parity deviations |
| Algorithm updates | Ports of new official pp/star rating deploys (with parity proof) |
| Documentation | Typos, clarifications, examples |
| Performance improvements | Faster parsing/calculation as long as results stay bit-identical |
| New features | Additional functionality aligned with the osu! spec |
| Tests | Additional parity cases, edge cases, pathological maps |
| Tooling | Better developer experience, CI/CD improvements |

---

### What We Do Not Accept

- Changes that break bit-exactness, even by 1 ULP
- Breaking API changes without prior discussion (open an issue first)
- Changes that only benefit a narrow niche use case
- Code that degrades performance without clear justification
- Unnecessary new dependencies (the core library is dependency-free by design)
- Anything that facilitates cheating or score manipulation

---

### Getting Started

### Reporting Bugs

Before submitting:

1. **Check the latest version** your issue may already be fixed
2. **Search existing issues** someone may have reported it already
3. **Reproduce in a clean environment**

A good bug report includes:

- What you expected vs. what actually happened
- A minimal code snippet **and the `.osu` file (or beatmap ID)** that reproduces the issue
- The mods, score statistics, and lazer/stable flag used
- parsecore version, Python version, and OS
- Full error traceback if applicable

> 💡 For "wrong pp/star rating" reports: please compare against **the current in-game values**, not third-party calculators those often lag behind official reworks.

### Suggesting Features

- Check if the feature already exists
- Describe the problem it solves, not just the solution
- Include a **problem statement**, a **proposed API** (code example), and **alternatives considered**

### Submitting Pull Requests

1. Open an issue first for non-trivial changes
2. Fork and create a branch from `main`
3. Write code following the standards below
4. Add or update parity/regression tests
5. Update the README if you add user-facing features
6. Ensure pre-commit passes: `pre-commit run --all-files`
7. Open a PR drafts are welcome for early feedback

---

### Development Setup

### Prerequisites

- Python 3.10+ (3.12 recommended)
- [`uv`](https://github.com/astral-sh/uv) or `pip` + `venv`

### Install

```bash
git clone https://github.com/O-Lib/parsecore.git
cd parsecore

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
# or
uv pip install -e ".[dev]"
```

### Verify

```bash
pytest
mypy parsecore/
ruff check parsecore/
```

### Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

---

### Coding Standards

We follow **PEP 8** with these additions:

| Rule | Standard |
| --- | --- |
| Line length | 88 characters |
| Indentation | 4 spaces |
| Imports | Grouped: stdlib → third-party → local |
| Naming | `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants |

### Type Hints

All public functions and methods must have full type annotations:

```python
def calculate(self, beatmap: Beatmap) -> OsuDifficultyAttributes: ...
```

### Comments & Docstrings

Every module, class, function and method carries a **Google-style docstring**
(summary line plus `Args:`/`Returns:`/`Raises:` where they add information). New
or changed public APIs must be documented this way, and internal helpers get at
least a concise summary. Module docstrings begin with a one-line summary above
the license header.

Inline `#` comments, on the other hand, are **discouraged**: the parity-sensitive
math is meant to read like the reference it mirrors, so put the "why" where it
belongs instead:

- **docstrings** for what a function does and how to call it,
- the **README** for user-facing behavior,
- the **PR description** for implementation reasoning (including which reference code a formula mirrors),
- **commit messages** for the "why" of a change.

When you need to explain a non-obvious parity detail (an f32 cast, an IEEE
division, a legacy sort), a short note in the docstring is preferred over an
inline comment.

---

### Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`

**Scopes:** `beatmap`, `mods`, `pp`, `ci`, `packaging`

**Examples:**

```
feat(pp): port the 2026 Q2 Reading skill for osu!
fix(pp): insert scroll-speed effect points in taiko converts
fix(beatmap): parse slider edgeSounds (field 8)
docs(readme): document the Performance quick start
chore(ci): pin ruff to 0.9.10
```

---

### Review Process

| Step | Timeline |
| --- | --- |
| First review | Within 5 business days |
| Follow-up reviews | Within 2–3 business days |
| Merge after approval | Within 24 hours |

Reviewers check: **parity (bit-exactness)**, correctness, types, tests, performance, and style.

<p align="center">
	<img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/footers/gray0_ctp_on_line.svg?sanitize=true" />
</p>

<p align="center">
        <code>&copy 2026-Present <a href="https://github.com/O-Lib">O!Lib Team</a></code>
</p>
