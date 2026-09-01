#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

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

int main(void)
{
    static const WCHAR text[] = {
        0x4f60, 0x597d, L' ', L'l', L'i', L'n', L'e', L' ', L'o', L'n', L'e',
        L'\r', L'\n', L'l', L'i', L'n', L'e', L' ', L't', L'w', L'o'
    };
    INPUT inputs[ARRAYSIZE(text) * 2U];
    INPUT surrogate[2];
    HANDLE pipe;
    DWORD index;

    ZeroMemory(inputs, sizeof(inputs));
    for (index = 0; index < ARRAYSIZE(text); index++) {
        INPUT *press = &inputs[index * 2U];
        INPUT *release = &inputs[index * 2U + 1U];

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
    CloseHandle(pipe);
    return 0;
}
