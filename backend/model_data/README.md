# Anthropometric model files

The production Docker build downloads the female local-RFE runtime files released in
`zengyh1900/3D-Human-Body-Shape` into this directory. The endpoint uses those matrices
to reconstruct all 12,500 vertices of one continuous body mesh and exports binary GLB.

If the released weights cannot be downloaded, the backend still generates a watertight
continuous implicit-surface GLB. It never returns the old independently scaled limb mock.
