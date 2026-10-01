#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

int wmain(void)
{
    const wchar_t expected[] = L"Copied from Ubuntu 中文\nsecond line “quote” 😀";
    for (unsigned int attempt = 0; attempt < 100; attempt++) {
        if (OpenClipboard(NULL)) {
            HANDLE handle = GetClipboardData(CF_UNICODETEXT);
            const wchar_t *text = handle ? GlobalLock(handle) : NULL;
            wchar_t normalized[256];
            size_t i = 0, j = 0;
            if (text) {
                while (text[i] && j < 255) {
                    if (text[i] != L'\r' || text[i+1] != L'\n')
                        normalized[j++] = text[i];
                    i++;
                }
            }
            normalized[j] = 0;
            BOOL match = text && wcscmp(normalized, expected) == 0;
            if (attempt == 99)
                fprintf(stderr, "clipboard exists=%d units=%u expected=%u\n",
                        text != NULL, (unsigned)j, (unsigned)wcslen(expected));
            if (text) GlobalUnlock(handle);
            CloseClipboard();
            if (match) {
                puts("exact host Unicode reached Win32 clipboard");
                return 0;
            }
        }
        Sleep(50);
    }
    fputs("Win32 clipboard did not match fixture\n", stderr);
    return 1;
}
