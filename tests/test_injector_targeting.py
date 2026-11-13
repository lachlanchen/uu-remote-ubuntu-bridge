"""The outer UU launcher and bin/GUI may share the same executable name."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_wine(argv, *, env, timeout, check=False):
    # Wine services can inherit anonymous capture pipes after the requested
    # process exits. Regular files let communicate() wait for that process,
    # while retaining stdout/stderr for the existing assertions.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr,
                                timeout=timeout)
        stdout.seek(0)
        stderr.seek(0)
        result.stdout = stdout.read()
        result.stderr = stderr.read()
        if check:
            result.check_returncode()
        return result


@unittest.skipUnless(os.environ.get('UURB_TEST_WINE') == '1', 'isolated Wine test')
class InjectorTargetTests(unittest.TestCase):
    def test_exact_path_ignores_same_named_launcher_and_missing_target(self):
        wine = os.environ.get('UURB_WINE_BIN', '/opt/wine-stable/bin/wine')
        wineserver = os.environ.get('UURB_WINESERVER_BIN', '/opt/wine-stable/bin/wineserver')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            (root / 'app.c').write_text('''#include <windows.h>
int main(void) { Sleep(60000); return 0; }
''')
            (root / 'marker.c').write_text('''#include <windows.h>
#include <stdio.h>
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID reserved) {
 (void)h; (void)reserved;
 if (reason == DLL_PROCESS_ATTACH) {
  char path[32768]; GetModuleFileNameA(NULL, path, sizeof(path));
  strcat(path, ".attached"); FILE *f=fopen(path,"w");
  if (f) { fputs("attached",f); fclose(f); }
 }
 return TRUE;
}
''')
            cc = ['x86_64-w64-mingw32-gcc', '-O2', '-Wall', '-Wextra', '-Werror']
            subprocess.run(cc + ['-o', str(root / 'GameViewer.exe'), str(root / 'app.c')], check=True)
            (root / 'bin/GameViewer.exe').write_bytes((root / 'GameViewer.exe').read_bytes())
            subprocess.run(cc + ['-shared', '-o', str(root / 'marker.dll'), str(root / 'marker.c')], check=True)
            subprocess.run(cc + ['-municode', '-o', str(root / 'injector.exe'),
                                str(ROOT / 'src/uu_injector.c')], check=True)
            xvfb = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0',
                                     '640x480x24', '-nolisten', 'tcp'],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            env = dict(os.environ, DISPLAY=':' + xvfb.stdout.readline().decode().strip(),
                       XAUTHORITY='', WINEPREFIX=tmp + '/wine', WINEDEBUG='-all',
                       WINEDLLOVERRIDES='mscoree,mshtml=')
            apps = []
            winpath = lambda p: 'Z:' + str(p).replace('/', '\\')
            try:
                run_wine([wine, 'wineboot', '-u'], env=env, timeout=60, check=True)
                for target in (root / 'GameViewer.exe', root / 'bin/GameViewer.exe'):
                    apps.append(subprocess.Popen([wine, str(target)], env=env,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                base = [wine, str(root / 'injector.exe'), winpath(root / 'marker.dll')]
                result = None
                for _ in range(30):
                    result = run_wine(base + [winpath(root / 'bin/GameViewer.exe')],
                                      env=env, timeout=10)
                    if result.returncode == 0:
                        break
                    time.sleep(.1)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                self.assertEqual((root / 'bin/GameViewer.exe.attached').read_text(), 'attached')
                self.assertFalse((root / 'GameViewer.exe.attached').exists())
                result = run_wine(base + [winpath(root / 'missing/GameViewer.exe')],
                                  env=env, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / 'GameViewer.exe.attached').exists())
            finally:
                run_wine([wineserver, '-k'], env=env, timeout=10)
                for app in apps:
                    app.wait(timeout=10)
                xvfb.terminate()
                xvfb.wait(timeout=5)
                xvfb.stdout.close()
