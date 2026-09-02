#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "terminal_bridge_protocol.h"

static SOCKET terminal_socket = INVALID_SOCKET;
static CRITICAL_SECTION send_lock;
static HANDLE stop_event;

static void write_error(const char *message)
{
    DWORD written;
    HANDLE error_handle = GetStdHandle(STD_ERROR_HANDLE);

    if (error_handle != NULL && error_handle != INVALID_HANDLE_VALUE) {
        WriteFile(error_handle, message, (DWORD)strlen(message), &written, NULL);
        WriteFile(error_handle, "\r\n", 2, &written, NULL);
    }
}

static int send_all(const void *buffer, size_t size)
{
    const char *cursor = (const char *)buffer;

    while (size > 0) {
        int chunk = size > INT_MAX ? INT_MAX : (int)size;
        int sent = send(terminal_socket, cursor, chunk, 0);

        if (sent <= 0)
            return 0;
        cursor += sent;
        size -= (size_t)sent;
    }
    return 1;
}

static int receive_all(void *buffer, size_t size)
{
    char *cursor = (char *)buffer;

    while (size > 0) {
        int chunk = size > INT_MAX ? INT_MAX : (int)size;
        int received = recv(terminal_socket, cursor, chunk, 0);

        if (received <= 0)
            return 0;
        cursor += received;
        size -= (size_t)received;
    }
    return 1;
}

static int send_frame(uint8_t type, const void *payload, uint32_t length)
{
    struct uurb_terminal_frame frame;
    int result;

    memset(&frame, 0, sizeof(frame));
    frame.type = type;
    frame.length = htonl(length);
    EnterCriticalSection(&send_lock);
    result = send_all(&frame, sizeof(frame));
    if (result && length > 0)
        result = send_all(payload, length);
    LeaveCriticalSection(&send_lock);
    return result;
}

static void console_size(uint16_t *columns, uint16_t *rows)
{
    CONSOLE_SCREEN_BUFFER_INFO info;
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    SHORT width;
    SHORT height;

    *columns = 80;
    *rows = 24;
    if (!GetConsoleScreenBufferInfo(output, &info))
        return;
    width = (SHORT)(info.srWindow.Right - info.srWindow.Left + 1);
    height = (SHORT)(info.srWindow.Bottom - info.srWindow.Top + 1);
    if (width > 0)
        *columns = (uint16_t)width;
    if (height > 0)
        *rows = (uint16_t)height;
}

static DWORD WINAPI input_worker(LPVOID unused)
{
    unsigned char buffer[16384];
    DWORD received;
    HANDLE input = GetStdHandle(STD_INPUT_HANDLE);

    (void)unused;
    while (WaitForSingleObject(stop_event, 0) == WAIT_TIMEOUT) {
        if (!ReadFile(input, buffer, sizeof(buffer), &received, NULL) ||
            received == 0) {
            send_frame(UURB_TERMINAL_FRAME_EOF, NULL, 0);
            return 0;
        }
        if (!send_frame(UURB_TERMINAL_FRAME_DATA, buffer, received))
            return 1;
    }
    return 0;
}

static DWORD WINAPI resize_worker(LPVOID unused)
{
    uint16_t columns;
    uint16_t rows;
    uint16_t previous_columns = 0;
    uint16_t previous_rows = 0;
    uint16_t dimensions[2];

    (void)unused;
    while (WaitForSingleObject(stop_event, 250) == WAIT_TIMEOUT) {
        console_size(&columns, &rows);
        if (columns == previous_columns && rows == previous_rows)
            continue;
        previous_columns = columns;
        previous_rows = rows;
        dimensions[0] = htons(columns);
        dimensions[1] = htons(rows);
        if (!send_frame(UURB_TERMINAL_FRAME_RESIZE, dimensions,
                        sizeof(dimensions)))
            return 1;
    }
    return 0;
}

static int parse_port(const char *value, uint16_t *port)
{
    char *end = NULL;
    unsigned long parsed;

    if (value == NULL || *value == '\0')
        return 0;
    parsed = strtoul(value, &end, 10);
    if (*end != '\0' || parsed == 0 || parsed > 65535)
        return 0;
    *port = (uint16_t)parsed;
    return 1;
}

static int token_is_valid(const char *token)
{
    size_t index;

    if (token == NULL || strlen(token) != UURB_TERMINAL_TOKEN_LENGTH)
        return 0;
    for (index = 0; index < UURB_TERMINAL_TOKEN_LENGTH; index++) {
        if (!((token[index] >= '0' && token[index] <= '9') ||
              (token[index] >= 'a' && token[index] <= 'f')))
            return 0;
    }
    return 1;
}

static int load_environment_configuration(char *token, uint16_t *port)
{
    char port_text[16];
    DWORD token_length;
    DWORD port_length;

    token_length = GetEnvironmentVariableA(
        "UURB_TERMINAL_BRIDGE_TOKEN", token,
        UURB_TERMINAL_TOKEN_LENGTH + 1);
    port_length = GetEnvironmentVariableA(
        "UURB_TERMINAL_BRIDGE_PORT", port_text, sizeof(port_text));
    return token_length == UURB_TERMINAL_TOKEN_LENGTH &&
           port_length > 0 && port_length < sizeof(port_text) &&
           token_is_valid(token) && parse_port(port_text, port);
}

static int runtime_configuration_path(char *path, size_t path_size)
{
    char *backslash;
    char *separator;
    char *slash;
    DWORD length;
    size_t directory_length;
    size_t filename_length = strlen(UURB_TERMINAL_CONFIG_FILENAME);

    length = GetModuleFileNameA(NULL, path, (DWORD)path_size);
    if (length == 0 || length >= path_size)
        return 0;
    backslash = strrchr(path, '\\');
    slash = strrchr(path, '/');
    separator = backslash;
    if (slash != NULL && (separator == NULL || slash > separator))
        separator = slash;
    if (separator == NULL)
        return 0;
    directory_length = (size_t)(separator - path) + 1;
    if (directory_length + filename_length + 1 > path_size)
        return 0;
    memcpy(path + directory_length, UURB_TERMINAL_CONFIG_FILENAME,
           filename_length + 1);
    return 1;
}

static int load_runtime_configuration(char *token, uint16_t *port)
{
    static const char prefix[] = "version=1\nport=";
    char config[256];
    char path[32768];
    char port_text[16];
    char *cursor;
    char *newline;
    DWORD received;
    HANDLE file = INVALID_HANDLE_VALUE;
    LARGE_INTEGER size;
    size_t port_length;
    int result = 0;

    if (!runtime_configuration_path(path, sizeof(path)))
        goto done;
    file = CreateFileA(path, GENERIC_READ,
                       FILE_SHARE_READ | FILE_SHARE_DELETE, NULL,
                       OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE ||
        !GetFileSizeEx(file, &size) || size.QuadPart <= 0 ||
        size.QuadPart >= (LONGLONG)sizeof(config) ||
        !ReadFile(file, config, (DWORD)size.QuadPart, &received, NULL) ||
        received != (DWORD)size.QuadPart)
        goto done;
    config[received] = '\0';
    if (strncmp(config, prefix, sizeof(prefix) - 1) != 0)
        goto done;
    cursor = config + sizeof(prefix) - 1;
    newline = strchr(cursor, '\n');
    if (newline == NULL)
        goto done;
    port_length = (size_t)(newline - cursor);
    if (port_length == 0 || port_length >= sizeof(port_text))
        goto done;
    memcpy(port_text, cursor, port_length);
    port_text[port_length] = '\0';
    cursor = newline + 1;
    if (strncmp(cursor, "token=", 6) != 0)
        goto done;
    cursor += 6;
    if (strlen(cursor) != UURB_TERMINAL_TOKEN_LENGTH + 1 ||
        cursor[UURB_TERMINAL_TOKEN_LENGTH] != '\n')
        goto done;
    memcpy(token, cursor, UURB_TERMINAL_TOKEN_LENGTH);
    token[UURB_TERMINAL_TOKEN_LENGTH] = '\0';
    result = token_is_valid(token) && parse_port(port_text, port);

done:
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    SecureZeroMemory(config, sizeof(config));
    SecureZeroMemory(path, sizeof(path));
    SecureZeroMemory(port_text, sizeof(port_text));
    if (!result)
        SecureZeroMemory(token, UURB_TERMINAL_TOKEN_LENGTH + 1);
    return result;
}

static int load_configuration(char *token, uint16_t *port)
{
    if (load_environment_configuration(token, port))
        return 1;
    SecureZeroMemory(token, UURB_TERMINAL_TOKEN_LENGTH + 1);
    return load_runtime_configuration(token, port);
}

int main(void)
{
    WSADATA winsock;
    struct sockaddr_in address;
    struct uurb_terminal_hello hello;
    char token[UURB_TERMINAL_TOKEN_LENGTH + 1];
    DWORD written;
    HANDLE input_thread = NULL;
    HANDLE resize_thread = NULL;
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    unsigned char buffer[16384];
    uint16_t columns;
    uint16_t rows;
    uint16_t port;
    unsigned char accepted;
    int received;
    int exit_code = 1;

    if (!load_configuration(token, &port)) {
        write_error("UU Ubuntu terminal bridge is not configured");
        return 2;
    }
    if (WSAStartup(MAKEWORD(2, 2), &winsock) != 0) {
        write_error("UU Ubuntu terminal bridge could not initialize Winsock");
        return 3;
    }
    terminal_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (terminal_socket == INVALID_SOCKET) {
        write_error("UU Ubuntu terminal bridge could not create a socket");
        goto done;
    }
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(terminal_socket, (struct sockaddr *)&address,
                sizeof(address)) == SOCKET_ERROR) {
        write_error("UU Ubuntu terminal bridge is not reachable");
        goto done;
    }

    console_size(&columns, &rows);
    memset(&hello, 0, sizeof(hello));
    hello.magic = htonl(UURB_TERMINAL_MAGIC);
    hello.version = htons(UURB_TERMINAL_VERSION);
    hello.token_length = htons(UURB_TERMINAL_TOKEN_LENGTH);
    hello.columns = htons(columns);
    hello.rows = htons(rows);
    if (!send_all(&hello, sizeof(hello)) ||
        !send_all(token, UURB_TERMINAL_TOKEN_LENGTH)) {
        write_error("UU Ubuntu terminal bridge handshake failed");
        goto done;
    }
    if (!receive_all(&accepted, 1) || accepted != UURB_TERMINAL_ACCEPTED) {
        write_error("UU Ubuntu terminal bridge rejected authentication");
        goto done;
    }

    InitializeCriticalSection(&send_lock);
    stop_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (stop_event == NULL) {
        write_error("UU Ubuntu terminal bridge could not create its stop event");
        DeleteCriticalSection(&send_lock);
        goto done;
    }
    input_thread = CreateThread(NULL, 0, input_worker, NULL, 0, NULL);
    resize_thread = CreateThread(NULL, 0, resize_worker, NULL, 0, NULL);
    if (input_thread == NULL || resize_thread == NULL) {
        write_error("UU Ubuntu terminal bridge could not start I/O workers");
        goto workers_done;
    }

    while ((received = recv(terminal_socket, (char *)buffer,
                            sizeof(buffer), 0)) > 0) {
        if (!WriteFile(output, buffer, (DWORD)received, &written, NULL))
            break;
    }
    exit_code = 0;

workers_done:
    SetEvent(stop_event);
    shutdown(terminal_socket, SD_BOTH);
    if (input_thread != NULL) {
        CancelSynchronousIo(input_thread);
        WaitForSingleObject(input_thread, 1000);
        CloseHandle(input_thread);
    }
    if (resize_thread != NULL) {
        WaitForSingleObject(resize_thread, 1000);
        CloseHandle(resize_thread);
    }
    CloseHandle(stop_event);
    DeleteCriticalSection(&send_lock);

done:
    if (terminal_socket != INVALID_SOCKET)
        closesocket(terminal_socket);
    SecureZeroMemory(token, sizeof(token));
    WSACleanup();
    return exit_code;
}
