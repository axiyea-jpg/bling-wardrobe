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

The adapter remains available for research comparison, but its reconstructed mesh is no longer displayed by the interactive Three.js body editor.

## Khronos glTF Sample Assets — CesiumMan

- Source: https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CesiumMan
- License: Creative Commons Attribution 4.0 International
- Use: temporary local SkinnedMesh/Skeleton GLB used to validate the rigged-body loading and smooth bone-chain deformation pipeline.

This is a replaceable technical base-model placeholder, not the final female visual asset.

## Wardrobe

- Source: https://github.com/tandpfun/wardrobe
- License: MIT
- Use: design reference for evidence-bound garment import, review and modeled outfit generation workflows.

## OpenAI image generation

Garment reconstruction and modeled outfit images can be generated through the OpenAI API when the private backend is configured. No API key is shipped to the browser.

## Local garment image stack

- rembg — MIT — optional local foreground segmentation: https://github.com/danielgatis/rembg
- OpenCV — Apache-2.0 — mask cleanup and crop support: https://opencv.org/
- Hugging Face Transformers and Diffusers — Apache-2.0 — optional local model adapters.

Individual model weights have their own licenses and provenance requirements and are not redistributed by this repository.

## Three.js

- Source: https://github.com/mrdoob/three.js (runtime version r128)
- License: MIT
- Use: local GLB viewer, orbit controls and GLTF loader for the existing 3D body-model page.
