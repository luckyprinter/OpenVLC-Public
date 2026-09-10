from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from gui_dev_v3.rx.experiments_page import ExperimentsPage
from gui_dev_v3.rx.table_builder_page import TableBuilderPage
from gui_dev_v3.rx.export_page import ExportPage
from gui_dev_v3.app_state import RXAppState

class StudyDataPage(QWidget):
    """Container page combining Experiments, Tables, and Export pages in tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        # Inner Tab Widget
        self.tabs = QTabWidget()

        from gui_dev_v3.widgets import scrollable
        self.experiments_page = ExperimentsPage()
        self.tables_page = TableBuilderPage()
        self.export_page = ExportPage()

        self.tabs.addTab(scrollable(self.experiments_page), "Experiments")
        self.tabs.addTab(scrollable(self.tables_page), "Table Builder")
        self.tabs.addTab(scrollable(self.export_page), "Export")

        layout.addWidget(self.tabs)

    def refresh(self, state: RXAppState) -> None:
        if hasattr(self.experiments_page, "refresh"):
            self.experiments_page.refresh(state)
        if hasattr(self.tables_page, "refresh"):
            self.tables_page.refresh(state)
        if hasattr(self.export_page, "refresh"):
            self.export_page.refresh(state)
