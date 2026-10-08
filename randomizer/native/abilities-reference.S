/* Reference for the validated native-rpc-ability-v2 fixture. Regenerate for each seed. */
/* Generated ARM source: exact words used by exefs/code.ips.
 * Sections must be placed at the addresses stated below.
 * GF owner + 0x144 is persistent storage; +0x404 is area storage.
 * Seed-specific constants are data, not instructions. */
.syntax unified
.arm
.section .rando_hook,"ax",%progbits
/* Place at 0x002d81c0. */
rando_attach_hook:
    .word 0xea03fa7c /* b rando_attach_guard */
.section .rando_guard,"ax",%progbits
/* Place at 0x003d6bb8. */
rando_attach_guard:
    .word 0xe59f20a0 /* 0x003d6bb8: ldr r2, [pc, #160] ; literal 0x0043c190 */
    .word 0xe5922000 /* 0x003d6bbc: ldr r2, [r2] */
    .word 0xe3520000 /* 0x003d6bc0: cmp r2, #0 */
    .word 0x0a000020 /* 0x003d6bc4: beq rando_deny */
    .word 0xe59231f8 /* 0x003d6bc8: ldr r3, [r2, #0x1f8] */
    .word 0xe3130040 /* 0x003d6bcc: tst r3, #0x40 */
    .word 0x0a00001d /* 0x003d6bd0: beq rando_deny */
    .word 0xe59231f8 /* 0x003d6bd4: ldr r3, [r2, #0x1f8] */
    .word 0xe59fc084 /* 0x003d6bd8: ldr r12, [pc, #132] ; literal 0xffffff80 */
    .word 0xe003300c /* 0x003d6bdc: and r3, r3, r12 */
    .word 0xe59fc080 /* 0x003d6be0: ldr r12, [pc, #128] ; literal 0xc8661580 */
    .word 0xe153000c /* 0x003d6be4: cmp r3, r12 */
    .word 0x1a000017 /* 0x003d6be8: bne rando_deny */
    .word 0xe59231fc /* 0x003d6bec: ldr r3, [r2, #0x1fc] */
    .word 0xe59fc074 /* 0x003d6bf0: ldr r12, [pc, #116] ; literal 0xead1b7e5 */
    .word 0xe153000c /* 0x003d6bf4: cmp r3, r12 */
    .word 0x1a000013 /* 0x003d6bf8: bne rando_deny */
    .word 0xe5923200 /* 0x003d6bfc: ldr r3, [r2, #0x200] */
    .word 0xe59fc068 /* 0x003d6c00: ldr r12, [pc, #104] ; literal 0x4a83d0c2 */
    .word 0xe153000c /* 0x003d6c04: cmp r3, r12 */
    .word 0x1a00000f /* 0x003d6c08: bne rando_deny */
    .word 0xe5923204 /* 0x003d6c0c: ldr r3, [r2, #0x204] */
    .word 0xe59fc05c /* 0x003d6c10: ldr r12, [pc, #92] ; literal 0xb5fdb8e9 */
    .word 0xe153000c /* 0x003d6c14: cmp r3, r12 */
    .word 0x1a00000b /* 0x003d6c18: bne rando_deny */
    .word 0xe5923208 /* 0x003d6c1c: ldr r3, [r2, #0x208] */
    .word 0xe203307f /* 0x003d6c20: and r3, r3, #0x7f */
    .word 0xe59fc04c /* 0x003d6c24: ldr r12, [pc, #76] ; literal 0x00000028 */
    .word 0xe153000c /* 0x003d6c28: cmp r3, r12 */
    .word 0x1a000006 /* 0x003d6c2c: bne rando_deny */
    .word 0xe5923208 /* 0x003d6c30: ldr r3, [r2, #0x208] */
    .word 0xe3130c02 /* 0x003d6c34: tst r3, #0x200 */
    .word 0x03c11001 /* 0x003d6c38: biceq r1, r1, #0x1 */
    .word 0xe5923208 /* 0x003d6c3c: ldr r3, [r2, #0x208] */
    .word 0xe3130b01 /* 0x003d6c40: tst r3, #0x400 */
    .word 0x03c11004 /* 0x003d6c44: biceq r1, r1, #0x4 */
    .word 0xea000000 /* 0x003d6c48: b rando_grant */
rando_deny:
    .word 0xe3c11005 /* 0x003d6c4c: bic r1, r1, #5 */
rando_grant:
    .word 0xe590213c /* 0x003d6c50: ldr r2, [r0, #0x13c] */
    .word 0xe1811002 /* 0x003d6c54: orr r1, r1, r2 */
    .word 0xe580113c /* 0x003d6c58: str r1, [r0, #0x13c] */
    .word 0xe12fff1e /* 0x003d6c5c: bx lr */
    .word 0x0043c190 /* 0x003d6c60: literal data */
    .word 0xffffff80 /* 0x003d6c64: literal data */
    .word 0xc8661580 /* 0x003d6c68: literal data */
    .word 0xead1b7e5 /* 0x003d6c6c: literal data */
    .word 0x4a83d0c2 /* 0x003d6c70: literal data */
    .word 0xb5fdb8e9 /* 0x003d6c74: literal data */
    .word 0x00000028 /* 0x003d6c78: literal data */
