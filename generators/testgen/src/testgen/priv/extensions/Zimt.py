##################################
# priv/extensions/Zimt.py
#
# Zimt (memory tagging) test generators for the Sm, S, U and H groups.
# SPDX-License-Identifier: Apache-2.0
##################################

"""Zimt test generators.

Zimt takes its instructions from the Zimop encoding space: gentag, addtag and checktag are MOP.RR.1 encodings and
settag is a MOP.RR.0 encoding, each with bit 24 = 0 and imm4 in bits 23:20. gentag needs rd != x0, rs1 = x0 and
imm4 = 0; addtag needs rd != x0 and imm4 != 0; checktag and settag need rd = x0 and rs1 != x0.

Each group (Sm: M-mode, S: S-mode, U: U-mode, H: VS-mode and VU-mode, entered from HS-mode) generates five files:

- <group>: the instructions with memory tagging disabled, the reset value of xMT_MODE: mseccfg.MT_MODE (M),
  menvcfg.MT_MODE (S), senvcfg.MT_MODE (U and VU) and henvcfg.MT_MODE (VS). gentag then writes 0 to rd, addtag
  copies rs1 to rd, and checktag and settag do nothing. The other MOP.RR.0 and MOP.RR.1 encodings stay Zimop
  instructions, which write 0 to rd.
- <group>_csr: the MT_MODE fields and tag generation exclusion mask CSRs that the group's modes write (WARL
  behavior, and access from each mode), and the software-check exception (cause 18) in medeleg, hedeleg and xcause.
  T-SBI calls read the CSRs from M-mode or HS-mode after each write from a less privileged mode.
- <group>_mt: gentag and addtag with memory tagging enabled, with 4-bit tags and, if the config supports them, 7-bit
  tags, which also shows which MT_MODE field and exclusion mask each mode uses. A mask either permits one tag value,
  or the test checks only that each draw is a permitted value, so the results do not depend on how a hart draws its
  pseudorandom tags. U_mt needs S-mode, where senvcfg.MT_MODE and senvmtagexclude are.
- <group>_settag: settag with memory tagging enabled, with 4-bit and 7-bit tags, which stores the tags of 1-16
  chunks in the tag table of the mode: mvitt (Smvatag), svitts, svittu, vsvitts or vsvittu (Svatag). Pointer
  masking (xenvcfg.PMM, mseccfg.PMM) ignores the pointer tags in the address. A pattern surrounds the tags, so the
  signature shows each tag byte and half byte that settag writes or keeps; with 4-bit tags it reads, modifies and
  writes the bytes it shares with other chunks. Sm_settag sweeps the first chunk and the chunk count, and rs1, and
  checks a zero-extended masked address and MPRV; S_settag, with Sv39 translation, crosses into tag table pages that
  raise store/AMO page faults and access faults (Svpbmt IO memory is not idempotent, NC memory is), and checks a
  sign-extended masked address; U_settag and H_settag check which tag table each mode uses, and H_settag guest
  translation, with its guest-page faults. The access-fault cases need RVMODEL_ACCESS_FAULT_ADDRESS_STORE and
  RVMODEL_ACCESS_FAULT_ADDRESS_LOAD. settag never raises a misaligned exception here, as in the Sail model; the
  specification says both that tag accesses must not raise one and that settag may without misaligned support.
- <group>_checktag: checktag, and the implicit tag checks of loads and stores, with memory tagging enabled, with 4-bit
  and 7-bit tags. With Bare first-stage address translation (satp, or vsatp at V=1) in the effective privilege mode,
  the scalar loads and stores of data that do not use sp as the base register are checked: a mismatch raises a software-check exception (xtval 4) before
  the access, a fault of a tag load a load access fault. A data page has its tags in the tag table through the tag
  table base of the mode. Sm_checktag sweeps checktag between mismatching chunks, and checks each kind of load and
  store (integer, floating-point and compressed ones), misaligned ones over two chunks, ones through sp and the
  ordering with older tag stores, none of which may raise an exception with memory tagging enabled in M-mode, where
  the trap handler runs; then mismatches with MPRV, which check with S-mode's MT_MODE and tag table. U_checktag and
  H_checktag (VS-mode, VU-mode) check the same, with mismatches, and tag loads and data accesses that fault; S_checktag
  and H_checktag check checktag with address translation, its load page faults, guest-page faults and access faults,
  and loads and stores, which are not checked with first-stage address translation. With the G stage only (vsatp
  Bare), H_checktag checks that they are, with load guest-page faults of their tag loads.

4-bit pointer tags are mandatory and 7-bit ones optional: the tests that need them are assembled only for a config
that defines UDB_ZIMT_POINTER_TAG_WIDTH_7 (ZIMT_POINTER_TAG_WIDTH_7 in the experimental_params of test_config.yaml).
Without them, MT_MODE = 11 is reserved, and the exclusion mask bits above 15 may be hardwired to zero.

The tests enable memory tagging only around code whose other loads and stores, such as the signature's, use sp: a
hart with tag tables (Svatag, Smvatag) checks the tags of the others. Only the settag and checktag tests set up a tag
table. Trap handlers run in modes where memory tagging stays disabled, or with translation, whose pages without
PTE.MTAG are not tag checked (the S-mode handlers of S_settag and S_checktag).

Each register field is swept over x0-x31 where the instruction allows it. A swept register that the framework
uses is saved and restored around the instruction. checktag and settag write no register: the trap signature
checks that they raise no exception.
"""

from collections.abc import Callable
from typing import NamedTuple

from testgen.asm.csr import gen_csr_read_sigupd, gen_csr_write_sigupd
from testgen.asm.helpers import comment_banner, gated, load_constant, write_sigupd
from testgen.asm.tsbi import tsbi_call
from testgen.data.state import TestData
from testgen.data.test_chunk import TestChunk
from testgen.priv.extensions.sv.generate import guest_translation_setup, guest_translation_teardown
from testgen.priv.extensions.sv.page_tables import (
    SV39,
    SV39X4,
    VS_SV39,
    PteExpression,
    PteFlags,
    create_page_mapping,
    guest_table_data,
    lower_table_data,
    write_pte,
)
from testgen.priv.registry import add_priv_test_generator

MASK64 = (1 << 64) - 1
MASK128 = (1 << 128) - 1
# Defined for a config whose Zimt supports 7-bit pointer tags (experimental_params in test_config.yaml). 4-bit pointer
# tags are mandatory.
TAG7 = "UDB_ZIMT_POINTER_TAG_WIDTH_7"
# rs1 of addtag, checktag and settag: a pointer with a nonzero pointer tag in bits 63:57
TAGGED_POINTER = 0x5A00_0000_8000_1230
# Written to rd before each instruction that writes rd, so that the signature shows the write
RD_CANARY = 0xA5A5_A5A5_A5A5_A5A5

MT_MODE_LSB = 34  # MT_MODE: bits 35:34 of mseccfg, menvcfg, senvcfg and henvcfg
VUMT_MODE_LSB = 50  # hstatus.VUMT_MODE: bits 51:50
MT_DISABLED, MT_RESERVED, MT_TAG4, MT_TAG7 = 0b00, 0b01, 0b10, 0b11
MT_NAMES = {MT_DISABLED: "disabled", MT_RESERVED: "reserved", MT_TAG4: "tag4", MT_TAG7: "tag7"}
TAG_BITS = {MT_TAG4: 4, MT_TAG7: 7}  # pointer_tag_width
SW_CHECK = 18  # software-check exception code

# rs1 of addtag with memory tagging enabled, whose tag wraps for the larger imm4: tag 5 of 4-bit tags (bits 63:60)
# and tag 120 of 7-bit tags (bits 63:57)
ADDTAG_POINTER = {MT_TAG4: TAGGED_POINTER, MT_TAG7: 0xF000_0000_8000_1230}

# Tag generation exclusion mask CSRs (low, high) of each controlled environment, named in rvtest_experimental.h.
# M: mmtagexclude, S/HS: menvmtagexclude, U and VU: senvmtagexclude, VS: henvmtagexclude.
MTAGEXCLUDE = {
    "m": ("CSR_MMTAGEXCLUDE0", "CSR_MMTAGEXCLUDE1"),
    "menv": ("CSR_MENVMTAGEXCLUDE0", "CSR_MENVMTAGEXCLUDE1"),
    "senv": ("CSR_SENVMTAGEXCLUDE0", "CSR_SENVMTAGEXCLUDE1"),
    "henv": ("CSR_HENVMTAGEXCLUDE0", "CSR_HENVMTAGEXCLUDE1"),
}
# Preprocessor condition under which the exclusion mask CSRs of each environment exist
MTAGEXCLUDE_GATE = {
    "m": None,
    "menv": "defined(S_SUPPORTED)",
    "senv": "defined(S_SUPPORTED)",
    "henv": "defined(H_SUPPORTED)",
}
# Environments whose exclusion mask CSRs code in each mode may access, when they exist. S-mode is HS-mode with H,
# which accesses the hypervisor CSRs; senvmtagexclude has no VS-level copy, so VS-mode accesses it.
MTAGEXCLUDE_ACCESS = {"S": ("senv", "henv"), "VS": ("senv",), "U": (), "VU": ()}
# Values written to the low exclusion mask CSRs. One that excludes all of the tag values 0-15 is illegal, and
# which bits the CSR then leaves clear is implementation-defined: only check that one of 0-15 is permitted.
MTAGEXCLUDE0_VALUES = (
    MASK64,
    0x0000_0000_0000_FFFF,
    0x5A5A_5A5A_5A5A_FFFF,
    0xFFFF_FFFF_FFFF_7FFF,
    0xFFFF_FFFF_FFFF_FFFE,
    0x0000_0000_0000_8001,
    0xA5A5_A5A5_A5A5_5A5A,
    0,
)
# Values written to the high exclusion mask CSRs, which are fully writable with 7-bit tags. Without them, the bits
# of a mask above 15 may be hardwired to zero.
MTAGEXCLUDE1_VALUES = (MASK64, 0xA5A5_A5A5_A5A5_5A5A, 0x8000_0000_0000_0001, 0)
# 7-bit tags above 15 that gentag draws from a mask permitting only that value and 0: the first and last value of
# each group of 16 values, which covers both mask CSRs and the boundaries between them
HIGH_TAGS = (16, 31, 32, 47, 48, 63, 64, 79, 80, 95, 96, 111, 112, 127)
# Draws of the high-tag tests: a hart drawing uniformly misses the high tag in all of them with probability 2^-128
HIGH_TAG_DRAWS = 128
# Masks permitting several tag values: (name, MT_MODE, low CSR, high CSR). The check for each is in _not_permitted.
SEVERAL_TAG_MASKS = (
    ("tag4_odd", MT_TAG4, 0x0000_0000_0000_5555, 0),  # 1, 3, ..., 15
    ("tag7_even", MT_TAG7, 0xAAAA_AAAA_AAAA_AAAA, 0xAAAA_AAAA_AAAA_AAAA),  # 0, 2, ..., 126
    ("tag7_ends", MT_TAG7, 0xFFFF_FFFF_FFFF_0000, 0x01FF_FFFF_FFFF_FFFF),  # 0-15 and 121-127
)
SEVERAL_TAG_DRAWS = 32


def _tag_field(tag: int, mt_mode: int) -> int:
    """A pointer with the pointer tag field set to tag: bits 63:60 with 4-bit tags, bits 63:57 with 7-bit tags."""
    return tag << (64 - TAG_BITS[mt_mode])


def _only(tag: int) -> tuple[int, int]:
    """The exclusion mask (low CSR, high CSR) that permits only tag."""
    mask = MASK128 & ~(1 << tag)
    return mask & MASK64, mask >> 64


def _check_sig_reg(test_data: TestData) -> None:
    """Memory tagging may only be enabled around signature updates that use sp, which no tag check covers."""
    assert test_data.int_regs.sig_reg == 2, "Zimt tests with memory tagging enabled need sp as the signature pointer"


def _tag7(lines: list[str]) -> list[str]:
    """``lines``, assembled only for a config with 7-bit pointer tags."""
    return gated(lines, f"defined({TAG7})")


def _as_written_if_zero(reg: int, tmp: int | None, value: int, low_bits: int) -> list[str]:
    """Without 7-bit pointer tags, record a mask CSR read into reg the same on harts that keep or hardwire its high bits.

    The exclusion mask bits above 15 may then be hardwired to zero. They are the bits of reg above low_bits (16 for a
    low CSR, 0 for a high CSR), which were written with value: when they read 0, take them as written. tmp is a
    scratch register, unused when low_bits is 0.
    """
    high = value & MASK64 & ~((1 << low_bits) - 1)
    if not high:
        return []
    test = [f"srli x{tmp}, x{reg}, {low_bits}", f"bnez x{tmp}, 1f"] if low_bits else [f"bnez x{reg}, 1f"]
    return [
        f"#ifndef {TAG7} // the mask bits above 15 may be hardwired to zero: if they read 0, take them as written",
        *test,
        f"LI(x{tmp if low_bits else reg}, {high:#x})",
        *([f"or x{reg}, x{reg}, x{tmp}"] if low_bits else []),
        "1:",
        f"#endif // {TAG7}",
    ]


def _write_field(csr: str, lsb: int, value: int, val: int, tmp: int) -> list[str]:
    """Write value to the 2-bit field at lsb of csr with one csrw that keeps the other bits."""
    lines = [f"csrr x{val}, {csr}", f"LI(x{tmp}, {~(0b11 << lsb) & MASK64:#x})", f"and x{val}, x{val}, x{tmp}"]
    if value:
        lines += [f"LI(x{tmp}, {value << lsb:#x})", f"or x{val}, x{val}, x{tmp}"]
    return [*lines, f"csrw {csr}, x{val}"]


def _write_mask(env: str, low: int, high: int, val: int) -> list[str]:
    """Write the exclusion mask CSRs of env."""
    csr0, csr1 = MTAGEXCLUDE[env]
    return [f"LI(x{val}, {low:#x})", f"csrw {csr0}, x{val}", f"LI(x{val}, {high:#x})", f"csrw {csr1}, x{val}"]


def _saved(reg: int, save_reg: int, lines: list[str]) -> list[str]:
    """``lines``, with ``reg`` saved in ``save_reg`` and restored around them, unless ``reg`` is x0."""
    if reg == 0:
        return lines
    return [f"mv x{save_reg}, x{reg}", *lines, f"mv x{reg}, x{save_reg}"]


# ---------------------------------------------------------------------------------------------------------------
# Instructions, swept over their register and immediate fields
# ---------------------------------------------------------------------------------------------------------------


def _state(mt_mode: int) -> str:
    """Coverpoint name part for the tagging state of the mode the instructions run in."""
    return f"mt_{MT_NAMES[mt_mode]}"


def _expected(mt_mode: int) -> str:
    """Comment for what gentag and addtag write in a mode with MT_MODE mt_mode."""
    if mt_mode == MT_DISABLED:
        return "gentag: rd = 0; addtag: rd = rs1"
    shift = 64 - TAG_BITS[mt_mode]
    return f"gentag: rd = permitted tag << {shift}; addtag: rd = rs1 + (imm4 << {shift})"


def _gentag_tests(test_data: TestData, cg: str, mode: str, mt_mode: int) -> list[str]:
    """gentag with each rd != x0. With memory tagging enabled, the mask must permit only one tag."""
    coverpoint = f"cp_gentag_{_state(mt_mode)}"
    pool = test_data.int_regs.get_registers(3)
    lines = [comment_banner(coverpoint, f"In {mode}-mode, gentag rd for each rd != x0.  {_expected(mt_mode)}")]
    for rd in range(1, 32):
        save_reg, res_reg = [r for r in pool if r != rd][:2]
        lines.extend(
            [
                *_saved(
                    rd,
                    save_reg,
                    [
                        f"LI(x{rd}, {RD_CANARY:#x})",
                        test_data.add_testcase(f"{mode}_rd_x{rd}", coverpoint, cg),
                        f"gentag x{rd}",
                        f"mv x{res_reg}, x{rd}",
                    ],
                ),
                write_sigupd(res_reg, test_data),
            ]
        )
    test_data.int_regs.return_registers(pool)
    return lines


def _addtag_tests(test_data: TestData, cg: str, mode: str, mt_mode: int) -> list[str]:
    """addtag with each imm4 != 0, each rd != x0, each rs1, and rd = rs1."""
    state = _state(mt_mode)
    pointer = ADDTAG_POINTER.get(mt_mode, TAGGED_POINTER)
    pool = test_data.int_regs.get_registers(4)
    src_reg, dst_reg = pool[:2]

    coverpoint = f"cp_addtag_{state}_imm"
    lines = [
        comment_banner(coverpoint, f"In {mode}-mode, addtag rd, rs1, imm4 for each imm4 != 0.  {_expected(mt_mode)}")
    ]
    for imm in range(1, 16):
        lines.extend(
            [
                f"LI(x{src_reg}, {pointer:#x})",
                f"LI(x{dst_reg}, {RD_CANARY:#x})",
                test_data.add_testcase(f"{mode}_imm{imm}", coverpoint, cg),
                f"addtag x{dst_reg}, x{src_reg}, {imm}",
                write_sigupd(dst_reg, test_data),
            ]
        )

    coverpoint = f"cp_addtag_{state}_rd"
    lines.append(
        comment_banner(coverpoint, f"In {mode}-mode, addtag rd, rs1, imm4 for each rd != x0.  {_expected(mt_mode)}")
    )
    for rd in range(1, 32):
        rs1, save_reg, res_reg = [r for r in pool if r != rd][:3]
        lines.extend(
            [
                f"LI(x{rs1}, {pointer:#x})",
                *_saved(
                    rd,
                    save_reg,
                    [
                        f"LI(x{rd}, {RD_CANARY:#x})",
                        test_data.add_testcase(f"{mode}_rd_x{rd}", coverpoint, cg),
                        f"addtag x{rd}, x{rs1}, {1 + rd % 15}",
                        f"mv x{res_reg}, x{rd}",
                    ],
                ),
                write_sigupd(res_reg, test_data),
            ]
        )

    coverpoint = f"cp_addtag_{state}_rs1"
    lines.append(
        comment_banner(coverpoint, f"In {mode}-mode, addtag rd, rs1, imm4 for each rs1.  {_expected(mt_mode)}")
    )
    for rs1 in range(32):
        rd, save_reg = [r for r in pool if r != rs1][:2]
        lines.extend(
            [
                f"LI(x{rd}, {RD_CANARY:#x})",
                *_saved(
                    rs1,
                    save_reg,
                    [
                        *([f"LI(x{rs1}, {pointer:#x})"] if rs1 else []),
                        test_data.add_testcase(f"{mode}_rs1_x{rs1}", coverpoint, cg),
                        f"addtag x{rd}, x{rs1}, {1 + rs1 % 15}",
                    ],
                ),
                write_sigupd(rd, test_data),
            ]
        )

    coverpoint = f"cp_addtag_{state}_rd_rs1"
    lines.extend(
        [
            comment_banner(coverpoint, f"In {mode}-mode, addtag rd, rd, imm4.  {_expected(mt_mode)}"),
            f"LI(x{src_reg}, {pointer:#x})",
            test_data.add_testcase(f"{mode}_rd_eq_rs1", coverpoint, cg),
            f"addtag x{src_reg}, x{src_reg}, 15",
            write_sigupd(src_reg, test_data),
        ]
    )
    test_data.int_regs.return_registers(pool)
    return lines


def _no_rd_tests(test_data: TestData, cg: str, mode: str, instr: str) -> list[str]:
    """checktag or settag with each imm4 and each rs1 != x0, with memory tagging disabled. No exception."""
    pool = test_data.int_regs.get_registers(2)

    coverpoint = f"cp_{instr}_mt_disabled_imm"
    lines = [comment_banner(coverpoint, f"In {mode}-mode, {instr} rs1, imm4 for each imm4.  No exception")]
    for imm in range(16):
        lines.extend(
            [
                f"LI(x{pool[0]}, {TAGGED_POINTER:#x})",
                test_data.add_testcase(f"{mode}_imm{imm}", coverpoint, cg),
                f"{instr} x{pool[0]}, {imm}",
            ]
        )

    coverpoint = f"cp_{instr}_mt_disabled_rs1"
    lines.append(comment_banner(coverpoint, f"In {mode}-mode, {instr} rs1, imm4 for each rs1 != x0.  No exception"))
    for rs1 in range(1, 32):
        save_reg = next(r for r in pool if r != rs1)
        lines.extend(
            _saved(
                rs1,
                save_reg,
                [
                    f"LI(x{rs1}, {TAGGED_POINTER:#x})",
                    test_data.add_testcase(f"{mode}_rs1_x{rs1}", coverpoint, cg),
                    f"{instr} x{rs1}, {rs1 % 16}",
                ],
            )
        )
    test_data.int_regs.return_registers(pool)
    return lines


def _non_zimt_mop_tests(test_data: TestData, cg: str, mode: str, mt_mode: int = MT_DISABLED) -> list[str]:
    """MOP.RR.1 and MOP.RR.0 encodings that each miss one condition of a Zimt instruction.

    They stay Zimop instructions, also with memory tagging enabled: rd = 0, or nothing when rd = x0.
    """
    coverpoint = "cp_mop_rr_not_zimt" if mt_mode == MT_DISABLED else f"cp_mop_rr_not_zimt_{_state(mt_mode)}"
    rs1, rd = test_data.int_regs.get_registers(2)
    # (bin, instruction, whether it writes rd). The rs2 field holds {bit 24, imm4}.
    cases = [(f"rr1_bit24_imm{imm}", f"mop.rr.1 x{rd}, x{rs1}, x{16 + imm}", True) for imm in range(16)]
    cases += [
        ("rr1_imm0", f"mop.rr.1 x{rd}, x{rs1}, x0", True),  # neither gentag (rs1 != x0) nor addtag (imm4 = 0)
        ("rr1_rd0_bit24", f"mop.rr.1 x0, x{rs1}, x21", False),  # not checktag: bit 24 = 1
        ("rr1_rd0_rs1_0", "mop.rr.1 x0, x0, x5", False),  # not checktag: rs1 = x0
        ("rr0_rd", f"mop.rr.0 x{rd}, x{rs1}, x5", True),  # not settag: rd != x0
        ("rr0_rd0_bit24", f"mop.rr.0 x0, x{rs1}, x21", False),  # not settag: bit 24 = 1
        ("rr0_rd0_rs1_0", "mop.rr.0 x0, x0, x5", False),  # not settag: rs1 = x0
    ]
    lines = [
        comment_banner(
            coverpoint,
            f"In {mode}-mode, MOP.RR.1 and MOP.RR.0 encodings that are not Zimt instructions.\n"
            "rd = 0, or no effect when rd = x0",
        ),
        f"LI(x{rs1}, {TAGGED_POINTER:#x})",
    ]
    for name, instr, writes_rd in cases:
        lines.extend(
            [
                *([f"LI(x{rd}, {RD_CANARY:#x})"] if writes_rd else []),
                test_data.add_testcase(f"{mode}_{name}", coverpoint, cg),
                instr,
                *([write_sigupd(rd, test_data)] if writes_rd else []),
            ]
        )
    test_data.int_regs.return_registers([rs1, rd])
    return lines


def _mt_disabled_tests(test_data: TestData, cg: str, mode: str) -> list[str]:
    """Every Zimt instruction, and the MOP.RR encodings around them, with memory tagging disabled in ``mode``."""
    return [
        *_gentag_tests(test_data, cg, mode, MT_DISABLED),
        *_addtag_tests(test_data, cg, mode, MT_DISABLED),
        *_no_rd_tests(test_data, cg, mode, "checktag"),
        *_no_rd_tests(test_data, cg, mode, "settag"),
        *_non_zimt_mop_tests(test_data, cg, mode),
    ]


# ---------------------------------------------------------------------------------------------------------------
# CSRs
# ---------------------------------------------------------------------------------------------------------------


def _mt_mode_warl_tests(test_data: TestData, cg: str, csr: str, lsb: int = MT_MODE_LSB) -> list[str]:
    """Write each MT_MODE encoding over each legal one with one csrw that keeps the other bits; record the field.

    The reserved encoding 01 is legalized to an implementation-defined value, and so is 11 without 7-bit pointer
    tags, so after writing them only check that the field holds a legal value: not 01, and not 11 either without
    7-bit pointer tags. The field holds 11 only with them.
    """
    field = "MT_MODE" if lsb == MT_MODE_LSB else "VUMT_MODE"
    coverpoint = f"cp_{field.lower()}_warl"
    save, val, tmp = test_data.int_regs.get_registers(3)
    tag4_legal = [f"andi x{val}, x{val}, 1", f"seqz x{val}, x{val}    # 1 if {field} is legal: 00 or 10"]
    lines = [
        comment_banner(
            f"{coverpoint} ({csr})",
            f"Write each {field} encoding over 00, 10 and 11 (with 7-bit tags) with one csrw that keeps the other\n"
            f"bits. Record {field}: the value written, or whether it is legal after the reserved 01, and after 11\n"
            "without 7-bit tags",
        ),
        f"csrr x{save}, {csr}",
    ]
    for old in (MT_DISABLED, MT_TAG4, MT_TAG7):
        cases = []
        for new in (MT_DISABLED, MT_RESERVED, MT_TAG4, MT_TAG7):
            cases += [
                *_write_field(csr, lsb, old, val, tmp),
                test_data.add_testcase(f"{csr}_{MT_NAMES[old]}_to_{MT_NAMES[new]}", coverpoint, cg),
                *_write_field(csr, lsb, new, val, tmp),
                f"csrr x{val}, {csr}",
                f"srli x{val}, x{val}, {lsb}",
                f"andi x{val}, x{val}, 0b11",
            ]
            if new == MT_RESERVED:
                cases += [
                    f"#ifdef {TAG7}",
                    f"xori x{val}, x{val}, {MT_RESERVED}",
                    f"snez x{val}, x{val}    # 1 if {field} is legal: not 01",
                    "#else",
                    *tag4_legal,
                    f"#endif // {TAG7}",
                ]
            elif new == MT_TAG7:
                cases += [f"#ifndef {TAG7} // 11 is reserved", *tag4_legal, f"#endif // {TAG7}"]
            cases.append(write_sigupd(val, test_data))
        lines += _tag7(cases) if old == MT_TAG7 else cases
    lines.append(f"csrw {csr}, x{save}")
    test_data.int_regs.return_registers([save, val, tmp])
    return lines


def _mtagexclude_warl_tests(test_data: TestData, cg: str, env: str) -> list[str]:
    """Write values to the exclusion mask CSRs of env and read them back.

    Without 7-bit pointer tags, the bits above 15 may be hardwired to zero, so a read of 0 there counts as written.
    """
    csr0, csr1 = MTAGEXCLUDE[env]
    save0, save1, val, tmp = test_data.int_regs.get_registers(4)
    coverpoint = "cp_mtagexclude0_warl"
    lines = [
        comment_banner(
            f"{coverpoint} ({env})",
            "Write values to the low exclusion mask CSR and record it: the value written, except that one\n"
            "excluding all of the tag values 0-15 is illegal; then record whether one of 0-15 is permitted",
        ),
        f"csrr x{save0}, {csr0}",
        f"csrr x{save1}, {csr1}",
    ]
    for value in MTAGEXCLUDE0_VALUES:
        lines += [
            f"LI(x{val}, {value:#x})",
            test_data.add_testcase(f"{env}0_{value:016x}", coverpoint, cg),
            f"csrw {csr0}, x{val}",
            f"csrr x{val}, {csr0}",
        ]
        if value & 0xFFFF == 0xFFFF:
            lines += [
                f"not x{val}, x{val}",
                f"slli x{val}, x{val}, 48",
                f"snez x{val}, x{val}    # 1 if one of the tag values 0-15 is permitted",
            ]
        else:
            lines += _as_written_if_zero(val, tmp, value, 16)
        lines.append(write_sigupd(val, test_data))
    coverpoint = "cp_mtagexclude1_write"
    lines.append(
        comment_banner(f"{coverpoint} ({env})", "Write values to the high exclusion mask CSR and read them back")
    )
    for value in MTAGEXCLUDE1_VALUES:
        lines += [
            f"LI(x{val}, {value:#x})",
            test_data.add_testcase(f"{env}1_{value:016x}", coverpoint, cg),
            f"csrw {csr1}, x{val}",
            f"csrr x{val}, {csr1}",
            *_as_written_if_zero(val, None, value, 0),
            write_sigupd(val, test_data),
        ]
    lines += [f"csrw {csr0}, x{save0}", f"csrw {csr1}, x{save1}"]
    test_data.int_regs.return_registers([save0, save1, val, tmp])
    return lines


def _mtagexclude_reset_tests(test_data: TestData, cg: str) -> list[str]:
    """Read every exclusion mask CSR that exists before any write: they reset to 0."""
    coverpoint = "cp_mtagexclude_reset"
    reg = test_data.int_regs.get_register()
    lines = [comment_banner(coverpoint, "Read each exclusion mask CSR after reset.  0")]
    for env, pair in MTAGEXCLUDE.items():
        reads = []
        for half, csr in enumerate(pair):
            reads += [
                test_data.add_testcase(f"{env}{half}", coverpoint, cg),
                gen_csr_read_sigupd(reg, (csr, None), test_data),
            ]
        lines += gated(reads, MTAGEXCLUDE_GATE[env])
    test_data.int_regs.return_register(reg)
    return lines


def _csr_access_tests(test_data: TestData, cg: str, mode: str) -> list[str]:
    """Read, write and read again each exclusion mask CSR from mode.

    An access the mode may not make raises an exception, which the trap signature records. T-SBI calls, which access
    the CSRs from M-mode or HS-mode, write a value to each CSR first and read it after the write: a write that raised
    an exception leaves that value. The values permit tag values 0-15. Those of the low CSRs are below bit 16 and
    those of the high CSRs 0, which every hart keeps; the ones written from mode go above bit 15 only in the high
    CSRs, where a hart without 7-bit pointer tags may not keep them.
    """
    coverpoint = "cp_csr_access"
    reg = test_data.int_regs.get_register()
    lines = [
        comment_banner(
            coverpoint,
            f"In {mode}-mode, read each exclusion mask CSR, write it with csrrw and read it again.\n"
            "Illegal or virtual instruction for the CSRs that the mode may not access. After the write,\n"
            "read the CSR with a T-SBI call: the value written before, unless the write reached the CSR",
        )
    ]
    for i, (env, (csr0, csr1)) in enumerate(MTAGEXCLUDE.items()):
        lines += gated(
            [f"LI(x{reg}, {0x0C30 + i:#x})", tsbi_call(f"csrw {csr0}, x{reg}"), tsbi_call(f"csrw {csr1}, x0")],
            MTAGEXCLUDE_GATE[env],
        )
    for i, (env, pair) in enumerate(MTAGEXCLUDE.items()):
        for half, csr in enumerate(pair):
            name = f"{env}{half}"
            value = 0x5A5A_0000_0000_0000 | (2 * i + 2) if half else 0x5A00 | (2 * i + 1)
            # A read of a high CSR that mode wrote, which may hold 0 instead
            written = _as_written_if_zero(reg, None, value, 0) if half and env in MTAGEXCLUDE_ACCESS[mode] else []
            lines += [
                f"LI(x{reg}, 42)    # known value; a trapping access leaves it unchanged",
                test_data.add_testcase(f"{mode}_{name}_read", coverpoint, cg),
                f"csrr x{reg}, {csr}",
                write_sigupd(reg, test_data),
                f"LI(x{reg}, {value:#x})",
                test_data.add_testcase(f"{mode}_{name}_write", coverpoint, cg),
                f"csrrw x{reg}, {csr}, x{reg}    # x{reg} = the old value",
                write_sigupd(reg, test_data),
                *gated(
                    [tsbi_call(f"csrr x{reg}, {csr}"), *written, write_sigupd(reg, test_data)],
                    MTAGEXCLUDE_GATE[env],
                ),
                f"LI(x{reg}, 42)",
                test_data.add_testcase(f"{mode}_{name}_reread", coverpoint, cg),
                f"csrr x{reg}, {csr}",
                *written,
                write_sigupd(reg, test_data),
            ]
    test_data.int_regs.return_register(reg)
    return lines


def _swcheck_deleg_tests(test_data: TestData, cg: str, csr: str) -> list[str]:
    """Set and clear bit 18 (software check) of medeleg or hedeleg, recording the bit: it is writable."""
    coverpoint = "cp_swcheck_deleg"
    save, val, bit = test_data.int_regs.get_registers(3)
    lines = [
        comment_banner(f"{coverpoint} ({csr})", f"Set and clear {csr}[18] (software check) and record it"),
        f"csrr x{save}, {csr}",
        f"LI(x{bit}, {1 << SW_CHECK:#x})",
    ]
    for op in ("csrs", "csrc"):
        lines += [
            test_data.add_testcase(f"{csr}_{op}", coverpoint, cg),
            f"{op} {csr}, x{bit}",
            f"csrr x{val}, {csr}",
            f"srli x{val}, x{val}, {SW_CHECK}",
            f"andi x{val}, x{val}, 1",
            write_sigupd(val, test_data),
        ]
    lines.append(f"csrw {csr}, x{save}")
    test_data.int_regs.return_registers([save, val, bit])
    return lines


def _swcheck_cause_tests(test_data: TestData, cg: str, csr: str) -> list[str]:
    """Write 18 (software check) to mcause, scause or vscause and read it back."""
    coverpoint = "cp_swcheck_cause"
    save, val = test_data.int_regs.get_registers(2)
    lines = [
        comment_banner(f"{coverpoint} ({csr})", f"Write 18 (software check) to {csr} and read it back.  18"),
        f"csrr x{save}, {csr}",
        f"LI(x{val}, {SW_CHECK})",
        test_data.add_testcase(f"{csr}_{SW_CHECK}", coverpoint, cg),
        gen_csr_write_sigupd(val, csr, test_data),
        f"csrw {csr}, x{save}",
    ]
    test_data.int_regs.return_registers([save, val])
    return lines


# ---------------------------------------------------------------------------------------------------------------
# Memory tagging enabled
# ---------------------------------------------------------------------------------------------------------------


def _gentag_tag_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """M-mode gentag with mmtagexclude permitting only one of the tag values 0-15, for each of them.

    With 4-bit tags, also with the mask bits of tags 16-127 clear, which gentag ignores then.
    """
    coverpoint = f"cp_gentag_{_state(mt_mode)}_tag"
    val, rd = test_data.int_regs.get_registers(2)
    lines = [
        comment_banner(
            coverpoint, f"In M-mode, gentag with each tag 0-15 the only one permitted.  {_expected(mt_mode)}"
        )
    ]
    for high_clear in (True, False) if mt_mode == MT_TAG4 else (False,):
        for tag in range(16):
            low, high = (0xFFFF & ~(1 << tag), 0) if high_clear else _only(tag)
            lines += [
                *_write_mask("m", low, high, val),
                f"LI(x{rd}, {RD_CANARY:#x})",
                test_data.add_testcase(f"tag{tag}{'_high_clear' if high_clear else ''}", coverpoint, cg),
                f"gentag x{rd}",
                write_sigupd(rd, test_data),
            ]
    test_data.int_regs.return_registers([val, rd])
    return lines


def _gentag_high_tag_tests(test_data: TestData, cg: str) -> list[str]:
    """M-mode gentag with 7-bit tags and the mask permitting only 0 and one tag above 15.

    Draw until that tag comes, recording whether it came within HIGH_TAG_DRAWS draws, with only 0 before it.
    """
    coverpoint = "cp_gentag_mt_tag7_high"
    res, exp, cnt, ok = test_data.int_regs.get_registers(4)
    lines = [
        comment_banner(
            coverpoint,
            f"In M-mode with 7-bit tags, permit only 0 and a tag above 15, and draw up to {HIGH_TAG_DRAWS} times.\n"
            "1 if the tag came, with only 0 before it",
        )
    ]
    for tag in HIGH_TAGS:
        mask = MASK128 & ~1 & ~(1 << tag)
        lines += [
            *_write_mask("m", mask & MASK64, mask >> 64, res),
            f"LI(x{exp}, {_tag_field(tag, MT_TAG7):#x})",
            f"li x{cnt}, {HIGH_TAG_DRAWS}",
            f"li x{ok}, 0",
            test_data.add_testcase(f"tag{tag}", coverpoint, cg),
            "81:",
            f"gentag x{res}",
            f"beq x{res}, x{exp}, 82f    # drew {tag}",
            f"bnez x{res}, 83f    # drew neither 0 nor {tag}",
            f"addi x{cnt}, x{cnt}, -1",
            f"bnez x{cnt}, 81b",
            "j 83f",
            "82:",
            f"li x{ok}, 1",
            "83:",
            write_sigupd(ok, test_data),
        ]
    test_data.int_regs.return_registers([res, exp, cnt, ok])
    return lines


def _not_permitted(name: str, res: int, tag: int, bad: int) -> list[str]:
    """Set bad to nonzero if the gentag result in res is not a pointer with a tag that mask name permits."""
    if name == "tag4_odd":
        return [
            f"slli x{bad}, x{res}, 4    # the bits below the tag must be 0",
            f"srli x{tag}, x{res}, 60",
            f"andi x{tag}, x{tag}, 1",
            f"xori x{tag}, x{tag}, 1    # even tags are excluded",
            f"or x{bad}, x{bad}, x{tag}",
        ]
    if name == "tag7_even":
        return [
            f"slli x{bad}, x{res}, 7    # the bits below the tag must be 0",
            f"srli x{tag}, x{res}, 57",
            f"andi x{tag}, x{tag}, 1    # odd tags are excluded",
            f"or x{bad}, x{bad}, x{tag}",
        ]
    assert name == "tag7_ends", name
    return [
        f"slli x{bad}, x{res}, 7    # the bits below the tag must be 0",
        f"srli x{tag}, x{res}, 57",
        f"addi x{tag}, x{tag}, -16",
        f"sltiu x{tag}, x{tag}, 105    # tags 16-120 are excluded",
        f"or x{bad}, x{bad}, x{tag}",
    ]


def _gentag_several_tag_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """M-mode gentag with masks permitting several tags: record whether every draw was a permitted tag."""
    coverpoint = "cp_gentag_mt_several"
    res, tag, bad, cnt, ok = test_data.int_regs.get_registers(5)
    lines = [
        comment_banner(
            f"{coverpoint} ({MT_NAMES[mt_mode]})",
            f"In M-mode, draw {SEVERAL_TAG_DRAWS} tags from masks permitting several.  1 if all were permitted",
        )
    ]
    for name, mask_mt_mode, low, high in SEVERAL_TAG_MASKS:
        if mask_mt_mode != mt_mode:
            continue
        lines += [
            *_write_mask("m", low, high, res),
            f"li x{cnt}, {SEVERAL_TAG_DRAWS}",
            f"li x{ok}, 1",
            test_data.add_testcase(name, coverpoint, cg),
            "84:",
            f"gentag x{res}",
            *_not_permitted(name, res, tag, bad),
            f"beqz x{bad}, 85f",
            f"li x{ok}, 0",
            "85:",
            f"addi x{cnt}, x{cnt}, -1",
            f"bnez x{cnt}, 84b",
            write_sigupd(ok, test_data),
        ]
    test_data.int_regs.return_registers([res, tag, bad, cnt, ok])
    return lines


def _mt_mode_tests(test_data: TestData, cg: str, mode: str, mt_mode: int, tag: int) -> list[str]:
    """gentag, and addtag with and without a wrapping tag, in mode, where memory tagging is enabled with mt_mode and
    the exclusion mask permits only tag."""
    _check_sig_reg(test_data)
    bits = TAG_BITS[mt_mode]
    low_bits = TAGGED_POINTER & ((1 << (64 - bits)) - 1)
    name = MT_NAMES[mt_mode]
    rd, rs1 = test_data.int_regs.get_registers(2)
    lines = [
        comment_banner(
            f"cp_gentag_mt_enabled, cp_addtag_mt_enabled ({mode}, {name})",
            f"In {mode}-mode with {bits}-bit tags and only tag {tag} permitted: gentag, and addtag with and without\n"
            f"a wrapping tag.  {_expected(mt_mode)}",
        ),
        f"LI(x{rd}, {RD_CANARY:#x})",
        test_data.add_testcase(f"{mode}_{name}_gentag", "cp_gentag_mt_enabled", cg),
        f"gentag x{rd}",
        write_sigupd(rd, test_data),
    ]
    # The largest tag plus 1 wraps to 0, 3 plus 5 does not wrap
    for start, imm in (((1 << bits) - 1, 1), (3, 5)):
        lines += [
            f"LI(x{rs1}, {_tag_field(start, mt_mode) | low_bits:#x})",
            f"LI(x{rd}, {RD_CANARY:#x})",
            test_data.add_testcase(f"{mode}_{name}_addtag_{start}_{imm}", "cp_addtag_mt_enabled", cg),
            f"addtag x{rd}, x{rs1}, {imm}",
            write_sigupd(rd, test_data),
        ]
    test_data.int_regs.return_registers([rd, rs1])
    return lines


def _m_mt_tests(test_data: TestData, cg: str) -> list[str]:
    """M-mode tests with mseccfg.MT_MODE enabling 4-bit tags, and then 7-bit tags if the config supports them."""
    _check_sig_reg(test_data)
    val, tmp = test_data.int_regs.get_registers(2)
    lines = []
    for mt_mode in (MT_TAG4, MT_TAG7):
        mode_lines = [
            comment_banner(f"M-mode with {TAG_BITS[mt_mode]}-bit tags", f"mseccfg.MT_MODE = {mt_mode:02b}"),
            *_write_field("mseccfg", MT_MODE_LSB, mt_mode, val, tmp),
        ]
        test_data.int_regs.return_registers([val, tmp])
        mode_lines += _gentag_tag_tests(test_data, cg, mt_mode)
        if mt_mode == MT_TAG7:
            mode_lines += _gentag_high_tag_tests(test_data, cg)
        mode_lines += _gentag_several_tag_tests(test_data, cg, mt_mode)
        val, tmp = test_data.int_regs.get_registers(2)
        # The mask permits only tag 9: gentag writes tag 9, and addtag is not affected by it
        mode_lines += _write_mask("m", *_only(9), val)
        test_data.int_regs.return_registers([val, tmp])
        mode_lines += [
            *_gentag_tests(test_data, cg, "M", mt_mode),
            *_addtag_tests(test_data, cg, "M", mt_mode),
            *_non_zimt_mop_tests(test_data, cg, "M", mt_mode),
        ]
        lines += _tag7(mode_lines) if mt_mode == MT_TAG7 else mode_lines
        val, tmp = test_data.int_regs.get_registers(2)
    lines += [
        comment_banner("Restore", "mseccfg.MT_MODE = 00 and mmtagexclude = 0"),
        *_write_field("mseccfg", MT_MODE_LSB, MT_DISABLED, val, tmp),
        *_write_mask("m", 0, 0, val),
    ]
    test_data.int_regs.return_registers([val, tmp])
    return lines


# Tag permitted by the exclusion mask of each environment in the _mt tests of the other modes: a mode using the
# wrong mask, or the wrong MT_MODE field, generates another value
ENV_TAG = {"m": 1, "menv": 2, "senv": 3, "henv": 4}


def _configure(fields: list[tuple[str, int]], masks: list[str], val: int, tmp: int) -> list[str]:
    """Set MT_MODE fields (csr, value), and let each listed environment's exclusion mask permit only its ENV_TAG."""
    lines = [line for csr, value in fields for line in _write_field(csr, MT_MODE_LSB, value, val, tmp)]
    for env in masks:
        lines += _write_mask(env, *_only(ENV_TAG[env]), val)
    return lines


def _restore(fields: list[str], masks: list[str], val: int, tmp: int) -> list[str]:
    """Clear MT_MODE fields and exclusion masks."""
    lines = [line for csr in fields for line in _write_field(csr, MT_MODE_LSB, MT_DISABLED, val, tmp)]
    for env in masks:
        lines += _write_mask(env, 0, 0, val)
    return lines


# ---------------------------------------------------------------------------------------------------------------
# settag
# ---------------------------------------------------------------------------------------------------------------

# Tag table of the settag tests: three 4 KiB pages of the test data. Each chunk that uses it adds it to the data
# section, which keeps one copy per file. Only a Svpbmt NC mapping accesses the third page, so that no cacheable access
# aliases it.
TAG_TABLE = "zimt_tag_table"
# The settag tests store the tags of chunks from SETTAG_CHUNK0: with 8-bit memory tags (7-bit pointer tags) the tag of
# chunk c is the byte at VITT + c, with 4-bit tags the upper (c odd) or lower half of the byte at VITT + c / 2
SETTAG_CHUNK0 = 0x100
# The pointer tags that settag stores: 0xa in bits 63:60, and 0x5a in bits 63:57, whose memory tag is the byte 0x5a
SETTAG_TAG = {MT_TAG4: 0xA, MT_TAG7: 0x5A}
# Tag table content around the tags before each settag: byte l of each doubleword is 0xf0 | l, whose halves differ
# from the 4-bit tag and which differs from the 8-bit memory tag
TAG_PATTERN = 0xF7F6F5F4F3F2F1F0
# First chunks of the M-mode sweep, from SETTAG_CHUNK0: with 4-bit tags 16 put the first tag in each half of a byte at
# each offset in a doubleword, with 7-bit tags 8 put it at each offset
SETTAG_FIRST_CHUNKS = {MT_TAG4: 16, MT_TAG7: 8}
PMM_LSB = 32  # PMM: bits 33:32 of mseccfg, menvcfg, senvcfg and henvcfg
# Virtual address of the tag table pages in the S-mode settag tests with Sv39: a 4 KiB page that maps the first page
# of the tag table, and one after it that maps a page each case chooses. It is outside the gigapage of the test image,
# which the boot page tables map.
SETTAG_VA = 0x1_4080_0000
# A tag table base whose tags are at non-canonical Sv39 addresses (bit 46 set), which ignoring bits 63:39 would map to
# the first tag table page
SETTAG_VA_NONCANONICAL = SETTAG_VA | (1 << 46)
# Store/AMO access faults come from RVMODEL_ACCESS_FAULT_ADDRESS_STORE, which defaults to RVMODEL_ACCESS_FAULT_ADDRESS:
# the cases that need it exist only if the DUT defines it. Their tags start FAULT_BYTE bytes into its faulting region,
# which is at least 128 bytes, so xtval holds an address that is not doubleword aligned.
STORE_FAULT = "RVMODEL_ACCESS_FAULT_ADDRESS_STORE"
FAULT_BYTE = 3
FAULT_TAG = f"({STORE_FAULT} + {FAULT_BYTE})"
# A page-table walk that reads a page table in the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD raises an
# access fault
LOAD_FAULT = "RVMODEL_ACCESS_FAULT_ADDRESS_LOAD"
SVPBMT_GATE = "defined(SVPBMT_SUPPORTED)"
# Pointers whose address bit 63 - PMLEN is set, bit 56 for PMLEN 7 and bit 47 for PMLEN 16: pointer masking sign-extends
# it with address translation and zero-extends it without, so the chunk index has high bits set, and a tag table base
# wraps the tag address around to the tag table. These are the masked addresses of chunk 0, whose tag offset from the
# tag table base is a multiple of 4 KiB with both tag widths. The zero-extended one depends on PMLEN.
SIGN_EXTENDED_BASE = 0xFFFF_FFFF_FFFE_0000
ZERO_EXTENDED_BASE = {7: 0x01FF_FFFF_FFFE_0000, 16: 0x0000_FFFF_FFFE_0000}
# The Sm test checks MPRV only if S-mode can be the effective privilege, with its pointer masking and tag table, and
# with MPV = 1 only if VS-mode and VU-mode can, with theirs
SM_MPRV_GATE = "defined(S_SUPPORTED) && defined(SMNPM_SUPPORTED) && defined(SVATAG_SUPPORTED)"
SM_MPRV_V_GATE = "defined(H_SUPPORTED) && defined(SSNPM_SUPPORTED) && defined(SVATAG_SUPPORTED)"


def _tag_table_data() -> list[str]:
    """The tag table pages, once per file."""
    return [f".ifndef {TAG_TABLE}", ".p2align 12", f"{TAG_TABLE}:", ".skip 12288", ".endif"]


def _tag_offset(chunk: int, mt_mode: int) -> int:
    """Offset from the tag table base of the byte holding the tag of chunk."""
    return chunk if mt_mode == MT_TAG7 else chunk >> 1


def _settag_window(first_chunk: int, last_chunk: int, mt_mode: int) -> list[int]:
    """Offsets of the doublewords with the tags of chunks first_chunk to last_chunk, and of one more on each side."""
    first, last = _tag_offset(first_chunk, mt_mode), _tag_offset(last_chunk, mt_mode)
    return list(range((first & ~7) - 8, (last & ~7) + 16, 8))


def _settag_pointer(chunk: int, mt_mode: int) -> int:
    """A pointer to chunk with the settag tag, and nonzero bits 3:0, which settag ignores."""
    return _tag_field(SETTAG_TAG[mt_mode], mt_mode) | (chunk << 4) | 0x9


def _extended_pointer(base: int, chunk: int, mt_mode: int) -> int:
    """A pointer with the settag tag whose masked address is base + 16 * chunk: its bits 56:0, which hold bit
    63 - PMLEN of that address for PMLEN 7 and 16."""
    return _tag_field(SETTAG_TAG[mt_mode], mt_mode) | ((base + (chunk << 4)) & ((1 << 57) - 1)) | 0x9


def _extended_vitt(table: int, base: int, mt_mode: int) -> int:
    """The tag table base that puts the tag of the chunk at masked address base at address table."""
    return (table - _tag_offset(base >> 4, mt_mode)) & MASK64


def _with_tags(offset: int, first_chunk: int, last_chunk: int, mt_mode: int, end: int) -> int:
    """TAG_PATTERN in the doubleword at offset of the tag table, with the settag tag in the tags of chunks first_chunk
    to last_chunk that are in it and below offset end."""
    value = TAG_PATTERN
    for chunk in range(first_chunk, last_chunk + 1):
        byte = _tag_offset(chunk, mt_mode)
        if byte & ~7 != offset or byte >= end:
            continue
        # The 8-bit memory tag of a 7-bit pointer tag is its zero-extension
        shift, mask = (8 * (byte & 7), 0xFF) if mt_mode == MT_TAG7 else (8 * (byte & 7) + 4 * (chunk & 1), 0xF)
        value = (value & ~(mask << shift)) | (SETTAG_TAG[mt_mode] << shift)
    return value


def _fill_tags(base: int, pattern: int, window: list[int], base_offset: int = 0) -> list[str]:
    """Write the pattern to the doublewords of window; x{base} holds the tag table base plus base_offset."""
    return [f"sd x{pattern}, {offset - base_offset}(x{base})" for offset in window]


def _record_tags(test_data: TestData, base: int, val: int, window: list[int], base_offset: int = 0) -> list[str]:
    """Record the doublewords of window; x{base} holds the tag table base plus base_offset."""
    return [
        line
        for offset in window
        for line in (f"ld x{val}, {offset - base_offset}(x{base})", write_sigupd(val, test_data))
    ]


def _set_pmm(reg: int, ext: str) -> list[str]:
    """x{reg} = the PMM field, in place, of the smallest pointer masking length of ext that masks the pointer tags:
    PMLEN 7 if ext supports it, otherwise 16."""
    return [
        f"#ifdef UDB_SUPPORTED_PMLEN_{ext}_7",
        f"LI(x{reg}, {0b10 << PMM_LSB:#x})    # PMLEN = 7",
        "#else",
        f"LI(x{reg}, {0b11 << PMM_LSB:#x})    # PMLEN = 16",
        "#endif",
    ]


def _settag_sweep_tests(test_data: TestData, cg: str, mode: str, mt_mode: int) -> list[str]:
    """settag of each chunk count from each first chunk, with memory tagging enabled in M-mode (mseccfg.MT_MODE).

    Before each settag the tag table holds the pattern around the tags; after it, record that part.
    """
    name = MT_NAMES[mt_mode]
    coverpoint = f"cp_settag_mt_{name}_chunks"
    firsts = SETTAG_FIRST_CHUNKS[mt_mode]
    window = _settag_window(SETTAG_CHUNK0, SETTAG_CHUNK0 + firsts - 1 + 15, mt_mode)
    base, pattern, ptr, mt, val = test_data.int_regs.get_registers(5)
    lines = [
        comment_banner(
            f"{coverpoint} ({mode})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, settag of 1-16 chunks from each of the chunks\n"
            f"{SETTAG_CHUNK0:#x} to {SETTAG_CHUNK0 + firsts - 1:#x}, and record the tag table around the tags: the\n"
            f"tags of the chunks, and the pattern {TAG_PATTERN:#x} in the other bytes"
            + (" and halves of bytes" if mt_mode == MT_TAG4 else ""),
        ),
        f"LA(x{base}, {TAG_TABLE})",
        f"LI(x{pattern}, {TAG_PATTERN:#x})",
        f"LI(x{mt}, {mt_mode << MT_MODE_LSB:#x})",
    ]
    for first in range(firsts):
        for count in range(16):
            lines += [
                *_fill_tags(base, pattern, window),
                f"LI(x{ptr}, {_settag_pointer(SETTAG_CHUNK0 + first, mt_mode):#x})",
                f"csrs mseccfg, x{mt}",
                test_data.add_testcase(f"{mode}_{name}_chunk{first}_n{count + 1}", coverpoint, cg),
                f"settag x{ptr}, {count}",
                f"csrc mseccfg, x{mt}",
                *_record_tags(test_data, base, val, window),
            ]
    test_data.int_regs.return_registers([base, pattern, ptr, mt, val])
    return lines


def _settag_rs1_tests(test_data: TestData, cg: str) -> list[str]:
    """settag x<r>, 0 for each r != 0 with 4-bit tags in M-mode: x<r> tags chunk SETTAG_CHUNK0 + r with tag r % 16."""
    coverpoint = "cp_settag_mt_tag4_rs1"
    window = _settag_window(SETTAG_CHUNK0, SETTAG_CHUNK0 + 31, MT_TAG4)
    # base holds the tag table address across the sweep: when rs1 is base, it is saved and restored like any other
    # register, and the MT_MODE bits and the saved register are two of the others
    base, *scratch = test_data.int_regs.get_registers(4)
    val = scratch[0]
    lines = [
        comment_banner(
            f"{coverpoint} (M)",
            f"In M-mode with 4-bit tags, settag x<r>, 0 for each r != 0, with x<r> tagged with r % 16 and pointing\n"
            f"to chunk {SETTAG_CHUNK0:#x} + r. Then record the tag table around the tags",
        ),
        f"LA(x{base}, {TAG_TABLE})",
        f"LI(x{val}, {TAG_PATTERN:#x})",
        *_fill_tags(base, val, window),
    ]
    for rs1 in range(1, 32):
        mt, save = [r for r in scratch if r != rs1][:2]
        lines += [
            f"LI(x{mt}, {MT_TAG4 << MT_MODE_LSB:#x})",
            *_saved(
                rs1,
                save,
                [
                    f"LI(x{rs1}, {_tag_field(rs1 % 16, MT_TAG4) | ((SETTAG_CHUNK0 + rs1) << 4):#x})",
                    f"csrs mseccfg, x{mt}",
                    test_data.add_testcase(f"M_rs1_x{rs1}", coverpoint, cg),
                    f"settag x{rs1}, 0",
                    f"csrc mseccfg, x{mt}",
                ],
            ),
        ]
    lines += _record_tags(test_data, base, val, window)
    test_data.int_regs.return_registers([base, *scratch])
    return lines


def _sm_zero_extended_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """settag of 16 chunks in M-mode through a pointer whose address bit 63 - PMLEN is set, which pointer masking
    zero-extends without address translation: mvitt wraps the tag addresses around to the tag table."""
    name = MT_NAMES[mt_mode]
    first, count = SETTAG_CHUNK0 + 3, 15
    window = _settag_window(first, first + count, mt_mode)
    base, val, ptr, mt = test_data.int_regs.get_registers(4)
    lines = [
        comment_banner(
            f"cp_settag_addr_msb (M, {name})",
            f"In M-mode with {TAG_BITS[mt_mode]}-bit tags, settag of 16 chunks from chunk {first:#x} through a pointer\n"
            "with bit 56 (PMLEN 7) or bit 47 (PMLEN 16) set, which pointer masking zero-extends: mvitt is the tag\n"
            "table minus the tag offset of that bit, so the tags land in the tag table. Record it around the tags",
        ),
        f"LA(x{base}, {TAG_TABLE})",
        f"LI(x{val}, {TAG_PATTERN:#x})",
        *_fill_tags(base, val, window),
        "#ifdef UDB_SUPPORTED_PMLEN_SMMPM_7",
        f"LI(x{ptr}, {_extended_pointer(ZERO_EXTENDED_BASE[7], first, mt_mode):#x})",
        f"LI(x{val}, {_tag_offset(ZERO_EXTENDED_BASE[7] >> 4, mt_mode):#x})",
        "#else",
        f"LI(x{ptr}, {_extended_pointer(ZERO_EXTENDED_BASE[16], first, mt_mode):#x})",
        f"LI(x{val}, {_tag_offset(ZERO_EXTENDED_BASE[16] >> 4, mt_mode):#x})",
        "#endif",
        f"sub x{val}, x{base}, x{val}",
        f"csrw CSR_MVITT, x{val}",
        f"LI(x{mt}, {mt_mode << MT_MODE_LSB:#x})",
        f"csrs mseccfg, x{mt}",
        test_data.add_testcase(f"M_{name}_zero_extended", "cp_settag_addr_msb", cg),
        f"settag x{ptr}, {count}",
        f"csrc mseccfg, x{mt}",
        f"csrw CSR_MVITT, x{base}",
        *_record_tags(test_data, base, val, window),
    ]
    test_data.int_regs.return_registers([base, val, ptr, mt])
    return lines


def _sm_mprv_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """settag in M-mode with mstatus.MPRV = 1 and MPP = S: the tag table and MT_MODE of M-mode, the pointer masking
    and address translation of S-mode."""
    name = MT_NAMES[mt_mode]
    first, count = SETTAG_CHUNK0 + 5, 9
    window = _settag_window(first, first + count, mt_mode)
    base, decoy, ptr, mt, tmp = test_data.int_regs.get_registers(5)
    lines = [
        comment_banner(
            f"cp_settag_mprv (M, {name})",
            f"In M-mode with {TAG_BITS[mt_mode]}-bit tags and mstatus.MPRV = 1, MPP = S, settag of 10 chunks from chunk\n"
            f"{first:#x}. It uses the tag table and MT_MODE of M-mode, mvitt = the first tag table page and\n"
            "mseccfg.MT_MODE, and the pointer masking and address translation of S-mode: menvcfg.PMM masks the pointer\n"
            "tag while mseccfg.PMM = 00, and satp is Bare. svitts = the second page and menvcfg.MT_MODE = 00, which\n"
            "settag must not use. Record both pages around the tags",
        ),
        f"LA(x{base}, {TAG_TABLE})",
        f"LI(x{tmp}, 0x1000)",
        f"add x{decoy}, x{base}, x{tmp}",
        f"csrw CSR_SVITTS, x{decoy}",
        f"LI(x{tmp}, {TAG_PATTERN:#x})",
        *_fill_tags(base, tmp, window),
        *_fill_tags(decoy, tmp, window),
        *_write_field("mseccfg", PMM_LSB, 0, ptr, tmp),
        *_set_pmm(tmp, "SMNPM"),
        f"csrs menvcfg, x{tmp}",
        f"LI(x{ptr}, {_settag_pointer(first, mt_mode):#x})",
        f"LI(x{mt}, {mt_mode << MT_MODE_LSB:#x})",
        f"LI(x{tmp}, MSTATUS_MPP)",
        f"csrc mstatus, x{tmp}",
        f"LI(x{tmp}, MSTATUS_MPRV | {1 << 11:#x})    # MPP = S",
        f"csrs mstatus, x{tmp}",
        f"csrs mseccfg, x{mt}",
        test_data.add_testcase(f"M_{name}_mprv", "cp_settag_mprv", cg),
        f"settag x{ptr}, {count}",
        f"csrc mseccfg, x{mt}",
        f"csrc mstatus, x{tmp}",
        f"LI(x{tmp}, {0b11 << PMM_LSB:#x})",
        f"csrc menvcfg, x{tmp}",
        *_set_pmm(tmp, "SMMPM"),
        f"csrs mseccfg, x{tmp}",
        "csrw CSR_SVITTS, x0",
        *_record_tags(test_data, base, tmp, window),
        *_record_tags(test_data, decoy, tmp, window),
    ]
    test_data.int_regs.return_registers([base, decoy, ptr, mt, tmp])
    return lines


class _CrossCase(NamedTuple):
    """A case of the S-mode settag tests whose tags cross into the second tag table page."""

    name: str
    flags: PteExpression  # leaf flags of the second page
    physical: str  # its physical address, a label expression
    gate: str | None = None
    faults: bool = False  # whether settag may fault at the first tag byte of the second page
    through_va: bool = False  # fill and record the tags at SETTAG_VA instead of the identity mapping


# Cases of the S-mode settag tests, which cross from the first tag table page (VA SETTAG_VA, mapped to the tag table)
# into the second one, mapped by the case's leaf PTE. A fault is at the first tag byte of the second page. Whether the
# tags before it, in the first page, are stored is implementation-defined: settag may split its tag store into parts,
# with no ordering among them. Before a settag that may fault, those tags already hold its tag.
S_SETTAG_CROSS_CASES = (
    _CrossCase("cross_valid", PteFlags(execute=False), f"{TAG_TABLE} + 0x1000"),
    _CrossCase("cross_invalid", "0", f"{TAG_TABLE} + 0x1000", faults=True),
    _CrossCase("cross_readonly", PteFlags(write=False, execute=False), f"{TAG_TABLE} + 0x1000", faults=True),
    # D = 0: a store/AMO page fault with Svade; with Svadu the hart sets D
    _CrossCase("cross_clean", PteFlags(execute=False, dirty=False), f"{TAG_TABLE} + 0x1000", faults=True),
    # Svpbmt IO memory is not idempotent: store/AMO access fault
    _CrossCase(
        "cross_io", PteFlags(execute=False, extra=("(2 << 61)",)), f"{TAG_TABLE} + 0x1000", SVPBMT_GATE, faults=True
    ),
    # Svpbmt NC memory is idempotent: the tags are stored. It maps the third page, which no cacheable access aliases.
    _CrossCase(
        "cross_nc", PteFlags(execute=False, extra=("(1 << 61)",)), f"{TAG_TABLE} + 0x2000", SVPBMT_GATE, through_va=True
    ),
)
# Chunks of the crossing settags: the first one and the chunk count - 1. With 4-bit tags, the first and last tag
# bytes, at offsets 0xffe and 0x1000, keep their other half, so they are read too.
S_SETTAG_CROSS = {MT_TAG4: (0x1FFD, 3), MT_TAG7: (0xFFC, 7)}


def _s_settag_case(
    test_data: TestData,
    cg: str,
    mt_mode: int,
    name: str,
    pointer: str,
    count: int,
    regs: tuple[int, int, int],
    stored: tuple[int, int] | None = None,
    through_va: bool = False,
    coverpoint: str = "cp_settag_mt_enabled",
) -> list[str]:
    """One settag of the S-mode tests: fill the doublewords around the page boundary, settag, record them.

    The fill is the pattern, with the settag tag in the tags of the chunks stored = (first, last) in the first page.
    The doublewords are accessed through the identity mapping of the tag table or, with through_va, at SETTAG_VA.
    """
    a, b, c = regs
    window = [0xFF0, 0xFF8, 0x1000, 0x1008]
    fill = [TAG_PATTERN if stored is None else _with_tags(offset, *stored, mt_mode, 0x1000) for offset in window]
    return [
        f"LI(x{b}, {SETTAG_VA + 0x1000:#x})" if through_va else f"LA(x{b}, {TAG_TABLE} + 0x1000)",
        *[
            line
            for offset, value in zip(window, fill, strict=True)
            for line in (f"LI(x{c}, {value:#x})", f"sd x{c}, {offset - 0x1000}(x{b})")
        ],
        load_constant(f"x{a}", pointer),
        test_data.add_testcase(f"S_{MT_NAMES[mt_mode]}_{name}", coverpoint, cg),
        f"settag x{a}, {count}",
        *_record_tags(test_data, b, c, window, 0x1000),
    ]


def _s_settag_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """settag in S-mode with Sv39 translation and memory tagging enabled with mt_mode (menvcfg.MT_MODE).

    The tags of a settag cross from the first tag table page into the second one, which is valid, invalid, read-only,
    clean (D = 0), Svpbmt IO memory or Svpbmt NC memory. Then the settag of the valid case through a pointer whose
    masked address is sign-extended; one that starts in the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_STORE; one
    whose page-table walk reads a table in the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD; and one with the
    tag table base at a non-canonical address. The S-mode trap handler records the store/AMO page faults and access
    faults: S-mode accesses with translation are not tag checked, so the handler runs with memory tagging enabled.
    """
    name = MT_NAMES[mt_mode]
    a, b, c = test_data.int_regs.get_registers(3)
    regs = (a, b, c)
    first, count = S_SETTAG_CROSS[mt_mode]
    first_chunks = (first, first + count)

    def second_page(flags: PteExpression, physical: str, *, is_label: bool = True) -> list[str]:
        """Map the second tag table page, the 4 KiB page after SETTAG_VA."""
        return [
            *write_pte(
                SV39,
                level=0,
                flags=flags,
                virtual_address=hex(SETTAG_VA + 0x1000),
                physical_address=physical,
                regs=regs,
                pa_is_label=is_label,
            ),
            "sfence.vma",
        ]

    def svitts(value: str) -> list[str]:
        return [load_constant(f"x{a}", value), f"csrw CSR_SVITTS, x{a}"]

    lines = [
        comment_banner(
            f"cp_settag_mt_enabled, cp_settag_addr_msb (S, {name})",
            f"In S-mode with Sv39 and {TAG_BITS[mt_mode]}-bit tags, settags whose tags cross into a second tag table\n"
            "page that is valid, invalid, read-only, clean, IO or NC memory: a store/AMO page fault or access fault at\n"
            "its first tag byte, or none. Before a settag that may fault, its tags in the first page hold its tag\n"
            "already, as the hart may or may not store them. Then the valid case through a pointer with bit 56 or 47\n"
            "set, which pointer masking sign-extends, a settag in the faulting region of the store access faults, one\n"
            "whose page-table walk faults, and one at a non-canonical address. Record the doublewords around the page\n"
            "boundary",
        ),
        *_set_pmm(a, "SMNPM"),
        f"LI(x{b}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{a}, x{a}, x{b}",
        *gated([f"LI(x{b}, MENVCFG_PBMTE)", f"or x{a}, x{a}, x{b}"], SVPBMT_GATE),
        tsbi_call(f"csrs menvcfg, x{a}"),
    ]
    pointer = hex(_settag_pointer(first, mt_mode))
    for case in S_SETTAG_CROSS_CASES:
        lines += gated(
            [
                *second_page(case.flags, case.physical),
                *_s_settag_case(
                    test_data,
                    cg,
                    mt_mode,
                    case.name,
                    pointer,
                    count,
                    regs,
                    first_chunks if case.faults else None,
                    case.through_va,
                ),
            ],
            case.gate,
        )
    # cross_valid through a pointer whose masked address is sign-extended: svitts wraps its tag addresses around to the
    # same tag bytes
    lines += [
        *second_page(PteFlags(execute=False), f"{TAG_TABLE} + 0x1000"),
        *svitts(hex(_extended_vitt(SETTAG_VA, SIGN_EXTENDED_BASE, mt_mode))),
        *_s_settag_case(
            test_data,
            cg,
            mt_mode,
            "sign_extended",
            hex(_extended_pointer(SIGN_EXTENDED_BASE, first, mt_mode)),
            count,
            regs,
            coverpoint="cp_settag_addr_msb",
        ),
        *svitts(hex(SETTAG_VA)),
    ]
    # Tags FAULT_BYTE bytes into the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_STORE, in the second page: store/AMO
    # access fault. With 4-bit tags, the first one is an upper half.
    fault_offset = f"(0x1000 + ({FAULT_TAG} & 0xfff))"
    fault_chunk = fault_offset if mt_mode == MT_TAG7 else f"(2 * {fault_offset} + 1)"
    lines += gated(
        [
            *second_page(PteFlags(execute=False), FAULT_TAG, is_label=False),
            *_s_settag_case(
                test_data,
                cg,
                mt_mode,
                "access_fault",
                f"{_tag_field(SETTAG_TAG[mt_mode], mt_mode):#x} | ({fault_chunk} << 4)",
                1,
                regs,
            ),
        ],
        f"defined({STORE_FAULT})",
    )
    # A tag table base in the 2 MiB after SETTAG_VA, whose level-0 page table is in the faulting region of
    # RVMODEL_ACCESS_FAULT_ADDRESS_LOAD: the page-table walk raises a store/AMO access fault
    walk_region = hex(SETTAG_VA + 0x20_0000)
    lines += gated(
        [
            *write_pte(
                SV39,
                level=1,
                flags=PteFlags.nonleaf(),
                virtual_address=walk_region,
                physical_address=SV39.access_fault_pte_address(LOAD_FAULT),
                regs=regs,
                pa_is_label=False,
            ),
            "sfence.vma",
            *svitts(f"({SV39.access_fault_walk_va(walk_region, 0, LOAD_FAULT)}) & ~0xfff"),
            *_s_settag_case(
                test_data,
                cg,
                mt_mode,
                "walk_access_fault",
                hex(_settag_pointer(SETTAG_CHUNK0 + 5, mt_mode)),
                1,
                regs,
            ),
            *svitts(hex(SETTAG_VA)),
        ],
        f"defined({LOAD_FAULT})",
    )
    lines += [
        # The tags of chunk SETTAG_CHUNK0 + 5, at a non-canonical address: store/AMO page fault
        *svitts(hex(SETTAG_VA_NONCANONICAL)),
        *_s_settag_case(
            test_data, cg, mt_mode, "noncanonical", hex(_settag_pointer(SETTAG_CHUNK0 + 5, mt_mode)), 1, regs
        ),
        *svitts(hex(SETTAG_VA)),
        f"LI(x{a}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        *gated([f"LI(x{b}, MENVCFG_PBMTE)", f"or x{a}, x{a}, x{b}"], SVPBMT_GATE),
        tsbi_call(f"csrc menvcfg, x{a}"),
    ]
    test_data.int_regs.return_registers(list(regs))
    return lines


# Cases of the settag tests in U, VS and VU modes, which check the tag table the mode uses: (first chunk - SETTAG_CHUNK0,
# chunk count - 1)
VITT_SETTAG_CASES = ((0, 0), (1, 15), (6, 5))


def _vitt_settag_tests(test_data: TestData, cg: str, mode: str, mt_mode: int, coverpoint: str) -> list[str]:
    """The settags of VITT_SETTAG_CASES in mode, which uses the tag table that the caller set."""
    ptr = test_data.int_regs.get_register()
    lines = []
    for first, count in VITT_SETTAG_CASES:
        lines += [
            f"LI(x{ptr}, {_settag_pointer(SETTAG_CHUNK0 + first, mt_mode):#x})",
            test_data.add_testcase(f"{mode}_{MT_NAMES[mt_mode]}_chunk{first}_n{count + 1}", coverpoint, cg),
            f"settag x{ptr}, {count}",
        ]
    test_data.int_regs.return_register(ptr)
    return lines


def _vitt_settag_window(mt_mode: int) -> list[int]:
    """Doublewords around the tags of VITT_SETTAG_CASES."""
    return _settag_window(SETTAG_CHUNK0, SETTAG_CHUNK0 + max(f + n for f, n in VITT_SETTAG_CASES), mt_mode)


# VS-mode settags with guest translation. With two-stage translation, the VS stage maps the tag page VS_SV39.data_va to
# the guest physical address SV39X4.data_va, which the G stage maps to the second tag table page: (name, VS-stage leaf
# flags, G-stage leaf flags). With the G stage only, the tag page is SV39X4.data_va: (name, G-stage leaf flags). A VS-stage
# fault is a store/AMO page fault; a G-stage fault a store/AMO guest-page fault, with htval = the guest physical
# address >> 2 and hstatus.GVA = 1.
H_TWO_STAGE_CASES = (
    ("two_stage", PteFlags(execute=False), PteFlags(user=True, execute=False)),
    ("two_stage_vs_readonly", PteFlags(write=False, execute=False), PteFlags(user=True, execute=False)),
    ("two_stage_g_readonly", PteFlags(execute=False), PteFlags(user=True, write=False, execute=False)),
    ("two_stage_g_invalid", PteFlags(execute=False), "0"),
)
H_G_STAGE_CASES = (
    ("g_stage", PteFlags(user=True, execute=False)),
    ("g_stage_readonly", PteFlags(user=True, write=False, execute=False)),
)
# A tag table base above the 41-bit guest physical addresses of Sv39x4: store/AMO guest-page fault
H_GPA_TOO_WIDE = 1 << 41


def _h_guest_settag_case(
    test_data: TestData, cg: str, mt_mode: int, name: str, coverpoint: str, vitt: int, setup: list[str]
) -> list[str]:
    """In HS-mode, run setup and fill the second tag table page around the tags; in VS-mode with vsvitts = vitt, settag
    of 2 chunks; in HS-mode, record the second page around the tags."""
    first = SETTAG_CHUNK0 + 5
    window = _settag_window(first, first + 1, mt_mode)
    base, val, ptr = test_data.int_regs.get_registers(3)
    lines = [
        *setup,
        f"LA(x{base}, {TAG_TABLE} + 0x1000)",
        f"LI(x{val}, {TAG_PATTERN:#x})",
        *_fill_tags(base, val, window),
        f"LI(x{val}, {vitt:#x})",
        f"csrw CSR_VSVITTS, x{val}",
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{ptr}, {_settag_pointer(first, mt_mode):#x})",
        test_data.add_testcase(f"VS_{MT_NAMES[mt_mode]}_{name}", coverpoint, cg),
        f"settag x{ptr}, 1",
        "RVTEST_TSBI_GOTO_SMODE",
        f"LA(x{base}, {TAG_TABLE} + 0x1000)",
        *_record_tags(test_data, base, val, window),
    ]
    test_data.int_regs.return_registers([base, val, ptr])
    return lines


def _h_guest_settag_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """settag in VS-mode with two-stage translation (vsatp = Sv39, hgatp = Sv39x4) and with the G stage only."""
    name = MT_NAMES[mt_mode]
    pte, addr, tmp = test_data.int_regs.get_registers(3)
    regs = (pte, addr, tmp)
    lines = [
        comment_banner(
            f"cp_settag_two_stage, cp_settag_g_stage (VS, {name})",
            f"In VS-mode with {TAG_BITS[mt_mode]}-bit tags, settags with two-stage translation whose tag page is valid,\n"
            "read-only in the VS stage (store/AMO page fault), or read-only or invalid in the G stage (store/AMO\n"
            "guest-page fault, htval = the guest physical address >> 2, GVA = 1), and with the G stage only whose tag\n"
            "page is valid or read-only, or whose tag table base is above the guest physical addresses of Sv39x4.\n"
            "HS-mode takes the traps and records the second tag table page around the tags",
        ),
        *_set_pmm(pte, "SSNPM"),
        f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{pte}, x{pte}, x{tmp}",
        f"csrs henvcfg, x{pte}",
        *guest_translation_setup(test_data, SV39X4, VS_SV39, "VSmode"),
    ]
    for case, vs_flags, g_flags in H_TWO_STAGE_CASES:
        setup = [
            *create_page_mapping(
                VS_SV39,
                leaf_level=0,
                leaf_flags=vs_flags,
                virtual_address=VS_SV39.data_va,
                physical_address=SV39X4.data_va,
                regs=regs,
                pa_is_label=False,
            ),
            *create_page_mapping(
                SV39X4,
                leaf_level=0,
                leaf_flags=g_flags,
                virtual_address=SV39X4.data_va,
                physical_address=f"{TAG_TABLE} + 0x1000",
                regs=regs,
            ),
            "hfence.vvma",
            "hfence.gvma",
        ]
        lines += _h_guest_settag_case(
            test_data, cg, mt_mode, case, "cp_settag_two_stage", int(VS_SV39.data_va, 16), setup
        )
    lines += [*guest_translation_teardown(test_data), *guest_translation_setup(test_data, SV39X4, None, "VSmode")]
    for case, g_flags in H_G_STAGE_CASES:
        setup = [
            *create_page_mapping(
                SV39X4,
                leaf_level=0,
                leaf_flags=g_flags,
                virtual_address=SV39X4.data_va,
                physical_address=f"{TAG_TABLE} + 0x1000",
                regs=regs,
            ),
            "hfence.gvma",
        ]
        lines += _h_guest_settag_case(test_data, cg, mt_mode, case, "cp_settag_g_stage", int(SV39X4.data_va, 16), setup)
    lines += _h_guest_settag_case(
        test_data, cg, mt_mode, "g_stage_gpa_too_wide", "cp_settag_g_stage", H_GPA_TOO_WIDE, []
    )
    lines += [
        *guest_translation_teardown(test_data),
        f"LI(x{pte}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        f"csrc henvcfg, x{pte}",
        "csrw CSR_VSVITTS, x0",
    ]
    test_data.int_regs.return_registers(list(regs))
    return lines


# ---------------------------------------------------------------------------------------------------------------
# checktag and implicit tag checks
# ---------------------------------------------------------------------------------------------------------------

# Data of the implicit tag check tests: a 4 KiB page whose first CHECK_CHUNKS chunks hold pattern bytes, byte i being
# (37 * i + 11) & 0xff. _check_vitt sets a tag table base that puts the tags of its chunks in the first tag table page.
CHECK_DATA = "zimt_check_data"
CHECK_CHUNKS = 64
# The memory tag of the data chunks (that of the settag tests), and a mismatching tag, which differs from it only in the
# top bit of the pointer tag
GOOD_TAG = SETTAG_TAG
BAD_TAG = {MT_TAG4: 0x2, MT_TAG7: 0x1A}
# Data chunks whose memory tag is BAD_TAG in the tests of the modes whose tag checks may raise exceptions
BAD_CHUNKS = (20, 23)
# Tag loads FAULT_BYTE bytes into the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
LOAD_FAULT_TAG = f"({LOAD_FAULT} + {FAULT_BYTE})"
LOAD_FAULT_GATE = f"defined({LOAD_FAULT})"
STORE_FAULT_GATE = f"defined({STORE_FAULT})"
# Misaligned loads and stores do not trap (the hart performs them)
MISALIGNED_LDST_GATE = "defined(UDB_MISALIGNED_LDST)"
# The data chunk of the accesses that implicit tag checks do not cover, which starts a cache block of 64 bytes
UNCHECKED_CHUNK = 52
# Data chunk of the checktags with sp as rs1, and of the 7-bit tag with bit 7 set
SP_CHECKTAG_CHUNK = 4
# The loads and stores of the tests are assembled only for a config that supports them, and M is for the divisions of
# the ordering tests. Compressed ones enable Zca, Zcb and Zcd around them (.option arch), so that the assembler
# compresses no other instruction, and so do the accesses that implicit tag checks do not cover with their extensions.
CHECK_MARCH = ["Zimop", "M", "F", "D", "Zfhmin"]
# Lines that enable and disable memory tagging around each checked access in a mode that does not keep it enabled
NO_MT: tuple[list[str], list[str]] = ([], [])
SW_CHECK_TEXT = "software-check exception (cause 18, xtval 4)"


class _Access(NamedTuple):
    """A kind of load or store that implicit tag checks cover."""

    mnemonic: str
    width: int
    store: bool
    fp: bool = False
    gate: str | None = None  # config define that the access needs

    @property
    def compressed(self) -> bool:
        return self.mnemonic.startswith("c.")


INT_ACCESSES = (
    _Access("lb", 1, False),
    _Access("lbu", 1, False),
    _Access("lh", 2, False),
    _Access("lhu", 2, False),
    _Access("lw", 4, False),
    _Access("lwu", 4, False),
    _Access("ld", 8, False),
    _Access("sb", 1, True),
    _Access("sh", 2, True),
    _Access("sw", 4, True),
    _Access("sd", 8, True),
    _Access("c.lw", 4, False, gate="ZCA_SUPPORTED"),
    _Access("c.ld", 8, False, gate="ZCA_SUPPORTED"),
    _Access("c.sw", 4, True, gate="ZCA_SUPPORTED"),
    _Access("c.sd", 8, True, gate="ZCA_SUPPORTED"),
    _Access("c.lbu", 1, False, gate="ZCB_SUPPORTED"),
    _Access("c.lh", 2, False, gate="ZCB_SUPPORTED"),
    _Access("c.lhu", 2, False, gate="ZCB_SUPPORTED"),
    _Access("c.sb", 1, True, gate="ZCB_SUPPORTED"),
    _Access("c.sh", 2, True, gate="ZCB_SUPPORTED"),
)
FP_ACCESSES = (
    _Access("flh", 2, False, True, "ZFHMIN_SUPPORTED"),
    _Access("flw", 4, False, True, "F_SUPPORTED"),
    _Access("fld", 8, False, True, "D_SUPPORTED"),
    _Access("fsh", 2, True, True, "ZFHMIN_SUPPORTED"),
    _Access("fsw", 4, True, True, "F_SUPPORTED"),
    _Access("fsd", 8, True, True, "D_SUPPORTED"),
    _Access("c.fld", 8, False, True, "ZCD_SUPPORTED"),
    _Access("c.fsd", 8, True, True, "ZCD_SUPPORTED"),
)
ACCESS = {access.mnemonic: access for access in (*INT_ACCESSES, *FP_ACCESSES)}
# Misaligned accesses over two chunks (access, chunk, offset in it), whose chunks have the matching tag...
TWO_CHUNK_CASES = (
    ("ld", 16, 12),
    ("lw", 16, 14),
    ("lh", 16, 15),
    ("fld", 17, 12),
    ("sd", 40, 12),
    ("sw", 41, 14),
    ("sh", 42, 15),
    ("fsd", 43, 12),
)
# ...and over a chunk of BAD_CHUNKS: 20 is the second chunk of the first ones and the first chunk of the second one
TWO_CHUNK_BAD_CASES = (("ld", 19, 12), ("lw", 20, 14), ("sh", 19, 15), ("sd", 22, 12), ("fsd", 22, 12))
# checktag around BAD_CHUNKS: (first chunk, chunk count - 1, whether the pointer tag is the matching one). No exception,
# or a software-check exception at the last chunk, at the first one or, for the mismatching pointer tag, at chunk 0.
CHECKTAG_CASES = (
    (16, 3, True),
    (17, 3, True),
    (20, 0, True),
    (21, 1, True),
    (21, 2, True),
    (5, 15, True),
    (24, 15, True),
    (0, 0, False),
)


def _check_data() -> list[str]:
    """The data page of the implicit tag check tests, once per file."""
    dwords = [sum(((37 * (8 * d + b) + 11) & 0xFF) << (8 * b) for b in range(8)) for d in range(2 * CHECK_CHUNKS)]
    return [
        f".ifndef {CHECK_DATA}",
        ".p2align 12",
        f"{CHECK_DATA}:",
        *[f".dword {value:#018x}" for value in dwords],
        f".skip {4096 - 16 * CHECK_CHUNKS}",
        ".endif",
    ]


def _check_vitt(
    csr: str,
    mt_mode: int,
    regs: tuple[int, int, int],
    base: str = CHECK_DATA,
    label: bool = True,
    table: str = TAG_TABLE,
) -> list[str]:
    """Set csr, a tag table base CSR, so that the tag of the chunk at base (a label, or a constant expression if not
    label) is in the page at table (the first tag table page by default, or a constant address): csr = table - its tag
    offset rounded down to 4 KiB. x{regs[0]} = the address of that tag."""
    tags, t1, t2 = regs
    return [
        f"LA(x{t1}, {base})" if label else load_constant(f"x{t1}", base),
        f"srli x{t1}, x{t1}, {4 if mt_mode == MT_TAG7 else 5}",
        f"srli x{t2}, x{t1}, 12",
        f"slli x{t2}, x{t2}, 12",
        f"sub x{t1}, x{t1}, x{t2}",
        f"LA(x{tags}, {table})" if table == TAG_TABLE else load_constant(f"x{tags}", table),
        f"sub x{t2}, x{tags}, x{t2}",
        f"csrw {csr}, x{t2}",
        f"add x{tags}, x{tags}, x{t1}",
    ]


def _check_tags(mt_mode: int, tags: int, tmp: int) -> list[str]:
    """x{tags} = the address of the tag of data chunk 0 with the tag table base of _check_vitt."""
    return [
        f"LA(x{tmp}, {CHECK_DATA})",
        f"srli x{tmp}, x{tmp}, {4 if mt_mode == MT_TAG7 else 5}",
        f"slli x{tmp}, x{tmp}, 52",
        f"srli x{tmp}, x{tmp}, 52",
        f"LA(x{tags}, {TAG_TABLE})",
        f"add x{tags}, x{tags}, x{tmp}",
    ]


def _check_tag_bytes(mt_mode: int, bad: tuple[int, ...] = ()) -> list[int]:
    """The tag bytes of the data chunks: GOOD_TAG, and BAD_TAG for the chunks in bad."""
    tag = [BAD_TAG[mt_mode] if chunk in bad else GOOD_TAG[mt_mode] for chunk in range(CHECK_CHUNKS)]
    if mt_mode == MT_TAG7:
        return tag
    return [tag[2 * i] | (tag[2 * i + 1] << 4) for i in range(CHECK_CHUNKS // 2)]


def _check_fill(mt_mode: int, tags: int, tmp: int, bad: tuple[int, ...] = ()) -> list[str]:
    """Write the tag bytes of the data chunks; x{tags} holds the address of the tag of chunk 0."""
    data = _check_tag_bytes(mt_mode, bad)
    lines = []
    for offset in range(0, len(data), 8):
        value = sum(byte << (8 * i) for i, byte in enumerate(data[offset : offset + 8]))
        lines += [f"LI(x{tmp}, {value:#x})", f"sd x{tmp}, {offset}(x{tags})"]
    return lines


def _check_pointer(reg: int, tmp: int, mt_mode: int, chunk: int, tag: int, offset: int = 0) -> list[str]:
    """x{reg} = the address of byte offset of data chunk chunk, with the pointer tag tag."""
    return [
        f"LA(x{reg}, {CHECK_DATA} + {16 * chunk + offset})",
        f"LI(x{tmp}, {_tag_field(tag, mt_mode):#x})",
        f"or x{reg}, x{reg}, x{tmp}",
    ]


def _record_via_sp(test_data: TestData, ptr: int, offset: int, val: int, save: int) -> list[str]:
    """Record the doubleword at x{ptr} + offset through sp, as no tag check covers a load with sp as base register. sp
    holds the address without the pointer tag, which pointer masking ignores, so the load is not a case of
    cp_checked_sp."""
    return [
        f"mv x{save}, sp",
        f"slli sp, x{ptr}, 7",
        "srli sp, sp, 7",
        f"ld x{val}, {offset}(sp)",
        f"mv sp, x{save}",
        write_sigupd(val, test_data),
    ]


def _access_case(
    test_data: TestData,
    cg: str,
    coverpoint: str,
    case: str,
    access: _Access,
    regs: tuple[int, int, int, int],
    offset: int,
    value: int,
    mt: tuple[list[str], list[str]] = NO_MT,
) -> list[str]:
    """access at x{ptr} + offset, between the lines of mt. A load, into data (an x or f register) holding RD_CANARY
    before, records data; a store of value records the doublewords it accesses, through sp. Both record through sp, as
    the tags of the other memory may not match while memory tagging is enabled."""
    ptr, data, tmp, save = regs
    mt_on, mt_off = mt
    initial = value if access.store else RD_CANARY
    if access.fp:
        precision = "d" if access.width == 8 else "w"
        setup = [f"LI(x{tmp}, {initial:#x})", f"fmv.{precision}.x f{data}, x{tmp}"]
    else:
        setup = [f"LI(x{data}, {initial:#x})"]
    instruction = [f"{access.mnemonic} {'f' if access.fp else 'x'}{data}, {offset}(x{ptr})"]
    if access.compressed:
        extensions = "+zca" + (", +zcd" if access.fp else "") + (", +zcb" if access.width < 4 else "")
        instruction = [".option push", f".option arch, {extensions}", *instruction, ".option pop"]
    lines = [*setup, *mt_on, test_data.add_testcase(case, coverpoint, cg), *instruction, *mt_off]
    if not access.store:
        if access.fp:
            return [*lines, f"fmv.x.{'d' if access.width == 8 else 'w'} x{tmp}, f{data}", write_sigupd(tmp, test_data)]
        return [*lines, write_sigupd(data, test_data)]
    for dword in range(offset & ~7, ((offset + access.width - 1) & ~7) + 8, 8):
        lines += _record_via_sp(test_data, ptr, dword, tmp, save)
    return lines


def _access_regs(test_data: TestData, access: _Access) -> tuple[int, int, int, int]:
    """Registers for _access_case: those of a compressed access in x8-x15 and f8-f15."""
    compressed = list(range(8, 16)) if access.compressed else None
    ptr = test_data.int_regs.get_register(reg_range=compressed)
    regs = test_data.float_regs if access.fp else test_data.int_regs
    data = regs.get_register(reg_range=compressed)
    tmp, save = test_data.int_regs.get_registers(2)
    return ptr, data, tmp, save


def _return_access_regs(test_data: TestData, access: _Access, regs: tuple[int, int, int, int]) -> None:
    ptr, data, tmp, save = regs
    test_data.int_regs.return_registers([ptr, tmp, save])
    (test_data.float_regs if access.fp else test_data.int_regs).return_register(data)


def _gated_access(access: _Access, lines: list[str]) -> list[str]:
    return gated(lines, f"defined({access.gate})") if access.gate else lines


def _checked_access_tests(
    test_data: TestData,
    cg: str,
    mode: str,
    mt_mode: int,
    accesses: tuple[_Access, ...],
    mismatch: bool,
    mt: tuple[list[str], list[str]] = NO_MT,
) -> list[str]:
    """Each kind of load and store on data chunk 24 + its index, with the matching pointer tag and, if mismatch, with a
    mismatching one, which raises a software-check exception and leaves rd and memory unchanged."""
    name = MT_NAMES[mt_mode]
    lines = [
        comment_banner(
            f"cp_checked_access ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, each kind of load and store that implicit tag checks\n"
            "cover, with the pointer tag of its data chunk: a load records rd, a store the doubleword"
            + (f". Then with a\nmismatching pointer tag: {SW_CHECK_TEXT}, rd and memory unchanged" if mismatch else ""),
        )
    ]
    for index, access in enumerate(accesses):
        # The last bytes of the chunk, or for a compressed access an offset it encodes: a multiple of its width, up to 3
        # for Zcb bytes and 2 for Zcb halfwords
        offset = {1: 3, 2: 2, 4: 12, 8: 8}[access.width] if access.compressed else 16 - access.width
        value = 0x8877_6655_4433_2211 ^ (index << 4)
        regs = _access_regs(test_data, access)
        cases = [(GOOD_TAG[mt_mode], "match", value)]
        if mismatch:
            cases.append((BAD_TAG[mt_mode], "mismatch", ~value & MASK64))
        case_lines = []
        for tag, result, data_value in cases:
            case_lines += [
                *_check_pointer(regs[0], regs[2], mt_mode, 24 + index, tag),
                *_access_case(
                    test_data,
                    cg,
                    "cp_checked_access",
                    f"{mode}_{name}_{access.mnemonic}_{result}",
                    access,
                    regs,
                    offset,
                    data_value,
                    mt,
                ),
            ]
        _return_access_regs(test_data, access, regs)
        lines += _gated_access(access, case_lines)
    return lines


def _two_chunk_tests(
    test_data: TestData,
    cg: str,
    mode: str,
    mt_mode: int,
    mismatch: bool,
    mt: tuple[list[str], list[str]] = NO_MT,
    fp: bool = True,
) -> list[str]:
    """Misaligned loads and stores over two chunks whose tags match, and, if mismatch, over a chunk of BAD_CHUNKS: a
    software-check exception that leaves rd and memory unchanged, whichever of the two chunks mismatches. fp includes
    floating-point ones. Without hardware misaligned loads and stores (UDB_MISALIGNED_LDST), the ones whose tags match
    raise their address-misaligned or access-fault exception."""
    name = MT_NAMES[mt_mode]
    lines = [
        comment_banner(
            f"cp_checked_two_chunks ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, misaligned loads and stores over two chunks with the\n"
            "matching tags"
            + (
                f", then over chunk {BAD_CHUNKS[0]} or {BAD_CHUNKS[1]}, whose memory tag mismatches as the first or\n"
                f"second chunk: {SW_CHECK_TEXT}, and no part of the access performed"
                if mismatch
                else ""
            ),
        )
    ]
    cases = [*((case, True) for case in TWO_CHUNK_CASES), *((case, False) for case in TWO_CHUNK_BAD_CASES)]
    for (mnemonic, chunk, offset), matches in cases:
        access = ACCESS[mnemonic]
        if (not matches and not mismatch) or (access.fp and not fp):
            continue
        regs = _access_regs(test_data, access)
        case_lines = [
            *_check_pointer(regs[0], regs[2], mt_mode, chunk, GOOD_TAG[mt_mode]),
            *_access_case(
                test_data,
                cg,
                "cp_checked_two_chunks",
                f"{mode}_{name}_{mnemonic}_chunk{chunk}_{offset}",
                access,
                regs,
                offset,
                0x1122_3344_5566_7788 ^ (chunk << 8),
                mt,
            ),
        ]
        _return_access_regs(test_data, access, regs)
        lines += _gated_access(access, case_lines)
    return lines


def _sp_base_tests(
    test_data: TestData,
    cg: str,
    mode: str,
    mt_mode: int,
    mt: tuple[list[str], list[str]] = NO_MT,
    fp: bool = True,
) -> list[str]:
    """Loads and stores with sp as the base register, through a pointer with a mismatching tag: not checked. ld and sd,
    and the compressed sp-relative forms with Zca (and, if fp, with Zcd)."""
    name = MT_NAMES[mt_mode]
    mt_on, mt_off = mt
    ptr, val, val2, tmp, save = test_data.int_regs.get_registers(5)
    fval = test_data.float_regs.get_register()

    def via_sp(
        cases: list[tuple[str, str]], record: Callable[[], list[str]], gate: str | None = None, arch: str = ""
    ) -> list[str]:
        """With sp = x{ptr} and memory tagging enabled: the (testcase, instruction) cases, assembled with arch (the
        compressed ones, cp_checked_sp_compressed); then the lines of record() with sp restored, made after the
        testcases, whose labels their signature updates refer to."""
        coverpoint = "cp_checked_sp_compressed" if arch else "cp_checked_sp"
        instructions = []
        for case, instruction in cases:
            instructions += [test_data.add_testcase(f"{mode}_{name}_{case}", coverpoint, cg), instruction]
        if arch:
            instructions = [".option push", f".option arch, {arch}", *instructions, ".option pop"]
        lines = [
            f"LI(x{val}, {RD_CANARY:#x})",
            f"mv x{save}, sp",
            f"mv sp, x{ptr}",
            *mt_on,
            *instructions,
            *mt_off,
            f"mv sp, x{save}",
            *record(),
        ]
        return gated(lines, gate) if gate else lines

    lines = [
        comment_banner(
            f"cp_checked_sp ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, loads and stores with sp as the base register and a\n"
            "mismatching pointer tag in sp: ld and sd, and the compressed sp-relative ones. No tag check, no\n"
            "exception. Record the loaded and the stored doublewords",
        ),
        *_check_pointer(ptr, tmp, mt_mode, 2, BAD_TAG[mt_mode]),
        f"LI(x{tmp}, 0x0123456789abcdef)",
        *via_sp(
            [("sp_load", f"ld x{val}, 0(sp)"), ("sp_store", f"sd x{tmp}, 8(sp)")],
            lambda: [write_sigupd(val, test_data), *_record_via_sp(test_data, ptr, 8, val, save)],
        ),
        f"LI(x{tmp}, 0x1122334455667788)",
        f"LI(x{val2}, {RD_CANARY:#x})",
        *via_sp(
            [
                ("sp_c_ldsp", f"c.ldsp x{val}, 8(sp)"),
                ("sp_c_sdsp", f"c.sdsp x{tmp}, 0(sp)"),
                ("sp_c_lwsp", f"c.lwsp x{val2}, 4(sp)"),
                ("sp_c_swsp", f"c.swsp x{tmp}, 12(sp)"),
            ],
            lambda: [
                write_sigupd(val, test_data),
                write_sigupd(val2, test_data),
                *_record_via_sp(test_data, ptr, 0, val, save),
                *_record_via_sp(test_data, ptr, 8, val, save),
            ],
            "defined(ZCA_SUPPORTED)",
            "+zca",
        ),
    ]
    if fp:
        lines += via_sp(
            [("sp_c_fldsp", f"c.fldsp f{fval}, 8(sp)"), ("sp_c_fsdsp", f"c.fsdsp f{fval}, 0(sp)")],
            lambda: [
                f"fmv.x.d x{val}, f{fval}",
                write_sigupd(val, test_data),
                *_record_via_sp(test_data, ptr, 0, val, save),
            ],
            "defined(ZCD_SUPPORTED)",
            "+zca, +zcd",
        )
    test_data.int_regs.return_registers([ptr, val, val2, tmp, save])
    test_data.float_regs.return_register(fval)
    return lines


def _order_tests(
    test_data: TestData, cg: str, mode: str, mt_mode: int, mismatch: bool, mt: tuple[list[str], list[str]] = NO_MT
) -> list[str]:
    """Ordering of tag accesses: a store through sp to the tag of data chunk 12 right before a load or a store of the
    chunk, and a settag of chunk 14 right before a load or a store of it: the access is checked against the new tag,
    and, if mismatch, one with the old tag raises a software-check exception. Older divisions delay the commit of the
    tag store, which a hart may still buffer when the access is checked."""
    name = MT_NAMES[mt_mode]
    mt_on, mt_off = mt
    ptr, val, new, save = test_data.int_regs.get_registers(4)
    # The tag byte of chunk 12 with BAD_TAG (and of chunk 13, which shares it with 4-bit tags), and with GOOD_TAG
    offset = 12 if mt_mode == MT_TAG7 else 6
    bad, good = _check_tag_bytes(mt_mode, (12, 13))[offset], _check_tag_bytes(mt_mode)[offset]

    def access(case: str, store: bool, disp: int) -> list[str]:
        """The checked load into x{val}, or store of x{val}, at x{ptr} + disp."""
        return [
            test_data.add_testcase(f"{mode}_{name}_{case}", "cp_checked_order", cg),
            f"{'sd' if store else 'ld'} x{val}, {disp}(x{ptr})",
        ]

    def record(store: bool, disp: int) -> list[str]:
        """Record the loaded doubleword, or the stored one through sp."""
        return _record_via_sp(test_data, ptr, disp, val, save) if store else [write_sigupd(val, test_data)]

    def store_then_access(case: str, byte: int, store: bool) -> list[str]:
        """sp points to the tag byte while memory tagging is enabled: the store through it is not tag checked."""
        return [
            *_check_pointer(ptr, val, mt_mode, 12, BAD_TAG[mt_mode]),
            f"mv x{save}, sp",
            *_check_tags(mt_mode, 2, new),
            f"addi sp, sp, {offset}",
            f"LI(x{new}, {byte:#x})",
            f"LI(x{val}, -1)",
            *mt_on,
            *gated([f"div x{val}, x{val}, x{val}"] * 3, "defined(M_SUPPORTED)"),
            f"sb x{new}, 0(sp)",
            *access(case, store, 0),
            *mt_off,
            f"mv sp, x{save}",
            *record(store, 0),
        ]

    def settag_then_access(case: str, tag: int, store: bool) -> list[str]:
        """settag of chunk 14 with BAD_TAG right before an access of it with the pointer tag tag, then settag of it
        with GOOD_TAG again."""
        return [
            *_check_pointer(new, val, mt_mode, 14, BAD_TAG[mt_mode]),
            *_check_pointer(ptr, val, mt_mode, 14, tag),
            f"LI(x{val}, {RD_CANARY:#x})",
            *mt_on,
            f"settag x{new}, 0",
            *access(case, store, 8),
            *mt_off,
            *record(store, 8),
            *_check_pointer(new, val, mt_mode, 14, GOOD_TAG[mt_mode]),
            *mt_on,
            f"settag x{new}, 0",
            *mt_off,
        ]

    lines = [
        comment_banner(
            f"cp_checked_order ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, a store through sp to the tag of a data chunk behind\n"
            "three divisions, right before a load or a store of the chunk with the stored tag: no exception"
            + (f"; with the old tag: {SW_CHECK_TEXT}" if mismatch else "")
            + ". Then a settag of\nanother chunk right before a load or a store of it with the new tag: no exception"
            + (f"; with the old tag: {SW_CHECK_TEXT}" if mismatch else "")
            + ". Record\nthe loaded and the stored doublewords",
        ),
    ]
    for store in (False, True):
        kind = "store" if store else "load"
        lines += store_then_access(f"store_then_{kind}", bad, store)
        if mismatch:
            lines += store_then_access(f"store_then_{kind}_old_tag", good, store)
    if not mismatch:
        # The tag byte back to GOOD_TAG, through sp: memory tagging may be enabled
        lines += [
            f"mv x{save}, sp",
            *_check_tags(mt_mode, 2, val),
            f"LI(x{val}, {good:#x})",
            f"sb x{val}, {offset}(sp)",
            f"mv sp, x{save}",
        ]
    for store in (False, True):
        kind = "store" if store else "load"
        lines += settag_then_access(f"settag_then_{kind}", BAD_TAG[mt_mode], store)
        if mismatch:
            lines += settag_then_access(f"settag_then_{kind}_old_tag", GOOD_TAG[mt_mode], store)
    test_data.int_regs.return_registers([ptr, val, new, save])
    return lines


def _unchecked_access_tests(
    test_data: TestData, cg: str, mode: str, mt_mode: int, mt: tuple[list[str], list[str]] = NO_MT, m_mode: bool = False
) -> list[str]:
    """Loads and stores that implicit tag checks do not cover, of data chunk UNCHECKED_CHUNK, whose tag is GOOD_TAG,
    with a pointer tag that does not match: LR/SC and an AMO through a pointer with BAD_TAG and, in M-mode, CMOs and
    HLV/HSV through one without a pointer tag (pointer masking need not apply to them), and vector loads and stores
    (unit-stride, strided, indexed and masked, element 0 masked off) with BAD_TAG. No exception. Record the loaded
    values and memory."""
    name = MT_NAMES[mt_mode]
    mt_on, mt_off = mt
    ptr, val, tmp, save = test_data.int_regs.get_registers(4)
    base = f"{CHECK_DATA} + {16 * UNCHECKED_CHUNK}"

    def accesses(cases: list[tuple[str, str]], arch: str) -> list[str]:
        """The (testcase, instruction) cases, assembled with the extensions arch, with memory tagging enabled."""
        lines = [".option push", f".option arch, {arch}", *mt_on]
        for case, instruction in cases:
            lines += [test_data.add_testcase(f"{mode}_{name}_{case}", "cp_unchecked_access", cg), instruction]
        return [*lines, *mt_off, ".option pop"]

    lines = [
        comment_banner(
            f"cp_unchecked_access ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, accesses that implicit tag checks do not cover, with a\n"
            "pointer tag that does not match: LR/SC and an AMO"
            + (", CMOs, HLV/HSV and vector loads and stores" if m_mode else "")
            + ". No exception. Record\nthe loaded values and memory",
        ),
        *gated(
            [
                *_check_pointer(ptr, tmp, mt_mode, UNCHECKED_CHUNK, BAD_TAG[mt_mode]),
                f"LI(x{val}, {RD_CANARY:#x})",
                *accesses([("lr", f"lr.d x{val}, (x{ptr})"), ("sc", f"sc.d x{tmp}, x{val}, (x{ptr})")], "+zalrsc"),
                write_sigupd(val, test_data),
                write_sigupd(tmp, test_data),
            ],
            "defined(ZALRSC_SUPPORTED)",
        ),
        *gated(
            [
                *_check_pointer(ptr, tmp, mt_mode, UNCHECKED_CHUNK, BAD_TAG[mt_mode]),
                f"LI(x{tmp}, 0x0101010101010101)",
                *accesses([("amo", f"amoadd.d x{val}, x{tmp}, (x{ptr})")], "+zaamo"),
                write_sigupd(val, test_data),
                *_record_via_sp(test_data, ptr, 0, val, save),
            ],
            "defined(ZAAMO_SUPPORTED)",
        ),
    ]
    if m_mode:
        lines += [
            f"LA(x{ptr}, {base})",
            *gated(
                accesses([("cbo_clean", f"cbo.clean (x{ptr})"), ("cbo_flush", f"cbo.flush (x{ptr})")], "+zicbom"),
                "defined(ZICBOM_SUPPORTED)",
            ),
            *gated(
                [
                    *accesses([("cbo_zero", f"cbo.zero (x{ptr})")], "+zicboz"),
                    *_record_via_sp(test_data, ptr, 0, val, save),
                ],
                "defined(ZICBOZ_SUPPORTED)",
            ),
            # V-mode loads and stores with Bare translation (vsatp and hgatp) in the VU-mode of hstatus.SPVP = 0
            *gated(
                [
                    "csrw CSR_VSATP, x0",
                    "csrw CSR_HGATP, x0",
                    f"LI(x{tmp}, {1 << 8:#x})    # hstatus.SPVP",
                    f"csrc CSR_HSTATUS, x{tmp}",
                    f"LI(x{val}, 0x0123456789abcdef)",
                    *accesses([("hsv", f"hsv.d x{val}, (x{ptr})"), ("hlv", f"hlv.d x{tmp}, (x{ptr})")], "+h"),
                    write_sigupd(tmp, test_data),
                ],
                "defined(H_SUPPORTED)",
            ),
            # Two 64-bit elements: at the pointer and 8 bytes on (unit-stride), or 16 bytes on (stride and indices 16)
            *gated(
                [
                    f"LI(x{tmp}, MSTATUS_VS)",
                    f"csrs mstatus, x{tmp}",
                    ".option push",
                    ".option arch, +v",
                    "vsetivli x0, 2, e64, m1, ta, ma",
                    f"LI(x{val}, 0x1122334455667788)",
                    f"vmv.v.x v8, x{val}",
                    "vid.v v16",
                    "vsll.vi v16, v16, 4",
                    "vmv.v.i v0, 2",
                    ".option pop",
                    *_check_pointer(ptr, tmp, mt_mode, UNCHECKED_CHUNK, BAD_TAG[mt_mode]),
                    f"LI(x{tmp}, 16)",
                    *accesses(
                        [
                            ("vse", f"vse64.v v8, (x{ptr})"),
                            ("vsse", f"vsse64.v v8, (x{ptr}), x{tmp}"),
                            ("vsuxei", f"vsuxei64.v v8, (x{ptr}), v16"),
                            ("vse_masked", f"vse64.v v8, (x{ptr}), v0.t"),
                            ("vle", f"vle64.v v24, (x{ptr})"),
                            ("vlse", f"vlse64.v v24, (x{ptr}), x{tmp}"),
                            ("vluxei", f"vluxei64.v v24, (x{ptr}), v16"),
                        ],
                        "+v",
                    ),
                    ".option push",
                    ".option arch, +v",
                    f"vmv.x.s x{val}, v24",
                    ".option pop",
                    write_sigupd(val, test_data),
                    *_record_via_sp(test_data, ptr, 0, val, save),
                    *_record_via_sp(test_data, ptr, 8, val, save),
                    *_record_via_sp(test_data, ptr, 16, val, save),
                ],
                "defined(V_SUPPORTED)",
            ),
        ]
    test_data.int_regs.return_registers([ptr, val, tmp, save])
    return lines


def _checktag_sp_tests(
    test_data: TestData, cg: str, mode: str, mt_mode: int, mismatch: bool, mt: tuple[list[str], list[str]] = NO_MT
) -> list[str]:
    """checktag with sp as rs1, which the exemption of the loads and stores with sp as the base register does not
    cover: with the matching pointer tag and, if mismatch, with a mismatching one (a software-check exception)."""
    name = MT_NAMES[mt_mode]
    mt_on, mt_off = mt
    ptr, tmp, save = test_data.int_regs.get_registers(3)
    cases = [(GOOD_TAG[mt_mode], "checktag_sp")]
    if mismatch:
        cases.append((BAD_TAG[mt_mode], "checktag_sp_mismatch"))
    lines = [
        comment_banner(
            f"cp_checktag_sp ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, checktag with sp as rs1 and the matching pointer tag: no\n"
            "exception" + (f"; with a mismatching one: {SW_CHECK_TEXT}" if mismatch else ""),
        ),
    ]
    for tag, case in cases:
        lines += [
            *_check_pointer(ptr, tmp, mt_mode, SP_CHECKTAG_CHUNK, tag),
            f"mv x{save}, sp",
            f"mv sp, x{ptr}",
            *mt_on,
            test_data.add_testcase(f"{mode}_{name}_{case}", "cp_checktag_sp", cg),
            "checktag x2, 0",
            *mt_off,
            f"mv sp, x{save}",
        ]
    test_data.int_regs.return_registers([ptr, tmp, save])
    return lines


def _tag_bit7_tests(test_data: TestData, cg: str, mode: str) -> list[str]:
    """7-bit tags: a memory tag with bit 7 set matches no pointer tag. With the tag of data chunk SP_CHECKTAG_CHUNK
    0x80 | GOOD_TAG, checktag and a load of it with GOOD_TAG raise a software-check exception. The tag byte is stored
    through sp, which no tag check covers."""
    ptr, val, save = test_data.int_regs.get_registers(3)

    def store_tag(byte: int) -> list[str]:
        return [
            f"mv x{save}, sp",
            *_check_tags(MT_TAG7, 2, val),
            f"LI(x{val}, {byte:#x})",
            f"sb x{val}, {SP_CHECKTAG_CHUNK}(sp)",
            f"mv sp, x{save}",
        ]

    lines = [
        comment_banner(
            f"cp_checktag_mt_enabled, cp_checked_access ({mode}, tag7)",
            f"In {mode}-mode with 7-bit tags, the memory tag of a chunk with bit 7 set: checktag and a load with the\n"
            f"pointer tag of its other bits: {SW_CHECK_TEXT}",
        ),
        *store_tag(0x80 | GOOD_TAG[MT_TAG7]),
        *_check_pointer(ptr, val, MT_TAG7, SP_CHECKTAG_CHUNK, GOOD_TAG[MT_TAG7]),
        test_data.add_testcase(f"{mode}_tag7_checktag_tag_bit7", "cp_checktag_mt_enabled", cg),
        f"checktag x{ptr}, 0",
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"{mode}_tag7_ld_tag_bit7", "cp_checked_access", cg),
        f"ld x{val}, 0(x{ptr})",
        write_sigupd(val, test_data),
        *store_tag(GOOD_TAG[MT_TAG7]),
    ]
    test_data.int_regs.return_registers([ptr, val, save])
    return lines


def _checktag_case_tests(
    test_data: TestData, cg: str, mode: str, mt_mode: int, coverpoint: str, exceptions: bool = True
) -> list[str]:
    """The checktags of CHECKTAG_CASES, in a mode whose data chunks have the tags of _check_fill with BAD_CHUNKS: all,
    or without exceptions only those whose chunks all match."""
    name = MT_NAMES[mt_mode]
    ptr, tmp = test_data.int_regs.get_registers(2)
    lines = []
    for first, count, matching in CHECKTAG_CASES:
        if not exceptions and (not matching or any(first <= chunk <= first + count for chunk in BAD_CHUNKS)):
            continue
        tag = GOOD_TAG[mt_mode] if matching else BAD_TAG[mt_mode]
        lines += [
            *_check_pointer(ptr, tmp, mt_mode, first, tag, 5),
            test_data.add_testcase(
                f"{mode}_{name}_chunk{first}_n{count + 1}{'' if matching else '_mismatch'}", coverpoint, cg
            ),
            f"checktag x{ptr}, {count}",
        ]
    test_data.int_regs.return_registers([ptr, tmp])
    return lines


# ---------------------------------------------------------------------------------------------------------------
# checktag and implicit tag checks in M-mode
# ---------------------------------------------------------------------------------------------------------------


def _checktag_sweep_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """checktag of each chunk count from each first chunk in M-mode, whose chunks have the matching tag and the chunks
    right before and after them a mismatching one: no exception."""
    name = MT_NAMES[mt_mode]
    coverpoint = f"cp_checktag_mt_{name}_chunks"
    firsts = SETTAG_FIRST_CHUNKS[mt_mode]
    tags, ptr, mt, tmp = test_data.int_regs.get_registers(4)
    base = _check_tag_bytes(mt_mode)
    lines = [
        comment_banner(
            f"{coverpoint} (M)",
            f"In M-mode with {TAG_BITS[mt_mode]}-bit tags, checktag of 1-16 chunks from each of the data chunks 1 to\n"
            f"{firsts}, whose tags match while those of the chunks right before and after them do not: no exception",
        ),
        *_check_tags(mt_mode, tags, tmp),
        f"LI(x{mt}, {mt_mode << MT_MODE_LSB:#x})",
    ]
    for first in range(1, firsts + 1):
        for count in range(16):
            around = _check_tag_bytes(mt_mode, (first - 1, first + count + 1))
            changed = [i for i, byte in enumerate(around) if byte != base[i]]
            lines += [line for i in changed for line in (f"LI(x{tmp}, {around[i]:#x})", f"sb x{tmp}, {i}(x{tags})")]
            lines += [
                *_check_pointer(ptr, tmp, mt_mode, first, GOOD_TAG[mt_mode], 9),
                f"csrs mseccfg, x{mt}",
                test_data.add_testcase(f"M_{name}_chunk{first}_n{count + 1}", coverpoint, cg),
                f"checktag x{ptr}, {count}",
                f"csrc mseccfg, x{mt}",
            ]
            lines += [line for i in changed for line in (f"LI(x{tmp}, {base[i]:#x})", f"sb x{tmp}, {i}(x{tags})")]
    test_data.int_regs.return_registers([tags, ptr, mt, tmp])
    return lines


def _m_checked_mprv_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """Loads and stores in M-mode with mstatus.MPRV = 1 and MPP = S, checked with the MT_MODE (menvcfg) and tag table
    (svitts) of S-mode, whose address translation is Bare, while mseccfg.MT_MODE = 00; and checktag, which uses those
    of M-mode."""
    name = MT_NAMES[mt_mode]
    ptr, val, tmp, mprv, save = test_data.int_regs.get_registers(5)
    mt = f"{mt_mode << MT_MODE_LSB:#x}"

    def with_mprv(case: str, coverpoint: str, instruction: str) -> list[str]:
        return [
            f"csrs mstatus, x{mprv}",
            test_data.add_testcase(f"M_{name}_mprv_{case}", coverpoint, cg),
            instruction,
            f"csrc mstatus, x{mprv}",
        ]

    lines = [
        comment_banner(
            f"cp_checked_mprv, cp_checktag_mprv (M, {name})",
            f"In M-mode with mstatus.MPRV = 1 and MPP = S, and {TAG_BITS[mt_mode]}-bit tags in S-mode (menvcfg.MT_MODE,\n"
            "svitts) and memory tagging disabled in M-mode: a load with the matching pointer tag, and a load and a\n"
            f"store with a mismatching one: {SW_CHECK_TEXT}, which M-mode takes. checktag uses\n"
            "M-mode's MT_MODE: no check. Then with memory tagging enabled in M-mode only: no check of a load and a\n"
            "store with a mismatching pointer tag, and checktag with the matching one. Record rd and memory",
        ),
        *_check_vitt("CSR_SVITTS", mt_mode, (mprv, tmp, val)),
        *_set_pmm(tmp, "SMNPM"),
        f"LI(x{val}, {mt})",
        f"or x{tmp}, x{tmp}, x{val}",
        f"csrs menvcfg, x{tmp}",
        f"LI(x{tmp}, MSTATUS_MPP)",
        f"csrc mstatus, x{tmp}",
        f"LI(x{mprv}, MSTATUS_MPRV | {1 << 11:#x})    # MPP = S",
        *_check_pointer(ptr, tmp, mt_mode, 3, GOOD_TAG[mt_mode]),
        f"LI(x{val}, {RD_CANARY:#x})",
        *with_mprv("match", "cp_checked_mprv", f"ld x{val}, 0(x{ptr})"),
        write_sigupd(val, test_data),
        *_check_pointer(ptr, tmp, mt_mode, 3, BAD_TAG[mt_mode]),
        f"LI(x{val}, {RD_CANARY:#x})",
        *with_mprv("mismatch", "cp_checked_mprv", f"ld x{val}, 0(x{ptr})"),
        write_sigupd(val, test_data),
        *with_mprv("store_mismatch", "cp_checked_mprv", f"sd x{val}, 0(x{ptr})"),
        *_record_via_sp(test_data, ptr, 0, val, save),
        *_check_pointer(save, tmp, mt_mode, 3, GOOD_TAG[mt_mode]),
        f"LI(x{val}, 0x0123456789abcdef)",
        *with_mprv("store_match", "cp_checked_mprv", f"sd x{val}, 8(x{save})"),
        *_record_via_sp(test_data, ptr, 8, val, save),
        *with_mprv("checktag_m_disabled", "cp_checktag_mprv", f"checktag x{ptr}, 0"),
        # Memory tagging enabled in M-mode only
        f"LI(x{tmp}, {mt})",
        f"csrc menvcfg, x{tmp}",
        f"csrs mseccfg, x{tmp}",
        f"LI(x{val}, {RD_CANARY:#x})",
        *with_mprv("s_disabled", "cp_checked_mprv", f"ld x{val}, 0(x{ptr})"),
        write_sigupd(val, test_data),
        *with_mprv("s_disabled_store", "cp_checked_mprv", f"sd x{val}, 0(x{ptr})"),
        *_record_via_sp(test_data, ptr, 0, val, save),
        *_check_pointer(ptr, tmp, mt_mode, 3, GOOD_TAG[mt_mode]),
        # mseccfg.PMM = 00: checktag still masks the pointer, as the address translation (S-mode's) is the effective one
        *_write_field("mseccfg", PMM_LSB, 0, val, tmp),
        *with_mprv("checktag", "cp_checktag_mprv", f"checktag x{ptr}, 1"),
        *_set_pmm(tmp, "SMMPM"),
        f"csrs mseccfg, x{tmp}",
        f"LI(x{tmp}, {mt})",
        f"csrc mseccfg, x{tmp}",
        f"LI(x{tmp}, {0b11 << PMM_LSB:#x})",
        f"csrc menvcfg, x{tmp}",
        "csrw CSR_SVITTS, x0",
    ]
    test_data.int_regs.return_registers([ptr, val, tmp, mprv, save])
    return lines


def _m_checked_mprv_v_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """Loads and stores in M-mode with mstatus.MPRV = 1 and MPV = 1, checked with the MT_MODE and tag table of VS-mode
    (MPP = S: henvcfg, vsvitts) or VU-mode (MPP = U: senvcfg, vsvittu), whose address translation (vsatp and hgatp)
    is Bare, while mseccfg.MT_MODE = 00 and the tag tables of S-mode and U-mode (svitts, svittu) are 0."""
    name = MT_NAMES[mt_mode]
    ptr, val, tmp, mprv, save = test_data.int_regs.get_registers(5)
    mt = f"{mt_mode << MT_MODE_LSB:#x}"
    lines = [
        comment_banner(
            f"cp_checked_mprv_v (M, {name})",
            f"In M-mode with mstatus.MPRV = 1, MPV = 1 and MPP = S, and {TAG_BITS[mt_mode]}-bit tags in VS-mode\n"
            "(henvcfg.MT_MODE, vsvitts), then MPP = U with them in VU-mode (senvcfg.MT_MODE, vsvittu), and Bare\n"
            "translation: a load and a store with the matching pointer tag, and with a mismatching one: "
            f"{SW_CHECK_TEXT},\nwhich M-mode takes with GVA = 0. Record rd and memory",
        ),
        "csrw CSR_VSATP, x0",
        "csrw CSR_HGATP, x0",
        "csrw CSR_SVITTS, x0",
        "csrw CSR_SVITTU, x0",
    ]
    for vmode, mpp, env, csr in (("VS", 1, "CSR_HENVCFG", "CSR_VSVITTS"), ("VU", 0, "CSR_SENVCFG", "CSR_VSVITTU")):

        def with_mprv(case: str, instruction: str, vmode: str = vmode) -> list[str]:
            return [
                f"csrs mstatus, x{mprv}",
                test_data.add_testcase(f"M_{name}_mprv_{vmode.lower()}_{case}", "cp_checked_mprv_v", cg),
                instruction,
                f"csrc mstatus, x{mprv}",
            ]

        lines += [
            *_check_vitt(csr, mt_mode, (mprv, tmp, val)),
            *_set_pmm(tmp, "SSNPM"),
            f"LI(x{val}, {mt})",
            f"or x{tmp}, x{tmp}, x{val}",
            f"csrs {env}, x{tmp}",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{mprv}, MSTATUS_MPRV | MSTATUS_MPV | {mpp << 11:#x})    # MPP = {'S' if mpp else 'U'}",
            *_check_pointer(ptr, tmp, mt_mode, 3, GOOD_TAG[mt_mode]),
            f"LI(x{val}, {RD_CANARY:#x})",
            *with_mprv("match", f"ld x{val}, 0(x{ptr})"),
            write_sigupd(val, test_data),
            f"LI(x{val}, 0x0123456789abcdef)",
            *with_mprv("store_match", f"sd x{val}, 8(x{ptr})"),
            *_record_via_sp(test_data, ptr, 8, val, save),
            *_check_pointer(ptr, tmp, mt_mode, 3, BAD_TAG[mt_mode]),
            f"LI(x{val}, {RD_CANARY:#x})",
            *with_mprv("mismatch", f"ld x{val}, 0(x{ptr})"),
            write_sigupd(val, test_data),
            *with_mprv("store_mismatch", f"sd x{val}, 0(x{ptr})"),
            *_record_via_sp(test_data, ptr, 0, val, save),
            f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc {env}, x{tmp}",
            f"csrw {csr}, x0",
        ]
    test_data.int_regs.return_registers([ptr, val, tmp, mprv, save])
    return lines


# ---------------------------------------------------------------------------------------------------------------
# checktag in S-mode with Sv39 translation
# ---------------------------------------------------------------------------------------------------------------


class _CheckCrossCase(NamedTuple):
    """A case of the S-mode checktag tests whose tags cross into the second tag table page."""

    name: str
    flags: PteExpression  # leaf flags of the second page
    physical: str  # its physical address, a label expression
    gate: str | None = None
    matching_end: int = 0x2000  # the tags of the checked chunks below this tag table offset match
    through_va: bool = False  # fill the tags at SETTAG_VA instead of the identity mapping


# The cases cross from the first tag table page into the second one, which the case's leaf PTE maps. The tags in the
# first page match; a fault, or a mismatch, is at the first tag byte of the second page. A load page fault without read
# permission (execute-only page) or with A = 0 (with Svade; with Svadu the hart sets A, and the tags of the second page
# match: no exception). Tag loads read Svpbmt IO and NC memory, which map the third page, which no cacheable access
# aliases.
S_CHECKTAG_CROSS_CASES = (
    _CheckCrossCase("cross_valid", PteFlags(execute=False), f"{TAG_TABLE} + 0x1000"),
    _CheckCrossCase("cross_mismatch", PteFlags(execute=False), f"{TAG_TABLE} + 0x1000", matching_end=0x1000),
    _CheckCrossCase("cross_invalid", "0", f"{TAG_TABLE} + 0x1000", matching_end=0x1000),
    _CheckCrossCase(
        "cross_execute_only", PteFlags(read=False, write=False), f"{TAG_TABLE} + 0x1000", matching_end=0x1000
    ),
    _CheckCrossCase("cross_unaccessed", PteFlags(execute=False, accessed=False, dirty=False), f"{TAG_TABLE} + 0x1000"),
    _CheckCrossCase(
        "cross_io", PteFlags(execute=False, extra=("(2 << 61)",)), f"{TAG_TABLE} + 0x2000", SVPBMT_GATE, through_va=True
    ),
    _CheckCrossCase(
        "cross_nc", PteFlags(execute=False, extra=("(1 << 61)",)), f"{TAG_TABLE} + 0x2000", SVPBMT_GATE, through_va=True
    ),
)


def _s_checktag_case(
    test_data: TestData,
    cg: str,
    mt_mode: int,
    name: str,
    pointer: str,
    count: int,
    regs: tuple[int, int, int],
    chunks: tuple[int, int] | None,
    matching_end: int = 0x2000,
    through_va: bool = False,
    coverpoint: str = "cp_checktag_mt_enabled",
) -> list[str]:
    """One checktag of the S-mode tests: fill the doublewords around the page boundary with the pattern, and with the
    checktag tag in the tags of chunks = (first, last) below matching_end; then checktag."""
    a, b, c = regs
    window = [0xFF0, 0xFF8, 0x1000, 0x1008]
    fill = [TAG_PATTERN if chunks is None else _with_tags(offset, *chunks, mt_mode, matching_end) for offset in window]
    return [
        f"LI(x{b}, {SETTAG_VA + 0x1000:#x})" if through_va else f"LA(x{b}, {TAG_TABLE} + 0x1000)",
        *[
            line
            for offset, value in zip(window, fill, strict=True)
            for line in (f"LI(x{c}, {value:#x})", f"sd x{c}, {offset - 0x1000}(x{b})")
        ],
        load_constant(f"x{a}", pointer),
        test_data.add_testcase(f"S_{MT_NAMES[mt_mode]}_{name}", coverpoint, cg),
        f"checktag x{a}, {count}",
    ]


def _s_checktag_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """checktag in S-mode with Sv39 translation and memory tagging enabled with mt_mode (menvcfg.MT_MODE), whose tags
    cross from the first tag table page into the second one; then loads and stores, which are not tag checked with
    address translation. The S-mode trap handler takes the exceptions."""
    name = MT_NAMES[mt_mode]
    a, b, c = test_data.int_regs.get_registers(3)
    regs = (a, b, c)
    first, count = S_SETTAG_CROSS[mt_mode]
    chunks = (first, first + count)

    def second_page(flags: PteExpression, physical: str, *, is_label: bool = True) -> list[str]:
        """Map the second tag table page, the 4 KiB page after SETTAG_VA."""
        return [
            *write_pte(
                SV39,
                level=0,
                flags=flags,
                virtual_address=hex(SETTAG_VA + 0x1000),
                physical_address=physical,
                regs=regs,
                pa_is_label=is_label,
            ),
            "sfence.vma",
        ]

    def svitts(value: str) -> list[str]:
        return [load_constant(f"x{a}", value), f"csrw CSR_SVITTS, x{a}"]

    lines = [
        comment_banner(
            f"cp_checktag_mt_enabled, cp_checktag_addr_msb (S, {name})",
            f"In S-mode with Sv39 and {TAG_BITS[mt_mode]}-bit tags, checktags whose tags cross into a second tag table\n"
            "page that is valid with matching or mismatching tags, invalid, execute-only, not accessed, IO or NC\n"
            f"memory: none, a {SW_CHECK_TEXT}, or a load page fault at its first tag byte. Then the valid case\n"
            "through a pointer with bit 56 or 47 set, which pointer masking sign-extends, a checktag in the faulting\n"
            "region of the load access faults, one whose page-table walk faults, and one at a non-canonical address",
        ),
        *_set_pmm(a, "SMNPM"),
        f"LI(x{b}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{a}, x{a}, x{b}",
        *gated([f"LI(x{b}, MENVCFG_PBMTE)", f"or x{a}, x{a}, x{b}"], SVPBMT_GATE),
        tsbi_call(f"csrs menvcfg, x{a}"),
    ]
    pointer = hex(_settag_pointer(first, mt_mode))
    for case in S_CHECKTAG_CROSS_CASES:
        lines += gated(
            [
                *second_page(case.flags, case.physical),
                *_s_checktag_case(
                    test_data, cg, mt_mode, case.name, pointer, count, regs, chunks, case.matching_end, case.through_va
                ),
            ],
            case.gate,
        )
    lines += [
        *second_page(PteFlags(execute=False), f"{TAG_TABLE} + 0x1000"),
        *svitts(hex(_extended_vitt(SETTAG_VA, SIGN_EXTENDED_BASE, mt_mode))),
        *_s_checktag_case(
            test_data,
            cg,
            mt_mode,
            "sign_extended",
            hex(_extended_pointer(SIGN_EXTENDED_BASE, first, mt_mode)),
            count,
            regs,
            chunks,
            coverpoint="cp_checktag_addr_msb",
        ),
        *svitts(hex(SETTAG_VA)),
    ]
    # Tags FAULT_BYTE bytes into the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD, in the second page: load
    # access fault. With 4-bit tags, the first one is an upper half.
    fault_offset = f"(0x1000 + ({LOAD_FAULT_TAG} & 0xfff))"
    fault_chunk = fault_offset if mt_mode == MT_TAG7 else f"(2 * {fault_offset} + 1)"
    lines += gated(
        [
            *second_page(PteFlags(execute=False), LOAD_FAULT_TAG, is_label=False),
            *_s_checktag_case(
                test_data,
                cg,
                mt_mode,
                "access_fault",
                f"{_tag_field(SETTAG_TAG[mt_mode], mt_mode):#x} | ({fault_chunk} << 4)",
                1,
                regs,
                None,
            ),
        ],
        f"defined({LOAD_FAULT})",
    )
    # A tag table base whose level-0 page table is in the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD: the
    # page-table walk raises a load access fault
    walk_region = hex(SETTAG_VA + 0x20_0000)
    lines += gated(
        [
            *write_pte(
                SV39,
                level=1,
                flags=PteFlags.nonleaf(),
                virtual_address=walk_region,
                physical_address=SV39.access_fault_pte_address(LOAD_FAULT),
                regs=regs,
                pa_is_label=False,
            ),
            "sfence.vma",
            *svitts(f"({SV39.access_fault_walk_va(walk_region, 0, LOAD_FAULT)}) & ~0xfff"),
            *_s_checktag_case(
                test_data,
                cg,
                mt_mode,
                "walk_access_fault",
                hex(_settag_pointer(SETTAG_CHUNK0 + 5, mt_mode)),
                1,
                regs,
                None,
            ),
            *svitts(hex(SETTAG_VA)),
        ],
        f"defined({LOAD_FAULT})",
    )
    lines += [
        *svitts(hex(SETTAG_VA_NONCANONICAL)),
        *_s_checktag_case(
            test_data, cg, mt_mode, "noncanonical", hex(_settag_pointer(SETTAG_CHUNK0 + 5, mt_mode)), 1, regs, None
        ),
        *svitts(hex(SETTAG_VA)),
        comment_banner(
            f"cp_checked_translated (S, {name})",
            "With address translation, loads and stores are not tag checked: a load and a store of the first tag\n"
            "table page through SETTAG_VA with a mismatching pointer tag, whose tags are not mapped. Record both",
        ),
        *second_page(PteFlags(execute=False), f"{TAG_TABLE} + 0x1000"),
        f"LI(x{b}, {_tag_field(BAD_TAG[mt_mode], mt_mode) | (SETTAG_VA + 0x800):#x})",
        f"LI(x{c}, {RD_CANARY:#x})",
        test_data.add_testcase(f"S_{name}_translated_load", "cp_checked_translated", cg),
        f"ld x{c}, 0(x{b})",
        write_sigupd(c, test_data),
        f"LI(x{c}, 0x0123456789abcdef)",
        test_data.add_testcase(f"S_{name}_translated_store", "cp_checked_translated", cg),
        f"sd x{c}, 8(x{b})",
        f"ld x{c}, 8(x{b})",
        write_sigupd(c, test_data),
        f"LI(x{a}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        *gated([f"LI(x{b}, MENVCFG_PBMTE)", f"or x{a}, x{a}, x{b}"], SVPBMT_GATE),
        tsbi_call(f"csrc menvcfg, x{a}"),
    ]
    test_data.int_regs.return_registers(list(regs))
    return lines


# ---------------------------------------------------------------------------------------------------------------
# checktag and implicit tag checks in VS-mode with guest translation
# ---------------------------------------------------------------------------------------------------------------

# VS-mode checktags with guest translation, as the settags of H_TWO_STAGE_CASES and H_G_STAGE_CASES: a VS-stage fault is
# a load page fault, a G-stage one a load guest-page fault. Without read permission, the page is execute-only.
H_CHECKTAG_TWO_STAGE_CASES = (
    ("two_stage", PteFlags(execute=False), PteFlags(user=True, execute=False), True),
    ("two_stage_mismatch", PteFlags(execute=False), PteFlags(user=True, execute=False), False),
    ("two_stage_vs_execute_only", PteFlags(read=False, write=False), PteFlags(user=True, execute=False), True),
    ("two_stage_g_execute_only", PteFlags(execute=False), PteFlags(user=True, read=False, write=False), True),
    ("two_stage_g_invalid", PteFlags(execute=False), "0", True),
)
H_CHECKTAG_G_STAGE_CASES = (
    ("g_stage", PteFlags(user=True, execute=False)),
    ("g_stage_execute_only", PteFlags(user=True, read=False, write=False)),
)


def _h_guest_checktag_case(
    test_data: TestData,
    cg: str,
    mt_mode: int,
    name: str,
    coverpoint: str,
    vitt: int,
    setup: list[str],
    matching: bool = True,
) -> list[str]:
    """In HS-mode, run setup and fill the second tag table page around the tags (with the matching tags, or the
    pattern); in VS-mode with vsvitts = vitt, checktag of 2 chunks."""
    first = SETTAG_CHUNK0 + 5
    window = _settag_window(first, first + 1, mt_mode)
    base, val, ptr = test_data.int_regs.get_registers(3)
    lines = [
        *setup,
        f"LA(x{base}, {TAG_TABLE} + 0x1000)",
        *[
            line
            for offset in window
            for line in (
                f"LI(x{val}, {(_with_tags(offset, first, first + 1, mt_mode, 0x2000) if matching else TAG_PATTERN):#x})",
                f"sd x{val}, {offset}(x{base})",
            )
        ],
        f"LI(x{val}, {vitt:#x})",
        f"csrw CSR_VSVITTS, x{val}",
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{ptr}, {_settag_pointer(first, mt_mode):#x})",
        test_data.add_testcase(f"VS_{MT_NAMES[mt_mode]}_{name}", coverpoint, cg),
        f"checktag x{ptr}, 1",
        "RVTEST_TSBI_GOTO_SMODE",
    ]
    test_data.int_regs.return_registers([base, val, ptr])
    return lines


# The data chunk of the VS-mode loads and stores with the G stage only, whose memory tag is GOOD_TAG, and the data of
# their stores with the matching and the mismatching pointer tag
G_STAGE_CHUNK = 3
G_STAGE_STORE_DATA = {"match": 0x0123_4567_89AB_CDEF, "mismatch": 0xFEDC_BA98_7654_3210}


def _check_data_dword(chunk: int, dword: int) -> int:
    """The original content of doubleword dword (0 or 1) of data chunk chunk (see _check_data)."""
    return sum(((37 * (16 * chunk + 8 * dword + b) + 11) & 0xFF) << (8 * b) for b in range(8))


def _h_two_stage_unchecked_tests(test_data: TestData, cg: str, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """With two-stage translation, whose first-stage paging makes only PTE.MTAG pages tagged-data pages (PTE.MTAG is
    not allocated yet): in VS-mode, a load and a store of the valid tag page with a mismatching pointer tag, which are
    not tag checked."""
    _, addr, tmp = regs
    name = MT_NAMES[mt_mode]
    return [
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=PteFlags(execute=False),
            virtual_address=VS_SV39.data_va,
            physical_address=SV39X4.data_va,
            regs=regs,
            pa_is_label=False,
        ),
        *create_page_mapping(
            SV39X4,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False),
            virtual_address=SV39X4.data_va,
            physical_address=f"{TAG_TABLE} + 0x1000",
            regs=regs,
        ),
        "hfence.vvma",
        "hfence.gvma",
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{addr}, {_tag_field(BAD_TAG[mt_mode], mt_mode) | (int(VS_SV39.data_va, 16) + 0x800):#x})",
        f"LI(x{tmp}, {RD_CANARY:#x})",
        test_data.add_testcase(f"VS_{name}_two_stage_load", "cp_checked_translated", cg),
        f"ld x{tmp}, 0(x{addr})",
        write_sigupd(tmp, test_data),
        f"LI(x{tmp}, 0x0123456789abcdef)",
        test_data.add_testcase(f"VS_{name}_two_stage_store", "cp_checked_translated", cg),
        f"sd x{tmp}, 8(x{addr})",
        f"ld x{tmp}, 8(x{addr})",
        write_sigupd(tmp, test_data),
        "RVTEST_TSBI_GOTO_SMODE",
    ]


def _h_g_stage_checked_tests(test_data: TestData, cg: str, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """With the G stage only: tagged-data pages are defined by first-stage page tables, so with vsatp = Bare all data
    pages are, and VS-mode loads and stores are tag checked, with the G stage translating their tag loads. With vsvitts
    putting the tags of the data chunks in the first tag table page (which the G stage maps with the test image), a
    load and a store of data chunk G_STAGE_CHUNK with the matching and with a mismatching pointer tag; then, with
    vsvitts putting them in the guest physical page SV39X4.data_va, which the G stage maps execute-only, a load and a
    store whose tag load raises a load guest-page fault. HS-mode computes the pointers (the guest code runs at an
    alias, so its PC-relative addresses differ), takes the traps, records the doubleword the stores write and restores
    it."""
    ptr, bad, val = regs
    name = MT_NAMES[mt_mode]
    coverpoint = "cp_checked_g_stage"
    offset = 16 * G_STAGE_CHUNK + 8
    lines = [
        *_check_vitt("CSR_VSVITTS", mt_mode, regs),
        *_check_fill(mt_mode, ptr, val, BAD_CHUNKS),
        *_check_pointer(ptr, val, mt_mode, G_STAGE_CHUNK, GOOD_TAG[mt_mode]),
        *_check_pointer(bad, val, mt_mode, G_STAGE_CHUNK, BAD_TAG[mt_mode]),
        "RVTEST_TSBI_GOTO_VSMODE",
    ]
    for case, reg in (("match", ptr), ("mismatch", bad)):
        lines += [
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase(f"VS_{name}_g_stage_{case}_load", coverpoint, cg),
            f"ld x{val}, 0(x{reg})",
            write_sigupd(val, test_data),
            f"LI(x{val}, {G_STAGE_STORE_DATA[case]:#x})",
            test_data.add_testcase(f"VS_{name}_g_stage_{case}_store", coverpoint, cg),
            f"sd x{val}, 8(x{reg})",
        ]

    def restore() -> list[str]:
        """Record the doubleword that the stores write, and restore it."""
        return [
            f"LA(x{ptr}, {CHECK_DATA} + {offset})",
            f"ld x{val}, 0(x{ptr})",
            write_sigupd(val, test_data),
            f"LI(x{val}, {_check_data_dword(G_STAGE_CHUNK, 1):#x})",
            f"sd x{val}, 0(x{ptr})",
        ]

    lines += [
        "RVTEST_TSBI_GOTO_SMODE",
        *restore(),
        *create_page_mapping(
            SV39X4,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, read=False, write=False),
            virtual_address=SV39X4.data_va,
            physical_address=f"{TAG_TABLE} + 0x1000",
            regs=regs,
        ),
        "hfence.gvma",
        *_check_vitt("CSR_VSVITTS", mt_mode, regs, table=SV39X4.data_va),
        *_check_pointer(ptr, val, mt_mode, G_STAGE_CHUNK, GOOD_TAG[mt_mode]),
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"VS_{name}_g_stage_tag_fault_load", coverpoint, cg),
        f"ld x{val}, 0(x{ptr})",
        write_sigupd(val, test_data),
        f"LI(x{val}, {G_STAGE_STORE_DATA['match']:#x})",
        test_data.add_testcase(f"VS_{name}_g_stage_tag_fault_store", coverpoint, cg),
        f"sd x{val}, 8(x{ptr})",
        "RVTEST_TSBI_GOTO_SMODE",
        *restore(),
    ]
    return lines


def _h_guest_checktag_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """checktag in VS-mode with two-stage translation and with the G stage only, and loads and stores: not tag checked
    with two-stage translation, tag checked with the G stage only."""
    name = MT_NAMES[mt_mode]
    pte, addr, tmp = test_data.int_regs.get_registers(3)
    regs = (pte, addr, tmp)
    lines = [
        comment_banner(
            f"cp_checktag_two_stage, cp_checktag_g_stage, cp_checked_translated, cp_checked_g_stage (VS, {name})",
            f"In VS-mode with {TAG_BITS[mt_mode]}-bit tags, checktags with two-stage translation whose tag page is\n"
            "valid with matching or mismatching tags, execute-only in the VS stage (load page fault), or\n"
            "execute-only or invalid in the G stage (load guest-page fault), and with the G stage only whose tag\n"
            "page is valid or execute-only, or whose tag table base is above the guest physical addresses of\n"
            "Sv39x4. HS-mode takes the traps. With two-stage translation, a load and a store with a mismatching\n"
            "pointer tag: not tag checked. With the G stage only, loads and stores with the matching and a\n"
            "mismatching pointer tag, and with their tags in a page that the G stage maps execute-only (load\n"
            "guest-page fault, also for the store): tag checked",
        ),
        *_set_pmm(pte, "SSNPM"),
        f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{pte}, x{pte}, x{tmp}",
        f"csrs henvcfg, x{pte}",
        *guest_translation_setup(test_data, SV39X4, VS_SV39, "VSmode"),
    ]
    for case, vs_flags, g_flags, matching in H_CHECKTAG_TWO_STAGE_CASES:
        setup = [
            *create_page_mapping(
                VS_SV39,
                leaf_level=0,
                leaf_flags=vs_flags,
                virtual_address=VS_SV39.data_va,
                physical_address=SV39X4.data_va,
                regs=regs,
                pa_is_label=False,
            ),
            *create_page_mapping(
                SV39X4,
                leaf_level=0,
                leaf_flags=g_flags,
                virtual_address=SV39X4.data_va,
                physical_address=f"{TAG_TABLE} + 0x1000",
                regs=regs,
            ),
            "hfence.vvma",
            "hfence.gvma",
        ]
        lines += _h_guest_checktag_case(
            test_data, cg, mt_mode, case, "cp_checktag_two_stage", int(VS_SV39.data_va, 16), setup, matching
        )
    lines += _h_two_stage_unchecked_tests(test_data, cg, mt_mode, regs)
    lines += [*guest_translation_teardown(test_data), *guest_translation_setup(test_data, SV39X4, None, "VSmode")]
    for case, g_flags in H_CHECKTAG_G_STAGE_CASES:
        setup = [
            *create_page_mapping(
                SV39X4,
                leaf_level=0,
                leaf_flags=g_flags,
                virtual_address=SV39X4.data_va,
                physical_address=f"{TAG_TABLE} + 0x1000",
                regs=regs,
            ),
            "hfence.gvma",
        ]
        lines += _h_guest_checktag_case(
            test_data, cg, mt_mode, case, "cp_checktag_g_stage", int(SV39X4.data_va, 16), setup
        )
    lines += _h_guest_checktag_case(
        test_data, cg, mt_mode, "g_stage_gpa_too_wide", "cp_checktag_g_stage", H_GPA_TOO_WIDE, []
    )
    lines += _h_g_stage_checked_tests(test_data, cg, mt_mode, regs)
    lines += [
        *guest_translation_teardown(test_data),
        f"LI(x{pte}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        f"csrc henvcfg, x{pte}",
        "csrw CSR_VSVITTS, x0",
    ]
    test_data.int_regs.return_registers(list(regs))
    return lines


# Each _mt test enables memory tagging in the mode under test with MT_MODE = 10 and then, with 7-bit pointer tags,
# 11. The field another mode uses then holds a value that changes what gentag and addtag write, so a hart that
# reads the wrong field fails: (MT_MODE of the mode under test, value of the other field).
MT_ITERATIONS = ((MT_TAG4, MT_DISABLED), (MT_TAG7, MT_TAG4))


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "Sm"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_MMODE"],
)
def make_zimt_sm(test_data: TestData) -> list[TestChunk]:
    """Generate the Zimt tests in M-mode."""
    cg = "Zimt_Sm_cg"
    chunks = []
    tc = test_data.begin_test_chunk("Sm")
    tc.code.extend(_mt_disabled_tests(test_data, cg, "M"))
    chunks.append(test_data.end_test_chunk())

    # menvcfg exists only with U-mode, and medeleg and menvmtagexclude only with S-mode
    tc = test_data.begin_test_chunk("Sm_csr")
    tc.code.extend(
        [
            *_mtagexclude_reset_tests(test_data, cg),
            *_mt_mode_warl_tests(test_data, cg, "mseccfg"),
            *gated(_mt_mode_warl_tests(test_data, cg, "menvcfg"), "defined(U_SUPPORTED)"),
            *_mtagexclude_warl_tests(test_data, cg, "m"),
            *gated(_mtagexclude_warl_tests(test_data, cg, "menv"), MTAGEXCLUDE_GATE["menv"]),
            *gated(_swcheck_deleg_tests(test_data, cg, "medeleg"), "defined(S_SUPPORTED)"),
            *_swcheck_cause_tests(test_data, cg, "mcause"),
        ]
    )
    chunks.append(test_data.end_test_chunk())

    tc = test_data.begin_test_chunk("Sm_mt")
    tc.code.extend(_m_mt_tests(test_data, cg))
    chunks.append(test_data.end_test_chunk())
    return chunks


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "S"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_zimt_s(test_data: TestData) -> list[TestChunk]:
    """Generate the Zimt tests in S-mode."""
    cg = "Zimt_S_cg"
    chunks = []
    tc = test_data.begin_test_chunk("S")
    tc.code.extend(_mt_disabled_tests(test_data, cg, "S"))
    chunks.append(test_data.end_test_chunk())

    tc = test_data.begin_test_chunk("S_csr")
    tc.code.extend(
        [
            *_mt_mode_warl_tests(test_data, cg, "senvcfg"),
            *_mtagexclude_warl_tests(test_data, cg, "senv"),
            *_swcheck_cause_tests(test_data, cg, "scause"),
            *_csr_access_tests(test_data, cg, "S"),
        ]
    )
    chunks.append(test_data.end_test_chunk())

    # S-mode uses menvcfg.MT_MODE and menvmtagexclude, which M-mode sets. The M-mode exclusion mask and the
    # U-mode MT_MODE and mask hold other values; mseccfg.MT_MODE stays 00 for the M-mode trap handler.
    tc = test_data.begin_test_chunk("S_mt")
    val, tmp = test_data.int_regs.get_registers(2)
    for mt_mode, other in MT_ITERATIONS:
        iteration = [
            "RVTEST_TSBI_GOTO_MMODE",
            *_configure([("menvcfg", mt_mode), ("senvcfg", other)], ["m", "menv", "senv"], val, tmp),
            "RVTEST_TSBI_GOTO_SMODE",
        ]
        test_data.int_regs.return_registers([val, tmp])
        iteration += _mt_mode_tests(test_data, cg, "S", mt_mode, ENV_TAG["menv"])
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
        val, tmp = test_data.int_regs.get_registers(2)
    tc.code += [
        "RVTEST_TSBI_GOTO_MMODE",
        *_restore(["menvcfg", "senvcfg"], ["m", "menv", "senv"], val, tmp),
        "RVTEST_TSBI_GOTO_SMODE",
    ]
    test_data.int_regs.return_registers([val, tmp])
    chunks.append(test_data.end_test_chunk())
    return chunks


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "U"],
    params=["MXLEN: 64"],
)
def make_zimt_u(test_data: TestData) -> list[TestChunk]:
    """Generate the Zimt tests in U-mode with memory tagging disabled, and the access to the CSRs from U-mode."""
    cg = "Zimt_U_cg"
    chunks = []
    tc = test_data.begin_test_chunk("U")
    tc.code.extend(_mt_disabled_tests(test_data, cg, "U"))
    chunks.append(test_data.end_test_chunk())

    tc = test_data.begin_test_chunk("U_csr")
    tc.code.extend(_csr_access_tests(test_data, cg, "U"))
    chunks.append(test_data.end_test_chunk())
    return chunks


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "U", "S"],
    params=["MXLEN: 64"],
)
def make_zimt_u_mt(test_data: TestData) -> list[TestChunk]:
    """Generate the Zimt tests in U-mode with memory tagging enabled.

    U-mode uses senvcfg.MT_MODE and senvmtagexclude, which exist only with S-mode, where they are set. menvcfg.MT_MODE
    stays 00 for the S-mode trap handler, which serves the U-mode T-SBI calls.
    """
    cg = "Zimt_U_cg"
    tc = test_data.begin_test_chunk("U_mt")
    val, tmp = test_data.int_regs.get_registers(2)
    for mt_mode, _ in MT_ITERATIONS:
        iteration = [
            "RVTEST_TSBI_GOTO_SMODE",
            *_configure([("senvcfg", mt_mode)], ["senv"], val, tmp),
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_registers([val, tmp])
        iteration += _mt_mode_tests(test_data, cg, "U", mt_mode, ENV_TAG["senv"])
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
        val, tmp = test_data.int_regs.get_registers(2)
    tc.code += [
        "RVTEST_TSBI_GOTO_SMODE",
        *_restore(["senvcfg"], ["senv"], val, tmp),
        "RVTEST_TSBI_GOTO_UMODE",
    ]
    test_data.int_regs.return_registers([val, tmp])
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "H"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_zimt_h(test_data: TestData) -> list[TestChunk]:
    """Generate the Zimt tests in VS-mode and VU-mode, entered from HS-mode."""
    cg = "Zimt_H_cg"
    chunks = []
    tc = test_data.begin_test_chunk("H")
    for mode in ("VS", "VU"):
        tc.code.append(f"RVTEST_TSBI_GOTO_{mode}MODE")
        tc.code.extend(_mt_disabled_tests(test_data, cg, mode))
    tc.code.append("RVTEST_TSBI_GOTO_SMODE")
    chunks.append(test_data.end_test_chunk())

    # The HS-mode CSRs, then the access from VS-mode and VU-mode
    tc = test_data.begin_test_chunk("H_csr")
    tc.code.extend(
        [
            *_mt_mode_warl_tests(test_data, cg, "henvcfg"),
            *_mt_mode_warl_tests(test_data, cg, "hstatus", VUMT_MODE_LSB),
            *_mtagexclude_warl_tests(test_data, cg, "henv"),
            *_swcheck_deleg_tests(test_data, cg, "hedeleg"),
            *_swcheck_cause_tests(test_data, cg, "vscause"),
        ]
    )
    for mode in ("VS", "VU"):
        tc.code += [
            f"RVTEST_TSBI_GOTO_{mode}MODE",
            *_csr_access_tests(test_data, cg, mode),
            "RVTEST_TSBI_GOTO_SMODE",
        ]
    chunks.append(test_data.end_test_chunk())

    # VS-mode uses henvcfg.MT_MODE and henvmtagexclude, VU-mode senvcfg.MT_MODE and senvmtagexclude, which HS-mode
    # sets. In VS-mode, senvcfg and senvmtagexclude hold other values. In VU-mode, henvcfg.MT_MODE stays 00 for the
    # VS-mode trap handler, which serves the VU-mode T-SBI calls, and henvmtagexclude holds another value.
    tc = test_data.begin_test_chunk("H_mt")
    val, tmp = test_data.int_regs.get_registers(2)
    for mode in ("VS", "VU"):
        for mt_mode, other in MT_ITERATIONS:
            fields = [("henvcfg", mt_mode), ("senvcfg", other)] if mode == "VS" else [("senvcfg", mt_mode)]
            iteration = [
                *_configure(fields, ["senv", "henv"], val, tmp),
                f"RVTEST_TSBI_GOTO_{mode}MODE",
            ]
            test_data.int_regs.return_registers([val, tmp])
            iteration += _mt_mode_tests(test_data, cg, mode, mt_mode, ENV_TAG["henv" if mode == "VS" else "senv"])
            val, tmp = test_data.int_regs.get_registers(2)
            iteration += ["RVTEST_TSBI_GOTO_SMODE", *_restore(["henvcfg", "senvcfg"], [], val, tmp)]
            tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.code += _restore([], ["senv", "henv"], val, tmp)
    test_data.int_regs.return_registers([val, tmp])
    chunks.append(test_data.end_test_chunk())
    return chunks


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "Sm", "Smvatag", "Smmpm"],
    march_extensions=["Zimop"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_MMODE"],
)
def make_zimt_sm_settag(test_data: TestData) -> list[TestChunk]:
    """Generate the settag tests in M-mode, with the tag table mvitt and pointer masking (mseccfg.PMM).

    Besides the sweeps, a settag through a pointer whose masked address is zero-extended and, if S-mode has pointer
    masking and a tag table, one with mstatus.MPRV = 1 and MPP = S.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_Sm_cg"
    tc = test_data.begin_test_chunk("Sm_settag")
    val, tmp = test_data.int_regs.get_registers(2)
    tc.code += [
        comment_banner("settag in M-mode", "mvitt = the tag table, and pointer masking in M-mode"),
        f"LA(x{val}, {TAG_TABLE})",
        f"csrw CSR_MVITT, x{val}",
        *_set_pmm(val, "SMMPM"),
        f"csrs mseccfg, x{val}",
    ]
    test_data.int_regs.return_registers([val, tmp])
    for mt_mode in (MT_TAG4, MT_TAG7):
        iteration = _settag_sweep_tests(test_data, cg, "M", mt_mode)
        if mt_mode == MT_TAG4:
            iteration += _settag_rs1_tests(test_data, cg)
        iteration += _sm_zero_extended_tests(test_data, cg, mt_mode)
        iteration += gated(_sm_mprv_tests(test_data, cg, mt_mode), SM_MPRV_GATE)
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    val, tmp = test_data.int_regs.get_registers(2)
    tc.code += [
        comment_banner("Restore", "mseccfg.PMM = 00 and mvitt = 0"),
        *_write_field("mseccfg", PMM_LSB, 0, val, tmp),
        "csrw CSR_MVITT, x0",
    ]
    test_data.int_regs.return_registers([val, tmp])
    tc.raw_data += _tag_table_data()
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "S", "Svatag", "Smnpm", "Sv39"],
    march_extensions=["Zimop"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_zimt_s_settag(test_data: TestData) -> list[TestChunk]:
    """Generate the settag tests in S-mode with Sv39 translation, with the tag table svitts."""
    _check_sig_reg(test_data)
    cg = "Zimt_S_cg"
    tc = test_data.begin_test_chunk("S_settag")
    a, b, c = test_data.int_regs.get_registers(3)
    regs = (a, b, c)
    tc.code += [
        comment_banner(
            "settag in S-mode",
            f"svitts = {SETTAG_VA:#x}, mapped with 4 KiB pages to the tag table, and Sv39 translation, which also\n"
            "maps the test image with the boot page tables. svittu = 0, which S-mode does not use",
        ),
        *create_page_mapping(
            SV39,
            leaf_level=0,
            leaf_flags=PteFlags(execute=False),
            virtual_address=hex(SETTAG_VA),
            physical_address=TAG_TABLE,
            regs=regs,
        ),
        f"LI(x{a}, {SETTAG_VA:#x})",
        f"csrw CSR_SVITTS, x{a}",
        "csrw CSR_SVITTU, x0",
        "sfence.vma",
        SV39.satp_setup,
        "sfence.vma",
    ]
    test_data.int_regs.return_registers(list(regs))
    tc.code += _s_settag_tests(test_data, cg, MT_TAG4)
    tc.code += _tag7(_s_settag_tests(test_data, cg, MT_TAG7))
    tc.code += [
        comment_banner("Restore", "satp = 0 and svitts = 0"),
        "csrw satp, x0",
        "sfence.vma",
        "csrw CSR_SVITTS, x0",
    ]
    tc.raw_data += [*_tag_table_data(), *lower_table_data(SV39)]
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "U", "S", "Svatag", "Ssnpm"],
    march_extensions=["Zimop"],
    params=["MXLEN: 64"],
)
def make_zimt_u_settag(test_data: TestData) -> list[TestChunk]:
    """Generate the settag tests in U-mode, with the tag table svittu, which S-mode sets.

    U-mode uses senvcfg.MT_MODE and senvcfg.PMM. S-mode, which serves the U-mode T-SBI calls, keeps memory tagging
    disabled and records the tag table. A settag in the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_STORE raises a
    store/AMO access fault.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_U_cg"
    tc = test_data.begin_test_chunk("U_settag")
    for mt_mode in (MT_TAG4, MT_TAG7):
        name = MT_NAMES[mt_mode]
        window = _vitt_settag_window(mt_mode)
        base, val, tmp = test_data.int_regs.get_registers(3)
        iteration = [
            comment_banner(
                f"cp_settag_mt_enabled (U, {name})",
                f"In U-mode with {TAG_BITS[mt_mode]}-bit tags, settags with svittu = the tag table, then one from\n"
                f"{STORE_FAULT} + {FAULT_BYTE}: store/AMO access fault. Record the tag table around the tags",
            ),
            "RVTEST_TSBI_GOTO_SMODE",
            f"LA(x{base}, {TAG_TABLE})",
            f"csrw CSR_SVITTU, x{base}",
            "csrw CSR_SVITTS, x0",
            f"LI(x{val}, {TAG_PATTERN:#x})",
            *_fill_tags(base, val, window),
            *_set_pmm(val, "SSNPM"),
            f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{val}, x{val}, x{tmp}",
            f"csrs senvcfg, x{val}",
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_registers([base, val, tmp])
        iteration += _vitt_settag_tests(test_data, cg, "U", mt_mode, "cp_settag_mt_enabled")
        base, val, tmp = test_data.int_regs.get_registers(3)
        fault_chunk = f"({FAULT_TAG} & 0xfff)" if mt_mode == MT_TAG7 else f"(2 * ({FAULT_TAG} & 0xfff) + 1)"
        iteration += gated(
            [
                "RVTEST_TSBI_GOTO_SMODE",
                load_constant(f"x{val}", f"{FAULT_TAG} & ~0xfff"),
                f"csrw CSR_SVITTU, x{val}",
                "RVTEST_TSBI_GOTO_UMODE",
                load_constant(f"x{val}", f"{_tag_field(SETTAG_TAG[mt_mode], mt_mode):#x} | ({fault_chunk} << 4)"),
                test_data.add_testcase(f"U_{name}_access_fault", "cp_settag_mt_enabled", cg),
                f"settag x{val}, 1",
            ],
            f"defined({STORE_FAULT})",
        )
        iteration += [
            "RVTEST_TSBI_GOTO_SMODE",
            f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{val}",
            "csrw CSR_SVITTU, x0",
            f"LA(x{base}, {TAG_TABLE})",
            *_record_tags(test_data, base, val, window),
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_registers([base, val, tmp])
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.raw_data += _tag_table_data()
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "H", "Svatag", "Ssnpm"],
    march_extensions=["Zimop", "H"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_zimt_h_settag(test_data: TestData) -> list[TestChunk]:
    """Generate the settag tests in VS-mode and VU-mode, which use the tag tables vsvitts and vsvittu.

    VS-mode uses henvcfg.MT_MODE and henvcfg.PMM, VU-mode senvcfg.MT_MODE and senvcfg.PMM, which HS-mode sets.
    vsvitts is the first tag table page and vsvittu the second, and svitts and svittu are 0. HS-mode, and VS-mode
    while VU-mode runs, keep memory tagging disabled. HS-mode records both pages around the tags. Then, with Sv39,
    VS-mode settags with guest translation, whose page faults and guest-page faults HS-mode takes.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_H_cg"
    tc = test_data.begin_test_chunk("H_settag")
    for mt_mode in (MT_TAG4, MT_TAG7):
        name = MT_NAMES[mt_mode]
        window = _vitt_settag_window(mt_mode)
        base, val, tmp = test_data.int_regs.get_registers(3)
        iteration = [
            comment_banner(
                f"cp_settag_mt_enabled (VS, VU, {name})",
                f"In VS-mode and VU-mode with {TAG_BITS[mt_mode]}-bit tags, settags with vsvitts = the first tag\n"
                "table page and vsvittu = the second one. Record both pages around the tags",
            ),
            f"LA(x{base}, {TAG_TABLE})",
            f"csrw CSR_VSVITTS, x{base}",
            f"LI(x{tmp}, 0x1000)",
            f"add x{tmp}, x{base}, x{tmp}",
            f"csrw CSR_VSVITTU, x{tmp}",
            "csrw CSR_SVITTS, x0",
            "csrw CSR_SVITTU, x0",
            f"LI(x{val}, {TAG_PATTERN:#x})",
            *_fill_tags(base, val, window),
            *_fill_tags(tmp, val, window),
            *_set_pmm(val, "SSNPM"),
            f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{val}, x{val}, x{tmp}",
            f"csrs henvcfg, x{val}",
            "RVTEST_TSBI_GOTO_VSMODE",
        ]
        test_data.int_regs.return_registers([base, val, tmp])
        iteration += _vitt_settag_tests(test_data, cg, "VS", mt_mode, "cp_settag_mt_enabled")
        base, val, tmp = test_data.int_regs.get_registers(3)
        iteration += [
            "RVTEST_TSBI_GOTO_SMODE",
            f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc henvcfg, x{val}",
            *_set_pmm(val, "SSNPM"),
            f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{val}, x{val}, x{tmp}",
            f"csrs senvcfg, x{val}",
            "RVTEST_TSBI_GOTO_VUMODE",
        ]
        test_data.int_regs.return_registers([base, val, tmp])
        iteration += _vitt_settag_tests(test_data, cg, "VU", mt_mode, "cp_settag_mt_enabled")
        base, val, tmp = test_data.int_regs.get_registers(3)
        iteration += [
            "RVTEST_TSBI_GOTO_SMODE",
            f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{val}",
            "csrw CSR_VSVITTS, x0",
            "csrw CSR_VSVITTU, x0",
            f"LA(x{base}, {TAG_TABLE})",
            *_record_tags(test_data, base, val, window),
            f"LI(x{tmp}, 0x1000)",
            f"add x{base}, x{base}, x{tmp}",
            *_record_tags(test_data, base, val, window),
        ]
        test_data.int_regs.return_registers([base, val, tmp])
        iteration += gated(_h_guest_settag_tests(test_data, cg, mt_mode), "defined(SV39_SUPPORTED)")
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.raw_data += [*_tag_table_data(), *guest_table_data()]
    return [test_data.end_test_chunk()]


def _vs_swcheck_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """In VU-mode with memory tagging enabled, whose VS-mode keeps it disabled: with hedeleg[18] = 1, VS-mode takes
    the software-check exceptions of checktag and of a load with a mismatching pointer tag (vscause 18, vstval 4)."""
    name = MT_NAMES[mt_mode]
    ptr, val = test_data.int_regs.get_registers(2)
    lines = [
        comment_banner(
            f"cp_swcheck_to_vs (VU, {name})",
            "In VU-mode, with hedeleg[18] = 1: checktag and a load with a mismatching pointer tag raise a software-check\n"
            "exception that VS-mode takes (vscause 18, vstval 4). Record rd",
        ),
        "RVTEST_TSBI_GOTO_SMODE",
        f"LI(x{val}, {1 << 18:#x})",
        f"csrs hedeleg, x{val}",
        "RVTEST_TSBI_GOTO_VUMODE",
        *_check_pointer(ptr, val, mt_mode, SP_CHECKTAG_CHUNK, BAD_TAG[mt_mode]),
        test_data.add_testcase(f"VU_{name}_checktag_to_vs", "cp_swcheck_to_vs", cg),
        f"checktag x{ptr}, 0",
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"VU_{name}_ld_to_vs", "cp_swcheck_to_vs", cg),
        f"ld x{val}, 0(x{ptr})",
        write_sigupd(val, test_data),
        "RVTEST_TSBI_GOTO_SMODE",
        f"LI(x{val}, {1 << 18:#x})",
        f"csrc hedeleg, x{val}",
        "RVTEST_TSBI_GOTO_VUMODE",
    ]
    test_data.int_regs.return_registers([ptr, val])
    return lines


def _bare_check_setup(csr: str, env: str, ext: str, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """In the supervisor mode of a mode with Bare translation: its tag table base csr for the data chunks, the tags of
    _check_fill with BAD_CHUNKS, and memory tagging (env MT_MODE = mt_mode) with pointer masking (ext's smallest
    PMLEN)."""
    tags, t1, t2 = regs
    return [
        *_check_vitt(csr, mt_mode, regs),
        *_check_fill(mt_mode, tags, t1, BAD_CHUNKS),
        *_set_pmm(t1, ext),
        f"LI(x{t2}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{t1}, x{t1}, x{t2}",
        f"csrs {env}, x{t1}",
    ]


def _bare_check_tests(
    test_data: TestData, cg: str, mode: str, mt_mode: int, accesses: tuple[_Access, ...], fp: bool
) -> list[str]:
    """The tests of a mode with Bare translation and memory tagging enabled, whose exceptions a mode with memory
    tagging disabled takes: checktag around BAD_CHUNKS, each kind of load and store, misaligned ones over two chunks,
    ones with sp as the base register, the ordering of tag accesses, accesses that implicit tag checks do not cover,
    checktag with sp as rs1, and with 7-bit tags a memory tag with bit 7 set."""
    name = MT_NAMES[mt_mode]
    return [
        comment_banner(
            f"cp_checktag_mt_enabled ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, checktags whose chunks match, or which reach the\n"
            f"mismatching data chunks {BAD_CHUNKS[0]} or {BAD_CHUNKS[1]} at their first or last chunk, or with a\n"
            f"mismatching pointer tag: {SW_CHECK_TEXT}",
        ),
        *_checktag_case_tests(test_data, cg, mode, mt_mode, "cp_checktag_mt_enabled"),
        *_checked_access_tests(test_data, cg, mode, mt_mode, accesses, True),
        *_two_chunk_tests(test_data, cg, mode, mt_mode, True, fp=fp),
        *_sp_base_tests(test_data, cg, mode, mt_mode, fp=fp),
        *_order_tests(test_data, cg, mode, mt_mode, True),
        *_unchecked_access_tests(test_data, cg, mode, mt_mode),
        *_checktag_sp_tests(test_data, cg, mode, mt_mode, True),
        *(_tag_bit7_tests(test_data, cg, mode) if mt_mode == MT_TAG7 else []),
    ]


def _fault_tests(
    test_data: TestData, cg: str, mode: str, mt_mode: int, csr: str, goto_super: str, goto_mode: str, data: bool
) -> list[str]:
    """Faults in a mode with Bare translation, whose supervisor sets its tag table base csr. A tag table in the faulting
    region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD: checktag, a load and a store raise a load access fault at the tag.
    If data, a load from the first whole chunk of the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD and a store
    to that of RVMODEL_ACCESS_FAULT_ADDRESS_STORE whose tags match raise their access fault; with a mismatching pointer
    tag, a software-check exception. csr keeps the tag table base of the last case: the caller clears it."""
    name = MT_NAMES[mt_mode]
    fault_chunk = f"({LOAD_FAULT_TAG} & 0xfff)" if mt_mode == MT_TAG7 else f"(2 * ({LOAD_FAULT_TAG} & 0xfff) + 1)"
    ptr, val, tmp = test_data.int_regs.get_registers(3)
    lines = gated(
        [
            comment_banner(
                f"cp_checked_fault ({mode}, {name})",
                f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags and the tag table base in the faulting region of\n"
                f"{LOAD_FAULT}: checktag, a load and a store raise a load access fault at the tag",
            ),
            goto_super,
            load_constant(f"x{val}", f"{LOAD_FAULT_TAG} & ~0xfff"),
            f"csrw {csr}, x{val}",
            goto_mode,
            load_constant(f"x{ptr}", f"{_tag_field(GOOD_TAG[mt_mode], mt_mode):#x} | ({fault_chunk} << 4)"),
            test_data.add_testcase(f"{mode}_{name}_tag_fault_checktag", "cp_checktag_mt_enabled", cg),
            f"checktag x{ptr}, 0",
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase(f"{mode}_{name}_tag_fault_load", "cp_checked_fault", cg),
            f"ld x{val}, 8(x{ptr})",
            write_sigupd(val, test_data),
            test_data.add_testcase(f"{mode}_{name}_tag_fault_store", "cp_checked_fault", cg),
            f"sw x{val}, 4(x{ptr})",
        ],
        LOAD_FAULT_GATE,
    )
    if data:
        for region, store, gate in ((LOAD_FAULT, False, LOAD_FAULT_GATE), (STORE_FAULT, True, STORE_FAULT_GATE)):
            kind = "store" if store else "load"
            tags = test_data.int_regs.get_register()
            # The first whole chunk of the faulting region (of at least 128 bytes), so that the access has one tag,
            # without the bits of the pointer tag: pointer masking (PMLEN 7) zero-extends the address
            chunk = f"((({region}) + 15) & {(1 << 57) - 16:#x})"
            access = f"sd x{val}, 0(x{ptr})" if store else f"ld x{val}, 0(x{ptr})"
            lines += gated(
                [
                    comment_banner(
                        f"cp_checked_fault ({mode}, {name}, {kind})",
                        f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, a {kind} of the faulting region of {region}\n"
                        f"whose tag matches: {'store/AMO' if store else 'load'} access fault; with a mismatching pointer "
                        f"tag: {SW_CHECK_TEXT}",
                    ),
                    goto_super,
                    *_check_vitt(csr, mt_mode, (tags, val, tmp), chunk, label=False),
                    f"LI(x{val}, {(GOOD_TAG[mt_mode] if mt_mode == MT_TAG7 else GOOD_TAG[mt_mode] * 0x11):#x})",
                    f"sb x{val}, 0(x{tags})",
                    goto_mode,
                    load_constant(f"x{ptr}", f"{_tag_field(GOOD_TAG[mt_mode], mt_mode):#x} | {chunk}"),
                    f"LI(x{val}, {RD_CANARY:#x})",
                    test_data.add_testcase(f"{mode}_{name}_{kind}_access_fault", "cp_checked_fault", cg),
                    access,
                    write_sigupd(val, test_data),
                    load_constant(f"x{ptr}", f"{_tag_field(BAD_TAG[mt_mode], mt_mode):#x} | {chunk}"),
                    test_data.add_testcase(f"{mode}_{name}_{kind}_access_fault_mismatch", "cp_checked_fault", cg),
                    access,
                    write_sigupd(val, test_data),
                ],
                gate,
            )
            test_data.int_regs.return_register(tags)
    test_data.int_regs.return_registers([ptr, val, tmp])
    return lines


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "Sm", "Smvatag", "Smmpm"],
    march_extensions=CHECK_MARCH,
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_MMODE"],
)
def make_zimt_sm_checktag(test_data: TestData) -> list[TestChunk]:
    """Generate the checktag and implicit tag check tests in M-mode, with the tag table mvitt and pointer masking
    (mseccfg.PMM).

    The M-mode trap handler takes the exceptions of M-mode, and its loads and stores would be tag checked with memory
    tagging enabled in M-mode. So, with it, the tests raise no exception: checktag sweeps whose chunks match while the
    chunks right before and after them do not, each kind of load and store, misaligned ones over two chunks (only with
    hardware misaligned loads and stores, UDB_MISALIGNED_LDST, as they trap otherwise), ones with sp as the base
    register, and the ordering of tag accesses. Mismatches raise exceptions with mstatus.MPRV = 1 and MPP = S, whose
    loads and stores are checked with the MT_MODE and tag table of S-mode, while M-mode keeps memory tagging disabled;
    this needs S-mode pointer masking and tag table.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_Sm_cg"
    tc = test_data.begin_test_chunk("Sm_checktag")
    for mt_mode in (MT_TAG4, MT_TAG7):
        name = MT_NAMES[mt_mode]
        tags, t1, t2 = test_data.int_regs.get_registers(3)
        iteration = [
            comment_banner(
                f"checktag and implicit tag checks in M-mode ({name})",
                "mvitt puts the tags of the data chunks in the tag table, which all match, and pointer masking in M-mode",
            ),
            *_check_vitt("CSR_MVITT", mt_mode, (tags, t1, t2)),
            *_check_fill(mt_mode, tags, t1),
            *_set_pmm(t1, "SMMPM"),
            f"csrs mseccfg, x{t1}",
        ]
        test_data.int_regs.return_registers([tags, t1, t2])
        iteration += _checktag_sweep_tests(test_data, cg, mt_mode)
        mt = test_data.int_regs.get_register()
        mt_lines = ([f"csrs mseccfg, x{mt}"], [f"csrc mseccfg, x{mt}"])
        iteration += [
            f"LI(x{mt}, {mt_mode << MT_MODE_LSB:#x})",
            *_checked_access_tests(test_data, cg, "M", mt_mode, (*INT_ACCESSES, *FP_ACCESSES), False, mt_lines),
            *gated(_two_chunk_tests(test_data, cg, "M", mt_mode, False, mt_lines), MISALIGNED_LDST_GATE),
            *_sp_base_tests(test_data, cg, "M", mt_mode, mt_lines),
            *_order_tests(test_data, cg, "M", mt_mode, False, mt_lines),
            *_unchecked_access_tests(test_data, cg, "M", mt_mode, mt_lines, m_mode=True),
            *_checktag_sp_tests(test_data, cg, "M", mt_mode, False, mt_lines),
        ]
        test_data.int_regs.return_register(mt)
        iteration += gated(_m_checked_mprv_tests(test_data, cg, mt_mode), SM_MPRV_GATE)
        iteration += gated(_m_checked_mprv_v_tests(test_data, cg, mt_mode), SM_MPRV_V_GATE)
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    val, tmp = test_data.int_regs.get_registers(2)
    tc.code += [
        comment_banner("Restore", "mseccfg.PMM = 00 and mvitt = 0"),
        *_write_field("mseccfg", PMM_LSB, 0, val, tmp),
        "csrw CSR_MVITT, x0",
    ]
    test_data.int_regs.return_registers([val, tmp])
    tc.raw_data += [*_tag_table_data(), *_check_data()]
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "S", "Svatag", "Smnpm", "Sv39"],
    march_extensions=CHECK_MARCH,
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_zimt_s_checktag(test_data: TestData) -> list[TestChunk]:
    """Generate the checktag and implicit tag check tests in S-mode with the tag table svitts: first with Bare
    translation, then the checktag tests with Sv39 translation, and loads and stores, which address translation keeps
    from being tag checked.

    With Bare translation and memory tagging enabled in S-mode (menvcfg), the tests raise no exception, as in M-mode:
    the trap handler of S-mode would be tag checked, and so would the read of the trapping instruction by the trap
    handler of M-mode, which uses mstatus.MPRV = 1 with MPP = S. The mismatches of S-mode's loads and stores are those
    of Zimt_Sm_checktag with MPRV.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_S_cg"
    tc = test_data.begin_test_chunk("S_checktag")
    for mt_mode in (MT_TAG4, MT_TAG7):
        name = MT_NAMES[mt_mode]
        tags, t1, t2 = test_data.int_regs.get_registers(3)
        iteration = [
            comment_banner(
                f"checktag and implicit tag checks in S-mode with Bare translation ({name})",
                "svitts puts the tags of the data chunks in the tag table, and M-mode enables memory tagging and\n"
                "pointer masking in S-mode (menvcfg). The tests raise no exception, as in M-mode",
            ),
            *_check_vitt("CSR_SVITTS", mt_mode, (tags, t1, t2)),
            *_check_fill(mt_mode, tags, t1, BAD_CHUNKS),
            *_set_pmm(t1, "SMNPM"),
            f"LI(x{t2}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{t1}, x{t1}, x{t2}",
            tsbi_call(f"csrs menvcfg, x{t1}"),
        ]
        test_data.int_regs.return_registers([tags, t1, t2])
        accesses = (*INT_ACCESSES, *FP_ACCESSES)
        iteration += [
            *_checktag_case_tests(test_data, cg, "S", mt_mode, "cp_checktag_mt_enabled", exceptions=False),
            *_checked_access_tests(test_data, cg, "S", mt_mode, accesses, False),
            *gated(_two_chunk_tests(test_data, cg, "S", mt_mode, False), MISALIGNED_LDST_GATE),
            *_sp_base_tests(test_data, cg, "S", mt_mode),
            *_order_tests(test_data, cg, "S", mt_mode, False),
            *_unchecked_access_tests(test_data, cg, "S", mt_mode),
            *_checktag_sp_tests(test_data, cg, "S", mt_mode, False),
        ]
        val = test_data.int_regs.get_register()
        iteration += [
            f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            tsbi_call(f"csrc menvcfg, x{val}"),
            "csrw CSR_SVITTS, x0",
        ]
        test_data.int_regs.return_register(val)
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    a, b, c = test_data.int_regs.get_registers(3)
    regs = (a, b, c)
    tc.code += [
        comment_banner(
            "checktag in S-mode",
            f"svitts = {SETTAG_VA:#x}, mapped with 4 KiB pages to the tag table, and Sv39 translation, which also\n"
            "maps the test image with the boot page tables. svittu = 0, which S-mode does not use",
        ),
        *create_page_mapping(
            SV39,
            leaf_level=0,
            leaf_flags=PteFlags(execute=False),
            virtual_address=hex(SETTAG_VA),
            physical_address=TAG_TABLE,
            regs=regs,
        ),
        f"LI(x{a}, {SETTAG_VA:#x})",
        f"csrw CSR_SVITTS, x{a}",
        "csrw CSR_SVITTU, x0",
        "sfence.vma",
        SV39.satp_setup,
        "sfence.vma",
    ]
    test_data.int_regs.return_registers(list(regs))
    tc.code += _s_checktag_tests(test_data, cg, MT_TAG4)
    tc.code += _tag7(_s_checktag_tests(test_data, cg, MT_TAG7))
    tc.code += [
        comment_banner("Restore", "satp = 0 and svitts = 0"),
        "csrw satp, x0",
        "sfence.vma",
        "csrw CSR_SVITTS, x0",
    ]
    tc.raw_data += [*_tag_table_data(), *_check_data(), *lower_table_data(SV39)]
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "U", "S", "Svatag", "Ssnpm"],
    march_extensions=CHECK_MARCH,
    params=["MXLEN: 64"],
)
def make_zimt_u_checktag(test_data: TestData) -> list[TestChunk]:
    """Generate the checktag and implicit tag check tests in U-mode, with Bare translation and the tag table svittu.

    U-mode uses senvcfg.MT_MODE and senvcfg.PMM. S-mode, which serves the U-mode T-SBI calls and takes the
    exceptions, keeps memory tagging disabled and sets up the tags. Data chunks 20 and 23 have a mismatching tag. Then
    faults: a tag table in the faulting region of RVMODEL_ACCESS_FAULT_ADDRESS_LOAD, and loads and stores of the
    faulting regions whose tags match.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_U_cg"
    tc = test_data.begin_test_chunk("U_checktag")
    for mt_mode in (MT_TAG4, MT_TAG7):
        name = MT_NAMES[mt_mode]
        tags, t1, t2 = test_data.int_regs.get_registers(3)
        regs = (tags, t1, t2)
        iteration = [
            comment_banner(
                f"checktag and implicit tag checks in U-mode ({name})",
                "svittu puts the tags of the data chunks in the tag table, and S-mode enables memory tagging and\n"
                "pointer masking in U-mode (senvcfg)",
            ),
            "RVTEST_TSBI_GOTO_SMODE",
            "csrw CSR_SVITTS, x0",
            *_bare_check_setup("CSR_SVITTU", "senvcfg", "SSNPM", mt_mode, regs),
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_registers(list(regs))
        iteration += _bare_check_tests(test_data, cg, "U", mt_mode, (*INT_ACCESSES, *FP_ACCESSES), True)
        iteration += _fault_tests(
            test_data, cg, "U", mt_mode, "CSR_SVITTU", "RVTEST_TSBI_GOTO_SMODE", "RVTEST_TSBI_GOTO_UMODE", True
        )
        val = test_data.int_regs.get_register()
        iteration += [
            "RVTEST_TSBI_GOTO_SMODE",
            f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{val}",
            "csrw CSR_SVITTU, x0",
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_register(val)
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.raw_data += [*_tag_table_data(), *_check_data()]
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "H", "Svatag", "Ssnpm"],
    march_extensions=[*CHECK_MARCH, "H"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_zimt_h_checktag(test_data: TestData) -> list[TestChunk]:
    """Generate the checktag and implicit tag check tests in VS-mode and VU-mode, with the tag tables vsvitts and
    vsvittu.

    With Bare translation (vsatp and hgatp), VS-mode uses henvcfg.MT_MODE and henvcfg.PMM, VU-mode senvcfg.MT_MODE and
    senvcfg.PMM, which HS-mode sets, as the tags. HS-mode, which takes the exceptions, keeps memory tagging disabled,
    and so does VS-mode while VU-mode runs. The loads and stores are integer ones. Then, with Sv39, VS-mode checktags
    with guest translation, whose page faults and guest-page faults HS-mode takes, and a load that is not tag checked.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_H_cg"
    tc = test_data.begin_test_chunk("H_checktag")
    for mt_mode in (MT_TAG4, MT_TAG7):
        name = MT_NAMES[mt_mode]
        iteration = []
        for mode, csr, env in (("VS", "CSR_VSVITTS", "henvcfg"), ("VU", "CSR_VSVITTU", "senvcfg")):
            tags, t1, t2 = test_data.int_regs.get_registers(3)
            regs = (tags, t1, t2)
            iteration += [
                comment_banner(
                    f"checktag and implicit tag checks in {mode}-mode ({name})",
                    f"{csr[4:].lower()} puts the tags of the data chunks in the tag table, and HS-mode enables memory\n"
                    f"tagging and pointer masking in {mode}-mode ({env})",
                ),
                "csrw CSR_SVITTS, x0",
                "csrw CSR_SVITTU, x0",
                *_bare_check_setup(csr, env, "SSNPM", mt_mode, regs),
                f"RVTEST_TSBI_GOTO_{mode}MODE",
            ]
            test_data.int_regs.return_registers(list(regs))
            iteration += _bare_check_tests(test_data, cg, mode, mt_mode, INT_ACCESSES, False)
            if mode == "VU":
                iteration += _vs_swcheck_tests(test_data, cg, mt_mode)
            iteration += _fault_tests(
                test_data, cg, mode, mt_mode, csr, "RVTEST_TSBI_GOTO_SMODE", f"RVTEST_TSBI_GOTO_{mode}MODE", False
            )
            val = test_data.int_regs.get_register()
            iteration += [
                "RVTEST_TSBI_GOTO_SMODE",
                f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
                f"csrc {env}, x{val}",
                f"csrw {csr}, x0",
            ]
            test_data.int_regs.return_register(val)
        iteration += gated(_h_guest_checktag_tests(test_data, cg, mt_mode), "defined(SV39_SUPPORTED)")
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.raw_data += [*_tag_table_data(), *_check_data(), *guest_table_data()]
    return [test_data.end_test_chunk()]
