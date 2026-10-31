# SPDX-License-Identifier: GPL-3.0-or-later
"""Every word of the extension in Spanish and the nine languages Sparky
Stereo OS requires, with the same placeholders as the English."""
import re

from stereo_view.strings import LANGUAGES, _TABLE, tr


def test_every_string_in_every_language():
    missing = [(text, lang) for text, row in _TABLE.items()
               for lang in LANGUAGES if lang != "en" and not row.get(lang)]
    assert not missing


def test_placeholders_kept():
    for text, row in _TABLE.items():
        want = sorted(re.findall(r"\{(\w+)\}", text))
        for lang, out in row.items():
            assert sorted(re.findall(r"\{(\w+)\}", out)) == want, (text, lang)


def test_fallback_is_english():
    assert tr("Enable 3D", "xx") == "Enable 3D"
    assert tr("Stereo 3D is not available here: {reason}", "es", reason="r").endswith(": r")
