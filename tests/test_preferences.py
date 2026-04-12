"""Tests for ``app_state.preferences``."""

from meshlite.app_state.preferences import Preferences


def test_defaults_roundtrip():
    """Serializing and deserializing defaults produces identical prefs."""
    original = Preferences()
    restored = Preferences.from_json(original.to_json())
    assert restored.rotate_sensitivity == original.rotate_sensitivity
    assert restored.fov_deg == original.fov_deg
    assert restored.background_color == original.background_color
    assert restored.mesh_color == original.mesh_color
    assert restored.undo_max_depth == original.undo_max_depth
    assert restored.recent_files == original.recent_files


def test_unknown_keys_ignored():
    """Extra keys in JSON don't cause an error."""
    import json
    raw = json.dumps({"fov_deg": 60.0, "nonexistent_key": True})
    prefs = Preferences.from_json(raw)
    assert prefs.fov_deg == 60.0
    assert not hasattr(prefs, "nonexistent_key") or "nonexistent_key" not in prefs.__dict__


def test_missing_keys_filled_from_defaults():
    """Missing keys in JSON are filled from defaults."""
    import json
    raw = json.dumps({"fov_deg": 90.0})
    prefs = Preferences.from_json(raw)
    assert prefs.fov_deg == 90.0
    assert prefs.rotate_sensitivity == Preferences().rotate_sensitivity


def test_clamping():
    """Out-of-range values are clamped to sensible bounds."""
    import json
    raw = json.dumps({
        "fov_deg": 999.0,
        "rotate_sensitivity": -5.0,
        "undo_max_depth": 0,
        "ambient_strength": 50.0,
    })
    prefs = Preferences.from_json(raw)
    assert prefs.fov_deg == 120.0
    assert prefs.rotate_sensitivity == 0.0001
    assert prefs.undo_max_depth == 1
    assert prefs.ambient_strength == 1.0


def test_invalid_json_returns_defaults():
    """Malformed JSON returns defaults instead of crashing."""
    prefs = Preferences.from_json("not valid json{{{")
    assert prefs == Preferences()


def test_recent_files_add_and_deduplicate():
    """add_recent_file puts the path first and deduplicates."""
    prefs = Preferences()
    prefs.add_recent_file("/a.stl")
    prefs.add_recent_file("/b.stl")
    prefs.add_recent_file("/a.stl")  # Should move to front, not duplicate.
    assert prefs.recent_files == ["/a.stl", "/b.stl"]


def test_recent_files_capped():
    """Recent files list is capped at RECENT_FILES_MAX."""
    from meshlite.app_state.preferences import RECENT_FILES_MAX
    prefs = Preferences()
    for i in range(20):
        prefs.add_recent_file(f"/mesh_{i}.stl")
    assert len(prefs.recent_files) == RECENT_FILES_MAX
    assert prefs.recent_files[0] == "/mesh_19.stl"


def test_tuple_colors_survive_roundtrip():
    """Color tuples survive JSON serialization (lists → tuples)."""
    prefs = Preferences(mesh_color=(0.1, 0.2, 0.3))
    restored = Preferences.from_json(prefs.to_json())
    assert isinstance(restored.mesh_color, tuple)
    assert restored.mesh_color == (0.1, 0.2, 0.3)
