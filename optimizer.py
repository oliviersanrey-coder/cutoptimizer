from dataclasses import dataclass
from typing import List


@dataclass
class PanelSpec:
    L: int
    W: int
    trim_L_each_side: int
    trim_W_each_side: int
    kerf: int


@dataclass
class PieceType:
    base_name: str
    length: int
    width: int
    qty: int
    grain_dim: str


def solve(panel: PanelSpec, piece_specs: List[PieceType]):
    return []
