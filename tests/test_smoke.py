"""Smoke-Test: Verifiziert, dass das Paket importierbar ist."""


def test_paket_importierbar():
    import pa_analyzer

    assert pa_analyzer is not None
