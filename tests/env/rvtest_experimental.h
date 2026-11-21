// Experimental RISC-V extensions header
// Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
// SPDX-License-Identifier: Apache-2.0
// Contains a macro for each instruction from an unratified RISC-V extension
// so tests can be compiled without requiring the experimental extensions to
// be implemented in the compiler


#ifndef RISCV_ARCH_TEST_EXPERIMENTAL_H
#define RISCV_ARCH_TEST_EXPERIMENTAL_H

#if defined(__ASSEMBLER__) && defined(ENABLE_EXPERIMENTAL_EXTENSIONS)

.macro beqi rs1, cimm, target
  .if \cimm == -1
    .insn b 0x63, 2, \rs1, x0, \target
  .else
    .insn b 0x63, 2, \rs1, x\cimm, \target
  .endif
.endm

.macro bnei rs1, cimm, target
  .if \cimm == -1
    .insn b 0x63, 3, \rs1, x0, \target
  .else
    .insn b 0x63, 3, \rs1, x\cimm, \target
  .endif
.endm

// Zimt: gentag, addtag and checktag are MOP.RR.1 encodings and settag is a MOP.RR.0
// encoding. imm4 (0-15) occupies bits 23:20, the rs2 field with bit 24 = 0.
.macro gentag rd
  .insn r 0x73, 4, 0x43, \rd, x0, x0
.endm

.macro addtag rd, rs1, imm4
  .insn r 0x73, 4, 0x43, \rd, \rs1, x\imm4
.endm

.macro checktag rs1, imm4
  .insn r 0x73, 4, 0x43, x0, \rs1, x\imm4
.endm

.macro settag rs1, imm4
  .insn r 0x73, 4, 0x41, x0, \rs1, x\imm4
.endm

// Zimt, Svatag and Smvatag CSRs. The draft specification does not allocate their
// addresses yet: these are the placeholders of the Sail reference model
// (sail-riscv-wsxarcher, zimt_regs.sail).
// Zimt tag generation exclusion masks, low (0) and high (1) halves
#define CSR_MMTAGEXCLUDE0    0x7C0
#define CSR_MMTAGEXCLUDE1    0x7C1
#define CSR_MENVMTAGEXCLUDE0 0x7C2
#define CSR_MENVMTAGEXCLUDE1 0x7C3
#define CSR_SENVMTAGEXCLUDE0 0x5C0
#define CSR_SENVMTAGEXCLUDE1 0x5C1
#define CSR_HENVMTAGEXCLUDE0 0x6C0
#define CSR_HENVMTAGEXCLUDE1 0x6C1
// Smvatag and Svatag virtually indexed tag table (VITT) bases
#define CSR_MVITT            0x7C4
#define CSR_SVITTS           0x5C2
#define CSR_SVITTU           0x5C3
#define CSR_VSVITTS          0x6C2
#define CSR_VSVITTU          0x6C3

#endif

#endif
