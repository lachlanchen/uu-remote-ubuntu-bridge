#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define INPUT_BRIDGE_MAGIC 0x42525555UL
#define INPUT_BRIDGE_MAX_INPUTS 64UL
#define INPUT_BRIDGE_MAX_TRANSLATED_INPUTS (INPUT_BRIDGE_MAX_INPUTS * 8UL)
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

static BOOL append_key_event(INPUT *inputs, DWORD *count, WORD virtual_key,
                             DWORD flags)
{
    INPUT *input;

    if (*count >= INPUT_BRIDGE_MAX_TRANSLATED_INPUTS)
        return FALSE;

    input = &inputs[*count];
    ZeroMemory(input, sizeof(*input));
    input->type = INPUT_KEYBOARD;
    input->ki.wVk = virtual_key;
    input->ki.dwFlags = flags;
    (*count)++;
    return TRUE;
}

static SHORT key_mapping_for_character(WCHAR character)
{
    switch (character) {
    case L'\b':
        return (SHORT)VK_BACK;
    case L'\t':
        return (SHORT)VK_TAB;
    case L'\n':
    case L'\r':
        return (SHORT)VK_RETURN;
    default:
        return VkKeyScanW(character);
    }
}

static BOOL append_character_chord(WCHAR character, INPUT *inputs,
                                   DWORD *count)
{
    SHORT mapping = key_mapping_for_character(character);
    WORD virtual_key;
    BYTE shift_state;

    if (mapping == (SHORT)-1)
        return FALSE;

    virtual_key = LOBYTE((WORD)mapping);
    shift_state = HIBYTE((WORD)mapping);
    if ((shift_state & ~7U) != 0)
        return FALSE;

    if ((shift_state & 2U) != 0 &&
        !append_key_event(inputs, count, VK_CONTROL, 0))
        return FALSE;
    if ((shift_state & 4U) != 0 &&
        !append_key_event(inputs, count, VK_MENU, 0))
        return FALSE;
    if ((shift_state & 1U) != 0 &&
        !append_key_event(inputs, count, VK_SHIFT, 0))
        return FALSE;

    if (!append_key_event(inputs, count, virtual_key, 0) ||
        !append_key_event(inputs, count, virtual_key, KEYEVENTF_KEYUP))
        return FALSE;

    if ((shift_state & 1U) != 0 &&
        !append_key_event(inputs, count, VK_SHIFT, KEYEVENTF_KEYUP))
        return FALSE;
    if ((shift_state & 4U) != 0 &&
        !append_key_event(inputs, count, VK_MENU, KEYEVENTF_KEYUP))
        return FALSE;
    if ((shift_state & 2U) != 0 &&
        !append_key_event(inputs, count, VK_CONTROL, KEYEVENTF_KEYUP))
        return FALSE;

    return TRUE;
}

static BOOL translate_inputs(DWORD source_count, const INPUT *source,
                             INPUT *translated, DWORD *translated_count,
                             BOOL *normalized_unicode)
{
    DWORD index;

    *translated_count = 0;
    *normalized_unicode = FALSE;
    for (index = 0; index < source_count; index++) {
        const INPUT *input = &source[index];

        if (input->type == INPUT_KEYBOARD &&
            (input->ki.dwFlags & KEYEVENTF_UNICODE) != 0) {
            *normalized_unicode = TRUE;
            if ((input->ki.dwFlags & KEYEVENTF_KEYUP) != 0)
                continue;
            if (!append_character_chord((WCHAR)input->ki.wScan, translated,
                                        translated_count))
                return FALSE;
            continue;
        }

        if (*translated_count >= INPUT_BRIDGE_MAX_TRANSLATED_INPUTS)
            return FALSE;
        translated[*translated_count] = *input;
        (*translated_count)++;
    }

    return TRUE;
}

static DWORD send_relay_inputs(DWORD source_count, const INPUT *source,
                               DWORD *error, BOOL *normalized_unicode)
{
    INPUT translated[INPUT_BRIDGE_MAX_TRANSLATED_INPUTS];
    DWORD translated_count;
    UINT sent;

    if (!translate_inputs(source_count, source, translated, &translated_count,
                          normalized_unicode)) {
        *error = ERROR_NO_UNICODE_TRANSLATION;
        return 0;
    }

    if (translated_count == 0) {
        *error = ERROR_SUCCESS;
        return source_count;
    }

    SetLastError(ERROR_SUCCESS);
    sent = SendInput(translated_count, translated, sizeof(INPUT));
    *error = GetLastError();
    if (sent != translated_count)
        return 0;

    *error = ERROR_SUCCESS;
    return source_count;
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
        BOOL normalized_unicode = FALSE;

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

        response.result = send_relay_inputs(request.count, inputs,
                                            &response.error,
                                            &normalized_unicode);
        first_type = inputs[0].type;
        if (first_type == INPUT_MOUSE)
            first_flags = inputs[0].mi.dwFlags;
        else if (first_type == INPUT_KEYBOARD)
            first_flags = inputs[0].ki.dwFlags;
        call_number = InterlockedIncrement(&input_call_count);
        if (call_number <= 500 || response.result != request.count) {
            _snprintf(
                line, sizeof(line),
                "call=%ld count=%lu type=%lu flags=0x%08lx text=%s result=%lu error=%lu\r\n",
                call_number, (unsigned long)request.count,
                (unsigned long)first_type, (unsigned long)first_flags,
                normalized_unicode ? "normalized" : "unchanged",
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
