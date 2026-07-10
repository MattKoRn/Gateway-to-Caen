"""Combined high-detail battlefield rendering mixin."""
from .terrain_graphics import TerrainGraphicsMixin
from .unit_graphics import UnitGraphicsMixin


class EnhancedGraphicsMixin(TerrainGraphicsMixin, UnitGraphicsMixin):
    pass
