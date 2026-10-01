import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('UURB_TEST_X11') == '1', 'opt-in isolated X11 test')
class HostClipboardTests(unittest.TestCase):
    def test_external_copy_unicode_no_startup_replay_and_no_bridge_echo(self):
        children = []
        groups = []
        with tempfile.TemporaryDirectory() as temporary:
            try:
                displays = []
                for _ in range(2):
                    process = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0',
                                                '800x600x24', '-ac', '-nolisten', 'tcp'],
                                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    children.append(process)
                    displays.append(':' + process.stdout.readline().decode().strip())
                host_env = dict(os.environ, DISPLAY=displays[0], XAUTHORITY='')
                private_env = dict(os.environ, DISPLAY=displays[1], XAUTHORITY='')

                def copy(text, env):
                    p = subprocess.Popen(['xclip', '-selection', 'clipboard', '-in', '-verbose'],
                                         env=env, stdin=subprocess.PIPE,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    children.append(p)
                    p.stdin.write(text.encode());p.stdin.close()
                    time.sleep(.15)

                def read():
                    return subprocess.run(['xclip', '-selection', 'clipboard', '-out'],
                                          env=private_env, capture_output=True, timeout=2).stdout

                copy('old host must not replay', host_env)
                copy('old private stays', private_env)
                # The fake bridge owns its clipboard child, exactly like the
                # semantic input and inbound clipboard helpers in production.
                blocked = subprocess.Popen(['/usr/bin/python3', '-c', '''
import subprocess,sys
text=sys.stdin.buffer.readline().rstrip(b'\\n')
p=subprocess.Popen(['xclip','-selection','clipboard','-in','-verbose'],stdin=subprocess.PIPE)
p.stdin.write(text);p.stdin.close();p.wait()
'''], env=host_env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
                children.append(blocked);groups.append(blocked.pid)
                with open(Path(temporary) / 'helper.log', 'wb') as log:
                    helper = subprocess.Popen(['/usr/bin/python3', str(ROOT/'scripts/uu-host-clipboard.py'),
                                               '--host-display', displays[0], '--host-authority', '',
                                               '--bridge-pid', str(blocked.pid)], env=private_env,
                                              stdout=log, stderr=log)
                    children.append(helper)
                    for _ in range(50):
                        if 'Host clipboard ready' in (Path(temporary)/'helper.log').read_text():break
                        if helper.poll() is not None:break
                        time.sleep(.05)
                    self.assertIsNone(helper.poll(), (Path(temporary)/'helper.log').read_text())
                    time.sleep(.3)
                    self.assertEqual(read(), b'old private stays')
                    message = 'Copied from Ubuntu 中文\nsecond line “quote” 😀'
                    copy(message, host_env)
                    for _ in range(50):
                        if read() == message.encode():break
                        time.sleep(.05)
                    self.assertEqual(read(), message.encode(), (Path(temporary)/'helper.log').read_text())
                    if os.environ.get('UURB_TEST_WINE') == '1':
                        exe = str(Path(temporary)/'clipboard-read.exe')
                        subprocess.run(['x86_64-w64-mingw32-gcc', '-municode', '-o', exe,
                                        str(ROOT/'tests/probes/uu_clipboard_read_probe.c'),
                                        '-luser32'], check=True)
                        wine_env = dict(private_env, WINEPREFIX=str(Path(temporary)/'wine'),
                                        WINEDEBUG='-all', WINEDLLOVERRIDES='mscoree,mshtml=')
                        try:
                            result = subprocess.run(['/opt/wine-stable/bin/wine', exe],
                                                    env=wine_env, capture_output=True, timeout=90)
                            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                        finally:
                            subprocess.run(['/opt/wine-stable/bin/wineserver', '-k'], env=wine_env,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    blocked.stdin.write('dictation must stay on host 中文\n'.encode());blocked.stdin.close()
                    time.sleep(.5)
                    self.assertEqual(read(), message.encode())
                    # Same app recopy and oversize copies must not truncate or
                    # replace the last good clipboard with a partial payload.
                    copy('x' * (60*1024+1), host_env)
                    time.sleep(.4)
                    self.assertEqual(read(), message.encode())
                    copy('final copy', host_env)
                    for _ in range(30):
                        if read() == b'final copy':break
                        time.sleep(.05)
                    self.assertEqual(read(), b'final copy')
                    self.assertIsNone(helper.poll())
            finally:
                for pid in groups:
                    try:os.killpg(pid, signal.SIGTERM)
                    except ProcessLookupError:pass
                for process in reversed(children):
                    if process.poll() is None:process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream is not None and not stream.closed:stream.close()


if __name__ == '__main__':
    unittest.main()
