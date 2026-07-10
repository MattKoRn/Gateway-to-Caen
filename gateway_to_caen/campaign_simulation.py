"""Loaded campaign simulation implementation."""
from ._source_loader import execute_parts
execute_parts(globals(), "campaign_simulation", 3)
del execute_parts
