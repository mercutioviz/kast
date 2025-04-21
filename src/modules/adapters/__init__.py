#!/usr/bin/env python3
#
# kast/src/modules/adapters/__init__.py
#
# Description: Registry for tool adapters to make adding new tools easier
#

from .nikto import NiktoAdapter
from .whatweb import WhatWebAdapter
from .theharvester import TheHarvesterAdapter
from .dnsenum import DNSenumAdapter
from .sslscan import SSLScanAdapter
from .wafw00f import WAFw00fAdapter
import os
import sys

# Registry of all available adapters
ADAPTERS = [
    NiktoAdapter(),
    WhatWebAdapter(),
    TheHarvesterAdapter(),
    DNSenumAdapter(),
    SSLScanAdapter(),
    WAFw00fAdapter()
]

def get_all_adapters():
    """
    Get all registered adapters.
    
    Returns:
        list: All registered tool adapters
    """
    return ADAPTERS

def get_adapter_by_name(name):
    """
    Get an adapter by tool name.
    
    Args:
        name (str): Name of the tool
        
    Returns:
        ToolAdapter: The adapter for the specified tool, or None if not found
    """
    for adapter in ADAPTERS:
        if adapter.tool_name == name:
            return adapter
    return None
