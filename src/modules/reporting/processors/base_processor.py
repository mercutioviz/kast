# src/modules/reporting/processors/base_processor.py
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseDataProcessor(ABC):
    """Base class for all tool-specific data processors"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw data from a tool and convert it to a standardized format
        
        Args:
            raw_data: The raw output data from the tool
            
        Returns:
            dict: Processed data in a standardized format
        """
        pass
    
    def get_empty_result(self) -> Dict[str, Any]:
        """
        Return an empty result structure when processing fails
        
        Returns:
            dict: Empty result structure
        """
        return {
            "title": f"{self.__class__.__name__.replace('Processor', '')} Results",
            "description": "No data available",
            "findings": []
        }
    
    def extract_summary(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract summary information from processed data
        
        Args:
            processed_data: The processed data from which to extract a summary
            
        Returns:
            dict: Summary information
        """
        # Default implementation - override in subclasses as needed
        return {
            "total": len(processed_data.get("findings", [])),
            "has_issues": len(processed_data.get("findings", [])) > 0
        }