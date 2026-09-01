#ifndef UURB_X11_INPUT_PROTOCOL_H
#define UURB_X11_INPUT_PROTOCOL_H

#include <stdint.h>

#define UURB_X11_INPUT_MAGIC UINT32_C(0x58315255)
#define UURB_X11_INPUT_VERSION UINT32_C(3)
#define UURB_X11_INPUT_MAX_EVENTS UINT32_C(64)
#define UURB_X11_INPUT_TOKEN_SIZE 64

#define UURB_KEYEVENTF_EXTENDED UINT32_C(0x0001)
#define UURB_KEYEVENTF_KEYUP UINT32_C(0x0002)
#define UURB_KEYEVENTF_UNICODE UINT32_C(0x0004)
#define UURB_KEYEVENTF_SCANCODE UINT32_C(0x0008)

#define UURB_X11_INPUT_KEYBOARD UINT32_C(1)
#define UURB_X11_INPUT_MOUSE UINT32_C(2)
#define UURB_X11_INPUT_TEXT UINT32_C(3)

#define UURB_MOUSEEVENTF_MOVE UINT32_C(0x0001)
#define UURB_MOUSEEVENTF_LEFTDOWN UINT32_C(0x0002)
#define UURB_MOUSEEVENTF_LEFTUP UINT32_C(0x0004)
#define UURB_MOUSEEVENTF_RIGHTDOWN UINT32_C(0x0008)
#define UURB_MOUSEEVENTF_RIGHTUP UINT32_C(0x0010)
#define UURB_MOUSEEVENTF_MIDDLEDOWN UINT32_C(0x0020)
#define UURB_MOUSEEVENTF_MIDDLEUP UINT32_C(0x0040)
#define UURB_MOUSEEVENTF_XDOWN UINT32_C(0x0080)
#define UURB_MOUSEEVENTF_XUP UINT32_C(0x0100)
#define UURB_MOUSEEVENTF_WHEEL UINT32_C(0x0800)
#define UURB_MOUSEEVENTF_HWHEEL UINT32_C(0x1000)
#define UURB_MOUSEEVENTF_MOVE_NOCOALESCE UINT32_C(0x2000)
#define UURB_MOUSEEVENTF_VIRTUALDESK UINT32_C(0x4000)
#define UURB_MOUSEEVENTF_ABSOLUTE UINT32_C(0x8000)

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

typedef struct uurb_x11_input_event {
    uint32_t type;
    uint32_t flags;
    int32_t x;
    int32_t y;
    uint32_t data;
    uint16_t virtual_key;
    uint16_t scan_code;
} uurb_x11_input_event;

typedef struct uurb_x11_response {
    uint32_t magic;
    uint32_t sequence;
    uint32_t result;
    uint32_t error;
} uurb_x11_response;

#endif
