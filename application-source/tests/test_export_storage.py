import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from gui_dev_v3.rx import experiment_store, export_page
from gui_dev_v3.widgets import scrollable


OLD_HISTORY = [{"tid": 12, "filename": "before.bin"}]
NEW_HISTORY = [{"tid": 13, "filename": "after.bin"}]
OLD_EXPERIMENTS = [
    {"id": 1, "name": "Before", "type": "Distance", "created_at": "2026-09-01", "notes": ""}
]
NEW_EXPERIMENTS = [
    {"id": 2, "name": "After", "type": "Distance", "created_at": "2026-09-02", "notes": ""}
]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def stores(monkeypatch, tmp_path):
    current = tmp_path / "state"
    legacy = tmp_path / "legacy"
    current.mkdir()
    legacy.mkdir()
    monkeypatch.setattr(export_page, "HISTORY_DIR", current)
    monkeypatch.setattr(export_page, "HISTORY_PATH", current / "transfer_history.json")
    monkeypatch.setattr(export_page, "LEGACY_HISTORY_PATH", legacy / "transfer_history.json")
    monkeypatch.setattr(experiment_store, "STORE_DIR", current)
    monkeypatch.setattr(experiment_store, "STORE_PATH", current / "experiments.json")
    monkeypatch.setattr(experiment_store, "LEGACY_STORE_PATH", legacy / "experiments.json")


@pytest.fixture
def dialogs(monkeypatch, tmp_path):
    backup = tmp_path / "backup.json"
    messages = []
    monkeypatch.setattr(export_page.QFileDialog, "getSaveFileName", lambda *_: (str(backup), ""))
    monkeypatch.setattr(export_page.QFileDialog, "getOpenFileName", lambda *_: (str(backup), ""))
    monkeypatch.setattr(
        export_page.QMessageBox, "question",
        lambda *_: messages.append("confirm") or export_page.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(export_page.QMessageBox, "warning", lambda *_: messages.append("warning"))
    monkeypatch.setattr(export_page.QMessageBox, "information", lambda *_: messages.append("success"))
    return backup, messages


def test_backup_and_restore_preserve_legacy_only_records(qapp, stores, dialogs):
    backup, messages = dialogs
    original_history = json.dumps(OLD_HISTORY)
    original_experiments = json.dumps(OLD_EXPERIMENTS)
    export_page.LEGACY_HISTORY_PATH.write_text(original_history, encoding="utf-8")
    experiment_store.LEGACY_STORE_PATH.write_text(original_experiments, encoding="utf-8")
    page = export_page.ExportPage()

    page._on_backup_db()

    assert json.loads(backup.read_text(encoding="utf-8")) == {
        "history": OLD_HISTORY, "experiments": OLD_EXPERIMENTS
    }
    page._on_restore_db()
    assert json.loads(export_page.HISTORY_PATH.read_text(encoding="utf-8")) == OLD_HISTORY
    assert json.loads(experiment_store.STORE_PATH.read_text(encoding="utf-8")) == OLD_EXPERIMENTS
    assert export_page.LEGACY_HISTORY_PATH.read_text(encoding="utf-8") == original_history
    assert experiment_store.LEGACY_STORE_PATH.read_text(encoding="utf-8") == original_experiments
    assert messages == ["success", "confirm", "success"]
    page.close()


@pytest.mark.parametrize("section", ["history", "experiments"])
def test_backup_refuses_corrupt_sources_and_preserves_destination(qapp, stores, dialogs, section):
    backup, messages = dialogs
    original = b"{ invalid data"
    source = export_page.HISTORY_PATH if section == "history" else experiment_store.STORE_PATH
    source.write_bytes(original)
    backup.write_bytes(b"earlier good backup")
    page = export_page.ExportPage()

    page._on_backup_db()

    assert source.read_bytes() == original
    assert backup.read_bytes() == b"earlier good backup"
    assert messages == ["warning"]
    page.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"history": [{"tid": {}, "filename": "bad.bin"}], "experiments": NEW_EXPERIMENTS},
        {"history": NEW_HISTORY, "experiments": [{"id": 19, "name": "incomplete"}]},
    ],
)
def test_restore_validates_every_section_before_confirming(qapp, stores, dialogs, payload):
    backup, messages = dialogs
    old_history = json.dumps(OLD_HISTORY).encode()
    old_experiments = json.dumps(OLD_EXPERIMENTS).encode()
    export_page.HISTORY_PATH.write_bytes(old_history)
    experiment_store.STORE_PATH.write_bytes(old_experiments)
    backup.write_text(json.dumps(payload), encoding="utf-8")
    page = export_page.ExportPage()

    page._on_restore_db()

    assert export_page.HISTORY_PATH.read_bytes() == old_history
    assert experiment_store.STORE_PATH.read_bytes() == old_experiments
    assert page._history_data == OLD_HISTORY
    assert messages == ["warning"]
    page.close()


def test_failed_second_restore_write_rolls_back_first_and_preserves_ui(
    qapp, stores, dialogs, monkeypatch
):
    backup, messages = dialogs
    old_history = json.dumps(OLD_HISTORY).encode()
    old_experiments = json.dumps(OLD_EXPERIMENTS).encode()
    export_page.HISTORY_PATH.write_bytes(old_history)
    experiment_store.STORE_PATH.write_bytes(old_experiments)
    backup.write_text(json.dumps({"history": NEW_HISTORY, "experiments": NEW_EXPERIMENTS}))
    page = export_page.ExportPage()

    real_replace = os.replace
    real_write_text = Path.write_text

    def replace(source, target, *args, **kwargs):
        if Path(target) == experiment_store.STORE_PATH:
            raise OSError("simulated second write failure")
        return real_replace(source, target, *args, **kwargs)

    def write_text(path, *args, **kwargs):
        if path == experiment_store.STORE_PATH:
            raise OSError("simulated second write failure")
        return real_write_text(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "write_text", write_text)
    page._on_restore_db()

    assert export_page.HISTORY_PATH.read_bytes() == old_history
    assert experiment_store.STORE_PATH.read_bytes() == old_experiments
    assert page._history_data == OLD_HISTORY
    assert messages == ["confirm", "warning"]
    page.close()


def test_restore_retains_original_bytes_for_explicit_recovery(qapp, stores, dialogs):
    backup, messages = dialogs
    original = b"{ damaged history to recover"
    export_page.HISTORY_PATH.write_bytes(original)
    backup.write_text(json.dumps({"history": NEW_HISTORY}), encoding="utf-8")
    page = export_page.ExportPage()

    page._on_restore_db()

    assert json.loads(export_page.HISTORY_PATH.read_text(encoding="utf-8")) == NEW_HISTORY
    assert any(path.read_bytes() == original for path in export_page.HISTORY_PATH.parent.glob("*.bak"))
    assert page._history_data == NEW_HISTORY
    assert messages == ["confirm", "success"]
    page.close()


def test_compact_history_table_and_actions_do_not_overlap(qapp, stores):
    page = export_page.ExportPage()
    area = scrollable(page)
    area.resize(568, 354)
    area.show()
    qapp.processEvents()

    table = page.table
    action = page.open_file_btn
    assert table.mapTo(page, table.rect().bottomLeft()).y() < action.mapTo(page, QPoint()).y()
    assert table.mapTo(area.viewport(), table.rect().topLeft()).y() < area.viewport().height()

    scrollbar = area.verticalScrollBar()
    maximum = scrollbar.maximum()
    for control in (page.open_file_btn, page.save_as_btn, page.backup_btn, page.restore_btn, page.csv_btn):
        scrollbar.setValue(0)
        y = control.mapTo(area.viewport(), QPoint()).y()
        scrollbar.setValue(min(y, maximum))
        assert area.viewport().rect().contains(control.mapTo(area.viewport(), QPoint()))
        assert area.viewport().rect().contains(control.mapTo(area.viewport(), control.rect().bottomRight()))
    area.close()


def test_sorted_history_selects_the_file_shown_in_the_row(qapp, stores):
    export_page.HISTORY_PATH.write_text(json.dumps(NEW_HISTORY + OLD_HISTORY), encoding="utf-8")
    page = export_page.ExportPage()
    page.table.sortItems(0, Qt.SortOrder.AscendingOrder)
    page.table.selectRow(0)

    assert page.table.item(0, 1).text() == "before.bin"
    assert page._get_selected_entry()["filename"] == "before.bin"
    page.close()


def test_terminal_history_distinguishes_reused_tid_and_updates_exact_comparison(
    qapp, stores, monkeypatch
):
    from types import SimpleNamespace

    from gui_dev_v3.models import TransferStatus

    def finished(capture_id, filename):
        return SimpleNamespace(
            tid=44, capture_id=capture_id, filename=filename, status=TransferStatus.COMPLETE,
            time_label="10:00:00", size_bytes=8, total_chunks=1, received_chunks=1,
        )

    first = finished("a" * 32, "first.bin")
    second = finished("b" * 32, "second.bin")
    state = SimpleNamespace(
        mode="physical", transfer=second, completed_physical_transfers=(first, second),
        get_method2_comparison=lambda: {"strict_ber": 0.125},
    )
    page = export_page.ExportPage()
    page.refresh(state)

    disk_rows = json.loads(export_page.HISTORY_PATH.read_text(encoding="utf-8"))
    assert [(row["filename"], row["ber"]) for row in disk_rows] == [
        ("second.bin", 0.125), ("first.bin", "N/A"),
    ]
    queries = []
    monkeypatch.setattr(
        export_page, "load_session_capture",
        lambda tid, *, capture_id=None: queries.append((tid, capture_id)),
    )
    first_row = next(
        row for row in range(page.table.rowCount()) if page.table.item(row, 1).text() == "first.bin"
    )
    page.table.selectRow(first_row)
    assert queries == [(44, first.capture_id)]
    page.close()


def test_rx_poll_records_terminal_reception_with_inspect_page_hidden(qapp, stores, monkeypatch):
    from types import SimpleNamespace

    from gui_dev_v3.app_state import RXAppState
    from gui_dev_v3.data.records import empty_transfer
    from gui_dev_v3.models import TransferStatus
    from gui_dev_v3.rx.shell import RXShell

    transfer = SimpleNamespace(
        tid=23, capture_id="c" * 32, filename="while-on-dashboard.bin",
        status=TransferStatus.COMPLETE, time_label="10:00:00", size_bytes=8,
        total_chunks=1, received_chunks=1,
    )
    state = RXAppState()
    state.transfer = empty_transfer()
    shell = RXShell(state)
    shell._timer.stop()

    def snapshot():
        state.completed_physical_transfers = (transfer,)

    monkeypatch.setattr(state, "refresh", snapshot)
    assert shell.pages.currentIndex() == 0

    shell._on_poll_timer()

    [row] = json.loads(export_page.HISTORY_PATH.read_text(encoding="utf-8"))
    assert row["capture_id"] == transfer.capture_id
    assert row["filename"] == transfer.filename
    shell.cleanup()
    shell.close()


def test_experiments_table_updates_after_restore_commits(qapp, stores, dialogs):
    from gui_dev_v3.rx.study_data_page import StudyDataPage

    backup, _ = dialogs
    experiment_store.STORE_PATH.write_text(json.dumps(OLD_EXPERIMENTS), encoding="utf-8")
    backup.write_text(json.dumps({"experiments": NEW_EXPERIMENTS}), encoding="utf-8")
    page = StudyDataPage()
    assert page.experiments_page._table.item(0, 1).text() == "Before"

    page.export_page._on_restore_db()

    assert page.experiments_page._table.item(0, 1).text() == "After"
    page.close()


@pytest.mark.parametrize("had_history", [True, False])
def test_interrupted_restore_rolls_back_before_another_reader(qapp, stores, had_history):
    old_experiments = json.dumps(OLD_EXPERIMENTS).encode()
    experiment_store.STORE_PATH.write_bytes(old_experiments)
    if had_history:
        old_history = json.dumps(OLD_HISTORY).encode()
        export_page.HISTORY_PATH.write_bytes(old_history)

    subprocess_restore = """
import json
import os
import sys
from pathlib import Path

from gui_dev_v3.rx.receiver_storage import lock_state, restore_json

history, experiments = map(Path, sys.argv[1:3])
real_replace = os.replace

def interrupt_after_history(source, target):
    real_replace(source, target)
    if target == history:
        os._exit(91)

os.replace = interrupt_after_history
with lock_state(history.parent):
    restore_json({history: json.loads(sys.argv[3]), experiments: json.loads(sys.argv[4])})
"""
    result = subprocess.run(
        [
            sys.executable, "-c", subprocess_restore,
            str(export_page.HISTORY_PATH), str(experiment_store.STORE_PATH),
            json.dumps(NEW_HISTORY), json.dumps(NEW_EXPERIMENTS),
        ],
        check=False,
        timeout=10,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 91, result.stderr

    # Use the Experiments reader first to prove recovery is shared, rather than
    # relying on opening the Export page to repair its own history file.
    assert experiment_store.list_experiments()[0].name == "Before"
    assert experiment_store.STORE_PATH.read_bytes() == old_experiments
    assert export_page.HISTORY_PATH.exists() == had_history
    if had_history:
        assert export_page.HISTORY_PATH.read_bytes() == old_history


def test_in_progress_physical_reception_enters_history_only_when_terminal(qapp, stores):
    from types import SimpleNamespace

    from gui_dev_v3.models import TransferStatus

    current = SimpleNamespace(
        tid=9, capture_id="d" * 32, filename="stream.bin", status=TransferStatus.INCOMPLETE,
        time_label="10:00:00", size_bytes=8, total_chunks=2, received_chunks=1,
    )
    state = SimpleNamespace(
        mode="physical", transfer=current, completed_physical_transfers=(),
        get_method2_comparison=lambda: None,
    )
    page = export_page.ExportPage()

    page.refresh(state)
    assert not export_page.HISTORY_PATH.exists()

    current.status = TransferStatus.COMPLETE
    current.received_chunks = 2
    state.completed_physical_transfers = (current,)
    page.refresh(state)

    [row] = json.loads(export_page.HISTORY_PATH.read_text(encoding="utf-8"))
    assert row["status"] == "Complete"
    assert row["received_chunks"] == 2
    page.close()


def test_export_recalculates_scroll_minimum_when_rotating_splitter(qapp, stores):
    from gui_dev_v3.app import VLCMainWindow

    window = VLCMainWindow()
    window.show()
    window.launch_mode("rx")
    shell = window._rx_shell
    shell._timer.stop()
    study = shell._page_widgets["study_data"]
    page = study.export_page

    window.resize(1366, 768)
    shell.nav.setCurrentRow(5)
    study.tabs.setCurrentIndex(2)
    qapp.processEvents()
    assert page.splitter.orientation() == Qt.Orientation.Horizontal

    study.tabs.setCurrentIndex(0)
    shell.nav.setCurrentRow(6)
    window.resize(1280, 720)
    qapp.processEvents()
    shell.nav.setCurrentRow(5)
    study.tabs.setCurrentIndex(2)
    qapp.processEvents()

    assert page.splitter.orientation() == Qt.Orientation.Vertical
    table_end = page.table.mapTo(page, page.table.rect().bottomLeft()).y()
    actions_start = page.open_file_btn.mapTo(page, QPoint()).y()
    assert table_end < actions_start
    assert page.open_file_btn.height() >= page.open_file_btn.minimumSizeHint().height()
    assert study.tabs.currentWidget().verticalScrollBar().maximum() > 0
    window.return_to_launcher()
    window.close()


def test_terminal_history_retries_after_temporary_write_failure(qapp, stores, monkeypatch):
    from types import SimpleNamespace

    from gui_dev_v3.models import TransferStatus

    transfer = SimpleNamespace(
        tid=23, capture_id="e" * 32, filename="queued-for-retry.bin",
        status=TransferStatus.COMPLETE, time_label="10:00:00", size_bytes=8,
        total_chunks=1, received_chunks=1,
    )
    state = SimpleNamespace(
        mode="physical", transfer=transfer, completed_physical_transfers=(transfer,),
        get_method2_comparison=lambda: None,
    )
    page = export_page.ExportPage()
    original_replace = os.replace

    def fail_history_write(source, destination):
        if destination == export_page.HISTORY_PATH:
            raise OSError("simulated temporary filesystem failure")
        return original_replace(source, destination)

    with monkeypatch.context() as filesystem:
        filesystem.setattr(os, "replace", fail_history_write)
        page.refresh(state)

    assert not export_page.HISTORY_PATH.exists()
    assert page.table.rowCount() == 0
    state.completed_physical_transfers = ()
    page.refresh(state)

    [row] = json.loads(export_page.HISTORY_PATH.read_text(encoding="utf-8"))
    assert row["capture_id"] == transfer.capture_id
    assert page.table.rowCount() == 1
    page.close()
