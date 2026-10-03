'use strict';

// Camera export uses canonical metres/Z-up, never map/georeferenced positions.
function makeRenderCamera(pose, settings, sceneZBounds) {
  if (!pose || pose.coordinate_frame !== 'building_local' || pose.units !== 'm' || pose.up_axis !== 'Z')
    throw new Error('Render HQ jest dostępny w widokach wnętrza, łazienki i rzutu.');
  const width = Number(pose.viewport?.width), height = Number(pose.viewport?.height);
  const maximum = Number(settings.max_long_edge_px);
  if (![width, height, maximum].every(n => Number.isFinite(n) && n >= 16))
    throw new Error('Nie można odczytać rozmiaru kadru.');
  const scale = maximum / Math.max(width, height);
  const resolution = [Math.max(16, Math.round(width * scale)), Math.max(16, Math.round(height * scale))];
  const vector = value => {
    if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite))
      throw new Error('Kamera nie ma prawidłowego położenia.');
    return [...value];
  };
  const result = {schema_version: 1, kind: 'dom-render-camera', coordinate_frame: 'building_local',
    units: 'm', up_axis: 'Z', projection: pose.projection, eye: vector(pose.eye),
    target: vector(pose.target), up: vector(pose.up), resolution,
    aspect_ratio: resolution[0] / resolution[1]};
  if (pose.projection === 'perspective') {
    result.vertical_fov_degrees = pose.vertical_fov_radians * 180 / Math.PI;
    if (!Number.isFinite(result.vertical_fov_degrees) || result.vertical_fov_degrees <= 0 || result.vertical_fov_degrees >= 180)
      throw new Error('Nieprawidłowy kąt widzenia.');
  } else if (pose.projection === 'orthographic') {
    result.orthographic_height_m = pose.orthographic_height_m;
    if (!Number.isFinite(result.orthographic_height_m) || result.orthographic_height_m <= 0)
      throw new Error('Nieprawidłowa skala rzutu.');
  } else throw new Error('Ten rodzaj widoku nie obsługuje renderowania.');
  if (Array.isArray(pose.visible_part_names)) {
    result.visible_part_names = [...new Set(pose.visible_part_names)];
    if (!result.visible_part_names.length) throw new Error('Włącz elementy modelu przed zapisaniem kadru.');
  }
  if (pose.section_height_m != null) result.section_height_m = pose.section_height_m;
  if (pose.focus_bounds_xy_m != null) {
    const b = pose.focus_bounds_xy_m;
    if (!Array.isArray(b) || b.length !== 4 || ![...b, ...sceneZBounds].every(Number.isFinite))
      throw new Error('Nieprawidłowy obszar widoku.');
    result.clip_bounds_m = [[b[0], b[2], sceneZBounds[0]], [b[1], b[3], sceneZBounds[1]]];
  }
  if (new TextEncoder().encode(JSON.stringify(result)).byteLength > 65536)
    throw new Error('Ten kadr zawiera zbyt wiele elementów. Ogranicz widok do pomieszczenia.');
  return result;
}

function bindModelCapture() {
  const dialog = document.querySelector('#captureDialog');
  if (!dialog) return;
  const settings = VIEWER_CONFIG.render_capture || {};
  const status = document.querySelector('#captureStatus');
  const code = document.querySelector('#captureCode');
  const snapshot = document.querySelector('#capturePng');
  const controls = ['#copyRenderCamera', '#downloadRenderCamera'].map(id => document.querySelector(id));
  const workflow = document.querySelector('#renderWorkflowLink');
  let camera = null;
  function message(text) {status.textContent = text;}
  function download(blob, filename) {
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  function captureSettings() {
    const bounds = [Infinity, -Infinity];
    for (const part of SCENE_LOCAL.parts) for (const point of part.positions_m || []) {
      bounds[0] = Math.min(bounds[0], point[2]); bounds[1] = Math.max(bounds[1], point[2]);
    }
    return makeRenderCamera(window.getViewPose?.(), settings, bounds);
  }
  function show() {
    camera = null; message(''); code.value = '';
    const google = viewerMode === 'gmaps';
    snapshot.disabled = google;
    try {
      if (google || !settings.enabled) throw new Error('Przejdź do wnętrza lub łazienki, aby przygotować render HQ.');
      camera = captureSettings(); code.value = JSON.stringify(camera);
    } catch (error) {message(error.message);}
    controls.forEach(button => {button.disabled = !camera;});
    document.querySelector('#captureCutNote').hidden = !camera || camera.section_height_m == null;
    workflow.hidden = !camera;
    if (camera) workflow.href = settings.workflow_url;
    if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
  }
  document.querySelector('#openCapture').onclick = show;
  document.querySelector('#closeCapture').onclick = () => {
    if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
    document.querySelector('#openCapture').focus();
  };
  dialog.addEventListener('keydown', event => event.stopPropagation());
  snapshot.onclick = () => {
    snapshot.disabled = true;
    try {
      window.__renderTest?.();
      canvas.toBlob(blob => {
        snapshot.disabled = false;
        if (!blob) {message('Nie udało się zapisać obrazu. Spróbuj ponownie.'); return;}
        download(blob, settings.snapshot_filename || 'widok-modelu.png');
        message('Przygotowano PNG do pobrania. Render HQ oblicza dodatkowo światło i odbicia.');
      }, 'image/png');
    } catch (error) {snapshot.disabled = false; message('Nie udało się zapisać obrazu: ' + error.message);}
  };
  document.querySelector('#copyRenderCamera').onclick = async () => {
    if (!camera) return;
    try {
      await navigator.clipboard.writeText(code.value);
      message('Skopiowano ustawienia. Na GitHub wybierz Run workflow, wklej je do camera_json i uruchom zadanie.');
    } catch (_) {
      document.querySelector('#cameraDetails').open = true; code.focus(); code.select();
      message('Schowek jest niedostępny. Skopiuj zaznaczone ustawienia ręcznie.');
    }
  };
  document.querySelector('#downloadRenderCamera').onclick = () => {
    if (camera) download(new Blob([JSON.stringify(camera, null, 2)], {type: 'application/json'}),
      settings.camera_filename || 'kamera-portalu.json');
  };
}

if (typeof module !== 'undefined' && module.exports) module.exports = {makeRenderCamera};
if (typeof window !== 'undefined' && typeof document !== 'undefined') bindModelCapture();
