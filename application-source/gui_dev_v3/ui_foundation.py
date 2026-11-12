"""Shared presentation primitives for the TX and RX workspaces.

This module contains UI-only building blocks. It deliberately has no access to
application state, serial controllers, hardware backends, or firmware commands.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class PageIntro(QWidget):
    """Consistent, accessible page identity block for workspace pages.

    The three text levels are kept separate so pages can share hierarchy and
    spacing without duplicating ad-hoc label construction. Labels wrap rather
    than forcing the surrounding layout to shrink the application's type.
    """

    def __init__(
        self,
        eyebrow: str,
        title: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PageIntro")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 2)
        layout.setSpacing(3)

        self.eyebrow_label = QLabel(eyebrow, self)
        self.eyebrow_label.setObjectName("SectionTitle")
        self.eyebrow_label.setWordWrap(True)
        self.eyebrow_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("PageTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.title_label.setStyleSheet(
            "font-size: 21px; font-weight: 750; "
            "letter-spacing: -0.4px; background: transparent;"
        )

        self.description_label = QLabel(description, self)
        self.description_label.setObjectName("Muted")
        self.description_label.setWordWrap(True)
        self.description_label.setMinimumWidth(0)
        self.description_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        layout.addWidget(self.eyebrow_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)


class SidebarNavigationList(QListWidget):
    """Keyboard- and screen-reader-friendly navigation list shared by TX/RX."""

    def __init__(self, workspace_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceNavigation")
        self.setAccessibleName(f"{workspace_name} navigation")
        self.setAccessibleDescription(
            f"Choose a page in the {workspace_name.lower()} workspace."
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setSpacing(2)
        self.setIconSize(QSize(18, 18))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def add_navigation_item(
    navigation: SidebarNavigationList,
    icon: QIcon,
    label: str,
) -> QListWidgetItem:
    """Add one navigation destination with persistent accessible metadata.

    Compact mode may hide the visible text, but the item's accessible name and
    tooltip remain available to assistive technology and mouse users.
    """
    item = QListWidgetItem(icon, label)
    item.setToolTip(label)
    item.setData(Qt.ItemDataRole.AccessibleTextRole, label)
    item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, f"Open {label}.")
    navigation.addItem(item)
    return item
