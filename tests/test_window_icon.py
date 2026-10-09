"""Window identity, safe fallback and optional Windows smoke with synthetic HTTP."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import window_icon as icon


class WindowIconTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.cleanup_fixture)
        self.root=Path(self.temp.name);self.launcher=self.root/'launcher.exe'
        self.launcher.write_bytes(icon.MODE.encode('utf-16le'))
        self.assets=self.root/'assets';self.assets.mkdir();(self.assets/'stubbs.ico').write_bytes(b'TEST icon')
        icon._launches.clear()
        self.address='http://127.0.0.1:18743/#key=TEST-PRIVATE-KEY'
        self.project='a'*24
    def cleanup_fixture(self):
        try:self.temp.cleanup()
        except PermissionError:
            if not getattr(self,'native_diagnostics',None):raise
            # Keep locked synthetic material; never find/kill a browser by name.
            self.native_diagnostics['fixtureCleanup']='locked synthetic profile preserved'
    def test_launch_returns_immediately_without_waiting_for_http_or_window(self):
        calls=[]
        self.assertTrue(icon.launch('msedge.exe',self.address,self.launcher,self.project,self.root,calls.append))
        self.assertEqual(len(calls),1)
        parsed=urlsplit(calls[0][3]);token=parse_qs(parsed.query)['window-icon'][0]
        self.assertEqual(parsed.fragment,'key=TEST-PRIVATE-KEY')
        self.assertEqual(calls[0][4],token)
        self.assertEqual(icon.status(token),'pending')
    def test_existing_service_can_register_in_its_own_process_and_acknowledge(self):
        token='b'*32
        self.assertTrue(icon.register(token,self.root))
        self.assertTrue(icon.acknowledge(token,'ready'))
        self.assertEqual(icon.status(token),'ready')
        self.assertFalse(icon.register(token,self.root))
    def test_old_launcher_and_spawn_failure_preserve_fallback_and_no_secrets(self):
        self.launcher.write_bytes(b'old launcher')
        self.assertFalse(icon.launch('msedge.exe',self.address,self.launcher,self.project,self.root,lambda _:self.fail('Old launcher executed')))
        self.launcher.write_bytes(icon.MODE.encode('utf-16le'))
        def fail(_):raise OSError('TEST-PRIVATE-KEY http://private.example')
        self.assertFalse(icon.launch('msedge.exe',self.address,self.launcher,self.project,self.root,fail))
        log=(self.root/'app-window.log').read_text()
        self.assertNotIn('PRIVATE',log);self.assertNotIn('http',log)
        self.assertFalse(icon._launches)
    def test_only_registered_local_openings_receive_a_marker(self):
        text='<title>Stubbs Jobs</title><link rel="icon" href="/assets/stubbs.ico"></head>'
        foreign='c'*32
        self.assertNotIn(foreign,icon.html(text,self.assets,foreign))
        self.assertTrue(icon.register(foreign,self.root))
        marked=icon.html(text,self.assets,foreign)
        self.assertIn('Stubbs Jobs · '+foreign,marked)
        self.assertIn('/window-icon.js?token='+foreign,marked)
        self.assertIsNone(icon.script('../../bad'))
        self.assertFalse(icon.acknowledge('d'*32,'ready'))
    def test_ephemeral_state_has_capacity_and_time_bounds(self):
        with patch.object(icon.time,'monotonic',return_value=10):
            for number in range(icon.MAX_PENDING):self.assertTrue(icon.register(format(number,'032x'),self.root))
            self.assertFalse(icon.register('e'*32,self.root))
        with patch.object(icon.time,'monotonic',return_value=10+icon.LIFETIME+1):
            self.assertEqual(icon.status(format(0,'032x')),'expired')
            self.assertTrue(icon.register('e'*32,self.root))
    def test_favicon_identity_changes_with_actual_icon_bytes(self):
        text='<title>Stubbs Jobs</title><link rel="icon" href="/assets/stubbs.ico"></head>'
        before=icon.html(text,self.assets)
        (self.assets/'stubbs.ico').write_bytes(b'TEST replacement')
        after=icon.html(text,self.assets)
        self.assertNotEqual(before,after)
        self.assertIn(hashlib.sha256(b'TEST replacement').hexdigest()[:20],after)
    def test_remote_or_unidentified_url_never_starts_a_helper(self):
        for address in ('https://example.org/#key=test','http://127.0.0.1:18743/','http://attacker@127.0.0.1:18743/#key=test'):
            self.assertFalse(icon.launch('msedge.exe',address,self.launcher,self.project,self.root,lambda _:self.fail('Unsafe helper')))

    @unittest.skipUnless(os.name=='nt','Windows compiler regression')
    def test_native_maintenance_retries_busy_window_and_stops_after_ownership_loss(self):
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        self.assertTrue(compiler.is_file(),'Se necesita el compilador del lanzador')
        source=self.root/'maintenance.cs';executable=self.root/'maintenance.exe'
        source.write_text('''using System;
class MaintenanceCheck {
    static int Main() {
        bool owned=true;int calls=0;
        Func<bool> owns=()=>owned;
        Func<bool> ensure=()=>{calls++;if(calls==1)throw new InvalidOperationException();return true;};
        if(!NativeWindowIcon.MaintainWindow(owns,ensure)||calls!=1)return 1;
        if(!NativeWindowIcon.MaintainWindow(owns,ensure)||calls!=2)return 2;
        if(!NativeWindowIcon.MaintainWindow(owns,()=>false))return 3;
        if(NativeWindowIcon.MaintainWindow(owns,()=>{owned=false;throw new InvalidOperationException();}))return 4;
        if(NativeWindowIcon.MaintainWindow(owns,()=>{throw new Exception("Foreign window touched");}))return 5;
        return 0;
    }
}
''',encoding='utf-8')
        result=subprocess.run([str(compiler),'/nologo','/target:exe','/main:MaintenanceCheck',
                               '/reference:System.Windows.Forms.dll','/out:'+str(executable),
                               str(PROJECT/'tools/launcher.cs'),str(source)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(subprocess.run([str(executable)],timeout=10).returncode,0)

    @unittest.skipUnless(os.name=='nt' and os.environ.get('STUBBS_JOBS_NATIVE_ICON_TEST')=='1','Explicit isolated Windows/Edge smoke only')
    def test_native_edge_window_only_with_synthetic_http_and_own_close(self):
        edge=shutil.which('msedge.exe')
        for variable in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA'):
            path=Path(os.environ.get(variable,''))/'Microsoft/Edge/Application/msedge.exe'
            if path.is_file():edge=str(path);break
        if not edge:self.skipTest('Edge is unavailable')
        root=self.root;assets=root/'app/assets';assets.mkdir(parents=True)
        shutil.copy2(PROJECT/'app/assets/stubbs.ico',assets/'stubbs.ico')
        launcher=root/'Abrir Stubbs Jobs.exe';shutil.copy2(PROJECT/'Abrir Stubbs Jobs.exe',launcher)
        self.assertIn(icon.MODE.encode('utf-16le'),launcher.read_bytes(),'Rebuild the launcher before native smoke; never execute a legacy launcher')
        (root/'.synthetic-ui-fixture').write_text('synthetic-only')
        key='TEST-WINDOW-ICON-'+secrets.token_hex(12);token=secrets.token_hex(16)
        calls={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,body,kind='application/json'):
                if not isinstance(body,bytes):body=json.dumps(body).encode()
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_GET(self):
                path=urlsplit(self.path).path
                calls[path]=calls.get(path,0)+1
                if path=='/':
                    text='<html><head><title>Stubbs Jobs</title><link rel="icon" href="/assets/stubbs.ico"></head><body>FICTIONAL WINDOWS ICON TEST ONLY</body></html>'
                    rendered=icon.html(text,assets,token)
                    calls['servedMarker']=('Stubbs Jobs · '+token) in rendered
                    return self.send(rendered.encode(),'text/html; charset=utf-8')
                if path=='/window-icon.js':return self.send(icon.script(token).encode(),'application/javascript')
                if path=='/window-icon-status':return self.send({'status':icon.status(token)})
                return self.send((assets/'stubbs.ico').read_bytes(),'image/x-icon')
            def do_POST(self):
                calls[self.path]=calls.get(self.path,0)+1
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if body.get('key')!=key:self.send_error(401);return
                if self.path.endswith('/start'):ok=icon.register(body['token'],root)
                else:ok=icon.acknowledge(body['token'],body['status'])
                self.send({'ok':ok})
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        address='http://127.0.0.1:'+str(server.server_port)+'/?window-icon='+token+'#key='+key
        result=subprocess.run([str(launcher),'StubbsJobs.WindowIcon.Smoke.v1',edge,address,token,'StubbsJobs.Desktop.'+self.project],timeout=50,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0)
        self.native_evidence={'diagnostics':(root/'app-window.log').read_text() if (root/'app-window.log').is_file() else '',
                              'routes':calls,'markerState':icon.status(token),
                              'matchingTokenWindows':json.loads((root/'window-icon-find.json').read_text()) if (root/'window-icon-find.json').is_file() else None,
                              'browser':json.loads((root/'window-icon-browser.json').read_text()) if (root/'window-icon-browser.json').is_file() else None}
        debug=(root/'synthetic-edge-debug.log').read_text(errors='replace') if (root/'synthetic-edge-debug.log').is_file() else ''
        self.native_evidence['browserErrorKinds']={kind:debug.lower().count(kind) for kind in ('sandbox','access denied','renderer','gpu','fatal','error:')}
        self.native_diagnostics=self.native_evidence.copy()
        self.assertTrue((root/'window-icon-smoke.json').is_file(),str(self.native_evidence))
        evidence=json.loads((root/'window-icon-smoke.json').read_text())
        self.native_evidence=evidence
        self.assertEqual(evidence,{'nativeIconVerified':True,'taskbarPropertiesVerified':True,'closedOwnWindow':True,'restoredAfterOverwrite':True})


if __name__=='__main__':unittest.main()
