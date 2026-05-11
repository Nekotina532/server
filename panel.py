#!/usr/bin/env python3
"""
VPS ETERNA - Panel Web v5.0 (Build Final Estable)
- Código 100% Completo
- Cero conflictos de reinicio.
- Filtros de spam y rastreo de CPU precisos.
- Gestor de archivos con auto-descubrimiento de ruta.
"""

import os
import sys
import time
import subprocess
import threading
import re
import html as html_mod
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

try:
    import psutil
    from flask import Flask, render_template_string, request, jsonify
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'flask', 'psutil', 'requests', 'werkzeug', '-q'])
    import psutil
    from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# =============================================
# AUTO-DESCUBRIDOR DE LA CARPETA DEL SERVIDOR
# =============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def find_server_dir():
    std_path = os.path.join(BASE_DIR, 'SRV', 'server')
    if os.path.exists(os.path.join(std_path, 'start.sh')):
        return std_path
    
    for root, dirs, files in os.walk(BASE_DIR):
        if 'start.sh' in files and ('PocketMine-MP.phar' in files or 'src' in dirs):
            return root
            
    return std_path

SERVER_DIR = find_server_dir()
os.makedirs(SERVER_DIR, exist_ok=True)

OUTPUT_LOG = '/tmp/mc_output.log'
COMMANDS_FILE = '/tmp/mc_commands'

DISK_TOTAL_GB = 10.0
RAM_TOTAL_GB = 14.0 

START_TIME = time.time()
_net = psutil.net_io_counters()
NET_INITIAL = {'recv': _net.bytes_recv, 'sent': _net.bytes_sent}

_console_pos = 0
_console_lock = threading.Lock()

Path(COMMANDS_FILE).touch(exist_ok=True)
Path(OUTPUT_LOG).touch(exist_ok=True)

HISTORY_LEN = 40
stats_history = {'cpu':[], 'mem':[], 'net_in': [], 'net_out':[]}
history_lock = threading.Lock()
_prev_net = {'recv': NET_INITIAL['recv'], 'sent': NET_INITIAL['sent']}
_prev_net_time = time.time()

_server_proc = None
_last_cpu_val = 0.0

# =============================================
# RASTREO PRECISO DE CPU (SIN FUEGO AMIGO)
# =============================================
def get_server_process():
    global _server_proc
    if _server_proc is not None:
        try:
            if _server_proc.is_running() and _server_proc.status() != psutil.STATUS_ZOMBIE:
                return _server_proc
        except: pass
            
    _server_proc = None
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = ' '.join(p.info['cmdline'] or[]).lower()
            if ('pocketmine' in cmd or 'genisys' in cmd) and 'panel.py' not in cmd:
                _server_proc = p
                _server_proc.cpu_percent() 
                return _server_proc
        except: pass
    return None

def record_stats():
    global _prev_net, _prev_net_time, _last_cpu_val
    try:
        proc = get_server_process()
        mem_pct_val = 0.0
        
        if proc:
            try:
                _last_cpu_val = proc.cpu_percent(interval=None) 
                mem_used_gb = proc.memory_info().rss / (1024 ** 3)
                mem_pct_val = (mem_used_gb / RAM_TOTAL_GB) * 100
            except: _last_cpu_val = 0.0
        else:
            _last_cpu_val = 0.0

        net = psutil.net_io_counters()
        now = time.time()
        dt = max(now - _prev_net_time, 0.1)

        net_in_rate = (net.bytes_recv - _prev_net['recv']) / dt / 1024
        net_out_rate = (net.bytes_sent - _prev_net['sent']) / dt / 1024

        _prev_net = {'recv': net.bytes_recv, 'sent': net.bytes_sent}
        _prev_net_time = now

        with history_lock:
            stats_history['cpu'].append(_last_cpu_val)
            stats_history['mem'].append(mem_pct_val)
            stats_history['net_in'].append(net_in_rate)
            stats_history['net_out'].append(net_out_rate)
            for k in stats_history:
                if len(stats_history[k]) > HISTORY_LEN:
                    stats_history[k] = stats_history[k][-HISTORY_LEN:]
    except: pass

def get_server_disk():
    total = 0
    try:
        for dirpath, _, filenames in os.walk(SERVER_DIR):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
    except: pass
    return round(total / (1024 ** 3), 3)

def safe_path(base, rel):
    base_real = os.path.realpath(base)
    target_real = os.path.realpath(os.path.join(base_real, rel))
    if not target_real.startswith(base_real): return None
    return target_real

# =============================================
# CONVERSOR ANSI -> HTML (CON FILTROS ANTI-SPAM)
# =============================================
def ansi_to_html(text):
    text = re.sub(r'tput: No value for \$TERM.*?\n', '', text)
    text = re.sub(r'tput: No value for \$TERM.*', '', text)
    text = re.sub(r'\x1b\]0;.*?(?:\x07|\x1b\\)', '', text)
    text = re.sub(r'\]0;Genisys.*?%', '', text)
    text = re.sub(r'\x1b\([A-Z]', '', text)

    text = html_mod.escape(text)
    
    color_map = {
        '0': '</span>', '1': '<span style="font-weight:bold">',
        '30': '<span style="color:#1f2937">', '31': '<span style="color:#ef4444">',
        '32': '<span style="color:#22c55e">', '33': '<span style="color:#facc15">',
        '34': '<span style="color:#3b82f6">', '35': '<span style="color:#a855f7">',
        '36': '<span style="color:#06b6d4">', '37': '<span style="color:#f3f4f6">',
        '90': '<span style="color:#9ca3af">', '91': '<span style="color:#fca5a5">',
        '92': '<span style="color:#86efac">', '93': '<span style="color:#fde047">',
        '94': '<span style="color:#93c5fd">', '95': '<span style="color:#d8b4fe">',
        '96': '<span style="color:#67e8f9">', '97': '<span style="color:#ffffff">'
    }
    
    parts = re.split(r'\x1b\[([0-9;]*)[mK]', text)
    res =[parts[0]]
    open_spans = 0
    
    for i in range(1, len(parts), 2):
        code_str = parts[i]
        text_part = parts[i+1] if i+1 < len(parts) else ""
        codes = code_str.split(';') if code_str else ['0']
        
        for c in codes:
            if c == '0' or c == '39':
                while open_spans > 0:
                    res.append('</span>')
                    open_spans -= 1
            elif c in color_map:
                res.append(color_map[c])
                if c != '0' and c != '39':
                    open_spans += 1
                    
        res.append(text_part)
        
    while open_spans > 0:
        res.append('</span>')
        open_spans -= 1
        
    return "".join(res)

def format_size(size):
    if size < 1024: return f'{size} B'
    elif size < 1024 ** 2: return f'{size / 1024:.1f} KB'
    elif size < 1024 ** 3: return f'{size / 1024 ** 2:.1f} MB'
    else: return f'{size / 1024 ** 3:.2f} GB'

# =============================================
# RUTAS DE LA API Y WEB
# =============================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stats')
def api_stats():
    proc = get_server_process()
    mem_used_gb = 0.0
    if proc:
        try: mem_used_gb = proc.memory_info().rss / (1024 ** 3)
        except: pass
            
    mem_pct = min(100.0, round((mem_used_gb / RAM_TOTAL_GB) * 100, 1))
    disk_used = get_server_disk()
    disk_pct = min(100, round((disk_used / DISK_TOTAL_GB) * 100, 1))

    with history_lock:
        sparklines = {k: list(v) for k, v in stats_history.items()}
        net_in = sparklines['net_in'][-1] if sparklines['net_in'] else 0
        net_out = sparklines['net_out'][-1] if sparklines['net_out'] else 0

    return jsonify({
        'cpu': round(_last_cpu_val, 1),
        'memory': {'used_gb': round(mem_used_gb, 2), 'total_gb': RAM_TOTAL_GB, 'percent': mem_pct},
        'disk': {'used_gb': disk_used, 'total_gb': DISK_TOTAL_GB, 'percent': disk_pct},
        'network': {'in_rate': round(net_in, 1), 'out_rate': round(net_out, 1)},
        'sparklines': sparklines,
        'server_running': (proc is not None)
    })

@app.route('/api/console')
def api_console():
    global _console_pos
    with _console_lock:
        try:
            with open(OUTPUT_LOG, 'r', errors='replace') as f:
                f.seek(_console_pos)
                new_content = f.read()
                _console_pos = f.tell()
            return jsonify({'html': ansi_to_html(new_content) if new_content else ''})
        except:
            return jsonify({'html': ''})

@app.route('/api/console/send', methods=['POST'])
def api_console_send():
    cmd = (request.json or {}).get('command', '').strip()
    if cmd:
        with open(COMMANDS_FILE, 'a') as f: f.write(cmd + '\n')
    return jsonify({'success': True})

@app.route('/api/console/clear')
def api_console_clear():
    global _console_pos
    with _console_lock: _console_pos = 0
    return jsonify({'success': True})

@app.route('/api/server/command', methods=['POST'])
def api_server_command():
    action = (request.json or {}).get('action', '')
    if action in ['stop', 'restart']:
        with open(COMMANDS_FILE, 'a') as f: f.write('stop\n')
    return jsonify({'success': True})

# =============================================
# API DE ARCHIVOS
# =============================================
@app.route('/api/files')
def api_files():
    rel = request.args.get('path', '')
    target = safe_path(SERVER_DIR, rel)
    
    if not target or not os.path.exists(target): 
        return jsonify({'error': 'No encontrado', 'real_path': SERVER_DIR}), 404
        
    items =[]
    try:
        for entry in sorted(os.scandir(target), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                st = entry.stat()
                items.append({
                    'name': entry.name, 'type': 'dir' if entry.is_dir() else 'file',
                    'size_str': format_size(st.st_size) if entry.is_file() else '--',
                    'modified': datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%y %H:%M'),
                    'path': (rel + '/' + entry.name).strip('/') if rel else entry.name,
                })
            except: continue
    except: pass
    return jsonify({'items': items, 'path': rel, 'real_path': target})

@app.route('/api/files/read')
def api_files_read():
    target = safe_path(SERVER_DIR, request.args.get('path', ''))
    if target and os.path.isfile(target):
        try:
            with open(target, 'r', errors='replace') as f:
                return jsonify({'content': f.read(500000), 'name': os.path.basename(target)})
        except Exception as e: return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Error reading'}), 400

@app.route('/api/files/write', methods=['POST'])
def api_files_write():
    data = request.json or {}; target = safe_path(SERVER_DIR, data.get('path', ''))
    if target:
        with open(target, 'w') as f: f.write(data.get('content', ''))
        return jsonify({'success': True})
    return jsonify({'error': 'Denegado'}), 403

@app.route('/api/files/upload', methods=['POST'])
def api_files_upload():
    target = safe_path(SERVER_DIR, request.form.get('path', ''))
    if target:
        os.makedirs(target, exist_ok=True)
        for f in request.files.getlist('files'):
            if f and f.filename: f.save(os.path.join(target, f.filename))
        return jsonify({'success': True})
    return jsonify({'error': 'Error'}), 403

@app.route('/api/files/delete_bulk', methods=['POST'])
def api_files_delete_bulk():
    paths = (request.json or {}).get('paths',[])
    for p in paths:
        target = safe_path(SERVER_DIR, p)
        if target:
            if os.path.isfile(target): os.remove(target)
            elif os.path.isdir(target): shutil.rmtree(target)
    return jsonify({'success': True})

@app.route('/api/files/extract', methods=['POST'])
def api_files_extract():
    target = safe_path(SERVER_DIR, (request.json or {}).get('path', ''))
    if target and target.endswith('.zip') and os.path.isfile(target):
        try:
            with zipfile.ZipFile(target, 'r') as zip_ref:
                zip_ref.extractall(os.path.dirname(target))
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Archivo invalido'}), 400

# =============================================
# HTML FRONTEND (INTERFAZ FINAL 100% COMPLETA)
# =============================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>VPS ETERNA - Panel</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap');
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --pt-bg: #0F172A; --pt-card: #1E293B; --pt-border: #334155; --pt-hover: #334155;
  --pt-text: #F8FAFC; --pt-muted: #94A3B8; --pt-input: #0B1120;
  --pt-blue: #3B82F6; --pt-green: #10B981; --pt-red: #EF4444; --pt-yellow: #F59E0B;
  --pt-cyan: #06B6D4;
}
html, body { height: 100dvh; font-family: 'Inter', sans-serif; background: var(--pt-bg); color: var(--pt-text); overflow: hidden; display: flex; flex-direction: column; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--pt-border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--pt-muted); }
.top-nav { background: var(--pt-card); border-bottom: 1px solid var(--pt-border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.server-title { display: flex; align-items: center; gap: 12px; }
.server-icon { width: 32px; height: 32px; background: var(--pt-blue); border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: bold; }
.server-name { font-size: 16px; font-weight: 700; }
.server-sub { font-size: 12px; color: var(--pt-muted); }
.sub-nav { background: var(--pt-card); padding: 0 24px; display: flex; gap: 24px; border-bottom: 1px solid var(--pt-border); flex-shrink: 0; }
.sub-nav a { padding: 12px 0; color: var(--pt-muted); font-size: 14px; font-weight: 500; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
.sub-nav a:hover { color: var(--pt-text); }
.sub-nav a.active { color: var(--pt-blue); border-bottom-color: var(--pt-blue); }
.tab-content { flex: 1; display: none; overflow: hidden; }
.tab-content.active { display: flex; }
.console-wrapper { flex: 1; display: flex; flex-direction: row; gap: 20px; padding: 20px; overflow-y: auto; align-items: stretch; }
.terminal-col { flex: 1; display: flex; flex-direction: column; background: #000; border: 1px solid var(--pt-border); border-radius: 8px; overflow: hidden; min-width: 0; }
.terminal-out { flex: 1; padding: 16px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 13px; line-height: 1.5; color: #E2E8F0; white-space: pre-wrap; word-wrap: break-word; }
.terminal-input-bar { display: flex; background: var(--pt-card); border-top: 1px solid var(--pt-border); padding: 12px; gap: 10px; align-items: center; flex-shrink: 0; }
.terminal-input-bar span { color: var(--pt-blue); font-family: monospace; font-weight: bold; }
.terminal-input-bar input { flex: 1; background: var(--pt-input); border: 1px solid var(--pt-border); color: #fff; padding: 8px 12px; border-radius: 4px; font-family: monospace; outline: none; }
.terminal-input-bar input:focus { border-color: var(--pt-blue); }
.stats-col { width: 300px; display: flex; flex-direction: column; gap: 16px; flex-shrink: 0; }
.btn-group { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.btn-action { flex: 1; padding: 10px; border: none; border-radius: 6px; font-weight: 600; font-size: 13px; color: #fff; cursor: pointer; }
.btn-action:hover { filter: brightness(1.1); }
.btn-start { background: var(--pt-blue); } .btn-restart { background: var(--pt-yellow); } .btn-stop { background: var(--pt-red); }
.stat-box { background: var(--pt-card); border: 1px solid var(--pt-border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.stat-top { display: flex; align-items: center; gap: 12px; }
.stat-icon { width: 36px; height: 36px; border-radius: 6px; display: flex; align-items: center; justify-content: center; }
.stat-texts { flex: 1; }
.stat-title { font-size: 11px; font-weight: 700; color: var(--pt-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { font-size: 15px; font-weight: 700; font-family: monospace; }
.ip-box { color: var(--pt-blue); background: rgba(59,130,246,0.1); padding: 4px 8px; border-radius: 4px; display: inline-block; cursor: pointer; margin-top: 4px; }
.spark { height: 40px; margin-top: 4px; width: 100%; display: block; }
.fm-wrapper { flex: 1; display: flex; flex-direction: column; padding: 20px; gap: 16px; overflow: hidden; }
.fm-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.fm-bread { font-size: 14px; font-weight: 500; }
.fm-bread a { color: var(--pt-blue); cursor: pointer; } .fm-bread a:hover { text-decoration: underline; }
.fm-actions-top { display: flex; gap: 8px; }
.btn { padding: 8px 14px; background: var(--pt-card); border: 1px solid var(--pt-border); color: var(--pt-text); border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: 0.2s; }
.btn:hover { background: var(--pt-hover); }
.btn-primary { background: var(--pt-blue); border-color: var(--pt-blue); }
.btn-primary:hover { background: #2563EB; }
.btn-danger { color: var(--pt-red); }
.fm-table-container { flex: 1; background: var(--pt-card); border: 1px solid var(--pt-border); border-radius: 8px; overflow-y: auto; }
.fm-row { display: grid; grid-template-columns: 40px 1fr 100px 140px 100px; padding: 12px 16px; border-bottom: 1px solid var(--pt-border); align-items: center; font-size: 14px; transition: 0.1s; }
.fm-row.head { background: var(--pt-bg); font-weight: 600; color: var(--pt-muted); font-size: 12px; text-transform: uppercase; position: sticky; top: 0; z-index: 2; }
.fm-row:not(.head):hover { background: var(--pt-hover); cursor: pointer; }
.fm-row input[type="checkbox"] { cursor: pointer; width: 16px; height: 16px; accent-color: var(--pt-blue); }
.fm-name { display: flex; align-items: center; gap: 12px; min-width: 0; }
.fm-name svg { color: var(--pt-muted); width: 20px; flex-shrink: 0; }
.fm-name span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fm-size { font-family: monospace; color: var(--pt-muted); text-align: right; }
.fm-date { color: var(--pt-muted); font-size: 13px; }
.fm-opts { display: flex; justify-content: flex-end; gap: 8px; }
.fm-opts svg { width: 16px; color: var(--pt-muted); cursor: pointer; }
.fm-opts svg:hover { color: var(--pt-text); }
.fm-opts svg.extract:hover { color: var(--pt-green); }
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 100; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
.modal-overlay.open { display: flex; }
.modal { background: var(--pt-card); width: 90%; max-width: 900px; height: 85vh; border: 1px solid var(--pt-border); border-radius: 8px; display: flex; flex-direction: column; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
.modal-header { padding: 16px 20px; border-bottom: 1px solid var(--pt-border); display: flex; justify-content: space-between; align-items: center; }
.modal-header h3 { font-size: 15px; font-weight: 600; }
.modal-body { flex: 1; padding: 16px; overflow: hidden; display: flex; }
.modal-body textarea { flex: 1; width: 100%; background: var(--pt-input); color: #E2E8F0; border: 1px solid var(--pt-border); border-radius: 4px; padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 13px; resize: none; outline: none; tab-size: 4; }
.modal-body textarea:focus { border-color: var(--pt-blue); }
.modal-footer { padding: 16px 20px; border-top: 1px solid var(--pt-border); display: flex; justify-content: flex-end; gap: 10px; }
.toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 200; display: flex; flex-direction: column; gap: 10px; }
.toast { background: var(--pt-card); border-left: 4px solid var(--pt-green); padding: 14px 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border-radius: 4px; font-size: 14px; font-weight: 500; animation: slideIn 0.3s; }
@keyframes slideIn { from{transform:translateX(100%);} to{transform:translateX(0);} }
@media(max-width: 900px) {
  .console-wrapper { flex-direction: column; }
  .stats-col { width: 100%; display: grid; grid-template-columns: 1fr 1fr; }
  .btn-group { grid-column: span 2; }
  .terminal-col { min-height: 50vh; }
  .fm-row { grid-template-columns: 30px 1fr 60px 40px; }
  .fm-date { display: none; }
}
@media(max-width: 600px) { .stats-col { grid-template-columns: 1fr; } .btn-group { grid-column: span 1; } }
</style>
</head>
<body>
<div class="top-nav">
  <div class="server-title">
    <div class="server-icon">V</div>
    <div>
      <div class="server-name">VPS ETERNA</div>
      <div class="server-sub">mcpe.qzz.io:4148</div>
    </div>
  </div>
</div>
<div class="sub-nav">
  <a class="active" id="nav-console" onclick="switchTab('console')">Consola</a>
  <a id="nav-files" onclick="switchTab('files')">Gestor de Archivos</a>
</div>
<div id="tab-console" class="tab-content active">
  <div class="console-wrapper">
    <div class="terminal-col">
      <div class="terminal-out" id="term-out"></div>
      <div class="terminal-input-bar">
        <span>~/$</span>
        <input type="text" id="cmd-input" placeholder="Escribe un comando..." autocomplete="off">
        <button class="btn" onclick="clearTerm()">Limpiar</button>
      </div>
    </div>
    <div class="stats-col">
      <div class="btn-group">
        <button class="btn-action btn-restart" onclick="sendCmd('restart')" title="Detiene y el script start.sh lo reiniciará.">Reiniciar</button>
        <button class="btn-action btn-stop" onclick="sendCmd('stop')" title="Detiene y el script start.sh lo reiniciará.">Detener</button>
      </div>
      <div class="stat-box">
        <div class="stat-top">
          <div class="stat-icon" style="background:rgba(59,130,246,0.1); color:var(--pt-blue)"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg></div>
          <div class="stat-texts">
            <div class="stat-title">DIRECCIÓN IP</div>
            <div class="stat-value ip-box" onclick="navigator.clipboard.writeText('mcpe.qzz.io:4148');toast('¡Copiado!')">mcpe.qzz.io:4148</div>
          </div>
        </div>
      </div>
      <div class="stat-box">
        <div class="stat-top">
          <div class="stat-icon" style="background:rgba(16,185,129,0.1); color:var(--pt-green)"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/></svg></div>
          <div class="stat-texts"><div class="stat-title">USO DE CPU</div><div class="stat-value" id="s-cpu">0%</div></div>
        </div>
        <svg class="spark" id="sp-cpu" preserveAspectRatio="none"></svg>
      </div>
      <div class="stat-box">
        <div class="stat-top">
          <div class="stat-icon" style="background:rgba(59,130,246,0.1); color:var(--pt-blue)"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="10" rx="2"/></svg></div>
          <div class="stat-texts"><div class="stat-title">MEMORIA</div><div class="stat-value" id="s-mem">0.00 / 14 GB</div></div>
        </div>
        <svg class="spark" id="sp-mem" preserveAspectRatio="none"></svg>
      </div>
      <div class="stat-box">
        <div class="stat-top">
          <div class="stat-icon" style="background:rgba(245,158,11,0.1); color:var(--pt-yellow)"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20V10M18 20V4M6 20v-4"/></svg></div>
          <div class="stat-texts"><div class="stat-title">RED (IN/OUT)</div><div class="stat-value" id="s-net" style="font-size:12px;">0 B/s / 0 B/s</div></div>
        </div>
        <svg class="spark" id="sp-net" preserveAspectRatio="none"></svg>
      </div>
    </div>
  </div>
</div>
<div id="tab-files" class="tab-content">
  <div class="fm-wrapper">
    <div class="fm-toolbar">
      <div>
        <div class="fm-bread" id="fm-bread"></div>
        <div style="font-size:10px; color:var(--pt-muted); margin-top: 4px;">Ruta interna detectada: <span id="real-path-debug">Buscando...</span></div>
      </div>
      <div class="fm-actions-top">
        <button class="btn btn-danger" onclick="deleteSelected()" style="display:none" id="btn-del-mass">Eliminar Sel.</button>
        <button class="btn btn-primary" onclick="document.getElementById('upload-input').click()">Subir Archivo</button>
        <button class="btn" onclick="loadFiles(cPath)">Recargar</button>
        <input type="file" id="upload-input" multiple style="display:none" onchange="uploadFiles(event)">
      </div>
    </div>
    <div class="fm-table-container">
      <div class="fm-row head">
        <div><input type="checkbox" id="chk-all" onchange="toggleAll()"></div>
        <div>Nombre de Archivo</div>
        <div style="text-align:right">Tamaño</div>
        <div>Fecha</div>
        <div></div>
      </div>
      <div id="fm-list">
        <div style="padding:40px;text-align:center;color:var(--pt-muted)">Cargando archivos...</div>
      </div>
    </div>
  </div>
</div>
<div class="modal-overlay" id="editor-modal">
  <div class="modal">
    <div class="modal-header">
      <h3 id="ed-title">Editando archivo</h3>
    </div>
    <div class="modal-body"><textarea id="ed-text" spellcheck="false"></textarea></div>
    <div class="modal-footer">
      <button class="btn" onclick="document.getElementById('editor-modal').classList.remove('open')">Cancelar</button>
      <button class="btn btn-primary" onclick="saveFile()">Guardar Archivo</button>
    </div>
  </div>
</div>
<div class="toast-container" id="toast-stack"></div>
<script>
let cPath = '';
let editPath = '';
let termAuto = true;

function switchTab(t) {
  document.querySelectorAll('.sub-nav a').forEach(a=>a.classList.remove('active'));
  document.getElementById('nav-'+t).classList.add('active');
  document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
  document.getElementById('tab-'+t).classList.add('active');
  if(t==='files') loadFiles(cPath);
}

function drawSpark(id, data, hexStr) {
  const svg = document.getElementById(id);
  if(!svg || !data || !data.length) return;
  let max = Math.max(...data, 0.1); 
  let pts = '';
  for(let i=0; i<data.length; i++) {
    let x = i * (100 / Math.max(1, data.length - 1));
    let y = 40 - (data[i] / max) * 40;
    pts += (i===0?'M':'L') + x.toFixed(2) + ',' + y.toFixed(2);
  }
  svg.innerHTML = `
    <defs><linearGradient id="g-${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${hexStr}" stop-opacity="0.3"/><stop offset="100%" stop-color="${hexStr}" stop-opacity="0"/></linearGradient></defs>
    <path d="${pts} L100,40 L0,40 Z" fill="url(#g-${id})"/>
    <path d="${pts}" fill="none" stroke="${hexStr}" stroke-width="2" stroke-linecap="round"/>
  `;
}

function fmt(kbps) {
  if(kbps<1) return (kbps*1024).toFixed(0)+' B/s';
  if(kbps<1024) return kbps.toFixed(1)+' KB/s';
  return (kbps/1024).toFixed(1)+' MB/s';
}

function toast(m) {
  const d = document.createElement('div'); d.className='toast'; d.textContent=m;
  document.getElementById('toast-stack').appendChild(d);
  setTimeout(()=>d.remove(), 3000);
}

async function fetchStats() {
  try {
    const r = await fetch('/api/stats'); const d = await r.json();
    document.getElementById('s-cpu').textContent = d.cpu + '%';
    document.getElementById('s-mem').textContent = d.memory.used_gb + ' / 14 GB';
    document.getElementById('s-net').innerHTML = `<span style="color:var(--pt-cyan)">IN: ${fmt(d.network.in_rate)}</span><br><span style="color:var(--pt-blue)">OUT: ${fmt(d.network.out_rate)}</span>`;
    
    if(d.sparklines) {
      drawSpark('sp-cpu', d.sparklines.cpu, '#10B981'); 
      drawSpark('sp-mem', d.sparklines.mem, '#3B82F6'); 
      let netCombined = d.sparklines.net_in.map((v, i) => v + d.sparklines.net_out[i]);
      drawSpark('sp-net', netCombined, '#F59E0B'); 
    }
  } catch(e){}
}

async function fetchTerm() {
  try {
    const r = await fetch('/api/console'); const d = await r.json();
    if(d.html) {
      const out = document.getElementById('term-out');
      out.innerHTML += d.html;
      if(termAuto) out.scrollTop = out.scrollHeight;
    }
  } catch(e){}
}

function sendCmd(act) { 
    toast('Enviando comando...');
    fetch('/api/server/command', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:act})}); 
}

function clearTerm() { fetch('/api/console/clear'); document.getElementById('term-out').innerHTML=''; }

document.getElementById('cmd-input').addEventListener('keydown', e => {
  if(e.key==='Enter') {
    const cmd = e.target.value.trim();
    if(cmd) {
      document.getElementById('term-out').innerHTML += `<span style="color:var(--pt-cyan);font-weight:bold;">~/$ ${cmd}</span>\n`;
      fetch('/api/console/send', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:cmd})});
      e.target.value = '';
    }
  }
});
document.getElementById('term-out').addEventListener('scroll', function() { termAuto = (this.scrollTop + this.clientHeight >= this.scrollHeight - 50); });

const icons = {
  dir: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  zip: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/></svg>'
};

async function loadFiles(p) {
  cPath = p; document.getElementById('chk-all').checked = false; checkMassDel();
  let bc = '<a onclick="loadFiles(\'\')">/home/container</a>';
  if(p) { let cum=''; p.split('/').forEach(x=>{ cum+=(cum?'/':'')+x; bc+=` / <a onclick="loadFiles('${cum}')">${x}</a>`; }); }
  document.getElementById('fm-bread').innerHTML = bc;
  
  try {
    const r = await fetch('/api/files?path='+encodeURIComponent(p), {cache: 'no-store'}); 
    const d = await r.json();
    
    document.getElementById('real-path-debug').textContent = d.real_path || "Ruta desconocida";

    if(d.error) throw new Error("Carpeta no encontrada");
    if(d.items.length === 0) {
        document.getElementById('fm-list').innerHTML = '<div style="padding:40px;text-align:center;color:var(--pt-muted)">Esta carpeta esta vacia. Sube tus archivos.</div>';
        return;
    }

    document.getElementById('fm-list').innerHTML = d.items.map(i => {
      const isDir = i.type==='dir'; const isZip = i.name.endsWith('.zip');
      const icon = isDir ? icons.dir : (isZip ? icons.zip : icons.file);
      const safePath = i.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'"); 
      const acts = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" onclick="event.stopPropagation();delFile('${safePath}')" title="Eliminar"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>` + 
        (isZip ? `<svg class="extract" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" onclick="event.stopPropagation();extractFile('${safePath}')" title="Descomprimir"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>` : '');
      
      return `<div class="fm-row" onclick="${isDir ? `loadFiles('${safePath}')` : `openEd('${safePath}')`}">
        <div onclick="event.stopPropagation()"><input type="checkbox" class="f-chk" value="${i.path}" onchange="checkMassDel()"></div>
        <div class="fm-name">${icon}<span>${i.name}</span></div>
        <div class="fm-size">${i.size_str}</div>
        <div class="fm-date">${i.modified}</div>
        <div class="fm-opts" onclick="event.stopPropagation()">${acts}</div>
      </div>`;
    }).join('');
  } catch(e) { 
      document.getElementById('fm-list').innerHTML = '<div style="padding:20px; color:var(--pt-red);">La carpeta no existe o no se encontro en el sistema.</div>'; 
  }
}

function toggleAll() {
  const st = document.getElementById('chk-all').checked;
  document.querySelectorAll('.f-chk').forEach(c=>c.checked=st);
  checkMassDel();
}
function checkMassDel() {
  const any = Array.from(document.querySelectorAll('.f-chk')).some(c=>c.checked);
  document.getElementById('btn-del-mass').style.display = any ? 'inline-block' : 'none';
}

async function delFile(p) {
  if(!confirm('¿Eliminar archivo seleccionado?')) return;
  await fetch('/api/files/delete_bulk', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({paths:[p]})});
  toast('Eliminado'); loadFiles(cPath);
}
async function deleteSelected() {
  const paths = Array.from(document.querySelectorAll('.f-chk:checked')).map(c=>c.value);
  if(!paths.length || !confirm(`¿Eliminar ${paths.length} elementos permanentemente?`)) return;
  await fetch('/api/files/delete_bulk', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({paths})});
  toast('Archivos eliminados'); loadFiles(cPath);
}
async function uploadFiles(e) {
  if(!e.target.files.length) return;
  const fd = new FormData(); fd.append('path', cPath);
  for(let f of e.target.files) fd.append('files', f);
  toast('Subiendo archivos...');
  await fetch('/api/files/upload', {method:'POST', body:fd});
  toast('Subida exitosa'); loadFiles(cPath); e.target.value='';
}
async function extractFile(p) {
  toast('Descomprimiendo...');
  const r = await fetch('/api/files/extract', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:p})});
  const d = await r.json();
  if(d.success) { toast('Extraido con exito'); loadFiles(cPath); } else toast('Error extrayendo');
}

async function openEd(p) {
  const r = await fetch('/api/files/read?path='+encodeURIComponent(p)); const d = await r.json();
  if(d.error) return toast('Este archivo no puede ser editado');
  editPath = p; document.getElementById('ed-title').textContent = d.name; document.getElementById('ed-text').value = d.content;
  document.getElementById('editor-modal').classList.add('open');
}
async function saveFile() {
  await fetch('/api/files/write', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:editPath, content:document.getElementById('ed-text').value})});
  toast('Archivo guardado'); document.getElementById('editor-modal').classList.remove('open');
}

setInterval(fetchStats, 2000);
setInterval(fetchTerm, 1500);
fetchStats();
</script>
</body>
</html>
"""

# =============================================
# HILO SECUNDARIO (SOLO STATS)
# =============================================
def background_loop():
    while True:
        try: 
            record_stats()
        except: 
            pass
        time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=background_loop, daemon=True).start()
    print("=" * 60)
    print("  VPS ETERNA PANEL v5.0 (FINAL BUILD)")
    print("  http://0.0.0.0:8080")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=False)
