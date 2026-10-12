"""Installer regressions with synthetic downloads and private shortcut fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / 'scripts/installer-download.sh'
spec = importlib.util.spec_from_file_location('archive_launchers', ROOT / 'scripts/archive-wine-launchers.py')
launchers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launchers)


class FreshInstallTests(unittest.TestCase):
    def test_translations_no_longer_advertise_the_obsolete_default(self):
        documents=[ROOT/'README.md', *sorted((ROOT/'i18n').glob('README.*.md'))]
        self.assertEqual(len(documents),11)
        for path in documents:
            with self.subTest(path=path.name):
                text=path.read_text()
                self.assertIn('**4.42.1.2835**',text)
                self.assertIn('docs/fresh-install-recovery.md',text)
                self.assertIn('./install.sh --desktop-relay vnc',text)
                if path.parent.name == 'i18n':
                    self.assertNotIn('4.33.0.8907',text)

    def test_manifest_selection_preserves_installed_and_explicit_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed, product = root / 'installed.json', root / 'GameViewer.exe'
            def choose(requested=''):
                return subprocess.check_output(['bash', '-c',
                    'source "$1"; shift; select_install_manifest "$@"', 'test',
                    str(HELPERS), requested, str(installed), str(product), str(ROOT)], text=True).strip()
            fresh = Path(choose())
            manifest = json.loads(fresh.read_text())
            self.assertEqual(manifest['version'], '4.42.1.2835')
            self.assertEqual(manifest['review_status'], 'approved')
            self.assertTrue(manifest['acceptance']['controller_input'])
            self.assertEqual(manifest['acceptance']['installer_sha256'], manifest['installer']['sha256'])
            installed.touch(); product.touch()
            self.assertEqual(choose(), str(installed))
            self.assertEqual(choose('/explicit/release.json'), '/explicit/release.json')

    def run_download(self, root, *, payload='good', cached=None, failure=False):
        destination = root / 'installer.exe'
        if cached is not None:
            destination.write_text(cached)
        (root / 'installer.exe.part').write_text('stale-other-build')
        fake_bin = root / 'bin'; fake_bin.mkdir()
        curl = fake_bin / 'curl'
        curl.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
pathlib.Path(os.environ['CALL']).write_text(json.dumps(args))
pathlib.Path(args[args.index('--output')+1]).write_text(os.environ['PAYLOAD'])
sys.exit(int(os.environ['FAIL']))
''')
        curl.chmod(0o700)
        import os
        env = dict(os.environ, PATH=str(fake_bin)+':'+os.environ['PATH'],
                   CALL=str(root/'curl.json'), PAYLOAD=payload, FAIL='22' if failure else '0')
        result = subprocess.run(['bash', '-c', 'set -Eeuo pipefail; source "$1"; shift; download_verified "$@"',
            'test', str(HELPERS), 'https://example.invalid/latest', hashlib.sha256(b'good').hexdigest(),
            str(destination)], env=env, capture_output=True, text=True)
        return result, destination

    def test_download_is_one_fresh_request_and_never_resumes_old_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); result, destination=self.run_download(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_text(), 'good')
            args=json.loads((root/'curl.json').read_text())
            self.assertNotIn('--continue-at', args)
            self.assertEqual(args[args.index('--retry')+1], '0')
            self.assertNotEqual(args[args.index('--output')+1], str(root/'installer.exe.part'))

    def test_verified_cache_does_not_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); result, _=self.run_download(root, cached='good')
            self.assertEqual(result.returncode, 0)
            self.assertFalse((root/'curl.json').exists())

    def test_wrong_version_or_failed_transfer_preserves_cache_and_cleans_new_partial(self):
        for failure in [False, True]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); result, destination=self.run_download(root, payload='other-release', cached='old-cache', failure=failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(destination.read_text(), 'old-cache')
                self.assertEqual(list(root.glob('*.part.*')), [])
                if not failure:
                    self.assertIn('--uu-installer', result.stderr)
                    self.assertIn('latest URL', result.stderr)

    def test_download_preflight_precedes_stopping_the_bridge(self):
        source=(ROOT/'install.sh').read_text()
        boundary=source.index('"${systemctl_user[@]}" stop uu-remote-bridge.service')
        self.assertLess(source.index('download_verified "$uu_download_url"'), boundary)
        self.assertLess(source.index('"$repo_dir/scripts/build-winpr.sh" --download-client-only'), boundary)


class WineShortcutTests(unittest.TestCase):
    def entry(self, path, prefix, target='UU远程.lnk', extra=''):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[Desktop Entry]\nType=Application\nName=UU远程\nExec=env '+
                        shlex.quote('WINEPREFIX='+str(prefix))+' wine '+shlex.quote('C:\\users\\me\\Desktop\\'+target)+'\n'+extra)
        return path

    def test_only_owned_visible_entries_and_paired_link_are_archived_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); prefix=root/'prefix with spaces'; apps=root/'applications'; desktop=root/'桌面'; state=root/'state'
            own=self.entry(apps/'wine/Programs/UU远程.desktop', prefix)
            desktop_entry=self.entry(desktop/'UU远程.desktop', prefix)
            link=desktop/'UU远程.lnk'; link.write_bytes(b'fixture')
            other=self.entry(apps/'wine/Programs/other.desktop', root/'other-prefix')
            unrelated=self.entry(apps/'wine/Programs/editor.desktop', prefix, 'Editor.lnk')
            hidden=self.entry(apps/'wine/Programs/wine-protocol-uuremote.desktop', prefix, extra='NoDisplay=true\n')
            canonical=apps/'uu-remote.desktop'; canonical.write_text('[Desktop Entry]\nExec=uu-remote open\n')
            plan=launchers.archive(prefix,apps,desktop,state)
            self.assertEqual(len(plan),3); self.assertTrue(own.exists()); self.assertFalse(state.exists())
            moved=launchers.archive(prefix,apps,desktop,state,True)
            self.assertEqual(len(moved),3)
            for item in moved:
                self.assertTrue(Path(item['backup']).is_file()); self.assertFalse(Path(item['source']).exists())
            for untouched in [other,unrelated,hidden,canonical]: self.assertTrue(untouched.exists())
            self.assertEqual(launchers.archive(prefix,apps,desktop,state,True),[])
            self.assertFalse(desktop_entry.exists()); self.assertFalse(link.exists())

    def test_malformed_or_symlink_shortcuts_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); apps=root/'apps'; desktop=root/'Desktop'; desktop.mkdir()
            valid=self.entry(root/'outside.desktop',root/'prefix')
            (desktop/'UU远程.desktop').symlink_to(valid)
            (desktop/'broken.desktop').write_text('not a desktop file')
            self.assertEqual(launchers.archive(root/'prefix',apps,desktop,root/'state',True),[])
            self.assertTrue(valid.exists())


class FreeRDPDownloadTests(unittest.TestCase):
    def test_exact_client_cache_and_override_work_offline_but_transport_failure_is_clear(self):
        source=(ROOT/'scripts/build-winpr.sh').read_text()
        functions=[]
        for name in ['download', 'prepare_sdl_client']:
            start=source.index(name+'() {')
            functions.append(source[start:source.index('\n}\n',start)+3])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); downloads=root/'downloads'; downloads.mkdir()
            supplied=root/'reviewed.exe'; supplied.write_bytes(b'approved')
            expected=hashlib.sha256(b'approved').hexdigest()
            setup='set -Eeuo pipefail\ndownloads="$1"\nsdl_sha256="$2"\nsdl_url=https://example.invalid/pruned\nUURB_FREERDP_CLIENT="$3"\naria2c() { echo network-unavailable >&2; return 22; }\ncurl() { echo network-unavailable >&2; return 22; }\n'
            def run(override):
                return subprocess.run(['bash','-c',setup+'\n'.join(functions)+'\nprepare_sdl_client','test',str(downloads),expected,override],capture_output=True,text=True)
            result=run(str(supplied))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('network-unavailable',result.stderr)
            result=run('')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('network-unavailable',result.stderr)
            (downloads/'sdl-freerdp.exe').write_bytes(b'wrong-build')
            result=run('')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('nightly may have been pruned',result.stderr)
            self.assertEqual((downloads/'sdl-freerdp.exe').read_bytes(),b'wrong-build')

    def test_missing_client_fails_with_actionable_fallback_and_override_stays_hash_bound(self):
        source=(ROOT/'scripts/build-winpr.sh').read_text()
        start=source.index('prepare_sdl_client() {')
        function=source[start:source.index('\n}\n',start)+3]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); supplied=root/'sdl-freerdp.exe'; supplied.write_bytes(b'wrong')
            expected=hashlib.sha256(b'approved').hexdigest()
            setup='set -Eeuo pipefail\ndownloads="$1"\nsdl_sha256="$2"\nsdl_url=https://example.invalid/pruned\nUURB_FREERDP_CLIENT="$3"\ndownload() { return 22; }\n'
            result=subprocess.run(['bash','-c',setup+function+'\nprepare_sdl_client','test',tmp,expected,''],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0); self.assertIn('--desktop-relay vnc',result.stderr)
            result=subprocess.run(['bash','-c',setup+function+'\nprepare_sdl_client','test',tmp,expected,str(supplied)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0); self.assertIn('must match',result.stderr)
            self.assertEqual(supplied.read_bytes(),b'wrong')


if __name__ == '__main__':
    unittest.main()
