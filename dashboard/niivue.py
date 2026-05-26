"""Niivue WebGL viewer embedded in Streamlit via st.components.v1.html.

`render_brain_view` accepts a list of (path, modality, colormap, opacity) tuples
and emits the HTML+JS needed to render them as a stack inside an iframe.
The first volume is the base; subsequent volumes are overlays.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import streamlit.components.v1 as components

NIIVUE_CDN = "https://unpkg.com/@niivue/niivue@latest/dist/niivue.umd.js"


@dataclass(frozen=True)
class VolumeLayer:
    path: Path
    colormap: str = "gray"
    opacity: float = 1.0


def _encode_volume(path: Path) -> str:
    """Read a NIfTI file and return a base64 data URL.

    Niivue accepts data URLs for `volumes[].url`, so we inline the file bytes
    rather than serving them over HTTP. Fine at ~50–100 MB per volume.
    """
    data = path.read_bytes()
    return "data:application/octet-stream;base64," + base64.b64encode(data).decode("ascii")


def render_brain_view(layers: list[VolumeLayer], *, height: int = 600) -> None:
    """Render a niivue 3D view of the given volume stack.

    The first layer is the base; later layers are overlays in z-order.
    """
    if not layers:
        raise ValueError("render_brain_view requires at least one VolumeLayer")

    volumes_js = []
    for layer in layers:
        url = _encode_volume(layer.path)
        volumes_js.append(
            f'{{ url: "{url}", name: "{layer.path.name}", '
            f'colormap: "{layer.colormap}", opacity: {layer.opacity} }}'
        )
    volumes_block = ",\n          ".join(volumes_js)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body {{ margin: 0; padding: 0; background: #000; height: 100%; }}
    #gl {{ width: 100%; height: {height}px; display: block; }}
    #err {{ color: #f88; font-family: sans-serif; padding: 8px; display: none; }}
  </style>
</head>
<body>
  <canvas id="gl"></canvas>
  <div id="err"></div>
  <script src="{NIIVUE_CDN}"></script>
  <script>
    (async () => {{
      try {{
        const nv = new niivue.Niivue({{ show3Dcrosshair: true, isOrientCube: true }});
        await nv.attachTo("gl");
        await nv.loadVolumes([
          {volumes_block}
        ]);
        nv.setSliceType(nv.sliceTypeRender);
        window.__nv = nv;  // dev handle for console poking
      }} catch (e) {{
        const el = document.getElementById("err");
        el.style.display = "block";
        el.textContent = "niivue init failed: " + (e && e.message ? e.message : e);
        console.error(e);
      }}
    }})();
  </script>
</body>
</html>"""

    components.html(html, height=height + 20, scrolling=False)
