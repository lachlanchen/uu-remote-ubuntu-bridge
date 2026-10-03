#!/usr/bin/env python3
"""Install only UU shell shortcuts; never restart a desktop or a carrier."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


def write(path, data, mode, backup):
    if path.is_symlink():
        raise ValueError('Refusing symlink: ' + str(path))
    if path.exists() and path.read_bytes() == data:
        return
    if path.exists():
        old = path.read_bytes()
        saved = backup / (path.name + '.' + hashlib.sha256(old).hexdigest()[:16])
        saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not saved.exists():saved.write_bytes(old); saved.chmod(0o600)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:stream.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inventory', type=Path, help='Reviewed private JSON map of peer names to profiles')
    args = ap.parse_args()
    os.umask(0o077)
    home = Path.home()
    source = Path(__file__).resolve().parent
    backup = home / '.local/state/uu-shell-tools/backups'
    profiles = json.loads(args.inventory.read_text()) if args.inventory else {}
    needs_fleet = any(p.get('shell_transport') == 'lazytunnel' for p in profiles.values())
    bundle = json.loads((home / '.config/lazytunnel-fleet/bundle.json').read_text()) if needs_fleet else {}
    for name, profile in profiles.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', name) or profile.get('name') != name:
            raise ValueError('Invalid peer name')
        if set(profile) - {'name','fleet_peer','shell_transport','device_id','terminal_shell'}:
            raise ValueError('Unexpected profile fields')
        if profile.get('shell_transport') not in ('lazytunnel','terminal'):
            raise ValueError('Invalid transport')
        if profile['shell_transport'] == 'lazytunnel' and profile.get('fleet_peer') not in bundle['aliases']:
            raise ValueError('Peer is not enrolled')
        if profile.get('device_id') and not re.fullmatch(r'[A-Za-z0-9-]{1,80}', profile['device_id']):
            raise ValueError('Invalid device ID')
        if profile.get('terminal_shell') not in ('powershell','cmd','zsh','bash'):
            raise ValueError('Invalid terminal shell')
    # Validate every input before writing any launcher or profile.
    for filename in ('uu-shell','uu-ssh'):
        data = (source / filename).read_bytes()
        if filename == 'uu-ssh':
            data = ('#!' + sys.executable + '\n').encode() + data.split(b'\n', 1)[1]
        write(home / '.local/bin' / filename, data, 0o755, backup)
    for name, profile in profiles.items():
        path = home / '.config/uu-ssh/peers' / (name + '.json')
        # Preserve explicit old mapping metadata for ssh uu-PEER and --native.
        old = json.loads(path.read_text()) if path.exists() else {}
        old.update(profile)
        write(path, (json.dumps(old, indent=2) + '\n').encode(), 0o600, backup)
    print('Installed shell shortcuts and', len(profiles), 'reviewed profiles; no service changes.')


if __name__ == '__main__':main()
