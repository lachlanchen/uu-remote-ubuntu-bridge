/* Exercise the real routing function against a Win32 broker pipe. The direct
 * Wine API deliberately reports success without delivering any input. */
#include "../../src/uu_input_bridge.c"

static DWORD direct_calls;
static HANDLE fixture_pipe;
static UINT WINAPI acknowledge_without_delivery(UINT n, LPINPUT p, int size)
{
    (void)p; (void)size;
    direct_calls++;
    SetLastError(0);
    return n;
}

static DWORD WINAPI broker_fixture(void *unused)
{
    (void)unused;
    if (!ConnectNamedPipe(fixture_pipe, NULL) && GetLastError() != ERROR_PIPE_CONNECTED)
        return 10;
    for (unsigned i = 0; i < 3; i++) {
        input_bridge_request request;
        input_bridge_response response;
        INPUT event;
        if (!read_all(fixture_pipe, &request, sizeof(request)) ||
            request.count != 1 || request.input_size != sizeof(event) ||
            !read_all(fixture_pipe, &event, sizeof(event))) return 11;
        response.result = i == 2 ? 0 : 1;
        response.error = i == 2 ? ERROR_ACCESS_DENIED : 0;
        if (!write_all(fixture_pipe, &response, sizeof(response))) return 12;
    }
    return 0;
}

int main(void)
{
    INPUT event;
    HANDLE route, worker;
    DWORD result;
    InitializeCriticalSection(&broker_lock);
    broker_lock_initialized = TRUE;
    original_send_input = acknowledge_without_delivery;
    ZeroMemory(&event, sizeof(event));
    event.type = INPUT_KEYBOARD; event.ki.wVk = VK_BACK;
    if (native_broker_route()) return 1;
    if (bridged_send_input(1, &event, sizeof(event)) != 1 || direct_calls != 1)
        return 2; /* RDP/default direct success preserved. */
    fixture_pipe = CreateNamedPipeW(INPUT_BRIDGE_PIPE, PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT, 1, 4096, 4096, 0, NULL);
    if (fixture_pipe == INVALID_HANDLE_VALUE) return 3;
    worker = CreateThread(NULL, 0, broker_fixture, NULL, 0, NULL);
    route = CreateEventW(NULL, TRUE, TRUE, UURB_NATIVE_INPUT_EVENT);
    if (!worker || !route || !native_broker_route()) return 4;
    if (bridged_send_input(1, &event, sizeof(event)) != 1 || direct_calls != 1)
        return 5; /* Native editing bypasses false-success API. */
    CloseHandle(route);
    if (native_broker_route()) return 6; /* No retained reader handle. */
    if (bridged_send_input(1, &event, sizeof(event)) != 1 || direct_calls != 2)
        return 7;
    event.ki.wVk = 0; event.ki.wScan = 0x4e2d; event.ki.dwFlags = KEYEVENTF_UNICODE;
    if (bridged_send_input(1, &event, sizeof(event)) != 1 || direct_calls != 2)
        return 8; /* Unicode always uses broker. */
    route = CreateEventW(NULL, TRUE, TRUE, UURB_NATIVE_INPUT_EVENT);
    event.ki.wVk = VK_DELETE; event.ki.wScan = 0; event.ki.dwFlags = KEYEVENTF_EXTENDEDKEY;
    if (bridged_send_input(1, &event, sizeof(event)) != 0 || direct_calls != 2)
        return 9; /* Broker failure must not replay on the private desktop. */
    if (WaitForSingleObject(worker, 5000) != WAIT_OBJECT_0 ||
        !GetExitCodeThread(worker, &result) || result) return 13;
    CloseHandle(worker); CloseHandle(route); disconnect_broker();
    CloseHandle(fixture_pipe); DeleteCriticalSection(&broker_lock);
    puts("PASS: native edit routing, RDP compatibility, Unicode, no replay, marker lifetime");
    return 0;
}
