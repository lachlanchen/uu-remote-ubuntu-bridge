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
    const BYTE *position = buffer;

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
    BYTE *position = buffer;

    while (size > 0) {
        DWORD received = 0;

        if (!ReadFile(handle, position, size, &received, NULL) || received == 0)
            return FALSE;
        position += received;
        size -= received;
    }
    return TRUE;
}

int main(void)
{
    static const WCHAR text[] = {
        L'U', L'U', L' ', L'b', L'r', L'o', L'k', L'e', L'r', L' ',
        0x4e2d, 0x6587, L' ', L'1', L'2', L'3'
    };
    INPUT inputs[ARRAYSIZE(text) * 2U];
    input_bridge_request request;
    input_bridge_response response;
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
    if (!WaitNamedPipeW(INPUT_BRIDGE_PIPE, 5000))
        return 2;
    pipe = CreateFileW(INPUT_BRIDGE_PIPE, GENERIC_READ | GENERIC_WRITE, 0,
                       NULL, OPEN_EXISTING, 0, NULL);
    if (pipe == INVALID_HANDLE_VALUE)
        return 3;
    request.magic = INPUT_BRIDGE_MAGIC;
    request.count = ARRAYSIZE(inputs);
    request.input_size = sizeof(INPUT);
    if (!write_all(pipe, &request, sizeof(request)) ||
        !write_all(pipe, inputs, sizeof(inputs)) ||
        !read_all(pipe, &response, sizeof(response))) {
        CloseHandle(pipe);
        return 4;
    }
    CloseHandle(pipe);
    printf("requested=%lu result=%lu error=%lu\n",
           (unsigned long)request.count, (unsigned long)response.result,
           (unsigned long)response.error);
    return response.result == request.count && response.error == 0 ? 0 : 5;
}
