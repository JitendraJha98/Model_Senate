from backend.calibration import DEFAULT_GRADE_PROB, calibrated_probability, load_calibration_map


def test_calibrated_probability_none_grade():
    assert calibrated_probability(None) is None


def test_calibrated_probability_uses_provided_map():
    assert calibrated_probability("A", {"A": 0.83}) == 0.83


def test_calibrated_probability_unknown_grade_is_none():
    assert calibrated_probability("Z", {}) is None


def test_calibrated_probability_defaults():
    assert calibrated_probability("B", DEFAULT_GRADE_PROB) == 0.75


def test_load_calibration_map_falls_back_when_missing(monkeypatch, tmp_path):
    import backend.calibration as c

    monkeypatch.setattr(c, "_CALIBRATION_PATH", tmp_path / "nope.json")
    assert load_calibration_map() == DEFAULT_GRADE_PROB


def test_load_calibration_backfills_unobserved_grades(monkeypatch, tmp_path):
    import backend.calibration as c

    path = tmp_path / "cal.json"
    path.write_text('{"A": 0.95}', encoding="utf-8")
    monkeypatch.setattr(c, "_CALIBRATION_PATH", path)
    fitted = load_calibration_map()
    assert fitted["A"] == 0.95  # fitted value wins
    assert fitted["B"] == 0.75  # unobserved grade backfilled from defaults
