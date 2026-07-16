#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${UURB_BUILD_DIR:-$repo_dir/build/winpr}"
output_dir="${1:-$repo_dir/build/freerdp}"
downloads="$work_dir/downloads"
runtime="$work_dir/runtime"
source_dir="$work_dir/FreeRDP"
build_dir="$work_dir/build"

freerdp_commit='6b107f0aadbabc47941c5a5b893b88c01792af6d'
sdl_url='https://ci.freerdp.com/job/freerdp-nightly-windows/arch=win64,label=vs2017/2038/artifact/install/bin/sdl-freerdp.exe'
sdl_sha256='1534187d731b2e4a6cb6d1107c0129727517fe3acf1441b5a2567aea5ea31d60'
openssl_url='https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-openssl-3.6.3-1-any.pkg.tar.zst'
openssl_sha256='82de7ff886112374ffae9e7b3c843c82342e198543fb024790416ef56434fe9f'
cjson_url='https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-cjson-1.7.19-1-any.pkg.tar.zst'
cjson_sha256='f20c3fa89ab072caba93baca374f40b8c9ce23d6383aa55552ff13f31c7879aa'
uriparser_url='https://repo.msys2.org/mingw/mingw64/mingw-w64-x86_64-uriparser-1.0.2-1-any.pkg.tar.zst'
uriparser_sha256='c7c1db089f04aa3c616fb53cddfa250b4e4dbb864b7d4d5250ade83e8a1e8d19'

require() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'missing build tool: %s\n' "$1" >&2
        exit 1
    }
}

download() {
    local url="$1"
    local expected="$2"
    local destination="$3"
    local attempt

    if [[ -f "$destination" ]] && \
       printf '%s  %s\n' "$expected" "$destination" | sha256sum -c - \
           >/dev/null 2>&1; then
        return
    fi
    for attempt in 1 2; do
        if command -v aria2c >/dev/null 2>&1; then
            aria2c --allow-overwrite=true --auto-file-renaming=false \
                --continue=true --max-connection-per-server=8 \
                --min-split-size=1M --split=8 \
                --dir="$(dirname -- "$destination")" \
                --out="$(basename -- "$destination").part" "$url"
        else
            curl --continue-at - --fail --location --retry 3 \
                --output "$destination.part" "$url"
        fi
        if printf '%s  %s\n' "$expected" "$destination.part" | \
            sha256sum -c -; then
            mv "$destination.part" "$destination"
            rm -f "$destination.part.aria2"
            return
        fi
        rm -f "$destination.part" "$destination.part.aria2"
        printf 'download hash mismatch; retrying %s (%s/2)\n' \
            "$url" "$attempt" >&2
    done
    printf 'download verification failed: %s\n' "$url" >&2
    exit 1
}

for command in cmake curl git ninja sha256sum tar \
    x86_64-w64-mingw32-gcc-win32 x86_64-w64-mingw32-windres; do
    require "$command"
done

mkdir -p "$downloads" "$output_dir"
download "$sdl_url" "$sdl_sha256" "$downloads/sdl-freerdp.exe"
download "$openssl_url" "$openssl_sha256" "$downloads/openssl.pkg.tar.zst"
download "$cjson_url" "$cjson_sha256" "$downloads/cjson.pkg.tar.zst"
download "$uriparser_url" "$uriparser_sha256" \
    "$downloads/uriparser.pkg.tar.zst"

rm -rf "$runtime"
mkdir -p "$runtime"
for package in "$downloads"/*.pkg.tar.zst; do
    tar --zstd -xf "$package" -C "$runtime"
done

if [[ ! -d "$source_dir/.git" ]]; then
    rm -rf "$source_dir"
    git clone --filter=blob:none --no-checkout \
        https://github.com/FreeRDP/FreeRDP.git "$source_dir"
fi
git -C "$source_dir" fetch --depth 1 origin "$freerdp_commit"
git -C "$source_dir" checkout --detach "$freerdp_commit"
if [[ "$(git -C "$source_dir" rev-parse HEAD)" != "$freerdp_commit" ]]; then
    printf 'FreeRDP source revision verification failed\n' >&2
    exit 1
fi

rm -rf "$build_dir"
cmake -S "$source_dir" -B "$build_dir" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    '-DCMAKE_C_FLAGS=-D__STDC_NO_THREADS__=1' \
    -DCMAKE_SYSTEM_NAME=Windows \
    -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc-win32 \
    -DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres \
    "-DCMAKE_FIND_ROOT_PATH=/usr/x86_64-w64-mingw32;$runtime/mingw64" \
    -DCMAKE_PREFIX_PATH="$runtime/mingw64" \
    -DOPENSSL_ROOT_DIR="$runtime/mingw64" \
    -DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER \
    -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY \
    -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY \
    -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY \
    -DUSE_UNWIND=OFF \
    -DWITH_VERBOSE_WINPR_ASSERT=OFF \
    -DWITH_INTERNAL_MD4=ON \
    -DWITH_INTERNAL_MD5=ON \
    -DWITH_INTERNAL_RC4=ON \
    -DWITH_NATIVE_SSPI=OFF \
    -DWITH_WINPR_TOOLS=OFF \
    -DWITH_CLIENT=OFF \
    -DWITH_SERVER=OFF \
    -DWITH_CHANNELS=OFF \
    -DWITH_PROXY=OFF \
    -DWITH_SHADOW=OFF \
    -DWITH_SAMPLE=ON \
    -DWITH_MANPAGES=OFF \
    -DWITH_FFMPEG=OFF \
    -DWITH_SWSCALE=OFF \
    -DWITH_CAIRO=OFF \
    -DWITH_JPEG=OFF \
    -DWITH_KRB5=OFF \
    -DWITH_PKCS11=OFF \
    -DWITH_SMARTCARD_EMULATE=OFF \
    -DWITH_SMARTCARD_INSPECT=OFF \
    -DWITH_FUSE=OFF \
    -DWITH_OPUS=OFF \
    -DWITH_SOXR=OFF \
    -DWITH_YUV=OFF
ninja -C "$build_dir" -j "$(nproc)" winpr

install -m 0755 "$downloads/sdl-freerdp.exe" \
    "$output_dir/sdl-freerdp.exe"
install -m 0755 "$build_dir/winpr/libwinpr/libwinpr3.dll" \
    "$output_dir/libwinpr3.dll"
install -m 0755 "$runtime/mingw64/bin/libcrypto-3-x64.dll" \
    "$output_dir/libcrypto-3-x64.dll"
install -m 0755 "$runtime/mingw64/bin/libssl-3-x64.dll" \
    "$output_dir/libssl-3-x64.dll"
install -m 0755 "$runtime/mingw64/bin/libcjson-1.dll" \
    "$output_dir/libcjson-1.dll"
install -m 0755 "$runtime/mingw64/bin/liburiparser-1.dll" \
    "$output_dir/liburiparser-1.dll"
mkdir -p "$output_dir/ossl-modules"
install -m 0755 "$runtime/mingw64/lib/ossl-modules/legacy.dll" \
    "$output_dir/ossl-modules/legacy.dll"

printf 'FreeRDP Windows relay runtime built in %s\n' "$output_dir"
