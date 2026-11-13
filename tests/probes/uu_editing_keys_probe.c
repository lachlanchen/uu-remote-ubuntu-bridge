#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

static int key(WORD vk, WORD scan, DWORD flags)
{
    INPUT input;
    ZeroMemory(&input, sizeof(input));
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = vk;
    input.ki.wScan = scan;
    input.ki.dwFlags = flags;
    return SendInput(1, &input, sizeof(input)) == 1 ? 0 : 1;
}

static int pair(WORD vk, DWORD flags)
{
    return key(vk, 0, flags) || key(vk, 0, flags | KEYEVENTF_KEYUP);
}

int main(int argc, char **argv)
{
    static const WORD ordinary[] = {VK_BACK, VK_RETURN, VK_TAB, VK_ESCAPE};
    static const WORD extended[] = {VK_DELETE, VK_LEFT, VK_RIGHT, VK_UP,
                                   VK_DOWN, VK_HOME, VK_END, VK_PRIOR,
                                   VK_NEXT, VK_INSERT};
    if (argc != 2 || !LoadLibraryA(argv[1]))
        return 2;
    Sleep(500);
    /* Deliberately exercise the vendor's actual SendInput/IAT entry, not
     * direct requests to the broker, and hold modifiers across calls. */
    for (unsigned i = 0; i < ARRAYSIZE(ordinary); i++)
        if (pair(ordinary[i], 0)) return 3;
    for (unsigned i = 0; i < ARRAYSIZE(extended); i++)
        if (pair(extended[i], KEYEVENTF_EXTENDEDKEY)) return 4;
    if (key(VK_SHIFT, 0, 0) || pair(VK_LEFT, KEYEVENTF_EXTENDEDKEY) ||
        key(VK_SHIFT, 0, KEYEVENTF_KEYUP)) return 5;
    if (key(VK_CONTROL, 0, 0) || pair('A', 0) ||
        key(VK_CONTROL, 0, KEYEVENTF_KEYUP)) return 6;
    if (key(VK_CONTROL, 0, 0) || pair(VK_LEFT, KEYEVENTF_EXTENDEDKEY) ||
        key(VK_CONTROL, 0, KEYEVENTF_KEYUP)) return 7;
    if (key(VK_SHIFT, 0, 0) || pair('A', 0) ||
        key(VK_SHIFT, 0, KEYEVENTF_KEYUP)) return 8;
    if (key(0, 0x0e, KEYEVENTF_SCANCODE) ||
        key(0, 0x0e, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP)) return 9;
    puts("editing-key SendInput requests accepted");
    return 0;
}
