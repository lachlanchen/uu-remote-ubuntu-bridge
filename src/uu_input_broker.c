#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define INPUT_BRIDGE_MAGIC 0x42525555UL
#define INPUT_BRIDGE_MAX_INPUTS 64UL
#define INPUT_BRIDGE_MAX_TRANSLATED_INPUTS (INPUT_BRIDGE_MAX_INPUTS * 8UL)
#define INPUT_BRIDGE_MAX_SEGMENTS (INPUT_BRIDGE_MAX_INPUTS + 1UL)
#define INPUT_BRIDGE_PIPE L"\\\\.\\pipe\\uurb-input-v1"
#define INPUT_BRIDGE_FOCUS_TIMEOUT_MS 300UL
#define INPUT_BRIDGE_DEFAULT_TEXT_KEY_DELAY_MS 8UL
#define INPUT_BRIDGE_MAX_TEXT_KEY_DELAY_MS 50UL
#define INPUT_BRIDGE_DEFAULT_PHYSICAL_KEY_DELAY_MS 0UL
#define INPUT_BRIDGE_MAX_PHYSICAL_KEY_DELAY_MS 50UL

typedef struct input_bridge_request {
    DWORD magic;
    DWORD count;
    DWORD input_size;
} input_bridge_request;

typedef struct input_bridge_response {
    DWORD result;
    DWORD error;
} input_bridge_response;

typedef struct input_segment {
    DWORD offset;
    DWORD count;
    BOOL text;
} input_segment;

static HANDLE log_file = INVALID_HANDLE_VALUE;
static volatile LONG input_call_count;
static volatile LONG keyboard_call_count;
static volatile LONG mouse_call_count;
static volatile LONG other_call_count;
static volatile LONG text_call_count;
static DWORD text_key_delay_ms = INPUT_BRIDGE_DEFAULT_TEXT_KEY_DELAY_MS;
static DWORD physical_key_delay_ms =
    INPUT_BRIDGE_DEFAULT_PHYSICAL_KEY_DELAY_MS;

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

static BOOL append_segment(input_segment *segments, DWORD *segment_count,
                           DWORD offset, DWORD count, BOOL text)
{
    input_segment *segment;

    if (count == 0)
        return TRUE;
    if (*segment_count >= INPUT_BRIDGE_MAX_SEGMENTS)
        return FALSE;

    segment = &segments[*segment_count];
    segment->offset = offset;
    segment->count = count;
    segment->text = text;
    (*segment_count)++;
    return TRUE;
}

static BOOL translate_inputs(DWORD source_count, const INPUT *source,
                             INPUT *translated, DWORD *translated_count,
                             input_segment *segments, DWORD *segment_count,
                             BOOL *normalized_unicode)
{
    DWORD index;
    DWORD ordinary_count = 0;
    DWORD ordinary_offset = 0;

    *translated_count = 0;
    *segment_count = 0;
    *normalized_unicode = FALSE;
    for (index = 0; index < source_count; index++) {
        const INPUT *input = &source[index];

        if (input->type == INPUT_KEYBOARD &&
            (input->ki.dwFlags & KEYEVENTF_UNICODE) != 0) {
            DWORD chord_offset;

            *normalized_unicode = TRUE;
            if (!append_segment(segments, segment_count, ordinary_offset,
                                ordinary_count, FALSE))
                return FALSE;
            ordinary_count = 0;
            if ((input->ki.dwFlags & KEYEVENTF_KEYUP) != 0)
                continue;
            chord_offset = *translated_count;
            if (!append_character_chord((WCHAR)input->ki.wScan, translated,
                                        translated_count))
                return FALSE;
            if (!append_segment(segments, segment_count, chord_offset,
                                *translated_count - chord_offset, TRUE))
                return FALSE;
            continue;
        }

        if (*translated_count >= INPUT_BRIDGE_MAX_TRANSLATED_INPUTS)
            return FALSE;
        if (ordinary_count == 0)
            ordinary_offset = *translated_count;
        translated[*translated_count] = *input;
        (*translated_count)++;
        ordinary_count++;
    }

    return append_segment(segments, segment_count, ordinary_offset,
                          ordinary_count, FALSE);
}

static BOOL inputs_contain_type(DWORD count, const INPUT *inputs, DWORD type)
{
    DWORD index;

    for (index = 0; index < count; index++) {
        if (inputs[index].type == type)
            return TRUE;
    }
    return FALSE;
}

static BOOL segment_contains_physical_keyboard(const input_segment *segment,
                                               const INPUT *inputs)
{
    DWORD index;

    if (segment->text)
        return FALSE;
    for (index = 0; index < segment->count; index++) {
        const INPUT *input = &inputs[segment->offset + index];

        if (input->type == INPUT_KEYBOARD &&
            (input->ki.dwFlags & KEYEVENTF_UNICODE) == 0)
            return TRUE;
    }
    return FALSE;
}

static DWORD send_relay_inputs(DWORD source_count, const INPUT *source,
                               DWORD *error, BOOL *normalized_unicode,
                               DWORD *paced_characters,
                               DWORD *paced_physical_segments)
{
    INPUT translated[INPUT_BRIDGE_MAX_TRANSLATED_INPUTS];
    input_segment segments[INPUT_BRIDGE_MAX_SEGMENTS];
    DWORD translated_count;
    DWORD segment_count;
    DWORD index;

    *paced_characters = 0;
    *paced_physical_segments = 0;
    if (!translate_inputs(source_count, source, translated, &translated_count,
                          segments, &segment_count, normalized_unicode)) {
        *error = ERROR_NO_UNICODE_TRANSLATION;
        return 0;
    }

    if (translated_count == 0) {
        *error = ERROR_SUCCESS;
        return source_count;
    }

    for (index = 0; index < segment_count; index++) {
        const input_segment *segment = &segments[index];
        UINT sent;

        SetLastError(ERROR_SUCCESS);
        sent = SendInput(segment->count, translated + segment->offset,
                         sizeof(INPUT));
        *error = GetLastError();
        if (sent != segment->count)
            return 0;
        if (segment->text) {
            (*paced_characters)++;
            if (text_key_delay_ms > 0)
                Sleep(text_key_delay_ms);
        } else if (segment_contains_physical_keyboard(segment, translated)) {
            (*paced_physical_segments)++;
            if (physical_key_delay_ms > 0)
                Sleep(physical_key_delay_ms);
        }
    }

    *error = ERROR_SUCCESS;
    return source_count;
}

static BOOL request_relay_focus(DWORD *waited_ms)
{
    HWND relay = FindWindowW(NULL, L"Ubuntu-Desktop-Relay");
    DWORD elapsed = 0;

    *waited_ms = 0;
    if (relay == NULL) {
        SetLastError(ERROR_NOT_READY);
        return FALSE;
    }
    if (GetForegroundWindow() == relay)
        return TRUE;

    if (IsIconic(relay))
        ShowWindow(relay, SW_RESTORE);
    while (elapsed <= INPUT_BRIDGE_FOCUS_TIMEOUT_MS) {
        if (elapsed == 0 || elapsed % 50 == 0)
            SetForegroundWindow(relay);
        if (GetForegroundWindow() == relay) {
            *waited_ms = elapsed;
            return TRUE;
        }
        Sleep(5);
        elapsed += 5;
    }

    *waited_ms = elapsed;
    SetLastError(ERROR_NOT_READY);
    return FALSE;
}

static DWORD configured_text_key_delay(void)
{
    wchar_t value[16];
    wchar_t *end = NULL;
    DWORD length;
    unsigned long parsed;

    length = GetEnvironmentVariableW(L"UURB_TEXT_KEY_DELAY_MS", value,
                                     ARRAYSIZE(value));
    if (length == 0 || length >= ARRAYSIZE(value))
        return INPUT_BRIDGE_DEFAULT_TEXT_KEY_DELAY_MS;

    parsed = wcstoul(value, &end, 10);
    if (end == value || *end != L'\0' ||
        parsed > INPUT_BRIDGE_MAX_TEXT_KEY_DELAY_MS)
        return INPUT_BRIDGE_DEFAULT_TEXT_KEY_DELAY_MS;
    return (DWORD)parsed;
}

static DWORD configured_physical_key_delay(void)
{
    wchar_t value[16];
    wchar_t *end = NULL;
    DWORD length;
    unsigned long parsed;

    length = GetEnvironmentVariableW(L"UURB_PHYSICAL_KEY_DELAY_MS", value,
                                     ARRAYSIZE(value));
    if (length == 0 || length >= ARRAYSIZE(value))
        return INPUT_BRIDGE_DEFAULT_PHYSICAL_KEY_DELAY_MS;

    parsed = wcstoul(value, &end, 10);
    if (end == value || *end != L'\0' ||
        parsed > INPUT_BRIDGE_MAX_PHYSICAL_KEY_DELAY_MS)
        return INPUT_BRIDGE_DEFAULT_PHYSICAL_KEY_DELAY_MS;
    return (DWORD)parsed;
}

static void serve_client(HANDLE pipe)
{
    for (;;) {
        input_bridge_request request;
        input_bridge_response response;
        INPUT inputs[INPUT_BRIDGE_MAX_INPUTS];
        char line[512];
        DWORD first_type = (DWORD)-1;
        DWORD first_flags = 0;
        DWORD focus_wait_ms = 0;
        DWORD paced_characters = 0;
        DWORD paced_physical_segments = 0;
        LONG call_number;
        LONG category_call_number;
        const char *category;
        BOOL focus_ready;
        BOOL normalized_unicode = FALSE;
        BOOL physical_keyboard;
        BOOL mouse_input;
        ULONGLONG started_ms;
        ULONGLONG inject_started_ms = 0;
        DWORD inject_ms = 0;

        started_ms = GetTickCount64();

        if (!read_all(pipe, &request, sizeof(request)))
            return;
        if (request.magic != INPUT_BRIDGE_MAGIC || request.count == 0 ||
            request.count > INPUT_BRIDGE_MAX_INPUTS ||
            request.input_size != sizeof(INPUT))
            return;
        if (!read_all(pipe, inputs, request.count * sizeof(INPUT)))
            return;

        focus_ready = request_relay_focus(&focus_wait_ms);
        if (focus_ready) {
            inject_started_ms = GetTickCount64();
            response.result = send_relay_inputs(request.count, inputs,
                                                &response.error,
                                                &normalized_unicode,
                                                &paced_characters,
                                                &paced_physical_segments);
            inject_ms = (DWORD)(GetTickCount64() - inject_started_ms);
        } else {
            DWORD index;

            response.result = 0;
            response.error = GetLastError();
            for (index = 0; index < request.count; index++) {
                if (inputs[index].type == INPUT_KEYBOARD &&
                    (inputs[index].ki.dwFlags & KEYEVENTF_UNICODE) != 0) {
                    normalized_unicode = TRUE;
                    break;
                }
            }
        }
        first_type = inputs[0].type;
        if (first_type == INPUT_MOUSE)
            first_flags = inputs[0].mi.dwFlags;
        else if (first_type == INPUT_KEYBOARD)
            first_flags = inputs[0].ki.dwFlags;
        physical_keyboard = !normalized_unicode &&
                            inputs_contain_type(request.count, inputs,
                                                INPUT_KEYBOARD);
        mouse_input = !normalized_unicode && !physical_keyboard &&
                      inputs_contain_type(request.count, inputs, INPUT_MOUSE);
        call_number = InterlockedIncrement(&input_call_count);
        if (normalized_unicode) {
            category = "text";
            category_call_number = InterlockedIncrement(&text_call_count);
        } else if (physical_keyboard) {
            category = "keyboard";
            category_call_number = InterlockedIncrement(&keyboard_call_count);
        } else if (mouse_input) {
            category = "mouse";
            category_call_number = InterlockedIncrement(&mouse_call_count);
        } else {
            category = "other";
            category_call_number = InterlockedIncrement(&other_call_count);
        }
        if ((normalized_unicode && category_call_number <= 256) ||
            (physical_keyboard && category_call_number <= 256) ||
            (mouse_input && category_call_number <= 32) ||
            (!normalized_unicode && !physical_keyboard && !mouse_input &&
             category_call_number <= 64) ||
            response.result != request.count) {
            _snprintf(
                line, sizeof(line),
                "call=%ld category=%s category-call=%ld count=%lu type=%lu flags=0x%08lx text=%s focus=%s focus-wait-ms=%lu paced-text=%lu text-delay-ms=%lu paced-physical=%lu physical-delay-ms=%lu inject-ms=%lu total-ms=%lu result=%lu error=%lu\r\n",
                call_number, category, category_call_number,
                (unsigned long)request.count,
                (unsigned long)first_type, (unsigned long)first_flags,
                normalized_unicode ? "normalized" : "unchanged",
                focus_ready ? "ready" : "timeout",
                (unsigned long)focus_wait_ms,
                (unsigned long)paced_characters,
                (unsigned long)text_key_delay_ms,
                (unsigned long)paced_physical_segments,
                (unsigned long)physical_key_delay_ms,
                (unsigned long)inject_ms,
                (unsigned long)(GetTickCount64() - started_ms),
                (unsigned long)response.result,
                (unsigned long)response.error);
            line[sizeof(line) - 1] = '\0';
            write_log(line);
            if (response.result != request.count)
                flush_log();
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
    text_key_delay_ms = configured_text_key_delay();
    physical_key_delay_ms = configured_physical_key_delay();
    {
        char line[192];

        _snprintf(line, sizeof(line),
                  "UU input broker active text-delay-ms=%lu physical-delay-ms=%lu focus-timeout-ms=%lu\r\n",
                  (unsigned long)text_key_delay_ms,
                  (unsigned long)physical_key_delay_ms,
                  (unsigned long)INPUT_BRIDGE_FOCUS_TIMEOUT_MS);
        line[sizeof(line) - 1] = '\0';
        write_log(line);
        flush_log();
    }

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
