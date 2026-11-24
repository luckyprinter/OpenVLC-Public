"""VLC Receiver App — modern PySide6 implementation."""

# Configure writable app-owned storage before importing modules that resolve
# status, logs, captures, or experiment files at module import time.
from .runtime_paths import configure_runtime_data_dir

configure_runtime_data_dir()
