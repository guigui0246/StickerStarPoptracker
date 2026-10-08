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
    .word 0xe59fc080 /* 0x003d6be0: ldr r12, [pc, #128] ; literal 0x0dd68b00 */
    .word 0xe153000c /* 0x003d6be4: cmp r3, r12 */
    .word 0x1a000017 /* 0x003d6be8: bne rando_deny */
    .word 0xe59231fc /* 0x003d6bec: ldr r3, [r2, #0x1fc] */
    .word 0xe59fc074 /* 0x003d6bf0: ldr r12, [pc, #116] ; literal 0x71620ac8 */
    .word 0xe153000c /* 0x003d6bf4: cmp r3, r12 */
    .word 0x1a000013 /* 0x003d6bf8: bne rando_deny */
    .word 0xe5923200 /* 0x003d6bfc: ldr r3, [r2, #0x200] */
    .word 0xe59fc068 /* 0x003d6c00: ldr r12, [pc, #104] ; literal 0x80936e14 */
    .word 0xe153000c /* 0x003d6c04: cmp r3, r12 */
    .word 0x1a00000f /* 0x003d6c08: bne rando_deny */
    .word 0xe5923204 /* 0x003d6c0c: ldr r3, [r2, #0x204] */
    .word 0xe59fc05c /* 0x003d6c10: ldr r12, [pc, #92] ; literal 0x02923801 */
    .word 0xe153000c /* 0x003d6c14: cmp r3, r12 */
    .word 0x1a00000b /* 0x003d6c18: bne rando_deny */
    .word 0xe5923208 /* 0x003d6c1c: ldr r3, [r2, #0x208] */
    .word 0xe203307f /* 0x003d6c20: and r3, r3, #0x7f */
    .word 0xe59fc04c /* 0x003d6c24: ldr r12, [pc, #76] ; literal 0x00000017 */
    .word 0xe153000c /* 0x003d6c28: cmp r3, r12 */
    .word 0x1a000006 /* 0x003d6c2c: bne rando_deny */
    .word 0xe5923208 /* 0x003d6c30: ldr r3, [r2, #0x208] */
    .word 0xe3130501 /* 0x003d6c34: tst r3, #0x400000 */
    .word 0x03c11001 /* 0x003d6c38: biceq r1, r1, #0x1 */
    .word 0xe5923208 /* 0x003d6c3c: ldr r3, [r2, #0x208] */
    .word 0xe3130502 /* 0x003d6c40: tst r3, #0x800000 */
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
    .word 0x0dd68b00 /* 0x003d6c68: literal data */
    .word 0x71620ac8 /* 0x003d6c6c: literal data */
    .word 0x80936e14 /* 0x003d6c70: literal data */
    .word 0x02923801 /* 0x003d6c74: literal data */
    .word 0x00000017 /* 0x003d6c78: literal data */

.section .rando_sticker_hook_normal,"ax",%progbits
/* Place at 0x00278e90. */
    .word 0xea057779 /* b rando_sticker_normal */
.section .rando_sticker_hook_forced,"ax",%progbits
/* Place at 0x00352ddc. */
    .word 0xea020faf /* b rando_sticker_forced */
.section .rando_sticker_hook_commit,"ax",%progbits
/* Place at 0x00270eac. */
    .word 0xea059782 /* b rando_sticker_commit */
.section .rando_sticker_hook_album,"ax",%progbits
/* Place at 0x002d8208. */
    .word 0xea03fab4 /* b rando_sticker_album */
.section .rando_sticker_guard,"ax",%progbits
/* Place at 0x003d6c7c. */
rando_sticker_normal:
    .word 0xe92d401f /* 0x003d6c7c: push {r0-r4, lr} */
    .word 0xe1a00002 /* 0x003d6c80: mov r0, r2 */
    .word 0xebfabbe4 /* 0x003d6c84: bl 0x00285c1c */
    .word 0xeb00001d /* 0x003d6c88: bl rando_sticker_filter */
    .word 0xe5900000 /* 0x003d6c8c: ldr r0, [r0] ; selected item name */
    .word 0xe58d0008 /* 0x003d6c90: str r0, [sp, #8] */
    .word 0xe8bd401f /* 0x003d6c94: pop {r0-r4, lr} */
    .word 0xe92d4ff0 /* 0x003d6c98: original native register-save prologue */
    .word 0xeafa887c /* 0x003d6c9c: b 0x00278e94 */
rando_sticker_forced:
    .word 0xe92d401f /* 0x003d6ca0: push {r0-r4, lr} */
    .word 0xe1a00001 /* 0x003d6ca4: mov r0, r1 */
    .word 0xeb000015 /* 0x003d6ca8: bl rando_sticker_filter */
    .word 0xe58d0004 /* 0x003d6cac: str r0, [sp, #4] */
    .word 0xe8bd401f /* 0x003d6cb0: pop {r0-r4, lr} */
    .word 0xe92d41f0 /* 0x003d6cb4: original native register-save prologue */
    .word 0xeafdf048 /* 0x003d6cb8: b 0x00352de0 */
rando_sticker_commit:
    .word 0xe92d401f /* 0x003d6cbc: push {r0-r4, lr} */
    .word 0xe1a00002 /* 0x003d6cc0: mov r0, r2 */
    .word 0xebfabbd4 /* 0x003d6cc4: bl 0x00285c1c */
    .word 0xeb00000d /* 0x003d6cc8: bl rando_sticker_filter */
    .word 0xe5900000 /* 0x003d6ccc: ldr r0, [r0] ; selected item name */
    .word 0xe58d0008 /* 0x003d6cd0: str r0, [sp, #8] */
    .word 0xe8bd401f /* 0x003d6cd4: pop {r0-r4, lr} */
    .word 0xe92d4ff0 /* 0x003d6cd8: original native register-save prologue */
    .word 0xeafa6873 /* 0x003d6cdc: b 0x00270eb0 */
rando_sticker_album:
    .word 0xe92d401f /* 0x003d6ce0: push {r0-r4, lr} */
    .word 0xe1a00002 /* 0x003d6ce4: mov r0, r2 */
    .word 0xebfabbcb /* 0x003d6ce8: bl 0x00285c1c */
    .word 0xeb000004 /* 0x003d6cec: bl rando_sticker_filter */
    .word 0xe5900000 /* 0x003d6cf0: ldr r0, [r0] ; selected item name */
    .word 0xe58d0008 /* 0x003d6cf4: str r0, [sp, #8] */
    .word 0xe8bd401f /* 0x003d6cf8: pop {r0-r4, lr} */
    .word 0xe92d4ff0 /* 0x003d6cfc: original native register-save prologue */
    .word 0xeafc0541 /* 0x003d6d00: b 0x002d820c */
rando_sticker_filter:
    .word 0xe92d4070 /* 0x003d6d04: push {r4-r6, lr} */
    .word 0xe1a04000 /* 0x003d6d08: mov r4, r0 ; original descriptor */
    .word 0xe5901040 /* 0x003d6d0c: ldr r1, [r0, #0x40] ; native kind */
    .word 0xe3510004 /* 0x003d6d10: cmp r1, #4 */
    .word 0x1a000031 /* 0x003d6d14: bne rando_sticker_original */
    .word 0xe590103c /* 0x003d6d18: ldr r1, [r0, #0x3c] ; native save index */
    .word 0xe35100c8 /* 0x003d6d1c: cmp r1, #200 */
    .word 0x8a00002e /* 0x003d6d20: bhi rando_sticker_original */
    .word 0xe59f30bc /* 0x003d6d24: ldr r3, [pc, literal] */
    .word 0xe7d35001 /* 0x003d6d28: ldrb r5, [r3, r1] ; generic ownership rank */
    .word 0xe35500ff /* 0x003d6d2c: cmp r5, #255 ; not a generic sticker */
    .word 0x0a00002a /* 0x003d6d30: beq rando_sticker_original */
    .word 0xe59f20b0 /* 0x003d6d34: ldr r2, [pc, literal] */
    .word 0xe5922000 /* 0x003d6d38: ldr r2, [r2] ; GF owner */
    .word 0xe3520000 /* 0x003d6d3c: cmp r2, #0 */
    .word 0x0a000023 /* 0x003d6d40: beq rando_sticker_convert */
    .word 0xe59231f8 /* 0x003d6d44: ldr r3, [r2, #0x1f8] */
    .word 0xe3130040 /* 0x003d6d48: tst r3, #seed_initialized_mask */
    .word 0x0a000020 /* 0x003d6d4c: beq rando_sticker_convert */
    .word 0xe59231f8 /* 0x003d6d50: ldr r3, [r2, #0x1f8] */
    .word 0xe59fc094 /* 0x003d6d54: ldr r12, [pc, literal] */
    .word 0xe003300c /* 0x003d6d58: and r3, r3, r12 */
    .word 0xe59fc090 /* 0x003d6d5c: ldr r12, [pc, literal] */
    .word 0xe153000c /* 0x003d6d60: cmp r3, r12 ; seed word */
    .word 0x1a00001a /* 0x003d6d64: bne rando_sticker_convert */
    .word 0xe59231fc /* 0x003d6d68: ldr r3, [r2, #0x1fc] */
    .word 0xe59fc084 /* 0x003d6d6c: ldr r12, [pc, literal] */
    .word 0xe153000c /* 0x003d6d70: cmp r3, r12 ; seed word */
    .word 0x1a000016 /* 0x003d6d74: bne rando_sticker_convert */
    .word 0xe5923200 /* 0x003d6d78: ldr r3, [r2, #0x200] */
    .word 0xe59fc078 /* 0x003d6d7c: ldr r12, [pc, literal] */
    .word 0xe153000c /* 0x003d6d80: cmp r3, r12 ; seed word */
    .word 0x1a000012 /* 0x003d6d84: bne rando_sticker_convert */
    .word 0xe5923204 /* 0x003d6d88: ldr r3, [r2, #0x204] */
    .word 0xe59fc06c /* 0x003d6d8c: ldr r12, [pc, literal] */
    .word 0xe153000c /* 0x003d6d90: cmp r3, r12 ; seed word */
    .word 0x1a00000e /* 0x003d6d94: bne rando_sticker_convert */
    .word 0xe5923208 /* 0x003d6d98: ldr r3, [r2, #0x208] */
    .word 0xe59fc060 /* 0x003d6d9c: ldr r12, [pc, literal] */
    .word 0xe003300c /* 0x003d6da0: and r3, r3, r12 */
    .word 0xe59fc05c /* 0x003d6da4: ldr r12, [pc, literal] */
    .word 0xe153000c /* 0x003d6da8: cmp r3, r12 ; seed word */
    .word 0x1a000008 /* 0x003d6dac: bne rando_sticker_convert */
    .word 0xe59f3054 /* 0x003d6db0: ldr r3, [pc, literal] */
    .word 0xe0855003 /* 0x003d6db4: add r5, r5, r3 ; ownership GF index */
    .word 0xe1a032a5 /* 0x003d6db8: mov r3, r5, lsr #5 */
    .word 0xe0823103 /* 0x003d6dbc: add r3, r2, r3, lsl #2 */
    .word 0xe5933144 /* 0x003d6dc0: ldr r3, [r3, #0x144] */
    .word 0xe205501f /* 0x003d6dc4: and r5, r5, #31 */
    .word 0xe3a0c001 /* 0x003d6dc8: mov r12, #1 */
    .word 0xe113051c /* 0x003d6dcc: tst r3, r12, lsl r5 */
    .word 0x1a000002 /* 0x003d6dd0: bne rando_sticker_original */
rando_sticker_convert:
    .word 0xe59f0034 /* 0x003d6dd4: ldr r0, [pc, literal] */
    .word 0xebfabb8f /* 0x003d6dd8: bl 0x00285c1c */
    .word 0xe8bd8070 /* 0x003d6ddc: pop {r4-r6, pc} */
rando_sticker_original:
    .word 0xe1a00004 /* 0x003d6de0: mov r0, r4 */
    .word 0xe8bd8070 /* 0x003d6de4: pop {r4-r6, pc} */
    .word 0x003d6e14 /* 0x003d6de8: literal address: table */
    .word 0x0043c190 /* 0x003d6dec: literal data */
    .word 0xffffff80 /* 0x003d6df0: literal data */
    .word 0x0dd68b00 /* 0x003d6df4: literal data */
    .word 0x71620ac8 /* 0x003d6df8: literal data */
    .word 0x80936e14 /* 0x003d6dfc: literal data */
    .word 0x02923801 /* 0x003d6e00: literal data */
    .word 0x0000007f /* 0x003d6e04: literal data */
    .word 0x00000017 /* 0x003d6e08: literal data */
    .word 0x00000690 /* 0x003d6e0c: literal data */
    .word 0x003d6ee0 /* 0x003d6e10: literal address: replacement */
rando_sticker_table:
    .word 0xffffffff /* 0x003d6e14: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6e18: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6e1c: generic save-index lookup data */
    .word 0x56ffffff /* 0x003d6e20: generic save-index lookup data */
    .word 0x393e3d3c /* 0x003d6e24: generic save-index lookup data */
    .word 0x26173b3a /* 0x003d6e28: generic save-index lookup data */
    .word 0x01002718 /* 0x003d6e2c: generic save-index lookup data */
    .word 0x4a210e02 /* 0x003d6e30: generic save-index lookup data */
    .word 0x6c6b2a1b /* 0x003d6e34: generic save-index lookup data */
    .word 0x072d206d /* 0x003d6e38: generic save-index lookup data */
    .word 0x33552211 /* 0x003d6e3c: generic save-index lookup data */
    .word 0x25163534 /* 0x003d6e40: generic save-index lookup data */
    .word 0x1c504f4e /* 0x003d6e44: generic save-index lookup data */
    .word 0x4847462b /* 0x003d6e48: generic save-index lookup data */
    .word 0x0908291a /* 0x003d6e4c: generic save-index lookup data */
    .word 0x4523120a /* 0x003d6e50: generic save-index lookup data */
    .word 0x130b2819 /* 0x003d6e54: generic save-index lookup data */
    .word 0x2c1d6024 /* 0x003d6e58: generic save-index lookup data */
    .word 0x5c5d5e5f /* 0x003d6e5c: generic save-index lookup data */
    .word 0x58595a5b /* 0x003d6e60: generic save-index lookup data */
    .word 0x74757657 /* 0x003d6e64: generic save-index lookup data */
    .word 0x70717273 /* 0x003d6e68: generic save-index lookup data */
    .word 0x100f6e6f /* 0x003d6e6c: generic save-index lookup data */
    .word 0x15141f1e /* 0x003d6e70: generic save-index lookup data */
    .word 0x2f6a6968 /* 0x003d6e74: generic save-index lookup data */
    .word 0x37363130 /* 0x003d6e78: generic save-index lookup data */
    .word 0x54535238 /* 0x003d6e7c: generic save-index lookup data */
    .word 0x3f4d4c4b /* 0x003d6e80: generic save-index lookup data */
    .word 0x0d0c4140 /* 0x003d6e84: generic save-index lookup data */
    .word 0x2e434251 /* 0x003d6e88: generic save-index lookup data */
    .word 0x65033263 /* 0x003d6e8c: generic save-index lookup data */
    .word 0x64040605 /* 0x003d6e90: generic save-index lookup data */
    .word 0xffff4467 /* 0x003d6e94: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6e98: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6e9c: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ea0: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ea4: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ea8: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6eac: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6eb0: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6eb4: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6eb8: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ebc: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ec0: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ec4: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ec8: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ecc: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ed0: generic save-index lookup data */
    .word 0xffffffff /* 0x003d6ed4: generic save-index lookup data */
    .word 0x496261ff /* 0x003d6ed8: generic save-index lookup data */
    .word 0xffffff66 /* 0x003d6edc: generic save-index lookup data */
rando_sticker_replacement:
    .word 0x575f4c53 /* 0x003d6ee0: replacement name data */
    .word 0x41535f36 /* 0x003d6ee4: replacement name data */
    .word 0x4c41444e /* 0x003d6ee8: replacement name data */
    .word 0x0000535f /* 0x003d6eec: replacement name data */
