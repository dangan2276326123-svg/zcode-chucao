#include "protocol.h"
#include <string.h>

uint16_t prot_crc16(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    uint16_t i;
    uint8_t b;
    for (i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (b = 0; b < 8; b++) {
            if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
            else crc = crc << 1;
        }
    }
    return crc;
}

/* byte-stream parser: accumulate header..payload into body_buf, then verify.
   body_buf = [len_l len_h type seq_l seq_h payload...]  (what CRC covers) */
static enum { S_H0, S_H1, S_LEN_L, S_LEN_H, S_BODY, S_CRC_L, S_CRC_H } pstate = S_H0;
static uint8_t  body_buf[PROT_META_LEN + PROT_MAX_PAYLOAD];
static uint16_t body_len;      /* declared body length */
static uint16_t body_idx;      /* bytes written to body_buf */
static uint8_t  crc_lo;

uint8_t prot_parse_byte(uint8_t byte, prot_frame_t *out)
{
    switch (pstate) {
    case S_H0:
        if (byte == PROT_HEADER0) pstate = S_H1;
        return 0;
    case S_H1:
        pstate = (byte == PROT_HEADER1) ? S_LEN_L : S_H0;
        return 0;
    case S_LEN_L:
        body_buf[0] = byte;
        pstate = S_LEN_H;
        return 0;
    case S_LEN_H:
        body_buf[1] = byte;
        body_len = body_buf[0] | ((uint16_t)byte << 8);
        if (body_len < PROT_META_LEN ||
            body_len > PROT_META_LEN + PROT_MAX_PAYLOAD) {
            pstate = S_H0;
            return 0;
        }
        body_idx = 2;
        pstate = S_BODY;
        return 0;
    case S_BODY:
        body_buf[body_idx++] = byte;
        if (body_idx >= body_len) pstate = S_CRC_L;
        return 0;
    case S_CRC_L:
        crc_lo = byte;
        pstate = S_CRC_H;
        return 0;
    case S_CRC_H: {
        uint16_t crc_rx = crc_lo | ((uint16_t)byte << 8);
        pstate = S_H0;
        if (prot_crc16(body_buf, body_len) != crc_rx) return 0;
        out->type = body_buf[2];
        out->seq = body_buf[3] | ((uint16_t)body_buf[4] << 8);
        out->payload_len = body_len - PROT_META_LEN;
        if (out->payload_len) memcpy(out->payload, &body_buf[5], out->payload_len);
        return 1;
    }
    default:
        pstate = S_H0;
        return 0;
    }
}

uint16_t prot_build(uint8_t type, uint16_t seq,
                    const uint8_t *payload, uint16_t payload_len,
                    uint8_t *buf)
{
    uint16_t body_len = PROT_META_LEN + payload_len;
    uint16_t crc, i = 0;
    buf[i++] = PROT_HEADER0;
    buf[i++] = PROT_HEADER1;
    buf[i++] = (uint8_t)(body_len & 0xFF);
    buf[i++] = (uint8_t)(body_len >> 8);
    buf[i++] = type;
    buf[i++] = (uint8_t)(seq & 0xFF);
    buf[i++] = (uint8_t)(seq >> 8);
    if (payload_len) memcpy(&buf[i], payload, payload_len);
    i += payload_len;
    crc = prot_crc16(&buf[2], body_len);
    buf[i++] = (uint8_t)(crc & 0xFF);
    buf[i++] = (uint8_t)(crc >> 8);
    return i;
}
