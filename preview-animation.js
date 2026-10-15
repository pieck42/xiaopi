const assets={fox:'__FOX_DATA__',dragon:'__DRAGON_DATA__'};
const manifest=__ANIMATION_MANIFEST__;
const $=s=>document.querySelector(s),pet=$('#pet'),wrap=$('#petWrap');
const safeGet=k=>{try{return localStorage.getItem(k)}catch{return null}},safeSet=(k,v)=>{try{localStorage.setItem(k,v)}catch{}};
let skin=safeGet('xiaopi-skin')==='fox'?'fox':'dragon',timers=[],activeState='idle',stateStarted=performance.now(),ready=false;
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)');
const states={
  idle:['我在这里，陪你慢慢来。','待机 · 眨眼休息'],
  listening:['嗯，我在听。','倾听 · 侧耳靠近'],
  thinking:['让我想一想……','思考 · 托腮抬眼'],
  speaking:['今天也一起，做点有意思的事吧！','回答 · 张嘴示意'],
  happy:['见到你，开心加倍！','开心 · 眯眼挥手']
};
const atlases={};
function canvas(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c}
// Isolate each connected sprite at runtime, including sheets whose cells slightly overlap.
function extract(sheet,info){
  const [x,y,right,bottom]=info.box,w=right-x,h=bottom-y,c=canvas(w,h),ctx=c.getContext('2d',{willReadFrequently:true});
  ctx.drawImage(sheet,x,y,w,h,0,0,w,h);
  const pixels=ctx.getImageData(0,0,w,h),data=pixels.data,seen=new Uint8Array(w*h),queue=new Int32Array(w*h);
  const start=(info.seed[1]-y)*w+info.seed[0]-x;
  if(data[start*4+3]<=40)throw Error('Invalid sprite seed');
  let head=0,tail=1;queue[0]=start;seen[start]=1;
  const add=p=>{if(!seen[p]&&data[p*4+3]>40){seen[p]=1;queue[tail++]=p}};
  while(head<tail){const p=queue[head++],col=p%w;if(col>0)add(p-1);if(col<w-1)add(p+1);if(p>=w)add(p-w);if(p<w*(h-1))add(p+w)}
  const keep=new Uint8Array(w*h);
  for(let i=0;i<tail;i++){const p=queue[i],col=p%w,row=Math.floor(p/w);for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){if(col+dx>=0&&col+dx<w&&row+dy>=0&&row+dy<h)keep[p+dy*w+dx]=1}}
  for(let p=0;p<w*h;p++)if(!keep[p])data[p*4+3]=0;
  ctx.putImageData(pixels,0,0);return c;
}
async function loadSkin(name){
  const sheet=new Image();sheet.src=assets[name];await sheet.decode();
  const frames={};for(const [s,items] of Object.entries(manifest.skins[name].frames))frames[s]=items.map(info=>extract(sheet,info));
  atlases[name]=frames;
}
function frameAt(s,elapsed){if(reduceMotion.matches)return 0;const [a,b]=manifest.timings[s];return elapsed%(a+b)>=a?1:0}
function draw(target,name,s,index){
  if(!atlases[name])return;
  const sprite=atlases[name][s][index],ctx=target.getContext('2d'),size=target.width,ratio=size*.88/manifest.skins[name].extent;
  ctx.clearRect(0,0,size,size);ctx.imageSmoothingEnabled=false;
  const w=Math.round(sprite.width*ratio),h=Math.round(sprite.height*ratio);
  ctx.drawImage(sprite,Math.floor((size-w)/2),Math.round(size*.94)-h,w,h);
  target.dataset.skin=name;target.dataset.state=s;target.dataset.frame=index;
}
function redraw(now=performance.now()){
  if(!ready)return;
  draw(pet,skin,activeState,frameAt(activeState,now-stateStarted));
  document.querySelectorAll('[data-pose]').forEach(c=>draw(c,skin,c.dataset.pose,frameAt(c.dataset.pose,now)));
  draw($('#foxThumb'),'fox','idle',0);draw($('#dragonThumb'),'dragon','idle',0);
}
function stopDemo(){timers.forEach(clearTimeout);timers=[];$('#demo').textContent='播放五种动作演示'}
function state(s){activeState=s;stateStarted=performance.now();pet.className='pet '+s;$('#bubble').textContent=states[s][0];$('#status').textContent=states[s][1];pet.setAttribute('aria-label','小皮，'+(skin==='fox'?'小狐狸':'小龙')+'，'+states[s][1]);document.querySelectorAll('[data-state]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.state===s));redraw()}
function choose(s){skin=s;safeSet('xiaopi-skin',s);document.querySelectorAll('[data-skin]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.skin===s));state(activeState)}
document.querySelectorAll('[data-skin]').forEach(b=>b.onclick=()=>choose(b.dataset.skin));
document.querySelectorAll('[data-state]').forEach(b=>b.onclick=()=>{stopDemo();state(b.dataset.state)});
const range=$('#size');range.value=Math.min(360,Math.max(160,Number(safeGet('xiaopi-size'))||280));
function resize(){pet.style.width=pet.style.height=range.value+'px';$('#sizeValue').textContent=range.value;safeSet('xiaopi-size',range.value)}range.oninput=resize;
$('#demo').onclick=()=>{stopDemo();$('#demo').textContent='演示中…';state('idle');[[3300,'listening'],[6100,'thinking'],[9100,'speaking'],[11900,'happy'],[14900,'idle']].forEach(([t,s])=>timers.push(setTimeout(()=>{state(s);if(t===14900)stopDemo()},t)))};
function greet(){stopDemo();state('happy');timers.push(setTimeout(()=>state('idle'),1800))}
let drag=null;
wrap.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,left:wrap.offsetLeft,top:wrap.offsetTop,moved:false};wrap.setPointerCapture(e.pointerId)};
wrap.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>5)drag.moved=true;const stage=wrap.parentElement,half=pet.clientWidth/2;wrap.style.left=Math.max(half,Math.min(stage.clientWidth-half,drag.left+dx))+'px';wrap.style.top=Math.max(140,Math.min(stage.clientHeight-100,drag.top+dy))+'px'};
wrap.onpointerup=()=>{if(drag&&!drag.moved)greet();drag=null};wrap.onpointercancel=()=>drag=null;
wrap.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();greet()}};
document.addEventListener('keydown',e=>{if(e.target.matches('input,button'))return;const i=Number(e.key)-1;if(i>=0&&i<5){stopDemo();state(manifest.states[i])}});
$('#reset').onclick=()=>{wrap.style.left='50%';wrap.style.top='52%'};
resize();
Promise.all(['fox','dragon'].map(loadSkin)).then(()=>{ready=true;choose(skin);setInterval(()=>redraw(),70)}).catch(error=>{$('#bubble').textContent='动作素材未能加载，请重新打开预览文件。';$('#status').textContent='加载失败';console.error(error)});
