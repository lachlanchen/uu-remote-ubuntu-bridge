#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>

#define LONG_TEXT_CHARACTERS 1000U
#define LONG_TEXT_INPUTS (LONG_TEXT_CHARACTERS * 2U)

int main(int argc, char **argv)
{
    INPUT inputs[LONG_TEXT_INPUTS];
    HMODULE bridge;
    UINT index;
    UINT result;
    DWORD error;

    if (argc < 2 || argc > 3) {
        fprintf(stderr,
                "usage: uu-long-text-probe.exe BRIDGE_DLL [unicode]\n");
        return 2;
    }

    bridge = LoadLibraryA(argv[1]);
    if (bridge == NULL) {
        fprintf(stderr, "LoadLibrary failed: %lu\n",
                (unsigned long)GetLastError());
        return 1;
    }
    /* DllMain starts the deliberately small IAT-patching initializer. */
    Sleep(500);

    ZeroMemory(inputs, sizeof(inputs));
    for (index = 0; index < LONG_TEXT_CHARACTERS; index++) {
        WCHAR character = argc == 3 ? (WCHAR)0x4f60
                                    : (WCHAR)(L'a' + (index % 26U));
        INPUT *press = &inputs[index * 2U];
        INPUT *release = &inputs[index * 2U + 1U];

        press->type = INPUT_KEYBOARD;
        press->ki.wScan = character;
        press->ki.dwFlags = KEYEVENTF_UNICODE;
        *release = *press;
        release->ki.dwFlags |= KEYEVENTF_KEYUP;
    }

    SetLastError(ERROR_SUCCESS);
    result = SendInput(LONG_TEXT_INPUTS, inputs, sizeof(INPUT));
    error = GetLastError();
    printf("requested=%u result=%u error=%lu\n", LONG_TEXT_INPUTS, result,
           (unsigned long)error);
    FreeLibrary(bridge);
    return result == LONG_TEXT_INPUTS && error == ERROR_SUCCESS ? 0 : 1;
}
