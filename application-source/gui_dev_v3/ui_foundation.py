"""Shared presentation primitives for the TX and RX workspaces.

This module contains UI-only building blocks. It deliberately has no access to
application state, serial controllers, hardware backends, or firmware commands.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


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
