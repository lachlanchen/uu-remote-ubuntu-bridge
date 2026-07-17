#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winevt.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef UINT(WINAPI *send_input_fn)(UINT, LPINPUT, int);

#define INPUT_BRIDGE_MAGIC 0x42525555UL
#define INPUT_BRIDGE_MAX_INPUTS 64UL
#define INPUT_BRIDGE_PIPE L"\\\\.\\pipe\\uurb-input-v1"

typedef struct input_bridge_request {
    DWORD magic;
    DWORD count;
    DWORD input_size;
} input_bridge_request;

typedef struct input_bridge_response {
    DWORD result;
    DWORD error;
} input_bridge_response;

static send_input_fn original_send_input;
static HANDLE log_file = INVALID_HANDLE_VALUE;
static HANDLE broker_pipe = INVALID_HANDLE_VALUE;
static CRITICAL_SECTION broker_lock;
static BOOL broker_lock_initialized;
static volatile LONG input_call_count;
static volatile LONG routine_call_count;
static volatile LONG text_call_count;

static EVT_HANDLE WINAPI safe_evt_open_publisher_metadata(
    EVT_HANDLE session, LPCWSTR publisher_identity, LPCWSTR log_file_path,
    LCID locale, DWORD flags)
{
    (void)session;
    (void)publisher_identity;
    (void)log_file_path;
    (void)locale;
    (void)flags;

    SetLastError(ERROR_EVT_PUBLISHER_METADATA_NOT_FOUND);
    return NULL;
}

static void write_log(const char *message)
{
    DWORD written;

    if (log_file == INVALID_HANDLE_VALUE)
        return;

    WriteFile(log_file, message, (DWORD)strlen(message), &written, NULL);
}

static void flush_log(void)
{
    if (log_file != INVALID_HANDLE_VALUE)
        FlushFileBuffers(log_file);
}

static void open_log(void)
{
    wchar_t path[MAX_PATH];
    DWORD length;

    length = GetEnvironmentVariableW(L"UU_INPUT_BRIDGE_LOG", path, MAX_PATH);
    if (length == 0 || length >= MAX_PATH) {
        length = GetTempPathW(MAX_PATH, path);
        if (length == 0 || length >= MAX_PATH - 20)
            lstrcpynW(path, L"uu-input-bridge.log", MAX_PATH);
        else
            lstrcatW(path, L"uu-input-bridge.log");
    }

    log_file = CreateFileW(path, FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
}

static HWND find_relay_window(void)
{
    return FindWindowW(NULL, L"Ubuntu-Desktop-Relay");
}

static BOOL write_all(HANDLE handle, const void *buffer, DWORD size)
{
    const BYTE *position = (const BYTE *)buffer;

    while (size > 0) {
        DWORD written = 0;

        if (!WriteFile(handle, position, size, &written, NULL) || written == 0)
            return FALSE;
        position += written;
        size -= written;
    }

    return TRUE;
}

static BOOL read_all(HANDLE handle, void *buffer, DWORD size)
{
    BYTE *position = (BYTE *)buffer;

    while (size > 0) {
        DWORD received = 0;

        if (!ReadFile(handle, position, size, &received, NULL) || received == 0)
            return FALSE;
        position += received;
        size -= received;
    }

    return TRUE;
}

static void disconnect_broker(void)
{
    if (broker_pipe != INVALID_HANDLE_VALUE) {
        CloseHandle(broker_pipe);
        broker_pipe = INVALID_HANDLE_VALUE;
    }
}

static BOOL connect_broker(void)
{
    if (broker_pipe != INVALID_HANDLE_VALUE)
        return TRUE;

    if (!WaitNamedPipeW(INPUT_BRIDGE_PIPE, 500))
        return FALSE;

    broker_pipe = CreateFileW(INPUT_BRIDGE_PIPE, GENERIC_READ | GENERIC_WRITE,
                              0, NULL, OPEN_EXISTING, 0, NULL);
    return broker_pipe != INVALID_HANDLE_VALUE;
}

static UINT send_through_broker(UINT count, const INPUT *inputs, int size,
                                DWORD *broker_error)
{
    input_bridge_request request;
    input_bridge_response response;
    UINT result = 0;
    int attempt;

    *broker_error = ERROR_ACCESS_DENIED;
    if (!broker_lock_initialized || count == 0 || inputs == NULL ||
        count > INPUT_BRIDGE_MAX_INPUTS || size != (int)sizeof(INPUT))
        return 0;

    request.magic = INPUT_BRIDGE_MAGIC;
    request.count = count;
    request.input_size = (DWORD)size;

    EnterCriticalSection(&broker_lock);
    for (attempt = 0; attempt < 2; attempt++) {
        if (connect_broker() &&
            write_all(broker_pipe, &request, sizeof(request)) &&
            write_all(broker_pipe, inputs, count * sizeof(INPUT)) &&
            read_all(broker_pipe, &response, sizeof(response))) {
            result = response.result;
            *broker_error = response.error;
            break;
        }
        disconnect_broker();
    }
    LeaveCriticalSection(&broker_lock);
    return result;
}

static BOOL contains_unicode_keyboard(UINT count, const INPUT *inputs, int size)
{
    UINT index;

    if (count == 0 || inputs == NULL || size != (int)sizeof(INPUT))
        return FALSE;

    for (index = 0; index < count; index++) {
        if (inputs[index].type == INPUT_KEYBOARD &&
            (inputs[index].ki.dwFlags & KEYEVENTF_UNICODE) != 0)
            return TRUE;
    }

    return FALSE;
}

static UINT WINAPI bridged_send_input(UINT count, LPINPUT inputs, int size)
{
    char line[256];
    HWND relay;
    UINT result;
    DWORD error;
    LONG call_number;
    DWORD first_type = UINT32_MAX;
    DWORD first_flags = 0;
    BOOL used_broker = FALSE;
    BOOL unicode_keyboard;
    LONG category_call_number;

    relay = find_relay_window();
    if (relay != NULL)
        SetForegroundWindow(relay);

    if (count > 0 && inputs != NULL && size == (int)sizeof(INPUT)) {
        first_type = inputs[0].type;
        if (first_type == INPUT_MOUSE)
            first_flags = inputs[0].mi.dwFlags;
        else if (first_type == INPUT_KEYBOARD)
            first_flags = inputs[0].ki.dwFlags;
    }

    unicode_keyboard = contains_unicode_keyboard(count, inputs, size);
    if (unicode_keyboard) {
        result = send_through_broker(count, inputs, size, &error);
        used_broker = TRUE;
        SetLastError(error);
    } else {
        SetLastError(ERROR_SUCCESS);
        result = original_send_input(count, inputs, size);
        error = GetLastError();
        if (result != count) {
            result = send_through_broker(count, inputs, size, &error);
            used_broker = TRUE;
            SetLastError(error);
        }
    }
    call_number = InterlockedIncrement(&input_call_count);
    category_call_number = InterlockedIncrement(
        unicode_keyboard ? &text_call_count : &routine_call_count);

    if ((unicode_keyboard && category_call_number <= 256) ||
        (!unicode_keyboard && category_call_number <= 64) ||
        result != count) {
        _snprintf(line, sizeof(line),
                  "call=%ld category-call=%ld count=%lu type=%lu flags=0x%08lx route=%s result=%lu error=%lu\r\n",
                  call_number, category_call_number, (unsigned long)count,
                  (unsigned long)first_type, (unsigned long)first_flags,
                  used_broker ? "broker" : "direct",
                  (unsigned long)result, (unsigned long)error);
        line[sizeof(line) - 1] = '\0';
        write_log(line);
        if (result != count)
            flush_log();
    }

    return result;
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

static DWORD WINAPI initialize_bridge(void *unused)
{
    uintptr_t send_input_address = 0;
    BOOL input_patched;
    BOOL event_log_patched;

    (void)unused;
    open_log();
    InitializeCriticalSection(&broker_lock);
    broker_lock_initialized = TRUE;
    input_patched = patch_import(
        GetModuleHandleW(NULL), "USER32.dll", "SendInput",
        (uintptr_t)&bridged_send_input, &send_input_address);
    original_send_input = (send_input_fn)send_input_address;
    event_log_patched = patch_import(
        GetModuleHandleW(NULL), "wevtapi.dll", "EvtOpenPublisherMetadata",
        (uintptr_t)&safe_evt_open_publisher_metadata, NULL);

    write_log(input_patched ? "UU SendInput bridge active\r\n"
                            : "UU bridge could not find SendInput import\r\n");
    write_log(event_log_patched
                  ? "UU Wine event-log compatibility active\r\n"
                  : "UU bridge could not find event-log import\r\n");
    flush_log();
    return input_patched && event_log_patched ? 0 : 1;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    HANDLE thread;

    (void)reserved;

    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
        thread = CreateThread(NULL, 0, initialize_bridge, NULL, 0, NULL);
        if (thread != NULL)
            CloseHandle(thread);
    } else if (reason == DLL_PROCESS_DETACH) {
        disconnect_broker();
        if (broker_lock_initialized) {
            DeleteCriticalSection(&broker_lock);
            broker_lock_initialized = FALSE;
        }
        if (log_file != INVALID_HANDLE_VALUE) {
            CloseHandle(log_file);
            log_file = INVALID_HANDLE_VALUE;
        }
    }

    return TRUE;
}
