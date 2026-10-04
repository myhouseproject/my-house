// Local-metric math gates shared by both rendering paths.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../podglad_szablon.html'),'utf8');
const source=html.slice(html.indexOf('// Local model coordinates'),html.indexOf('populateProjectMetadata();'));
function fixture(){
 const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,{checked:true,value:'1.2',textContent:''});return elements.get(id);};
 const context={SCENE:{parts:[]},SCENE_LOCAL:{parts:[]},VIEWER_CONFIG:{bounds_m:{minx:0,maxx:28,miny:0,maxy:12}},ROOM_LABELS:[],canvas:{clientWidth:800,clientHeight:600,getBoundingClientRect:()=>({left:0,top:0})},$:el,console};
 vm.createContext(context);vm.runInContext(source,context);return {run:s=>vm.runInContext(s,context),el,context};
}
const cube={positions_m:[[0,0,0],[2,0,0],[2,3,0],[0,3,0],[0,0,2],[2,0,2],[2,3,2],[0,3,2]],faces:[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]};
test('closed slice keeps a wall footprint with exact local area, and no cap outside mesh',()=>{
 const f=fixture();f.context.part=cube;const loops=f.run('sectionLoops(part,1.2)');assert.equal(loops.length,1);
 const ps=loops[0],area=Math.abs(ps.reduce((a,p,i)=>{const q=ps[(i+1)%ps.length];return a+p[0]*q[1]-q[0]*p[1]},0))/2;
 assert.ok(Math.abs(area-6)<1e-9);assert.equal(f.run('sectionLoops(part,3).length'),0);
});
test('metric inverse projection preserves lengths with a translated rotated screen frame',()=>{
 const f=fixture();f.run('drawingProject=v=>[200+v[0]*30-v[2]*40,100+v[0]*40+v[2]*30]');
 const p=f.run('planePointAt(390,20)');assert.ok(Math.abs(p[0]-1)<1e-9);assert.ok(Math.abs(p[1]-4)<1e-9);
});
test('two-point measurement snaps only visible local geometry and distinguishes free points',()=>{
 const f=fixture();f.run(`viewerMode='top';measurementOn=true;drawingProject=v=>[v[0]*100,-v[2]*100];currentVisibility=o=>o.name!=='hidden';ALL_PARTS.push({__local:true,name:'hidden',category:'sciany',positions_m:[[1,1,0]]},{__local:true,name:'visible',category:'sciany',positions_m:[[2,1,0],[3,1,0]]},{__local:false,name:'map',category:'sciany',positions_m:[[1.05,1,0]]});`);
 assert.equal(f.run('handlePlanClick(100,100)'),true);assert.equal(f.run('measurePoints[0].snapped'),false);
 f.run('measurePoints=[];handlePlanClick(204,101);handlePlanClick(298,101)');assert.equal(f.run('measurePoints.every(p=>p.snapped)'),true);assert.match(f.el('#measureReading').textContent,/1,000 m/);assert.match(f.el('#measureReading').textContent,/narożniki modelu/);
});
test('interior scene cannot include map geometry even with map layers enabled',()=>{
 const f=fixture();assert.equal(f.run("sceneEnabled({__local:false,name:'map',category:'sciany'},'interior')"),false);assert.equal(f.run("sceneEnabled({__local:true,name:'local',category:'sciany'},'top')"),true);assert.equal(f.run("sceneEnabled({__local:true,name:'local',category:'sciany'},'geo')"),false);
});

function bathroomFixture(){
 const f=fixture();f.context.VIEWER_CONFIG.parameters={finished_ceiling_height_mm:2850};f.context.VIEWER_CONFIG.room_presets={bathroom:{room_id:'R07',entrance_side:'north',wall_context_mm:350}};
 f.context.ROOM_LABELS.push({id:'R07',number:7,polygon_m:[[25.11,2.1692],[27.7374,2.1692],[27.7374,6.4192],[25.11,6.4192]],policy:{floor:{level_mm:0},ceiling:{level_mm:2850}}});return f;
}
test('bathroom entrance camera fits full room height in both projections and east is on the left',()=>{
 for(const webgl of [false,true]){
  const f=bathroomFixture();f.context.gl=webgl?{}:null;
  const c=f.run("focusedCamera('bathroom')"),b=f.run("focusedBounds('bathroom')");
  assert.equal(c.yaw,Math.PI);assert.equal(c.target[1],2.85/2);
  const vertical=2.85*Math.cos(c.pitch)+(b.maxy-b.miny)*Math.sin(c.pitch);
  const nearDepth=((b.maxy-b.miny)*Math.cos(c.pitch)+2.85*Math.sin(c.pitch))/2;
  const height=2*(c.distance-nearDepth)*Math.tan(.72/2);
  assert.ok(height>=vertical*1.3,`full height must fit with margin: ${height} >= ${vertical}`);
  assert.ok(Math.cos(c.yaw)<0,'east +X projects toward screen left from north entrance');
 }
});
test('bathroom cutaway removes the entrance wall and neighboring geometry without editing parts',()=>{
 const f=bathroomFixture();const wall=[[25,0,-6.6],[28,0,-6.6],[28,3,-6.6]],copy=JSON.stringify(wall);f.context.wall=wall;
 assert.equal(f.run("clipPolygonToFocus(wall,'bathroom').length"),0);
 assert.equal(JSON.stringify(wall),copy);
 assert.equal(f.run("sceneEnabled({__local:true,room_number:10,category:'wnetrze_elementy',positions_m:[[26,3,0]]},'bathroom')"),false);
 assert.equal(f.run("sceneEnabled({__local:true,room_number:10,category:'wnetrze_elementy',positions_m:[[26,3,0]]},'interior')"),true);
 const b=f.run("focusedBounds('bathroom')");assert.ok(b.maxy<6.4192);
 assert.equal(f.run("focusedBounds('bathroom_top').maxy"),6.4192+.35);
});

test('bathroom focus preserves both corner window frames embedded outside the floor polygon',()=>{
 const f=bathroomFixture();
 for(const triangle of [[[26.85,0,-1.9742],[27.72,0,-1.9742],[27.72,2.58,-1.9742]],[[27.9324,0,-2.1867],[27.9324,0,-3.0517],[27.9324,2.58,-3.0517]]]){
  f.context.frame=triangle;
  assert.equal(f.run("clipPolygonToFocus(frame,'bathroom').length"),3);
  assert.equal(f.run("clipPolygonToFocus(frame,'bathroom_top').length"),3);
 }
});
test('software bathroom perspective matches the WebGL projection and uses reciprocal depth',()=>{
 const f=fixture();f.context.projection={eye:[0,0,10],target:[0,0,0],X:[1,0,0],Y:[0,1,0],Z:[0,0,1],width:800,height:600,distance:10,perspective:true};
 const far=f.run('softwareProjectPoint([1,1,0],projection)'),near=f.run('softwareProjectPoint([1,1,5],projection)'),focal=600/(2*Math.tan(.72/2));
 assert.ok(Math.abs(far[0]-(400+focal/10))<1e-9);assert.ok(Math.abs(far[1]-(300-focal/10))<1e-9);
 assert.ok(Math.abs((near[0]-400)/(far[0]-400)-2)<1e-9);assert.equal(far[2],.1);assert.equal(near[2],.2);
 const orthographic=f.run('softwareProjectPoint([1,1,0],{...projection,perspective:false})');
 assert.ok(Math.abs(orthographic[0]-(400+600/5.2))<1e-9);assert.equal(orthographic[2],-10);
});
test('software perspective clips triangles at the near plane before division',()=>{
 const f=fixture();const polygon=f.run('clipPolygonToNearPlane([[0,0,-1],[1,0,-1],[0,1,1]],[0,0,0],[0,0,1])');
 assert.equal(polygon.length,4);assert.ok(polygon.every(v=>v[2]<=-.2+1e-12));
 assert.equal(f.run('clipPolygonToNearPlane([[0,0,1],[1,0,1],[0,1,1]],[0,0,0],[0,0,1]).length'),0);
});

test('surface texture UVs survive near and height clipping and interpolate with perspective depth',()=>{
 const f=fixture(),plain=v=>JSON.parse(JSON.stringify(v));
 const clipped=f.run('clipPolygonToNearPlane([[0,0,-1,0,0],[1,0,-1,1,0],[0,1,1,0,1]],[0,0,0],[0,0,1])');
 assert.equal(clipped.length,4);assert.ok(clipped.every(v=>v.length===5&&v.every(Number.isFinite)));assert.ok(clipped.some(v=>Math.abs(v[2]+.2)<1e-9&&Math.abs(v[4]-.4)<1e-9));
 const height=f.run('clipPolygonAtHeight([[0,0,-1,0,0],[1,0,-1,1,0],[0,2,-1,0,1]],1)');assert.ok(height.some(v=>v[1]===1&&v[4]===.5));
 const projected=f.run('softwareTextureProjection([[0,0],[1,0],[0,1]],[1,.5,.25],true)'),weights=[.2,.3,.5],den=projected.reduce((sum,p,i)=>sum+p[2]*weights[i],0),u=projected.reduce((sum,p,i)=>sum+p[0]*weights[i],0)/den,v=projected.reduce((sum,p,i)=>sum+p[1]*weights[i],0)/den;
 assert.ok(Math.abs(u-.15/.475)<1e-9);assert.ok(Math.abs(v-.125/.475)<1e-9);assert.deepEqual(plain(f.run('softwareTextureProjection([[0,0],[1,0],[0,1]],[1,.5,.25],false)')),[[0,0,1],[1,0,1],[0,1,1]]);
});
