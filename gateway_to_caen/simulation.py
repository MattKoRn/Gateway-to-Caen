"""Loaded simulation implementation."""
from ._source_loader import execute_parts
execute_parts(globals(), "simulation", 4)
del execute_parts
