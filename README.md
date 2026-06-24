# AETHER Local App

Run the full local application:

```powershell
.\run.ps1
```

Then open:

```text
http://127.0.0.1:8000/app/
```

The backend stores all local data in `BACKEND/data`. It uses SQLite for users,
sessions, uploads, and tours. Uploaded room photos and generated panoramas stay
on this machine.

## Local Generation

The 360 tour generator is self-contained. It does not call Google, cloud AI, or
paid APIs. It uses Pillow and NumPy to synthesize an equirectangular panorama
from the uploaded room photo, then the existing Three.js viewer renders that
panorama with drag, wheel zoom, toolbar controls, and a joystick-style panner.

This is a deterministic local panorama synthesis pipeline, not a trained
photorealistic depth/inpainting model. Training a high-quality single-image
room-to-360 model requires a large licensed panorama dataset and GPU training
time; no such external dataset is bundled here.
