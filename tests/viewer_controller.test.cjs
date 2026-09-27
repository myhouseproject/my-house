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
  orientation: {heading: 0, tilt: 0, roll: 0}, altitude_mode: 'absolute',
  camera: {center: {lat: 50.852, lng: 19.088, altitude: 269}, heading: 27, tilt: 65, range: 110},
  model_url: 'dom_Gruszowa60.glb'
};
const plain = value => JSON.parse(JSON.stringify(value));

function fixture(metadata = georef) {
  const elements = new Map(), scripts = [], maps = [], models = [], clicked = [], storage = new Map();
  const node = () => {
    const classes = new Set();
    return {
      style: {}, children: [], checked: true, clientWidth: 800, clientHeight: 600,
      classList: {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x),
        toggle(x, on) {if (on) classes.add(x); else classes.delete(x);}},
      appendChild(x) {this.children.push(x);}, append(x) {this.children.push(x);},
      addEventListener() {}, remove() {this.removed = true;}, click() {clicked.push(this);},
      getContext: type => type === '2d' ? {} : null
    };
  };
  const el = id => {if (!elements.has(id)) elements.set(id, node()); return elements.get(id);};
  class Map3DElement {constructor(options) {Object.assign(this, node(), options); maps.push(this);}}
  class Model3DElement {constructor(options) {Object.assign(this, options); models.push(this);}}
  const context = {
    URL, URLSearchParams, Blob, console, clearTimeout,
    setTimeout(fn, ms) {const timer = setTimeout(fn, ms); timer.unref(); return timer;},
    requestAnimationFrame() {}, addEventListener() {}, devicePixelRatio: 1,
    $: el, GOOGLE_MODEL_GEOREF: structuredClone(metadata),
    location: {href: 'https://example.test/dom/index.html', search: '', reload() {context.reloads++;}}, reloads: 0,
    history: {replaceState() {}},
    document: {querySelector: el, querySelectorAll: () => [], addEventListener() {},
      createElement: node, head: {appendChild(script) {scripts.push(script);}}},
    localStorage: {setItem: (k, v) => storage.set(k, v), getItem: k => storage.get(k), removeItem: k => storage.delete(k)}
  };
  context.window = context;
  vm.createContext(context);
  return {context, scripts, maps, models, clicked, el, library: {Map3DElement, Model3DElement},
    run: source => vm.runInContext(source, context)};
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
  f.maps[0].center = {lat: 0}; f.maps[0].heading = 180; f.run('resetGoogleMapCamera()');
  assert.deepEqual(plain(f.maps[0].center), georef.camera.center);
  assert.equal(f.maps[0].heading, georef.camera.heading);
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

test('full viewer starts without WebGL and its Google quick button opens the key prompt', () => {
  const f = fixture();
  let script = html.split('<script>')[1].split('</script>')[0];
  for (const [marker, value] of Object.entries({__SCENE__: '{"parts":[]}', __GLB_INTERIOR__: '',
    __GLB_EXTERIOR__: '', __GOOGLE_MODEL_GEOREF__: JSON.stringify(georef), __ROOM_LABELS__: '[]', __ORTHO_JPG__: ''})) {
    script = script.replaceAll(marker, value);
  }
  f.run(script);
  assert.equal(f.context.__modelReady, true);
  assert.match(f.el('.version').textContent, /Canvas2D/);
  f.el('#vbtn-gmaps').onclick();
  assert.equal(f.context.__modelMode(), 'gmaps');
  assert.equal(f.el('#gmapsKeyPrompt').style.display, 'flex');
  assert.equal(f.el('#view').style.display, 'none');
  f.el('#vbtn-exterior').onclick();
  assert.equal(f.context.__modelMode(), 'exterior');
  assert.equal(f.el('#view').style.display, 'block');
});
