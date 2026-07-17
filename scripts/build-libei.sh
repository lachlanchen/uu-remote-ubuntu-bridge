#!/usr/bin/env bash

set -Eeuo pipefail

# Keep an activated Conda environment from supplying a different Python,
# CMake, or XML toolchain than the Ubuntu packages used for this native shim.
export PATH=/usr/bin:/bin

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-$repo_dir/build/libei}"
version=1.2.1
archive_name="libei-$version.tar.gz"
archive_url="https://gitlab.freedesktop.org/libinput/libei/-/archive/$version/$archive_name"
archive_sha256=7e06f06aa4dd1f7d170a0e5194644fe5cc889adc9b7be16bed5f2c39145569a4
patch_file="$repo_dir/patches/libei-1.2.1-close-keymap-fd.patch"
downloads_dir="$repo_dir/build/downloads"
archive="$downloads_dir/$archive_name"
source_dir="$repo_dir/build/libei-$version-source"
build_dir="$repo_dir/build/libei-$version-build"
source_stamp="$source_dir/.uurb-source-stamp"
expected_stamp="$archive_sha256:$(sha256sum "$patch_file" | awk '{print $1}')"

for command in curl meson ninja patch readelf sha256sum tar; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'missing libei build command: %s\n' "$command" >&2
        exit 1
    fi
done

mkdir -p "$downloads_dir"
if [[ ! -f "$archive" ]] ||
   ! printf '%s  %s\n' "$archive_sha256" "$archive" |
       sha256sum -c - >/dev/null 2>&1; then
    temporary_archive="$(mktemp "$downloads_dir/.$archive_name.XXXXXX")"
    trap 'rm -f "${temporary_archive:-}"' EXIT
    curl --fail --location --retry 3 --output "$temporary_archive" \
        "$archive_url"
    printf '%s  %s\n' "$archive_sha256" "$temporary_archive" |
        sha256sum -c -
    mv "$temporary_archive" "$archive"
    temporary_archive=''
fi

if [[ ! -f "$source_stamp" ]] ||
   [[ "$(cat "$source_stamp")" != "$expected_stamp" ]]; then
    rm -rf "$source_dir" "$build_dir"
    mkdir -p "$source_dir"
    tar -xzf "$archive" --strip-components=1 -C "$source_dir"
    patch --batch --fuzz=0 --directory="$source_dir" --strip=1 <"$patch_file"
    printf '%s\n' "$expected_stamp" >"$source_stamp"
fi

if [[ -d "$build_dir" ]]; then
    meson setup --wipe "$build_dir" "$source_dir" \
        --buildtype=release \
        -Dliboeffis=disabled \
        -Dtests=disabled \
        -Ddocumentation=[]
else
    meson setup "$build_dir" "$source_dir" \
        --buildtype=release \
        -Dliboeffis=disabled \
        -Dtests=disabled \
        -Ddocumentation=[]
fi
ninja -C "$build_dir" src/libei.so.$version

library="$build_dir/src/libei.so.$version"
if ! readelf -d "$library" | grep -q 'Library soname: \[libei.so.1\]'; then
    printf 'The patched libei build has an unexpected SONAME.\n' >&2
    exit 1
fi

mkdir -p "$output_dir"
install -m 0755 "$library" "$output_dir/libei.so.$version"
ln -sfn "libei.so.$version" "$output_dir/libei.so.1"
printf 'Built patched libei %s at %s\n' "$version" "$output_dir"
