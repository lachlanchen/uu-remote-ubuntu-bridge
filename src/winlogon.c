#ifdef __WINE__
#include <unistd.h>

int __stdcall WinMain(void *instance, void *previous, char *command_line,
                      int show_command)
#else
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command_line,
                   int show_command)
#endif
{
    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show_command;

#ifdef __WINE__
    for (;;)
        pause();
#else
    Sleep(INFINITE);
#endif
    return 0;
}
