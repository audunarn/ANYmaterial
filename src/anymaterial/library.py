"""The material library: named grades, where they came from, and how to add more.

Three sources feed one library:

* the **DNV-RP-C208** section 4.6.6 steel curves, built from
  ``data/dnv_rp_c208.json`` -- one entry per grade and thickness class, each with
  its flow curve;
* a small **curated** set in ``data/materials.json``, each entry naming the source
  its numbers came from;
* the **user's own** file, which is where anything added at runtime goes.

Every entry carries a ``status``.  ``tabulated`` means the numbers are a
standard's own table, reproduced with the reference. ``indicative`` means they are
typical published figures for the grade and are **not design values**: a grade
designation covers a range that varies with product form, temper and thickness,
and the governing standard or the mill certificate is what settles it.  The
distinction is carried through the API, the CLI and the editor rather than being
left in a README, because a library that presents a looked-up number and a
qualified number identically invites the first to be used as the second.

Selection fails closed.  A thickness outside a grade's tabulated range is an
error, not an invitation to use the nearest row: the rows are strength reductions
with plate thickness, and silently reusing the thickest row for a thicker plate
would overstate strength in exactly the case the reduction exists to prevent.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .curves import DNVC208MaterialCurve, curve_from_properties
from .isotropic import IsotropicMaterial
from .spec import MaterialSpec

__all__ = [
    "LibraryEntry",
    "MaterialLibrary",
    "STEEL_DENSITY",
    "STEEL_POISSON_RATIO",
    "available_grades",
    "builtin_library",
    "dnv_c208_steel_curve",
    "dnv_c208_steel_properties",
    "library",
    "steel",
    "thickness_classes",
    "user_library_path",
]

_MPA = 1.0e6

_DATA_DIR = Path(__file__).with_name("data")
_DNV_PATH = _DATA_DIR / "dnv_rp_c208.json"
_CURATED_PATH = _DATA_DIR / "materials.json"

LIBRARY_FORMAT = "anymaterial.library"
LIBRARY_VERSION = 1

# Where a material added at runtime is kept.  Overridable, because a project that
# wants its materials beside its models should be able to say so.
LIBRARY_PATH_VARIABLE = "ANYMATERIAL_LIBRARY"
DEFAULT_USER_LIBRARY = Path.home() / ".anymaterial" / "materials.json"

_LOW_FRACTILE_ALIASES = frozenset({"low", "low_fractile", "5%", "5_percent"})
_AUTOMATIC_ALIASES = frozenset({"auto", "automatic", "bythickness", "autobyplatethickness"})

# Not part of the RP-C208 flow-curve tables; the conventional structural-steel
# values, stated here rather than hidden in a default argument.
STEEL_POISSON_RATIO = 0.3
STEEL_DENSITY = 7850.0

# What kind of number an entry holds.  The distinction is the point of the
# library: all three are useful and only one of them is a design value.
#
#   tabulated  a standard's own table, reproduced with the reference
#   measured   the mean of a named test campaign -- a mean, not a characteristic
#              value, and therefore unconservative if used as one
#   indicative a typical published figure for the grade
#   user       whatever the user added
STATUSES = ("tabulated", "measured", "indicative", "user")


@dataclass(frozen=True)
class LibraryEntry:
    """A material in the library, with the provenance of its numbers.

    ``calculation`` records how a derived entry was derived -- the Ramberg-Osgood
    exponent behind a tabulated curve, the transverse-isotropy assumption behind a
    composite lamina's ``G23``.  It is carried rather than dropped because a
    derived number whose derivation is not recorded cannot be checked, and an
    assumption nobody can see is one nobody will question.
    """

    spec: MaterialSpec
    category: str = "other"
    status: str = "user"
    standard: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    tensile_strength: Optional[float] = None
    calculation: Optional[Mapping[str, Any]] = None
    measurement: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, not {self.status!r}")
        if self.status == "measured" and not self.measurement:
            # A measured value without its sample size and scatter is just a
            # number claiming an authority it cannot show.
            raise ValueError(
                f"{self.name!r} is marked measured but carries no measurement record "
                "(coupon count and coefficient of variation)"
            )

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def is_design_value(self) -> bool:
        """Whether the numbers came from a standard's own table.

        ``False`` does not mean wrong -- it means unverified for design, and the
        caller is the one who has to verify it.
        """

        return self.status == "tabulated"

    def build(self):
        """Construct the live material this entry describes."""

        return self.spec.build()

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.spec.name,
            "category": self.category,
            "status": self.status,
            "symmetry": self.spec.symmetry,
            "constants": dict(self.spec.constants),
            "density": float(self.spec.density),
            "yield_stress": float(self.spec.yield_stress),
        }
        if self.spec.hardening:
            data["hardening"] = dict(self.spec.hardening)
        if self.spec.hill:
            data["hill"] = dict(self.spec.hill)
        for key in ("standard", "source", "notes"):
            value = getattr(self, key)
            if value:
                data[key] = value
        if self.tensile_strength is not None:
            data["tensile_strength"] = float(self.tensile_strength)
        if self.calculation:
            data["calculation"] = dict(self.calculation)
        if self.measurement:
            data["measurement"] = dict(self.measurement)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LibraryEntry":
        spec = MaterialSpec.from_dict(data)
        tensile = data.get("tensile_strength")
        return cls(
            spec=spec,
            category=str(data.get("category", "other")),
            status=str(data.get("status", "user")),
            standard=data.get("standard"),
            source=data.get("source"),
            notes=data.get("notes"),
            tensile_strength=None if tensile is None else float(tensile),
            calculation=dict(data["calculation"]) if data.get("calculation") else None,
            measurement=dict(data["measurement"]) if data.get("measurement") else None,
        )


# --------------------------------------------------------------- DNV-RP-C208


@lru_cache(maxsize=1)
def _dnv_table() -> Mapping[str, Any]:
    return json.loads(_DNV_PATH.read_text(encoding="utf-8"))


def _thickness_class_label(lower_mm: float, upper_mm: float) -> str:
    if lower_mm <= 0.0:
        return f"t <= {upper_mm:g}"
    return f"{lower_mm:g} < t <= {upper_mm:g}"


def _normalized_thickness_class(value: str) -> str:
    return str(value or "auto").strip().lower().replace(" ", "")


def _grade_key(grade: str) -> str:
    return str(grade).upper().replace(" ", "")


def available_grades() -> Tuple[str, ...]:
    """Return the tabulated RP-C208 steel grades, sorted."""

    return tuple(sorted(_dnv_table()["grades"]))


def thickness_classes(grade: str) -> Tuple[str, ...]:
    """Return the tabulated thickness-class labels for one grade."""

    grades = _dnv_table()["grades"]
    key = _grade_key(grade)
    if key not in grades:
        raise ValueError(f"Unsupported RP-C208 steel grade {grade!r}; use one of {sorted(grades)}")
    return tuple(
        _thickness_class_label(float(row["thickness_from"]), float(row["thickness_to"]))
        for row in grades[key]
    )


def dnv_c208_steel_properties(
    grade: str,
    thickness: float,
    thickness_class: str = "auto",
    fractile: str = "low",
) -> Dict[str, float | str]:
    """Return one validated RP-C208 low-fractile steel table row in SI units.

    ``thickness`` is in metres.  Mean curves are intentionally not guessed; pass
    explicit properties through :func:`anymaterial.curves.curve_from_properties`
    if mean data is required.

    An explicit ``thickness_class`` selects a row deliberately, which is what
    makes a documented deviation possible without making an accident possible.
    """

    if fractile.lower() not in _LOW_FRACTILE_ALIASES:
        raise NotImplementedError(
            "Built-in RP-C208 mean curves are not available; supply explicit curve properties"
        )
    table = _dnv_table()
    grades = table["grades"]
    grade_key = _grade_key(grade)
    if grade_key not in grades:
        raise ValueError(f"Unsupported RP-C208 steel grade {grade!r}; use one of {sorted(grades)}")
    thickness_mm = float(thickness) * 1000.0
    if thickness_mm <= 0.0:
        raise ValueError("thickness must be positive")

    rows = grades[grade_key]
    selected: Optional[Mapping[str, float]] = None
    class_key = _normalized_thickness_class(thickness_class)
    if class_key in _AUTOMATIC_ALIASES:
        for row in rows:
            if float(row["thickness_from"]) < thickness_mm <= float(row["thickness_to"]):
                selected = row
                break
        if selected is None:
            raise ValueError(
                f"Thickness {thickness_mm:g} mm is outside the built-in RP-C208 range "
                f"for {grade_key} (maximum {float(rows[-1]['thickness_to']):g} mm)"
            )
    else:
        for row in rows:
            label = _thickness_class_label(float(row["thickness_from"]), float(row["thickness_to"]))
            if class_key == _normalized_thickness_class(label):
                selected = row
                break
        if selected is None:
            raise ValueError(
                f"Unsupported thickness_class {thickness_class!r} for {grade_key}; "
                f"use one of {list(thickness_classes(grade_key))}"
            )

    lower = float(selected["thickness_from"])
    upper = float(selected["thickness_to"])
    return {
        "grade": grade_key,
        "thickness_class": _thickness_class_label(lower, upper),
        "thickness_mm": thickness_mm,
        "source": str(table["source"]),
        "E_pa": float(table["elastic_modulus"]) * _MPA,
        "sigma_prop": float(selected["sigma_prop"]) * _MPA,
        "sigma_yield": float(selected["sigma_yield"]) * _MPA,
        "sigma_yield_2": float(selected["sigma_yield_2"]) * _MPA,
        "eps_p_y1": float(selected.get("eps_p_y1", table["default_eps_p_y1"])),
        "eps_p_y2": float(selected["eps_p_y2"]),
        "K": float(selected["K"]) * _MPA,
        "n": float(selected["n"]),
    }


def dnv_c208_steel_curve(grade: str, thickness: float, fractile: str = "low") -> DNVC208MaterialCurve:
    """Return a validated RP-C208 steel curve for a grade and plate thickness."""

    return curve_from_properties(dnv_c208_steel_properties(grade, thickness, fractile=fractile))


def steel(
    grade: str = "S355",
    thickness: float = 0.010,
    *,
    name: Optional[str] = None,
    density: float = STEEL_DENSITY,
    nonlinear: bool = False,
) -> IsotropicMaterial:
    """Build a steel material from the RP-C208 table.

    ``thickness`` is in metres and selects the table row.  ``nonlinear=True``
    attaches the matching hardening curve; without it a nonlinear solve is
    geometrically nonlinear but the material stays elastic, which is a different
    analysis and worth asking for explicitly.
    """

    properties = dnv_c208_steel_properties(grade, thickness)
    return IsotropicMaterial(
        name=name or str(properties["grade"]),
        elastic_modulus=float(properties["E_pa"]),
        poisson_ratio=STEEL_POISSON_RATIO,
        density=density,
        yield_stress=float(properties["sigma_yield"]),
        hardening_curve=curve_from_properties(properties) if nonlinear else None,
    )


def _dnv_entries() -> List[LibraryEntry]:
    """One entry per grade and thickness class, built from the table itself.

    Derived rather than duplicated, so the curve numbers have exactly one home.
    """

    table = _dnv_table()
    entries: List[LibraryEntry] = []
    for grade in sorted(table["grades"]):
        for row in table["grades"][grade]:
            lower = float(row["thickness_from"])
            upper = float(row["thickness_to"])
            # A representative thickness inside the class, used to resolve the
            # same row again when the specification is rebuilt.
            thickness = (upper if lower <= 0.0 else 0.5 * (lower + upper)) / 1000.0
            properties = dnv_c208_steel_properties(grade, thickness)
            label = _thickness_class_label(lower, upper)
            entries.append(
                LibraryEntry(
                    spec=MaterialSpec(
                        name=f"{grade} ({label} mm)",
                        symmetry="isotropic",
                        constants={
                            "elastic_modulus": float(properties["E_pa"]),
                            "poisson_ratio": STEEL_POISSON_RATIO,
                        },
                        density=STEEL_DENSITY,
                        yield_stress=float(properties["sigma_yield"]),
                        hardening={"kind": "dnv_c208", "grade": grade, "thickness": thickness},
                    ),
                    category="structural steel",
                    status="tabulated",
                    standard=str(table["reference"]),
                    source=str(table["source"]),
                    notes=(
                        f"Low-fractile true stress / true plastic strain curve for {grade} "
                        f"at {label} mm plate thickness."
                    ),
                )
            )
    return entries


# ------------------------------------------------------------------- library


@dataclass
class MaterialLibrary:
    """A named collection of materials, with provenance."""

    entries: List[LibraryEntry] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __contains__(self, name: object) -> bool:
        return any(entry.name == name for entry in self.entries)

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(entry.name for entry in self.entries)

    @property
    def categories(self) -> Tuple[str, ...]:
        return tuple(sorted({entry.category for entry in self.entries}))

    def get(self, name: str) -> LibraryEntry:
        """Return one entry by name."""

        for entry in self.entries:
            if entry.name == name:
                return entry
        raise KeyError(f"no material named {name!r} in the library")

    def find(
        self,
        *,
        category: Optional[str] = None,
        status: Optional[str] = None,
        nonlinear: Optional[bool] = None,
        text: Optional[str] = None,
    ) -> List[LibraryEntry]:
        """Filter the library."""

        results = list(self.entries)
        if category is not None:
            results = [entry for entry in results if entry.category == category]
        if status is not None:
            results = [entry for entry in results if entry.status == status]
        if nonlinear is not None:
            results = [entry for entry in results if entry.spec.is_nonlinear is nonlinear]
        if text:
            needle = text.lower()
            results = [
                entry
                for entry in results
                if needle in entry.name.lower() or needle in entry.category.lower()
            ]
        return results

    def add(self, entry: LibraryEntry, *, replace_existing: bool = False) -> LibraryEntry:
        """Add a material.

        A duplicate name is refused unless replacing is asked for: two materials
        with one name is how the wrong one ends up in an analysis.
        """

        entry.spec.build()  # Validate before it can be stored or written out.
        existing = next((item for item in self.entries if item.name == entry.name), None)
        if existing is not None:
            if not replace_existing:
                raise ValueError(
                    f"a material named {entry.name!r} is already in the library; "
                    "pass replace_existing=True to overwrite it"
                )
            self.entries[self.entries.index(existing)] = entry
            return entry
        self.entries.append(entry)
        return entry

    def remove(self, name: str) -> LibraryEntry:
        """Remove a material by name."""

        entry = self.get(name)
        self.entries.remove(entry)
        return entry

    def merged_with(self, other: "MaterialLibrary") -> "MaterialLibrary":
        """A library with ``other``'s entries taking precedence on a name clash."""

        by_name: Dict[str, LibraryEntry] = {entry.name: entry for entry in self.entries}
        for entry in other.entries:
            by_name[entry.name] = entry
        return MaterialLibrary(entries=list(by_name.values()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": LIBRARY_FORMAT,
            "version": LIBRARY_VERSION,
            "materials": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MaterialLibrary":
        if data.get("format") != LIBRARY_FORMAT:
            raise ValueError(f"not an {LIBRARY_FORMAT} document: format={data.get('format')!r}")
        version = int(data.get("version", 0))
        if version != LIBRARY_VERSION:
            raise ValueError(
                f"unsupported {LIBRARY_FORMAT} version {version}; this build reads {LIBRARY_VERSION}"
            )
        return cls(entries=[LibraryEntry.from_dict(item) for item in data.get("materials", ())])

    @classmethod
    def load(cls, path: str | Path) -> "MaterialLibrary":
        """Read a library file."""

        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path, *, overwrite: bool = True) -> Path:
        """Write the library to a file."""

        destination = Path(path)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite existing file: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return destination


@lru_cache(maxsize=1)
def _curated_entries() -> Tuple[LibraryEntry, ...]:
    data = json.loads(_CURATED_PATH.read_text(encoding="utf-8"))
    return tuple(LibraryEntry.from_dict(item) for item in data.get("materials", ()))


def builtin_library() -> MaterialLibrary:
    """The materials that ship with the package.

    The RP-C208 steels are derived from the curve table, so their numbers are not
    duplicated; the curated entries are read from ``data/materials.json``.
    """

    return MaterialLibrary(entries=_dnv_entries() + list(_curated_entries()))


def user_library_path() -> Path:
    """Where a material added at runtime is kept.

    ``ANYMATERIAL_LIBRARY`` overrides it, so a project can keep its materials
    beside its models rather than in a home directory.
    """

    override = os.environ.get(LIBRARY_PATH_VARIABLE)
    return Path(override) if override else DEFAULT_USER_LIBRARY


def library(*, include_user: bool = True) -> MaterialLibrary:
    """The full library: what ships, plus the user's own file if it exists.

    A user entry with the same name as a built-in one wins, which is how a grade
    gets corrected locally without editing the package.
    """

    result = builtin_library()
    path = user_library_path()
    if include_user and path.is_file():
        result = result.merged_with(MaterialLibrary.load(path))
    return result


def add_to_user_library(entry: LibraryEntry, *, replace_existing: bool = False) -> Path:
    """Add a material to the user's library file and save it."""

    path = user_library_path()
    existing = MaterialLibrary.load(path) if path.is_file() else MaterialLibrary()
    existing.add(replace(entry, status="user"), replace_existing=replace_existing)
    return existing.save(path)
