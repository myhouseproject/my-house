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
  model_url: 'dom_Gruszowa60.glb'
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
  assert.deepEqual(plain(f.models[0].position), georef.center);
  assert.deepEqual(plain(f.models[0].orientation), georef.orientation);
  assert.equal(f.models[0].altitudeMode, 'ABSOLUTE');
  assert.equal(f.models[0].src, 'https://example.test/dom/dom_Gruszowa60.glb');
  assert.deepEqual(f.modelAppendChecks, [true], 'the map must be connected before its model is appended');
  assert.equal(f.requests[0].url, f.models[0].src);
  assert.equal(f.requests[0].options.cache, 'no-cache');
  assert.equal(f.markers.length, 1);
  assert.deepEqual(plain(f.markers[0].position), {...georef.center, altitude: georef.center.altitude + 5});
  assert.equal(f.markers[0].drawsWhenOccluded, true);
  assert.equal(f.markers[0].altitudeMode, 'ABSOLUTE');
  f.maps[0].center = {lat: 0}; f.maps[0].heading = 180; f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(f.maps[0].center), georef.camera.center);
  assert.equal(f.maps[0].heading, georef.camera.heading);
  let flight;
  f.maps[0].flyCameraTo = options => {flight = options;};
  f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(flight), {endCamera: georef.camera, durationMillis: 400});
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

test('Google 3D deep link opens on startup and hash changes work without WebGL', () => {
  const f = fixture(georef, 'https://example.test/dom/index.html#google3d');
  f.run(fullViewerScript());
  assert.equal(f.context.__modelMode(), 'gmaps');
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(f.el('#view').style.display, 'none');

  f.context.location.href = 'https://example.test/dom/index.html';
  f.dispatch('hashchange');
  assert.equal(f.context.__modelMode(), 'exterior');
  assert.equal(f.el('#view').style.display, 'block');

  f.context.location.href += '#google3d';
  f.dispatch('hashchange');
  assert.equal(f.context.__modelMode(), 'gmaps');
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
});
