#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#include "x11_clipboard_protocol.h"

#define UURB_CLIPBOARD_POLL_MS 125UL
#define UURB_CLIPBOARD_MAX_UNITS 1048576UL

static SOCKET clipboard_socket = INVALID_SOCKET;
static BOOL winsock_initialized;
static unsigned short clipboard_port;
static char clipboard_token[UURB_X11_CLIPBOARD_TOKEN_SIZE + 1];

static void close_clipboard_socket(void)
{
    if (clipboard_socket != INVALID_SOCKET) {
        closesocket(clipboard_socket);
        clipboard_socket = INVALID_SOCKET;
    }
}

static BOOL socket_write_all(SOCKET socket_handle, const void *buffer, int size)
{
    const char *position = (const char *)buffer;

    while (size > 0) {
        int written = send(socket_handle, position, size, 0);

        if (written == SOCKET_ERROR || written == 0)
            return FALSE;
        position += written;
        size -= written;
    }
    return TRUE;
}

static BOOL socket_read_all(SOCKET socket_handle, void *buffer, int size)
{
    char *position = (char *)buffer;

    while (size > 0) {
        int received = recv(socket_handle, position, size, 0);

        if (received == SOCKET_ERROR || received == 0)
            return FALSE;
        position += received;
        size -= received;
    }
    return TRUE;
}

static BOOL configure_bridge(void)
{
    wchar_t port_value[16];
    wchar_t token_value[UURB_X11_CLIPBOARD_TOKEN_SIZE + 1];
    wchar_t *end = NULL;
    DWORD port_length;
    DWORD token_length;
    unsigned long parsed_port;
    DWORD index;

    port_length = GetEnvironmentVariableW(L"UURB_X11_CLIPBOARD_PORT",
                                           port_value, ARRAYSIZE(port_value));
    token_length = GetEnvironmentVariableW(L"UURB_X11_CLIPBOARD_TOKEN",
                                            token_value, ARRAYSIZE(token_value));
    if (port_length == 0 || port_length >= ARRAYSIZE(port_value) ||
        token_length != UURB_X11_CLIPBOARD_TOKEN_SIZE)
        return FALSE;
    parsed_port = wcstoul(port_value, &end, 10);
    if (end == port_value || *end != L'\0' || parsed_port == 0 ||
        parsed_port > 65535)
        return FALSE;
    for (index = 0; index < UURB_X11_CLIPBOARD_TOKEN_SIZE; index++) {
        wchar_t character = token_value[index];

        if (!((character >= L'0' && character <= L'9') ||
              (character >= L'a' && character <= L'f') ||
              (character >= L'A' && character <= L'F')))
            return FALSE;
        clipboard_token[index] = (char)character;
    }
    clipboard_token[UURB_X11_CLIPBOARD_TOKEN_SIZE] = '\0';
    clipboard_port = (unsigned short)parsed_port;
    return TRUE;
}

static BOOL connect_clipboard_listener(void)
{
    struct sockaddr_in address;
    uurb_x11_clipboard_handshake handshake;
    uurb_x11_clipboard_response response;
    DWORD timeout_ms = 1000;
    WSADATA data;

    if (clipboard_socket != INVALID_SOCKET)
        return TRUE;
    if (!winsock_initialized) {
        if (WSAStartup(MAKEWORD(2, 2), &data) != 0)
            return FALSE;
        winsock_initialized = TRUE;
    }
    clipboard_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (clipboard_socket == INVALID_SOCKET)
        return FALSE;
    setsockopt(clipboard_socket, SOL_SOCKET, SO_SNDTIMEO,
               (const char *)&timeout_ms, sizeof(timeout_ms));
    setsockopt(clipboard_socket, SOL_SOCKET, SO_RCVTIMEO,
               (const char *)&timeout_ms, sizeof(timeout_ms));
    ZeroMemory(&address, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(clipboard_port);
    if (connect(clipboard_socket, (struct sockaddr *)&address,
                sizeof(address)) == SOCKET_ERROR) {
        close_clipboard_socket();
        return FALSE;
    }
    ZeroMemory(&handshake, sizeof(handshake));
    handshake.magic = UURB_X11_CLIPBOARD_MAGIC;
    handshake.version = UURB_X11_CLIPBOARD_VERSION;
    memcpy(handshake.token, clipboard_token, UURB_X11_CLIPBOARD_TOKEN_SIZE);
    if (!socket_write_all(clipboard_socket, &handshake, sizeof(handshake)) ||
        !socket_read_all(clipboard_socket, &response, sizeof(response)) ||
        response.magic != UURB_X11_CLIPBOARD_MAGIC || response.sequence != 0 ||
        response.result != 1 || response.error != 0) {
        close_clipboard_socket();
        return FALSE;
    }
    return TRUE;
}

static BOOL owner_is_gameviewer(void)
{
    HWND owner;
    DWORD process_id = 0;
    HANDLE process;
    wchar_t path[MAX_PATH];
    DWORD length = ARRAYSIZE(path);
    const wchar_t *basename;

    owner = GetClipboardOwner();
    if (!owner || !GetWindowThreadProcessId(owner, &process_id) ||
        process_id == 0)
        return FALSE;
    process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, process_id);
    if (!process)
        return FALSE;
    if (!QueryFullProcessImageNameW(process, 0, path, &length)) {
        CloseHandle(process);
        return FALSE;
    }
    CloseHandle(process);
    basename = wcsrchr(path, L'\\');
    basename = basename ? basename + 1 : path;
    return lstrcmpiW(basename, L"GameViewer.exe") == 0;
}

static BOOL read_clipboard_utf8(char **output, DWORD *output_size)
{
    HANDLE handle;
    const wchar_t *source;
    SIZE_T allocation_bytes;
    SIZE_T source_units;
    SIZE_T index;
    wchar_t *normalized;
    SIZE_T normalized_units = 0;
    int bytes;
    char *result;

    *output = NULL;
    *output_size = 0;
    if (!OpenClipboard(NULL))
        return FALSE;
    handle = GetClipboardData(CF_UNICODETEXT);
    if (!handle) {
        CloseClipboard();
        return FALSE;
    }
    source = GlobalLock(handle);
    allocation_bytes = GlobalSize(handle);
    if (!source || allocation_bytes < sizeof(wchar_t) ||
        allocation_bytes / sizeof(wchar_t) > UURB_CLIPBOARD_MAX_UNITS) {
        if (source)
            GlobalUnlock(handle);
        CloseClipboard();
        return FALSE;
    }
    source_units = allocation_bytes / sizeof(wchar_t);
    for (index = 0; index < source_units && source[index] != L'\0'; index++)
        ;
    if (index == source_units) {
        GlobalUnlock(handle);
        CloseClipboard();
        return FALSE;
    }
    normalized = HeapAlloc(GetProcessHeap(), 0,
                           (index + 1) * sizeof(wchar_t));
    if (!normalized) {
        GlobalUnlock(handle);
        CloseClipboard();
        return FALSE;
    }
    for (source_units = 0; source_units < index; source_units++) {
        wchar_t character = source[source_units];

        if (character == L'\0') {
            HeapFree(GetProcessHeap(), 0, normalized);
            GlobalUnlock(handle);
            CloseClipboard();
            return FALSE;
        }
        if (character == L'\r') {
            normalized[normalized_units++] = L'\n';
            if (source_units + 1 < index && source[source_units + 1] == L'\n')
                source_units++;
        } else {
            normalized[normalized_units++] = character;
        }
    }
    GlobalUnlock(handle);
    CloseClipboard();
    if (normalized_units == 0) {
        HeapFree(GetProcessHeap(), 0, normalized);
        return FALSE;
    }
    bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, normalized,
                                (int)normalized_units, NULL, 0, NULL, NULL);
    if (bytes <= 0 || (DWORD)bytes > UURB_X11_CLIPBOARD_MAX_TEXT_BYTES) {
        HeapFree(GetProcessHeap(), 0, normalized);
        return FALSE;
    }
    result = HeapAlloc(GetProcessHeap(), 0, (SIZE_T)bytes);
    if (!result || WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS,
                                       normalized, (int)normalized_units,
                                       result, bytes, NULL, NULL) != bytes) {
        if (result)
            HeapFree(GetProcessHeap(), 0, result);
        HeapFree(GetProcessHeap(), 0, normalized);
        return FALSE;
    }
    HeapFree(GetProcessHeap(), 0, normalized);
    *output = result;
    *output_size = (DWORD)bytes;
    return TRUE;
}

static BOOL forward_current_clipboard(DWORD sequence)
{
    uurb_x11_clipboard_request request;
    uurb_x11_clipboard_response response;
    char *text = NULL;
    DWORD text_size;
    BOOL sent = FALSE;

    if (!owner_is_gameviewer() || !read_clipboard_utf8(&text, &text_size))
        return FALSE;
    if (!connect_clipboard_listener())
        goto cleanup;
    request.magic = UURB_X11_CLIPBOARD_MAGIC;
    request.sequence = sequence;
    request.text_bytes = text_size;
    request.reserved = 0;
    if (!socket_write_all(clipboard_socket, &request, sizeof(request)) ||
        !socket_write_all(clipboard_socket, text, (int)text_size) ||
        !socket_read_all(clipboard_socket, &response, sizeof(response)) ||
        response.magic != UURB_X11_CLIPBOARD_MAGIC ||
        response.sequence != sequence || response.result != text_size ||
        response.error != 0) {
        close_clipboard_socket();
        goto cleanup;
    }
    sent = TRUE;

cleanup:
    HeapFree(GetProcessHeap(), 0, text);
    return sent;
}

int wmain(void)
{
    DWORD delivered_sequence = 0;

    if (!configure_bridge())
        return 2;
    for (;;) {
        DWORD sequence = GetClipboardSequenceNumber();

        if (sequence != 0 && sequence != delivered_sequence &&
            forward_current_clipboard(sequence))
            delivered_sequence = sequence;
        Sleep(UURB_CLIPBOARD_POLL_MS);
    }
}
