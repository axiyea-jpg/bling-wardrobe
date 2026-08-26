# Third-party notices

## BodyApps Visualizer female model

This project vendors the female body mesh and legacy Three.js runtime from [OpnTec/bodyapps-viz](https://github.com/OpnTec/bodyapps-viz).

- Original copyright: Fashiontec / BodyApps contributors
- License: GNU Lesser General Public License v3.0
- Local license copy: `bodyapps/LICENSE`
- Modified integration: custom responsive viewer, clay-blue material, app measurement bindings, and mobile interaction.

The proprietary MPI Body Visualizer application and its restricted assets are not copied or redistributed here.

## 3D-Human-Body-Shape

- Source: https://github.com/zengyh1900/3D-Human-Body-Shape
- Code license: MIT
- Use: anthropometric measurement completion and local-RFE full-mesh reconstruction adapter.

The production container downloads the upstream released female local-RFE runtime weights during its build. The weights are not committed to this repository. Their training-data provenance must still be reviewed before commercial distribution.

## Wardrobe

- Source: https://github.com/tandpfun/wardrobe
- License: MIT
- Use: design reference for evidence-bound garment import, review and modeled outfit generation workflows.

## OpenAI image generation

Garment reconstruction and modeled outfit images can be generated through the OpenAI API when the private backend is configured. No API key is shipped to the browser.
