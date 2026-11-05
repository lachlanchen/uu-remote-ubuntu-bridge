/* Exercise the production logger without injecting into any application. */
#include "../../src/uu_cursor_guard.c"

#define WRITERS 8
#define ITERATIONS 2000

static HANDLE start_event;
static const char *messages[] = {
    "UU relay cursor guard active (cursor 24x24)\r\n",
    "UU cursor guard replaced a hidden cursor\r\n"
};

static DWORD WINAPI log_writer(void *argument)
{
    const char *message = messages[(uintptr_t)argument % 2];
    unsigned int i;

    WaitForSingleObject(start_event, INFINITE);
    for (i = 0; i < ITERATIONS; i++)
        write_log(message);
    return 0;
}

int main(int argc, char **argv)
{
    HANDLE threads[WRITERS];
    unsigned int i;
    unsigned int counts[2] = {0, 0};
    unsigned int malformed = 0;
    char line[256];
    FILE *input;

    if (argc != 2)
        return 2;
    log_file = CreateFileA(argv[1], FILE_APPEND_DATA,
                          FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                          CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (log_file == INVALID_HANDLE_VALUE)
        return 3;
    start_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (start_event == NULL)
        return 4;
    for (i = 0; i < WRITERS; i++) {
        threads[i] = CreateThread(NULL, 0, log_writer, (void *)(uintptr_t)i,
                                  0, NULL);
        if (threads[i] == NULL)
            return 5;
    }
    SetEvent(start_event);
    if (WaitForMultipleObjects(WRITERS, threads, TRUE, 30000) != WAIT_OBJECT_0)
        return 6;
    for (i = 0; i < WRITERS; i++)
        CloseHandle(threads[i]);
    CloseHandle(start_event);
    CloseHandle(log_file);
    log_file = INVALID_HANDLE_VALUE;
    input = fopen(argv[1], "rb");
    if (input == NULL)
        return 7;
    while (fgets(line, sizeof(line), input) != NULL) {
        if (strcmp(line, messages[0]) == 0)
            counts[0]++;
        else if (strcmp(line, messages[1]) == 0)
            counts[1]++;
        else
            malformed++;
    }
    if (ferror(input))
        return 8;
    fclose(input);
    printf("cursor log: ready=%u hidden=%u malformed=%u expected-each=%u\n",
           counts[0], counts[1], malformed, WRITERS * ITERATIONS / 2);
    return counts[0] == WRITERS * ITERATIONS / 2 &&
                   counts[1] == WRITERS * ITERATIONS / 2 && malformed == 0
               ? 0 : 1;
}
