# Architecture

## Position in the family

```
ANYmaterial ──┐
              ├──→ ANYfileio ──┐
ANYmesher ────┘                ├──→ ANYsolver ──→ ANYfem
                               │         └──────→ ANYstructure
                               └────────────────→ ANYstructure
```

ANYmaterial is a leaf. It imports numpy and the standard library, and nothing
else in the family. That is not a stylistic preference: ANYsolver depends on
ANYmaterial, so any import in the other direction closes a cycle and the two
packages can no longer be versioned or released independently.
`tests/test_layering.py` enforces it by walking the AST of every module, because
the rule is one careless debug import away from being broken.

The same constraint decides where things live. A material *record* belongs here;
turning that record into a solver element's constitutive matrices at assembly
time belongs in ANYsolver. Where a function needs both, the neutral half is here
and the adapter is there.

## Conventions

**Units.** SI throughout: Pa for stress and moduli, kg/m³ for density, m for
length, dimensionless strain. There is no conversion layer, so a value in MPa is
a bug rather than a supported alternative. The RP-C208 tables are tabulated in
MPa in the source document and converted once, at the data-file boundary.

**Voigt order.** `[11, 22, 33, 23, 13, 12]`, engineering (shear strains are
angles, not tensor components):

```
[eps11, eps22, eps33, gamma23, gamma13, gamma12] = S @ [sig11, sig22, sig33, tau23, tau13, tau12]
```

This package defines the family convention. Consumers match it; nobody
transposes at the boundary.

**Compliance, not constants.** Reductions are computed from the 6x6 compliance
rather than from re-entered engineering constants, so an isotropic and an
orthotropic material reach a shell or beam formulation by the same path and
there is one place for the algebra to be wrong.

## Structural typing at the boundary

ANYsolver accepts any object satisfying its material protocol — a name, a
density, a declared elastic symmetry and an `elastic_compliance_matrix()`. It
does not require inheritance from anything here. That is what lets ANYmaterial
supply materials across a repository boundary without either side importing the
other's classes, and it is why validation is written against attributes rather
than against types.

The same applies to hardening curves: a curve is anything with
`flow_stress(alpha)` and `hardening_modulus(alpha)` accepting and returning
numpy arrays. Vectorization is part of the contract, not an optimization — the
solver's return mapping calls these for every integration point and thickness
layer at once.

## Failing closed

Where the source material is silent, this package raises rather than
extrapolates. A plate thickness outside a tabulated RP-C208 range is an error,
not an invitation to use the nearest row; mean curves the recommended practice
does not tabulate are unavailable rather than interpolated. A material that
quietly returns plausible numbers outside its qualified range is worse than one
that refuses, because the refusal is visible and the plausible number is not.
