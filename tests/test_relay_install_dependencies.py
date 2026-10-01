"""Execute the installer preparation boundary with failing download stubs."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RelayDependenciesTest(unittest.TestCase):
    def test_vnc_refresh_does_not_fetch_or_install_unused_rdp_runtime(self):
        source = (ROOT / "install.sh").read_text()
        body = source.split('"$repo_dir/scripts/build-compat.sh" "$compat_build"', 1)[1]
        body = body.split('runtime_digest_tmp=', 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            for name in ("build-winpr.sh", "build-libei.sh"):
                path = root / "scripts" / name
                path.write_text('#!/bin/bash\necho forbidden-download >&2\nexit 91\n')
                path.chmod(0o700)
            setup = '''set -Eeuo pipefail
repo_dir="$1"
desktop_relay="$2"
wine_prefix="$1/prefix"
compat_build="$1/compat"
freerdp_build="$1/rdp-build"
libei_build="$1/ei-build"
freerdp_install="$1/rdp-installed"
libei_install="$1/ei-installed"
terminal_proxy_install="$1/missing-proxy"
installed_terminal_proxy="$1/missing-compat-proxy"
release_manifest="$1/manifest"
installed_manifest="$1/installed-manifest"
install() { printf 'install %s\\n' "$*"; }
ln() { printf 'ln %s\\n' "$*"; }
'''
            vnc = subprocess.run(['bash', '-c', setup + body, 'test', str(root), 'vnc'],
                                 text=True, capture_output=True)
            self.assertEqual(vnc.returncode, 0, vnc.stderr)
            self.assertIn('uu-input-broker.exe', vnc.stdout)
            self.assertIn('uu-wine-clipboard-bridge.exe', vnc.stdout)
            self.assertNotIn('rdp-installed', vnc.stdout)
            self.assertNotIn('ei-installed', vnc.stdout)
            rdp = subprocess.run(['bash', '-c', setup + body, 'test', str(root), 'rdp'],
                                 text=True, capture_output=True)
            self.assertEqual(rdp.returncode, 91)
            self.assertIn('forbidden-download', rdp.stderr)


if __name__ == '__main__':
    unittest.main()
