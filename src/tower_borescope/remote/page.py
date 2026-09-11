"""Web page served to phones: the live MJPEG stream with snapshot and record buttons."""

from __future__ import annotations

PAGE_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Tower Borescope</title>
<meta name="viewport"
      content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<style>
html,body{margin:0;height:100%;background:#0f1012;color:#e8e8ea;
  font-family:-apple-system,system-ui,sans-serif;overflow:hidden}
#v{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
#bar{position:absolute;left:0;right:0;bottom:0;display:flex;justify-content:center;
  gap:12px;padding:14px;padding-bottom:max(14px, env(safe-area-inset-bottom));
  background:linear-gradient(transparent,rgba(0,0,0,.6))}
button{font-size:17px;padding:12px 26px;border-radius:24px;border:0;background:#3b6fd6;
  color:#fff;font-weight:600}
button:active{background:#2b58b3}
#msg{position:absolute;top:14px;left:0;right:0;text-align:center;font-size:15px;
  opacity:0;transition:opacity .3s}
</style>
</head>
<body>
<img id="v" src="/stream">
<div id="msg"></div>
<div id="bar">
<button onclick="snap()">Snapshot</button>
<button onclick="rec()" id="r">Record</button>
</div>
<script>
function show(t){const m=document.getElementById('msg');m.textContent=t;
  m.style.opacity=1;setTimeout(()=>m.style.opacity=0,1800)}
async function snap(){await fetch('/snapshot',{method:'POST'});show('Snapshot taken')}
async function rec(){const r=await fetch('/record',{method:'POST'});
  const j=await r.json();
  document.getElementById('r').textContent=j.recording?'Stop':'Record';
  show(j.recording?'Recording':'Saved')}
document.getElementById('v').onerror=()=>setTimeout(()=>{
  document.getElementById('v').src='/stream?'+Date.now()},1500);
</script>
</body>
</html>
"""
