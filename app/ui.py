"""Interfaz web de configuración (HTML autocontenido, sin dependencias)."""

PAGE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>print-agent · Configuración</title>
<style>
  :root { --bg:#0f1115; --card:#1a1d24; --ink:#e8eaed; --muted:#9aa0aa;
          --line:#2a2e37; --acc:#c96442; --ok:#3fa66a; --bad:#d9534f; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif; }
  .wrap { max-width:920px; margin:0 auto; padding:24px 18px 60px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 20px; font-size:13px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:18px 18px 14px; margin-bottom:16px; }
  .card h2 { font-size:14px; text-transform:uppercase; letter-spacing:.04em;
             color:var(--muted); margin:0 0 14px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px 16px; }
  @media (max-width:560px){ .grid { grid-template-columns:1fr; } }
  label { display:block; font-size:13px; color:var(--muted); margin-bottom:4px; }
  input, select { width:100%; padding:9px 10px; background:#0f1115; color:var(--ink);
          border:1px solid var(--line); border-radius:8px; font:inherit; }
  input:focus, select:focus { outline:none; border-color:var(--acc); }
  .row-check { display:flex; align-items:center; gap:8px; margin:6px 0; }
  .row-check input { width:auto; }
  .row-check label { margin:0; color:var(--ink); }
  .hint { font-size:12px; color:var(--muted); margin:2px 0 0; }
  .bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:12px; }
  button { padding:9px 15px; border-radius:8px; border:1px solid var(--line);
           background:#222632; color:var(--ink); font:inherit; cursor:pointer; }
  button.primary { background:var(--acc); border-color:var(--acc); color:#fff; font-weight:600; }
  button.sm { padding:5px 10px; font-size:13px; }
  button.danger { color:var(--bad); }
  button:hover { filter:brightness(1.1); }
  .status { display:flex; gap:18px; flex-wrap:wrap; font-size:14px; align-items:center; }
  .status b { font-weight:600; }
  .pill { padding:2px 9px; border-radius:20px; font-size:12px; background:#222632; }
  .pill.ok { background:rgba(63,166,106,.18); color:var(--ok); }
  .pill.bad { background:rgba(217,83,79,.18); color:var(--bad); }
  .tag { font-size:11px; padding:1px 7px; border-radius:6px; background:rgba(201,100,66,.2);
         color:var(--acc); margin-left:6px; }
  table { width:100%; border-collapse:collapse; font-size:13px; margin-top:8px; }
  th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:middle; }
  th { color:var(--muted); font-weight:500; }
  .toast { position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
           background:#222632; border:1px solid var(--line); padding:10px 18px;
           border-radius:8px; opacity:0; transition:opacity .2s; pointer-events:none; }
  .toast.show { opacity:1; }
  .err { color:var(--bad); font-size:12px; word-break:break-word; }
  .muted { color:var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <h1>print-agent · Configuración</h1>
  <p class="sub">Servicio de impresión genérico. Cualquier sistema puede mandar trabajos a estas impresoras. Los cambios se aplican al instante.</p>

  <!-- ESTADO -->
  <div class="card">
    <h2>Estado</h2>
    <div class="status" id="status">Cargando…</div>
    <div class="bar">
      <select id="testPrinter" style="max-width:220px"></select>
      <button class="primary" onclick="testPrint()">Imprimir prueba</button>
      <button onclick="retryFailed()">Reintentar fallidos</button>
      <button onclick="clearFailed()">Vaciar fallidos</button>
      <button onclick="loadStatus()">Refrescar</button>
    </div>
    <div id="jobs"></div>
  </div>

  <!-- IMPRESORAS -->
  <div class="card">
    <h2>Impresoras</h2>
    <table id="printersTbl"><tr><th>Nombre</th><th>Host / Recurso</th><th>Modo</th><th></th></tr></table>
    <div class="bar"><button class="sm" onclick="newPrinter()">+ Nueva impresora</button></div>

    <form id="pform" style="margin-top:14px; display:none">
      <div class="grid">
        <div><label>Nombre (para rutear, ej. caja / cocina)</label><input name="name" placeholder="caja"></div>
        <div><label>IP del PC Windows (SMB_HOST)</label><input name="smb_host" placeholder="192.168.1.50"></div>
        <div><label>Recurso compartido (SMB_SHARE)</label><input name="smb_share" placeholder="TICKETERA"></div>
        <div><label>Usuario Windows</label><input name="smb_user" placeholder="(vacío si es abierta)"></div>
        <div><label>Contraseña</label><input name="smb_pass" type="password" placeholder="(sin cambios)"></div>
        <div><label>Dominio / Grupo</label><input name="smb_domain" placeholder="WORKGROUP"></div>
        <div><label>IP explícita (opcional)</label><input name="smb_ip" placeholder="si el nombre no resuelve"></div>
        <div>
          <label>Modo</label>
          <select name="print_mode">
            <option value="escpos">ESC/POS — Generic Text Only / RAW (recomendado)</option>
            <option value="text">Texto plano — driver del fabricante</option>
          </select>
        </div>
        <div><label>Ancho (caracteres)</label><input name="paper_width_chars" type="number" min="24" max="64" placeholder="48"><p class="hint">80mm = 48</p></div>
        <div><label>Codepage</label><input name="codepage" placeholder="cp850"><p class="hint">cp850 para acentos en español</p></div>
      </div>
      <div class="row-check"><input type="checkbox" name="cut_paper" id="cut_paper"><label for="cut_paper">Cortar papel (solo ESC/POS)</label></div>
      <div class="row-check"><input type="checkbox" name="open_drawer" id="open_drawer"><label for="open_drawer">Abrir cajón de dinero</label></div>
      <div class="row-check"><input type="checkbox" name="make_default" id="make_default"><label for="make_default">Marcar como impresora por defecto</label></div>
      <div class="bar">
        <button class="primary" type="button" onclick="savePrinter()">Guardar impresora</button>
        <button type="button" onclick="hidePrinterForm()">Cancelar</button>
      </div>
    </form>
  </div>

  <!-- CLIENTES -->
  <div class="card">
    <h2>Clientes / tokens</h2>
    <p class="hint" style="margin-top:-6px">Cada sistema que imprime usa su token (header <code>Authorization: Bearer &lt;token&gt;</code>). Si no defines ninguno, el servicio queda abierto en la red local.</p>
    <table id="clientsTbl"><tr><th>Cliente</th><th>Token</th><th></th></tr></table>
    <form id="cform" style="margin-top:12px">
      <div class="grid">
        <div><label>Nombre del sistema</label><input name="name" placeholder="sistema-pos"></div>
        <div><label>Token</label><input name="token" placeholder="pega o genera un token"></div>
      </div>
      <div class="bar">
        <button type="button" onclick="genToken()">Generar token</button>
        <button class="primary" type="button" onclick="saveClient()">Guardar cliente</button>
      </div>
    </form>
  </div>

  <!-- GLOBALES -->
  <div class="card">
    <h2>Reintentos y retención</h2>
    <form id="gform">
      <div class="grid">
        <div><label>Espera entre reintentos (seg)</label><input name="retry_delay_seconds" type="number" min="1"></div>
        <div><label>Máx. intentos (0 = infinito)</label><input name="max_attempts" type="number" min="0"></div>
        <div><label>Impresos a conservar (purga)</label><input name="keep_done" type="number" min="0"></div>
      </div>
      <div class="bar"><button class="primary" type="button" onclick="saveGlobals()">Guardar</button></div>
    </form>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
const PBOOL = ["cut_paper","open_drawer","make_default"];
let STATE = {printers:[], clients:[], default_printer:""};
function toast(m){ const t=document.getElementById('toast'); t.textContent=m; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),2200); }
function fmt(d){ return d ? d.replace('T',' ') : '—'; }
const esc = s => String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function loadSettings(){
  STATE = await (await fetch('api/settings')).json();
  // tabla impresoras
  let t = '<tr><th>Nombre</th><th>Host / Recurso</th><th>Modo</th><th></th></tr>';
  for(const p of STATE.printers){
    const def = p.name===STATE.default_printer ? '<span class="tag">por defecto</span>' : '';
    t += `<tr><td>${esc(p.name)}${def}</td><td class="muted">${esc(p.smb_host)} / ${esc(p.smb_share)}</td><td class="muted">${esc(p.print_mode)}</td>
      <td><button class="sm" onclick='editPrinter(${JSON.stringify(p.name)})'>editar</button>
          <button class="sm danger" onclick='delPrinter(${JSON.stringify(p.name)})'>borrar</button></td></tr>`;
  }
  if(!STATE.printers.length) t += '<tr><td colspan="4" class="muted">Sin impresoras. Añade una.</td></tr>';
  document.getElementById('printersTbl').innerHTML = t;
  // selector de prueba
  const sel = document.getElementById('testPrinter');
  sel.innerHTML = STATE.printers.map(p=>`<option value="${esc(p.name)}"${p.name===STATE.default_printer?' selected':''}>${esc(p.name)}</option>`).join('') || '<option value="">(sin impresoras)</option>';
  // tabla clientes
  let c = '<tr><th>Cliente</th><th>Token</th><th></th></tr>';
  for(const cl of STATE.clients){
    c += `<tr><td>${esc(cl.name)}</td><td class="muted">${cl.token?'•••••• (guardado)':'(sin token)'}</td>
      <td><button class="sm danger" onclick='delClient(${JSON.stringify(cl.name)})'>borrar</button></td></tr>`;
  }
  if(!STATE.clients.length) c += '<tr><td colspan="3" class="muted">Sin clientes: servicio abierto en la red local.</td></tr>';
  document.getElementById('clientsTbl').innerHTML = c;
  // globales
  const g = document.getElementById('gform');
  g.retry_delay_seconds.value = STATE.retry_delay_seconds;
  g.max_attempts.value = STATE.max_attempts;
  g.keep_done.value = STATE.keep_done;
}

// ---- impresoras ----
function showPrinterForm(){ document.getElementById('pform').style.display='block'; }
function hidePrinterForm(){ document.getElementById('pform').style.display='none'; }
function newPrinter(){
  const f=document.getElementById('pform'); f.reset();
  f.print_mode.value='escpos'; f.cut_paper.checked=true; f.paper_width_chars.value=48; f.codepage.value='cp850';
  showPrinterForm(); f.name.focus();
}
function editPrinter(name){
  const p = STATE.printers.find(x=>x.name===name); if(!p) return;
  const f=document.getElementById('pform'); f.reset();
  for(const k in p){ const el=f.elements[k]; if(!el) continue;
    if(PBOOL.includes(k)) el.checked=!!p[k]; else if(p[k]==='***') el.placeholder='(sin cambios)'; else el.value=p[k]; }
  f.make_default.checked = (name===STATE.default_printer);
  showPrinterForm();
}
async function savePrinter(){
  const f=document.getElementById('pform'); const body={};
  for(const el of f.elements){ if(!el.name) continue;
    if(PBOOL.includes(el.name)) body[el.name]=el.checked;
    else if(el.type==='password' && el.value==='') continue;
    else body[el.name]=el.value; }
  if(!body.name){ toast('La impresora necesita un nombre'); return; }
  const r=await fetch('api/printers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.ok){ toast('Impresora guardada ✓'); hidePrinterForm(); loadSettings(); loadStatus(); } else toast('Error al guardar');
}
async function delPrinter(name){ if(!confirm('¿Borrar la impresora '+name+'?'))return;
  await fetch('api/printers/'+encodeURIComponent(name),{method:'DELETE'}); toast('Borrada'); loadSettings(); loadStatus(); }

// ---- clientes ----
function genToken(){ const a=new Uint8Array(24); crypto.getRandomValues(a);
  document.getElementById('cform').token.value=[...a].map(b=>b.toString(16).padStart(2,'0')).join(''); }
async function saveClient(){
  const f=document.getElementById('cform');
  const body={name:f.name.value.trim(), token:f.token.value.trim()};
  if(!body.name){ toast('El cliente necesita un nombre'); return; }
  const r=await fetch('api/clients',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.ok){ toast('Cliente guardado ✓ (copia el token, no se vuelve a mostrar)'); f.reset(); loadSettings(); } else toast('Error');
}
async function delClient(name){ if(!confirm('¿Borrar el cliente '+name+'?'))return;
  await fetch('api/clients/'+encodeURIComponent(name),{method:'DELETE'}); toast('Borrado'); loadSettings(); }

// ---- globales ----
async function saveGlobals(){
  const f=document.getElementById('gform');
  const body={retry_delay_seconds:+f.retry_delay_seconds.value, max_attempts:+f.max_attempts.value, keep_done:+f.keep_done.value};
  const r=await fetch('api/globals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  toast(r.ok?'Guardado ✓':'Error');
}

// ---- estado / cola ----
async function loadStatus(){
  const s = await (await fetch('api/status')).json();
  const pend=`<span class="pill ${s.pending?'':'ok'}">pendientes: ${s.pending}</span>`;
  const fail=`<span class="pill ${s.failed?'bad':''}">fallidos: ${s.failed}</span>`;
  let html = pend+fail+`<span>Última impresión: <b>${fmt(s.last_ok)}</b></span>`;
  if(s.last_error) html += `<div class="err">Último error: ${esc(s.last_error)}</div>`;
  document.getElementById('status').innerHTML = html;
  const j = s.jobs || {pending:[],failed:[],done:[]};
  function tbl(title, rows, showErr){
    if(!rows.length) return '';
    let t=`<table><tr><th>${title}</th><th>impresora</th><th>origen</th><th>creado</th>${showErr?'<th>error</th>':'<th>impreso</th>'}</tr>`;
    for(const r of rows) t+=`<tr><td>${esc(r.job_id)}</td><td>${esc(r.printer)}</td><td>${esc(r.source)}</td><td>${fmt(r.created_at)}</td><td class="${showErr?'err':''}">${showErr?esc(r.last_error||''):fmt(r.printed_at)}</td></tr>`;
    return t+'</table>';
  }
  document.getElementById('jobs').innerHTML =
    tbl('en cola',j.pending,false)+tbl('fallidos',j.failed,true)+tbl('impresos (últimos)',j.done,false);
}
async function testPrint(){ const p=document.getElementById('testPrinter').value;
  const r=await fetch('api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({printer:p})});
  toast(r.ok?'Ticket de prueba enviado a la cola':'Error'); loadStatus(); }
async function retryFailed(){ const r=await (await fetch('api/retry',{method:'POST'})).json(); toast('Reencolados: '+r.moved); loadStatus(); }
async function clearFailed(){ if(!confirm('¿Borrar los pedidos fallidos?'))return; const r=await (await fetch('api/clear',{method:'POST'})).json(); toast('Borrados: '+r.removed); loadStatus(); }

loadSettings(); loadStatus(); setInterval(loadStatus, 4000);
</script>
</body>
</html>
"""
