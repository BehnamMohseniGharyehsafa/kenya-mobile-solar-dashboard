# Field operations UI · November 2026

This redesign applies lighting, material, batching and responsive-checking
guidance from [Open 3D Skills](https://github.com/Moh4696/open-3d-skills), revision
`7b04ab491d5bcbd920cbffbf06ebae3f9429d8e3`, specifically `threejs-scene` and
`site-check`. The existing Python/VTK simulation is retained; the Three.js
starter is not copied or added as a second renderer.

- Olive/charcoal palette, compact navigation, four telemetry cards, a dedicated
  plant console and clear engineering/export sections.
- Responsive desktop, tablet and phone layouts, visible keyboard focus,
  reduced-motion styling, and full-size HMI controls.
- Dark monocrystalline cells with fine busbars, subdued enclosure materials,
  less opaque chain-link fencing, irregular spreading crowns, worn entrance
  tracks and feathered foundation contact shade. Static geometry stays batched.
- World-space directional sunlight and cool sky fill follow the model's solar
  position/cloud cover. The same lighting parameters drive PNG exports and the
  persistent browser scene. Camera orbit no longer moves a headlight around the
  equipment. A guarded adapter targets the pinned Dash VTK 0.0.9 bundle and fails
  explicitly if its two source anchors change.

Plant physics, deployment/retraction, wind and emergency-stop interlocks,
session isolation and the Render plan are preserved. Shadows remain analytical
projections onto a flat plane. The installation is a conceptual engineering
illustration, rather than a photogrammetric or surveyed digital twin.

The source release is identified as `field-operations-v3` at `/healthz`,
independently of older Render environment-variable values. Automatic deployment
remains disabled; publishing uses Render's manual deployment of the GitHub commit.

Browser QA uses available browser-control tools following the `site-check`
criteria: rendering, desktop/tablet/phone overflow, deployment/retraction,
camera/HMI controls and console errors. Headless WebKit and physical-phone GPU
performance are not verified by these checks.
