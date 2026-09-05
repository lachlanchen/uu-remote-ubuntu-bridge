#define _GNU_SOURCE
#include <arpa/inet.h>
#include <ctype.h>
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
#include <unistd.h>

#include "x11_clipboard_protocol.h"

static volatile sig_atomic_t stop_requested;
static volatile sig_atomic_t listener_fd = -1;
static volatile sig_atomic_t active_client_fd = -1;
static volatile sig_atomic_t clipboard_owner_pid = -1;
static volatile sig_atomic_t primary_owner_pid = -1;

static void stop_owner(volatile sig_atomic_t *owner_pid)
{
    pid_t pid = (pid_t)*owner_pid;
    int status;

    *owner_pid = -1;
    if (pid <= 0)
        return;
    kill(pid, SIGTERM);
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

static bool start_owner(const char *selection, const char *text, size_t size,
                        volatile sig_atomic_t *owner_pid)
{
    int input_pipe[2];
    pid_t pid;

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
        execl("/usr/bin/xclip", "xclip", "-selection", selection,
              "-in", "-loops", "0", (char *)NULL);
        _exit(127);
    }
    close(input_pipe[0]);
    if (!write_fd_all(input_pipe[1], text, size)) {
        close(input_pipe[1]);
        kill(pid, SIGTERM);
        waitpid(pid, NULL, 0);
        return false;
    }
    close(input_pipe[1]);
    *owner_pid = (sig_atomic_t)pid;
    return true;
}

static bool replace_clipboard(const char *text, size_t size)
{
    volatile sig_atomic_t old_clipboard = clipboard_owner_pid;
    volatile sig_atomic_t old_primary = primary_owner_pid;

    clipboard_owner_pid = primary_owner_pid = -1;
    if (!start_owner("CLIPBOARD", text, size, &clipboard_owner_pid) ||
        !start_owner("PRIMARY", text, size, &primary_owner_pid)) {
        stop_owners();
        clipboard_owner_pid = old_clipboard;
        primary_owner_pid = old_primary;
        return false;
    }
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

static void serve_client(int client, const char *token)
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
        else if (!replace_clipboard(text, request.text_bytes))
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
    struct sigaction action;
    int status = EXIT_FAILURE;

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
        active_client_fd = client;
        serve_client(client, token);
        active_client_fd = -1;
        close(client);
    }
    status = stop_requested ? EXIT_SUCCESS : EXIT_FAILURE;

cleanup:
    stop_owners();
    if (listener_fd >= 0)
        close(listener_fd);
    unlink(ready_file);
    return status;
}
