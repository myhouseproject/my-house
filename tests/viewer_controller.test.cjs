// Run with: node --test tests/viewer_controller.test.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'podglad_szablon.html'), 'utf8');
const controller = html.slice(html.indexOf('let gmapsInitialized = false;'), html.indexOf('// SOFTWARE VIEWER'));
const downloads = html.slice(html.indexOf('function downloadModel('), html.indexOf('const layerRank='));
const georef = {
  center: {lat: 50.8519, lng: 19.0875, altitude: 253.72652},
  orientation: {heading: 0, tilt: 270, roll: 0}, altitude_mode: 'absolute',
  camera: {center: {lat: 50.852, lng: 19.088, altitude: 269}, heading: 27, tilt: 65, range: 110},
  model_url: 'google_models/dom_Gruszowa60.0123456789abcdef.glb'
};
const plain = value => JSON.parse(JSON.stringify(value));

function validGlb() {
  const bytes = new ArrayBuffer(20), header = new DataView(bytes);
  header.setUint32(0, 0x46546c67, true);
  header.setUint32(4, 2, true);
  header.setUint32(8, bytes.byteLength, true);
  return bytes;
}

const modelResponse = () => ({ok: true, status: 200, arrayBuffer: async () => validGlb()});

function fixture(metadata = georef, href = 'https://example.test/dom/index.html') {
  const elements = new Map(), scripts = [], maps = [], models = [], markers = [], flatteners = [],
    clicked = [], storage = new Map(), listeners = new Map(), requests = [], modelAppendChecks = [];
  const node = () => {
    const classes = new Set(), attributes = new Map(), handlers = new Map();
    return {
      style: {}, children: [], parentNode: null, checked: true, clientWidth: 800, clientHeight: 600,
      classList: {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x),
        toggle(x, on) {if (on) classes.add(x); else classes.delete(x);}},
      setAttribute: (key, value) => attributes.set(key, value), getAttribute: key => attributes.get(key),
      appendChild(x) {
        if (x.parentNode) x.parentNode.removeChild(x);
        if (x.kind === 'model') modelAppendChecks.push(!!this.parentNode);
        this.children.push(x); x.parentNode = this; return x;
      },
      append(x) {this.appendChild(x);},
      removeChild(x) {this.children = this.children.filter(child => child !== x); x.parentNode = null; return x;},
      set innerHTML(value) {assert.equal(value, ''); for (const child of [...this.children]) this.removeChild(child);},
      addEventListener(type, listener) {if (!handlers.has(type)) handlers.set(type, []); handlers.get(type).push(listener);},
      dispatchEvent(event) {(handlers.get(event.type) || []).forEach(listener => listener(event));},
      remove() {if (this.parentNode) this.parentNode.removeChild(this); this.removed = true;},
      focus() {this.focused = true;},
      click() {clicked.push(this); if (this.onclick) return this.onclick();},
      getContext: type => type === '2d' ? {} : null
    };
  };
  const el = id => {if (!elements.has(id)) elements.set(id, node()); return elements.get(id);};
  class Map3DElement {constructor(options) {Object.assign(this, node(), options); maps.push(this);}}
  class Model3DElement {constructor(options) {Object.assign(this, node(), options); this.kind = 'model'; models.push(this);}}
  class Marker3DElement {constructor(options) {Object.assign(this, node(), options); markers.push(this);}}
  class FlattenerElement {constructor() {Object.assign(this, node()); flatteners.push(this);}}
  const context = {
    URL, URLSearchParams, Blob, AbortController, DataView, console, clearTimeout,
    fetch: async (url, options) => {requests.push({url, options}); return modelResponse();},
    setTimeout(fn, ms) {const timer = setTimeout(fn, ms); timer.unref(); return timer;},
    requestAnimationFrame() {},
    addEventListener(type, listener) {if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(listener);},
    devicePixelRatio: 1,
    $: el, GOOGLE_MODEL_GEOREF: structuredClone(metadata),
    location: {href, search: new URL(href).search, reload() {context.reloads++;}}, reloads: 0,
    history: {replaceState(_state, _title, url) {context.location.href = String(url); context.location.search = new URL(url).search;}},
    document: {querySelector: el, querySelectorAll: () => [], addEventListener() {},
      createElement: node, head: {appendChild(script) {scripts.push(script);}}},
    localStorage: {setItem: (k, v) => storage.set(k, v), getItem: k => storage.get(k), removeItem: k => storage.delete(k)}
  };
  context.window = context;
  vm.createContext(context);
  return {context, scripts, maps, models, markers, flatteners, requests, modelAppendChecks, clicked, el,
    library: {Map3DElement, Model3DElement, Marker3DElement, FlattenerElement},
    dispatch: type => (listeners.get(type) || []).forEach(listener => listener()),
    run: source => vm.runInContext(source, context)};
}

function fullViewerScript() {
  let script = html.split('<script>')[1].split('</script>')[0];
  for (const [marker, value] of Object.entries({__SCENE__: '{"parts":[]}', __GLB_INTERIOR__: '',
    __GLB_EXTERIOR__: '', __GOOGLE_MODEL_GEOREF__: JSON.stringify(georef), __ROOM_LABELS__: '[]', __ORTHO_JPG__: ''})) {
    script = script.replaceAll(marker, value);
  }
  return script;
}

test('waits for SDK and 3D library, mounts once, applies exported placement and camera', async () => {
  const f = fixture(); f.run(controller);
  const first = f.run('loadGoogleMaps3DLibrary("test_key")');
  const second = f.run('loadGoogleMaps3DLibrary("test_key")');
  assert.equal(f.scripts.length, 1);
  assert.equal(new URL(f.scripts[0].src).searchParams.get('key'), 'test_key');
  let release, imports = 0;
  const pendingLibrary = new Promise(resolve => {release = resolve;});
  f.context.google = {maps: {importLibrary(name) {assert.equal(name, 'maps3d'); imports++; return pendingLibrary;}}};
  f.context.__domMapsReady();
  await new Promise(setImmediate);
  assert.equal(imports, 1);
  assert.equal(f.maps.length, 0);
  release(f.library); await Promise.all([first, second]);
  assert.equal(f.maps.length, 1);
  assert.equal(f.models.length, 1);
  assert.deepEqual(plain(f.models[0].position), {...georef.center, altitude: 254.72652});
  assert.deepEqual(plain(f.models[0].orientation), georef.orientation);
  assert.equal(f.models[0].altitudeMode, 'ABSOLUTE');
  assert.equal(f.models[0].src, 'https://example.test/dom/google_models/dom_Gruszowa60.0123456789abcdef.glb');
  assert.deepEqual(f.modelAppendChecks, [true], 'the map must be connected before its model is appended');
  assert.equal(f.requests[0].url, f.models[0].src);
  assert.equal(f.requests[0].options.cache, 'no-cache');
  assert.equal(f.markers.length, 1);
  assert.deepEqual(plain(f.markers[0].position), {...georef.center, altitude: georef.center.altitude + 6});
  assert.equal(f.markers[0].drawsWhenOccluded, true);
  assert.equal(f.markers[0].altitudeMode, 'ABSOLUTE');
  f.maps[0].center = {lat: 0}; f.maps[0].heading = 180; f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(f.maps[0].center), {...georef.camera.center, altitude: 270});
  assert.equal(f.maps[0].heading, georef.camera.heading);
  let flight;
  f.maps[0].flyCameraTo = options => {flight = options;};
  f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(flight), {endCamera: {...georef.camera, center: {...georef.camera.center, altitude: 270}}, durationMillis: 400});
});

test('network failure can be retried; authentication failure remains visible; changed key reloads', async () => {
  const f = fixture({...georef, altitude_mode: 'relative-to-ground'}); f.run(controller);
  let attempt = f.run('loadGoogleMaps3DLibrary("test_key")');
  f.scripts[0].onerror(); await attempt;
  assert.equal(f.maps.length, 0);
  assert.equal(f.el('#gmapsKeyError').style.display, 'block');
  attempt = f.run('loadGoogleMaps3DLibrary("test_key")');
  assert.equal(f.scripts.length, 2);
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.context.__domMapsReady(); await attempt;
  assert.equal(f.models[0].altitudeMode, 'RELATIVE_TO_GROUND');
  assert.equal(f.el('#gmapsKeyError').style.display, 'none');
  await f.run('loadGoogleMaps3DLibrary("replacement_key")');
  assert.equal(f.context.reloads, 1);
  const bad = fixture(); bad.run(controller);
  const rejected = bad.run('loadGoogleMaps3DLibrary("bad_key")');
  bad.context.gm_authFailure(); await rejected;
  assert.equal(bad.maps.length, 0);
  assert.equal(bad.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(bad.el('#gmapsKeyError').style.display, 'block');
});

test('missing, invalid and failed model downloads keep the map and key available for retry', async () => {
  const failures = [
    {name: '404', fetch: async () => ({ok: false, status: 404}), message: /HTTP 404/},
    {name: 'HTML instead of GLB', fetch: async () => ({ok: true, arrayBuffer: async () => new ArrayBuffer(40)}), message: /Nieprawidłowy plik modelu/},
    {name: 'network failure', fetch: async () => {throw new Error('Network failed');}, message: /Network failed/}
  ];
  for (const failure of failures) {
    const f = fixture(), successfulFetch = f.context.fetch;
    f.context.localStorage.setItem('google_maps_3d_api_key', 'retained_key');
    let imports = 0;
    f.context.google = {maps: {importLibrary: async () => {imports++; return f.library;}}};
    f.context.fetch = failure.fetch;
    f.run(controller);
    f.run('setupGmapsListeners()');
    await f.run('loadGoogleMaps3DLibrary("retained_key")');
    const map = f.maps[0];
    assert.equal(f.maps.length, 1, failure.name);
    assert.equal(map.parentNode, f.el('#gmaps3dMount'), failure.name);
    assert.equal(f.models.length, 0, failure.name);
    assert.equal(f.el('#gmaps3dMount').style.display, 'block', failure.name);
    assert.equal(f.el('#gmapsKeyPrompt').style.display, 'none', failure.name);
    assert.equal(f.el('#gmaps3dToolbar').style.display, 'flex', failure.name);
    assert.match(f.el('#gmapsProjectStatus').textContent, failure.message, failure.name);
    assert.equal(f.el('#gmapsProjectStatus').classList.contains('error'), true, failure.name);
    assert.equal(f.context.localStorage.getItem('google_maps_3d_api_key'), 'retained_key', failure.name);

    f.context.fetch = successfulFetch;
    await f.el('#btnGmapsRetryModel').onclick();
    assert.equal(f.maps.length, 1, failure.name);
    assert.equal(f.models.length, 1, failure.name);
    assert.equal(f.models[0].parentNode, map, failure.name);
    assert.equal(imports, 1, failure.name);
    assert.equal(f.el('#gmapsProjectStatus').classList.contains('error'), false, failure.name);
    assert.match(f.el('#gmapsProjectStatus').textContent, /plik pobrany/, failure.name);
    assert.equal(f.context.localStorage.getItem('google_maps_3d_api_key'), 'retained_key', failure.name);
  }
});

test('native-incompatible model URLs show an error instead of claiming a successful download', async () => {
  for (const suffix of ['?v=abc', '#revision']) {
    const f = fixture({...georef, model_url: 'dom_Gruszowa60.glb' + suffix});
    f.context.google = {maps: {importLibrary: async () => f.library}};
    f.run(controller);
    await f.run('loadGoogleMaps3DLibrary("test_key")');
    assert.equal(f.models.length, 0);
    assert.equal(f.requests.length, 0);
    assert.match(f.el('#gmapsProjectStatus').textContent, /Nieprawidłowy adres pliku modelu/);
    assert.equal(f.el('#gmapsProjectStatus').classList.contains('error'), true);
    assert.equal(f.el('#gmaps3dMount').style.display, 'block');
  }
});

test('changing the API key aborts a pending model download and ignores its late response', async () => {
  const f = fixture();
  f.context.localStorage.setItem('google_maps_3d_api_key', 'old_key');
  f.context.google = {maps: {importLibrary: async () => f.library}};
  let finishDownload, signal;
  f.context.fetch = (_url, options) => {
    signal = options.signal;
    return new Promise(resolve => {finishDownload = resolve;});
  };
  f.run(controller);
  f.run('setupGmapsListeners()');
  const loading = f.run('loadGoogleMaps3DLibrary("old_key")');
  await new Promise(setImmediate);
  assert.equal(f.maps.length, 1);
  assert.equal(f.models.length, 0);
  assert.equal(signal.aborted, false);
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(f.run('gmapsHeightMeasuring'), true);

  f.el('#btnGmapsChangeKey').onclick();
  assert.equal(signal.aborted, true);
  assert.equal(f.maps[0].parentNode, null);
  assert.equal(f.context.localStorage.getItem('google_maps_3d_api_key'), undefined);
  finishDownload(modelResponse());
  await loading;
  assert.equal(f.models.length, 0);
  assert.equal(f.el('#gmaps3dMount').children.length, 0);
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(f.el('#gmaps3dToolbar').style.display, 'none');
  assert.equal(f.el('#gmapsProjectStatus').style.display, 'none');
  assert.equal(f.run('gmapsHeightMeasuring'), false);
  assert.equal(f.run('gmapsHeightSample'), null);
  assert.equal(f.el('#gmapsHeightPanel').style.display, 'none');
});

test('a map rendering error remains visible after an in-flight model succeeds and retry is clicked', async () => {
  const f = fixture();
  f.context.google = {maps: {importLibrary: async () => f.library}};
  let finishDownload, downloads = 0;
  f.context.fetch = () => {
    downloads++;
    return new Promise(resolve => {finishDownload = resolve;});
  };
  f.run(controller);
  f.run('setupGmapsListeners()');
  const loading = f.run('loadGoogleMaps3DLibrary("test_key")');
  await new Promise(setImmediate);
  f.maps[0].dispatchEvent({type: 'gmp-error'});
  const error = f.el('#gmapsProjectStatus').textContent;
  assert.match(error, /Google nie może wyświetlić mapy 3D/);
  assert.equal(f.el('#gmapsProjectStatus').classList.contains('error'), true);

  finishDownload(modelResponse());
  await loading;
  assert.equal(f.el('#gmapsProjectStatus').textContent, error);
  await f.el('#btnGmapsRetryModel').onclick();
  assert.equal(downloads, 1, 'model refresh must not erase or bypass a map error');
  assert.equal(f.el('#gmapsProjectStatus').textContent, error);
  assert.equal(f.el('#gmapsProjectStatus').classList.contains('error'), true);
});

test('late authentication failure survives leaving and reopening Google, and same-key retry reloads the SDK', async () => {
  const f = fixture();
  f.run(fullViewerScript());
  f.run('setupGmapsListeners()');
  f.context.localStorage.setItem('google_maps_3d_api_key', 'late_key');
  const loading = f.run('loadGoogleMaps3DLibrary("late_key")');
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.context.__domMapsReady();
  await loading;
  f.el('#vbtn-gmaps').onclick();
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'none');
  f.context.gm_authFailure();
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(f.el('#gmaps3dMount').style.display, 'none');
  f.el('#vbtn-exterior').onclick();
  f.el('#vbtn-gmaps').onclick();
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(f.el('#gmapsKeyError').style.display, 'block');
  assert.match(f.el('#gmapsKeyError').textContent, /odrzuciło klucz API/);
  assert.equal(f.el('#gmaps3dMount').style.display, 'none');

  const downloads = f.requests.length;
  await f.el('#btnGmapsRetryModel').onclick();
  assert.equal(f.requests.length, downloads, 'model retry cannot recover a rejected SDK key');
  f.el('#inputGmapsApiKey').value = 'late_key';
  f.el('#btnSaveGmapsKey').onclick();
  assert.equal(f.context.reloads, 1);
});

test('Google building clearing uses only the house footprint and toggles off and on', async () => {
  const footprint = [
    {lat: 50.8518, lng: 19.0874}, {lat: 50.8520, lng: 19.0874},
    {lat: 50.8520, lng: 19.0876}, {lat: 50.8518, lng: 19.0876}
  ];
  const f = fixture({...georef, house_footprint: footprint});
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.run(controller);
  f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  assert.equal(f.flatteners.length, 1);
  assert.deepEqual(plain(f.flatteners[0].path), footprint);
  assert.equal(f.flatteners[0].parentNode, f.maps[0]);
  assert.equal(f.el('#btnGmapsTerrain').getAttribute('aria-pressed'), 'true');
  f.el('#btnGmapsTerrain').onclick();
  assert.equal(f.flatteners[0].parentNode, null);
  assert.equal(f.el('#btnGmapsTerrain').getAttribute('aria-pressed'), 'false');
  assert.equal(f.models[0].parentNode, f.maps[0]);
  f.el('#btnGmapsTerrain').onclick();
  assert.equal(f.flatteners.length, 1);
  assert.equal(f.flatteners[0].parentNode, f.maps[0]);
  assert.equal(f.el('#btnGmapsTerrain').getAttribute('aria-pressed'), 'true');

  const minimal = fixture({...georef, house_footprint: footprint});
  delete minimal.library.FlattenerElement;
  delete minimal.library.Marker3DElement;
  minimal.context.google = {maps: {importLibrary: async () => minimal.library}};
  minimal.run(controller);
  await minimal.run('loadGoogleMaps3DLibrary("test_key")');
  assert.equal(minimal.models.length, 1, 'optional Google elements must not block the project');
  assert.equal(minimal.flatteners.length, 0);
  assert.equal(minimal.el('#btnGmapsTerrain').style.display, 'none');
});

test('Google height offset changes model, marker and current camera without modifying the survey', async () => {
  const f = fixture({...georef, source: {model_zero_elevation_m: 254}});
  const original = structuredClone(f.context.GOOGLE_MODEL_GEOREF);
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.run(controller); f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  const map = f.maps[0], model = f.models[0];
  assert.equal(f.run('gmapsHeightOffset'), 1);
  // Google returns LatLngAltitude objects; their coordinates need not be enumerable.
  const center = {};
  Object.defineProperties(center, {
    lat: {get: () => 50.8521}, lng: {get: () => 19.0877}, altitude: {get: () => 260}
  });
  map.center = center; map.heading = 170; map.tilt = 54; map.range = 72;
  f.el('#inputGmapsHeightOffset').value = '2.20';
  f.el('#btnApplyGmapsHeightOffset').onclick();
  assert.ok(Math.abs(model.position.altitude - 255.92652) < 1e-8);
  assert.ok(Math.abs(f.markers[0].position.altitude - 260.92652) < 1e-8);
  assert.deepEqual(plain(map.center), {lat: 50.8521, lng: 19.0877, altitude: 261.2});
  assert.deepEqual([map.heading, map.tilt, map.range], [170, 54, 72]);
  assert.equal(f.context.localStorage.getItem('google_maps_height_offset_m_v1'), '2.2');
  assert.equal(f.el('#gmapsHeightDisplay').textContent, '255,93 m');
  const position = plain(model.position), saved = f.context.localStorage.getItem('google_maps_height_offset_m_v1');
  for (const value of ['', ' ', 'nope', 'Infinity', '10.01', '-10.01']) {
    f.el('#inputGmapsHeightOffset').value = value;
    f.el('#btnApplyGmapsHeightOffset').onclick();
    assert.deepEqual(plain(model.position), position, 'invalid input cannot move the model');
    assert.equal(f.context.localStorage.getItem('google_maps_height_offset_m_v1'), saved);
  }
  f.el('#btnResetGmapsHeightOffset').onclick();
  assert.deepEqual(plain(model.position), georef.center);
  assert.equal(f.run('gmapsHeightOffset'), 0);
  assert.equal(f.context.localStorage.getItem('google_maps_height_offset_m_v1'), '0');
  assert.deepEqual(plain(f.context.GOOGLE_MODEL_GEOREF), original);
});

test('Google height offset persists explicit zero and tolerates invalid or unavailable storage', () => {
  const key = 'google_maps_height_offset_m_v1';
  for (const [stored, expected] of [[null, 1], ['', 1], ['bad', 1], ['Infinity', 1], ['11', 1], ['0', 0], ['-1.5', -1.5], ['2.3', 2.3]]) {
    const f = fixture();
    if (stored !== null) f.context.localStorage.setItem(key, stored);
    f.run(controller);
    assert.equal(f.run('gmapsHeightOffset'), expected, String(stored));
    assert.ok(Math.abs(f.run('googleViewPosition().altitude') - georef.center.altitude - expected) < 1e-8);
    assert.deepEqual(plain(f.context.GOOGLE_MODEL_GEOREF), georef);
  }
  const blocked = fixture();
  blocked.context.localStorage.getItem = () => {throw new Error('storage unavailable');};
  blocked.context.localStorage.setItem = () => {throw new Error('storage unavailable');};
  blocked.run(controller);
  assert.equal(blocked.run('gmapsHeightOffset'), 1);
  assert.equal(blocked.run('setGoogleHeightOffset(1.5)'), true);
  assert.equal(blocked.run('gmapsHeightOffset'), 1.5);
});

test('pending and hidden Google models use the latest display offset', async () => {
  const f = fixture();
  f.context.google = {maps: {importLibrary: async () => f.library}};
  let finishDownload;
  f.context.fetch = () => new Promise(resolve => {finishDownload = resolve;});
  f.run(controller); f.run('setupGmapsListeners()');
  const loading = f.run('loadGoogleMaps3DLibrary("test_key")');
  await new Promise(setImmediate);
  assert.equal(f.models.length, 0);
  assert.equal(f.run('setGoogleHeightOffset(2.1)'), true);
  finishDownload(modelResponse()); await loading;
  assert.ok(Math.abs(f.models[0].position.altitude - 255.82652) < 1e-8);
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(f.models[0].parentNode, null);
  f.maps[0].dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  f.maps[0].dispatchEvent({type: 'gmp-click', position: {...georef.center, altitude: 254.52652}});
  assert.ok(f.run('gmapsHeightSample'));
  assert.equal(f.run('setGoogleHeightOffset(-0.5)'), true);
  assert.equal(f.run('gmapsHeightSample'), null, 'a changed display zero invalidates its old comparison');
  assert.equal(f.models[0].parentNode, null, 'adjustment must keep measurement mode active');
  assert.ok(Math.abs(f.models[0].position.altitude - 253.22652) < 1e-8);
  f.el('#btnGmapsHeightsClose').onclick();
  assert.equal(f.models[0].parentNode, f.maps[0]);
  assert.ok(Math.abs(f.models[0].position.altitude - 253.22652) < 1e-8);
  f.el('#btnGmapsChangeKey').onclick();
  assert.equal(f.context.localStorage.getItem('google_maps_height_offset_m_v1'), '-0.5');
  assert.deepEqual(plain(f.context.GOOGLE_MODEL_GEOREF), georef);
});

test('height checks compare the Google surface to the EGM96 house zero and restore the model', async () => {
  const metadata = {...georef, center: {...georef.center, altitude: 253.7265},
    source: {model_zero_elevation_m: 254},
    house_footprint: [{lat: 50.8518, lng: 19.0874}, {lat: 50.852, lng: 19.0874}, {lat: 50.852, lng: 19.0876}]};
  const f = fixture(metadata);
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.run(controller); f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  const map = f.maps[0], model = f.models[0], flattener = f.flatteners[0];
  f.el('#btnGmapsHeights').onclick();
  assert.equal(f.el('#gmapsHeightPanel').style.display, 'block');
  assert.equal(f.el('#btnGmapsHeights').getAttribute('aria-expanded'), 'true');
  assert.equal(f.el('#gmapsHeightSource').textContent, '254,00 m');
  assert.equal(f.el('#gmapsHeightReference').textContent, '253,73 m');
  assert.equal(f.el('#btnGmapsHeightsClose').focused, true);
  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(model.parentNode, null);
  assert.equal(flattener.parentNode, map, 'measuring preserves the chosen Google flattener state');
  assert.equal(f.el('#btnGmapsMeasureHeight').getAttribute('aria-pressed'), 'true');
  const click = {type: 'gmp-click', target: map, position: {...metadata.center, altitude: 254.5265}};
  map.dispatchEvent(click);
  assert.equal(f.run('gmapsHeightSample'), null, 'an unsettled map cannot supply a measurement');
  map.dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  map.dispatchEvent(click);
  const reading = f.run('gmapsHeightSample');
  assert.ok(Math.abs(reading.difference - 0.8) < 1e-10, 'subtract EGM96 zero, not the source PZT elevation');
  assert.equal(reading.altitude, 254.5265);
  assert.equal(reading.flattened, true);
  assert.match(f.el('#gmapsHeightReading').textContent, /\+0,80 m/);
  assert.match(f.el('#gmapsHeightReading').textContent, /Spłaszczenie terenu włączone/);
  assert.deepEqual(plain(model.position), {...metadata.center, altitude: 254.7265}, 'measurement must preserve the Google display offset');
  assert.deepEqual(plain(f.context.GOOGLE_MODEL_GEOREF), metadata, 'measurement and display offset must not modify surveyed coordinates');
  assert.ok(Math.abs(reading.displayDifference + 0.2) < 1e-10, 'also compare against the shifted Google view');
  assert.match(f.el('#gmapsHeightReading').textContent, /-0,20 m/);
  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(model.parentNode, map);
  assert.equal(map.children.filter(child => child.kind === 'model').length, 1);
  assert.equal(f.run('gmapsHeightSample'), null);
  assert.equal(f.el('#btnGmapsMeasureHeight').getAttribute('aria-pressed'), 'false');
  f.el('#btnGmapsMeasureHeight').onclick();
  let prevented = false;
  f.el('#gmapsHeightPanel').onkeydown({key: 'Escape', preventDefault() {prevented = true;}});
  assert.equal(prevented, true);
  assert.equal(model.parentNode, map);
  assert.equal(f.el('#gmapsHeightPanel').style.display, 'none');
  assert.equal(f.el('#btnGmapsHeights').getAttribute('aria-expanded'), 'false');
  assert.equal(f.el('#btnGmapsHeights').focused, true);
});

test('height checks reject invalid and remote clicks and invalidate readings when the surface changes', async () => {
  const f = fixture({...georef,
    house_footprint: [{lat: 50.8518, lng: 19.0874}, {lat: 50.852, lng: 19.0874}, {lat: 50.852, lng: 19.0876}]});
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.run(controller); f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  const map = f.maps[0];
  f.el('#btnGmapsHeights').onclick();
  assert.equal(f.el('#gmapsHeightSource').textContent, 'brak danych', 'older metadata can omit the source datum');
  f.el('#btnGmapsMeasureHeight').onclick();
  map.dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  const valid = {type: 'gmp-click', position: {...georef.center, altitude: 253.52652}};
  const invalid = [undefined, null, {...georef.center, altitude: NaN}, {...georef.center, altitude: Infinity},
    {...georef.center, altitude: '254'}, {...georef.center, lat: 91}, {...georef.center, lng: 181},
    {...georef.center, lat: georef.center.lat + 0.002}];
  for (const position of invalid) {
    map.dispatchEvent(valid);
    assert.ok(f.run('gmapsHeightSample'));
    map.dispatchEvent({type: 'gmp-click', position});
    assert.equal(f.run('gmapsHeightSample'), null, 'an invalid click must not retain the prior reading');
  }
  assert.match(f.el('#gmapsHeightReading').textContent, /100 m/);
  map.dispatchEvent({...valid, target: f.markers[0]});
  assert.equal(f.run('gmapsHeightSample'), null, 'a marker click is not a ground sample');
  map.dispatchEvent(valid);
  assert.ok(Math.abs(f.run('gmapsHeightSample.difference') + 0.2) < 1e-10);
  map.dispatchEvent({type: 'gmp-steadychange', isSteady: false});
  assert.equal(f.run('gmapsHeightSample'), null);
  map.dispatchEvent(valid);
  assert.equal(f.run('gmapsHeightSample'), null);
  map.dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  map.dispatchEvent(valid);
  f.el('#btnGmapsTerrain').onclick();
  assert.equal(f.run('gmapsHeightSample'), null);
  assert.equal(f.flatteners[0].parentNode, null);
  assert.equal(f.models[0].parentNode, null, 'changing flattening must leave measurement mode active');
  map.dispatchEvent(valid);
  assert.equal(f.run('gmapsHeightSample'), null, 'changed terrain must finish rendering before another measurement');
  map.dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  map.dispatchEvent(valid);
  assert.equal(f.run('gmapsHeightSample.flattened'), false);
  assert.match(f.el('#gmapsHeightReading').textContent, /Spłaszczenie terenu wyłączone/);
  f.el('#btnGmapsHeightsClose').onclick();
  assert.equal(f.flatteners[0].parentNode, null, 'closing must preserve the last flattener selection');
});

test('measurement can start on a steady map while its first model download is still pending', async () => {
  const f = fixture();
  f.context.google = {maps: {importLibrary: async () => f.library}};
  let finishDownload;
  f.context.fetch = () => new Promise(resolve => {finishDownload = resolve;});
  f.run(controller); f.run('setupGmapsListeners()');
  const loading = f.run('loadGoogleMaps3DLibrary("test_key")');
  await new Promise(setImmediate);
  const map = f.maps[0];
  map.dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(f.run('gmapsSteady'), true, 'without an attached model no new steady event is guaranteed');
  map.dispatchEvent({type: 'gmp-click', position: georef.center});
  assert.equal(f.run('gmapsHeightSample.difference'), 0);
  finishDownload(modelResponse()); await loading;
  assert.equal(f.models[0].parentNode, null, 'the first asynchronous model must also honor measurement mode');
  assert.equal(f.run('gmapsSteady'), true);
  f.el('#btnGmapsHeightsClose').onclick();
  assert.equal(f.models[0].parentNode, map);
  assert.equal(f.run('gmapsSteady'), false, 'restoring the downloaded model changes the rendered scene');
});

test('a model retry during measurement remains hidden and closing restores only the latest model', async () => {
  const f = fixture();
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.run(controller); f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  const map = f.maps[0];
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  let finishDownload;
  f.context.fetch = () => new Promise(resolve => {finishDownload = resolve;});
  const retry = f.el('#btnGmapsRetryModel').onclick();
  finishDownload(modelResponse()); await retry;
  assert.equal(f.models.length, 2);
  assert.equal(f.models[0].parentNode, null);
  assert.equal(f.models[1].parentNode, null);
  assert.equal(map.children.filter(child => child.kind === 'model').length, 0);
  f.el('#btnGmapsHeightsClose').onclick();
  f.el('#btnGmapsHeightsClose').onclick();
  assert.equal(f.models[1].parentNode, map);
  assert.equal(map.children.filter(child => child.kind === 'model').length, 1);
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  const nextRetry = f.el('#btnGmapsRetryModel').onclick();
  f.el('#btnGmapsHeightsClose').onclick();
  finishDownload(modelResponse()); await nextRetry;
  assert.equal(f.models[1].parentNode, null);
  assert.equal(f.models[2].parentNode, map, 'a response after closing must use the current visibility mode');
  assert.equal(map.children.filter(child => child.kind === 'model').length, 1);
});

test('leaving Google or a renderer failure closes height measurement and restores the house', async () => {
  const f = fixture();
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.context.localStorage.setItem('google_maps_3d_api_key', 'test_key');
  f.run(fullViewerScript()); f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  f.el('#vbtn-gmaps').onclick();
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  f.maps[0].dispatchEvent({type: 'gmp-steadychange', isSteady: true});
  f.maps[0].dispatchEvent({type: 'gmp-click', position: georef.center});
  assert.equal(f.run('gmapsHeightSample.difference'), 0);
  f.el('#vbtn-exterior').onclick();
  assert.equal(f.run('gmapsHeightMeasuring'), false);
  assert.equal(f.run('gmapsHeightSample'), null);
  assert.equal(f.models[0].parentNode, f.maps[0]);
  assert.equal(f.el('#gmapsHeightPanel').style.display, 'none');
  f.el('#vbtn-gmaps').onclick();
  f.el('#btnGmapsHeights').onclick();
  f.el('#btnGmapsMeasureHeight').onclick();
  f.maps[0].dispatchEvent({type: 'gmp-error'});
  assert.equal(f.run('gmapsHeightMeasuring'), false);
  assert.equal(f.models[0].parentNode, f.maps[0]);
  assert.equal(f.el('#gmapsHeightPanel').style.display, 'none');
  f.el('#btnGmapsHeights').onclick();
  assert.equal(f.el('#gmapsHeightPanel').style.display, 'none');
});

test('hosted downloads stay lazy while portable downloads decode embedded models', () => {
  const f = fixture(); let decoded = 0;
  f.context.atob = data => {decoded++; return Buffer.from(data, 'base64').toString('binary');};
  f.run(downloads);
  f.run('downloadModel("", "dom_bryla.glb")');
  assert.equal(decoded, 0);
  assert.equal(f.clicked.at(-1).href, 'https://example.test/dom/dom_bryla.glb');
  f.run('downloadModel("Z2xm", "dom_wnetrze.glb")');
  assert.equal(decoded, 1);
  assert.match(f.clicked.at(-1).href, /^blob:/);
  URL.revokeObjectURL(f.clicked.at(-1).href);
});

test('all Google project buttons open the embedded map and close the sidebar without WebGL', () => {
  for (const id of ['#vbtn-gmaps', '#btnModeGmaps', '#btnGmaps3D', '#btnGoogleProject']) {
    const f = fixture();
    f.run(fullViewerScript());
    assert.equal(f.context.__modelReady, true);
    assert.match(f.el('.version').textContent, /Canvas2D/);
    f.el('#toggleSidebar').onclick();
    assert.equal(f.el('#sidebar').classList.contains('open'), true);
    f.el(id).onclick();
    assert.equal(f.context.__modelMode(), 'gmaps', id);
    assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex', id);
    assert.equal(f.el('#view').style.display, 'none', id);
    assert.equal(f.el('#sidebar').classList.contains('open'), false, id);
    assert.equal(new URL(f.context.location.href).hash, '#google3d');
    f.el('#vbtn-exterior').onclick();
    assert.equal(f.context.__modelMode(), 'exterior');
    assert.equal(f.el('#view').style.display, 'block');
    assert.equal(new URL(f.context.location.href).hash, '');
  }
  assert.match(html, /<button id="btnGmaps3D"[^>]*aria-label="Google 3D z projektem domu"/);
  assert.match(html, /<button id="btnGoogleProject"/);
  assert.match(html, />🗺️ Mapa Google bez projektu<\/a>/);
  assert.match(html, />🛰️ Google Earth bez projektu<\/a>/);
});

test('Google 3D deep link skips a hidden zero-size canvas and resumes rendering outside Google without WebGL', () => {
  const f = fixture(georef, 'https://example.test/dom/index.html#google3d');
  const frames = [], reads = [], writes = [], canvas = f.el('#view');
  f.context.requestAnimationFrame = callback => frames.push(callback);
  Object.defineProperties(canvas, {
    clientWidth: {get: () => canvas.style.display === 'none' ? 0 : 64},
    clientHeight: {get: () => canvas.style.display === 'none' ? 0 : 48}
  });
  const drawingContext = {
    setTransform() {}, fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
    getImageData(x, y, width, height) {
      assert.ok(width > 0 && height > 0, 'getImageData must never receive a hidden canvas size');
      reads.push({x, y, width, height});
      return {data: new Uint8ClampedArray(width * height * 4)};
    },
    putImageData(image) {writes.push(image);}
  };
  canvas.getContext = type => type === '2d' ? drawingContext : null;
  const runFrame = () => {
    assert.ok(frames.length > 0, 'the animation loop must keep running');
    for (const callback of frames.splice(0)) callback();
  };
  f.run(fullViewerScript());
  assert.equal(f.context.__modelMode(), 'gmaps');
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(canvas.style.display, 'none');
  assert.equal(canvas.clientWidth, 0);
  assert.equal(canvas.clientHeight, 0);
  assert.doesNotThrow(runFrame);
  assert.equal(reads.length, 0);
  assert.equal(writes.length, 0);

  f.context.location.href = 'https://example.test/dom/index.html';
  f.dispatch('hashchange');
  assert.equal(f.context.__modelMode(), 'exterior');
  assert.equal(canvas.style.display, 'block');
  runFrame();
  assert.deepEqual(reads, [{x: 0, y: 0, width: 64, height: 48}]);
  assert.equal(writes.length, 1, 'switching back must resume the Canvas2D renderer');

  f.context.location.href += '#google3d';
  f.dispatch('hashchange');
  assert.equal(f.context.__modelMode(), 'gmaps');
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.doesNotThrow(runFrame);
  assert.equal(reads.length, 1, 'reopening Google must skip the hidden canvas again');
});
