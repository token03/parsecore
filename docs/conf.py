"""Sphinx configuration for the parsecore documentation."""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(".."))

project = "parsecore"
author = "O!Lib Team"
copyright = f"{datetime.now():%Y}, {author}"

try:
    import tomllib

    with open(os.path.join(os.path.dirname(__file__), "..", "pyproject.toml"), "rb") as fh:
        release = tomllib.load(fh)["tool"]["poetry"]["version"]
except Exception:
    release = "1.0.1"

version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_design",
    "myst_parser",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "locales"]
suppress_warnings = ["sphinx_autodoc_typehints", "myst.header"]

language = "en"
locale_dirs = ["locales/"]
gettext_compact = False
gettext_uuid = True

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": False,
}
autodoc_mock_imports = ["requests"]

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_rtype = True

always_use_bars_union = True
typehints_defaults = "comma"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

html_theme = "furo"
html_title = "parsecore"
html_favicon = "_static/logo.svg"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_show_sphinx = False

# Pycord-style theme: stock Furo palette, Outfit/Saira fonts, blurple accents.
_ACCENT = "#5865f2"
_ACCENT_DARK = "#4752c4"
_ACCENT_SOFT = "#8ea2ff"

html_theme_options = {
    "sidebar_hide_name": False,
    "top_of_page_buttons": ["view", "edit"],
    "source_repository": "https://github.com/O-Lib/parsecore/",
    "source_branch": "main",
    "source_directory": "docs/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/O-Lib/parsecore",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" viewBox="0 0 16 16">'
                '<path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 '
                '5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94'
                '-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 '
                '1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 '
                '0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 '
                '1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92'
                '.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 '
                '1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path></svg>'
            ),
            "class": "",
        },
    ],
    "light_css_variables": {
        "font-stack": "Outfit, sans-serif",
        "color-code-background": "#f0f0f0",
        "color-code-foreground": "black",
        "color-brand-primary": _ACCENT_DARK,
        "color-brand-content": _ACCENT_DARK,
    },
    "dark_css_variables": {
        "font-stack": "Outfit, sans-serif",
        "color-code-background": "#202020",
        "color-code-foreground": "#d0d0d0",
        "color-brand-primary": _ACCENT,
        "color-brand-content": _ACCENT_SOFT,
    },
}

copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True


def _strip_module_license(app, what, name, obj, options, lines):
    if what != "module":
        return

    for i, line in enumerate(lines):
        if line.strip().startswith("MIT License"):
            del lines[i:]
            while lines and not lines[-1].strip():
                lines.pop()
            break


def setup(app):
    app.connect("autodoc-process-docstring", _strip_module_license)
