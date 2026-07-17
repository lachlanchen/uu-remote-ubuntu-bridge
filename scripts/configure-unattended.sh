#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bridge_user="$(id -un)"
bridge_home="$(getent passwd "$bridge_user" | cut -d: -f6)"
primary_group="$(id -gn "$bridge_user")"
credential_dir="$bridge_home/.config/uu-remote-bridge"
credential_file="$credential_dir/login-keyring-password.cred"
user_unit_dir="$bridge_home/.config/systemd/user"
dropin_dir="$user_unit_dir/uu-remote-bridge.service.d"
gdm_config='/etc/gdm3/custom.conf'
state_dir='/var/lib/uu-remote-bridge'
state_file="$state_dir/gdm-autologin-state.ini"
replace_credential=false
action='enable'
systemctl_user=(
    /usr/bin/env
    "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    /usr/bin/systemctl --user
)

usage() {
    cat <<'EOF'
usage: ./scripts/configure-unattended.sh [enable|disable|status] [options]

  enable                 enable unattended startup (default)
  disable                restore the previous GDM autologin configuration
  status                 report boot-readiness without displaying secrets
  --replace-credential   replace the TPM-backed keyring credential
  -h, --help             show this help
EOF
}

while (($#)); do
    case "$1" in
        enable|disable|status)
            action="$1"
            shift
            ;;
        --replace-credential)
            replace_credential=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ $EUID -eq 0 ]]; then
    printf 'Run this command as the desktop user, not as root.\n' >&2
    exit 1
fi
if [[ -z "$bridge_home" || ! -d "$bridge_home" ]]; then
    printf 'Cannot determine the desktop user home directory.\n' >&2
    exit 1
fi

current_group_has_tss() {
    id -nG | tr ' ' '\n' | grep -Fxq tss
}

account_has_tss() {
    id -nG "$bridge_user" | tr ' ' '\n' | grep -Fxq tss
}

ensure_dependencies() {
    if command -v crudini >/dev/null 2>&1 && \
       command -v setfacl >/dev/null 2>&1 && \
       /usr/bin/python3 -c 'from gi.repository import Gio, GLib' \
           >/dev/null 2>&1; then
        return
    fi
    sudo apt-get update
    sudo apt-get install -y acl crudini python3-gi
}

state_get() {
    sudo crudini --get "$state_file" previous "$1"
}

remember_gdm_state() {
    local key
    local value

    if sudo test -f "$state_file"; then
        return
    fi

    sudo install -d -m 0700 "$state_dir"
    sudo install -m 0600 /dev/null "$state_file"
    sudo crudini --set "$state_file" previous ManagedUser "$bridge_user"
    sudo crudini --set "$state_file" previous TemporaryTpmAcl false
    if account_has_tss; then
        sudo crudini --set "$state_file" previous TssMember true
    else
        sudo crudini --set "$state_file" previous TssMember false
    fi

    for key in AutomaticLoginEnable AutomaticLogin; do
        if value="$(sudo crudini --get "$gdm_config" daemon "$key" \
            2>/dev/null)"; then
            sudo crudini --set "$state_file" previous "${key}Present" true
            sudo crudini --set "$state_file" previous "$key" "$value"
        else
            sudo crudini --set "$state_file" previous "${key}Present" false
        fi
    done
}

restore_gdm_state() {
    local key
    local managed_user
    local present
    local value

    if ! sudo test -f "$state_file"; then
        return
    fi

    managed_user="$(state_get ManagedUser)"
    if [[ "$managed_user" != "$bridge_user" ]]; then
        printf 'Refusing to restore state owned by user %s.\n' \
            "$managed_user" >&2
        exit 1
    fi

    if [[ "$(sudo crudini --get "$gdm_config" daemon AutomaticLoginEnable \
        2>/dev/null || true)" == true && \
          "$(sudo crudini --get "$gdm_config" daemon AutomaticLogin \
        2>/dev/null || true)" == "$bridge_user" ]]; then
        for key in AutomaticLoginEnable AutomaticLogin; do
            present="$(state_get "${key}Present")"
            if [[ "$present" == true ]]; then
                value="$(state_get "$key")"
                sudo crudini --set "$gdm_config" daemon "$key" "$value"
            else
                sudo crudini --del "$gdm_config" daemon "$key" \
                    2>/dev/null || true
            fi
        done
    else
        printf 'GDM autologin changed after setup; preserving current values.\n'
    fi

    if [[ "$(state_get TemporaryTpmAcl 2>/dev/null || printf false)" == \
          true && -e /dev/tpmrm0 ]]; then
        sudo setfacl -x "u:$bridge_user" /dev/tpmrm0 2>/dev/null || true
    fi
    if [[ "$(state_get TssMember)" == false ]] && account_has_tss; then
        sudo gpasswd --delete "$bridge_user" tss >/dev/null
    fi
    sudo rm -f "$state_file"
}

write_encrypted_credential() {
    local confirmation
    local password
    local temporary

    if [[ -s "$credential_file" && "$replace_credential" == false ]]; then
        return
    fi

    printf 'Enter the GNOME login keyring password.\n'
    printf 'This is normally the Ubuntu login password.\n'
    while true; do
        read -rsp 'Keyring password: ' password
        printf '\n'
        read -rsp 'Repeat keyring password: ' confirmation
        printf '\n'
        if [[ -n "$password" && "$password" == "$confirmation" ]]; then
            break
        fi
        printf 'Passwords did not match or were empty.\n' >&2
    done

    temporary="$(mktemp -d)"
    trap 'rm -rf "${temporary:-}"' EXIT
    printf '%s' "$password" >"$temporary/plaintext"
    unset password confirmation

    sudo systemd-creds encrypt --with-key=tpm2 \
        --name=login-keyring-password \
        "$temporary/plaintext" "$temporary/encrypted"
    install -d -m 0700 "$credential_dir"
    sudo install -o "$bridge_user" -g "$primary_group" -m 0600 \
        "$temporary/encrypted" "$credential_file"
    rm -rf "$temporary"
    trap - EXIT
}

install_units() {
    install -d -m 0755 "$bridge_home/.local/bin" "$user_unit_dir" \
        "$dropin_dir"
    install -m 0755 "$repo_dir/scripts/uu-keyring-unlock.py" \
        "$bridge_home/.local/bin/uu-keyring-unlock"
    install -m 0644 "$repo_dir/systemd/uu-keyring-unlock.service" \
        "$user_unit_dir/uu-keyring-unlock.service"
    install -m 0644 "$repo_dir/systemd/uu-remote-bridge-unattended.conf" \
        "$dropin_dir/10-unattended.conf"
}

enable_unattended() {
    if [[ ! -f "$gdm_config" ]]; then
        printf 'GDM configuration is missing: %s\n' "$gdm_config" >&2
        exit 1
    fi
    sudo -v
    if ! sudo systemd-creds has-tpm2 >/dev/null; then
        printf 'A working TPM2 is required for unattended credential storage.\n' \
            >&2
        exit 1
    fi
    if [[ ! -e /dev/tpmrm0 ]]; then
        printf 'The TPM2 resource manager device /dev/tpmrm0 is missing.\n' \
            >&2
        exit 1
    fi

    ensure_dependencies
    remember_gdm_state
    write_encrypted_credential
    install_units

    sudo usermod --append --groups tss "$bridge_user"
    if ! current_group_has_tss && \
       [[ ! -r /dev/tpmrm0 || ! -w /dev/tpmrm0 ]]; then
        sudo setfacl -m "u:$bridge_user:rw" /dev/tpmrm0
        sudo crudini --set "$state_file" previous TemporaryTpmAcl true
    fi
    sudo crudini --set "$gdm_config" daemon AutomaticLoginEnable true
    sudo crudini --set "$gdm_config" daemon AutomaticLogin "$bridge_user"

    "${systemctl_user[@]}" daemon-reload
    "${systemctl_user[@]}" reenable uu-keyring-unlock.service

    "${systemctl_user[@]}" restart uu-keyring-unlock.service
    "${systemctl_user[@]}" restart uu-remote-bridge.service
    if ! current_group_has_tss; then
        printf 'Per-user TPM device access keeps this login restart-safe.\n'
        printf 'The tss group replaces it at the next login or reboot.\n'
    fi

    printf 'Unattended startup is configured for user %s.\n' "$bridge_user"
    printf 'Reboot is required before the new boot path is authoritative.\n'
}

disable_unattended() {
    sudo -v
    ensure_dependencies
    restore_gdm_state
    "${systemctl_user[@]}" disable --now uu-keyring-unlock.service \
        >/dev/null 2>&1 || true
    rm -f "$dropin_dir/10-unattended.conf" "$credential_file"
    "${systemctl_user[@]}" daemon-reload
    printf 'Unattended startup is disabled; reboot to apply the GDM change.\n'
}

show_status() {
    local autologin='no'
    local credential='missing'
    local enabled='no'
    local membership='no'
    local session_membership='no'
    local tpm_access='no'

    if [[ -r "$gdm_config" ]] && command -v crudini >/dev/null 2>&1 && \
       [[ "$(crudini --get "$gdm_config" daemon AutomaticLoginEnable \
            2>/dev/null || true)" == true ]] && \
       [[ "$(crudini --get "$gdm_config" daemon AutomaticLogin \
            2>/dev/null || true)" == "$bridge_user" ]]; then
        autologin='yes'
    fi
    [[ -s "$credential_file" ]] && credential='present'
    "${systemctl_user[@]}" is-enabled --quiet \
        uu-keyring-unlock.service && enabled='yes'
    account_has_tss && membership='yes'
    current_group_has_tss && session_membership='yes'
    [[ -r /dev/tpmrm0 && -w /dev/tpmrm0 ]] && tpm_access='yes'

    printf 'GDM autologin:             %s\n' "$autologin"
    printf 'TPM credential:            %s\n' "$credential"
    printf 'Keyring unlock enabled:    %s\n' "$enabled"
    printf 'Account in tss group:      %s\n' "$membership"
    printf 'tss active in this login:  %s\n' "$session_membership"
    printf 'TPM access in this login:  %s\n' "$tpm_access"
}

case "$action" in
    enable)
        enable_unattended
        ;;
    disable)
        disable_unattended
        ;;
    status)
        show_status
        ;;
esac
