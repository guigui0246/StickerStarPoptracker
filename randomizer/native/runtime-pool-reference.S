.syntax unified
.arm

.section .text.rando_pool_10a36c, "ax"
.org 0x0010a36c
    .word 0xe3a00809 // mov r0, #0x90000 // allocate bytes

.section .text.rando_pool_10a37c, "ax"
.org 0x0010a37c
    .word 0xe3a01809 // mov r1, #0x90000 // clear bytes

.section .text.rando_pool_10a3a8, "ax"
.org 0x0010a3a8
    .word 0xe3540a06 // cmp r4, #0x6000 // initialize cells

.section .text.rando_pool_2b4150, "ax"
.org 0x002b4150
    .word 0xe3550a06 // cmp r5, #0x6000 // forward allocation scan

.section .text.rando_pool_2b41b0, "ax"
.org 0x002b41b0
    .word 0xe3550a06 // cmp r5, #0x6000 // wrapped allocation scan
