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
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "x11_input_protocol.h"

#define UURB_SELECTION_QUIET_MS UINT64_C(50)
#define UURB_SELECTION_READY_TIMEOUT_MS UINT64_C(500)
#define UURB_SELECTION_REQUEST_TIMEOUT_MS UINT64_C(1500)
#define UURB_SELECTION_POST_REQUEST_MS UINT64_C(50)
#define UURB_BACKSPACE_SETTLE_MS UINT64_C(5)
#define UURB_RELAY_PASTE_KEY_DELAY_MS UINT64_C(20)
#define UURB_VK_BACK UINT16_C(0x08)
#define UURB_SELECTION_STATUS_CAPACITY 512U

/* Keep the helper buildable with runtime X11 libraries only. */
typedef struct _XDisplay Display;
typedef int Bool;
typedef unsigned long Atom;
typedef unsigned long KeySym;
typedef unsigned long Window;
typedef unsigned char KeyCode;
typedef Display *(*x_open_display_fn)(const char *);
typedef int (*x_close_display_fn)(Display *);
typedef int (*x_sync_fn)(Display *, Bool);
typedef Atom (*x_intern_atom_fn)(Display *, const char *, Bool);
typedef Window (*x_get_selection_owner_fn)(Display *, Atom);
typedef int (*x_default_screen_fn)(Display *);
typedef int (*x_display_dimension_fn)(Display *, int);
typedef KeyCode (*x_keysym_to_keycode_fn)(Display *, KeySym);
typedef Bool (*xtest_query_extension_fn)(Display *, int *, int *, int *, int *);
typedef Bool (*xtest_fake_key_event_fn)(Display *, unsigned int, Bool,
                                        unsigned long);
typedef Bool (*xtest_fake_button_event_fn)(Display *, unsigned int, Bool,
                                           unsigned long);
typedef Bool (*xtest_fake_motion_event_fn)(Display *, int, int, int,
                                           unsigned long);
typedef Bool (*xtest_fake_relative_motion_event_fn)(Display *, int, int,
                                                    unsigned long);

typedef struct x11_api {
    void *x11_library;
    void *xtst_library;
    x_open_display_fn open_display;
    x_close_display_fn close_display;
    x_sync_fn sync;
    x_intern_atom_fn intern_atom;
    x_get_selection_owner_fn get_selection_owner;
    x_default_screen_fn default_screen;
    x_display_dimension_fn display_width;
    x_display_dimension_fn display_height;
    x_keysym_to_keycode_fn keysym_to_keycode;
    xtest_query_extension_fn query_extension;
    xtest_fake_key_event_fn fake_key_event;
    xtest_fake_button_event_fn fake_button_event;
    xtest_fake_motion_event_fn fake_motion_event;
    xtest_fake_relative_motion_event_fn fake_relative_motion_event;
} x11_api;

typedef struct selection_status {
    char buffer[UURB_SELECTION_STATUS_CAPACITY];
    size_t length;
    unsigned long next_request_number;
} selection_status;

static volatile sig_atomic_t stop_requested;
static volatile sig_atomic_t listener_fd = -1;
static volatile sig_atomic_t active_client_fd = -1;
static volatile sig_atomic_t clipboard_owner_pid = -1;
static volatile sig_atomic_t primary_owner_pid = -1;
static volatile sig_atomic_t clipboard_status_fd = -1;
static volatile sig_atomic_t primary_status_fd = -1;
static selection_status clipboard_status;
static selection_status primary_status;

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
    fd = clipboard_owner_pid;
    clipboard_owner_pid = -1;
    if (fd > 0)
        kill(fd, SIGTERM);
    fd = primary_owner_pid;
    primary_owner_pid = -1;
    if (fd > 0)
        kill(fd, SIGTERM);
    fd = clipboard_status_fd;
    clipboard_status_fd = -1;
    if (fd >= 0)
        close(fd);
    fd = primary_status_fd;
    primary_status_fd = -1;
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

static bool write_fd_all(int fd, const void *buffer, size_t size)
{
    const unsigned char *position = buffer;

    while (size > 0) {
        ssize_t written = write(fd, position, size);

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

static void reset_selection_status(selection_status *status)
{
    memset(status, 0, sizeof(*status));
}

static void stop_selection_owner(volatile sig_atomic_t *owner_pid,
                                 volatile sig_atomic_t *status_fd,
                                 selection_status *status)
{
    pid_t pid = (pid_t)*owner_pid;
    int fd = (int)*status_fd;
    int wait_status;
    unsigned int attempt;

    *owner_pid = -1;
    *status_fd = -1;
    if (fd >= 0)
        close(fd);
    reset_selection_status(status);
    if (pid <= 0)
        return;
    kill(pid, SIGTERM);
    for (attempt = 0; attempt < 25; attempt++) {
        pid_t result = waitpid(pid, &wait_status, WNOHANG);

        if (result == pid || (result < 0 && errno == ECHILD))
            return;
        if (result < 0 && errno != EINTR)
            break;
        sleep_milliseconds(2);
    }
    kill(pid, SIGKILL);
    while (waitpid(pid, &wait_status, 0) < 0 && errno == EINTR)
        ;
}

static void stop_clipboard_owner(void)
{
    stop_selection_owner(&clipboard_owner_pid, &clipboard_status_fd,
                         &clipboard_status);
    stop_selection_owner(&primary_owner_pid, &primary_status_fd,
                         &primary_status);
}

static void update_selection_status(int fd, selection_status *status)
{
    if (fd < 0)
        return;

    for (;;) {
        ssize_t received;
        char *line_start;
        char *newline;

        if (status->length == sizeof(status->buffer) - 1)
            status->length = 0;
        received = read(fd, status->buffer + status->length,
                        sizeof(status->buffer) - status->length - 1);
        if (received < 0) {
            if (errno == EINTR)
                continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK)
                break;
            return;
        }
        if (received == 0)
            break;
        status->length += (size_t)received;
        status->buffer[status->length] = '\0';
        line_start = status->buffer;
        while ((newline = strchr(line_start, '\n')) != NULL) {
            static const char marker[] =
                "Waiting for selection request number ";
            char *number;

            *newline = '\0';
            number = strstr(line_start, marker);
            if (number != NULL) {
                char *end = NULL;
                unsigned long parsed;

                number += sizeof(marker) - 1;
                parsed = strtoul(number, &end, 10);
                if (end != number && parsed > status->next_request_number)
                    status->next_request_number = parsed;
            }
            line_start = newline + 1;
        }
        if (line_start != status->buffer) {
            size_t remaining = status->length -
                               (size_t)(line_start - status->buffer);

            memmove(status->buffer, line_start, remaining);
            status->length = remaining;
            status->buffer[remaining] = '\0';
        }
    }
}

static unsigned long completed_selection_requests(
    const selection_status *status)
{
    return status->next_request_number > 0 ?
           status->next_request_number - 1 : 0;
}

static bool selection_owner_alive(volatile sig_atomic_t *owner_pid)
{
    pid_t pid = (pid_t)*owner_pid;
    int status;
    pid_t result;

    if (pid <= 0)
        return false;
    result = waitpid(pid, &status, WNOHANG);
    if (result == 0 || (result < 0 && errno == EINTR))
        return true;
    if (result == pid || (result < 0 && errno == ECHILD))
        *owner_pid = -1;
    return false;
}

static bool selection_owners_quiet(unsigned long *clipboard_baseline,
                                   unsigned long *primary_baseline)
{
    uint64_t deadline = monotonic_milliseconds() +
                        UURB_SELECTION_READY_TIMEOUT_MS;
    uint64_t quiet_since = monotonic_milliseconds();
    unsigned long prior_clipboard = 0;
    unsigned long prior_primary = 0;

    while (!stop_requested && monotonic_milliseconds() <= deadline) {
        unsigned long current_clipboard;
        unsigned long current_primary;

        update_selection_status((int)clipboard_status_fd,
                                &clipboard_status);
        update_selection_status((int)primary_status_fd, &primary_status);
        current_clipboard = completed_selection_requests(&clipboard_status);
        current_primary = completed_selection_requests(&primary_status);
        if (current_clipboard != prior_clipboard ||
            current_primary != prior_primary) {
            prior_clipboard = current_clipboard;
            prior_primary = current_primary;
            quiet_since = monotonic_milliseconds();
        }
        if (clipboard_status.next_request_number > 0 &&
            primary_status.next_request_number > 0 &&
            monotonic_milliseconds() - quiet_since >=
                UURB_SELECTION_QUIET_MS) {
            *clipboard_baseline = current_clipboard;
            *primary_baseline = current_primary;
            return true;
        }
        if (!selection_owner_alive(&clipboard_owner_pid) ||
            !selection_owner_alive(&primary_owner_pid))
            return false;
        sleep_milliseconds(5);
    }
    return false;
}

static bool wait_for_selection_request(unsigned long clipboard_baseline,
                                       unsigned long primary_baseline)
{
    uint64_t deadline = monotonic_milliseconds() +
                        UURB_SELECTION_REQUEST_TIMEOUT_MS;

    while (!stop_requested && monotonic_milliseconds() <= deadline) {
        update_selection_status((int)clipboard_status_fd,
                                &clipboard_status);
        update_selection_status((int)primary_status_fd, &primary_status);
        if (completed_selection_requests(&clipboard_status) >
                clipboard_baseline ||
            completed_selection_requests(&primary_status) >
                primary_baseline) {
            sleep_milliseconds(UURB_SELECTION_POST_REQUEST_MS);
            update_selection_status((int)clipboard_status_fd,
                                    &clipboard_status);
            update_selection_status((int)primary_status_fd,
                                    &primary_status);
            return true;
        }
        if (!selection_owner_alive(&clipboard_owner_pid) ||
            !selection_owner_alive(&primary_owner_pid))
            return false;
        sleep_milliseconds(5);
    }
    return false;
}

static bool start_selection_owner(const x11_api *api, Display *display,
                                  const char *selection_name,
                                  const char *text, size_t size,
                                  volatile sig_atomic_t *owner_pid,
                                  volatile sig_atomic_t *status_fd,
                                  selection_status *owner_status)
{
    int input_pipe[2];
    int status_pipe[2];
    int status_flags;
    pid_t pid;
    int status;
    int null_fd;
    unsigned int attempt;
    Atom clipboard;
    Window previous_owner;
    Window current_owner = 0;

    clipboard = api->intern_atom(display, selection_name, 0);
    if (clipboard == 0)
        return false;
    api->sync(display, 0);
    previous_owner = api->get_selection_owner(display, clipboard);
    if (pipe2(input_pipe, O_CLOEXEC) != 0)
        return false;
    if (pipe2(status_pipe, O_CLOEXEC) != 0) {
        close(input_pipe[0]);
        close(input_pipe[1]);
        return false;
    }
    pid = fork();
    if (pid < 0) {
        close(input_pipe[0]);
        close(input_pipe[1]);
        close(status_pipe[0]);
        close(status_pipe[1]);
        return false;
    }
    if (pid == 0) {
        if (dup2(input_pipe[0], STDIN_FILENO) < 0)
            _exit(126);
        close(input_pipe[0]);
        close(input_pipe[1]);
        close(status_pipe[0]);
        if (dup2(status_pipe[1], STDERR_FILENO) < 0)
            _exit(126);
        close(status_pipe[1]);
        null_fd = open("/dev/null", O_WRONLY | O_CLOEXEC);
        if (null_fd >= 0) {
            dup2(null_fd, STDOUT_FILENO);
            close(null_fd);
        }
        setenv("LC_ALL", "C.UTF-8", 1);
        execl("/usr/bin/xclip", "xclip", "-selection", selection_name,
              "-in", "-loops", "0", "-verbose", (char *)NULL);
        _exit(127);
    }

    close(input_pipe[0]);
    close(status_pipe[1]);
    *owner_pid = (sig_atomic_t)pid;
    *status_fd = (sig_atomic_t)status_pipe[0];
    reset_selection_status(owner_status);
    status_flags = fcntl(status_pipe[0], F_GETFL);
    if (status_flags < 0 ||
        fcntl(status_pipe[0], F_SETFL, status_flags | O_NONBLOCK) < 0) {
        close(input_pipe[1]);
        stop_selection_owner(owner_pid, status_fd, owner_status);
        return false;
    }
    if (!write_fd_all(input_pipe[1], text, size)) {
        close(input_pipe[1]);
        stop_selection_owner(owner_pid, status_fd, owner_status);
        return false;
    }
    close(input_pipe[1]);

    /* Never paste on the strength of a timer alone.  A busy desktop can leave
     * xclip alive but not yet owning CLIPBOARD, which would make Shift+Insert
     * paste stale user data.  Wait for a new, non-None owner and fail closed. */
    for (attempt = 0; attempt < 100; attempt++) {
        pid_t result;

        api->sync(display, 0);
        current_owner = api->get_selection_owner(display, clipboard);
        if (current_owner != 0 && current_owner != previous_owner)
            break;
        result = waitpid(pid, &status, WNOHANG);
        if (result == pid || (result < 0 && errno == ECHILD)) {
            *owner_pid = -1;
            return false;
        }
        if (result < 0 && errno != EINTR)
            break;
        sleep_milliseconds(5);
    }
    if (current_owner == 0 || current_owner == previous_owner) {
        stop_selection_owner(owner_pid, status_fd, owner_status);
        return false;
    }
    return true;
}

static bool start_clipboard_owner(const x11_api *api, Display *display,
                                  const char *text, size_t size,
                                  unsigned long *clipboard_baseline,
                                  unsigned long *primary_baseline)
{
    stop_clipboard_owner();
    if (!start_selection_owner(api, display, "CLIPBOARD", text, size,
                               &clipboard_owner_pid, &clipboard_status_fd,
                               &clipboard_status) ||
        !start_selection_owner(api, display, "PRIMARY", text, size,
                               &primary_owner_pid, &primary_status_fd,
                               &primary_status) ||
        !selection_owners_quiet(clipboard_baseline, primary_baseline)) {
        stop_clipboard_owner();
        return false;
    }
    return true;
}

static bool append_utf8(char *output, size_t capacity, size_t *length,
                        uint32_t codepoint)
{
    unsigned int bytes;

    if (codepoint == 0 || codepoint > UINT32_C(0x10ffff) ||
        (codepoint >= UINT32_C(0xd800) &&
         codepoint <= UINT32_C(0xdfff)))
        return false;
    if (codepoint <= UINT32_C(0x7f))
        bytes = 1;
    else if (codepoint <= UINT32_C(0x7ff))
        bytes = 2;
    else if (codepoint <= UINT32_C(0xffff))
        bytes = 3;
    else
        bytes = 4;
    if (*length + bytes >= capacity)
        return false;

    if (bytes == 1) {
        output[(*length)++] = (char)codepoint;
    } else if (bytes == 2) {
        output[(*length)++] = (char)(UINT32_C(0xc0) | (codepoint >> 6));
        output[(*length)++] = (char)(UINT32_C(0x80) |
                                     (codepoint & UINT32_C(0x3f)));
    } else if (bytes == 3) {
        output[(*length)++] = (char)(UINT32_C(0xe0) | (codepoint >> 12));
        output[(*length)++] = (char)(UINT32_C(0x80) |
                                     ((codepoint >> 6) & UINT32_C(0x3f)));
        output[(*length)++] = (char)(UINT32_C(0x80) |
                                     (codepoint & UINT32_C(0x3f)));
    } else {
        output[(*length)++] = (char)(UINT32_C(0xf0) | (codepoint >> 18));
        output[(*length)++] = (char)(UINT32_C(0x80) |
                                     ((codepoint >> 12) & UINT32_C(0x3f)));
        output[(*length)++] = (char)(UINT32_C(0x80) |
                                     ((codepoint >> 6) & UINT32_C(0x3f)));
        output[(*length)++] = (char)(UINT32_C(0x80) |
                                     (codepoint & UINT32_C(0x3f)));
    }
    return true;
}

static bool valid_text_event(const uurb_x11_input_event *event)
{
    return event->type == UURB_X11_INPUT_TEXT && event->flags == 0 &&
           event->x == 0 && event->y == 0 && event->virtual_key == 0 &&
           event->scan_code == 0 && event->data <= UINT32_C(0xffff);
}

static bool text_events_to_utf8(const uurb_x11_input_event *events,
                                uint32_t count, char *output,
                                size_t capacity, size_t *length,
                                bool *previous_ended_cr,
                                uint32_t *pending_high_surrogate)
{
    uint32_t index = 0;

    *length = 0;
    if (*pending_high_surrogate != 0) {
        uint32_t low;
        uint32_t codepoint;

        if (!valid_text_event(&events[0])) {
            *pending_high_surrogate = 0;
            return false;
        }
        low = events[0].data;
        if (low < UINT32_C(0xdc00) || low > UINT32_C(0xdfff)) {
            *pending_high_surrogate = 0;
            return false;
        }
        codepoint = UINT32_C(0x10000) +
                    ((*pending_high_surrogate - UINT32_C(0xd800)) << 10) +
                    (low - UINT32_C(0xdc00));
        *pending_high_surrogate = 0;
        if (!append_utf8(output, capacity, length, codepoint))
            return false;
        index = 1;
    }
    for (; index < count; index++) {
        uint32_t unit;
        uint32_t codepoint;

        if (!valid_text_event(&events[index]))
            return false;
        unit = events[index].data;
        if (unit == (uint32_t)'\n' && *previous_ended_cr) {
            *previous_ended_cr = false;
            continue;
        }
        *previous_ended_cr = false;
        if (unit == (uint32_t)'\r') {
            codepoint = (uint32_t)'\n';
            if (index + 1 < count &&
                valid_text_event(&events[index + 1]) &&
                events[index + 1].data == (uint32_t)'\n') {
                index++;
            } else {
                *previous_ended_cr = true;
            }
        } else if (unit >= UINT32_C(0xd800) &&
                   unit <= UINT32_C(0xdbff)) {
            uint32_t low;

            if (index + 1 >= count) {
                *pending_high_surrogate = unit;
                continue;
            }
            if (!valid_text_event(&events[index + 1]))
                return false;
            low = events[++index].data;
            if (low < UINT32_C(0xdc00) || low > UINT32_C(0xdfff))
                return false;
            codepoint = UINT32_C(0x10000) +
                        ((unit - UINT32_C(0xd800)) << 10) +
                        (low - UINT32_C(0xdc00));
        } else if (unit >= UINT32_C(0xdc00) &&
                   unit <= UINT32_C(0xdfff)) {
            return false;
        } else {
            codepoint = unit;
        }
        if (!append_utf8(output, capacity, length, codepoint))
            return false;
    }
    output[*length] = '\0';
    return true;
}

static bool inject_clipboard_text(const x11_api *api,
                                  Display *clipboard_display,
                                  Display *injection_display,
                                  const char *text, size_t size,
                                  bool pressed_keys[256])
{
    const KeySym shift_left = 0xffe1UL;
    const KeySym insert = 0xff63UL;
    unsigned int shift_keycode;
    unsigned int insert_keycode;
    bool shift_was_pressed;
    bool shift_pressed_here = false;
    bool insert_pressed = false;
    uint64_t key_delay_ms;
    unsigned long clipboard_baseline;
    unsigned long primary_baseline;

    if (size == 0)
        return true;
    shift_keycode = api->keysym_to_keycode(injection_display, shift_left);
    insert_keycode = api->keysym_to_keycode(injection_display, insert);
    if (shift_keycode == 0 || shift_keycode >= 256 ||
        insert_keycode == 0 || insert_keycode >= 256 ||
        !start_clipboard_owner(api, clipboard_display, text, size,
                               &clipboard_baseline, &primary_baseline))
        return false;

    shift_was_pressed = pressed_keys[shift_keycode];
    key_delay_ms = injection_display == clipboard_display ? 0 :
                   UURB_RELAY_PASTE_KEY_DELAY_MS;
    if (!shift_was_pressed) {
        if (!api->fake_key_event(injection_display, shift_keycode, 1, 0))
            goto injection_failed;
        shift_pressed_here = true;
        api->sync(injection_display, 0);
        sleep_milliseconds(key_delay_ms);
    }
    if (!api->fake_key_event(injection_display, insert_keycode, 1, 0))
        goto injection_failed;
    insert_pressed = true;
    api->sync(injection_display, 0);
    sleep_milliseconds(key_delay_ms);
    if (!api->fake_key_event(injection_display, insert_keycode, 0, 0))
        goto injection_failed;
    insert_pressed = false;
    api->sync(injection_display, 0);
    sleep_milliseconds(key_delay_ms);
    if (shift_pressed_here) {
        if (!api->fake_key_event(injection_display, shift_keycode, 0, 0))
            goto injection_failed;
        shift_pressed_here = false;
    }
    api->sync(injection_display, 0);

    /* xclip announces each completed selection request on its private status
     * pipe. Initial clipboard-manager reads are allowed to settle before the
     * paste, then at least one new request must follow the synthetic chord.
     * Do not grant revision credit merely because ownership changed. */
    if (!wait_for_selection_request(clipboard_baseline, primary_baseline)) {
        stop_clipboard_owner();
        return false;
    }
    return true;

injection_failed:
    if (insert_pressed)
        api->fake_key_event(injection_display, insert_keycode, 0, 0);
    if (shift_pressed_here)
        api->fake_key_event(injection_display, shift_keycode, 0, 0);
    api->sync(injection_display, 0);
    stop_clipboard_owner();
    return false;
}

static KeySym extended_scan_to_keysym(unsigned int scan)
{
    switch (scan) {
    case 0x1c:
        return 0xff8dUL; /* XK_KP_Enter */
    case 0x1d:
        return 0xffe4UL; /* XK_Control_R */
    case 0x35:
        return 0xffafUL; /* XK_KP_Divide */
    case 0x37:
        return 0xff61UL; /* XK_Print */
    case 0x38:
        return 0xffeaUL; /* XK_Alt_R */
    case 0x47:
        return 0xff50UL; /* XK_Home */
    case 0x48:
        return 0xff52UL; /* XK_Up */
    case 0x49:
        return 0xff55UL; /* XK_Prior */
    case 0x4b:
        return 0xff51UL; /* XK_Left */
    case 0x4d:
        return 0xff53UL; /* XK_Right */
    case 0x4f:
        return 0xff57UL; /* XK_End */
    case 0x50:
        return 0xff54UL; /* XK_Down */
    case 0x51:
        return 0xff56UL; /* XK_Next */
    case 0x52:
        return 0xff63UL; /* XK_Insert */
    case 0x53:
        return 0xffffUL; /* XK_Delete */
    case 0x5b:
        return 0xffebUL; /* XK_Super_L */
    case 0x5c:
        return 0xffecUL; /* XK_Super_R */
    case 0x5d:
        return 0xff67UL; /* XK_Menu */
    default:
        return 0;
    }
}

static unsigned int event_to_x_keycode(const x11_api *api, Display *display,
                                       const uurb_x11_input_event *event)
{
    unsigned int scan = event->scan_code & 0xffU;

    if (scan == 0 || (event->flags & UURB_KEYEVENTF_UNICODE) != 0)
        return 0;
    if ((event->flags & UURB_KEYEVENTF_EXTENDED) != 0) {
        KeySym keysym = extended_scan_to_keysym(scan);

        if (keysym == 0)
            return 0;
        return api->keysym_to_keycode(display, keysym);
    }
    if (scan > 247U)
        return 0;
    return scan + 8U;
}

static bool valid_mouse_event(const uurb_x11_input_event *event)
{
    const uint32_t allowed_flags =
        UURB_MOUSEEVENTF_MOVE | UURB_MOUSEEVENTF_LEFTDOWN |
        UURB_MOUSEEVENTF_LEFTUP | UURB_MOUSEEVENTF_RIGHTDOWN |
        UURB_MOUSEEVENTF_RIGHTUP | UURB_MOUSEEVENTF_MIDDLEDOWN |
        UURB_MOUSEEVENTF_MIDDLEUP | UURB_MOUSEEVENTF_XDOWN |
        UURB_MOUSEEVENTF_XUP | UURB_MOUSEEVENTF_WHEEL |
        UURB_MOUSEEVENTF_HWHEEL | UURB_MOUSEEVENTF_MOVE_NOCOALESCE |
        UURB_MOUSEEVENTF_VIRTUALDESK | UURB_MOUSEEVENTF_ABSOLUTE;
    uint32_t xbutton;

    if ((event->flags & ~allowed_flags) != 0)
        return false;
    if ((event->flags & (UURB_MOUSEEVENTF_WHEEL |
                         UURB_MOUSEEVENTF_HWHEEL)) ==
        (UURB_MOUSEEVENTF_WHEEL | UURB_MOUSEEVENTF_HWHEEL))
        return false;
    if ((event->flags & (UURB_MOUSEEVENTF_WHEEL |
                         UURB_MOUSEEVENTF_HWHEEL)) != 0 &&
        (int32_t)event->data == 0)
        return false;
    if ((event->flags & (UURB_MOUSEEVENTF_XDOWN |
                         UURB_MOUSEEVENTF_XUP)) == 0)
        return true;

    xbutton = event->data & UINT32_C(0xffff);
    return xbutton == 1U || xbutton == 2U;
}

static int normalized_coordinate(int32_t value, int extent)
{
    int64_t clamped = value;

    if (clamped < 0)
        clamped = 0;
    if (clamped > 65535)
        clamped = 65535;
    if (extent <= 1)
        return 0;
    return (int)((clamped * (extent - 1) + 32767) / 65535);
}

static bool fake_button(const x11_api *api, Display *display,
                        unsigned int button, bool press,
                        bool pressed_buttons[10])
{
    if (button == 0 || button >= 10 ||
        !api->fake_button_event(display, button, press ? 1 : 0, 0))
        return false;
    pressed_buttons[button] = press;
    return true;
}

static unsigned int wheel_steps(int32_t delta)
{
    int64_t magnitude = delta;
    uint64_t steps;

    if (magnitude < 0)
        magnitude = -magnitude;
    steps = ((uint64_t)magnitude + UINT64_C(119)) / UINT64_C(120);
    if (steps > 32U)
        steps = 32U;
    return (unsigned int)steps;
}

static bool fake_wheel(const x11_api *api, Display *display,
                       unsigned int button, unsigned int steps,
                       bool pressed_buttons[10])
{
    unsigned int index;

    for (index = 0; index < steps; index++) {
        if (!fake_button(api, display, button, true, pressed_buttons) ||
            !fake_button(api, display, button, false, pressed_buttons))
            return false;
    }
    return true;
}

static bool inject_mouse_event(const x11_api *api, Display *display,
                               const uurb_x11_input_event *event,
                               bool pressed_buttons[10])
{
    uint32_t flags = event->flags;

    if ((flags & UURB_MOUSEEVENTF_MOVE) != 0) {
        if ((flags & UURB_MOUSEEVENTF_ABSOLUTE) != 0) {
            int screen = api->default_screen(display);
            int width = api->display_width(display, screen);
            int height = api->display_height(display, screen);

            if (!api->fake_motion_event(
                    display, screen,
                    normalized_coordinate(event->x, width),
                    normalized_coordinate(event->y, height), 0))
                return false;
        } else if (!api->fake_relative_motion_event(
                       display, event->x, event->y, 0)) {
            return false;
        }
    }
    if ((flags & UURB_MOUSEEVENTF_LEFTDOWN) != 0 &&
        !fake_button(api, display, 1, true, pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_LEFTUP) != 0 &&
        !fake_button(api, display, 1, false, pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_RIGHTDOWN) != 0 &&
        !fake_button(api, display, 3, true, pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_RIGHTUP) != 0 &&
        !fake_button(api, display, 3, false, pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_MIDDLEDOWN) != 0 &&
        !fake_button(api, display, 2, true, pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_MIDDLEUP) != 0 &&
        !fake_button(api, display, 2, false, pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_XDOWN) != 0 &&
        !fake_button(api, display,
                     (event->data & UINT32_C(0xffff)) == 1U ? 8U : 9U, true,
                     pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_XUP) != 0 &&
        !fake_button(api, display,
                     (event->data & UINT32_C(0xffff)) == 1U ? 8U : 9U, false,
                     pressed_buttons))
        return false;
    if ((flags & UURB_MOUSEEVENTF_WHEEL) != 0) {
        int32_t delta = (int32_t)event->data;

        if (!fake_wheel(api, display, delta > 0 ? 4U : 5U,
                        wheel_steps(delta), pressed_buttons))
            return false;
    }
    if ((flags & UURB_MOUSEEVENTF_HWHEEL) != 0) {
        int32_t delta = (int32_t)event->data;

        if (!fake_wheel(api, display, delta > 0 ? 7U : 6U,
                        wheel_steps(delta), pressed_buttons))
            return false;
    }
    return true;
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
    api->intern_atom = (x_intern_atom_fn)dlsym(api->x11_library,
                                               "XInternAtom");
    api->get_selection_owner = (x_get_selection_owner_fn)dlsym(
        api->x11_library, "XGetSelectionOwner");
    api->default_screen = (x_default_screen_fn)dlsym(
        api->x11_library, "XDefaultScreen");
    api->display_width = (x_display_dimension_fn)dlsym(
        api->x11_library, "XDisplayWidth");
    api->display_height = (x_display_dimension_fn)dlsym(
        api->x11_library, "XDisplayHeight");
    api->keysym_to_keycode = (x_keysym_to_keycode_fn)dlsym(
        api->x11_library, "XKeysymToKeycode");
    api->query_extension = (xtest_query_extension_fn)dlsym(
        api->xtst_library, "XTestQueryExtension");
    api->fake_key_event = (xtest_fake_key_event_fn)dlsym(
        api->xtst_library, "XTestFakeKeyEvent");
    api->fake_button_event = (xtest_fake_button_event_fn)dlsym(
        api->xtst_library, "XTestFakeButtonEvent");
    api->fake_motion_event = (xtest_fake_motion_event_fn)dlsym(
        api->xtst_library, "XTestFakeMotionEvent");
    api->fake_relative_motion_event =
        (xtest_fake_relative_motion_event_fn)dlsym(
            api->xtst_library, "XTestFakeRelativeMotionEvent");
    if (!api->open_display || !api->close_display || !api->sync ||
        !api->intern_atom || !api->get_selection_owner ||
        !api->default_screen || !api->display_width ||
        !api->display_height || !api->keysym_to_keycode ||
        !api->query_extension || !api->fake_key_event ||
        !api->fake_button_event || !api->fake_motion_event ||
        !api->fake_relative_motion_event)
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

static void release_pressed_inputs(x11_api *api, Display *display,
                                   bool pressed_keys[256],
                                   bool pressed_buttons[10])
{
    unsigned int keycode;
    unsigned int button;
    bool changed = false;

    for (keycode = 8; keycode < 256; keycode++) {
        if (!pressed_keys[keycode])
            continue;
        api->fake_key_event(display, keycode, 0, 0);
        pressed_keys[keycode] = false;
        changed = true;
    }
    for (button = 1; button < 10; button++) {
        if (!pressed_buttons[button])
            continue;
        api->fake_button_event(display, button, 0, 0);
        pressed_buttons[button] = false;
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
                         Display *clipboard_display,
                         Display *injection_display,
                         unsigned int minimum_hold_ms)
{
    bool pressed_keys[256] = {false};
    bool pressed_buttons[10] = {false};
    uint64_t pressed_at[256] = {0};
    bool previous_text_ended_cr = false;
    uint32_t pending_high_surrogate = 0;
    uurb_x11_handshake handshake;

    if (!read_all(client, &handshake, sizeof(handshake)) ||
        handshake.magic != UURB_X11_INPUT_MAGIC ||
        handshake.version != UURB_X11_INPUT_VERSION ||
        memcmp(handshake.token, token, UURB_X11_INPUT_TOKEN_SIZE) != 0 ||
        !send_response(client, 0, 1, 0))
        return;

    while (!stop_requested) {
        uurb_x11_input_event events[UURB_X11_INPUT_MAX_EVENTS];
        unsigned int keycodes[UURB_X11_INPUT_MAX_EVENTS];
        uurb_x11_request request;
        uint32_t index;
        uint32_t injected = 0;
        uint32_t error = 0;
        bool text_request;

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

        text_request = events[0].type == UURB_X11_INPUT_TEXT;
        if (text_request) {
            char text[UURB_X11_INPUT_MAX_EVENTS * 4U + 1U];
            size_t text_length;
            bool ended_cr = previous_text_ended_cr;

            if (!text_events_to_utf8(events, request.count, text,
                                     sizeof(text), &text_length,
                                     &ended_cr,
                                     &pending_high_surrogate)) {
                if (!send_response(client, request.sequence, 0,
                                   UURB_X11_ERROR_UNSUPPORTED))
                    break;
                continue;
            }
            if (!inject_clipboard_text(api, clipboard_display,
                                       injection_display, text, text_length,
                                       pressed_keys)) {
                if (!send_response(client, request.sequence, 0,
                                   UURB_X11_ERROR_INJECTION))
                    break;
                continue;
            }
            previous_text_ended_cr = ended_cr;
            if (!send_response(client, request.sequence, request.count, 0))
                break;
            continue;
        }

        for (index = 0; index < request.count; index++) {
            keycodes[index] = 0;
            if (events[index].type == UURB_X11_INPUT_KEYBOARD)
                keycodes[index] = event_to_x_keycode(api, injection_display,
                                                     &events[index]);
            else if (events[index].type != UURB_X11_INPUT_MOUSE ||
                     !valid_mouse_event(&events[index])) {
                error = UURB_X11_ERROR_UNSUPPORTED;
                break;
            }
            if (events[index].type == UURB_X11_INPUT_KEYBOARD &&
                keycodes[index] == 0) {
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
            if (events[index].type == UURB_X11_INPUT_KEYBOARD) {
                unsigned int keycode = keycodes[index];
                bool is_release =
                    (events[index].flags & UURB_KEYEVENTF_KEYUP) != 0;

                if (is_release && pressed_keys[keycode] &&
                    minimum_hold_ms > 0) {
                    uint64_t now = monotonic_milliseconds();
                    uint64_t elapsed = now - pressed_at[keycode];

                    if (elapsed < minimum_hold_ms)
                        sleep_milliseconds(minimum_hold_ms - elapsed);
                }
                if (!api->fake_key_event(injection_display, keycode,
                                         is_release ? 0 : 1, 0)) {
                    error = UURB_X11_ERROR_INJECTION;
                    break;
                }
                pressed_keys[keycode] = !is_release;
                if (!is_release)
                    pressed_at[keycode] = monotonic_milliseconds();
                else if (events[index].virtual_key == UURB_VK_BACK) {
                    /* A long dictation revision can contain many Backspace
                     * pairs. Flush each completed pair so full GNOME/VTE
                     * clients cannot collapse or outrun the edit stream. */
                    api->sync(injection_display, 0);
                    sleep_milliseconds(UURB_BACKSPACE_SETTLE_MS);
                }
            } else if (!inject_mouse_event(api, injection_display,
                                           &events[index],
                                           pressed_buttons)) {
                error = UURB_X11_ERROR_INJECTION;
                break;
            }
            injected++;
        }
        api->sync(injection_display, 0);
        if (!send_response(client, request.sequence,
                           error == 0 ? request.count : injected, error))
            break;
    }
    release_pressed_inputs(api, injection_display, pressed_keys,
                           pressed_buttons);
}

static void usage(const char *program)
{
    fprintf(stderr,
            "usage: UURB_X11_INPUT_TOKEN=HEX64 %s --ready-file PATH "
            "[--min-hold-ms 0..50] "
            "[--inject-display DISPLAY --inject-xauthority PATH]\n",
            program);
}

static Display *open_display_with_xauthority(const x11_api *api,
                                             const char *display_name,
                                             const char *xauthority)
{
    const char *current_xauthority = getenv("XAUTHORITY");
    char *saved_xauthority = NULL;
    Display *display;
    bool restored;

    if (current_xauthority) {
        saved_xauthority = strdup(current_xauthority);
        if (!saved_xauthority)
            return NULL;
    }
    if (setenv("XAUTHORITY", xauthority, 1) != 0) {
        free(saved_xauthority);
        return NULL;
    }
    display = api->open_display(display_name);
    if (saved_xauthority)
        restored = setenv("XAUTHORITY", saved_xauthority, 1) == 0;
    else
        restored = unsetenv("XAUTHORITY") == 0;
    free(saved_xauthority);
    if (!restored && display) {
        api->close_display(display);
        display = NULL;
    }
    return display;
}

int main(int argc, char **argv)
{
    const char *ready_file = NULL;
    const char *token = getenv("UURB_X11_INPUT_TOKEN");
    const char *injection_display_name = NULL;
    const char *injection_xauthority = NULL;
    unsigned int minimum_hold_ms = 0;
    struct sigaction action;
    x11_api api;
    Display *display;
    Display *injection_display;
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
        } else if (strcmp(argv[index], "--inject-display") == 0 &&
                   index + 1 < argc) {
            injection_display_name = argv[++index];
        } else if (strcmp(argv[index], "--inject-xauthority") == 0 &&
                   index + 1 < argc) {
            injection_xauthority = argv[++index];
        } else {
            usage(argv[0]);
            return EXIT_FAILURE;
        }
    }
    if (!ready_file || !valid_token(token) ||
        ((injection_display_name == NULL) !=
         (injection_xauthority == NULL)) ||
        (injection_display_name && injection_display_name[0] == '\0') ||
        (injection_xauthority &&
         (injection_xauthority[0] != '/' ||
          access(injection_xauthority, R_OK) != 0))) {
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
    injection_display = display;
    if (injection_display_name) {
        injection_display = open_display_with_xauthority(
            &api, injection_display_name, injection_xauthority);
        if (!injection_display) {
            fprintf(stderr, "Cannot open the selected injection display.\n");
            api.close_display(display);
            unload_x11_api(&api);
            return EXIT_FAILURE;
        }
    }

    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    signal(SIGPIPE, SIG_IGN);

    listener_fd = create_listener(ready_file);
    if (listener_fd < 0) {
        fprintf(stderr, "Cannot create the private X11 input listener.\n");
        goto cleanup;
    }
    fprintf(stderr,
            "X11 input helper ready; minimum-hold-ms=%u clipboard-text=%s "
            "injection-display=%s.\n",
            minimum_hold_ms,
            access("/usr/bin/xclip", X_OK) == 0 ? "available" : "unavailable",
            injection_display_name ? injection_display_name : "same");

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
        serve_client(client, token, &api, display, injection_display,
                     minimum_hold_ms);
        active_client_fd = -1;
        close(client);
    }
    status = stop_requested ? EXIT_SUCCESS : EXIT_FAILURE;

cleanup:
    stop_clipboard_owner();
    if (listener_fd >= 0)
        close(listener_fd);
    unlink(ready_file);
    if (injection_display != display)
        api.close_display(injection_display);
    api.close_display(display);
    unload_x11_api(&api);
    return status;
}
