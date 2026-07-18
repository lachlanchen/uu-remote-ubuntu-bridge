#define _GNU_SOURCE
#include <arpa/inet.h>
#include <ctype.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "x11_input_protocol.h"

/* Keep the helper buildable with runtime X11 libraries only. */
typedef struct _XDisplay Display;
typedef int Bool;
typedef Display *(*x_open_display_fn)(const char *);
typedef int (*x_close_display_fn)(Display *);
typedef int (*x_sync_fn)(Display *, Bool);
typedef Bool (*xtest_query_extension_fn)(Display *, int *, int *, int *, int *);
typedef Bool (*xtest_fake_key_event_fn)(Display *, unsigned int, Bool,
                                        unsigned long);

typedef struct x11_api {
    void *x11_library;
    void *xtst_library;
    x_open_display_fn open_display;
    x_close_display_fn close_display;
    x_sync_fn sync;
    xtest_query_extension_fn query_extension;
    xtest_fake_key_event_fn fake_key_event;
} x11_api;

static volatile sig_atomic_t stop_requested;
static volatile sig_atomic_t listener_fd = -1;
static volatile sig_atomic_t active_client_fd = -1;

static void handle_signal(int signal_number)
{
    int fd;

    (void)signal_number;
    stop_requested = 1;
    fd = listener_fd;
    listener_fd = -1;
    if (fd >= 0)
        close(fd);
    fd = active_client_fd;
    active_client_fd = -1;
    if (fd >= 0)
        close(fd);
}

static bool read_all(int fd, void *buffer, size_t size)
{
    unsigned char *position = buffer;

    while (size > 0) {
        ssize_t received = recv(fd, position, size, 0);

        if (received == 0)
            return false;
        if (received < 0) {
            if (errno == EINTR)
                continue;
            return false;
        }
        position += (size_t)received;
        size -= (size_t)received;
    }
    return true;
}

static bool write_all(int fd, const void *buffer, size_t size)
{
    const unsigned char *position = buffer;

    while (size > 0) {
        ssize_t written = send(fd, position, size, MSG_NOSIGNAL);

        if (written < 0) {
            if (errno == EINTR)
                continue;
            return false;
        }
        if (written == 0)
            return false;
        position += (size_t)written;
        size -= (size_t)written;
    }
    return true;
}

static uint64_t monotonic_milliseconds(void)
{
    struct timespec value;

    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0)
        return 0;
    return (uint64_t)value.tv_sec * UINT64_C(1000) +
           (uint64_t)value.tv_nsec / UINT64_C(1000000);
}

static void sleep_milliseconds(uint64_t milliseconds)
{
    struct timespec delay;

    delay.tv_sec = (time_t)(milliseconds / UINT64_C(1000));
    delay.tv_nsec = (long)(milliseconds % UINT64_C(1000)) * 1000000L;
    while (nanosleep(&delay, &delay) != 0 && errno == EINTR)
        ;
}

static unsigned int extended_scan_to_x_keycode(unsigned int scan)
{
    switch (scan) {
    case 0x1c:
        return 108; /* keypad Enter */
    case 0x1d:
        return 109; /* right Control */
    case 0x35:
        return 112; /* keypad Divide */
    case 0x37:
        return 111; /* Print */
    case 0x38:
        return 113; /* right Alt */
    case 0x47:
        return 97;  /* Home */
    case 0x48:
        return 98;  /* Up */
    case 0x49:
        return 99;  /* Page Up */
    case 0x4b:
        return 100; /* Left */
    case 0x4d:
        return 102; /* Right */
    case 0x4f:
        return 103; /* End */
    case 0x50:
        return 104; /* Down */
    case 0x51:
        return 105; /* Page Down */
    case 0x52:
        return 106; /* Insert */
    case 0x53:
        return 107; /* Delete */
    case 0x5b:
        return 115; /* left Super */
    case 0x5c:
        return 116; /* right Super */
    case 0x5d:
        return 117; /* Menu */
    default:
        return 0;
    }
}

static unsigned int event_to_x_keycode(const uurb_x11_key_event *event)
{
    unsigned int scan = event->scan_code & 0xffU;

    if (scan == 0 || (event->flags & UURB_KEYEVENTF_UNICODE) != 0)
        return 0;
    if ((event->flags & UURB_KEYEVENTF_EXTENDED) != 0)
        return extended_scan_to_x_keycode(scan);
    if (scan > 247U)
        return 0;
    return scan + 8U;
}

static bool load_x11_api(x11_api *api)
{
    int event_base;
    int error_base;
    int major;
    int minor;
    Display *display;

    memset(api, 0, sizeof(*api));
    api->x11_library = dlopen("libX11.so.6", RTLD_NOW | RTLD_LOCAL);
    api->xtst_library = dlopen("libXtst.so.6", RTLD_NOW | RTLD_LOCAL);
    if (!api->x11_library || !api->xtst_library)
        return false;

    api->open_display = (x_open_display_fn)dlsym(api->x11_library,
                                                 "XOpenDisplay");
    api->close_display = (x_close_display_fn)dlsym(api->x11_library,
                                                   "XCloseDisplay");
    api->sync = (x_sync_fn)dlsym(api->x11_library, "XSync");
    api->query_extension = (xtest_query_extension_fn)dlsym(
        api->xtst_library, "XTestQueryExtension");
    api->fake_key_event = (xtest_fake_key_event_fn)dlsym(
        api->xtst_library, "XTestFakeKeyEvent");
    if (!api->open_display || !api->close_display || !api->sync ||
        !api->query_extension || !api->fake_key_event)
        return false;

    display = api->open_display(NULL);
    if (!display)
        return false;
    if (!api->query_extension(display, &event_base, &error_base, &major,
                              &minor)) {
        api->close_display(display);
        return false;
    }
    api->close_display(display);
    return true;
}

static void unload_x11_api(x11_api *api)
{
    if (api->xtst_library)
        dlclose(api->xtst_library);
    if (api->x11_library)
        dlclose(api->x11_library);
    memset(api, 0, sizeof(*api));
}

static bool valid_token(const char *token)
{
    size_t index;

    if (!token || strlen(token) != UURB_X11_INPUT_TOKEN_SIZE)
        return false;
    for (index = 0; index < UURB_X11_INPUT_TOKEN_SIZE; index++) {
        if (!isxdigit((unsigned char)token[index]))
            return false;
    }
    return true;
}

static bool publish_port(const char *path, unsigned int port)
{
    char value[32];
    int fd;
    int length;
    ssize_t written;

    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    if (fd < 0)
        return false;
    length = snprintf(value, sizeof(value), "%u\n", port);
    written = write(fd, value, (size_t)length);
    if (written == length)
        fsync(fd);
    close(fd);
    return written == length;
}

static int create_listener(const char *ready_file)
{
    struct sockaddr_in address;
    socklen_t address_size = sizeof(address);
    int fd;

    fd = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return -1;
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(fd, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(fd, 1) != 0 ||
        getsockname(fd, (struct sockaddr *)&address, &address_size) != 0 ||
        !publish_port(ready_file, ntohs(address.sin_port))) {
        close(fd);
        return -1;
    }
    return fd;
}

static void release_pressed_keys(x11_api *api, Display *display,
                                 bool pressed[256])
{
    unsigned int keycode;
    bool changed = false;

    for (keycode = 8; keycode < 256; keycode++) {
        if (!pressed[keycode])
            continue;
        api->fake_key_event(display, keycode, 0, 0);
        pressed[keycode] = false;
        changed = true;
    }
    if (changed)
        api->sync(display, 0);
}

static bool send_response(int client, uint32_t sequence, uint32_t result,
                          uint32_t error)
{
    uurb_x11_response response;

    response.magic = UURB_X11_INPUT_MAGIC;
    response.sequence = sequence;
    response.result = result;
    response.error = error;
    return write_all(client, &response, sizeof(response));
}

static void serve_client(int client, const char *token, x11_api *api,
                         Display *display, unsigned int minimum_hold_ms)
{
    bool pressed[256] = {false};
    uint64_t pressed_at[256] = {0};
    uurb_x11_handshake handshake;

    if (!read_all(client, &handshake, sizeof(handshake)) ||
        handshake.magic != UURB_X11_INPUT_MAGIC ||
        handshake.version != UURB_X11_INPUT_VERSION ||
        memcmp(handshake.token, token, UURB_X11_INPUT_TOKEN_SIZE) != 0 ||
        !send_response(client, 0, 1, 0))
        return;

    while (!stop_requested) {
        uurb_x11_key_event events[UURB_X11_INPUT_MAX_EVENTS];
        unsigned int keycodes[UURB_X11_INPUT_MAX_EVENTS];
        uurb_x11_request request;
        uint32_t index;
        uint32_t injected = 0;
        uint32_t error = 0;

        if (!read_all(client, &request, sizeof(request)))
            break;
        if (request.magic != UURB_X11_INPUT_MAGIC || request.reserved != 0 ||
            request.count == 0 ||
            request.count > UURB_X11_INPUT_MAX_EVENTS) {
            send_response(client, request.sequence, 0,
                          UURB_X11_ERROR_BAD_REQUEST);
            break;
        }
        if (!read_all(client, events,
                      request.count * sizeof(events[0])))
            break;

        for (index = 0; index < request.count; index++) {
            keycodes[index] = event_to_x_keycode(&events[index]);
            if (keycodes[index] == 0) {
                error = UURB_X11_ERROR_UNSUPPORTED;
                break;
            }
        }
        if (error != 0) {
            if (!send_response(client, request.sequence, 0, error))
                break;
            continue;
        }

        for (index = 0; index < request.count; index++) {
            unsigned int keycode = keycodes[index];
            bool is_release =
                (events[index].flags & UURB_KEYEVENTF_KEYUP) != 0;

            if (is_release && pressed[keycode] && minimum_hold_ms > 0) {
                uint64_t now = monotonic_milliseconds();
                uint64_t elapsed = now - pressed_at[keycode];

                if (elapsed < minimum_hold_ms)
                    sleep_milliseconds(minimum_hold_ms - elapsed);
            }
            if (!api->fake_key_event(display, keycode,
                                     is_release ? 0 : 1, 0)) {
                error = UURB_X11_ERROR_INJECTION;
                break;
            }
            pressed[keycode] = !is_release;
            if (!is_release)
                pressed_at[keycode] = monotonic_milliseconds();
            injected++;
        }
        api->sync(display, 0);
        if (!send_response(client, request.sequence,
                           error == 0 ? request.count : injected, error))
            break;
    }
    release_pressed_keys(api, display, pressed);
}

static void usage(const char *program)
{
    fprintf(stderr,
            "usage: UURB_X11_INPUT_TOKEN=HEX64 %s --ready-file PATH "
            "[--min-hold-ms 0..50]\n",
            program);
}

int main(int argc, char **argv)
{
    const char *ready_file = NULL;
    const char *token = getenv("UURB_X11_INPUT_TOKEN");
    unsigned int minimum_hold_ms = 0;
    struct sigaction action;
    x11_api api;
    Display *display;
    int index;
    int status = EXIT_FAILURE;

    for (index = 1; index < argc; index++) {
        if (strcmp(argv[index], "--ready-file") == 0 && index + 1 < argc) {
            ready_file = argv[++index];
        } else if (strcmp(argv[index], "--min-hold-ms") == 0 &&
                   index + 1 < argc) {
            char *end = NULL;
            unsigned long parsed = strtoul(argv[++index], &end, 10);

            if (end == argv[index] || *end != '\0' || parsed > 50) {
                usage(argv[0]);
                return EXIT_FAILURE;
            }
            minimum_hold_ms = (unsigned int)parsed;
        } else {
            usage(argv[0]);
            return EXIT_FAILURE;
        }
    }
    if (!ready_file || !valid_token(token)) {
        usage(argv[0]);
        return EXIT_FAILURE;
    }
    if (!load_x11_api(&api)) {
        fprintf(stderr, "X11 XTEST runtime is unavailable.\n");
        return EXIT_FAILURE;
    }
    display = api.open_display(NULL);
    if (!display) {
        fprintf(stderr, "Cannot open the selected X11 desktop.\n");
        unload_x11_api(&api);
        return EXIT_FAILURE;
    }

    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);

    listener_fd = create_listener(ready_file);
    if (listener_fd < 0) {
        fprintf(stderr, "Cannot create the private X11 input listener.\n");
        goto cleanup;
    }
    fprintf(stderr, "X11 input helper ready; minimum-hold-ms=%u.\n",
            minimum_hold_ms);

    while (!stop_requested) {
        int client = accept(listener_fd, NULL, NULL);

        if (client < 0) {
            if (errno == EINTR)
                continue;
            if (!stop_requested)
                fprintf(stderr, "X11 input listener failed: %s\n",
                        strerror(errno));
            break;
        }
        active_client_fd = client;
        serve_client(client, token, &api, display, minimum_hold_ms);
        active_client_fd = -1;
        close(client);
    }
    status = stop_requested ? EXIT_SUCCESS : EXIT_FAILURE;

cleanup:
    if (listener_fd >= 0)
        close(listener_fd);
    unlink(ready_file);
    api.close_display(display);
    unload_x11_api(&api);
    return status;
}
