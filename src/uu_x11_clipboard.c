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
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

#include "x11_clipboard_protocol.h"

#ifndef UURB_XCLIP_PATH
#define UURB_XCLIP_PATH "/usr/bin/xclip"
#endif

/* Match uu_x11_input.c: keep the helper buildable with runtime X11 libraries
 * only, then prove that each foreground xclip owns its requested selection. */
typedef struct _XDisplay Display;
typedef int Bool;
typedef unsigned long Atom;
typedef unsigned long Window;
typedef Display *(*x_open_display_fn)(const char *);
typedef int (*x_close_display_fn)(Display *);
typedef int (*x_sync_fn)(Display *, Bool);
typedef Atom (*x_intern_atom_fn)(Display *, const char *, Bool);
typedef Window (*x_get_selection_owner_fn)(Display *, Atom);

typedef struct x11_api {
    void *library;
    x_open_display_fn open_display;
    x_close_display_fn close_display;
    x_sync_fn sync;
    x_intern_atom_fn intern_atom;
    x_get_selection_owner_fn get_selection_owner;
} x11_api;

static volatile sig_atomic_t stop_requested;
static volatile sig_atomic_t listener_fd = -1;
static volatile sig_atomic_t active_client_fd = -1;
static volatile sig_atomic_t clipboard_owner_pid = -1;
static volatile sig_atomic_t primary_owner_pid = -1;

static void stop_owner(volatile sig_atomic_t *owner_pid)
{
    pid_t pid = (pid_t)*owner_pid;
    int status;
    unsigned int attempt;

    *owner_pid = -1;
    if (pid <= 0)
        return;
    kill(pid, SIGTERM);
    for (attempt = 0; attempt < 25; attempt++) {
        pid_t result = waitpid(pid, &status, WNOHANG);

        if (result == pid || (result < 0 && errno == ECHILD))
            return;
        if (result < 0 && errno != EINTR)
            break;
        usleep(2000);
    }
    kill(pid, SIGKILL);
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR)
        ;
}

static void stop_owners(void)
{
    stop_owner(&clipboard_owner_pid);
    stop_owner(&primary_owner_pid);
}

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

static bool write_fd_all(int fd, const char *buffer, size_t size)
{
    while (size > 0) {
        ssize_t written = write(fd, buffer, size);

        if (written < 0) {
            if (errno == EINTR)
                continue;
            return false;
        }
        if (written == 0)
            return false;
        buffer += written;
        size -= (size_t)written;
    }
    return true;
}

static bool valid_token(const char *token)
{
    size_t index;

    if (!token || strlen(token) != UURB_X11_CLIPBOARD_TOKEN_SIZE)
        return false;
    for (index = 0; index < UURB_X11_CLIPBOARD_TOKEN_SIZE; index++) {
        if (!isxdigit((unsigned char)token[index]))
            return false;
    }
    return true;
}

static bool load_x11_api(x11_api *api)
{
    memset(api, 0, sizeof(*api));
    api->library = dlopen("libX11.so.6", RTLD_NOW | RTLD_LOCAL);
    if (!api->library)
        return false;
    api->open_display = (x_open_display_fn)dlsym(api->library,
                                                 "XOpenDisplay");
    api->close_display = (x_close_display_fn)dlsym(api->library,
                                                   "XCloseDisplay");
    api->sync = (x_sync_fn)dlsym(api->library, "XSync");
    api->intern_atom = (x_intern_atom_fn)dlsym(api->library,
                                               "XInternAtom");
    api->get_selection_owner = (x_get_selection_owner_fn)dlsym(
        api->library, "XGetSelectionOwner");
    if (!api->open_display || !api->close_display || !api->sync ||
        !api->intern_atom || !api->get_selection_owner) {
        dlclose(api->library);
        memset(api, 0, sizeof(*api));
        return false;
    }
    return true;
}

static void unload_x11_api(x11_api *api)
{
    if (api->library)
        dlclose(api->library);
    memset(api, 0, sizeof(*api));
}

/* Strict UTF-8 validation also rejects NUL.  The companion is the only
 * intended sender, but content is nevertheless treated as untrusted. */
static bool valid_utf8_text(const unsigned char *text, size_t size)
{
    size_t index = 0;

    while (index < size) {
        unsigned char first = text[index++];
        uint32_t codepoint;
        unsigned int continuation;

        if (first == 0)
            return false;
        if (first < 0x80)
            continue;
        if (first >= 0xc2 && first <= 0xdf) {
            codepoint = first & 0x1f;
            continuation = 1;
        } else if (first >= 0xe0 && first <= 0xef) {
            codepoint = first & 0x0f;
            continuation = 2;
        } else if (first >= 0xf0 && first <= 0xf4) {
            codepoint = first & 0x07;
            continuation = 3;
        } else {
            return false;
        }
        if (index + continuation > size)
            return false;
        while (continuation-- > 0) {
            unsigned char next = text[index++];

            if ((next & 0xc0) != 0x80)
                return false;
            codepoint = (codepoint << 6) | (next & 0x3f);
        }
        if ((codepoint < 0x80) ||
            (codepoint < 0x800 && first >= 0xe0) ||
            (codepoint < 0x10000 && first >= 0xf0) ||
            (codepoint >= 0xd800 && codepoint <= 0xdfff) ||
            codepoint > 0x10ffff)
            return false;
    }
    return true;
}

static bool start_owner(const x11_api *api, Display *display,
                        const char *selection, const char *text, size_t size,
                        volatile sig_atomic_t *owner_pid)
{
    Atom selection_atom;
    int input_pipe[2];
    pid_t pid;
    Window previous_owner;
    Window current_owner = 0;
    unsigned int attempt;

    selection_atom = api->intern_atom(display, selection, 0);
    if (selection_atom == 0)
        return false;
    api->sync(display, 0);
    previous_owner = api->get_selection_owner(display, selection_atom);

    if (pipe2(input_pipe, O_CLOEXEC) != 0)
        return false;
    pid = fork();
    if (pid < 0) {
        close(input_pipe[0]);
        close(input_pipe[1]);
        return false;
    }
    if (pid == 0) {
        int null_fd;

        if (dup2(input_pipe[0], STDIN_FILENO) < 0)
            _exit(126);
        close(input_pipe[0]);
        close(input_pipe[1]);
        null_fd = open("/dev/null", O_WRONLY | O_CLOEXEC);
        if (null_fd >= 0) {
            dup2(null_fd, STDOUT_FILENO);
            dup2(null_fd, STDERR_FILENO);
            close(null_fd);
        }
        setenv("LC_ALL", "C.UTF-8", 1);
        /* -verbose keeps xclip in the foreground.  Without it xclip forks,
         * leaving the launcher PID unable to supervise or clean up the real
         * X11 selection owner. */
        execl(UURB_XCLIP_PATH, "xclip", "-selection", selection,
              "-in", "-loops", "0", "-verbose", (char *)NULL);
        _exit(127);
    }
    close(input_pipe[0]);
    *owner_pid = (sig_atomic_t)pid;
    if (!write_fd_all(input_pipe[1], text, size)) {
        close(input_pipe[1]);
        stop_owner(owner_pid);
        return false;
    }
    close(input_pipe[1]);

    for (attempt = 0; attempt < 100; attempt++) {
        int status;
        pid_t result;

        api->sync(display, 0);
        current_owner = api->get_selection_owner(display, selection_atom);
        if (current_owner != 0 && current_owner != previous_owner)
            return true;
        result = waitpid(pid, &status, WNOHANG);
        if (result == pid || (result < 0 && errno == ECHILD)) {
            *owner_pid = -1;
            return false;
        }
        if (result < 0 && errno != EINTR)
            break;
        usleep(5000);
    }
    stop_owner(owner_pid);
    return false;
}

static bool replace_clipboard(const x11_api *api, Display *display,
                              const char *text, size_t size)
{
    volatile sig_atomic_t old_clipboard = clipboard_owner_pid;
    volatile sig_atomic_t old_primary = primary_owner_pid;
    volatile sig_atomic_t new_clipboard = -1;
    volatile sig_atomic_t new_primary = -1;

    if (!start_owner(api, display, "CLIPBOARD", text, size,
                     &new_clipboard) ||
        !start_owner(api, display, "PRIMARY", text, size, &new_primary)) {
        stop_owner(&new_clipboard);
        stop_owner(&new_primary);
        /* A partial X11 handoff can already have displaced either old owner.
         * Do not restore stale PIDs as if they still owned the selections. */
        stop_owner(&old_clipboard);
        stop_owner(&old_primary);
        clipboard_owner_pid = -1;
        primary_owner_pid = -1;
        return false;
    }
    clipboard_owner_pid = new_clipboard;
    primary_owner_pid = new_primary;
    stop_owner(&old_clipboard);
    stop_owner(&old_primary);
    return true;
}

static bool send_response(int client, uint32_t sequence, uint32_t result,
                          uint32_t error)
{
    uurb_x11_clipboard_response response;

    response.magic = UURB_X11_CLIPBOARD_MAGIC;
    response.sequence = sequence;
    response.result = result;
    response.error = error;
    return write_all(client, &response, sizeof(response));
}

static bool set_client_deadlines(int client)
{
    struct timeval timeout;

    timeout.tv_sec = 1;
    timeout.tv_usec = 0;
    return setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout,
                      sizeof(timeout)) == 0 &&
           setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout,
                      sizeof(timeout)) == 0;
}

static void serve_client(int client, const char *token,
                         const x11_api *api, Display *display)
{
    uurb_x11_clipboard_handshake handshake;

    if (!read_all(client, &handshake, sizeof(handshake)) ||
        handshake.magic != UURB_X11_CLIPBOARD_MAGIC ||
        handshake.version != UURB_X11_CLIPBOARD_VERSION ||
        memcmp(handshake.token, token, UURB_X11_CLIPBOARD_TOKEN_SIZE) != 0 ||
        !send_response(client, 0, 1, 0))
        return;

    while (!stop_requested) {
        uurb_x11_clipboard_request request;
        char *text;
        uint32_t error = 0;

        if (!read_all(client, &request, sizeof(request)))
            break;
        if (request.magic != UURB_X11_CLIPBOARD_MAGIC || request.reserved != 0 ||
            request.text_bytes == 0 ||
            request.text_bytes > UURB_X11_CLIPBOARD_MAX_TEXT_BYTES) {
            send_response(client, request.sequence, 0,
                          UURB_X11_CLIPBOARD_ERROR_BAD_REQUEST);
            break;
        }
        text = malloc((size_t)request.text_bytes + 1U);
        if (!text)
            break;
        if (!read_all(client, text, request.text_bytes)) {
            free(text);
            break;
        }
        text[request.text_bytes] = '\0';
        if (!valid_utf8_text((const unsigned char *)text, request.text_bytes))
            error = UURB_X11_CLIPBOARD_ERROR_INVALID_TEXT;
        else if (!replace_clipboard(api, display, text, request.text_bytes))
            error = UURB_X11_CLIPBOARD_ERROR_OWNER;
        free(text);
        if (!send_response(client, request.sequence,
                           error == 0 ? request.text_bytes : 0, error))
            break;
    }
}

static bool publish_port(const char *path, unsigned int port)
{
    char value[32];
    int fd;
    int length;

    fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    if (fd < 0)
        return false;
    length = snprintf(value, sizeof(value), "%u\n", port);
    if (write_fd_all(fd, value, (size_t)length)) {
        fsync(fd);
        close(fd);
        return true;
    }
    close(fd);
    return false;
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
    if (bind(fd, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(fd, 1) != 0 ||
        getsockname(fd, (struct sockaddr *)&address, &address_size) != 0 ||
        !publish_port(ready_file, ntohs(address.sin_port))) {
        close(fd);
        return -1;
    }
    return fd;
}

static void usage(const char *program)
{
    fprintf(stderr, "usage: UURB_X11_CLIPBOARD_TOKEN=HEX64 %s --ready-file PATH\n",
            program);
}

int main(int argc, char **argv)
{
    const char *token = getenv("UURB_X11_CLIPBOARD_TOKEN");
    const char *ready_file = NULL;
    Display *display = NULL;
    struct sigaction action;
    int status = EXIT_FAILURE;
    x11_api api;

    memset(&api, 0, sizeof(api));

    if (argc == 3 && strcmp(argv[1], "--ready-file") == 0)
        ready_file = argv[2];
    if (!ready_file || ready_file[0] != '/' || !valid_token(token)) {
        usage(argv[0]);
        return EXIT_FAILURE;
    }
    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    signal(SIGPIPE, SIG_IGN);

    if (!load_x11_api(&api) || !(display = api.open_display(NULL))) {
        fprintf(stderr, "Cannot inspect X11 clipboard ownership.\n");
        goto cleanup;
    }
    listener_fd = create_listener(ready_file);
    if (listener_fd < 0) {
        fprintf(stderr, "Cannot create the private X11 clipboard listener.\n");
        goto cleanup;
    }
    fprintf(stderr, "X11 clipboard helper ready; direction=wine-to-host-only.\n");
    while (!stop_requested) {
        int client = accept(listener_fd, NULL, NULL);

        if (client < 0) {
            if (errno == EINTR)
                continue;
            break;
        }
        if (!set_client_deadlines(client)) {
            close(client);
            continue;
        }
        active_client_fd = client;
        serve_client(client, token, &api, display);
        active_client_fd = -1;
        close(client);
    }
    status = stop_requested ? EXIT_SUCCESS : EXIT_FAILURE;

cleanup:
    stop_owners();
    if (listener_fd >= 0)
        close(listener_fd);
    if (display)
        api.close_display(display);
    unload_x11_api(&api);
    unlink(ready_file);
    return status;
}
