"""Tests for shared TX/RX presentation primitives."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui_dev_v3.ui_foundation import (
    PageIntro,
    SidebarNavigationList,
    WorkspaceHeader,
    add_navigation_item,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_page_intro_exposes_consistent_text_hierarchy(qapp: QApplication) -> None:
    intro = PageIntro(
        "TRANSMITTER / CONTROL ROOM",
        "Prepare an optical transfer",
        "Choose a file, review the link state, then start transmission.",
    )

    assert intro.objectName() == "PageIntro"
    assert intro.eyebrow_label.text() == "TRANSMITTER / CONTROL ROOM"
    assert intro.title_label.text() == "Prepare an optical transfer"
    assert intro.description_label.text().startswith("Choose a file")
    assert intro.title_label.wordWrap()
    assert intro.description_label.wordWrap()
    assert intro.accessibleName() == "Prepare an optical transfer"
    assert intro.accessibleDescription().startswith("Choose a file")


def test_page_intro_keeps_labels_expandable_at_narrow_width(qapp: QApplication) -> None:
    intro = PageIntro(
        "RECEIVER / MONITORING",
        "Reception overview",
        "Track link quality, signal levels, file progress, and decoder state.",
    )
    intro.resize(220, 120)
    intro.show()
    qapp.processEvents()

    assert intro.title_label.width() > 0
    assert intro.description_label.width() > 0
    assert intro.title_label.wordWrap()
    assert intro.description_label.wordWrap()

    intro.close()


def test_sidebar_navigation_is_keyboard_accessible(qapp: QApplication) -> None:
    navigation = SidebarNavigationList("Receiver")
    item = add_navigation_item(navigation, QIcon(), "Signal")

    assert navigation.accessibleName() == "Receiver navigation"
    assert navigation.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert navigation.selectionMode() == navigation.SelectionMode.SingleSelection
    assert item.data(Qt.ItemDataRole.AccessibleTextRole) == "Signal"
    assert item.data(Qt.ItemDataRole.AccessibleDescriptionRole) == "Open Signal."
    assert item.toolTip() == "Signal"

    navigation.close()


def test_workspace_header_collapses_supplemental_label_on_narrow_width(
    qapp: QApplication,
) -> None:
    header = WorkspaceHeader("RECEIVER WORKSPACE")
    header.resize(420, 52)
    header.show()
    qapp.processEvents()

    assert header.page_heading.text() == "Dashboard"
    assert not header.workspace_label.isVisible()

    header.resize(640, 52)
    qapp.processEvents()
    assert header.workspace_label.isVisible()

    header.close()
