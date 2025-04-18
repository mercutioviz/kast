#!/usr/bin/env python3

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)
console = Console()

def display_banner():
    """Display the KAST banner"""
    banner_text = """
    ██╗  ██╗ █████╗ ███████╗████████╗
    ██║ ██╔╝██╔══██╗██╔════╝╚══██╔══╝
    █████╔╝ ███████║███████╗   ██║   
    ██╔═██╗ ██╔══██║╚════██║   ██║   
    ██║  ██╗██║  ██║███████║   ██║   
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝   
    """
    
    subtitle = "Kali Automated Scanning Tool"
    version = "v1.1.0"
    
    banner = Text(banner_text, style="bold blue")
    panel_text = Text.assemble(
        banner,
        "\n",
        Text(subtitle, style="bold yellow"),
        "\n",
        Text(version, style="green")
    )
    
    console.print(Panel(panel_text, border_style="blue"))
    console.print("[bold yellow]A comprehensive web application security scanner[/bold yellow]")
    console.print("[bold red]Legal Disclaimer:[/bold red] Use only on systems you have permission to scan.")
    console.print()
    
    logger.debug("Banner displayed")
