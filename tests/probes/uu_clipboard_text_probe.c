#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define INPUT_BRIDGE_MAGIC 0x42525555UL
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

        if (!ReadFile(handle, position, size, &received, NULL) ||
            received == 0)
            return FALSE;
        position += received;
        size -= received;
    }
    return TRUE;
}

static BOOL send_inputs(HANDLE pipe, const INPUT *inputs, DWORD count)
{
    input_bridge_request request;
    input_bridge_response response;

    request.magic = INPUT_BRIDGE_MAGIC;
    request.count = count;
    request.input_size = sizeof(INPUT);
    if (!write_all(pipe, &request, sizeof(request)) ||
        !write_all(pipe, inputs, count * sizeof(*inputs)) ||
        !read_all(pipe, &response, sizeof(response))) {
        fprintf(stderr, "input broker request failed: %lu\n",
                (unsigned long)GetLastError());
        return FALSE;
    }
    printf("requested=%lu result=%lu error=%lu\n",
           (unsigned long)count, (unsigned long)response.result,
           (unsigned long)response.error);
    return response.result == count && response.error == 0;
}

static void unicode_input_pair(INPUT inputs[2], WCHAR unit)
{
    ZeroMemory(inputs, 2U * sizeof(*inputs));
    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wScan = unit;
    inputs[0].ki.dwFlags = KEYEVENTF_UNICODE;
    inputs[1] = inputs[0];
    inputs[1].ki.dwFlags |= KEYEVENTF_KEYUP;
}

static BOOL send_unicode_text(HANDLE pipe, const WCHAR *text, DWORD length)
{
    INPUT inputs[128];
    DWORD index;

    if (length == 0 || length * 2U > ARRAYSIZE(inputs))
        return FALSE;
    ZeroMemory(inputs, sizeof(inputs));
    for (index = 0; index < length; index++) {
        INPUT *press = &inputs[index * 2U];
        INPUT *release = &inputs[index * 2U + 1U];

        press->type = INPUT_KEYBOARD;
        press->ki.wScan = text[index];
        press->ki.dwFlags = KEYEVENTF_UNICODE;
        *release = *press;
        release->ki.dwFlags |= KEYEVENTF_KEYUP;
    }
    return send_inputs(pipe, inputs, length * 2U);
}

int main(int argc, char **argv)
{
    static const WCHAR text[] = {
        0x4f60, 0x597d, L' ', L'l', L'i', L'n', L'e', L' ', L'o', L'n', L'e',
        L'\r', L'\n', L'l', L'i', L'n', L'e', L' ', L't', L'w', L'o',
        L' ', 0x2018, 0x2019, 0x201c, 0x201d, 0xff01, 0xff1f,
        L'@', L'&', L'?'
    };
    static const WCHAR revised[] = {0x4fee, 0x8ba2, 0x5b8c, 0x6210};
    static const WCHAR symbols[] = {
        0x4e2d, 0x6587, 0xff0c, 0x7b26, 0x53f7, 0xff1a,
        0x2018, 0x2019, 0x201c, 0x201d, 0xff01, 0xff1f,
        L'@', L'&', L'?', 0xd83d, 0xde42
    };
    INPUT inputs[ARRAYSIZE(text) * 2U + 2U];
    INPUT revision[(ARRAYSIZE(text) + ARRAYSIZE(revised)) * 2U];
    INPUT surrogate[2];
    HANDLE pipe;
    DWORD index;

    if (argc > 2 || (argc == 2 && strcmp(argv[1], "symbols") != 0)) {
        fprintf(stderr, "usage: uu-clipboard-text-probe.exe [symbols]\n");
        return 2;
    }

    ZeroMemory(inputs, sizeof(inputs));
    /* Dictation may mix composition editing keys and Unicode replacement text
     * in one SendInput batch. Backspace on an empty editor is harmless here. */
    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wVk = VK_BACK;
    inputs[1] = inputs[0];
    inputs[1].ki.dwFlags = KEYEVENTF_KEYUP;
    for (index = 0; index < ARRAYSIZE(text); index++) {
        INPUT *press = &inputs[index * 2U + 2U];
        INPUT *release = &inputs[index * 2U + 3U];

        press->type = INPUT_KEYBOARD;
        press->ki.wScan = text[index];
        press->ki.dwFlags = KEYEVENTF_UNICODE;
        *release = *press;
        release->ki.dwFlags |= KEYEVENTF_KEYUP;
    }

    if (!WaitNamedPipeW(INPUT_BRIDGE_PIPE, 5000)) {
        fprintf(stderr, "input broker pipe was not ready: %lu\n",
                (unsigned long)GetLastError());
        return 1;
    }
    pipe = CreateFileW(INPUT_BRIDGE_PIPE, GENERIC_READ | GENERIC_WRITE, 0,
                       NULL, OPEN_EXISTING, 0, NULL);
    if (pipe == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "could not open input broker pipe: %lu\n",
                (unsigned long)GetLastError());
        return 1;
    }

    if (argc == 2) {
        BOOL success = send_unicode_text(pipe, symbols, ARRAYSIZE(symbols));

        CloseHandle(pipe);
        return success ? 0 : 1;
    }

    if (!send_inputs(pipe, inputs, ARRAYSIZE(inputs))) {
        CloseHandle(pipe);
        return 1;
    }

    /* U+1F642 SLIGHTLY SMILING FACE split across separate SendInput calls. */
    unicode_input_pair(surrogate, 0xd83d);
    if (!send_inputs(pipe, surrogate, ARRAYSIZE(surrogate))) {
        CloseHandle(pipe);
        return 1;
    }
    unicode_input_pair(surrogate, 0xde42);
    if (!send_inputs(pipe, surrogate, ARRAYSIZE(surrogate))) {
        CloseHandle(pipe);
        return 1;
    }

    ZeroMemory(revision, sizeof(revision));
    /* Replace only the text inserted by this broker client. ARRAYSIZE(text)
     * equals the visible text length after CRLF normalization plus the emoji
     * sent above. The unrelated prefix in the target must remain untouched. */
    for (index = 0; index < ARRAYSIZE(text); index++) {
        INPUT *press = &revision[index * 2U];
        INPUT *release = &revision[index * 2U + 1U];

        press->type = INPUT_KEYBOARD;
        press->ki.wVk = VK_BACK;
        *release = *press;
        release->ki.dwFlags = KEYEVENTF_KEYUP;
    }
    for (index = 0; index < ARRAYSIZE(revised); index++) {
        DWORD offset = ARRAYSIZE(text) * 2U + index * 2U;
        INPUT *press = &revision[offset];
        INPUT *release = &revision[offset + 1U];

        press->type = INPUT_KEYBOARD;
        press->ki.wScan = revised[index];
        press->ki.dwFlags = KEYEVENTF_UNICODE;
        *release = *press;
        release->ki.dwFlags |= KEYEVENTF_KEYUP;
    }
    if (!send_inputs(pipe, revision, ARRAYSIZE(revision))) {
        CloseHandle(pipe);
        return 1;
    }
    CloseHandle(pipe);
    return 0;
}
