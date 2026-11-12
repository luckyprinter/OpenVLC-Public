from gui_dev_v3.rx import experiment_store as experiment_store_module


def test_experiment_store_starts_empty_and_persists_user_created_records(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(experiment_store_module, "STORE_DIR", tmp_path)
    monkeypatch.setattr(
        experiment_store_module, "STORE_PATH", tmp_path / "experiments.json"
    )

    assert experiment_store_module.list_experiments() == []
    assert not experiment_store_module.STORE_PATH.exists()

    created = experiment_store_module.create_experiment(
        "Distance validation", "Distance Test", "Initial test"
    )
    assert created.id == 1
    records = experiment_store_module.list_experiments()
    assert len(records) == 1
    assert records[0].name == "Distance validation"
    assert records[0].notes == "Initial test"


def test_experiment_store_does_not_overwrite_corrupt_user_data(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(experiment_store_module, "STORE_DIR", tmp_path)
    store_path = tmp_path / "experiments.json"
    monkeypatch.setattr(experiment_store_module, "STORE_PATH", store_path)
    store_path.write_text("{ invalid json", encoding="utf-8")

    assert experiment_store_module.list_experiments() == []
    assert store_path.read_text(encoding="utf-8") == "{ invalid json"
