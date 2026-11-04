import pytest

from jarvis import voice


def test_clean_removes_markdown_and_links():
    spoken = voice.clean("**Listo**: abrí `https://youtube.com/watch?v=1` en _Chrome_.")
    assert spoken == "Listo: abrí el enlace en Chrome."


def test_clean_limits_length():
    assert len(voice.clean("a " * 5000)) == voice.MAX_CHARS


def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        voice.synthesize("** __ ``")
