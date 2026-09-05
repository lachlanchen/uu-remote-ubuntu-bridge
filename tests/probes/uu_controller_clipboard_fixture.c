#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

#ifndef UURB_FIXTURE_TEXT
#define UURB_FIXTURE_TEXT L"controller clipboard fixture"
#endif

static LRESULT CALLBACK fixture_window_proc(HWND window, UINT message,
                                             WPARAM wparam, LPARAM lparam)
{
    return DefWindowProcW(window, message, wparam, lparam);
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line,
                    int show_command)
{
    static const wchar_t class_name[] = L"UURBClipboardFixture";
    static const wchar_t text[] = UURB_FIXTURE_TEXT;
    WNDCLASSW window_class;
    HGLOBAL allocation;
    HWND window;
    wchar_t *destination;

    (void)previous;
    (void)command_line;
    (void)show_command;
    ZeroMemory(&window_class, sizeof(window_class));
    window_class.lpfnWndProc = fixture_window_proc;
    window_class.hInstance = instance;
    window_class.lpszClassName = class_name;
    if (!RegisterClassW(&window_class) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
        return 2;
    window = CreateWindowExW(0, class_name, L"UU clipboard fixture", 0,
                             0, 0, 1, 1, NULL, NULL, instance, NULL);
    if (!window || !OpenClipboard(window))
        return 3;
    if (!EmptyClipboard()) {
        CloseClipboard();
        return 4;
    }
    allocation = GlobalAlloc(GMEM_MOVEABLE, sizeof(text));
    if (!allocation) {
        CloseClipboard();
        return 5;
    }
    destination = GlobalLock(allocation);
    if (!destination) {
        GlobalFree(allocation);
        CloseClipboard();
        return 6;
    }
    memcpy(destination, text, sizeof(text));
    GlobalUnlock(allocation);
    if (!SetClipboardData(CF_UNICODETEXT, allocation)) {
        GlobalFree(allocation);
        CloseClipboard();
        return 7;
    }
    CloseClipboard();
    Sleep(2000);
    DestroyWindow(window);
    return 0;
}
