<div align="center">

# Security Policy

**Found a vulnerability? Thank you for telling us privately first.**

</div>

---

### Supported Versions

| Version | Supported |
| --- | --- |
| Latest stable release | ✅ Yes |
| Older versions | ❌ No please update first |

---

### Reporting a Vulnerability

> **⚠️ Do not open a public GitHub issue for security vulnerabilities.**

Send a report to **[security@olib.dev](mailto:security@olib.dev)** with the subject line:

```
[parsecore] Security Vulnerability Report
```

Please include:

- Affected version(s) (`pip show parsecore`)
- Steps to reproduce for parser issues, attach the crafted `.osu` file
- Potential impact (crash, resource exhaustion, code execution, ...)
- Suggested fix, if you have one

### What counts as a security issue here?

ParseCore parses untrusted `.osu` files bots and websites feed it user-supplied maps. Typical security-relevant reports:

- Crafted beatmap files causing crashes, hangs, or unbounded memory/CPU usage (decompression bombs, pathological object counts, malformed sections)
- Anything that could lead to code execution from file contents
- Denial-of-service vectors in the calculation pipeline

---

### Response Timeline

| Step | Timeframe |
| --- | --- |
| Initial acknowledgment | Within 48 hours |
| Assessment | Within 5 business days |
| Fix released | Within 14 business days (severity-dependent) |

---

### Disclosure Policy

We follow **responsible disclosure**. Once a fix is publicly available, a GitHub Security Advisory will be published. Reporters who wish to be credited will be named in the release notes.

<p align="center">
	<img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/footers/gray0_ctp_on_line.svg?sanitize=true" />
</p>

<p align="center">
        <code>&copy 2026-Present <a href="https://github.com/O-Lib">O!Lib Team</a></code>
</p>
