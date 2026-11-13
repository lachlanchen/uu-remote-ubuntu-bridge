"""Opt-in native clipboard publication through a long-running Wine session."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
WINE = os.environ.get('UURB_WINE_BIN', '/opt/wine-stable/bin/wine')
WINESERVER = os.environ.get('UURB_WINESERVER_BIN', '/opt/wine-stable/bin/wineserver')


@unittest.skipUnless(os.environ.get('UURB_TEST_WINE') == '1', 'isolated Wine test')
class Win32HostClipboardTests(unittest.TestCase):
    def test_live_unicode_updates_invalid_rejection_and_no_startup_replay(self):
        children = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wine_env = None
            try:
                ds = []
                for _ in range(2):
                    p = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0',
                                          '800x600x24', '-ac', '-nolisten', 'tcp'],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    children.append(p)
                    ds.append(':' + p.stdout.readline().decode().strip())
                host = dict(os.environ, DISPLAY=ds[0], XAUTHORITY='')
                wine_env = dict(os.environ, DISPLAY=ds[1], XAUTHORITY='',
                                WINEPREFIX=str(root/'wine'), WINEDEBUG='-all',
                                WINEDLLOVERRIDES='mscoree,mshtml=')
                writer, reader = str(root/'writer.exe'), str(root/'reader.exe')
                for out, src, lib in ((writer, 'src/uu_wine_clipboard_bridge.c', '-lws2_32'),
                                       (reader, 'tests/probes/uu_clipboard_read_probe.c', '-luser32')):
                    subprocess.run(['x86_64-w64-mingw32-gcc', '-std=c11', '-O2',
                                    '-Wall', '-Wextra', '-Werror', '-municode', '-o', out,
                                    str(ROOT/src), lib], check=True)
                subprocess.run([WINE, 'cmd', '/c', 'exit', '0'], env=wine_env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=True, timeout=90)

                def write(data):
                    return subprocess.run([WINE, writer, '--set-host-text'], input=data,
                                          env=wine_env, capture_output=True, timeout=10)

                def expect(text):
                    result = subprocess.run([WINE, reader, text], env=wine_env,
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

                def copy(text):
                    p = subprocess.Popen(['xclip', '-selection', 'clipboard', '-in', '-verbose'],
                                         env=host, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    children.append(p)
                    p.stdin.write(text.encode()); p.stdin.close()
                    time.sleep(.2)

                self.assertEqual(write(b'private baseline').returncode, 0)
                copy('stale Ubuntu text must not replay')
                with open(root/'helper.log', 'wb') as log:
                    helper = subprocess.Popen(['/usr/bin/python3', str(ROOT/'scripts/uu-host-clipboard.py'),
                                               '--host-display', ds[0], '--host-authority', '',
                                               '--bridge-pid', str(os.getpid()),
                                               '--wine-clipboard-writer', writer],
                                              env=wine_env, stdout=log, stderr=log)
                    children.append(helper)
                    for _ in range(50):
                        if 'Host clipboard ready' in (root/'helper.log').read_text(): break
                        time.sleep(.05)
                    self.assertIsNone(helper.poll())
                    expect('private baseline')
                    # These subprocess copies descend from the supplied fake bridge
                    # PID and must not echo through the helper.
                    copy('excluded semantic input 中文')
                    time.sleep(.3)
                    expect('private baseline')
                    helper.terminate(); helper.wait(timeout=3)
                    # A dedicated unrelated process is now the fake bridge owner.
                    blocked = subprocess.Popen(['sleep', '60'])
                    children.append(blocked)
                    args = ['/usr/bin/python3', str(ROOT/'scripts/uu-host-clipboard.py'),
                            '--host-display', ds[0], '--host-authority', '',
                            '--bridge-pid', str(blocked.pid), '--wine-clipboard-writer', writer]
                    helper = subprocess.Popen(args, env=wine_env, stdout=log, stderr=log)
                    children.append(helper)
                    time.sleep(.4)
                    for text in ('中文测试 日本語 😀 “引号”',
                                 'second copy 繁體中文\nsecond line “quote” 😀',
                                 'same copy again 中文', 'same copy again 中文'):
                        copy(text)
                        expect(text)
                    last = 'same copy again 中文'
                    for bad in (b'', b'bad\xffutf8', b'nul\0hidden', b'x'*61441):
                        self.assertNotEqual(write(bad).returncode, 0)
                        expect(last)
                    copy('x'*61441)
                    time.sleep(.4)
                    expect(last)
                    self.assertIsNone(helper.poll(), (root/'helper.log').read_text())
            finally:
                for p in reversed(children):
                    if p.poll() is None: p.terminate()
                    try: p.wait(timeout=3)
                    except subprocess.TimeoutExpired: p.kill(); p.wait()
                    for stream in (p.stdin, p.stdout, p.stderr):
                        if stream is not None and not stream.closed: stream.close()
                if wine_env:
                    subprocess.run([WINESERVER, '-k'], env=wine_env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
