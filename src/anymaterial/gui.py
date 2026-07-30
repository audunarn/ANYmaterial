"""A tkinter material library and editor.

Three panes: the library on the left, the material being edited in the middle,
what that material implies on the right.

Validation runs on every keystroke because the interesting failures here are not
typos but combinations -- three Poisson ratios that are individually sensible and
jointly describe a material that releases energy under load.  Telling the user at
the point of entry is the whole value of a form over a JSON file.

The curve panel plots the material being edited together with whatever is
selected in the library, so a new material can be seen against the grades it is
meant to sit near rather than in isolation.

Flow curves are drawn on a plain ``Canvas``, so the editor adds no dependency
beyond the standard library.  The same curves go to SVG through
:mod:`anymaterial.plot` when they need to leave the window.

Nothing here is imported by ``anymaterial/__init__.py``, so importing the package
never requires a display or a tkinter build.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .contract import material_symmetry
from .library import (
    LibraryEntry,
    MaterialLibrary,
    add_to_user_library,
    available_grades,
    library,
    user_library_path,
)
from .plot import _PALETTE, DEFAULT_MAX_STRAIN, sample_curve, write_curve_svg
from .reductions import beam_material_properties, shell_material_matrices
from .spec import MaterialSpec, load_specs, save_specs
from .validation import material_validation_errors

__all__ = ["MaterialEditor", "main"]


_SYMMETRIES = ("isotropic", "orthotropic")

_HARDENING_KINDS = ("none", "dnv_c208", "linear", "power_law")

# (key, label, default).  Fields whose key contains "modulus" are entered in GPa.
_Field = Tuple[str, str, str]

_ISOTROPIC_FIELDS: Tuple[_Field, ...] = (
    ("elastic_modulus", "E [GPa]", "210"),
    ("poisson_ratio", "nu [-]", "0.3"),
)

_ORTHOTROPIC_FIELDS: Tuple[_Field, ...] = (
    ("elastic_modulus_1", "E1 [GPa]", "150"),
    ("elastic_modulus_2", "E2 [GPa]", "10"),
    ("elastic_modulus_3", "E3 [GPa]", "8"),
    ("poisson_ratio_12", "nu12 [-]", "0.25"),
    ("poisson_ratio_13", "nu13 [-]", "0.20"),
    ("poisson_ratio_23", "nu23 [-]", "0.30"),
    ("shear_modulus_12", "G12 [GPa]", "5"),
    ("shear_modulus_13", "G13 [GPa]", "4"),
    ("shear_modulus_23", "G23 [GPa]", "3"),
)

_HARDENING_FIELDS: Dict[str, Tuple[_Field, ...]] = {
    "dnv_c208": (("thickness", "Thickness [mm]", "10"),),
    "linear": (
        ("sigma_yield", "sigma_y [MPa]", "355"),
        ("hardening_modulus", "H [MPa]", "2000"),
    ),
    "power_law": (
        ("sigma_yield", "sigma_y [MPa]", "355"),
        ("K", "K [MPa]", "740"),
        ("n", "n [-]", "0.166"),
    ),
}

# Moduli are entered in GPa and stresses in MPa because that is how they are
# quoted on a drawing; the package itself is strictly SI, so the conversion
# happens here at the edge and nowhere else.
_GPA = 1.0e9
_MPA = 1.0e6

_STATUS_COLOURS = {
    "tabulated": "#006000",
    "indicative": "#8a5a00",
    "user": "#1a5fb4",
}


class MaterialEditor(ttk.Frame):
    """The library browser and editor, as a frame so it can be embedded."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=8)
        self._constant_vars: Dict[str, tk.StringVar] = {}
        self._hardening_vars: Dict[str, tk.StringVar] = {}
        self._current_spec: Optional[MaterialSpec] = None
        self._message: str = ""
        self._library: MaterialLibrary = library()

        self.columnconfigure(2, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_library_pane()
        self._build_form()
        self._build_report()
        self._rebuild_constant_fields()
        self._rebuild_hardening_fields()
        self._refresh_library_tree()

    # --------------------------------------------------------------- library

    def _build_library_pane(self) -> None:
        pane = ttk.Frame(self)
        pane.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        pane.rowconfigure(2, weight=1)

        ttk.Label(pane, text="Library", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        filters = ttk.Frame(pane)
        filters.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        self._search = tk.StringVar()
        ttk.Entry(filters, textvariable=self._search, width=16).pack(side="left")
        self._search.trace_add("write", lambda *_: self._refresh_library_tree())
        self._only_nonlinear = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filters, text="curves", variable=self._only_nonlinear,
            command=self._refresh_library_tree,
        ).pack(side="left", padx=(4, 0))

        self._tree = ttk.Treeview(
            pane, columns=("category", "status"), show="tree headings", height=18, selectmode="extended"
        )
        self._tree.heading("#0", text="Material")
        self._tree.heading("category", text="Category")
        self._tree.heading("status", text="Status")
        self._tree.column("#0", width=190, anchor="w")
        self._tree.column("category", width=110, anchor="w")
        self._tree.column("status", width=80, anchor="w")
        self._tree.grid(row=2, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(pane, orient="vertical", command=self._tree.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.bind("<<TreeviewSelect>>", lambda _event: self._on_library_select())
        for status, colour in _STATUS_COLOURS.items():
            self._tree.tag_configure(status, foreground=colour)

        buttons = ttk.Frame(pane)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Load", command=self.load_selected).pack(side="left")
        ttk.Button(buttons, text="Add current...", command=self.add_current_to_library).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="Export SVG...", command=self.export_svg).pack(side="left")

    def _refresh_library_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        entries = self._library.find(
            text=self._search.get() or None,
            nonlinear=True if self._only_nonlinear.get() else None,
        )
        for entry in entries:
            self._tree.insert(
                "",
                "end",
                iid=entry.name,
                text=entry.name,
                values=(entry.category, entry.status),
                tags=(entry.status,),
            )

    @property
    def selected_entries(self) -> List[LibraryEntry]:
        """The library entries currently selected."""

        return [self._library.get(name) for name in self._tree.selection()]

    def _on_library_select(self) -> None:
        entries = self.selected_entries
        if entries:
            self._show_provenance(entries[0])
        self._draw_curve()

    def _show_provenance(self, entry: LibraryEntry) -> None:
        lines = [f"{entry.name}  [{entry.status}]"]
        if entry.standard:
            lines.append(f"standard: {entry.standard}")
        if entry.source:
            lines.append(f"source:   {entry.source}")
        if entry.tensile_strength:
            lines.append(f"tensile:  {entry.tensile_strength / _MPA:.0f} MPa")
        if not entry.is_design_value:
            # The whole risk this library carries is a looked-up number being
            # used as a design value, so it is said on the entry itself.
            lines.append("NOT a design value - verify against the governing standard.")
        if entry.notes:
            lines.append("")
            lines.append(entry.notes)
        self._provenance.configure(text="\n".join(lines))

    def load_selected(self) -> None:
        """Load the first selected library material into the form."""

        entries = self.selected_entries
        if not entries:
            messagebox.showinfo("Load", "select a material in the library first")
            return
        self.write_spec(entries[0].spec)

    def add_current_to_library(self) -> None:
        """Add the material in the form to the user's library file."""

        if self._current_spec is None:
            messagebox.showerror("Add failed", "the material is not valid; fix it before adding")
            return
        category = simpledialog.askstring(
            "Add to library", "Category:", initialvalue="other", parent=self
        )
        if category is None:
            return
        entry = LibraryEntry(spec=self._current_spec, category=category or "other", status="user")
        try:
            path = add_to_user_library(entry)
        except ValueError:
            if not messagebox.askyesno(
                "Already in the library",
                f"A material named {entry.name!r} already exists. Replace it?",
            ):
                return
            path = add_to_user_library(entry, replace_existing=True)
        except OSError as error:
            messagebox.showerror("Add failed", str(error))
            return
        self._library = library()
        self._refresh_library_tree()
        messagebox.showinfo("Added", f"{entry.name!r} written to {path}")

    def export_svg(self) -> None:
        """Write the plotted curves to an SVG file."""

        series = self._plot_series()
        if not series:
            messagebox.showinfo("Export", "there are no flow curves to plot")
            return
        path = filedialog.asksaveasfilename(
            title="Export curves", defaultextension=".svg", filetypes=[("SVG", "*.svg")]
        )
        if not path:
            return
        try:
            write_curve_svg(path, series, overwrite=True, title="Flow curves")
        except OSError as error:
            messagebox.showerror("Export failed", str(error))

    # ------------------------------------------------------------------ form

    def _build_form(self) -> None:
        form = ttk.Frame(self)
        form.grid(row=0, column=1, sticky="nsew", padx=(0, 8))

        row = 0
        self._material_name = self._labelled_entry(form, row, "Name", "steel", width=24)

        row += 1
        ttk.Label(form, text="Symmetry").grid(row=row, column=0, sticky="w")
        self._symmetry = tk.StringVar(value="isotropic")
        symmetry_box = ttk.Combobox(
            form, textvariable=self._symmetry, values=_SYMMETRIES, state="readonly", width=21
        )
        symmetry_box.grid(row=row, column=1, sticky="ew", pady=2)
        symmetry_box.bind("<<ComboboxSelected>>", lambda _event: self._rebuild_constant_fields())

        row += 1
        self._density = self._labelled_entry(form, row, "Density [kg/m3]", "7850", width=24)

        row += 1
        self._yield_stress = self._labelled_entry(form, row, "Yield stress [MPa]", "355", width=24)

        row += 1
        self._constants_frame = ttk.LabelFrame(form, text="Elastic constants", padding=6)
        self._constants_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        self._constants_frame.columnconfigure(1, weight=1)

        row += 1
        ttk.Label(form, text="Hardening").grid(row=row, column=0, sticky="w")
        self._hardening_kind = tk.StringVar(value="none")
        hardening_box = ttk.Combobox(
            form, textvariable=self._hardening_kind, values=_HARDENING_KINDS,
            state="readonly", width=21,
        )
        hardening_box.grid(row=row, column=1, sticky="ew", pady=2)
        hardening_box.bind("<<ComboboxSelected>>", lambda _event: self._rebuild_hardening_fields())

        row += 1
        self._hardening_frame = ttk.LabelFrame(form, text="Hardening parameters", padding=6)
        self._hardening_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        self._hardening_frame.columnconfigure(1, weight=1)

        row += 1
        buttons = ttk.Frame(form)
        buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Load file...", command=self.load).pack(side="left")
        ttk.Button(buttons, text="Save as...", command=self.save).pack(side="left", padx=4)

    def _labelled_entry(
        self, parent: tk.Misc, row: int, label: str, default: str, *, width: int = 16
    ) -> tk.StringVar:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        variable = tk.StringVar(value=default)
        ttk.Entry(parent, textvariable=variable, width=width).grid(
            row=row, column=1, sticky="ew", pady=2
        )
        variable.trace_add("write", lambda *_: self.refresh())
        return variable

    def _entry_grid(
        self, parent: tk.Misc, fields: Sequence[_Field], *, start_row: int = 0
    ) -> Dict[str, tk.StringVar]:
        return {
            key: self._labelled_entry(parent, start_row + index, label, default, width=13)
            for index, (key, label, default) in enumerate(fields)
        }

    def _rebuild_constant_fields(self) -> None:
        for child in self._constants_frame.winfo_children():
            child.destroy()
        fields = _ISOTROPIC_FIELDS if self._symmetry.get() == "isotropic" else _ORTHOTROPIC_FIELDS
        self._constant_vars = self._entry_grid(self._constants_frame, fields)
        self.refresh()

    def _rebuild_hardening_fields(self) -> None:
        for child in self._hardening_frame.winfo_children():
            child.destroy()
        self._hardening_vars = {}
        kind = self._hardening_kind.get()
        start_row = 0
        if kind == "dnv_c208":
            ttk.Label(self._hardening_frame, text="Grade").grid(row=0, column=0, sticky="w")
            self._grade = tk.StringVar(value="S355")
            grade_box = ttk.Combobox(
                self._hardening_frame, textvariable=self._grade,
                values=list(available_grades()), state="readonly", width=10,
            )
            grade_box.grid(row=0, column=1, sticky="ew", pady=1)
            grade_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
            start_row = 1
        self._hardening_vars = self._entry_grid(
            self._hardening_frame, _HARDENING_FIELDS.get(kind, ()), start_row=start_row
        )
        self.refresh()

    # ---------------------------------------------------------------- report

    def _build_report(self) -> None:
        report = ttk.Frame(self)
        report.grid(row=0, column=2, sticky="nsew")
        report.columnconfigure(0, weight=1)
        report.rowconfigure(3, weight=1)

        self._status = ttk.Label(report, text="", anchor="w", wraplength=460, justify="left")
        self._status.grid(row=0, column=0, sticky="ew")

        self._derived = ttk.Label(
            report, text="", anchor="w", justify="left", font=("TkFixedFont", 9)
        )
        self._derived.grid(row=1, column=0, sticky="ew", pady=(6, 6))

        provenance = ttk.LabelFrame(report, text="Selected library material", padding=6)
        provenance.grid(row=2, column=0, sticky="ew")
        provenance.columnconfigure(0, weight=1)
        self._provenance = ttk.Label(
            provenance, text="nothing selected", anchor="w", justify="left",
            wraplength=440, font=("TkDefaultFont", 8),
        )
        self._provenance.grid(row=0, column=0, sticky="ew")

        curve_frame = ttk.LabelFrame(
            report, text="Flow curves (true stress / true plastic strain)", padding=4
        )
        curve_frame.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        curve_frame.columnconfigure(0, weight=1)
        curve_frame.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(
            curve_frame, width=460, height=260, background="white", highlightthickness=0
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", lambda _event: self._draw_curve())

    # ------------------------------------------------------------ conversion

    @property
    def status_text(self) -> str:
        """The message currently shown to the user."""

        return self._message

    @property
    def spec(self) -> Optional[MaterialSpec]:
        """The valid specification the form describes, or ``None``."""

        return self._current_spec

    @property
    def library_names(self) -> Tuple[str, ...]:
        """Every material name currently listed."""

        return tuple(self._tree.get_children())

    def read_spec(self) -> MaterialSpec:
        """Build a specification from the form, converting to SI."""

        constants: Dict[str, float] = {}
        for key, variable in self._constant_vars.items():
            value = float(variable.get())
            constants[key] = value * _GPA if "modulus" in key else value

        hardening: Optional[Dict[str, Any]] = None
        kind = self._hardening_kind.get()
        if kind == "dnv_c208":
            hardening = {
                "kind": "dnv_c208",
                "grade": self._grade.get(),
                # Entered in mm because plate thickness is quoted in mm.
                "thickness": float(self._hardening_vars["thickness"].get()) / 1000.0,
            }
        elif kind == "linear":
            hardening = {
                "kind": "linear",
                "sigma_yield": float(self._hardening_vars["sigma_yield"].get()) * _MPA,
                "hardening_modulus": float(self._hardening_vars["hardening_modulus"].get()) * _MPA,
            }
        elif kind == "power_law":
            hardening = {
                "kind": "power_law",
                "sigma_yield": float(self._hardening_vars["sigma_yield"].get()) * _MPA,
                "K": float(self._hardening_vars["K"].get()) * _MPA,
                "n": float(self._hardening_vars["n"].get()),
            }

        return MaterialSpec(
            name=self._material_name.get(),
            symmetry=self._symmetry.get(),
            constants=constants,
            density=float(self._density.get()),
            yield_stress=float(self._yield_stress.get()) * _MPA,
            hardening=hardening,
        )

    def write_spec(self, spec: MaterialSpec) -> None:
        """Load a specification into the form, converting from SI."""

        self._material_name.set(spec.name)
        self._symmetry.set(spec.symmetry)
        self._rebuild_constant_fields()
        for key, variable in self._constant_vars.items():
            value = float(spec.constants.get(key, 0.0))
            variable.set(f"{value / _GPA:g}" if "modulus" in key else f"{value:g}")
        self._density.set(f"{float(spec.density):g}")
        self._yield_stress.set(f"{float(spec.yield_stress) / _MPA:g}")

        hardening = dict(spec.hardening or {})
        kind = str(hardening.get("kind", "none"))
        editable = kind in _HARDENING_KINDS
        self._hardening_kind.set(kind if editable else "none")
        self._rebuild_hardening_fields()
        if kind == "dnv_c208":
            self._grade.set(str(hardening.get("grade", "S355")))
            self._hardening_vars["thickness"].set(
                f"{float(hardening.get('thickness', 0.01)) * 1000.0:g}"
            )
        elif editable:
            for key, variable in self._hardening_vars.items():
                if key in hardening:
                    value = float(hardening[key])
                    variable.set(f"{value:g}" if key == "n" else f"{value / _MPA:g}")
        self.refresh()
        if not editable:
            # Reported rather than quietly reset to elastic, which would drop the
            # curve on the next save -- what the specification format exists to
            # prevent.
            self._set_status(
                f"loaded material uses hardening kind {kind!r}, which this editor cannot edit",
                "#8a5a00",
            )

    # -------------------------------------------------------------- refresh

    def _set_status(self, message: str, colour: str) -> None:
        self._message = message
        self._status.configure(text=message, foreground=colour)

    def refresh(self) -> None:
        """Re-validate and redraw.  Called on every edit."""

        self._current_spec = None
        try:
            spec = self.read_spec()
        except (ValueError, KeyError, AttributeError) as error:
            self._set_status(f"incomplete input: {error}", "#8a5a00")
            self._derived.configure(text="")
            self._draw_curve()
            return

        try:
            material = spec.build()
        except ValueError as error:
            self._set_status(str(error), "#a00000")
            self._derived.configure(text="")
            self._draw_curve()
            return

        errors = material_validation_errors(material)
        if errors:
            self._set_status("; ".join(errors), "#a00000")
            self._derived.configure(text="")
        else:
            self._current_spec = spec
            self._set_status(f"valid {material_symmetry(material)} material", "#006000")
            self._derived.configure(text=self._derived_text(material))
        self._draw_curve()

    @staticmethod
    def _derived_text(material: Any) -> str:
        plane_stress, transverse_shear, drilling = shell_material_matrices(material)
        beam = beam_material_properties(material)
        return "\n".join(
            [
                "shell plane stress Q [GPa]",
                *(
                    "  " + "  ".join(f"{value / _GPA:9.3f}" for value in row)
                    for row in plane_stress
                ),
                f"transverse shear  G13 {transverse_shear[0, 0] / _GPA:.3f}  "
                f"G23 {transverse_shear[1, 1] / _GPA:.3f} GPa",
                f"drilling shear    {drilling / _GPA:.3f} GPa",
                f"beam              E {beam.axial_modulus / _GPA:.3f}  "
                f"Gxy {beam.shear_modulus_xy / _GPA:.3f}  "
                f"Gxz {beam.shear_modulus_xz / _GPA:.3f} GPa",
            ]
        )

    # ----------------------------------------------------------------- plot

    def _plot_series(self) -> List[Any]:
        """The curves to draw: the edited material, then the library selection."""

        series = []
        if self._current_spec is not None:
            try:
                curve = self._current_spec.hardening_curve()
            except ValueError:
                curve = None
            if curve is not None:
                series.append(sample_curve(curve, self._current_spec.name))
        for entry in self.selected_entries:
            if entry.name == getattr(self._current_spec, "name", None):
                continue
            try:
                curve = entry.spec.hardening_curve()
            except ValueError:
                continue
            if curve is not None:
                series.append(sample_curve(curve, entry.name))
        return series

    def _draw_curve(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        width = max(int(canvas.winfo_width()), 160)
        height = max(int(canvas.winfo_height()), 120)
        left, right, top, bottom = 58, 12, 12, 30

        series = self._plot_series()
        if not series:
            canvas.create_text(
                width // 2, height // 2, text="elastic - no hardening curve", fill="#909090"
            )
            return

        stress_max = max(item.max_stress for item in series) / _MPA * 1.05
        span = max(stress_max, 1.0e-9)

        def to_pixel(strain: float, stress_mpa: float) -> Tuple[float, float]:
            x = left + (width - left - right) * strain / DEFAULT_MAX_STRAIN
            y = height - bottom - (height - top - bottom) * stress_mpa / span
            return x, y

        canvas.create_line(left, top, left, height - bottom, fill="#606060")
        canvas.create_line(left, height - bottom, width - right, height - bottom, fill="#606060")
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            stress = span * fraction
            _x, y = to_pixel(0.0, stress)
            canvas.create_line(left - 4, y, left, y, fill="#606060")
            canvas.create_text(left - 6, y, text=f"{stress:.0f}", anchor="e", fill="#404040")
            strain = DEFAULT_MAX_STRAIN * fraction
            x, _y = to_pixel(strain, 0.0)
            canvas.create_text(
                x, height - bottom + 12, text=f"{strain:.3f}", anchor="n", fill="#404040"
            )
        canvas.create_text(left - 6, top, text="MPa", anchor="se", fill="#404040")
        canvas.create_text(
            width - right, height - bottom + 12, text="eps_p", anchor="ne", fill="#404040"
        )

        for index, item in enumerate(series):
            colour = _PALETTE[index % len(_PALETTE)]
            points: List[float] = []
            for strain, stress in zip(item.plastic_strain, item.flow_stress):
                x, y = to_pixel(float(strain), float(stress) / _MPA)
                points.extend((x, y))
            canvas.create_line(*points, fill=colour, width=2)
            canvas.create_text(
                left + 8, top + 8 + index * 14, text=item.label, anchor="w",
                fill=colour, font=("TkDefaultFont", 8),
            )

    # ------------------------------------------------------------ file menu

    def load(self) -> None:
        path = filedialog.askopenfilename(
            title="Load material", filetypes=[("Material JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            specs = load_specs(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Load failed", str(error))
            return
        if not specs:
            messagebox.showerror("Load failed", "the file contains no materials")
            return
        if len(specs) > 1:
            messagebox.showinfo(
                "Multiple materials",
                f"the file contains {len(specs)} materials; loading the first, {specs[0].name!r}",
            )
        self.write_spec(specs[0])

    def save(self) -> None:
        if self._current_spec is None:
            messagebox.showerror("Save failed", "the material is not valid; fix it before saving")
            return
        path = filedialog.asksaveasfilename(
            title="Save material", defaultextension=".json", filetypes=[("Material JSON", "*.json")]
        )
        if not path:
            return
        try:
            save_specs(path, [self._current_spec], overwrite=True)
        except OSError as error:
            messagebox.showerror("Save failed", str(error))


def main(argv: Optional[List[str]] = None) -> int:
    """Open the library and editor."""

    root = tk.Tk()
    root.title(f"ANYmaterial - user library: {user_library_path()}")
    root.minsize(1180, 560)
    editor = MaterialEditor(root)
    editor.pack(fill="both", expand=True)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
