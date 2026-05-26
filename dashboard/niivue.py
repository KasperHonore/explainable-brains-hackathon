"""Niivue WebGL viewer embedded in Streamlit via st.components.v1.html.

Volumes are served by Streamlit's static-file mount at /app/static/<name>
(see .streamlit/config.toml: `server.enableStaticServing = true`).
The component iframe and the static mount share the Streamlit origin, so
relative URLs work without CORS headers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit.components.v1 as components

NIIVUE_CDN = "https://unpkg.com/@niivue/niivue@latest/dist/niivue.umd.js"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@dataclass(frozen=True)
class VolumeLayer:
    # `static_name` is the filename inside `static/` (a symlink into `data/`),
    # served by Streamlit at /app/static/<name>.
    static_name: str
    colormap: str = "gray"
    opacity: float = 1.0
    colormap_negative: str = ""  # niivue: paired colormap for negative voxels
    cal_min: float | None = None
    cal_max: float | None = None


def render_brain_view(layers: list[VolumeLayer], *, height: int = 600) -> None:
    if not layers:
        raise ValueError("render_brain_view requires at least one VolumeLayer")

    for layer in layers:
        path = STATIC_DIR / layer.static_name
        if not path.exists():
            raise FileNotFoundError(
                f"Expected {path} to exist (symlink into data/). "
                "Did `static/` get set up?"
            )

    volumes_js = []
    for layer in layers:
        # Absolute URL relative to the Streamlit origin. Works from inside the
        # components-iframe because Streamlit serves the iframe and the static
        # files from the same host:port.
        url = f"/app/static/{layer.static_name}"
        extras = [f'colormap: "{layer.colormap}"', f"opacity: {layer.opacity}"]
        if layer.colormap_negative:
            extras.append(f'colormapNegative: "{layer.colormap_negative}"')
        if layer.cal_min is not None:
            extras.append(f"cal_min: {layer.cal_min}")
        if layer.cal_max is not None:
            extras.append(f"cal_max: {layer.cal_max}")
        extras_str = ", ".join(extras)
        volumes_js.append(
            f'{{ url: "{url}", name: "{layer.static_name}", {extras_str} }}'
        )
    volumes_block = ",\n          ".join(volumes_js)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body {{ margin: 0; padding: 0; background: #000; height: 100%; }}
    #gl {{ width: 100%; height: {height}px; display: block; }}
    #status {{
      color: #ccc; font-family: sans-serif; padding: 6px 10px;
      position: absolute; top: 4px; left: 4px;
      background: rgba(0,0,0,0.4); border-radius: 4px;
      font-size: 12px; max-width: 80%;
    }}
    .err {{ color: #f88; }}
  </style>
</head>
<body>
  <canvas id="gl"></canvas>
  <div id="status">loading niivue…</div>
  <script src="{NIIVUE_CDN}"></script>
  <script>
    const status = document.getElementById("status");
    const log = (msg, isErr) => {{
      status.className = isErr ? "err" : "";
      status.textContent = msg;
      console[isErr ? "error" : "log"]("[niivue]", msg);
    }};
    (async () => {{
      try {{
        if (!window.niivue || !niivue.Niivue) {{
          throw new Error("niivue UMD did not load — check CDN reachability");
        }}
        const nv = new niivue.Niivue({{
          show3Dcrosshair: true,
          isOrientCube: true,
          backColor: [0, 0, 0, 1],
        }});
        await nv.attachTo("gl");
        log("loading volumes…");
        await nv.loadVolumes([
          {volumes_block}
        ]);
        log(`loaded ${{nv.volumes.length}} volume(s) — drag to rotate`);
        // Multiplanar (3 slices + 3D render) is niivue's most informative default.
        if (typeof nv.sliceTypeMultiplanar === "number") {{
          nv.setSliceType(nv.sliceTypeMultiplanar);
        }}
        window.__nv = nv;
        setTimeout(() => {{ status.style.display = "none"; }}, 3000);
      }} catch (e) {{
        log("init failed: " + (e && e.message ? e.message : e), true);
        console.error(e);
      }}
    }})();
  </script>
</body>
</html>"""

    components.html(html, height=height + 20, scrolling=False)
