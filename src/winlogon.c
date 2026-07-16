#define WIN32_LEAN_AND_MEAN
#include <windows.h>

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line,
                   int show_command)
{
    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show_command;

    Sleep(INFINITE);
    return 0;
}
