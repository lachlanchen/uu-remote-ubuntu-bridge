#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>

#define DEFAULT_CURSOR_SIZE 48U
#define MIN_CURSOR_SIZE 24U
#define MAX_CURSOR_SIZE 128U

typedef HCURSOR(WINAPI *set_cursor_fn)(HCURSOR);
typedef BOOL(WINAPI *get_cursor_info_fn)(PCURSORINFO);
typedef BOOL(WINAPI *get_icon_info_fn)(HICON, PICONINFO);

static set_cursor_fn original_set_cursor;
static get_cursor_info_fn original_get_cursor_info;
static get_icon_info_fn original_get_icon_info;
static HCURSOR fallback_cursor;
static UINT fallback_cursor_width;
static UINT fallback_cursor_height;
static HANDLE log_file = INVALID_HANDLE_VALUE;
static SRWLOCK log_lock = SRWLOCK_INIT;
static volatile LONG hidden_cursor_count;

static void write_log(const char *message)
{
    DWORD written;

    if (log_file == INVALID_HANDLE_VALUE)
        return;
    /* Wine's append handle can overwrite records from concurrent callers. */
    AcquireSRWLockExclusive(&log_lock);
    WriteFile(log_file, message, (DWORD)strlen(message), &written, NULL);
    ReleaseSRWLockExclusive(&log_lock);
}

static void default_log_path(wchar_t *path)
{
    DWORD length;

    length = GetTempPathW(MAX_PATH, path);
    if (length == 0 || length >= MAX_PATH - 20)
        lstrcpynW(path, L"uu-cursor-guard.log", MAX_PATH);
    else
        lstrcatW(path, L"uu-cursor-guard.log");
}

static void open_log(const wchar_t *process_name)
{
    wchar_t path[MAX_PATH];
    DWORD length = 0;

    /*
     * Wine services do not reliably inherit the bridge environment. Keep the
     * server guard on its process-local temp path even when launch order
     * changes; the relay guard uses the explicit bridge log path.
     */
    if (_wcsicmp(process_name, L"GameViewerServer.exe") != 0)
        length = GetEnvironmentVariableW(
            L"UURB_CURSOR_GUARD_LOG", path, MAX_PATH);
    if (length == 0 || length >= MAX_PATH)
        default_log_path(path);

    log_file = CreateFileW(path, FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
}

static UINT configured_cursor_size(void)
{
    wchar_t value[16];
    wchar_t *end;
    unsigned long parsed;
    DWORD length;

    length = GetEnvironmentVariableW(
        L"UURB_CURSOR_SIZE", value, sizeof(value) / sizeof(value[0]));
    if (length == 0 || length >= sizeof(value) / sizeof(value[0]))
        return DEFAULT_CURSOR_SIZE;

    parsed = wcstoul(value, &end, 10);
    if (end == value || *end != L'\0' ||
        parsed < MIN_CURSOR_SIZE || parsed > MAX_CURSOR_SIZE)
        return DEFAULT_CURSOR_SIZE;
    return (UINT)parsed;
}

static BOOL cursor_dimensions(HCURSOR cursor, UINT *width, UINT *height)
{
    ICONINFO icon;
    BITMAP bitmap;
    HBITMAP source;
    LONG bitmap_width;
    LONG bitmap_height;
    BOOL result = FALSE;

    ZeroMemory(&icon, sizeof(icon));
    ZeroMemory(&bitmap, sizeof(bitmap));
    if (!GetIconInfo(cursor, &icon))
        return FALSE;

    source = icon.hbmColor != NULL ? icon.hbmColor : icon.hbmMask;
    if (source != NULL &&
        GetObjectW(source, (int)sizeof(bitmap), &bitmap) != 0) {
        bitmap_width =
            bitmap.bmWidth < 0 ? -bitmap.bmWidth : bitmap.bmWidth;
        bitmap_height =
            bitmap.bmHeight < 0 ? -bitmap.bmHeight : bitmap.bmHeight;
        if (icon.hbmColor == NULL)
            bitmap_height /= 2;
        if (bitmap_width > 0 && bitmap_height > 0) {
            *width = (UINT)bitmap_width;
            *height = (UINT)bitmap_height;
            result = TRUE;
        }
    }

    if (icon.hbmMask != NULL)
        DeleteObject(icon.hbmMask);
    if (icon.hbmColor != NULL)
        DeleteObject(icon.hbmColor);
    return result;
}

static BOOL load_fallback_cursor(void)
{
    HCURSOR base_cursor;
    UINT requested_size;

    requested_size = configured_cursor_size();
    base_cursor = LoadCursorW(NULL, IDC_ARROW);
    if (base_cursor == NULL)
        return FALSE;

    fallback_cursor = (HCURSOR)CopyImage(
        base_cursor, IMAGE_CURSOR, (int)requested_size,
        (int)requested_size, LR_DEFAULTCOLOR);
    if (fallback_cursor == NULL ||
        !cursor_dimensions(fallback_cursor, &fallback_cursor_width,
                           &fallback_cursor_height) ||
        fallback_cursor_width != requested_size ||
        fallback_cursor_height != requested_size) {
        if (fallback_cursor != NULL)
            DestroyCursor(fallback_cursor);
        fallback_cursor = base_cursor;
        if (!cursor_dimensions(fallback_cursor, &fallback_cursor_width,
                               &fallback_cursor_height))
            return FALSE;
    }
    return TRUE;
}

static void write_active_log(const char *guard_name)
{
    char message[128];
    int length;

    length = snprintf(message, sizeof(message),
                      "%s active (cursor %ux%u)\r\n", guard_name,
                      fallback_cursor_width, fallback_cursor_height);
    if (length > 0 && (size_t)length < sizeof(message))
        write_log(message);
}

static HCURSOR WINAPI guarded_set_cursor(HCURSOR cursor)
{
    if (cursor == NULL) {
        cursor = fallback_cursor;
        if (InterlockedIncrement(&hidden_cursor_count) == 1)
            write_log("UU cursor guard replaced a hidden cursor\r\n");
    }

    if (original_set_cursor == NULL)
        return NULL;
    return original_set_cursor(cursor);
}

static BOOL WINAPI guarded_get_cursor_info(PCURSORINFO cursor)
{
    BOOL result;

    if (original_get_cursor_info == NULL)
        return FALSE;
    result = original_get_cursor_info(cursor);
    if (result && cursor != NULL) {
        cursor->flags = CURSOR_SHOWING;
        cursor->hCursor = fallback_cursor;
    }
    return result;
}

static BOOL WINAPI guarded_get_icon_info(HICON icon, PICONINFO info)
{
    BOOL result;
    DWORD error;

    if (original_get_icon_info == NULL)
        return FALSE;
    result = original_get_icon_info(icon, info);
    if (result)
        return TRUE;

    error = GetLastError();
    if (error != ERROR_INVALID_CURSOR_HANDLE || fallback_cursor == NULL)
        return FALSE;
    return original_get_icon_info(fallback_cursor, info);
}

static BOOL cursor_reader_self_test(void)
{
    CURSORINFO cursor;
    ICONINFO icon;

    ZeroMemory(&cursor, sizeof(cursor));
    cursor.cbSize = sizeof(cursor);
    if (!guarded_get_cursor_info(&cursor) ||
        cursor.hCursor != fallback_cursor ||
        fallback_cursor_width == 0 || fallback_cursor_height == 0 ||
        (cursor.flags & CURSOR_SHOWING) == 0)
        return FALSE;

    ZeroMemory(&icon, sizeof(icon));
    if (!guarded_get_icon_info(cursor.hCursor, &icon))
        return FALSE;
    if (icon.hbmMask != NULL)
        DeleteObject(icon.hbmMask);
    if (icon.hbmColor != NULL)
        DeleteObject(icon.hbmColor);
    return TRUE;
}

static BOOL patch_import(HMODULE module, const char *dll_name,
                         const char *function_name, uintptr_t replacement,
                         uintptr_t *original)
{
    BYTE *base = (BYTE *)module;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt;
    IMAGE_IMPORT_DESCRIPTOR *descriptor;

    if (dos->e_magic != IMAGE_DOS_SIGNATURE)
        return FALSE;

    nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE)
        return FALSE;

    descriptor = (IMAGE_IMPORT_DESCRIPTOR *)(
        base + nt->OptionalHeader
                   .DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT]
                   .VirtualAddress);
    if ((BYTE *)descriptor == base)
        return FALSE;

    for (; descriptor->Name != 0; descriptor++) {
        const char *imported_dll = (const char *)(base + descriptor->Name);
        IMAGE_THUNK_DATA *names;
        IMAGE_THUNK_DATA *addresses;

        if (_stricmp(imported_dll, dll_name) != 0)
            continue;

        names = descriptor->OriginalFirstThunk != 0
                    ? (IMAGE_THUNK_DATA *)(base + descriptor->OriginalFirstThunk)
                    : (IMAGE_THUNK_DATA *)(base + descriptor->FirstThunk);
        addresses = (IMAGE_THUNK_DATA *)(base + descriptor->FirstThunk);

        for (; names->u1.AddressOfData != 0; names++, addresses++) {
            IMAGE_IMPORT_BY_NAME *import_name;
            DWORD old_protection;

            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal))
                continue;
            import_name = (IMAGE_IMPORT_BY_NAME *)(
                base + names->u1.AddressOfData);
            if (strcmp((const char *)import_name->Name, function_name) != 0)
                continue;

            if (original != NULL)
                *original = (uintptr_t)addresses->u1.Function;
            if (!VirtualProtect(&addresses->u1.Function,
                                sizeof(addresses->u1.Function),
                                PAGE_READWRITE, &old_protection))
                return FALSE;
            addresses->u1.Function = (ULONGLONG)replacement;
            FlushInstructionCache(GetCurrentProcess(),
                                  &addresses->u1.Function,
                                  sizeof(addresses->u1.Function));
            VirtualProtect(&addresses->u1.Function,
                           sizeof(addresses->u1.Function), old_protection,
                           &old_protection);
            return TRUE;
        }
    }

    return FALSE;
}

static DWORD WINAPI initialize_guard(void *unused)
{
    HMODULE main_module;
    HMODULE streamer_module;
    HWND relay;
    wchar_t executable[MAX_PATH];
    const wchar_t *process_name;
    wchar_t *separator;
    uintptr_t set_cursor_address = 0;
    uintptr_t get_cursor_info_address = 0;
    uintptr_t get_icon_info_address = 0;
    BOOL cursor_info_patched;
    BOOL icon_info_patched;
    BOOL streamer_cursor_info_patched;
    BOOL streamer_icon_info_patched;

    (void)unused;
    if (GetModuleFileNameW(NULL, executable, MAX_PATH) == 0)
        return 1;
    separator = wcsrchr(executable, L'\\');
    process_name = separator == NULL ? executable : separator + 1;
    open_log(process_name);
    if (!load_fallback_cursor()) {
        write_log("UU cursor guard initialization failed\r\n");
        if (log_file != INVALID_HANDLE_VALUE)
            FlushFileBuffers(log_file);
        return 1;
    }

    main_module = GetModuleHandleW(NULL);
    if (_wcsicmp(process_name, L"sdl-freerdp.exe") == 0) {
        if (!patch_import(main_module, "USER32.dll", "SetCursor",
                          (uintptr_t)&guarded_set_cursor,
                          &set_cursor_address)) {
            write_log("UU cursor guard initialization failed\r\n");
            if (log_file != INVALID_HANDLE_VALUE)
                FlushFileBuffers(log_file);
            return 1;
        }
        original_set_cursor = (set_cursor_fn)set_cursor_address;
        if (original_set_cursor == NULL) {
            write_log("UU cursor guard initialization failed\r\n");
            if (log_file != INVALID_HANDLE_VALUE)
                FlushFileBuffers(log_file);
            return 1;
        }

        original_set_cursor(fallback_cursor);
        relay = FindWindowW(NULL, L"Ubuntu-Desktop-Relay");
        if (relay != NULL)
            PostMessageW(relay, WM_SETCURSOR, (WPARAM)relay,
                         MAKELPARAM(HTCLIENT, WM_MOUSEMOVE));
        write_active_log("UU relay cursor guard");
    } else if (_wcsicmp(process_name, L"GameViewerServer.exe") == 0) {
        cursor_info_patched = patch_import(
            main_module, "USER32.dll", "GetCursorInfo",
            (uintptr_t)&guarded_get_cursor_info,
            &get_cursor_info_address);
        icon_info_patched = patch_import(
            main_module, "USER32.dll", "GetIconInfo",
            (uintptr_t)&guarded_get_icon_info,
            &get_icon_info_address);
        original_get_cursor_info =
            (get_cursor_info_fn)get_cursor_info_address;
        original_get_icon_info = (get_icon_info_fn)get_icon_info_address;
        streamer_module = GetModuleHandleW(L"streamer.dll");
        streamer_cursor_info_patched =
            streamer_module != NULL &&
            patch_import(streamer_module, "USER32.dll", "GetCursorInfo",
                         (uintptr_t)&guarded_get_cursor_info, NULL);
        streamer_icon_info_patched =
            streamer_module != NULL &&
            patch_import(streamer_module, "USER32.dll", "GetIconInfo",
                         (uintptr_t)&guarded_get_icon_info, NULL);
        if (!cursor_info_patched || !icon_info_patched ||
            !streamer_cursor_info_patched || !streamer_icon_info_patched ||
            original_get_cursor_info == NULL ||
            original_get_icon_info == NULL ||
            !cursor_reader_self_test()) {
            write_log("UU cursor reader guard initialization failed\r\n");
            if (log_file != INVALID_HANDLE_VALUE)
                FlushFileBuffers(log_file);
            return 1;
        }
        write_active_log("UU cursor reader guard");
    } else {
        write_log("UU cursor guard initialization failed\r\n");
        if (log_file != INVALID_HANDLE_VALUE)
            FlushFileBuffers(log_file);
        return 1;
    }

    if (log_file != INVALID_HANDLE_VALUE)
        FlushFileBuffers(log_file);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    HANDLE thread;

    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
        thread = CreateThread(NULL, 0, initialize_guard, NULL, 0, NULL);
        if (thread != NULL)
            CloseHandle(thread);
    } else if (reason == DLL_PROCESS_DETACH &&
               log_file != INVALID_HANDLE_VALUE) {
        CloseHandle(log_file);
        log_file = INVALID_HANDLE_VALUE;
    }
    return TRUE;
}
