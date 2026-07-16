#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int wmain(int argc, wchar_t **argv)
{
    SERVICE_STATUS status;
    SC_HANDLE manager;
    SC_HANDLE service;
    DWORD control_code;

    if (argc != 3) {
        fwprintf(stderr, L"Usage: uu-service-control.exe SERVICE CODE\n");
        return 2;
    }

    control_code = wcstoul(argv[2], NULL, 10);
    if (control_code < 128 || control_code > 255) {
        fwprintf(stderr, L"Custom service code must be between 128 and 255\n");
        return 2;
    }

    manager = OpenSCManagerW(NULL, NULL, SC_MANAGER_CONNECT);
    if (manager == NULL) {
        fwprintf(stderr, L"OpenSCManagerW failed: %lu\n", GetLastError());
        return 1;
    }

    service = OpenServiceW(manager, argv[1], SERVICE_USER_DEFINED_CONTROL);
    if (service == NULL) {
        fwprintf(stderr, L"OpenServiceW failed: %lu\n", GetLastError());
        CloseServiceHandle(manager);
        return 1;
    }

    if (!ControlService(service, control_code, &status)) {
        fwprintf(stderr, L"ControlService failed: %lu\n", GetLastError());
        CloseServiceHandle(service);
        CloseServiceHandle(manager);
        return 1;
    }

    CloseServiceHandle(service);
    CloseServiceHandle(manager);
    return 0;
}
