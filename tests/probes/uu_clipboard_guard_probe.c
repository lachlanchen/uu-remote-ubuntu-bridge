#define UURB_CLIPBOARD_GUARD_TEST
#include <windows.h>
static void *probe_caller;
static void *probe_frame;
static USHORT probe_stack(DWORD skip, DWORD count, void **frames, DWORD *hash)
{
    (void)skip;
    (void)hash;
    if (!count || !probe_frame)
        return 0;
    frames[0] = probe_frame;
    return 1;
}
#undef CaptureStackBackTrace
#define CaptureStackBackTrace probe_stack
#define __builtin_return_address(n) probe_caller
#include "../../src/uu_clipboard_guard.c"

static HANDLE fixture;
static HANDLE WINAPI fixture_data(UINT format)
{
    return format == CF_UNICODETEXT ? fixture : NULL;
}

static void set_fixture(const WCHAR *text, SIZE_T bytes)
{
    void *destination;
    if (fixture)
        GlobalFree(fixture);
    fixture = GlobalAlloc(GMEM_MOVEABLE, bytes);
    destination = GlobalLock(fixture);
    memcpy(destination, text, bytes);
    GlobalUnlock(fixture);
}

struct read_result {
    char text[256];
    int bytes;
    DWORD thread;
};

static DWORD WINAPI read_on_worker(void *argument)
{
    struct read_result *result = argument;
    HGLOBAL snapshot;
    const char *text;
    result->thread = GetCurrentThreadId();
    if (!OpenClipboard(NULL))
        return 40;
    snapshot = guarded_data(CF_TEXT);
    if (!snapshot || TlsGetValue(scratch_slot) != snapshot)
        return 41;
    result->bytes = (int)GlobalSize(snapshot);
    text = GlobalLock(snapshot);
    if (!text || result->bytes > (int)sizeof(result->text))
        return 42;
    memcpy(result->text, text, result->bytes);
    GlobalUnlock(snapshot);
    if (!guarded_close() || TlsGetValue(scratch_slot))
        return 43;
    return 0;
}

static int collect_on_worker(struct read_result *result)
{
    DWORD status;
    HANDLE worker = CreateThread(NULL, 0, read_on_worker, result, 0, NULL);
    if (!worker || WaitForSingleObject(worker, 10000) != WAIT_OBJECT_0 ||
        !GetExitCodeThread(worker, &status))
        return 44;
    CloseHandle(worker);
    return status || result->thread == GetCurrentThreadId() ? 45 : 0;
}

int main(void)
{
    static const WCHAR text[] = L"中文测试 日本語 😀 “引号”\r\nsecond line";
    static const char expected[] = "中文测试 日本語 😀 “引号”\r\nsecond line";
    static const WCHAR second[] = L"第二条 ' @ 😀";
    const WCHAR invalid[] = {0xd800, 0};
    const WCHAR unterminated[] = {L'a', L'b'};
    WCHAR *large;
    HGLOBAL snapshot;
    char *utf8;
    BYTE header[8192] = {0};
    void *frames[2];
    HWND owner;
    HANDLE native;
    WCHAR decoded[128];
    struct read_result first_read, second_read;
    int units;
    (void)initialize_guard; /* Test the same implementation without DLL entry. */

    original_data = fixture_data;
    set_fixture(text, sizeof(text));
    snapshot = unicode_snapshot();
    if (!snapshot)
        return 10;
    utf8 = GlobalLock(snapshot);
    if (!utf8 || strcmp(utf8, expected) || GlobalSize(snapshot) != sizeof(expected))
        return 11;
    GlobalUnlock(snapshot);
    GlobalFree(snapshot);
    set_fixture(invalid, sizeof(invalid));
    if (unicode_snapshot())
        return 12;
    set_fixture(unterminated, sizeof(unterminated));
    if (unicode_snapshot())
        return 13;
    large = calloc(MAX_UTF8_BYTES + 2, sizeof(WCHAR));
    if (!large)
        return 14;
    for (unsigned i = 0; i < MAX_UTF8_BYTES + 1; i++)
        large[i] = L'x';
    set_fixture(large, (MAX_UTF8_BYTES + 2) * sizeof(WCHAR));
    if (unicode_snapshot())
        return 15;
    /* Under the UTF-16 limit but over the UTF-8 limit must also be rejected. */
    for (unsigned i = 0; i < MAX_UTF8_BYTES / 2; i++)
        large[i] = 0x4e2d;
    large[MAX_UTF8_BYTES / 2] = 0;
    set_fixture(large, (MAX_UTF8_BYTES / 2 + 1) * sizeof(WCHAR));
    if (unicode_snapshot())
        return 16;
    free(large);
    GlobalFree(fixture);
    fixture = NULL;

    image = (BYTE *)0x140000000;
    frames[0] = image + EXPORT_RETURN_RVA;
    frames[1] = image + 0x1000;
    if (!export_context(image + DATA_RETURN_RVA, frames, 2) ||
        export_context(image + DATA_RETURN_RVA + 1, frames, 2) ||
        export_context(image + DATA_RETURN_RVA, frames + 1, 1))
        return 20;
    frames[0] = image + DECODE_RETURN_RVA;
    if (!decode_context(CP_ACP, image + 0x1a2b6d3, frames, 2) ||
        !decode_context(CP_ACP, image + 0x1a2b710, frames, 2) ||
        decode_context(CP_UTF8, image + 0x1a2b710, frames, 2) ||
        decode_context(CP_ACP, image + 0x1a2b710, frames + 1, 1) ||
        decode_context(CP_ACP, image + 0x1234, frames, 2))
        return 23;
    image = NULL;
    if (export_context((void *)DATA_RETURN_RVA, frames, 2) || supported_image(header))
        return 21;
    ((IMAGE_DOS_HEADER *)header)->e_magic = IMAGE_DOS_SIGNATURE;
    ((IMAGE_DOS_HEADER *)header)->e_lfanew = 128;
    ((IMAGE_NT_HEADERS *)(header + 128))->Signature = IMAGE_NT_SIGNATURE;
    if (supported_image(header))
        return 22;

    original_data = GetClipboardData;
    original_close = CloseClipboard;
    original_multibyte = MultiByteToWideChar;
    scratch_slot = TlsAlloc();
    owner = CreateWindowExW(0, L"STATIC", L"isolated clipboard guard probe", 0,
                            0, 0, 0, 0, HWND_MESSAGE, NULL, NULL, NULL);
    if (!owner || scratch_slot == TLS_OUT_OF_INDEXES || !OpenClipboard(owner) ||
        !EmptyClipboard())
        return 30;
    native = GlobalAlloc(GMEM_MOVEABLE, sizeof(text));
    memcpy(GlobalLock(native), text, sizeof(text));
    GlobalUnlock(native);
    if (!SetClipboardData(CF_UNICODETEXT, native))
        return 31;
    /* This caller is outside the audited export: normal ANSI remains normal. */
    if (guarded_data(CF_TEXT) != GetClipboardData(CF_TEXT) ||
        guarded_data(CF_UNICODETEXT) != GetClipboardData(CF_UNICODETEXT))
        return 32;
    CloseClipboard();
    image = (BYTE *)0x140000000;
    probe_caller = image + DATA_RETURN_RVA;
    probe_frame = image + EXPORT_RETURN_RVA;
    if (collect_on_worker(&first_read) || strcmp(first_read.text, expected) ||
        !matching_export(first_read.text, first_read.bytes))
        return 33;
    /* Queue another copy BEFORE the first is decoded. The callback runs on
     * a different thread and may consume copies out of order. */
    if (!OpenClipboard(owner) || !EmptyClipboard())
        return 34;
    native = GlobalAlloc(GMEM_MOVEABLE, sizeof(second));
    memcpy(GlobalLock(native), second, sizeof(second));
    GlobalUnlock(native);
    if (!SetClipboardData(CF_UNICODETEXT, native) || !CloseClipboard() ||
        collect_on_worker(&second_read))
        return 35;
    probe_frame = image + DECODE_RETURN_RVA;
    probe_caller = image + 0x1a2b6d3;
    /* Context alone must not reinterpret arbitrary ANSI bytes as UTF-8. */
    if (guarded_multibyte(CP_ACP, 0, "\xc3\xa9", 2, NULL, 0) !=
        MultiByteToWideChar(CP_ACP, 0, "\xc3\xa9", 2, NULL, 0))
        return 36;
    for (unsigned i = 0; i < 2; i++) {
        struct read_result *read = i == 0 ? &second_read : &first_read;
        const WCHAR *wanted = i == 0 ? second : text;
        probe_caller = image + 0x1a2b6d3;
        units = guarded_multibyte(CP_ACP, 0, read->text, read->bytes, NULL, 0);
        if (units != (int)wcslen(wanted) + 1 || !matching_export(read->text, read->bytes))
            return 37;
        probe_caller = image + 0x1a2b710;
        if (guarded_multibyte(CP_ACP, 0, read->text, read->bytes, decoded, 128) != units ||
            wcscmp(decoded, wanted) || matching_export(read->text, read->bytes))
            return 38;
    }
    /* No pending export: retain native ACP behavior even at this call site. */
    if (guarded_multibyte(CP_ACP, 0, first_read.text, first_read.bytes, NULL, 0) !=
        MultiByteToWideChar(CP_ACP, 0, first_read.text, first_read.bytes, NULL, 0))
        return 39;
    snapshot = GlobalAlloc(GMEM_MOVEABLE, sizeof(expected));
    memcpy(GlobalLock(snapshot), expected, sizeof(expected));
    GlobalUnlock(snapshot);
    for (unsigned i = 0; i < PENDING_EXPORTS; i++)
        if (!remember_export(snapshot))
            return 50;
    if (remember_export(snapshot))
        return 51;
    pending[0].created = GetTickCount64() - PENDING_MILLISECONDS - 1;
    if (!remember_export(snapshot))
        return 52;
    for (unsigned i = 0; i < PENDING_EXPORTS; i++)
        clear_pending(&pending[i]);
    GlobalFree(snapshot);
    DestroyWindow(owner);
    TlsFree(scratch_slot);
    puts("PASS: cross-thread queued copies, out-of-order decode, exact matching, bounds, call-site isolation and lifetime");
    return 0;
}
