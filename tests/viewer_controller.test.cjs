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
      replaceChildren(...xs) {this.children=[];xs.forEach(x=>this.appendChild(x));},
      removeChild(x) {this.children = this.children.filter(child => child !== x); x.parentNode = null; return x;},
      set innerHTML(value) {assert.equal(value, ''); for (const child of [...this.children]) this.removeChild(child);},
      addEventListener(type, listener) {if (!handlers.has(type)) handlers.set(type, []); handlers.get(type).push(listener);},
      listenerCount: type => (handlers.get(type) || []).length,
      dispatchEvent(event) {(handlers.get(event.type) || []).forEach(listener => listener(event));},
      getBoundingClientRect: () => ({left:0,top:0,width:800,height:600,bottom:600,right:800}),
      setPointerCapture() {}, releasePointerCapture() {},
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
    document: {body:node(),querySelector: el, querySelectorAll: () => [], addEventListener() {},
      createElement: node, head: {appendChild(script) {scripts.push(script);}}},
    localStorage: {setItem: (k, v) => storage.set(k, v), getItem: k => storage.get(k), removeItem: k => storage.delete(k)}
  };
  context.window = context;
  context.sessionStorage={setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)};
  vm.createContext(context);
  return {context, scripts, maps, models, markers, flatteners, requests, modelAppendChecks, clicked, el,
    library: {Map3DElement, Model3DElement, Marker3DElement, FlattenerElement},
    dispatch: (type,event={}) => (listeners.get(type) || []).forEach(listener => listener(event)),
    run: source => vm.runInContext(source, context)};
}

function fullViewerScript(metadata=georef, available=true, rooms=[], presets={}, localScene={parts:[]}, navigation={}) {
  let script = html.split('<script>')[1].split('</script>')[0];
  for (const [marker, value] of Object.entries({__SCENE__: '{"parts":[]}', __GLB_INTERIOR__: '',
    __GLB_EXTERIOR__: '', __GLB_BLOCKS__: '', __GLB_SHELL__: '', __SCENE_LOCAL__: JSON.stringify(localScene), __VIEWER_CONFIG__: JSON.stringify({bounds_m:{minx:0,miny:0,maxx:28,maxy:12},parameters:{},navigation,room_presets:presets,decisions:[],google_available:available,map_scene_available:available}), __GOOGLE_MODEL_GEOREF__: JSON.stringify(metadata), __ROOM_LABELS__: JSON.stringify(rooms), __ORTHO_JPG__: ''})) {
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
  assert.deepEqual(plain(f.models[0].position), {...georef.center, altitude: 255.72652});
  assert.deepEqual(plain(f.models[0].orientation), georef.orientation);
  assert.equal(f.models[0].altitudeMode, 'ABSOLUTE');
  assert.equal(f.models[0].src, 'https://example.test/dom/google_models/dom_Gruszowa60.0123456789abcdef.glb');
  assert.deepEqual(f.modelAppendChecks, [true], 'the map must be connected before its model is appended');
  assert.equal(f.requests[0].url, f.models[0].src);
  assert.equal(f.requests[0].options.cache, 'no-cache');
  assert.equal(f.markers.length, 1);
  assert.deepEqual(plain(f.markers[0].position), {...georef.center, altitude: georef.center.altitude + 7});
  assert.equal(f.markers[0].drawsWhenOccluded, true);
  assert.equal(f.markers[0].altitudeMode, 'ABSOLUTE');
  f.maps[0].center = {lat: 0}; f.maps[0].heading = 180; f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(f.maps[0].center), {...georef.camera.center, altitude: 271});
  assert.equal(f.maps[0].heading, georef.camera.heading);
  let flight;
  f.maps[0].flyCameraTo = options => {flight = options;};
  f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(flight), {endCamera: {...georef.camera, center: {...georef.camera.center, altitude: 271}}, durationMillis: 400});
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
  assert.equal(f.run('gmapsHeightOffset'), 2);
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
  assert.deepEqual(plain(map.center), {lat: 50.8521, lng: 19.0877, altitude: 260.2});
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
  for (const [stored, expected] of [[null, 2], ['', 2], ['bad', 2], ['Infinity', 2], ['11', 2], ['0', 0], ['-1.5', -1.5], ['2.3', 2.3]]) {
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
  assert.equal(blocked.run('gmapsHeightOffset'), 2);
  assert.equal(blocked.run('setGoogleHeightOffset(1.5)'), true);
  assert.equal(blocked.run('gmapsHeightOffset'), 1.5);
});

test('building offset moves only the split house layer and persists independently', async () => {
  const metadata = {...georef, source: {model_zero_elevation_m: 254},
    building_model_url: 'google_models/dom_Gruszowa60_building.aaaaaaaaaaaaaaaa.glb',
    site_model_url: 'google_models/dom_Gruszowa60_site.bbbbbbbbbbbbbbbb.glb'};
  const f = fixture(metadata);
  f.context.google = {maps: {importLibrary: async () => f.library}};
  f.run(controller); f.run('setupGmapsListeners()');
  await f.run('loadGoogleMaps3DLibrary("test_key")');
  assert.equal(f.models.length, 2);
  assert.equal(f.requests.length, 2);
  const building = f.models.find(model => model.src.includes('_building.'));
  const site = f.models.find(model => model.src.includes('_site.'));
  assert.ok(building);
  assert.ok(site);
  assert.equal(f.run('gmapsBuildingHeightOffset'), 0);
  assert.ok(Math.abs(site.position.altitude - 255.72652) < 1e-8);
  assert.ok(Math.abs(building.position.altitude - 255.72652) < 1e-8);
  const map = f.maps[0], cameraBefore = plain(map.center);
  f.el('#btnGmapsHeights').onclick();
  assert.equal(f.el('#gmapsHeightBuilding').textContent, '255,73 m');
  f.el('#inputGmapsBuildingOffset').value = '0.45';
  f.el('#btnApplyGmapsBuildingOffset').onclick();
  assert.ok(Math.abs(site.position.altitude - 255.72652) < 1e-8, 'site stays at the global Google offset');
  assert.ok(Math.abs(building.position.altitude - 256.17652) < 1e-8, 'house receives the additional as-built offset');
  assert.ok(Math.abs(f.markers[0].position.altitude - 261.17652) < 1e-8);
  assert.deepEqual(plain(map.center), cameraBefore, 'building-only correction must not move the camera');
  assert.equal(f.context.localStorage.getItem('google_maps_building_height_offset_m_v1'), '0.45');
  assert.equal(f.el('#gmapsHeightBuilding').textContent, '256,18 m');

  f.el('#inputGmapsHeightOffset').value = '2.30';
  f.el('#btnApplyGmapsHeightOffset').onclick();
  assert.ok(Math.abs(site.position.altitude - 256.02652) < 1e-8);
  assert.ok(Math.abs(building.position.altitude - 256.47652) < 1e-8, 'global and building offsets add');
  assert.ok(Math.abs(f.markers[0].position.altitude - 261.47652) < 1e-8);

  const saved = plain(building.position);
  for (const value of ['', 'bad', '5.01', '-5.01']) {
    f.el('#inputGmapsBuildingOffset').value = value;
    f.el('#btnApplyGmapsBuildingOffset').onclick();
    assert.deepEqual(plain(building.position), saved);
    assert.equal(f.context.localStorage.getItem('google_maps_building_height_offset_m_v1'), '0.45');
  }

  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(site.parentNode, null);
  assert.equal(building.parentNode, null);
  f.el('#btnGmapsMeasureHeight').onclick();
  assert.equal(site.parentNode, map);
  assert.equal(building.parentNode, map);
  assert.equal(map.children.filter(child => child.kind === 'model').length, 2);

  f.el('#btnResetGmapsBuildingOffset').onclick();
  assert.equal(f.run('gmapsBuildingHeightOffset'), 0);
  assert.ok(Math.abs(building.position.altitude - site.position.altitude) < 1e-8);
  assert.equal(f.context.localStorage.getItem('google_maps_building_height_offset_m_v1'), '0');
  assert.deepEqual(plain(f.context.GOOGLE_MODEL_GEOREF), metadata);
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
  assert.deepEqual(plain(model.position), {...metadata.center, altitude: 255.7265}, 'measurement must preserve the Google display offset');
  assert.deepEqual(plain(f.context.GOOGLE_MODEL_GEOREF), metadata, 'measurement and display offset must not modify surveyed coordinates');
  assert.ok(Math.abs(reading.displayDifference + 1.2) < 1e-10, 'also compare against the shifted Google view');
  assert.match(f.el('#gmapsHeightReading').textContent, /-1,20 m/);
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


test('interior-only package starts locally without any Google or map metadata',()=>{
  const f=fixture();f.run(fullViewerScript({},false));
  assert.equal(f.context.__modelMode(),'interior');
  assert.equal(f.el('#roof').checked,false);
  assert.equal(f.el('#gardenPlants').checked,false);
  assert.equal(f.el('#vbtn-gmaps').disabled,true);
  assert.equal(f.el('#vbtn-exterior').disabled,true);
  assert.equal(f.el('#interiorTools').style.display,'flex');
  assert.equal(f.el('#sectionEnabled').checked,false);
});

const bathroomRoom={id:'R07',number:7,name:'Łazienka',reported_area_m2:11.17,polygon_m:[[25.11,2.1692],[27.7374,2.1692],[27.7374,6.4192],[25.11,6.4192]],local_x:26.4237,local_y:4.2942,x:26.4237,y:4.2942,policy:{floor:{level_mm:0},ceiling:{level_mm:2850}}};
const bathroomPreset={bathroom:{room_id:'R07',entrance_side:'north',wall_context_mm:350,label:'Łazienka'}};
const navigationConfig={eye_height_m:1.65,walk_speed_m_s:1.35,collision_radius_m:.12,collision_slice_height_m:1,movement_substep_m:.04,walk_vertical_fov_radians:1.05,near_plane_m:.05,room_starts:{R07:{eye_mm:[26423.7,5719.2,1650],target_mm:[26423.7,3719.2,1650]}}};
function navigationFixture(engine,parts=[],href='https://example.test/dom/?view=bathroom',storage,options={}){
 const f=fixture(georef,href);
 if(storage)f.context.sessionStorage=storage;
 if(engine==='WebGL')f.el('#view').getContext=()=>new Proxy({getShaderParameter:()=>true,getProgramParameter:()=>true,getAttribLocation:()=>0,getUniformLocation:(_p,n)=>n,getError:()=>0},{get:(t,k)=>k in t?t[k]:/^[A-Z_0-9]+$/.test(k)?0:()=>({})});
 else f.el('#view').getContext=type=>type==='2d'?{setTransform(){},fillRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},getImageData:(_x,_y,w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}}:null;
 f.context.document.createElementNS=()=>f.context.document.createElement();
 f.el('#finishReferences').checked=false;
 if(options.prepare)options.prepare(f);
 f.run(fullViewerScript({},false,options.rooms||[bathroomRoom],options.presets||bathroomPreset,{parts},options.navigation||navigationConfig));
 const pointer=(type,id,x,y,extra={})=>f.el('#view').dispatchEvent({type,pointerId:id,clientX:x,clientY:y,pointerType:'touch',button:0,preventDefault(){},...extra});
 return {...f,pointer,pose:()=>plain(f.context.getViewPose())};
}
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
for(const engine of ['Canvas2D','WebGL']){
 test(`${engine}: one shared pointer controller orbits, pinches and pans without jumps after lifting or cancelling a finger`,()=>{
  const f=navigationFixture(engine),canvas=f.el('#view');
  assert.equal(canvas.listenerCount('pointerdown'),1);assert.equal(canvas.listenerCount('touchstart'),0);
  const initial=f.pose();
  f.pointer('pointerdown',1,250,250);f.pointer('pointermove',1,280,260);f.pointer('pointerup',1,280,260);
  assert.ok(distance(initial.eye,f.pose().eye)>.1);assert.deepEqual(initial.target,f.pose().target);
  const beforePinch=f.pose();
  f.pointer('pointerdown',1,250,250);f.pointer('pointerdown',2,350,250);f.pointer('pointermove',2,400,280);
  const pinched=f.pose();assert.ok(distance(pinched.eye,pinched.target)<distance(beforePinch.eye,beforePinch.target));assert.ok(distance(pinched.target,beforePinch.target)>.01);
  f.pointer('pointerup',1,250,250);const remaining=f.pose();f.pointer('pointermove',2,400,280);assert.deepEqual(f.pose(),remaining);
  f.pointer('pointermove',2,401,280);assert.ok(distance(f.pose().eye,remaining.eye)<.2);assert.deepEqual(f.pose().target,remaining.target);
  f.pointer('pointercancel',2,401,280);const cancelled=f.pose();f.pointer('pointermove',2,900,900);assert.deepEqual(f.pose(),cancelled);
 });
 test(`${engine}: focus ray selects actual geometry and pose exports correct top-view up and cut state`,()=>{
  const wall={name:'pivot wall',category:'sciany',geometry:'solid',color:[.8,.8,.8,1],positions_m:[[25.11,4,0],[27.7374,4,0],[27.7374,4,2.85],[25.11,4,2.85]],faces:[[0,1,2],[0,2,3]]};
  const f=navigationFixture(engine,[wall]),before=f.pose();
  assert.equal(f.context.__modelNavigation.focusAt(400,300),true);
  const after=f.pose();assert.ok(distance(after.eye,before.eye)<1e-8,'re-centering pivot keeps the eye fixed');assert.ok(Math.abs(after.target[1]-4)<1e-9);
  assert.deepEqual(after.visible_part_names,['pivot wall']);assert.equal(after.section_height_m,null);assert.equal(after.focus_bounds_xy_m.length,4);
  f.el('#bathroomTop').click();const top=f.pose(),direction=top.target.map((v,i)=>v-top.eye[i]);
  assert.equal(top.projection,'orthographic');assert.ok(Math.abs(direction.reduce((s,v,i)=>s+v*top.up[i],0))<1e-8);assert.equal(top.section_height_m,1.2);
 });
 test(`${engine}: walkthrough fixes eye height, preserves position while looking, moves via touch/keyboard and exits to prior camera`,()=>{
  const f=navigationFixture(engine),before=f.pose();f.el('#btnWalk').click();const walk=f.pose();
  assert.equal(walk.mode,'walk');assert.equal(walk.projection,'perspective');assert.equal(walk.eye[2],1.65);assert.equal(walk.vertical_fov_radians,1.05);assert.equal(walk.focus_bounds_xy_m,null);assert.equal(walk.section_height_m,null);assert.equal(f.el('#walkControls').style.display,'grid');
  f.pointer('pointerdown',1,200,200);f.pointer('pointermove',1,230,210);f.pointer('pointerup',1,230,210);
  assert.ok(distance(f.pose().eye,walk.eye)<1e-9);assert.ok(distance(f.pose().target,walk.target)>.01);
  f.context.__modelNavigation.move(1,0,.2);assert.equal(f.pose().eye[2],1.65);assert.ok(distance(f.pose().eye,walk.eye)>.1);
  const beforeHeld=f.pose();f.el('#walkForward').dispatchEvent({type:'pointerdown',pointerId:2,preventDefault(){},stopPropagation(){}});f.context.__modelNavigation.tick(0);f.context.__modelNavigation.tick(50);assert.ok(distance(f.pose().eye,beforeHeld.eye)>.05);
  f.el('#walkForward').dispatchEvent({type:'pointercancel',pointerId:2,preventDefault(){}});const released=f.pose();f.context.__modelNavigation.tick(100);assert.deepEqual(f.pose(),released);
  f.dispatch('keydown',{code:'KeyD',preventDefault(){}});f.context.__modelNavigation.tick(150);assert.ok(distance(f.pose().eye,released.eye)>.05);f.dispatch('blur');const blurred=f.pose();f.context.__modelNavigation.tick(200);assert.deepEqual(f.pose(),blurred);
  f.dispatch('keydown',{code:'Escape'});assert.equal(f.pose().mode,'bathroom');assert.ok(distance(f.pose().eye,before.eye)<1e-8);assert.equal(f.el('#walkControls').style.display,'none');
 });
 test(`${engine}: walking cannot tunnel through a wall and can pass an actual doorway opening`,()=>{
  const wall=(name,x1,x2)=>({name,category:'sciany',geometry:'solid',color:[.8,.8,.8,1],positions_m:[[x1,4,0],[x2,4,0],[x2,4,2.85],[x1,4,2.85]],faces:[[0,1,2],[0,2,3]]});
  const solid=navigationFixture(engine,[wall('wall',25,28)]);solid.el('#btnWalk').click();solid.context.__modelNavigation.move(1,0,4);assert.ok(solid.pose().eye[1]>=4.12-1e-8);assert.ok(solid.pose().eye[1]<4.2);
  const doorway=navigationFixture(engine,[wall('wall left',25,26),wall('wall right',26.9,28)]);doorway.el('#btnWalk').click();doorway.context.__modelNavigation.move(1,0,3);assert.ok(doorway.pose().eye[1]<3,'opening must remain passable');
  doorway.context.__modelNavigation.move(0,1,50);assert.ok(doorway.pose().eye[0]>=.12&&doorway.pose().eye[0]<=27.88,'stay inside local model bounds');
 });
 test(`${engine}: camera position persists across reload, while an explicit bathroom link wins`,()=>{
  const f=navigationFixture(engine);f.el('#btnWalk').click();f.context.__modelNavigation.move(1,0,.3);const saved=f.pose();
  const resumed=navigationFixture(engine,[],'https://example.test/dom/',f.context.sessionStorage);assert.equal(resumed.pose().mode,'walk');assert.ok(distance(resumed.pose().eye,saved.eye)<1e-9);
  const explicit=navigationFixture(engine,[],'https://example.test/dom/?view=bathroom',f.context.sessionStorage);assert.equal(explicit.pose().mode,'bathroom');
 });
 test(`${engine}: walking follows floor elevations and respects the actual nonrectangular footprint`,()=>{
  const f=navigationFixture(engine);f.el('#btnWalk').click();
  f.run(`ROOM_LABELS[0].polygon_m=[[25,4],[28,4],[28,6],[25,6]];ROOM_LABELS.push({id:'raised',polygon_m:[[25,2],[28,2],[28,4],[25,4]],policy:{floor:{level_mm:240}}});VIEWER_CONFIG.footprint_m=[[25,4],[26,4],[26,2],[28,2],[28,6],[25,6]];`);
  f.context.__modelNavigation.move(1,0,3);assert.ok(Math.abs(f.pose().eye[2]-1.89)<1e-9,'eye stays at 1.65m above the raised floor');
  f.context.__modelNavigation.move(0,1,2);assert.ok(f.pose().eye[0]>=26,'camera cannot enter the missing part of the L-shaped footprint');
  f.el('#vbtn-interior').click();const state=JSON.parse(f.context.sessionStorage.getItem('dom_model_navigation_v1'));assert.equal(state.mode,'interior','leaving walk must replace its persisted camera mode');
 });
}
for(const engine of ['Canvas2D','WebGL'])test(`bathroom URL, visible controls and zone toggle work in ${engine}`,()=>{
  const f=fixture(georef,'https://example.test/dom/?view=bathroom');
  const uniforms=new Map();
  if(engine==='WebGL'){
    const mockGL=new Proxy({getShaderParameter:()=>true,getProgramParameter:()=>true,getAttribLocation:()=>0,getUniformLocation:(_program,name)=>name,getError:()=>0,uniform1i:(name,value)=>uniforms.set(name,value),uniform4fv:(name,value)=>uniforms.set(name,[...value])},{get:(target,key)=>key in target?target[key]:/^[A-Z_0-9]+$/.test(key)?0:()=>({})});
    f.el('#view').getContext=()=>mockGL;
  }else{
    const ctx={setTransform(){},fillRect(){},getImageData:(_x,_y,w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData(){}};
    f.el('#view').getContext=kind=>kind==='2d'?ctx:null;
  }
  f.context.document.createElementNS=()=>f.context.document.createElement();
  const part={name:'bathroom test fixture',__local:true,room_number:7,category:'wnetrze_elementy',color:[.8,.8,.8,1],positions_m:[[26,3,0],[26.1,3,.2],[26,3.1,.2]],faces:[[0,1,2]],geometry:'surface'};
  const floor={...part,name:'bathroom source floor',category:'podlogi',superseded_by_finish:true,positions_m:[[26,3,0],[26.1,3,0],[26,3.1,0]]};
  const tile={...floor,name:'bathroom finish tile',category:'wnetrze_elementy',superseded_by_finish:false};
  f.el('#finishReferences').checked=false;
  f.run(fullViewerScript({},false,[bathroomRoom],bathroomPreset,{parts:[part,floor,tile]}));
  assert.equal(f.context.__modelMode(),'bathroom');
  assert.equal(f.el('#bathroomViews').style.display,'inline');
  assert.equal(f.run('selectedRoom'),null,'opening the preset must not paint a selection overlay over the floor');
  assert.equal(f.el('#interiorTools').classList.contains('room-focus'),true);
  assert.equal(f.el('#interiorSelected').checked,true);
  assert.equal(f.el('#zoneBathroom').checked,true);
  assert.equal(f.context.__renderTest().visible,2,'the finish replaces the coplanar source floor');
  f.el('#interiorSelected').checked=false;
  assert.equal(f.context.__renderTest().visible,1,'the shell floor returns when the selected interior is disabled');
  f.el('#interiorSelected').checked=true;
  f.el('#zoneBathroom').checked=false;
  assert.equal(f.context.__renderTest().visible,1,'the shell floor returns when bathroom finishes are disabled');
  f.el('#bathroomTop').click();
  assert.equal(f.context.__modelMode(),'bathroom_top');
  assert.equal(new URL(f.context.location.href).searchParams.get('view'),'bathroom-top');
  assert.equal(f.el('#sectionEnabled').checked,true);
  assert.equal(f.run('selectedRoom'),null);
  assert.equal(f.context.__renderTest().visible,2);
  if(engine==='WebGL')assert.equal(uniforms.get('uFocusRoom'),1);
  f.el('#bathroomEntrance').click();
  assert.equal(f.context.__modelMode(),'bathroom');
  f.el('#vbtn-interior').click();
  assert.equal(f.context.__modelMode(),'interior');
  assert.equal(new URL(f.context.location.href).searchParams.has('view'),false);
  assert.equal(f.el('#bathroomViews').style.display,'none');
});

const smallBathroomRoom={...bathroomRoom,id:'R03',number:3,polygon_m:[[16.76,2.96],[18.7614,2.96],[18.7614,5.62],[16.76,5.62]],local_x:17.7607,local_y:4.29};
const laundryRoom={...bathroomRoom,id:'R02',number:2,name:'Pralnia',polygon_m:[[15.11,2.96],[16.61,2.96],[16.61,5.62],[15.11,5.62]],local_x:15.86,local_y:4.29};
const smallBathroomOptions={rooms:[bathroomRoom,smallBathroomRoom,laundryRoom],presets:{...bathroomPreset,small_bathroom:{room_id:'R03',room_ids:['R03','R02'],entrance_side:'east',entrance_cut_inset_mm:20,wall_context_mm:350,label:'Łazienka z pralnią'}},navigation:{...navigationConfig,room_starts:{...navigationConfig.room_starts,R03:{eye_mm:[18450,5010,1650],target_mm:[17000,4140,1400]}}}};
for(const engine of ['Canvas2D','WebGL']){
 test(`${engine}: small bathroom preset includes laundry, clips the eastern entrance and exports the same view`,()=>{
  const part=(name,number,x)=>({name,room_number:number,category:'wnetrze_elementy',color:[.8,.8,.8,1],positions_m:[[x,4,0],[x+.1,4,.2],[x,4.1,.2]],faces:[[0,1,2]],geometry:'surface'});
  const entranceFinish={...part('east entrance finish',3,18.748),positions_m:[[18.748,2.96,0],[18.748,4.5,0],[18.748,4.5,2.6],[18.76,2.96,2.6]],faces:[[0,1,2],[0,2,3]]};
  const f=navigationFixture(engine,[part('small sink',3,17),part('laundry cabinet',2,15.5),part('large bath',7,26),entranceFinish],'https://example.test/dom/?view=small-bathroom',null,smallBathroomOptions),initial=f.pose();
  assert.equal(initial.mode,'small_bathroom');assert.equal(initial.projection,'perspective');
  assert.equal(f.el('#focusedRoomSelect').value,'small_bathroom');assert.equal(f.el('#focusedRoomSelect').classList.contains('active'),true);
  assert.equal(f.el('#viewTitle').textContent,'Łazienka z pralnią · od wejścia · ściana wejściowa odcięta');
  assert.deepEqual(initial.visible_part_names,['small sink','laundry cabinet'],'the 12 mm entrance finish inside the room boundary must not hide the fixtures');
  const [minx,maxx,miny,maxy]=initial.focus_bounds_xy_m;
  assert.ok(Math.abs(minx-14.76)<1e-9);assert.ok(Math.abs(maxx-18.7414)<1e-9,'only the east boundary and its interior finish are cut away');
  assert.ok(Math.abs(miny-2.61)<1e-9&&Math.abs(maxy-5.97)<1e-9);
  assert.ok(initial.eye[0]>initial.target[0],'entrance view looks west from the real east entrance');
  f.el('#zoneSmallBathroom').checked=false;assert.deepEqual(f.pose().visible_part_names,[]);
  f.el('#bathroomTop').click();assert.equal(f.pose().mode,'small_bathroom_top');assert.equal(f.el('#zoneSmallBathroom').checked,true);
  assert.equal(f.pose().projection,'orthographic');assert.equal(f.pose().section_height_m,1.2);assert.ok(Math.abs(f.pose().focus_bounds_xy_m[1]-19.1114)<1e-9);
  assert.ok(f.pose().visible_part_names.includes('east entrance finish'),'the finish returns in plan view');
  assert.equal(new URL(f.context.location.href).searchParams.get('view'),'small-bathroom-top');
  f.el('#roomSelect').value='R02';f.el('#roomSelect').onchange();assert.equal(f.pose().mode,'small_bathroom_top','selecting the laundry keeps the two-room preset');
  f.el('#bathroomEntrance').click();assert.equal(f.pose().mode,'small_bathroom');
  f.el('#measureToggle').click();assert.equal(f.pose().mode,'small_bathroom_top','measurement retains the chosen bathroom');
  f.el('#btnTilt2D3D').click();assert.equal(f.pose().mode,'small_bathroom');
  f.el('#focusedRoomSelect').value='bathroom';f.el('#focusedRoomSelect').onchange();assert.equal(f.pose().mode,'bathroom');assert.deepEqual(f.pose().visible_part_names,['large bath']);
  assert.ok(f.pose().focus_bounds_xy_m[3]>6.4182&&f.pose().focus_bounds_xy_m[3]<6.4192,'presets without an inset retain the original boundary cut');
  f.el('#focusedRoomSelect').value='small_bathroom';f.el('#focusedRoomSelect').onchange();assert.equal(f.pose().mode,'small_bathroom');
  f.el('#vbtn-interior').click();assert.equal(new URL(f.context.location.href).searchParams.has('view'),false);assert.equal(f.el('#bathroomViews').style.display,'none');
  assert.equal(f.el('#view').listenerCount('pointerdown'),1);
 });
 test(`${engine}: small bathroom top deep link and walkthrough use R03 and restore the chosen room`,()=>{
  const f=navigationFixture(engine,[],'https://example.test/dom/?view=small-bathroom-top',null,smallBathroomOptions),before=f.pose();
  assert.equal(before.mode,'small_bathroom_top');
  f.el('#btnWalk').click();const walk=f.pose();assert.equal(walk.mode,'walk');assert.ok(distance(walk.eye,[18.45,5.01,1.65])<1e-9);
  assert.equal(walk.focus_bounds_xy_m,null);assert.equal(walk.section_height_m,null);assert.ok(walk.target[0]<walk.eye[0]);
  f.context.__modelNavigation.move(1,0,.1);assert.ok(distance(f.pose().eye,walk.eye)>.09);
  f.dispatch('keydown',{code:'Escape'});assert.equal(f.pose().mode,'small_bathroom_top');assert.ok(distance(f.pose().eye,before.eye)<1e-8);
  const explicit=navigationFixture(engine,[],'https://example.test/dom/?view=small-bathroom',f.context.sessionStorage,smallBathroomOptions);assert.equal(explicit.pose().mode,'small_bathroom');
 });
}

const bedroomRoom={...bathroomRoom,id:'R08',number:8,name:'Sypialnia',polygon_m:[[23.96,6.7192],[27.4371,6.7192],[27.4371,10.36],[23.96,10.36]],local_x:25.69855,local_y:8.5396};
const bedroomOptions={rooms:[...smallBathroomOptions.rooms,bedroomRoom],presets:{...smallBathroomOptions.presets,bedroom:{room_id:'R08',entrance_side:'south',entrance_cut_inset_mm:20,wall_context_mm:350,label:'Sypialnia'}},navigation:{...smallBathroomOptions.navigation,room_starts:{...smallBathroomOptions.navigation.room_starts,R08:{eye_mm:[24510,7169.2,1650],target_mm:[25700,9619.2,1350]}}}};
const bedroomPart=(name,extras={})=>({name,room_number:8,category:'wnetrze_elementy',interior_layer:'selected',bedroom_fixture:true,interior_fixture:name,color:[.8,.8,.8,1],positions_m:[[25,8,0],[25.1,8,.2],[25,8.1,.2]],faces:[[0,1,2]],geometry:'surface',...extras});
for(const engine of ['Canvas2D','WebGL']){
 test(`${engine}: bedroom routes focus R08, cut the south finish and preserve the chosen room in plan and camera exports`,()=>{
  const southFinish=bedroomPart('south entrance finish',{interior_finish:true,positions_m:[[23.96,6.724,0],[27.4371,6.724,0],[27.4371,6.7312,2.85]]});
  const f=navigationFixture(engine,[bedroomPart('bed'),bedroomPart('nightstand'),southFinish,bedroomPart('bath outside bedroom',{room_number:7,positions_m:[[25.7,6.42,0],[25.8,6.42,.2],[25.7,6.3,.2]]})],'https://example.test/dom/?view=bedroom',null,bedroomOptions),initial=f.pose();
  assert.equal(initial.mode,'bedroom');assert.equal(initial.projection,'perspective');assert.equal(initial.coordinate_frame,'building_local');
  assert.equal(f.el('#focusedRoomSelect').value,'bedroom');assert.equal(f.el('#focusedRoomSelect').classList.contains('active'),true);
  assert.equal(f.el('#viewTitle').textContent,'Sypialnia · od wejścia · ściana wejściowa odcięta');assert.equal(f.el('#bathroomTop').textContent,'Sypialnia z góry');
  assert.deepEqual(initial.visible_part_names,['bed','nightstand']);
  const expected=[23.61,27.7871,6.7392,10.71];initial.focus_bounds_xy_m.forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-9));
  assert.ok(initial.eye[1]<initial.target[1],'the real south entrance looks north toward the headboard');
  f.el('#bathroomTop').click();const top=f.pose();assert.equal(top.mode,'bedroom_top');assert.equal(top.projection,'orthographic');assert.equal(top.section_height_m,1.2);
  assert.ok(Math.abs(top.focus_bounds_xy_m[2]-6.3692)<1e-9);assert.ok(top.visible_part_names.includes('south entrance finish'));assert.ok(!top.visible_part_names.includes('bath outside bedroom'),'room metadata excludes the neighboring bathroom even inside wall context');
  assert.equal(new URL(f.context.location.href).searchParams.get('view'),'bedroom-top');
  f.el('#roomSelect').value='R08';f.el('#roomSelect').onchange();assert.equal(f.pose().mode,'bedroom_top');
  f.el('#bathroomEntrance').click();f.el('#measureToggle').click();assert.equal(f.pose().mode,'bedroom_top');f.el('#btnTilt2D3D').click();assert.equal(f.pose().mode,'bedroom');
  f.el('#focusedRoomSelect').value='small_bathroom';f.el('#focusedRoomSelect').onchange();assert.equal(f.pose().mode,'small_bathroom');f.el('#focusedRoomSelect').value='bedroom';f.el('#focusedRoomSelect').onchange();assert.equal(f.pose().mode,'bedroom');
  f.el('#vbtn-interior').click();assert.equal(new URL(f.context.location.href).searchParams.has('view'),false);assert.equal(f.el('#bathroomViews').style.display,'none');
  assert.equal(f.el('#view').listenerCount('pointerdown'),1,'all room presets share the same touch navigation');
 });
 test(`${engine}: bedroom finishes and ceiling follow both the room zone and selected-interior switches`,()=>{
  const floor=bedroomPart('shell floor',{interior_layer:null,category:'podlogi',superseded_by_finish:true}),ceiling=bedroomPart('shell ceiling',{interior_layer:null,category:'sufity',superseded_by_finish:true});
  const f=navigationFixture(engine,[floor,ceiling,bedroomPart('selected floor',{interior_finish:true}),bedroomPart('selected ceiling',{category:'sufity',interior_finish:true}),bedroomPart('bed')],'https://example.test/dom/?view=bedroom',null,bedroomOptions);
  assert.deepEqual(f.pose().visible_part_names,['selected floor','bed']);f.el('#ceilings').checked=true;assert.deepEqual(f.pose().visible_part_names,['selected floor','selected ceiling','bed']);
  f.el('#zoneBedroom').checked=false;assert.deepEqual(f.pose().visible_part_names,['shell floor','shell ceiling'],'turning off the bedroom must restore the shell, including its ceiling');
  f.el('#zoneBedroom').checked=true;f.el('#interiorSelected').checked=false;assert.deepEqual(f.pose().visible_part_names,['shell floor','shell ceiling']);
  f.el('#interiorSelected').checked=true;assert.deepEqual(f.pose().visible_part_names,['selected floor','selected ceiling','bed']);
 });
 test(`${engine}: bedroom top link starts walking through DR06 and restores the bedroom camera`,()=>{
  const f=navigationFixture(engine,[],'https://example.test/dom/?view=bedroom-top',null,bedroomOptions),before=f.pose();assert.equal(before.mode,'bedroom_top');
  f.el('#btnWalk').click();const walk=f.pose();assert.equal(walk.mode,'walk');assert.ok(distance(walk.eye,[24.51,7.1692,1.65])<1e-9);assert.equal(walk.focus_bounds_xy_m,null);assert.equal(walk.section_height_m,null);assert.ok(walk.target[1]>walk.eye[1]);
  f.context.__modelNavigation.move(1,0,.1);assert.ok(distance(f.pose().eye,walk.eye)>.09);assert.equal(f.pose().eye[2],1.65);
  f.dispatch('keydown',{code:'Escape'});assert.equal(f.pose().mode,'bedroom_top');assert.ok(distance(f.pose().eye,before.eye)<1e-8);
  const explicit=navigationFixture(engine,[],'https://example.test/dom/?view=bedroom',f.context.sessionStorage,bedroomOptions);assert.equal(explicit.pose().mode,'bedroom');
 });
}

for(const engine of ['Canvas2D','WebGL'])test(`${engine}: authored image texture loads once, affects only declared faces and stays visible after cutaway`,()=>{
 const images=[],uniformKinds=[],buffers=[];let output;
 const mural=bedroomPart('mural',{positions_m:[[24.6,10.1,.8],[26.8,10.1,.8],[26.8,10.1,2.5],[24.6,10.1,2.5]],faces:[[0,1,2],[0,2,3]],texture_url:'assets/textures/mural.jpg',texture_uv:[[0,0],[1,0],[1,1],[0,1]],texture_faces:[0]});
 const options={...bedroomOptions,prepare(f){
  f.context.Image=class{constructor(){this.naturalWidth=2;this.naturalHeight=2;images.push(this);}};
  if(engine==='WebGL'){const gl=f.el('#view').getContext();gl.uniform1i=(name,value)=>{if(name==='uUseTex')uniformKinds.push(value);};gl.bufferData=(_target,data)=>buffers.push([...data]);f.el('#view').getContext=()=>gl;}
  else{const ctx=f.el('#view').getContext('2d');ctx.putImageData=image=>{output=image.data;};f.el('#view').getContext=kind=>kind==='2d'?ctx:null;
   const create=f.context.document.createElement;f.context.document.createElement=tag=>tag==='canvas'?{getContext:()=>({drawImage(){},getImageData:()=>({data:new Uint8ClampedArray([255,0,0,255,255,0,0,255,255,0,0,255,255,0,0,255])})})}:create(tag);}
 }};
 const f=navigationFixture(engine,[mural,{...mural,name:'same asset hidden room',room_number:7}],'https://example.test/dom/?view=bedroom',null,options);
 assert.equal(images.length,1,'shared asset is fetched once');assert.equal(images[0].src,mural.texture_url);
 f.context.__renderTest();if(engine==='WebGL')assert.ok(!uniformKinds.includes(2),'the unready image leaves the base material intact');
 images[0].onload();f.context.__renderTest();
 assert.deepEqual(f.pose().visible_part_names,['mural']);
 if(engine==='WebGL'){assert.ok(uniformKinds.includes(2));assert.ok(buffers.some(v=>JSON.stringify(v)===JSON.stringify([0,0,1,0,1,1,-1,-1,-1,-1,-1,-1])),'only the declared front triangle has UVs; other faces retain the plain base');}
 else{let red=0,gray=0;for(let i=0;i<output.length;i+=4){if(output[i]>100&&output[i+1]<10&&output[i+2]<10)red++;if(output[i]>100&&Math.abs(output[i]-output[i+1])<2&&Math.abs(output[i]-output[i+2])<2)gray++;}assert.ok(red>200,'software rasterizer samples the image');assert.ok(gray>200,'the other face keeps its plain base material');}
});


const familyRoomDefinitions=[
 {key:'kids_room_1',route:'kids-room-1',id:'R04',number:4,label:'Pokój dziecięcy 1',bounds:[19.06,.56,21.935,4.31],side:'north',zone:'zoneKidsRoom1',eye:[20685,3710,1650],target:[20497.5,1960,1450]},
 {key:'kids_room_2',route:'kids-room-2',id:'R05',number:5,label:'Pokój dziecięcy 2',bounds:[22.085,.56,24.96,4.31],side:'north',zone:'zoneKidsRoom2',eye:[23335,3710,1650],target:[23522.5,1960,1450]},
 {key:'wardrobe',route:'wardrobe',id:'R09',number:9,label:'Garderoba',bounds:[20.21,6.7192,23.81,10.36],side:'east',zone:'zoneWardrobe',eye:[23360,9060,1650],target:[21710,8460,1450]},
 {key:'office',route:'office',id:'R15',number:15,label:'Gabinet',bounds:[7.01,.56,10.01,4.06],side:'east',zone:'zoneOffice',eye:[9610,3510,1650],target:[8460,2060,1450]}
];
const familyRoomOptions={
 rooms:[...bedroomOptions.rooms,...familyRoomDefinitions.map(({id,number,label,bounds:[x0,y0,x1,y1]})=>({...bathroomRoom,id,number,name:label,polygon_m:[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],local_x:(x0+x1)/2,local_y:(y0+y1)/2}))],
 presets:{...bedroomOptions.presets,...Object.fromEntries(familyRoomDefinitions.map(r=>[r.key,{room_id:r.id,label:r.label,entrance_side:r.side,entrance_cut_inset_mm:60,wall_context_mm:350}]))},
 navigation:{...bedroomOptions.navigation,room_starts:{...bedroomOptions.navigation.room_starts,...Object.fromEntries(familyRoomDefinitions.map(r=>[r.id,{eye_mm:r.eye,target_mm:r.target}]))}}
};
for(const engine of ['Canvas2D','WebGL']){
 for(const room of familyRoomDefinitions){
  test(`${engine}: ${room.route} keeps room geometry, finishes, plan routes and first-person start together`,()=>{
   const [x0,y0,x1,y1]=room.bounds,x=(x0+x1)/2,y=(y0+y1)/2;
   const part=(name,extras={})=>bedroomPart(name,{room_number:room.number,bedroom_fixture:undefined,positions_m:[[x,y,0],[x+.1,y,.2],[x,y+.1,.2]],...extras});
   const entrance=part('entrance finish',{interior_finish:true,positions_m:room.side==='east'?[[x1-.01,y0,0],[x1-.01,y1,0],[x1-.02,y1,2.85]]:[[x0,y1-.01,0],[x1,y1-.01,0],[x1,y1-.02,2.85]]});
   const f=navigationFixture(engine,[part('new furniture'),part('new floor',{interior_finish:true}),part('new ceiling',{category:'sufity',interior_finish:true}),part('source floor',{interior_layer:null,category:'podlogi',superseded_by_finish:true}),part('source ceiling',{interior_layer:null,category:'sufity',superseded_by_finish:true}),entrance,part('neighbor',{room_number:99})],`https://example.test/dom/?view=${room.route}`,null,familyRoomOptions);
   const entrancePose=f.pose();assert.equal(entrancePose.mode,room.key);assert.equal(entrancePose.projection,'perspective');assert.equal(f.el('#focusedRoomSelect').value,room.key);assert.equal(f.el('#focusedRoomSidebar').value,room.key);
   assert.deepEqual(entrancePose.visible_part_names,['new furniture','new floor']);
   assert.equal(f.el('#bathroomTop').textContent,room.label+' z góry');
   f.el('#ceilings').checked=true;assert.ok(f.pose().visible_part_names.includes('new ceiling'));
   f.el('#'+room.zone).checked=false;assert.deepEqual(f.pose().visible_part_names,['source floor','source ceiling'],'room zone restores only the shell');
   f.el('#'+room.zone).checked=true;f.el('#interiorSelected').checked=false;assert.deepEqual(f.pose().visible_part_names,['source floor','source ceiling'],'selected layer and finishes share the same toggle');
   f.el('#bathroomTop').click();const top=f.pose();assert.equal(top.mode,room.key+'_top');assert.equal(top.projection,'orthographic');assert.equal(new URL(f.context.location.href).searchParams.get('view'),room.route+'-top');assert.ok(top.visible_part_names.includes('entrance finish'));assert.ok(!top.visible_part_names.includes('neighbor'));
   f.el('#roomSelect').value=room.id;f.el('#roomSelect').onchange();assert.equal(f.pose().mode,room.key+'_top');
   f.context.__modelNavigation.enterWalk();assert.equal(f.pose().mode,'walk');assert.ok(distance(f.pose().eye,room.eye.map(v=>v/1000))<1e-8);assert.equal(f.el('#ceilings').checked,true);
   f.dispatch('keydown',{code:'Escape'});assert.equal(f.pose().mode,room.key+'_top');assert.ok(distance(f.pose().eye,top.eye)<1e-8);
   const linked=navigationFixture(engine,[],`https://example.test/dom/?view=${room.route}-top`,null,familyRoomOptions);assert.equal(linked.pose().mode,room.key+'_top');
  });
 }
 test(`${engine}: compact room selectors expose all seven rooms, preserve plan mode and synchronize with whole-house navigation`,()=>{
  const f=navigationFixture(engine,[],'https://example.test/dom/?view=bedroom',null,{...familyRoomOptions,prepare(f){f.el('#view').clientWidth=390;f.el('#view').clientHeight=720;}});
  const expected=['bathroom','small_bathroom','bedroom','wardrobe','kids_room_1','kids_room_2','office'];
  for(const selector of ['#focusedRoomSelect','#focusedRoomSidebar'])assert.deepEqual(f.el(selector).children.map(o=>o.value),expected);
  f.el('#focusedRoomSelect').value='kids_room_1';f.el('#focusedRoomSelect').onchange();assert.equal(f.pose().mode,'kids_room_1');assert.equal(f.el('#focusedRoomSidebar').value,'kids_room_1');
  f.el('#bathroomTop').click();f.el('#focusedRoomSidebar').value='office';f.el('#focusedRoomSidebar').onchange();assert.equal(f.pose().mode,'office_top');assert.equal(f.el('#focusedRoomSelect').value,'office');
  f.el('#focusedRoomSelect').value='';f.el('#focusedRoomSelect').onchange();assert.equal(f.pose().mode,'interior');assert.equal(f.el('#focusedRoomSidebar').value,'');assert.equal(new URL(f.context.location.href).searchParams.has('view'),false);
  assert.equal(f.el('#view').listenerCount('pointerdown'),1,'switching rooms must not add competing touch handlers');
 });
}
test('the compact room menu uses native labelled selects with independently scrollable house modes',()=>{
 assert.match(html,/<label[^>]+for="focusedRoomSelect"[^>]*>Pomieszczenie<select id="focusedRoomSelect">/);
 assert.match(html,/<label[^>]+for="focusedRoomSidebar"[^>]*>Pomieszczenie<select id="focusedRoomSidebar">/);
 assert.match(html,/\.view-mode-buttons\{[^}]*overflow-x:auto/);
 assert.match(html,/\.room-view-picker\{[^}]*flex-shrink:0/);
 assert.doesNotMatch(html,/<button[^>]+id="vbtn-(bathroom|small_bathroom|bedroom|wardrobe|kids_room_1|kids_room_2|office)"/);
});
