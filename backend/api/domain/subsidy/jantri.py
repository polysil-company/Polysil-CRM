"""The Jantri: GGRC's unit cost per hectare, read from a matrix (FS-008 rules 6 to 8,
14 to 16, 18).

Two models. Drip and Mini Sprinkler interpolate a two-dimensional matrix of
lateral spacing (rows) by area (columns) bilinearly; Sprinkler looks a one-
dimensional table up by exact area. Both are the workbooks' own arithmetic:

* the area bracket is the tabulated column at or below the area and the next
  column (`'New Subsidy Calculation C1'!B20:C20`); the spacing bracket is the
  smallest tabulated row at or above the spacing and the next row down
  (`A21:A22`);
* the spacing weight is `(s_hi - spacing) / (s_hi - s_lo)`, the algebraic
  reduction of the workbook's `(B21 - (B21 + (B22-B21)*(A21-C28)/(A21-A22))) /
  (B21-B22)`;
* a spacing below 1 m, or an area below the smallest column, takes the value at
  the row's upper bracket and the lower column with no interpolation (the
  workbook's guards, cliffs included);
* an area above the largest column takes the value at that column scaled by
  area / largest (the workbook's own `*C27/5`).

Where the workbook leaves the table it extrapolates: toward zero below the
smallest row (its "next row" is 0) and without bound above the largest (the
weight goes negative; a negative subsidy at 20 m). The engine clamps to the edge
row on both sides and says so in a warning; `OutsideTable.EXTRAPOLATE` restores
the workbook's arithmetic (GAP-078, GAP-081).

Pure: `Decimal` in, `Decimal` out, no rounding here. Rounding is the pipeline's
business, at the cells the workbook rounds.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ONE_METRE = Decimal("1")


class OutsideTable(StrEnum):
    CLAMP = "clamp"
    EXTRAPOLATE = "extrapolate"


def _dec(v: object) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


@dataclass(frozen=True)
class Matrix2D:
    """Spacing rows (descending, as the workbook lists them) by area columns
    (ascending); a cell per pair, at the workbook's precision."""

    spacings: tuple[Decimal, ...]
    areas: tuple[Decimal, ...]
    cells: Mapping[tuple[Decimal, Decimal], Decimal]

    @classmethod
    def from_rows(cls, areas: Iterable[object],
                  rows: Iterable[tuple[object, Iterable[object]]]) -> Matrix2D:
        cols = tuple(_dec(a) for a in areas)
        spacings: list[Decimal] = []
        cells: dict[tuple[Decimal, Decimal], Decimal] = {}
        for spacing, costs in rows:
            s = _dec(spacing)
            spacings.append(s)
            for a, c in zip(cols, costs, strict=True):
                cells[(s, a)] = _dec(c)
        ordered = tuple(sorted(spacings, reverse=True))
        return cls(ordered, cols, cells)

    def at(self, spacing: Decimal, area: Decimal) -> Decimal:
        return self.cells[(spacing, area)]

    @property
    def min_area(self) -> Decimal:
        return self.areas[0]

    @property
    def max_area(self) -> Decimal:
        return self.areas[-1]

    @property
    def largest_spacing(self) -> Decimal:
        return self.spacings[0]

    @property
    def smallest_spacing(self) -> Decimal:
        return self.spacings[-1]


@dataclass(frozen=True)
class Jantri:
    unit_cost: Decimal
    spacing_used: Decimal        # the row or the value the interpolation ran at, after any clamp
    area_used: Decimal
    warnings: tuple[str, ...]


def area_bracket(areas: tuple[Decimal, ...], area: Decimal) -> tuple[Decimal, Decimal | None]:
    """The workbook's B20 and C20: the largest column at or below the area (the
    first column when the area is below it), and the next column, None past the
    last."""
    lo = areas[0]
    for a in areas:
        if area >= a:
            lo = a
        else:
            break
    i = areas.index(lo)
    return lo, (areas[i + 1] if i + 1 < len(areas) else None)


def spacing_bracket(spacings: tuple[Decimal, ...],
                    spacing: Decimal) -> tuple[Decimal, Decimal | None]:
    """The workbook's A21 and A22: the smallest row at or above the spacing (the
    largest row when the spacing is above it), and the next row down, None below
    the smallest."""
    hi = spacings[0]
    for s in spacings:                      # descending
        if spacing <= s:
            hi = s
        else:
            break
    i = spacings.index(hi)
    return hi, (spacings[i + 1] if i + 1 < len(spacings) else None)


def bilinear(matrix: Matrix2D, *, area: Decimal, spacing: Decimal,
             outside: OutsideTable = OutsideTable.CLAMP, scale_above_max: bool = True) -> Jantri:
    """Rule 6, with the guards of rules 7 and 8. `scale_above_max` is the regular
    table's `* area / 5`; the 7-year tables are only ever called inside their
    window, so their callers pass False."""
    if scale_above_max and area > matrix.max_area:
        base = bilinear(matrix, area=matrix.max_area, spacing=spacing, outside=outside,
                        scale_above_max=False)
        note = (f"area_above_table: {area} Ha is above the largest tabulated "
                f"{matrix.max_area} Ha; the unit cost was scaled by area / {matrix.max_area}")
        return Jantri(base.unit_cost * area / matrix.max_area, base.spacing_used, area,
                      (*base.warnings, note))

    a_lo, a_hi = area_bracket(matrix.areas, area)
    s_hi, s_lo = spacing_bracket(matrix.spacings, spacing)
    warnings: list[str] = []
    if spacing > matrix.largest_spacing or spacing < matrix.smallest_spacing:
        warnings.append(f"spacing_outside_table: {spacing} m is outside the tabulated "
                        f"{matrix.smallest_spacing} to {matrix.largest_spacing} m; "
                        f"the {s_hi} m row was used")
    below_area = area < matrix.min_area
    if below_area:
        warnings.append(f"area_below_table: {area} Ha is below the smallest tabulated "
                        f"{matrix.min_area} Ha; that column was used")

    # The workbook's guards: no interpolation at all, the row's upper bracket at
    # the lower column. Below 1 m the row is the smallest one. Both guards can
    # fire at once, and both are reported (code review F-10).
    if spacing < ONE_METRE or below_area:
        return Jantri(matrix.at(s_hi, a_lo), s_hi, a_lo, tuple(warnings))

    # The area weight along each of the two rows. Past the last column the
    # workbook's C20 is 0 and the term vanishes.
    if a_hi is None:
        t = Decimal(0)
        along = {s_hi: matrix.at(s_hi, a_lo)}
        if s_lo is not None:
            along[s_lo] = matrix.at(s_lo, a_lo)
    else:
        t = (area - a_lo) / (a_hi - a_lo)
        def between(s: Decimal) -> Decimal:
            return matrix.at(s, a_lo) + (matrix.at(s, a_hi) - matrix.at(s, a_lo)) * t

        along = {s_hi: between(s_hi)}
        if s_lo is not None:
            along[s_lo] = between(s_lo)

    v_hi = along[s_hi]
    if s_lo is None:
        # At or below the smallest row (and at least 1 m). The workbook's next row
        # is 0, so its weight extrapolates toward zero.
        if outside is OutsideTable.EXTRAPOLATE and spacing < s_hi:
            w = (s_hi - spacing) / s_hi
            return Jantri(v_hi + (Decimal(0) - v_hi) * w, spacing, area, tuple(warnings))
        return Jantri(v_hi, s_hi, area, tuple(warnings))

    w = (s_hi - spacing) / (s_hi - s_lo)
    if spacing > s_hi:
        # Above the largest row the weight is negative and the workbook keeps going.
        if outside is OutsideTable.EXTRAPOLATE:
            return Jantri(v_hi + (along[s_lo] - v_hi) * w, spacing, area, tuple(warnings))
        return Jantri(v_hi, s_hi, area, tuple(warnings))
    return Jantri(v_hi + (along[s_lo] - v_hi) * w, spacing, area, tuple(warnings))


def lookup_1d(table: Mapping[Decimal, Decimal], area: Decimal) -> Decimal | None:
    """Rule 18: exact match on the tabulated area, as `VLOOKUP(..., 0)` matches.
    None off a step; the caller turns that into the 422 that names the steps."""
    for key, cost in table.items():
        if key == area:
            return cost
    return None


def table_1d(rows: Iterable[tuple[object, object]]) -> dict[Decimal, Decimal]:
    return {_dec(a): _dec(c) for a, c in rows}
