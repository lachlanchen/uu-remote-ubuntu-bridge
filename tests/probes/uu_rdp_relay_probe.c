#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>

static WCHAR marker_path[MAX_PATH];

static void record_paste_chord(void)
{
    static BOOL recorded;
    HANDLE marker;

    if (recorded || marker_path[0] == L'\0')
        return;
    marker = CreateFileW(marker_path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                         CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (marker == INVALID_HANDLE_VALUE)
        return;
    CloseHandle(marker);
    recorded = TRUE;
}

static LRESULT CALLBACK relay_window_proc(HWND window, UINT message,
                                          WPARAM wparam, LPARAM lparam)
{
    if ((message == WM_KEYDOWN || message == WM_SYSKEYDOWN) &&
        wparam == VK_INSERT && (GetKeyState(VK_SHIFT) & 0x8000) != 0)
        record_paste_chord();
    if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous,
                    PWSTR command_line, int show_command)
{
    static const WCHAR class_name[] = L"UURBRelayAcceptanceWindow";
    WNDCLASSW window_class;
    MSG message;
    HWND window;

    (void)previous;
    (void)command_line;
    (void)show_command;
    if (GetEnvironmentVariableW(L"UURB_RELAY_MARKER", marker_path,
                                ARRAYSIZE(marker_path)) == 0)
        return 2;

    ZeroMemory(&window_class, sizeof(window_class));
    window_class.lpfnWndProc = relay_window_proc;
    window_class.hInstance = instance;
    window_class.lpszClassName = class_name;
    if (!RegisterClassW(&window_class))
        return 3;
    window = CreateWindowExW(0, class_name, L"Ubuntu-Desktop-Relay",
                             WS_OVERLAPPEDWINDOW, CW_USEDEFAULT,
                             CW_USEDEFAULT, 640, 480, NULL, NULL, instance,
                             NULL);
    if (!window)
        return 4;
    ShowWindow(window, SW_SHOW);
    UpdateWindow(window);

    while (GetMessageW(&message, NULL, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    return 0;
}
