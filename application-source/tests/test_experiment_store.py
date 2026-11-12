import pytest

from gui_dev_v3.rx import experiment_store as store


def test_experiment_store_starts_empty_and_persists_user_created_records(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(store, "STORE_PATH", tmp_path / "experiments.json")

    assert store.list_experiments() == []
    assert not store.STORE_PATH.exists()

    created = store.create_experiment(
        "Distance validation", "Distance Test", "Initial test"
    )
    assert created.id == 1
    records = store.list_experiments()
    assert len(records) == 1
    assert records[0].name == "Distance validation"
    assert records[0].notes == "Initial test"


def test_corrupt_experiment_store_is_never_overwritten(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    store_path = tmp_path / "experiments.json"
    monkeypatch.setattr(store, "STORE_PATH", store_path)
    original = "{ invalid json"
    store_path.write_text(original, encoding="utf-8")

    assert store.list_experiments() == []
    with pytest.raises(store.ExperimentStoreError):
        store.create_experiment("New record", "Test", "Must not replace data")
    assert store_path.read_text(encoding="utf-8") == original


def test_malformed_experiment_store_is_never_overwritten(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    store_path = tmp_path / "experiments.json"
    monkeypatch.setattr(store, "STORE_PATH", store_path)
    original = '{"not": "a list"}'
    store_path.write_text(original, encoding="utf-8")

    assert store.list_experiments() == []
    assert store.delete_experiment(1) is False
    assert store_path.read_text(encoding="utf-8") == original

def test_invalid_record_schema_is_not_overwritten(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path)
    store_path = tmp_path / "experiments.json"
    monkeypatch.setattr(store, "STORE_PATH", store_path)
    original = '[{"id": 1, "name": "partial"}]'
    store_path.write_text(original, encoding="utf-8")

    assert store.list_experiments() == []
    with pytest.raises(store.ExperimentStoreError):
        store.create_experiment("New record", "Test", "Must not replace data")
    assert store_path.read_text(encoding="utf-8") == original

def test_legacy_experiment_records_remain_available_and_are_copied_on_save(
    monkeypatch, tmp_path
):
    legacy_path = tmp_path / "legacy" / "experiments.json"
    legacy_path.parent.mkdir()
    original = [{
        "id": 4,
        "name": "Earlier distance test",
        "type": "Distance Test",
        "created_at": "2026-10-01 10:00:00",
        "notes": "Existing user record",
        "record_count": 2,
    }]
    legacy_path.write_text(__import__("json").dumps(original), encoding="utf-8")
    current_path = tmp_path / "app-data" / "experiments.json"
    monkeypatch.setattr(store, "STORE_DIR", current_path.parent)
    monkeypatch.setattr(store, "STORE_PATH", current_path)
    monkeypatch.setattr(store, "LEGACY_STORE_PATH", legacy_path)

    assert store.list_experiments()[0].name == "Earlier distance test"
    created = store.create_experiment("New test", "Distance Test", "")
    assert created.id == 5
    assert current_path.exists()
    assert legacy_path.read_text(encoding="utf-8") == __import__("json").dumps(original)
