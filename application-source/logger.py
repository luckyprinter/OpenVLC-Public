import os
import sys
import time
import logging
import traceback
from logging.handlers import RotatingFileHandler

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_active_role: str = "app"   # updated by reinit_logger()


def setup_logger(role: str = "app") -> str:
    global _active_role
    _active_role = role.lower()
    base_dir = get_base_dir()
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(log_dir, f"vlc_{_active_role}_{timestamp_str}.log")
    
    # Configure root logger with RotatingFileHandler
    handler = RotatingFileHandler(
        log_file, 
        maxBytes=10 * 1024 * 1024, # 10 MB limit
        backupCount=5, # Keep last 5 files
        encoding="utf-8"
    )
    
    formatter = logging.Formatter(
        "[{asctime}] [{levelname:^7}] {message}", 
        style='{', 
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates during reload
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    
    # Also add a console handler for developers
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root_logger.addHandler(console)
    
    # Log session start
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"\n{'='*50}\n--- New {role.upper()} Session: {now_str} ---\n{'='*50}")
    
    # Capture unhandled exceptions
    def global_exception_handler(exctype, value, tb):
        if issubclass(exctype, KeyboardInterrupt):
            sys.__excepthook__(exctype, value, tb)
            return
        logging.critical("Unhandled Exception", exc_info=(exctype, value, tb))
    
    sys.excepthook = global_exception_handler
    
    return log_file


def reinit_logger(role: str) -> str:
    """Re-initialise the logger with a TX/RX role prefix once the mode is known."""
    return setup_logger(role)


_log_file = setup_logger("app")

def file_log(role: str, event: str, details: str) -> None:
    """Backwards compatibility for existing file_log calls."""
    logging.info(f"[{role}] {event} - {details}")
