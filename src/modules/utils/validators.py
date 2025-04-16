#!/usr/bin/env python3

import re
import socket
from urllib.parse import urlparse
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def is_valid_target(target):
    """
    Validate if the target is a valid URL or IP address
    
    Args:
        target (str): The target URL or IP address
        
    Returns:
        bool: True if valid, False otherwise
    """
    # Check if it's a URL
    if target.startswith(('http://', 'https://')):
        try:
            result = urlparse(target)
            return all([result.scheme, result.netloc])
        except:
            logger.error(f"Invalid URL format: {target}")
            return False
    
    # Check if it's an IP address
    try:
        socket.inet_aton(target)
        return True
    except:
        # Check if it's a hostname
        if re.match(r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$', target):
            return True
        logger.error(f"Invalid target format: {target}")
        return False

def normalize_url(url):
    """
    Normalize a URL by ensuring it has a scheme
    
    Args:
        url (str): The URL to normalize
        
    Returns:
        str: The normalized URL
    """
    if not url.startswith(('http://', 'https://')):
        return f'http://{url}'
    return url

def extract_domain(url):
    """
    Extract the domain from a URL
    
    Args:
        url (str): The URL to extract the domain from
        
    Returns:
        str: The extracted domain
    """
    parsed_url = urlparse(normalize_url(url))
    return parsed_url.netloc
