"""Loaded enhanced UI implementation."""
from ._source_loader import execute_parts
execute_parts(globals(), "enhanced_ui", 1)
del execute_parts
