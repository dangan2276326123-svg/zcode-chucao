#ifndef _PROTOCOL_H
#define _PROTOCOL_H
/* 0xA5 0x5A frame protocol — firmware side (STM32F407, SPL).
   Matches common/protocol.py exactly. Frame:
     A5 5A | len u16le | type u8 | seq u16le | payload | crc16 u16le
   crc16 = CRC-16/CCITT-FALSE over bytes after header (len..payload).
*/
#include <stdint.h>

#define PROT_HEADER0 0xA5
#define PROT_HEADER1 0x5A
#define PROT_META_LEN 5
#define PROT_MAX_PAYLOAD 512

#define TYPE_NAV     1
#define TYPE_ESTOP   2
#define TYPE_HEARTBEAT 3
#define TYPE_TOOL    4
#define TYPE_STATUS  0x10

typedef struct {
    uint8_t  type;
    uint16_t seq;
    uint8_t  payload[PROT_MAX_PAYLOAD];
    uint16_t payload_len;
} prot_frame_t;

/* feed one received byte; returns 1 when a full valid frame is decoded
   (result in *out), 0 otherwise. Corrupt frames silently reset the parser. */
uint8_t prot_parse_byte(uint8_t byte, prot_frame_t *out);

/* build a frame into buf; returns total length */
uint16_t prot_build(uint8_t type, uint16_t seq,
                    const uint8_t *payload, uint16_t payload_len,
                    uint8_t *buf);

uint16_t prot_crc16(const uint8_t *data, uint16_t len);

#endif
