const test = require('node:test');
const assert = require('node:assert/strict');
const {makeRenderCamera} = require('../viewer_capture.js');
const base = {coordinate_frame:'building_local',units:'m',up_axis:'Z',projection:'perspective',
  eye:[26,6,1.6],target:[26,2,1.6],up:[0,0,1],viewport:{width:390,height:750},
  vertical_fov_radians:Math.PI/3,visible_part_names:['wall','floor'],section_height_m:null,focus_bounds_xy_m:null};
const settings={max_long_edge_px:2000};

test('portrait phone camera preserves canonical pose, vertical field of view and aspect',()=>{
  const actual=makeRenderCamera(base,settings,[-.1,3]);
  assert.deepEqual(actual.eye,base.eye);assert.deepEqual(actual.target,base.target);
  assert.deepEqual(actual.resolution,[1040,2000]);assert.equal(actual.aspect_ratio,.52);
  assert.ok(Math.abs(actual.vertical_fov_degrees-60)<1e-10);
  assert.equal(Object.hasOwn(actual,'section_height_m'),false);
  assert.equal(Object.hasOwn(actual,'clip_bounds_m'),false);
});
test('orthographic bathroom export carries actual cut, visibility and nonvertical up',()=>{
  const actual=makeRenderCamera({...base,projection:'orthographic',up:[0,1,0],
    orthographic_height_m:5,section_height_m:1.2,focus_bounds_xy_m:[25,28,2,6],
    visible_part_names:['floor','floor','ceiling']},settings,[-.2,3]);
  assert.deepEqual(actual.clip_bounds_m,[[25,2,-.2],[28,6,3]]);
  assert.equal(actual.section_height_m,1.2);assert.equal(actual.orthographic_height_m,5);
  assert.deepEqual(actual.up,[0,1,0]);assert.deepEqual(actual.visible_part_names,['floor','ceiling']);
  assert.equal(Object.hasOwn(actual,'vertical_fov_degrees'),false);
});
test('map camera, empty scene and nonfinite camera cannot be sent as interior renders',()=>{
  for(const change of [{coordinate_frame:'site'},{visible_part_names:[]},{eye:[NaN,0,0]},
    {viewport:{width:0,height:800}},{projection:'unknown'}]){
    assert.throws(()=>makeRenderCamera({...base,...change},settings,[-.1,3]));
  }
});
