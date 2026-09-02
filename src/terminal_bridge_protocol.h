#ifndef UURB_TERMINAL_BRIDGE_PROTOCOL_H
#define UURB_TERMINAL_BRIDGE_PROTOCOL_H

#include <stdint.h>

#define UURB_TERMINAL_MAGIC 0x55555242U /* "UURB" in network byte order. */
#define UURB_TERMINAL_VERSION 1U
#define UURB_TERMINAL_TOKEN_LENGTH 64U
#define UURB_TERMINAL_MAX_FRAME 65536U
#define UURB_TERMINAL_ACCEPTED 0x06U
#define UURB_TERMINAL_CONFIG_FILENAME "uu-terminal-bridge.runtime"

enum uurb_terminal_frame_type {
    UURB_TERMINAL_FRAME_DATA = 1,
    UURB_TERMINAL_FRAME_RESIZE = 2,
    UURB_TERMINAL_FRAME_EOF = 3,
};

#pragma pack(push, 1)
struct uurb_terminal_hello {
    uint32_t magic;
    uint16_t version;
    uint16_t token_length;
    uint16_t columns;
    uint16_t rows;
};

struct uurb_terminal_frame {
    uint8_t type;
    uint8_t reserved[3];
    uint32_t length;
};
#pragma pack(pop)

#endif
