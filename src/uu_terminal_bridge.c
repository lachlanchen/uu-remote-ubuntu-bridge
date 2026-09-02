#define _GNU_SOURCE

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pty.h>
#include <pwd.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

#include "terminal_bridge_protocol.h"

#define MAX_SESSIONS 4

static volatile sig_atomic_t stop_requested;
static volatile sig_atomic_t children_changed;
static pid_t handlers[MAX_SESSIONS];

static void handle_signal(int signal_number)
{
    if (signal_number == SIGCHLD)
        children_changed = 1;
    else
        stop_requested = 1;
}

static int constant_time_equal(const char *left, const char *right, size_t size)
{
    unsigned char difference = 0;
    size_t index;

    for (index = 0; index < size; index++)
        difference |= (unsigned char)left[index] ^ (unsigned char)right[index];
    return difference == 0;
}

static int sibling_path(char *path, size_t path_size, const char *filename)
{
    char *separator;
    ssize_t executable_length;
    size_t directory_length;
    size_t filename_length;

    if (path_size < 2)
        return 0;
    executable_length = readlink("/proc/self/exe", path, path_size - 1);
    if (executable_length <= 0 || (size_t)executable_length >= path_size - 1)
        return 0;
    path[executable_length] = '\0';
    separator = strrchr(path, '/');
    if (separator == NULL)
        return 0;
    directory_length = (size_t)(separator - path) + 1;
    filename_length = strlen(filename);
    if (directory_length + filename_length >= path_size)
        return 0;
    memcpy(path + directory_length, filename, filename_length + 1);
    return 1;
}

static int token_is_valid(const char *token)
{
    size_t index;

    if (token == NULL || strlen(token) != UURB_TERMINAL_TOKEN_LENGTH)
        return 0;
    for (index = 0; index < UURB_TERMINAL_TOKEN_LENGTH; index++) {
        if (!((token[index] >= '0' && token[index] <= '9') ||
              (token[index] >= 'a' && token[index] <= 'f')))
            return 0;
    }
    return 1;
}

static int read_exact(int fd, void *buffer, size_t size)
{
    unsigned char *cursor = buffer;

    while (size > 0) {
        ssize_t received = recv(fd, cursor, size, 0);

        if (received == 0)
            return 0;
        if (received < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        cursor += received;
        size -= (size_t)received;
    }
    return 1;
}

static int write_all_fd(int fd, const void *buffer, size_t size)
{
    const unsigned char *cursor = buffer;

    while (size > 0) {
        ssize_t written = write(fd, cursor, size);

        if (written <= 0) {
            if (errno == EINTR)
                continue;
            return 0;
        }
        cursor += written;
        size -= (size_t)written;
    }
    return 1;
}

static int send_all(int fd, const void *buffer, size_t size)
{
    const unsigned char *cursor = buffer;

    while (size > 0) {
        ssize_t sent = send(fd, cursor, size, MSG_NOSIGNAL);

        if (sent <= 0) {
            if (errno == EINTR)
                continue;
            return 0;
        }
        cursor += sent;
        size -= (size_t)sent;
    }
    return 1;
}

static void stop_shell(pid_t child)
{
    int status;
    unsigned int attempt;

    if (child <= 0)
        return;
    if (waitpid(child, &status, WNOHANG) == child)
        return;
    kill(-child, SIGHUP);
    for (attempt = 0; attempt < 20; attempt++) {
        if (waitpid(child, &status, WNOHANG) == child)
            return;
        usleep(50000);
    }
    kill(-child, SIGTERM);
    for (attempt = 0; attempt < 20; attempt++) {
        if (waitpid(child, &status, WNOHANG) == child)
            return;
        usleep(50000);
    }
    kill(-child, SIGKILL);
    while (waitpid(child, &status, 0) < 0 && errno == EINTR)
        ;
}

static void run_user_shell(void)
{
    struct passwd *account = getpwuid(getuid());
    char inputrc_path[PATH_MAX];
    const char *shell_name;
    const char *home;
    const char *shell;
    bool is_bash;

    if (account == NULL)
        _exit(126);
    home = account->pw_dir != NULL ? account->pw_dir : "/";
    shell = account->pw_shell != NULL && account->pw_shell[0] != '\0'
                ? account->pw_shell
                : "/bin/bash";
    unsetenv("UURB_TERMINAL_BRIDGE_TOKEN");
    unsetenv("UURB_TERMINAL_BRIDGE_PORT");
    unsetenv("VTE_VERSION");
    unsetenv("VTE_PTY_FD");
    unsetenv("COLORTERM");
    setenv("HOME", home, 1);
    setenv("USER", account->pw_name, 1);
    setenv("LOGNAME", account->pw_name, 1);
    setenv("SHELL", shell, 1);
    setenv("TERM", "xterm-256color", 1);
    setenv("UURB_NATIVE_TERMINAL", "1", 1);
    shell_name = strrchr(shell, '/');
    shell_name = shell_name != NULL ? shell_name + 1 : shell;
    is_bash = strcmp(shell_name, "bash") == 0;
    if (is_bash) {
        if (!sibling_path(inputrc_path, sizeof(inputrc_path),
                          "uu-terminal.inputrc") ||
            access(inputrc_path, R_OK) != 0)
            _exit(126);
        setenv("INPUTRC", inputrc_path, 1);
        setenv("PROMPT_DIRTRIM", "3", 1);
        setenv("PROMPT_COMMAND",
               "PS1='${CONDA_PROMPT_MODIFIER:-}\\u@\\h:\\w\\$ '", 1);
    }
    if (chdir(home) != 0)
        _exit(126);
    if (is_bash)
        execl(shell, shell, "-i", (char *)NULL);
    execl(shell, shell, "-l", (char *)NULL);
    _exit(127);
}

static int apply_resize(int pty_master, const unsigned char *payload)
{
    struct winsize size;
    uint16_t columns_network;
    uint16_t rows_network;

    memcpy(&columns_network, payload, sizeof(columns_network));
    memcpy(&rows_network, payload + sizeof(columns_network),
           sizeof(rows_network));
    memset(&size, 0, sizeof(size));
    size.ws_col = ntohs(columns_network);
    size.ws_row = ntohs(rows_network);
    if (size.ws_col == 0 || size.ws_col > 1000 ||
        size.ws_row == 0 || size.ws_row > 1000)
        return 0;
    return ioctl(pty_master, TIOCSWINSZ, &size) == 0;
}

static int relay_session(int client, const char *expected_token)
{
    struct uurb_terminal_hello hello;
    struct winsize initial_size;
    struct pollfd descriptors[2];
    unsigned char payload[UURB_TERMINAL_MAX_FRAME];
    char supplied_token[UURB_TERMINAL_TOKEN_LENGTH];
    struct timeval handshake_timeout = {.tv_sec = 5, .tv_usec = 0};
    pid_t shell_pid = -1;
    int pty_master = -1;
    int status;
    int result = 1;

    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &handshake_timeout,
               sizeof(handshake_timeout));
    if (read_exact(client, &hello, sizeof(hello)) != 1 ||
        ntohl(hello.magic) != UURB_TERMINAL_MAGIC ||
        ntohs(hello.version) != UURB_TERMINAL_VERSION ||
        ntohs(hello.token_length) != UURB_TERMINAL_TOKEN_LENGTH ||
        read_exact(client, supplied_token, sizeof(supplied_token)) != 1 ||
        !constant_time_equal(supplied_token, expected_token,
                             sizeof(supplied_token))) {
        fprintf(stderr, "rejected terminal bridge handshake\n");
        goto done;
    }
    memset(supplied_token, 0, sizeof(supplied_token));
    {
        const unsigned char accepted = UURB_TERMINAL_ACCEPTED;

        if (!send_all(client, &accepted, 1))
            goto done;
    }
    handshake_timeout.tv_sec = 0;
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &handshake_timeout,
               sizeof(handshake_timeout));

    memset(&initial_size, 0, sizeof(initial_size));
    initial_size.ws_col = ntohs(hello.columns);
    initial_size.ws_row = ntohs(hello.rows);
    if (initial_size.ws_col == 0 || initial_size.ws_col > 1000)
        initial_size.ws_col = 80;
    if (initial_size.ws_row == 0 || initial_size.ws_row > 1000)
        initial_size.ws_row = 24;
    shell_pid = forkpty(&pty_master, NULL, NULL, &initial_size);
    if (shell_pid < 0)
        goto done;
    if (shell_pid == 0)
        run_user_shell();

    fprintf(stderr, "terminal session opened pid=%ld size=%ux%u\n",
            (long)shell_pid, initial_size.ws_col, initial_size.ws_row);
    descriptors[0].fd = client;
    descriptors[0].events = POLLIN;
    descriptors[1].fd = pty_master;
    descriptors[1].events = POLLIN;

    while (!stop_requested) {
        int ready;

        if (waitpid(shell_pid, &status, WNOHANG) == shell_pid) {
            shell_pid = -1;
            result = 0;
            break;
        }
        ready = poll(descriptors, 2, 500);
        if (ready < 0) {
            if (errno == EINTR)
                continue;
            break;
        }
        if (ready == 0)
            continue;
        if (descriptors[1].revents & POLLIN) {
            ssize_t size = read(pty_master, payload, sizeof(payload));

            if (size <= 0 || !send_all(client, payload, (size_t)size))
                break;
        }
        if (descriptors[0].revents & POLLIN) {
            struct uurb_terminal_frame frame;
            uint32_t length;

            if (read_exact(client, &frame, sizeof(frame)) != 1)
                break;
            if (frame.reserved[0] != 0 || frame.reserved[1] != 0 ||
                frame.reserved[2] != 0)
                break;
            length = ntohl(frame.length);
            if (length > UURB_TERMINAL_MAX_FRAME)
                break;
            if (length > 0 && read_exact(client, payload, length) != 1)
                break;
            if (frame.type == UURB_TERMINAL_FRAME_DATA) {
                if (length == 0 ||
                    !write_all_fd(pty_master, payload, length))
                    break;
            } else if (frame.type == UURB_TERMINAL_FRAME_RESIZE) {
                if (length != 4 || !apply_resize(pty_master, payload))
                    break;
            } else if (frame.type == UURB_TERMINAL_FRAME_EOF) {
                unsigned char end_of_input = 4;

                if (length != 0 ||
                    !write_all_fd(pty_master, &end_of_input, 1))
                    break;
            } else {
                break;
            }
        }
        if (descriptors[0].revents & (POLLERR | POLLHUP | POLLNVAL))
            break;
        if (descriptors[1].revents & (POLLERR | POLLHUP | POLLNVAL))
            break;
    }

done:
    memset(supplied_token, 0, sizeof(supplied_token));
    if (pty_master >= 0)
        close(pty_master);
    stop_shell(shell_pid);
    fprintf(stderr, "terminal session closed\n");
    return result;
}

static void reap_handlers(void)
{
    size_t index;
    int status;
    pid_t pid;

    while ((pid = waitpid(-1, &status, WNOHANG)) > 0) {
        for (index = 0; index < MAX_SESSIONS; index++) {
            if (handlers[index] == pid) {
                handlers[index] = 0;
                break;
            }
        }
    }
    children_changed = 0;
}

static int available_slot(void)
{
    size_t index;

    for (index = 0; index < MAX_SESSIONS; index++) {
        if (handlers[index] == 0)
            return (int)index;
    }
    return -1;
}

static int write_ready_file(const char *path, uint16_t port)
{
    char temporary[4096];
    char contents[32];
    int fd;
    int length;

    if (snprintf(temporary, sizeof(temporary), "%s.%ld.tmp", path,
                 (long)getpid()) >= (int)sizeof(temporary))
        return 0;
    fd = open(temporary, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0)
        return 0;
    length = snprintf(contents, sizeof(contents), "%u\n", port);
    if (length <= 0 || !write_all_fd(fd, contents, (size_t)length) ||
        fsync(fd) != 0) {
        close(fd);
        unlink(temporary);
        return 0;
    }
    if (close(fd) != 0) {
        unlink(temporary);
        return 0;
    }
    if (rename(temporary, path) != 0) {
        unlink(temporary);
        return 0;
    }
    return 1;
}

int main(int argc, char **argv)
{
    const char *token = getenv("UURB_TERMINAL_BRIDGE_TOKEN");
    const char *ready_file = NULL;
    struct sockaddr_in address;
    socklen_t address_size = sizeof(address);
    struct sigaction action;
    struct pollfd listener_poll;
    int listener = -1;
    int option = 1;
    int index;
    int exit_code = 1;

    if (argc == 3 && strcmp(argv[1], "--ready-file") == 0)
        ready_file = argv[2];
    if (ready_file == NULL || ready_file[0] != '/' ||
        !token_is_valid(token)) {
        fprintf(stderr, "usage: uu-terminal-bridge --ready-file /absolute/path\n");
        return 2;
    }
    memset(&action, 0, sizeof(action));
    sigemptyset(&action.sa_mask);
    action.sa_handler = handle_signal;
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGHUP, &action, NULL);
    sigaction(SIGCHLD, &action, NULL);
    signal(SIGPIPE, SIG_IGN);

    listener = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (listener < 0)
        goto done;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &option, sizeof(option));
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        getsockname(listener, (struct sockaddr *)&address, &address_size) != 0 ||
        listen(listener, MAX_SESSIONS) != 0 ||
        !write_ready_file(ready_file, ntohs(address.sin_port)))
        goto done;
    fprintf(stderr, "terminal bridge ready on loopback port %u\n",
            ntohs(address.sin_port));
    listener_poll.fd = listener;
    listener_poll.events = POLLIN;
    exit_code = 0;

    while (!stop_requested) {
        int ready;
        int client;
        int slot;
        pid_t handler;

        if (children_changed)
            reap_handlers();
        ready = poll(&listener_poll, 1, 500);
        if (ready < 0) {
            if (errno == EINTR)
                continue;
            exit_code = 1;
            break;
        }
        if (ready == 0)
            continue;
        client = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
        if (client < 0) {
            if (errno == EINTR)
                continue;
            exit_code = 1;
            break;
        }
        slot = available_slot();
        if (slot < 0) {
            close(client);
            continue;
        }
        handler = fork();
        if (handler == 0) {
            int result;

            close(listener);
            result = relay_session(client, token);
            close(client);
            _exit(result);
        }
        close(client);
        if (handler < 0)
            continue;
        handlers[slot] = handler;
    }

done:
    if (listener >= 0)
        close(listener);
    if (ready_file != NULL)
        unlink(ready_file);
    for (index = 0; index < MAX_SESSIONS; index++) {
        if (handlers[index] > 0)
            kill(handlers[index], SIGTERM);
    }
    for (index = 0; index < MAX_SESSIONS; index++) {
        if (handlers[index] > 0) {
            while (waitpid(handlers[index], NULL, 0) < 0 && errno == EINTR)
                ;
        }
    }
    return exit_code;
}
