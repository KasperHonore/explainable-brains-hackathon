"""Niivue WebGL viewer embedded in Streamlit via st.components.v1.html.

Default layout: one full-canvas 3D volume render (drag to rotate all axes) plus a
vertical Z slider on the right that moves the crosshair and clip plane.

Compare mode: side-by-side Vehicle (G001) vs Semaglutide (G002) with a shared Z slider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import streamlit.components.v1 as components

# Pin a recent build — @latest broke layouts before.
NIIVUE_CDN = "https://unpkg.com/@niivue/niivue@0.68.1/dist/niivue.umd.js"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
) -> None:
    """Render the brain viewer. `layers` is used for DIFFERENCE mode only."""
    if mode == BrainViewMode.COMPARE_GROUPS:
        # cal_min=4 hides background voxels below the p75-ish floor (G001/G002
        # signal: p50=2, p90=4-6, p99=8-12), cal_max=10 saturates the bright
        # regions, opacity 0.55 lets anatomy gray show through. Same idiom as
        # FIX-1 on the diff overlay.
        _g_signal_cal = dict(cal_min=4.0, cal_max=10.0)
        specs = [
            ViewerSpec(
                canvas_id="gl-g001",
                label="Vehicle (G001)",
                layers=[
                    VolumeLayer("anatomy.nii.gz", colormap="gray", opacity=1.0),
                    VolumeLayer("g001.nii.gz", colormap="warm", opacity=0.55, **_g_signal_cal),
                ],
            ),
            ViewerSpec(
                canvas_id="gl-g002",
                label="Semaglutide (G002)",
                layers=[
                    VolumeLayer("anatomy.nii.gz", colormap="gray", opacity=1.0),
                    VolumeLayer("g002.nii.gz", colormap="warm", opacity=0.55, **_g_signal_cal),
                ],
            ),
        ]
        html = _html_compare(specs, height=height)
    else:
        if not layers:
            raise ValueError("DIFFERENCE mode requires at least one overlay layer")
        html = _html_single(
            ViewerSpec(canvas_id="gl", label="G002 − G001", layers=layers),
            height=height,
        )

    components.html(html, height=height + 36, scrolling=False)


def _html_single(spec: ViewerSpec, *, height: int) -> str:
    _check_static(spec.layers)
    volumes_js = ",\n          ".join(_layer_to_js(layer) for layer in spec.layers)
    return _html_shell(
        height=height,
        body=f"""
  <div class="viewer-shell">
    <div class="canvas-wrap">
      <canvas id="{spec.canvas_id}"></canvas>
      <div class="canvas-label">{spec.label}</div>
    </div>
    {_z_rail_html()}
  </div>
""",
        init_script=_init_script([spec], volumes_by_canvas={spec.canvas_id: volumes_js}),
    )


def _html_compare(specs: list[ViewerSpec], *, height: int) -> str:
    for spec in specs:
        _check_static(spec.layers)
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

    function syncCameras() {{
      // Bidirectional camera + zoom + pan sync between compare-mode viewers.
      // Niivue 0.68.1 exposes broadcastTo([others], opts); pair each viewer
      // pointing at the others so a drag/zoom on one mirrors to all.
      if (viewers.length < 2) return;
      const opts = {{ "3d": true, "2d": true, zoomPan: true, cal: false, sliceType: false }};
      for (let i = 0; i < viewers.length; i++) {{
        const others = viewers.filter((_, j) => j !== i);
        try {{
          viewers[i].broadcastTo(others, opts);
        }} catch (e) {{
          console.warn("[niivue] broadcastTo failed for viewer " + i, e);
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
        syncCameras();
        log(viewers.length > 1
          ? "Compare: drag either brain — both rotate together · Z slider cuts both"
          : "Drag to rotate · Z slider cuts the volume");
        setTimeout(() => {{ status.style.opacity = "0.6"; }}, 4000);
      }} catch (e) {{
        log("init failed: " + (e && e.message ? e.message : e), true);
      }}
    }})();
    """
