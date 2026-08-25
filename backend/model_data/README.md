# Anthropometric model files

Place the licensed female model files exported from `zengyh1900/3D-Human-Body-Shape`
in this directory before building the production container:

- `female_template.obj`
- `female_rfe.npz` containing `mean`, `components`, `coef`, `intercept` and
  optional `measurement_mean`

The service intentionally does not bundle research weights whose data provenance has
not yet been confirmed. It returns `503 body_model_unavailable` instead of silently
using the old segmented body mock.

