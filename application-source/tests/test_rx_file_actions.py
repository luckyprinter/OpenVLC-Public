from pathlib import Path

from gui_dev_v3.rx import export_page as export_page_module


def test_save_as_copies_original_received_bytes(qapp, monkeypatch, tmp_path):
    source = tmp_path / "received.bin"
    destination = tmp_path / "exported.bin"
    payload = bytes(range(256)) + b"\\x00\\xffOpenVLC"
    source.write_bytes(payload)

    page = export_page_module.ExportPage()
    monkeypatch.setattr(
        page, "_get_selected_entry",
        lambda: {
            "filename": "received.bin",
            "tid": 17,
            "received_path": str(source),
        },
    )
    monkeypatch.setattr(
        export_page_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "All Files (*)"),
    )
    monkeypatch.setattr(
        export_page_module.QMessageBox,
        "information",
        lambda *_args, **_kwargs: export_page_module.QMessageBox.StandardButton.Ok,
    )

    page._on_save_as()

    assert destination.read_bytes() == payload
    page.close()


def test_open_file_uses_the_received_payload_path(qapp, monkeypatch, tmp_path):
    source = tmp_path / "received.dat"
    source.write_bytes(b"actual payload")
    opened = []

    page = export_page_module.ExportPage()
    monkeypatch.setattr(
        page, "_get_selected_entry",
        lambda: {"received_path": str(source)},
    )
    monkeypatch.setattr(
        export_page_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    page._on_open_file()

    assert opened == [str(source.resolve())]
    page.close()


def test_file_actions_refuse_missing_payload_instead_of_fabricating_data(
    qapp, monkeypatch, tmp_path
):
    destination = tmp_path / "must-not-be-created.bin"
    warnings = []

    page = export_page_module.ExportPage()
    monkeypatch.setattr(
        page, "_get_selected_entry",
        lambda: {
            "filename": "missing.bin",
            "received_path": str(tmp_path / "missing.bin"),
        },
    )
    monkeypatch.setattr(
        export_page_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "All Files (*)"),
    )
    monkeypatch.setattr(
        export_page_module.QMessageBox,
        "warning",
        lambda *_args, **_kwargs: warnings.append(_args[1]),
    )

    page._on_save_as()

    assert not destination.exists()
    assert warnings == ["Received File Unavailable"]
    page.close()
