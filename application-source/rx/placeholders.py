"""Placeholder pages for non-Dashboard tabs, plus real Settings page with signal config."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from gui_dev_v3.widgets import Card, muted_label


class PlaceholderPage(QWidget):
    """Generic placeholder page showing the tab name."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        card = Card(title)
        card.body.addWidget(
            muted_label(subtitle or f"The {title} view is not yet implemented. It will be added in a future update.")
        )
        layout.addWidget(card)
        layout.addStretch(1)


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        card = Card("VLC GUI")
        
        # Version and Build
        version_label = muted_label("Version: 1.0.0 | Build: June 2026")
        card.body.addWidget(version_label)
        
        # Created by
        creator_label = QLabel("Created by: Reymart Martinez")
        creator_label.setStyleSheet("font-weight: bold; margin-top: 10px; margin-bottom: 10px;")
        card.body.addWidget(creator_label)
        
        # About description
        about_title = QLabel("About:")
        about_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        card.body.addWidget(about_title)
        
        about_text = QLabel(
            "An experimental Visible Light Communication (VLC) graphical user interface "
            "developed in partial fulfillment of the requirements for the degree of "
            "Bachelor of Science in Electronics Engineering. Designed to monitor, encode, "
            "and reconstruct 4B5B + NRZ/OOK optical payloads via ESP32 microcontrollers."
        )
        about_text.setWordWrap(True)
        about_text.setStyleSheet("line-height: 1.4;")
        card.body.addWidget(about_text)
        
        # License & Legal
        legal_title = QLabel("License & Legal:")
        legal_title.setStyleSheet("font-weight: bold; margin-top: 15px;")
        card.body.addWidget(legal_title)
        
        legal_text = muted_label(
            "Copyright © 2026. All rights reserved.\n"
            "This software is provided \"as-is\", without warranty of any kind, express or implied. "
            "For academic and experimental use only."
        )
        legal_text.setWordWrap(True)
        card.body.addWidget(legal_text)

        layout.addWidget(card)
        layout.addStretch(1)
