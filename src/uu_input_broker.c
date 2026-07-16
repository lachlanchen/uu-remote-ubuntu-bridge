#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

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

static HANDLE log_file = INVALID_HANDLE_VALUE;
static volatile LONG input_call_count;

static void write_log(const char *message)
{
    DWORD written;

    if (log_file == INVALID_HANDLE_VALUE)
        return;
    WriteFile(log_file, message, (DWORD)strlen(message), &written, NULL);
    FlushFileBuffers(log_file);
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

static void serve_client(HANDLE pipe)
{
    for (;;) {
        input_bridge_request request;
        input_bridge_response response;
        INPUT inputs[INPUT_BRIDGE_MAX_INPUTS];
        HWND relay;
        char line[256];
        DWORD first_type = (DWORD)-1;
        DWORD first_flags = 0;
        LONG call_number;

        if (!read_all(pipe, &request, sizeof(request)))
            return;
        if (request.magic != INPUT_BRIDGE_MAGIC || request.count == 0 ||
            request.count > INPUT_BRIDGE_MAX_INPUTS ||
            request.input_size != sizeof(INPUT))
            return;
        if (!read_all(pipe, inputs, request.count * sizeof(INPUT)))
            return;

        relay = FindWindowW(NULL, L"Ubuntu-Desktop-Relay");
        if (relay != NULL) {
            SetForegroundWindow(relay);
            SetFocus(relay);
        }

        SetLastError(ERROR_SUCCESS);
        response.result = SendInput(request.count, inputs, sizeof(INPUT));
        response.error = GetLastError();
        first_type = inputs[0].type;
        if (first_type == INPUT_MOUSE)
            first_flags = inputs[0].mi.dwFlags;
        else if (first_type == INPUT_KEYBOARD)
            first_flags = inputs[0].ki.dwFlags;
        call_number = InterlockedIncrement(&input_call_count);
        if (call_number <= 500 || response.result != request.count) {
            _snprintf(
                line, sizeof(line),
                "call=%ld count=%lu type=%lu flags=0x%08lx result=%lu error=%lu\r\n",
                call_number, (unsigned long)request.count,
                (unsigned long)first_type, (unsigned long)first_flags,
                (unsigned long)response.result,
                (unsigned long)response.error);
            line[sizeof(line) - 1] = '\0';
            write_log(line);
        }
        if (!write_all(pipe, &response, sizeof(response)))
            return;
    }
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous,
                    wchar_t *command_line, int show_command)
{
    wchar_t log_path[MAX_PATH];
    DWORD length;

    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show_command;

    length = GetEnvironmentVariableW(L"UU_INPUT_BROKER_LOG", log_path,
                                     MAX_PATH);
    if (length == 0 || length >= MAX_PATH) {
        length = GetTempPathW(MAX_PATH, log_path);
        if (length == 0 || length >= MAX_PATH - 20)
            lstrcpynW(log_path, L"uu-input-broker.log", MAX_PATH);
        else
            lstrcatW(log_path, L"uu-input-broker.log");
    }

    log_file = CreateFileW(log_path, FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    write_log("UU input broker active\r\n");

    for (;;) {
        HANDLE pipe = CreateNamedPipeW(
            INPUT_BRIDGE_PIPE, PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT, 1,
            64 * 1024, 64 * 1024, 0, NULL);
        BOOL connected;

        if (pipe == INVALID_HANDLE_VALUE) {
            Sleep(1000);
            continue;
        }

        connected = ConnectNamedPipe(pipe, NULL) ||
                    GetLastError() == ERROR_PIPE_CONNECTED;
        if (connected)
            serve_client(pipe);
        FlushFileBuffers(pipe);
        DisconnectNamedPipe(pipe);
        CloseHandle(pipe);
    }
}
