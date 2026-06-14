"""
Buckshot Roulette round tracker — single-file, always-on-top desktop app.

Everything (UI, styles, logic) lives in this one file, shown in an embedded
webview.

Sizing: on startup the app measures the exact pixel size that stage two needs
(its tallest layout, with the Shoot button showing, and a column of 4 shells
plus 8 in the chamber on single rows), then resizes the window in a short
feedback loop until the real viewport matches that size exactly. This makes
the fit correct on any display scaling. The window is then frame-locked so it
cannot be resized. Stage one is shorter, so it leaves a gap at the bottom —
by design.

Requirements:
    pip install pywebview

Run:
    python buckshot_tracker.py
"""

import sys
import threading
import time

try:
    import webview
except ImportError:
    sys.exit("pywebview is required. Install it with:  pip install pywebview")


WIN_TITLE = "Buckshot Tracker"
INIT_W = 400     # provisional; corrected to a perfect fit on startup
INIT_H = 400


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Buckshot Tracker</title>
<style>
  :root{
    --bg:#3A3530; --panel:#453F38; --line:#5A5249; --text:#ECE6DE;
    --muted:#A89F94; --live:#e23b34; --live-bright:#ff6f61;
    --blank:#B6AB9C; --gray:#5a6068; --used:#34373d; --brass:#c79a44;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
  html,body{height:100%;overflow:hidden;}
  body{margin:0;background:var(--bg);color:var(--text);visibility:hidden;
    font-family:-apple-system,Segoe UI,Roboto,system-ui,sans-serif;
    display:flex;justify-content:center;padding:12px 14px;}
  .app{width:100%;max-width:520px;}
  header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;}
  h1{font-size:19px;font-weight:600;letter-spacing:.04em;margin:0;color:var(--muted);text-transform:uppercase;text-align:left;}
  button{font-family:inherit;cursor:pointer;}
  .btn{background:var(--panel);color:var(--text);border:1px solid var(--line);
    border-radius:8px;padding:8px 14px;font-size:13px;font-weight:600;
    transition:.12s;letter-spacing:.02em;}
  .btn:hover{border-color:#6d6358;}
  .btn:active{transform:scale(.97);}
  .btn:disabled{opacity:.35;color:var(--muted);cursor:default;transform:none;}
  .btn:disabled:hover{border-color:var(--line);}
  .reset{color:var(--muted);}

  .cols{display:flex;gap:14px;}
  .col{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:10px 12px;display:flex;flex-direction:column;align-items:center;gap:9px;}
  .col-label{font-size:12px;font-weight:600;letter-spacing:.03em;text-align:center;line-height:1.3;}
  .col-live .col-label{color:var(--live-bright);}
  .col-blank .col-label{color:var(--blank);}
  .col-label small{display:block;font-weight:400;color:var(--muted);font-size:10px;margin-top:2px;}

  /* stage 1 number grid */
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;width:100%;}
  .num{aspect-ratio:1;background:#2F2A25;border:1px solid var(--line);border-radius:10px;
    color:var(--text);font-size:20px;font-weight:600;display:flex;align-items:center;justify-content:center;}
  .num:hover{border-color:#6d6358;background:#3F3933;}
  .num.sel{background:#3a1714;border-color:var(--live);color:var(--live-bright);}
  .col-blank .num.sel{background:#2F2A25;border-color:var(--blank);color:#fff;}
  .hidden{display:none !important;}
  .invisible{visibility:hidden !important;}
  .hint{font-size:11px;color:var(--muted);text-align:center;margin-top:2px;min-height:14px;}

  .odds-value{margin-top:10px;text-align:center;font-size:26px;font-weight:700;
    color:var(--live-bright);font-variant-numeric:tabular-nums;}

  /* shells — never wrap, never scroll */
  .shellrow{display:flex;flex-wrap:nowrap;gap:5px;justify-content:center;min-height:50px;align-items:flex-end;}
  .shell{width:26px;height:50px;flex:none;display:block;pointer-events:none;}
  .draggable .shell{width:100%;height:100%;}
  .placed{width:26px;height:50px;flex:none;opacity:.3;}
  .placed .shell{width:100%;height:100%;}
  .draggable{width:26px;height:50px;flex:none;cursor:grab;touch-action:none;}
  .draggable:active{cursor:grabbing;}
  .draggable.dragging{opacity:.3;}
  .ghost{position:fixed;width:26px;height:50px;z-index:999;pointer-events:none;
    transform:translate(-50%,-50%);filter:drop-shadow(0 4px 6px rgba(0,0,0,.5));}

  .colbtns{height:32px;display:flex;align-items:center;}

  /* chamber line */
  .chamber-wrap{margin-top:10px;background:var(--panel);border:1px solid var(--line);
    border-radius:12px;padding:9px 10px;}
  .chamber-title{font-size:11px;color:var(--muted);letter-spacing:.04em;text-transform:uppercase;
    text-align:center;margin-bottom:7px;}
  .chamber{display:flex;align-items:flex-end;justify-content:center;gap:3px;min-height:64px;overflow:visible;}
  .slot{display:flex;flex-direction:column;align-items:center;gap:3px;flex:none;}
  .slot .shell{width:24px;height:46px;}
  .slot.first{margin-right:12px;}
  .slot .lbl{font-size:10px;color:var(--muted);}
  .slot.dropok .shell{outline:2px dashed var(--live-bright);outline-offset:2px;border-radius:4px;}
  .shoot-wrap{display:flex;justify-content:center;margin-top:9px;min-height:0;}
  .shoot{background:#2c1413;border-color:var(--live);color:var(--live-bright);}
  .shoot:hover{background:#3a1916;}
  .shoot:disabled,.shoot:disabled:hover{background:#2c1413;border-color:var(--line);}
  .empty-note{font-size:11px;color:var(--muted);text-align:center;}
</style>
</head>
<body>
<div class="app">
  <header>
    <h1>Buckshot Tracker</h1>
    <button class="btn reset" id="reset">Reset</button>
  </header>

  <!-- STAGE 1 -->
  <section id="stage1">
    <div class="cols">
      <div class="col col-live">
        <div class="col-label">Live</div>
        <div class="grid" id="liveGrid"></div>
        <div class="hint">How many live rounds?</div>
      </div>
      <div class="col col-blank">
        <div class="col-label">Blank</div>
        <div class="grid" id="blankGrid"></div>
        <div class="hint" id="blankHint">How many blank rounds?</div>
      </div>
    </div>
  </section>

  <!-- STAGE 2 -->
  <section id="stage2" class="hidden">
    <div class="cols">
      <div class="col col-live">
        <div class="col-label">Live</div>
        <div class="shellrow" id="liveRow"></div>
        <div class="colbtns"><button class="btn usedbtn" data-type="live">Eject</button></div>
      </div>
      <div class="col col-blank">
        <div class="col-label">Blank</div>
        <div class="shellrow" id="blankRow"></div>
        <div class="colbtns"><button class="btn usedbtn" data-type="blank">Eject</button></div>
      </div>
    </div>

    <div class="chamber-wrap">
      <div class="chamber-title">Shotgun</div>
      <div class="chamber" id="chamber"></div>
      <div class="shoot-wrap" id="shootWrap"></div>
    </div>

    <div class="odds-value" id="odds">&mdash;</div>
  </section>
</div>

<script>
"use strict";

/* ---------- shell SVGs (cropped viewBox) ---------- */
function shellSVG(cls,body,base,rim){
  // 12 gauge proportions: long plastic hull (~2/3), brass base, protruding rim/lip
  return `<svg class="${cls}" viewBox="258 32 164 350" xmlns="http://www.w3.org/2000/svg">
    <rect x="282" y="40" width="116" height="232" rx="12" fill="${body}"/>
    <rect x="282" y="262" width="116" height="78" fill="${base}"/>
    <rect x="266" y="334" width="148" height="34" rx="8" fill="${rim}"/>
  </svg>`;
}
function svg(type){
  if(type==='live')  return shellSVG('shell','#A82020','#C09030','#A87820'); // brighter
  if(type==='blank') return shellSVG('shell','#2E2E2E','#C09030','#A87820'); // dark
  if(type==='gray')  return shellSVG('shell','#909090','#909090','#909090'); // unknown
  if(type==='used')  return shellSVG('shell','#5A4A4A','#7A7060','#605850'); // spent
  return '';
}

/* ---------- state ---------- */
let state;
function fresh(){
  return {
    stage:1,
    liveCount:0, blankCount:0,
    pickedLive:false,
    live:{used:0, gray:0},   // colored = liveCount-used-gray
    blank:{used:0, gray:0},
    chamber:[]               // [{type:'live'|'blank'|null}], index 0 = next to fire
  };
}
const total   = () => state.liveCount + state.blankCount;
const usedAll = () => state.live.used + state.blank.used;
const colored = c => (c==='live'? state.liveCount : state.blankCount) - state[c].used - state[c].gray;
const frontKnown = () => state.chamber.length>0 && state.chamber[0].type!==null;

/* ---------- elements ---------- */
const $ = id => document.getElementById(id);

/* ---------- stage 1 ---------- */
function buildGrids(){
  const mk = (grid,type)=>{
    grid.innerHTML='';
    for(let n=1;n<=4;n++){
      const b=document.createElement('button');
      b.className='num'; b.textContent=n;
      b.onclick=()=>pick(type,n,b);
      grid.appendChild(b);
    }
  };
  mk($('liveGrid'),'live');
  mk($('blankGrid'),'blank');
}
function pick(type,n,btn){
  const grid = btn.parentElement;
  grid.querySelectorAll('.num').forEach(x=>x.classList.remove('sel'));
  btn.classList.add('sel');
  if(type==='live'){
    state.liveCount=n; state.pickedLive=true;
    $('blankGrid').classList.remove('invisible');
    $('blankHint').classList.remove('invisible');
  }else{
    state.blankCount=n;
    enterStage2();
  }
}

/* ---------- stage transitions ---------- */
function enterStage2(){
  state.stage=2;
  state.chamber = Array.from({length:total()},()=>({type:null}));
  $('stage1').classList.add('hidden');
  $('stage2').classList.remove('hidden');
  render();
}
function reset(){
  state = fresh();
  buildGrids();
  $('blankGrid').classList.add('invisible');
  $('blankHint').classList.add('invisible');
  $('stage2').classList.add('hidden');
  $('stage1').classList.remove('hidden');
}

/* ---------- actions ---------- */
function ejectUnknown(type){           // "Eject" button: front is unknown, learned to be `type`
  if(frontKnown()) return;
  if(colored(type)<=0) return;
  state[type].used++;
  state.chamber.shift();
  afterFire();
}
function shoot(){                       // front is known: fire it
  if(!frontKnown()) return;
  const t = state.chamber[0].type;
  state[t].used++; state[t].gray--;
  state.chamber.shift();
  afterFire();
}
function markKnown(slotIdx,type){        // drag a colored shell onto a chamber slot
  if(state.chamber[slotIdx].type!==null) return;
  if(colored(type)<=0) return;
  state.chamber[slotIdx].type=type;
  state[type].gray++;
  render();
}
function afterFire(){
  if(usedAll()>=total()){ reset(); return; }
  render();
}

/* ---------- render stage 2 ---------- */
function autoReveal(){                    // when only one type can remain, place them all
  const ul=colored('live'), ub=colored('blank');
  let t=null;
  if(ul===0 && ub>0) t='blank';
  else if(ub===0 && ul>0) t='live';
  else return;
  state.chamber.forEach(slot=>{
    if(slot.type===null){ slot.type=t; state[t].gray++; }
  });
}
function render(){
  autoReveal();
  renderColumn('live',$('liveRow'));
  renderColumn('blank',$('blankRow'));
  renderChamber();
  renderOdds();
  const known=frontKnown();
  document.querySelectorAll('.usedbtn').forEach(b=>b.disabled=known);
  const sw=$('shootWrap'); sw.innerHTML='';
  const b=document.createElement('button');
  b.className='btn shoot'; b.textContent='Shoot';
  b.disabled=!known;                       // grayed out until the front shell is known
  b.onclick=shoot; sw.appendChild(b);
}
function fmtPct(p){                       // "66.7%", "50%", "100%", "0%"
  const r=Math.round(p*10)/10;
  return (Number.isInteger(r)? r : r.toFixed(1)) + '%';
}
function renderOdds(){
  const el=$('odds');
  if(state.chamber.length===0){ el.textContent='—'; return; }
  // if the front shell is already known, it's certain
  if(state.chamber[0].type!==null){
    el.textContent = state.chamber[0].type==='live' ? '100%' : '0%';
    return;
  }
  // otherwise: unknown live among unknown shells remaining in the gun
  const unkLive  = colored('live');
  const unkTotal = colored('live') + colored('blank');
  el.textContent = unkTotal===0 ? '—' : fmtPct(100*unkLive/unkTotal);
}
function renderColumn(type,row){
  row.innerHTML='';
  const st=state[type];
  // invariant order: used, placed(known), colored(remaining)
  for(let i=0;i<st.used;i++) row.insertAdjacentHTML('beforeend',svg('used'));
  for(let i=0;i<st.gray;i++){
    const p=document.createElement('div');
    p.className='placed'; p.innerHTML=svg(type);
    row.appendChild(p);
  }
  for(let i=0;i<colored(type);i++){
    const d=document.createElement('div');
    d.className='draggable'; d.innerHTML=svg(type);
    d.addEventListener('pointerdown',e=>startDrag(e,type,d));
    row.appendChild(d);
  }
}
function renderChamber(){
  const c=$('chamber'); c.innerHTML='';
  if(state.chamber.length===0){
    c.innerHTML='<div class="empty-note">Empty</div>'; return;
  }
  state.chamber.forEach((slot,i)=>{
    const d=document.createElement('div');
    d.className='slot'+(i===0?' first':'');
    if(slot.type===null) d.dataset.empty=i;
    d.innerHTML = svg(slot.type===null?'gray':slot.type) + `<span class="lbl">${i+1}</span>`;
    c.appendChild(d);
  });
}

/* ---------- pointer drag (mouse + touch) ---------- */
let drag=null;
function startDrag(e,type,el){
  e.preventDefault();
  el.classList.add('dragging');
  const ghost=document.createElement('div');
  ghost.className='ghost'; ghost.innerHTML=svg(type);
  document.body.appendChild(ghost);
  drag={type,el,ghost,slot:null};
  moveGhost(e);
  window.addEventListener('pointermove',moveGhost);
  window.addEventListener('pointerup',endDrag,{once:true});
}
function moveGhost(e){
  if(!drag) return;
  drag.ghost.style.left=e.clientX+'px';
  drag.ghost.style.top =e.clientY+'px';
  drag.ghost.style.display='none';
  const under=document.elementFromPoint(e.clientX,e.clientY);
  drag.ghost.style.display='';
  const slot=under&&under.closest('.slot[data-empty]');
  if(drag.slot && drag.slot!==slot) drag.slot.classList.remove('dropok');
  drag.slot=slot;
  if(slot) slot.classList.add('dropok');
}
function endDrag(e){
  if(!drag) return;
  const slot=drag.slot;
  drag.ghost.remove();
  if(slot){ markKnown(+slot.dataset.empty, drag.type); }
  else { drag.el.classList.remove('dragging'); }
  window.removeEventListener('pointermove',moveGhost);
  drag=null;
}

/* ---------- startup: measure perfect size, fit window, then show ---------- */
function reveal(){ document.body.style.visibility='visible'; }

function buildMaxLayout(){                 // tallest + widest stage two
  state = fresh(); state.liveCount=4; state.blankCount=4;
  state.chamber = Array.from({length:8},()=>({type:null}));
  state.chamber[0].type='live'; state.live.gray=1;   // front known -> Shoot shows
  $('stage1').classList.add('hidden');
  $('stage2').classList.remove('hidden');
  render();
}
function px(v){ return parseFloat(v)||0; }
function measureNeed(){                     // exact CSS px the window must contain
  buildMaxLayout();
  const cs = getComputedStyle;
  // widest of: two columns of 4 shells, or the chamber of 8 shells
  const colInner = Math.max($('liveRow').scrollWidth, $('blankRow').scrollWidth);
  const col   = document.querySelector('#stage2 .col');
  const colsE = document.querySelector('#stage2 .cols');
  const cw    = document.querySelector('#stage2 .chamber-wrap');
  const colSt = cs(col), cwSt = cs(cw);
  const colPad = px(colSt.paddingLeft)+px(colSt.paddingRight)+px(colSt.borderLeftWidth)+px(colSt.borderRightWidth);
  const cwPad  = px(cwSt.paddingLeft)+px(cwSt.paddingRight)+px(cwSt.borderLeftWidth)+px(cwSt.borderRightWidth);
  const colsGap = px(cs(colsE).gap);
  const colsW = 2*(colInner+colPad) + colsGap;
  const chamW = $('chamber').scrollWidth + cwPad;
  const bs = cs(document.body);
  const bodyPad = px(bs.paddingLeft)+px(bs.paddingRight);
  const w = Math.ceil(Math.max(colsW, chamW) + bodyPad) + 2;        // +2 safety so it never wraps
  // height = true content bottom (root overflow:hidden clamps scrollHeight, so
  // measure from the bottom-most element instead) + body's bottom padding
  const bottom = $('odds').getBoundingClientRect().bottom;
  const h = Math.ceil(bottom + px(bs.paddingBottom));
  return {w, h};
}

let need=null, fitTries=0;
function fitStep(){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.fit){ finishFit(); return; }
  const iw = window.innerWidth, ih = window.innerHeight;
  const dw = Math.abs(need.w - iw), dh = Math.abs(need.h - ih);
  if((dw<=1.5 && dh<=1.5) || fitTries>=8){ finishFit(); return; }
  fitTries++;
  Promise.resolve(api.fit(need.w, need.h, iw, ih)).then(()=>{
    requestAnimationFrame(()=>requestAnimationFrame(fitStep));
  }).catch(()=>finishFit());
}
function finishFit(){
  const api = window.pywebview && window.pywebview.api;
  if(api && api.lock){ try{ api.lock(); }catch(e){} }
  reset();
  reveal();
}
function startup(){
  const api = window.pywebview && window.pywebview.api;
  if(!api || !api.fit){ reset(); reveal(); return; }
  need = measureNeed();
  fitTries = 0;
  fitStep();
}
window.addEventListener('pywebviewready', ()=>{
  requestAnimationFrame(()=>requestAnimationFrame(startup));
});
setTimeout(reveal, 2500);   // safety: never stay hidden

/* ---------- wire up ---------- */
$('reset').onclick=reset;
document.querySelectorAll('.usedbtn').forEach(b=>{
  b.onclick=()=>ejectUnknown(b.dataset.type);
});
reset();
</script>
</body>
</html>
"""


def _strip_resize(hwnd):
    import ctypes
    user32 = ctypes.windll.user32
    GWL_STYLE = -16
    WS_THICKFRAME = 0x00040000
    WS_MAXIMIZEBOX = 0x00010000
    SWP = 0x0002 | 0x0001 | 0x0004 | 0x0020   # NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED
    getf = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    setf = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    style = getf(hwnd, GWL_STYLE)
    style &= ~(WS_THICKFRAME | WS_MAXIMIZEBOX)
    setf(hwnd, GWL_STYLE, style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP)


def lock_unresizable():
    """Strip the resize border / maximize box. Windows only; reliable even
    when the webview backend ignores resizable=False."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        for _ in range(50):                  # wait for the native window to exist
            hwnd = user32.FindWindowW(None, WIN_TITLE)
            if hwnd:
                _strip_resize(hwnd)
                return
            time.sleep(0.1)
    except Exception:
        pass


class Api:
    """Bridge: the page reports the exact content size it needs and the live
    viewport size; we resize the window and converge on a perfect fit even if
    window units differ from CSS pixels (DPI scaling)."""

    def __init__(self):
        self.ow = float(INIT_W)
        self.oh = float(INIT_H)
        self.prev_w = None   # (outer, inner) from the previous step
        self.prev_h = None

    @staticmethod
    def _solve(need, inner, outer, prev):
        # estimate d(outer)/d(inner) from two samples; default 1:1 on first call
        if prev is not None and abs(inner - prev[1]) > 0.5:
            slope = (outer - prev[0]) / (inner - prev[1])
            if slope <= 0:
                slope = 1.0
        else:
            slope = 1.0
        return outer + slope * (need - inner)

    def fit(self, need_w, need_h, inner_w, inner_h):
        try:
            need_w = float(need_w); need_h = float(need_h)
            inner_w = float(inner_w); inner_h = float(inner_h)
        except (TypeError, ValueError):
            return
        new_w = self._solve(need_w, inner_w, self.ow, self.prev_w)
        new_h = self._solve(need_h, inner_h, self.oh, self.prev_h)
        self.prev_w = (self.ow, inner_w)
        self.prev_h = (self.oh, inner_h)
        self.ow, self.oh = new_w, new_h
        try:
            webview.windows[0].resize(int(round(new_w)), int(round(new_h)))
        except Exception:
            pass

    def lock(self):
        lock_unresizable()


def register_start_menu_shortcut():
    """Make the app searchable in Start: create a Start Menu shortcut on first
    run. Only acts on the built .exe (not the bare Python interpreter), and only
    if the shortcut doesn't already exist."""
    if not sys.platform.startswith("win"):
        return
    if not getattr(sys, "frozen", False):     # only the packaged .exe
        return
    try:
        import os
        import subprocess
        target = sys.executable
        programs = os.path.join(os.environ["APPDATA"],
                                r"Microsoft\Windows\Start Menu\Programs")
        lnk = os.path.join(programs, "Buckshot Tracker.lnk")
        if os.path.exists(lnk):
            return
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
            "$s.TargetPath='%s';"
            "$s.WorkingDirectory='%s';"
            "$s.Save()"
        ) % (lnk, target, os.path.dirname(target))
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=0x08000000,          # CREATE_NO_WINDOW
        )
    except Exception:
        pass


def main():
    register_start_menu_shortcut()
    webview.create_window(
        WIN_TITLE,
        html=HTML,
        width=INIT_W,
        height=INIT_H,
        resizable=False,
        frameless=True,
        on_top=True,
        js_api=Api(),
    )
    threading.Thread(target=lock_unresizable, daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
