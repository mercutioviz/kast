# src/modules/reporting/processors/__init__.py
from .base_processor import BaseDataProcessor
from .whatweb_processor import WhatWebProcessor
from .theharvester_processor import TheHarvesterProcessor
from .dnsenum_processor import DNSEnumProcessor
from .sslscan_processor import SSLScanProcessor
from .wafw00f_processor import Wafw00fProcessor
from .nikto_processor import NiktoProcessor

# Dictionary mapping tool names to their processor classes
PROCESSORS = {
    "whatweb": WhatWebProcessor,
    "theharvester": TheHarvesterProcessor,
    "dnsenum": DNSEnumProcessor,
    "sslscan": SSLScanProcessor,
    "wafw00f": Wafw00fProcessor,
    "nikto": NiktoProcessor
}

def get_processor(tool_name):
    """
    Get the appropriate processor for a tool
    
    Args:
        tool_name (str): Name of the tool
        
    Returns:
        BaseDataProcessor: An instance of the appropriate processor
    """
    processor_class = PROCESSORS.get(tool_name.lower())
    if processor_class:
        return processor_class()
    return None