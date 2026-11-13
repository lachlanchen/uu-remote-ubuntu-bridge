#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#define INPUT_BRIDGE_MAGIC 0x42525555UL
#define INPUT_BRIDGE_PIPE L"\\\\.\\pipe\\uurb-input-v1"
#define ACCEPTANCE_INPUTS 6UL

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

int main(int argc, char **argv)
{
    input_bridge_request request;
    input_bridge_response response;
    INPUT inputs[ACCEPTANCE_INPUTS];
    HANDLE pipe;

    ZeroMemory(inputs, sizeof(inputs));
    inputs[0].type = INPUT_MOUSE;
    inputs[0].mi.dx = 32768;
    inputs[0].mi.dy = 32768;
    inputs[0].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
    inputs[1].type = INPUT_MOUSE;
    inputs[1].mi.dx = 5;
    inputs[1].mi.dy = 3;
    inputs[1].mi.dwFlags = MOUSEEVENTF_MOVE;
    inputs[2].type = INPUT_MOUSE;
    inputs[2].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
    inputs[3].type = INPUT_MOUSE;
    inputs[3].mi.dwFlags = MOUSEEVENTF_LEFTUP;
    inputs[4].type = INPUT_MOUSE;
    inputs[4].mi.mouseData = WHEEL_DELTA;
    inputs[4].mi.dwFlags = MOUSEEVENTF_WHEEL;
    inputs[5].type = INPUT_MOUSE;
    inputs[5].mi.mouseData = (DWORD)-WHEEL_DELTA;
    inputs[5].mi.dwFlags = MOUSEEVENTF_HWHEEL;

    if (argc == 2) {
        if (!LoadLibraryA(argv[1])) return 2;
        Sleep(500);
        UINT sent = SendInput(ACCEPTANCE_INPUTS, inputs, sizeof(INPUT));
        printf("hooked mouse requested=%lu result=%u\n", ACCEPTANCE_INPUTS, sent);
        return sent == ACCEPTANCE_INPUTS ? 0 : 1;
    }
    if (argc != 1) return 2;

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

    request.magic = INPUT_BRIDGE_MAGIC;
    request.count = ACCEPTANCE_INPUTS;
    request.input_size = sizeof(INPUT);
    if (!write_all(pipe, &request, sizeof(request)) ||
        !write_all(pipe, inputs, sizeof(inputs)) ||
        !read_all(pipe, &response, sizeof(response))) {
        fprintf(stderr, "input broker request failed: %lu\n",
                (unsigned long)GetLastError());
        CloseHandle(pipe);
        return 1;
    }
    CloseHandle(pipe);

    printf("requested=%lu result=%lu error=%lu\n",
           (unsigned long)request.count, (unsigned long)response.result,
           (unsigned long)response.error);
    return response.result == request.count && response.error == 0 ? 0 : 1;
}
