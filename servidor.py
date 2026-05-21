#!/usr/bin/env python3
"""
OMAIRA v4 — Servidor todo-en-uno
Ejecutar: python servidor.py
Inicia automáticamente:
  - Servidor HTTP + proxy CORS en :8080
  - Backend FastAPI (uvicorn) en :8000 (si existe)
  - Abre el navegador automáticamente
"""
import http.server, urllib.request, urllib.error
import os, sys, subprocess, threading, webbrowser, time, signal
from urllib.parse import urlparse, unquote
import atexit, platform

# ── Asegurar que hijos mueren con el padre (Windows + Unix) ─
def _setup_process_group():
    """En Windows: Job Object garantiza que uvicorn muere si servidor.py muere."""
    if platform.system() == 'Windows':
        try:
            import ctypes, ctypes.wintypes
            kernel32 = ctypes.windll.kernel32
            job = kernel32.CreateJobObjectW(None, None)
            info = ctypes.c_bool(True)
            kernel32.SetInformationJobObject(
                job, 9,  # JobObjectExtendedLimitInformation
                ctypes.byref(info), ctypes.sizeof(info))
            kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
        except Exception:
            pass  # Si falla, continuar normalmente

_setup_process_group()

PORT_FRONTEND = 8080
PORT_BACKEND  = 8000

# ── Buscar el HTML — toma el más reciente automáticamente ──
def encontrar_frontend():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    carpetas_buscar = [
        os.path.join(script_dir, 'frontend'),
        script_dir,
        os.path.join(script_dir, '..'),
        os.path.expanduser('~/Desktop'),
        os.path.expanduser('~/OneDrive/Desktop'),
        os.path.expanduser('~/OneDrive/Escritorio'),
        os.path.expanduser('~/Downloads'),
        os.path.expanduser('~/Descargas'),
    ]
    # Primero: buscar index.html en frontend/ (instalación correcta)
    ruta_index = os.path.join(script_dir, 'frontend', 'index.html')
    if os.path.exists(ruta_index):
        return os.path.join(script_dir, 'frontend'), 'index.html'

    # Segundo: buscar el HTML de OMAIRA más reciente en todas las carpetas
    mejor = None
    mejor_ts = 0
    for carpeta in carpetas_buscar:
        carpeta = os.path.normpath(carpeta)
        if not os.path.isdir(carpeta):
            continue
        try:
            for f in os.listdir(carpeta):
                if (f.startswith('OMAIRA') or f.startswith('SIRGA')) and f.endswith('.html'):
                    ruta = os.path.join(carpeta, f)
                    ts = os.path.getmtime(ruta)
                    if ts > mejor_ts:
                        mejor_ts = ts
                        mejor = (carpeta, f)
        except Exception:
            pass

    if mejor:
        print(f'  ℹ️  Tip: para actualizaciones futuras, renombra el HTML a')
        print(f'     index.html en la carpeta frontend/ — así siempre carga el nuevo.')
        return mejor

    # Fallback
    return script_dir, 'index.html'

# ── Buscar el backend ───────────────────────────────────────
def encontrar_backend():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidatos = [
        os.path.join(script_dir, 'backend'),
        os.path.join(script_dir, '..', 'backend'),
    ]
    for carpeta in candidatos:
        main_py = os.path.join(carpeta, 'app', 'main.py')
        if os.path.exists(main_py):
            return carpeta
    return None

FRONTEND_DIR, HTML_PRINCIPAL = encontrar_frontend()
BACKEND_DIR  = encontrar_backend()

# ── Proxies CORS ────────────────────────────────────────────
PROXY_MAP = {
    '/proxy/dhime':   'http://dhime.ideam.gov.co/ords/ws_fenes/',
    '/proxy/ideam':   'http://dhime.ideam.gov.co/ords/ws_fenes/',
    '/proxy/siata':   'http://siata.gov.co/descarga_siata_2/index.php',
    '/proxy/epm':     'https://datos.epm.com.co/api',
    '/proxy/cornare': 'https://sia.cornare.gov.co/api',
    '/proxy/sama':    'https://dagran.antioquia.gov.co/api/sama',
    '/proxy/noaa':    'https://www.cpc.ncep.noaa.gov/data/indices/',
    '/proxy/windy':   'https://api.windy.com/api/point-forecast/v2',
    '/proxy/arcgis_dagran': 'https://geodatos-gobantioquia.opendata.arcgis.com/api/search/v1/items',
}

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'es-CO,es;q=0.9,en;q=0.7',
    'Cache-Control': 'no-cache',
}

class OMAIRAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def log_message(self, fmt, *args):
        msg = fmt % args
        status = args[1] if len(args) > 1 else '?'
        if str(status).startswith('2'):
            print(f'  ✅ {self.path[:60]:60} {status}')
        elif str(status) in ('304',):
            pass  # ignorar not-modified
        elif str(status).startswith('4') or str(status).startswith('5'):
            print(f'  ❌ {self.path[:60]:60} {status}')

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
            'Content-Type, Authorization, x-api-key, anthropic-version, '
            'anthropic-dangerous-direct-browser-access')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Proxy para APIs institucionales + NOAA + ArcGIS
        for prefix, base_url in PROXY_MAP.items():
            if path.startswith(prefix):
                suffix = path[len(prefix):]
                target = base_url + suffix
                if parsed.query:
                    # Para arcgis_dagran pasar los query params directo
                    if 'arcgis_dagran' in prefix:
                        target = base_url + ('?' + parsed.query if parsed.query else '')
                    else:
                        target += '?' + parsed.query
                self._proxy(target)
                return

        # Raíz → HTML principal
        if path == '/' or path == '':
            self.path = '/' + HTML_PRINCIPAL

        super().do_GET()


    def _proxy_windy(self):
        """Proxy especial para Windy Point Forecast API.
        Hace la llamada directamente desde Python, sin restricciones CORS ni de host.
        """
        import json as _json
        try:
            # Leer body del request
            length = self.headers.get('Content-Length')
            if length and int(length) > 0:
                body_bytes = self.rfile.read(int(length))
            else:
                body_bytes = b''

            # Hacer la llamada a Windy desde Python (sin Origin ni Referer)
            req = urllib.request.Request(
                'https://api.windy.com/api/point-forecast/v2',
                data=body_bytes,
                headers={'Content-Type': 'application/json',
                         'Accept': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                print(f'  /proxy/windy                                        200')
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
            print(f'  /proxy/windy                                        {e.code} {err_body.decode()[:50]}')
        except Exception as e:
            err = str(e).encode()
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(err)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Handler especial para Windy Point Forecast
        if path == '/proxy/windy':
            self._proxy_windy()
            return

        for prefix, base_url in PROXY_MAP.items():
            if path.startswith(prefix):
                # Leer body completo — soporta Content-Length y chunked transfer
                length = self.headers.get('Content-Length')
                if length:
                    body = self.rfile.read(int(length))
                else:
                    # Sin Content-Length: leer hasta que no haya más datos
                    body = b''
                    while True:
                        chunk = self.rfile.read(4096)
                        if not chunk:
                            break
                        body += chunk
                target = base_url + path[len(prefix):]
                self._proxy(target, method='POST', body=body)
                return
        self.send_response(404)
        self.end_headers()

    def _proxy(self, target_url, method='GET', body=None):
        try:
            headers = dict(BROWSER_HEADERS)
            for h in ['Authorization', 'x-api-key', 'Content-Type',
                      'anthropic-version', 'anthropic-dangerous-direct-browser-access']:
                v = self.headers.get(h)
                if v:
                    headers[h] = v
            # Para Windy: NO enviar Origin/Referer (causa "Host not in allowlist")
            # Para otras APIs: usar el dominio destino
            parsed_t = urlparse(target_url)
            if 'windy.com' not in target_url:
                headers['Referer'] = f'{parsed_t.scheme}://{parsed_t.netloc}/'
                headers['Origin']  = f'{parsed_t.scheme}://{parsed_t.netloc}'

            req = urllib.request.Request(
                target_url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=12) as resp:
                content = resp.read()
                self.send_response(resp.status)
                ct = resp.headers.get('Content-Type', 'application/json')
                self.send_header('Content-Type', ct)
                self.end_headers()
                self.wfile.write(content)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(f'{{"error":"{e.reason}","code":{e.code}}}'.encode())
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(f'{{"error":"{str(e)}"}}'.encode())

# ── Iniciar backend uvicorn ─────────────────────────────────
backend_proc = None

def iniciar_backend():
    global backend_proc
    if not BACKEND_DIR:
        print('  ⚠️  Backend no encontrado — solo frontend activo')
        return
    print(f'  🚀 Iniciando backend FastAPI en :{PORT_BACKEND}...')
    try:
        # Flags para Windows: el proceso hijo queda en el mismo Job Object
        extra_flags = {}
        if platform.system() == 'Windows':
            extra_flags['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        backend_proc = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn',
             'app.main:app',
             '--host', '0.0.0.0',
             '--port', str(PORT_BACKEND),
             '--reload'],
            cwd=BACKEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **extra_flags
        )
        # Guardar PID para limpieza
        with open(os.path.join(BACKEND_DIR, '.backend.pid'), 'w') as pf:
            pf.write(str(backend_proc.pid))
        # Leer las primeras líneas para confirmar que arrancó
        for _ in range(20):
            line = backend_proc.stdout.readline().decode('utf-8','replace').strip()
            if 'Application startup complete' in line or 'running on' in line.lower():
                print(f'  ✅ Backend activo en http://localhost:{PORT_BACKEND}')
                print(f'  📖 Documentación API: http://localhost:{PORT_BACKEND}/docs')
                break
            elif line:
                print(f'     {line}')
    except FileNotFoundError:
        print('  ⚠️  uvicorn no encontrado. Instalar con: pip install uvicorn fastapi')
    except Exception as e:
        print(f'  ❌ Error iniciando backend: {e}')

def detener_backend():
    global backend_proc
    # Matar el proceso principal
    if backend_proc:
        try:
            backend_proc.terminate()
            try: backend_proc.wait(timeout=2)
            except: backend_proc.kill()
        except Exception: pass
        backend_proc = None
    # En Windows: matar también uvicorn por puerto por si acaso
    if platform.system() == 'Windows':
        try:
            # Buscar PIDs en el puerto del backend y matarlos
            r = subprocess.run(
                f'netstat -aon', shell=True,
                capture_output=True, text=True, timeout=3)
            for line in r.stdout.splitlines():
                if f':{PORT_BACKEND} ' in line and 'LISTENING' in line:
                    parts = line.strip().split()
                    pid = parts[-1] if parts else ''
                    if pid.isdigit() and int(pid) != os.getpid():
                        subprocess.run(f'taskkill /F /PID {pid}',
                            shell=True, capture_output=True, timeout=2)
        except Exception: pass
    else:
        try:
            subprocess.run(f'fuser -k {PORT_BACKEND}/tcp', shell=True,
                         capture_output=True, timeout=3)
        except Exception: pass

# ── Abrir navegador ─────────────────────────────────────────
def abrir_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{PORT_FRONTEND}')

# ── Señal de cierre ─────────────────────────────────────────
def manejar_cierre(sig, frame):
    print('\n\n  Deteniendo servicios...')
    detener_backend()
    print('  ✅ Servidor detenido.')
    sys.exit(0)

signal.signal(signal.SIGINT, manejar_cierre)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, manejar_cierre)

# Limpiar también si el proceso termina de forma inesperada
atexit.register(detener_backend)

# ── Main ────────────────────────────────────────────────────
def _liberar_puertos():
    """Matar procesos que ocupen los puertos antes de iniciar."""
    for port in [PORT_FRONTEND, PORT_BACKEND]:
        if platform.system() == 'Windows':
            try:
                result = subprocess.run(
                    f'netstat -aon | findstr ":{port} "',
                    shell=True, capture_output=True, text=True, timeout=3)
                for line in result.stdout.splitlines():
                    parts = line.strip().split()
                    if parts and 'LISTENING' in line:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != os.getpid():
                            subprocess.run(f'taskkill /F /PID {pid}',
                                         shell=True, capture_output=True, timeout=2)
            except Exception: pass
        else:
            try:
                subprocess.run(f'fuser -k {port}/tcp',
                             shell=True, capture_output=True, timeout=2)
            except Exception: pass

def main():
    _liberar_puertos()  # Limpiar puertos antes de iniciar
    print()
    print('  ╔════════════════════════════════════════════════════╗')
    print('  ║   OMAIRA v4 — Sistema todo-en-uno                  ║')
    print('  ╚════════════════════════════════════════════════════╝')
    print()
    print(f'  HTML encontrado: {os.path.join(FRONTEND_DIR, HTML_PRINCIPAL)}')
    if BACKEND_DIR:
        print(f'  Backend encontrado: {BACKEND_DIR}')
    print()

    # Iniciar backend en hilo separado
    if BACKEND_DIR:
        t_backend = threading.Thread(target=iniciar_backend, daemon=True)
        t_backend.start()
        time.sleep(0.5)  # pequeña pausa para que el backend empiece

    # Abrir navegador después de 1.5s
    threading.Thread(target=abrir_browser, daemon=True).start()

    print(f'  🌐 Dashboard:  http://localhost:{PORT_FRONTEND}')
    if BACKEND_DIR:
        print(f'  ⚙️  Backend API: http://localhost:{PORT_BACKEND}')
        print(f'  📖 API Docs:    http://localhost:{PORT_BACKEND}/docs')
    print()
    print('  Proxies CORS activos:')
    for p in PROXY_MAP:
        print(f'    :{PORT_FRONTEND}{p}/*')
    print()
    print('  Presiona Ctrl+C para detener todo')
    print()

    try:
        with http.server.HTTPServer(('', PORT_FRONTEND), OMAIRAHandler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        if 'already in use' in str(e).lower() or '10048' in str(e):
            print(f'\n  ⚠️  Puerto {PORT_FRONTEND} ya en uso.')
            print(f'  Intenta abrir directamente: http://localhost:{PORT_FRONTEND}')
        else:
            raise

if __name__ == '__main__':
    main()
