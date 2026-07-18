#ifndef UURB_X11_INPUT_PROTOCOL_H
#define UURB_X11_INPUT_PROTOCOL_H

#include <stdint.h>

#define UURB_X11_INPUT_MAGIC UINT32_C(0x58315255)
#define UURB_X11_INPUT_VERSION UINT32_C(1)
#define UURB_X11_INPUT_MAX_EVENTS UINT32_C(64)
#define UURB_X11_INPUT_TOKEN_SIZE 64

#define UURB_KEYEVENTF_EXTENDED UINT32_C(0x0001)
#define UURB_KEYEVENTF_KEYUP UINT32_C(0x0002)
#define UURB_KEYEVENTF_UNICODE UINT32_C(0x0004)
#define UURB_KEYEVENTF_SCANCODE UINT32_C(0x0008)

#define UURB_X11_ERROR_BAD_REQUEST UINT32_C(0x2001)
#define UURB_X11_ERROR_UNSUPPORTED UINT32_C(0x2002)
#define UURB_X11_ERROR_INJECTION UINT32_C(0x2003)

typedef struct uurb_x11_handshake {
    uint32_t magic;
    uint32_t version;
    char token[UURB_X11_INPUT_TOKEN_SIZE];
} uurb_x11_handshake;

typedef struct uurb_x11_request {
    uint32_t magic;
    uint32_t sequence;
    uint32_t count;
    uint32_t reserved;
} uurb_x11_request;

typedef struct uurb_x11_key_event {
    uint16_t virtual_key;
    uint16_t scan_code;
    uint32_t flags;
} uurb_x11_key_event;

typedef struct uurb_x11_response {
    uint32_t magic;
    uint32_t sequence;
    uint32_t result;
    uint32_t error;
} uurb_x11_response;

#endif
