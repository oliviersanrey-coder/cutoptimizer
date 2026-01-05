from dataclasses import dataclass
from typing import List, Tuple, Dict


@dataclass(frozen=True)
class PanelSpec:
    L: int
    W: int
    trim_L_each_side: int
    trim_W_each_side: int
    kerf: int

    @property
    def usable_L(self) -> int:
        return max(0, self.L - 2 * self.trim_L_each_side)

    @property
    def usable_W(self) -> int:
        return max(0, self.W - 2 * self.trim_W_each_side)

    @property
    def usable_area_mm2(self) -> int:
        return self.usable_L * self.usable_W


@dataclass
class PieceType:
    base_name: str
    length: int
    width: int
    qty: int
    grain_dim: str  # "L", "W", "0"


@dataclass
class PieceInstance:
    name: str
    length: int
    width: int
    grain_dim: str  # "L", "W", "0"


@dataclass
class Placement:
    piece_name: str
    x: int
    y: int
    L: int
    W: int
    rotated: bool

    @property
    def area_mm2(self) -> int:
        return self.L * self.W


@dataclass
class PanelLayout:
    strategy: str  # "RIP_FIRST" or "CROSSCUT_FIRST"
    placements: List[Placement]
    groups: List[Tuple[int, int]]  # RIP_FIRST: (y,height). CROSSCUT_FIRST: (x,width)

    @property
    def used_area_mm2(self) -> int:
        return sum(p.area_mm2 for p in self.placements)


@dataclass
class Solution:
    strategy: str
    panel_layouts: List[PanelLayout]
    panels_used: int
    est_cuts: int
    used_area_mm2: int
    utilization_pct: float


def expand_pieces(specs: List[PieceType]) -> List[PieceInstance]:
    out: List[PieceInstance] = []
    for s in specs:
        if s.qty <= 1:
            out.append(PieceInstance(s.base_name, s.length, s.width, s.grain_dim))
        else:
            for i in range(1, s.qty + 1):
                out.append(PieceInstance(f"{s.base_name}{i}", s.length, s.width, s.grain_dim))
    return out


def can_fit(panel: PanelSpec, piece: PieceInstance) -> bool:
    UL, UW = panel.usable_L, panel.usable_W
    g = piece.grain_dim.lower()
    if g == "l":
        return piece.length <= UL and piece.width <= UW
    if g == "w":
        return piece.width <= UL and piece.length <= UW
    return (
        (piece.length <= UL and piece.width <= UW)
        or (piece.width <= UL and piece.length <= UW)
    )


def oriented_candidates(piece: PieceInstance):
    g = piece.grain_dim.lower()
    L0, W0 = piece.length, piece.width
    if g == "l":
        return [(L0, W0, False)]
    if g == "w":
        return [(W0, L0, True)]
    return [(L0, W0, False), (W0, L0, True)]


def pack_rip_first(panel: PanelSpec, pieces: List[PieceInstance]) -> PanelLayout:
    UL, UW, k = panel.usable_L, panel.usable_W, panel.kerf
    pieces_sorted = sorted(pieces, key=lambda p: max(p.length, p.width), reverse=True)

    strips: List[Dict] = []  # {y,h,x_cursor}
    placements: List[Placement] = []

    for p in pieces_sorted:
        cands = [(L, W, rot) for (L, W, rot) in oriented_candidates(p) if L <= UL and W <= UW]
        if not cands:
            continue

        best_choice = None
        # score: (creates_new_strip, strip_height, wasted_x_after, y_pos)  lower is better
        for L, W, rot in cands:
            # try existing strip first
            for s in strips:
                if s["h"] != W:
                    continue
                x = s["x"]
                if x + L <= UL:
                    wasted_x = UL - (x + L)
                    score = (0, W, wasted_x, s["y"])
                    if best_choice is None or score < best_choice[0]:
                        best_choice = (score, ("existing", s, L, W, rot))

            # otherwise consider creating a new strip
            new_y = 0 if not strips else strips[-1]["y"] + strips[-1]["h"] + k
            if new_y + W <= UW:
                wasted_x = UL - L
                score = (1, W, wasted_x, new_y)
                if best_choice is None or score < best_choice[0]:
                    best_choice = (score, ("new", new_y, L, W, rot))

        if best_choice is None:
            continue

        choice = best_choice[1]
        if choice[0] == "existing":
            s = choice[1]
            L, W, rot = choice[2], choice[3], choice[4]
            x = s["x"]
            placements.append(Placement(p.name, x, s["y"], L, W, rot))
            s["x"] = x + L + k
        else:
            new_y, L, W, rot = choice[1], choice[2], choice[3], choice[4]
            strips.append({"y": new_y, "h": W, "x": L + k})
            placements.append(Placement(p.name, 0, new_y, L, W, rot))

    groups = [(s["y"], s["h"]) for s in strips]
    return PanelLayout(strategy="RIP_FIRST", placements=placements, groups=groups)


def pack_crosscut_first(panel: PanelSpec, pieces: List[PieceInstance]) -> PanelLayout:
    UL, UW, k = panel.usable_L, panel.usable_W, panel.kerf
    pieces_sorted = sorted(pieces, key=lambda p: max(p.length, p.width), reverse=True)

    bands: List[Dict] = []  # {x,w,y_cursor}
    placements: List[Placement] = []

    for p in pieces_sorted:
        cands = [(L, W, rot) for (L, W, rot) in oriented_candidates(p) if L <= UL and W <= UW]
        if not cands:
            continue

        best_choice = None
        # score: (creates_new_band, band_length, wasted_y_after, x_pos) lower is better
        for L, W, rot in cands:
            # try existing band first
            for b in bands:
                if b["w"] != L:
                    continue
                y = b["y"]
                if y + W <= UW:
                    wasted_y = UW - (y + W)
                    score = (0, L, wasted_y, b["x"])
                    if best_choice is None or score < best_choice[0]:
                        best_choice = (score, ("existing", b, L, W, rot))

            # otherwise consider creating a new band
            new_x = 0 if not bands else bands[-1]["x"] + bands[-1]["w"] + k
            if new_x + L <= UL:
                wasted_y = UW - W
                score = (1, L, wasted_y, new_x)
                if best_choice is None or score < best_choice[0]:
                    best_choice = (score, ("new", new_x, L, W, rot))

        if best_choice is None:
            continue

        choice = best_choice[1]
        if choice[0] == "existing":
            b = choice[1]
            L, W, rot = choice[2], choice[3], choice[4]
            y = b["y"]
            placements.append(Placement(p.name, b["x"], y, L, W, rot))
            b["y"] = y + W + k
        else:
            new

