#!/usr/bin/env python3

import os
import logging
from datetime import datetime
from rich.logging import RichHandler
from rich.console import Console

# Global console instance
console = Console()

def setup_logger(target, results_dir):
    """
    Set up a logger that logs to both console and file
    
    Args:
        target (str): The target being scanned
        results_dir (str): The directory where results are stored
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(results_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create a log file name based on timestamp and target
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = os.path.join(logs_dir, f"kast-{timestamp}.log")
    
    # Create logger
    logger = logging.getLogger("kast")
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers if any
    if logger.handlers:
        logger.handlers.clear()
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # Console handler - using Rich for colorized output
    console_handler = RichHandler(
        rich_tracebacks=True,
        console=console,
        show_time=False,
        show_path=False
    )
    console_handler.setLevel(logging.INFO)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Log initial message
    logger.info(f"Starting KAST scan against {target}")
    logger.info(f"Logs will be saved to {log_file}")
    
    return logger

def get_module_logger(name):
    """
    Get a module-specific logger
    
    Args:
        name (str): The name of the module
        
    Returns:
        logging.Logger: Module-specific logger
    """
    return logging.getLogger(f"kast.{name}")
