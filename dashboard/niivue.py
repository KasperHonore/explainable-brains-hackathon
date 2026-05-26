"""Niivue WebGL viewer.

DIFFERENCE mode goes through a Streamlit custom component
(`dashboard/brain_view/index.html`) so the labelmap voxel under the crosshair
can be posted back to Python on mouseup / Z-slider release.

COMPARE_GROUPS mode stays on the one-way `st.components.v1.html` path — no pick
needed when comparing two volumes side by side.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import streamlit.components.v1 as components

# Pin a recent build — @latest broke layouts before.
NIIVUE_CDN = "https://unpkg.com/@niivue/niivue@0.68.1/dist/niivue.umd.js"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_COMPONENT_DIR = Path(__file__).resolve().parent / "brain_view"

_brain_view = components.declare_component("brain_view", path=str(_COMPONENT_DIR))


class BrainViewMode(str, Enum):
    DIFFERENCE = "difference"
    COMPARE_GROUPS = "compare"


@dataclass(frozen=True)
class VolumeLayer:
    static_name: str
    colormap: str = "gray"
    opacity: float = 1.0
    colormap_negative: str = ""
    # For divergent overlays, cal_min acts as a symmetric threshold —
    # voxels with |value| < cal_min render transparent.
    cal_min: float | None = None
    cal_max: float | None = None


@dataclass(frozen=True)
class ViewerSpec:
    """One Niivue canvas worth of volumes."""

    canvas_id: str
    label: str
    layers: list[VolumeLayer] = field(default_factory=list)


def _layer_to_js(layer: VolumeLayer) -> str:
    url = f"/app/static/{layer.static_name}"
    extras = [f'colormap: "{layer.colormap}"', f"opacity: {layer.opacity}"]
    if layer.colormap_negative:
        extras.append(f'colormapNegative: "{layer.colormap_negative}"')
    if layer.cal_min is not None:
        extras.append(f"cal_min: {layer.cal_min}")
    if layer.cal_max is not None:
        extras.append(f"cal_max: {layer.cal_max}")
    return f'{{ url: "{url}", name: "{layer.static_name}", {", ".join(extras)} }}'


def _check_static(layers: list[VolumeLayer]) -> None:
    for layer in layers:
        path = STATIC_DIR / layer.static_name
        if not path.exists():
            raise FileNotFoundError(
                f"Expected {path} (run data.ensure_static_volumes() first)."
            )


def render_brain_view(
    layers: list[VolumeLayer],
    *,
    height: int = 600,
    mode: BrainViewMode = BrainViewMode.DIFFERENCE,
    regions_layer_name: str = "",
    key: str = "brain_view",
) -> Optional[dict[str, Any]]:
    """Render the brain viewer.

    DIFFERENCE mode returns the latest crosshair pick (or None until the user
    interacts). `regions_layer_name` selects which loaded layer is queried for
    the atlas label — typically "regions.nii.gz", loaded with opacity 0 so it
    stays invisible.

    COMPARE_GROUPS mode always returns None — it uses the one-way
    `components.html` path and ignores `layers`.
    """
    if mode == BrainViewMode.COMPARE_GROUPS:
        specs = [
            ViewerSpec(
                canvas_id="gl-g001",
                label="Vehicle (G001)",
                layers=[
                    VolumeLayer("anatomy.nii.gz", colormap="gray", opacity=1.0),
                    VolumeLayer("g001.nii.gz", colormap="warm", opacity=0.75),
                ],
            ),
            ViewerSpec(
                canvas_id="gl-g002",
                label="Semaglutide (G002)",
                layers=[
                    VolumeLayer("anatomy.nii.gz", colormap="gray", opacity=1.0),
                    VolumeLayer("g002.nii.gz", colormap="warm", opacity=0.75),
                ],
            ),
        ]
        for spec in specs:
            _check_static(spec.layers)
        html = _html_compare(specs, height=height)
        components.html(html, height=height + 36, scrolling=False)
        return None

    if not layers:
        raise ValueError("DIFFERENCE mode requires at least one overlay layer")
    _check_static(layers)

    layer_specs = [
        {
            "url": f"/app/static/{layer.static_name}",
            "name": layer.static_name,
            "colormap": layer.colormap,
            "opacity": layer.opacity,
            "colormapNegative": layer.colormap_negative or None,
            "cal_min": layer.cal_min,
            "cal_max": layer.cal_max,
        }
        for layer in layers
    ]

    return _brain_view(
        layers=layer_specs,
        regions_layer_name=regions_layer_name,
        height=height,
        label="G002 − G001",
        key=key,
        default=None,
    )


def _html_compare(specs: list[ViewerSpec], *, height: int) -> str:
    panels = "\n".join(
        f"""
    <div class="compare-panel">
      <div class="panel-label">{spec.label}</div>
      <canvas id="{spec.canvas_id}"></canvas>
    </div>"""
        for spec in specs
    )
    volumes_by_canvas = {
        spec.canvas_id: ",\n          ".join(_layer_to_js(layer) for layer in spec.layers)
        for spec in specs
    }
    init = _init_script(specs, volumes_by_canvas=volumes_by_canvas)
    return _html_shell(
        height=height,
        body=f"""
  <div class="viewer-shell compare-mode">
    <div class="compare-row">{panels}
    </div>
    {_z_rail_html()}
  </div>
""",
        init_script=init,
    )


def _z_rail_html() -> str:
    return """
    <div class="z-rail">
      <span class="z-title">Z</span>
      <input type="range" id="zSlider" min="0" max="1" value="0" orient="vertical" />
      <span id="zLabel" class="z-label">…</span>
    </div>"""


def _html_shell(*, height: int, body: str, init_script: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body {{ margin: 0; padding: 0; background: #0a0a0a; height: 100%; color: #ccc;
      font-family: system-ui, sans-serif; }}
    .viewer-shell {{ display: flex; height: {height}px; width: 100%; }}
    .compare-mode .compare-row {{ flex: 1; display: flex; gap: 6px; min-width: 0; }}
    .compare-panel {{ flex: 1; display: flex; flex-direction: column; min-width: 0;
      background: #000; border-radius: 4px; overflow: hidden; }}
    .panel-label, .canvas-label {{
      font-size: 11px; padding: 4px 8px; background: rgba(0,0,0,0.55);
      position: absolute; top: 6px; left: 6px; z-index: 2; border-radius: 3px;
    }}
    .canvas-wrap {{ position: relative; flex: 1; min-width: 0; height: 100%; }}
    .compare-row {{ height: 100%; }}
    .compare-panel {{
      position: relative; flex: 1; min-width: 0; height: 100%;
      display: flex; flex-direction: column;
    }}
    .compare-panel .panel-label {{
      position: static; flex-shrink: 0; text-align: center;
    }}
    .compare-panel canvas, .canvas-wrap canvas {{
      flex: 1; width: 100%; min-height: 0; display: block;
    }}
    .z-rail {{
      width: 56px; flex-shrink: 0; display: flex; flex-direction: column;
      align-items: center; padding: 10px 6px; background: #141414;
      border-left: 1px solid #333; gap: 8px;
    }}
    .z-title {{ font-size: 11px; font-weight: 600; letter-spacing: 0.05em; }}
    #zSlider {{
      flex: 1; width: 28px; accent-color: #6af;
      writing-mode: vertical-lr; direction: rtl;
    }}
    .z-label {{ font-size: 10px; text-align: center; line-height: 1.2; max-width: 52px; }}
    #status {{
      color: #aaa; font-size: 11px; padding: 4px 10px;
      border-top: 1px solid #222;
    }}
    .err {{ color: #f88; }}
  </style>
</head>
<body>
{body}
  <div id="status">loading…</div>
  <script src="{NIIVUE_CDN}"></script>
  <script>
    {init_script}
  </script>
</body>
</html>"""


def _init_script(specs: list[ViewerSpec], *, volumes_by_canvas: dict[str, str]) -> str:
    """JavaScript shared by single and compare layouts."""
    inits = []
    for spec in specs:
        vols = volumes_by_canvas[spec.canvas_id]
        inits.append(
            f'await initViewer("{spec.canvas_id}", [{vols}])'
        )
    inits_block = "\n      ".join(inits)
    return f"""
    const status = document.getElementById("status");
    const log = (msg, isErr) => {{
      status.className = isErr ? "err" : "";
      status.textContent = msg;
      console[isErr ? "error" : "log"]("[niivue]", msg);
    }};

    const viewers = [];

    async function initViewer(canvasId, volumeList) {{
      if (!window.niivue || !niivue.Niivue) {{
        throw new Error("Niivue failed to load");
      }}
      const canvas = document.getElementById(canvasId);
      const nv = new niivue.Niivue({{
        show3Dcrosshair: true,
        isOrientCube: true,
        backColor: [0, 0, 0, 1],
      }});
      await nv.attachToCanvas(canvas);
      await nv.loadVolumes(volumeList);
      // Single full-canvas 3D render — not multiplanar (no 2×2 slice grid).
      nv.setSliceType(nv.sliceTypeRender);
      if (nv.opts) {{
        nv.opts.multiplanarShowRender = 0; // SHOW_RENDER.NEVER
      }}
      viewers.push(nv);
      window.__brainViewers = viewers;
      return nv;
    }}

    function volumeDims(nv) {{
      const hdr = nv.volumes[0]?.hdr;
      if (!hdr || !hdr.dims) return {{ nx: 1, ny: 1, nz: 1 }};
      return {{ nx: hdr.dims[1], ny: hdr.dims[2], nz: hdr.dims[3] }};
    }}

    function applyZ(z) {{
      const slider = document.getElementById("zSlider");
      const label = document.getElementById("zLabel");
      for (const nv of viewers) {{
        const {{ nx, ny, nz }} = volumeDims(nv);
        const zi = Math.max(0, Math.min(nz - 1, z));
        const cx = Math.floor(nx / 2);
        const cy = Math.floor(ny / 2);
        nv.moveCrosshairInVox(cx, cy, zi);
        // Clip plane: reveal tissue below this Z (superior → inferior slider).
        // depth in roughly [-0.6, 1.0] — top of range hides the plane outside
        // the volume (no clip), bottom cuts deep into interior.
        const frac = nz > 1 ? zi / (nz - 1) : 0;
        const depth = 1.0 - frac * 1.6;
        if (typeof nv.setClipPlane === "function") {{
          nv.setClipPlane([depth, 0, 90]);
        }}
        nv.drawScene();
        if (nv === viewers[0]) {{
          label.textContent = `slice ${{zi + 1}} / ${{nz}}`;
          slider.value = String(zi);
          slider.max = String(nz - 1);
        }}
      }}
    }}

    (async () => {{
      try {{
        {inits_block}
        const nz = volumeDims(viewers[0]).nz;
        const slider = document.getElementById("zSlider");
        slider.min = "0";
        slider.max = String(Math.max(0, nz - 1));
        slider.value = String(Math.floor((nz - 1) / 2));
        slider.addEventListener("input", () => applyZ(parseInt(slider.value, 10)));
        applyZ(parseInt(slider.value, 10));
        log(viewers.length > 1
          ? "Compare: drag either brain to rotate · Z slider cuts both"
          : "Drag to rotate · Z slider cuts the volume");
        setTimeout(() => {{ status.style.opacity = "0.6"; }}, 4000);
      }} catch (e) {{
        log("init failed: " + (e && e.message ? e.message : e), true);
      }}
    }})();
    """
