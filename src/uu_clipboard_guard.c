/* UU 4.44.1.3978 mobile text export asks for CF_TEXT even when Unicode is
 * available. Convert only that audited export to UTF-8; never redefine the
 * system clipboard's ANSI format or affect incoming text / keyboard input. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define MAX_UTF8_BYTES 61440U
#define EXPORT_RETURN_RVA 0xf72d69U
#define DATA_RETURN_RVA 0xf71493U
/* The conversion runs later through Qt's queued callback, after the clipboard
 * reader returned. The reader's original stack is no longer present here. */
#define DECODE_RETURN_RVA 0x2dc72bU

static HANDLE (WINAPI *original_data)(UINT);
static BOOL (WINAPI *original_close)(void);
static int (WINAPI *original_multibyte)(UINT, DWORD, LPCCH, int, LPWSTR, int);
static BYTE *image;
static DWORD scratch_slot = TLS_OUT_OF_INDEXES;
static DWORD utf8_slot = TLS_OUT_OF_INDEXES;
static HANDLE log_handle = INVALID_HANDLE_VALUE;
static SRWLOCK log_lock = SRWLOCK_INIT;
static volatile LONG report_count;

static void report(const char *message)
{
    DWORD saved = GetLastError(), written;
    if (InterlockedIncrement(&report_count) <= 32 &&
        log_handle != INVALID_HANDLE_VALUE) {
        AcquireSRWLockExclusive(&log_lock);
        WriteFile(log_handle, message, (DWORD)strlen(message), &written, NULL);
        ReleaseSRWLockExclusive(&log_lock);
    }
    SetLastError(saved);
}

static BOOL export_context(void *caller, void **frames, USHORT count)
{
    USHORT index;
    if (!image || caller != image + DATA_RETURN_RVA)
        return FALSE;
    for (index = 0; index < count; index++)
        if (frames[index] == image + EXPORT_RETURN_RVA)
            return TRUE;
    return FALSE;
}

static BOOL decode_context(UINT codepage, void *caller, void **frames, USHORT count)
{
    USHORT index;
    if (!image || codepage != CP_ACP ||
        (caller != image + 0x1a2b6d3 && caller != image + 0x1a2b710))
        return FALSE;
    for (index = 0; index < count; index++)
        if (frames[index] == image + DECODE_RETURN_RVA)
            return TRUE;
    return FALSE;
}

static int WINAPI guarded_multibyte(UINT codepage, DWORD flags, LPCCH text,
                                     int bytes, LPWSTR output, int capacity)
{
    void *frames[32];
    BOOL converted = FALSE;
    int result;
    if (codepage == CP_ACP && utf8_slot != TLS_OUT_OF_INDEXES &&
        TlsGetValue(utf8_slot)) {
        USHORT count = CaptureStackBackTrace(0, 32, frames, NULL);
        if (decode_context(codepage, __builtin_return_address(0), frames, count)) {
            codepage = CP_UTF8;
            converted = TRUE;
        }
    }
    result = original_multibyte(codepage, flags, text, bytes, output, capacity);
    if (converted && output && capacity > 0) {
        DWORD saved = GetLastError();
        TlsSetValue(utf8_slot, NULL);
        report("mobile-clipboard result=decoded encoding=utf8\r\n");
        SetLastError(saved);
    }
    return result;
}

/* Caller owns the returned allocation. Invalid/oversized Unicode is never
 * partially converted, and the original clipboard allocation is not changed. */
static HGLOBAL unicode_snapshot(void)
{
    HANDLE source = original_data(CF_UNICODETEXT);
    SIZE_T allocation, units = 0;
    const WCHAR *wide;
    HGLOBAL result = NULL;
    char *utf8;
    int bytes;

    if (!source)
        return NULL;
    allocation = GlobalSize(source);
    if (allocation < sizeof(WCHAR) || allocation % sizeof(WCHAR) ||
        allocation > (MAX_UTF8_BYTES + 1) * sizeof(WCHAR))
        return NULL;
    wide = GlobalLock(source);
    if (!wide)
        return NULL;
    while (units < allocation / sizeof(WCHAR) && wide[units])
        units++;
    if (units == 0 || units == allocation / sizeof(WCHAR))
        goto done;
    bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide,
                                (int)units, NULL, 0, NULL, NULL);
    if (bytes <= 0 || bytes > (int)MAX_UTF8_BYTES)
        goto done;
    result = GlobalAlloc(GMEM_MOVEABLE, (SIZE_T)bytes + 1);
    if (!result)
        goto done;
    utf8 = GlobalLock(result);
    if (!utf8) {
        GlobalFree(result);
        result = NULL;
        goto done;
    }
    if (WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, (int)units,
                             utf8, bytes, NULL, NULL) != bytes) {
        GlobalUnlock(result);
        GlobalFree(result);
        result = NULL;
        goto done;
    }
    utf8[bytes] = 0;
    GlobalUnlock(result);
done:
    GlobalUnlock(source);
    return result;
}

static HANDLE WINAPI guarded_data(UINT format)
{
    void *frames[16];
    USHORT count;
    HANDLE scratch;
    if (format != CF_TEXT || scratch_slot == TLS_OUT_OF_INDEXES)
        return original_data(format);
    count = CaptureStackBackTrace(0, 16, frames, NULL);
    if (!export_context(__builtin_return_address(0), frames, count))
        return original_data(format);
    TlsSetValue(utf8_slot, NULL);
    scratch = TlsGetValue(scratch_slot);
    if (scratch) {
        TlsSetValue(utf8_slot, (void *)1);
        return scratch;
    }
    scratch = unicode_snapshot();
    if (!scratch || !TlsSetValue(scratch_slot, scratch)) {
        if (scratch)
            GlobalFree(scratch);
        report("mobile-clipboard result=fallback reason=unicode-unavailable\r\n");
        return original_data(format);
    }
    TlsSetValue(utf8_slot, (void *)1);
    report("mobile-clipboard result=exported encoding=utf8\r\n");
    return scratch;
}

static BOOL WINAPI guarded_close(void)
{
    BOOL result = original_close();
    DWORD saved = GetLastError();
    if (result && scratch_slot != TLS_OUT_OF_INDEXES) {
        HANDLE scratch = TlsGetValue(scratch_slot);
        if (scratch) {
            TlsSetValue(scratch_slot, NULL);
            GlobalFree(scratch);
        }
    }
    SetLastError(saved);
    return result;
}

/* Reviewed unmodified GameViewer.exe SHA256:
 * 35d8f6bd659870e432a9f80facc964bcead0d5dc42b6170bd12ebc52790a5c08
 * Check PE metadata AND the actual call sites. Unknown versions are left alone. */
static BOOL supported_image(BYTE *base)
{
    static const BYTE priority[] = {
        0xc7,0x44,0x24,0x30,1,0,0,0,0xba,1,0,0,0,
        0x48,0x8d,0x4c,0x24,0x30,0xff,0x15,0x6c,0xdd,0x60,3,0x83,0xf8,1
    };
    static const BYTE export_call[] = {
        0xba,1,0,0,0,0xe8,0xff,0x20,0x0d,0xff,0x84,0xc0,0x74,0x24,0x48,0x83
    };
    static const BYTE data_call[] = {0x8b,0xce,0xff,0x15,0xc5,0xf5,0x60,3};
    static const BYTE decode_call[] = {
        0x45,0x33,0xc0,0x48,0x8d,0x55,0xd7,0x48,0x8d,0x4d,0x07,
        0xe8,0x52,0x67,0xdc,0xff
    };
    IMAGE_DOS_HEADER *dos = (void *)base;
    IMAGE_NT_HEADERS *nt;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0 ||
        dos->e_lfanew > 4096)
        return FALSE;
    nt = (void *)(base + dos->e_lfanew);
    return nt->Signature == IMAGE_NT_SIGNATURE &&
        nt->FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64 &&
        nt->OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC &&
        nt->FileHeader.TimeDateStamp == 0x6ad9f0ae &&
        nt->OptionalHeader.SizeOfImage == 0x4673000 &&
        !memcmp(base + 0xf72cfc, priority, sizeof(priority)) &&
        !memcmp(base + 0xf72d5f, export_call, sizeof(export_call)) &&
        !memcmp(base + 0xf7148b, data_call, sizeof(data_call)) &&
        !memcmp(base + 0x2dc71b, decode_call, sizeof(decode_call)) &&
        !memcmp(base + 0x1a2b6cd, "\xff\x15\x65\xe0\xb4\x02", 6) &&
        !memcmp(base + 0x1a2b70a, "\xff\x15\x28\xe0\xb4\x02", 6);
}

static PVOID volatile *import_slot(const char *dll_name, const char *name)
{
    IMAGE_NT_HEADERS *nt = (void *)(image + ((IMAGE_DOS_HEADER *)image)->e_lfanew);
    DWORD rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    IMAGE_IMPORT_DESCRIPTOR *descriptor;
    if (!rva)
        return NULL;
    descriptor = (void *)(image + rva);
    for (; descriptor->Name; descriptor++) {
        IMAGE_THUNK_DATA *names, *addresses;
        if (_stricmp((char *)image + descriptor->Name, dll_name) ||
            !descriptor->OriginalFirstThunk)
            continue;
        names = (void *)(image + descriptor->OriginalFirstThunk);
        addresses = (void *)(image + descriptor->FirstThunk);
        for (; names->u1.AddressOfData; names++, addresses++) {
            IMAGE_IMPORT_BY_NAME *entry;
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal))
                continue;
            entry = (void *)(image + names->u1.AddressOfData);
            if (!strcmp((char *)entry->Name, name))
                return (PVOID volatile *)&addresses->u1.Function;
        }
    }
    return NULL;
}

static BOOL exchange_slot(PVOID volatile *slot, void *replacement)
{
    DWORD protection;
    if (!VirtualProtect((void *)slot, sizeof(void *), PAGE_READWRITE, &protection))
        return FALSE;
    InterlockedExchangePointer(slot, replacement);
    VirtualProtect((void *)slot, sizeof(void *), protection, &protection);
    return TRUE;
}

static DWORD WINAPI initialize_guard(void *unused)
{
    wchar_t executable[MAX_PATH], path[MAX_PATH];
    wchar_t *basename;
    DWORD length;
    PVOID volatile *data_slot, *close_slot, *multibyte_slot;
    void *previous_close, *previous_multibyte;
    (void)unused;
    length = GetModuleFileNameW(NULL, executable, MAX_PATH);
    if (!length || length >= MAX_PATH)
        return 1;
    basename = wcsrchr(executable, L'\\');
    basename = basename ? basename + 1 : executable;
    if (_wcsicmp(basename, L"GameViewer.exe"))
        return 1;
    length = GetTempPathW(MAX_PATH, path);
    if (length && length < MAX_PATH - 24) {
        lstrcatW(path, L"uu-clipboard-guard.log");
        log_handle = CreateFileW(path, FILE_APPEND_DATA,
                                 FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                                 OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    }
    image = (BYTE *)GetModuleHandleW(NULL);
    if (!supported_image(image)) {
        report("mobile-clipboard result=skipped reason=unreviewed-build\r\n");
        return 1;
    }
    data_slot = import_slot("USER32.dll", "GetClipboardData");
    close_slot = import_slot("USER32.dll", "CloseClipboard");
    multibyte_slot = import_slot("KERNEL32.dll", "MultiByteToWideChar");
    if (!data_slot || !close_slot || !multibyte_slot ||
        (scratch_slot = TlsAlloc()) == TLS_OUT_OF_INDEXES ||
        (utf8_slot = TlsAlloc()) == TLS_OUT_OF_INDEXES)
        return 1;
    /* Capture originals before installing either pointer. Preserve other
     * shims; the deployment verifier requires a fresh process's receipt. */
    memcpy(&original_data, (void *)data_slot, sizeof(original_data));
    memcpy(&original_close, (void *)close_slot, sizeof(original_close));
    memcpy(&original_multibyte, (void *)multibyte_slot, sizeof(original_multibyte));
    previous_close = (void *)*close_slot;
    previous_multibyte = (void *)*multibyte_slot;
    if (!exchange_slot(close_slot, guarded_close))
        return 1;
    if (!exchange_slot(multibyte_slot, guarded_multibyte)) {
        exchange_slot(close_slot, previous_close);
        return 1;
    }
    if (!exchange_slot(data_slot, guarded_data)) {
        exchange_slot(multibyte_slot, previous_multibyte);
        exchange_slot(close_slot, previous_close);
        return 1;
    }
    {
        char message[128];
        snprintf(message, sizeof(message),
                 "mobile-clipboard result=ready pid=%lu build=4.44.1.3978\r\n",
                 GetCurrentProcessId());
        report(message);
    }
    return 0;
}

#ifndef UURB_CLIPBOARD_GUARD_TEST
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        HANDLE worker;
        DisableThreadLibraryCalls(instance);
        worker = CreateThread(NULL, 0, initialize_guard, NULL, 0, NULL);
        if (worker)
            CloseHandle(worker);
    }
    return TRUE;
}
#endif
