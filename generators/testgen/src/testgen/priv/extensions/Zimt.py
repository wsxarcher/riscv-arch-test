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
  behavior, and access from each mode), the software-check exception (cause 18) in medeleg, hedeleg and xcause, and
  mstatus.MTAG_I (Sm_csr, which sstatus does not show) and hstatus.MTAG_I (H_csr). T-SBI calls read the CSRs from
  M-mode or HS-mode after each write from a less privileged mode.
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
  the regular accesses that do not use sp as the base register are checked: the scalar loads and stores of data,
  LR/SC, AMOs, cbo.zero (its cache block) and vector loads and stores (each element), not prefetches, cbo.clean and
  cbo.flush. A mismatch raises a software-check exception (xtval 4) before the access, a fault of a tag load a load
  access fault. A data page has its
  tags in the tag table through the tag table base of the mode. Sm_checktag sweeps checktag between mismatching
  chunks, and checks each kind of load and store (integer, floating-point and compressed ones), misaligned ones over
  two chunks, ones through sp, the ordering with older tag stores, LR/SC, AMOs, cbo.zero and vector loads and stores,
  none of which may raise an exception with memory tagging enabled in M-mode, where the trap handler runs; then
  mismatches with MPRV, which check with S-mode's MT_MODE and tag table (also of LR/SC, AMOs, cbo.zero and vector
  elements), and not with mstatus.MTAG_I = 1. U_checktag and H_checktag (VS-mode, VU-mode) check the same, with
  mismatches, and tag loads and data accesses that fault; S_checktag and H_checktag check checktag with address
  translation, its load page faults, guest-page faults and access faults. mstatus.MTAG_I without MPRV (S_checktag,
  whose software-check exceptions M-mode then takes) and hstatus.MTAG_I (H_checktag) leave the loads and stores of
  S-mode, VS-mode and VU-mode checked. With first-stage address translation, only the pages whose leaf PTE has
  PTE.MTAG (a placeholder bit, rvtest_experimental.h) and X = 0 are tagged-data pages: S_checktag checks them, pages
  without it, with it and X = 1, user pages (which S-mode does not check, and U-mode does, through MPRV), loads and
  stores over two pages (with misaligned accesses performed byte by byte), also into an unmapped page, the
  tagcheck-exempt code pages (PTE.MTAG and X = 1, also execute-only), whose instructions' loads and stores are not
  checked, LR/SC and AMOs of a tagged-data page and of a page with PTE.MTAG and X = 1, and PTE.MTAG in a non-leaf PTE (a page fault) and with memory tagging disabled (ignored); H_checktag a
  VS-stage page with and without PTE.MTAG, VS-stage code pages with and without it, VS-stage user pages through MPRV
  with MPV = 1, and a G-stage leaf PTE with it (a guest-page fault). With the G stage only (vsatp Bare), H_checktag
  checks that loads and stores are checked, with load guest-page faults of their tag loads. H_checktag also checks
  HLV and HSV in HS-mode and HU-mode, with the memory tagging and tag table of their guest mode (hstatus.SPVP, and in
  HU-mode hstatus.VUMT_MODE), hstatus.MTAG_I and HLVX, which are not checked, and with two-stage translation, where
  they are checked in VS-stage tagged-data pages only and their tag loads take page faults and guest-page faults.

4-bit pointer tags are mandatory and 7-bit ones optional: the tests that need them are assembled only for a config
that defines UDB_ZIMT_POINTER_TAG_WIDTH_7 (ZIMT_POINTER_TAG_WIDTH_7 in the experimental_params of test_config.yaml).
Without them, MT_MODE = 11 is reserved, and the exclusion mask bits above 15 may be hardwired to zero.

The tests enable memory tagging only around code whose other loads and stores, such as the signature's, use sp: a
hart with tag tables (Svatag, Smvatag) checks the tags of the others. Only the settag and checktag tests set up a tag
table. Trap handlers run in modes where memory tagging stays disabled, or with translation, whose pages without
PTE.MTAG are not tag checked (the S-mode handlers of S_settag and S_checktag). No test takes a trap that writes a
nonzero mtinst or htinst while it uses a tagcheck-exempt code page or MTAG_I, whose deposit in mstatus.MTAG_I and
hstatus.MTAG_I depends on which traps write those (transformed instructions).

With first-stage address translation and memory tagging enabled, Svatag protects the tag storage of the effective
privilege mode: its regular accesses in its VITT range, mc_tag_va of its lowest to its highest virtual address, and its
settags whose chunks overlap that range raise access faults. The tests put each tag table base so that the range holds
no memory that the mode accesses, through page-table aliases where needed. S_checktag checks the range of S-mode at its
edges (loads, also through sp, stores, LR/SC, AMOs, cbo.zero and settag, after their page faults and tag checks, and
none with memory tagging disabled) and, through MPRV, that of U-mode (also with mstatus.MTAG_I, of vector loads and
stores, and of a user tagged-data page in it, whose tag check comes first, with a matching and a mismatching pointer
tag) and in U-mode itself; H_checktag, through MPRV with MPV = 1, those of VS-mode and VU-mode, those of VS-mode and
VU-mode themselves, and those of HLV and HSV in HS-mode with hstatus.MTAG_I, and in HU-mode with hstatus.VUMT_MODE, and
none of HLVX. U-mode and VU-mode run from a user alias of the code region, which the T-SBI mode switches relocate to.
Svatag depends on Svukte, and assumes the even split of the address space that it enforces: with Svukte, S_checktag
and H_checktag check that senvcfg.UKTE (hstatus.HUKTE for HLV in HU-mode) makes the tag accesses of U-mode and VU-mode,
also through MPRV and HLV, raise page faults at a tag address in the upper half. The ranges of M-mode
(Smvatag) and of Bare first-stage translation (Svatag) are implementation-defined: the tests whose regular accesses or
settags run with memory tagging enabled there take them as empty, and exist only without the extension or for a config
that declares them empty (SMVATAG_NO_M_MODE_VITT_RANGE, SVATAG_NO_BARE_VITT_RANGE in its experimental_params). They are
the _mt tests and the settag and checktag tests of M-mode and of Bare translation, also through MPRV and with the G
stage only (vsatp Bare).

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
# The VITT ranges of M-mode (Smvatag) and of the modes with Bare first-stage address translation (Svatag) are
# implementation-defined. The tests whose regular loads and stores or settags run with memory tagging enabled there
# take them as empty: they are assembled only without the extension or for a config that declares the range empty
# (SMVATAG_NO_M_MODE_VITT_RANGE, SVATAG_NO_BARE_VITT_RANGE in the experimental_params of test_config.yaml).
NO_M_VITT_RANGE = "!defined(SMVATAG_SUPPORTED) || defined(UDB_SMVATAG_NO_M_MODE_VITT_RANGE)"
NO_BARE_VITT_RANGE = "!defined(SVATAG_SUPPORTED) || defined(UDB_SVATAG_NO_BARE_VITT_RANGE)"
# rs1 of addtag, checktag and settag: a pointer with a nonzero pointer tag in bits 63:57
TAGGED_POINTER = 0x5A00_0000_8000_1230
# Written to rd before each instruction that writes rd, so that the signature shows the write
RD_CANARY = 0xA5A5_A5A5_A5A5_A5A5

MT_MODE_LSB = 34  # MT_MODE: bits 35:34 of mseccfg, menvcfg, senvcfg and henvcfg
VUMT_MODE_LSB = 50  # hstatus.VUMT_MODE: bits 51:50
# MTAG_I of mstatus, which with MPRV = 1 makes loads and stores unchecked, and of hstatus, which makes HLV and HSV
# unchecked
MSTATUS_MTAG_I_BIT = 40
HSTATUS_MTAG_I_BIT = 10
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
    7-bit pointer tags. The field holds 11 only with them. The field is cleared before each record, so that with
    mseccfg the signature store does not run with memory tagging enabled in M-mode (NO_M_VITT_RANGE).
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
            cases += [f"LI(x{tmp}, {0b11 << lsb:#x})", f"csrc {csr}, x{tmp}", write_sigupd(val, test_data)]
        lines += _tag7(cases) if old == MT_TAG7 else cases
    lines.append(f"csrw {csr}, x{save}")
    test_data.int_regs.return_registers([save, val, tmp])
    return lines


def _mtag_i_write_tests(test_data: TestData, cg: str, csr: str, bit: int, view: str | None = None) -> list[str]:
    """Set and clear the MTAG_I bit of csr with csrs and csrc, and record it after each; while it is set, also record
    that bit of view (sstatus, which does not include mstatus.MTAG_I) if S-mode exists."""
    mask, val = test_data.int_regs.get_registers(2)

    def record(source: str) -> list[str]:
        return [
            f"csrr x{val}, {source}",
            f"srli x{val}, x{val}, {bit}",
            f"andi x{val}, x{val}, 1",
            write_sigupd(val, test_data),
        ]

    lines = [
        comment_banner(
            f"cp_mtag_i_write ({csr})",
            f"Set and clear {csr}.MTAG_I (bit {bit}) with csrs and csrc. Record it"
            + (f", and bit {bit} of {view} while it is set" if view else ""),
        ),
        f"LI(x{mask}, {1 << bit:#x})",
        test_data.add_testcase(f"{csr}_mtag_i_set", "cp_mtag_i_write", cg),
        f"csrs {csr}, x{mask}",
        *record(csr),
    ]
    if view:
        lines += gated(
            [test_data.add_testcase(f"{view}_mtag_i", "cp_mtag_i_view", cg), *record(view)], "defined(S_SUPPORTED)"
        )
    lines += [
        test_data.add_testcase(f"{csr}_mtag_i_clear", "cp_mtag_i_write", cg),
        f"csrc {csr}, x{mask}",
        *record(csr),
    ]
    test_data.int_regs.return_registers([mask, val])
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
# Smstateen and Ssstateen: mstateen0.MT and hstateen0.MT
# ---------------------------------------------------------------------------------------------------------------

# The CSRs that mstateen0.MT gates below M-mode, and hstateen0.MT (the S-level ones) in VS-mode: (name, macro, level,
# preprocessor condition for the CSR to exist beyond S-mode). The level is "s" for the S-level CSRs and "h" for the
# H-level ones.
STATEEN_MT_CSRS = (
    ("senvmtagexclude0", "CSR_SENVMTAGEXCLUDE0", "s", None),
    ("senvmtagexclude1", "CSR_SENVMTAGEXCLUDE1", "s", None),
    ("svitts", "CSR_SVITTS", "s", "defined(SVATAG_SUPPORTED)"),
    ("svittu", "CSR_SVITTU", "s", "defined(SVATAG_SUPPORTED)"),
    ("henvmtagexclude0", "CSR_HENVMTAGEXCLUDE0", "h", "defined(H_SUPPORTED)"),
    ("henvmtagexclude1", "CSR_HENVMTAGEXCLUDE1", "h", "defined(H_SUPPORTED)"),
    ("vsvitts", "CSR_VSVITTS", "h", "defined(H_SUPPORTED) && defined(SVATAG_SUPPORTED)"),
    ("vsvittu", "CSR_VSVITTU", "h", "defined(H_SUPPORTED) && defined(SVATAG_SUPPORTED)"),
)
# The M-level CSRs of Zimt and Smvatag (level "m"), which the MT bits do not gate: M-mode accesses them with them as
# well, in each state of the MT bits (the other tests access them with both bits set)
STATEEN_MT_M_CSRS = (
    ("mmtagexclude0", "CSR_MMTAGEXCLUDE0", "m", None),
    ("mmtagexclude1", "CSR_MMTAGEXCLUDE1", "m", None),
    ("menvmtagexclude0", "CSR_MENVMTAGEXCLUDE0", "m", None),
    ("menvmtagexclude1", "CSR_MENVMTAGEXCLUDE1", "m", None),
    ("mvitt", "CSR_MVITT", "m", "defined(SMVATAG_SUPPORTED)"),
)
# Values written to them in M-mode before the accesses of each mode, so that their reads are known, and the values
# that the accesses write, which M-mode reads back after them, so that a write that is performed shows in the CSR it
# reaches (vsvitts and vsvittu for svitts and svittu in VS-mode) and one that traps in none: tag table bases 4 KiB
# aligned, and exclusion masks that every hart keeps (bits 15:1 of a low CSR; 0 in a high one, whose bits are
# hardwired to zero without 7-bit tags, and STATEEN_MT_TAG7_VALUES with them)
STATEEN_MT_VALUES = {
    "senvmtagexclude0": 0x5A02,
    "senvmtagexclude1": 0,
    "svitts": 0x8000_1000,
    "svittu": 0x8000_2000,
    "henvmtagexclude0": 0x3C04,
    "henvmtagexclude1": 0,
    "vsvitts": 0x8000_3000,
    "vsvittu": 0x8000_4000,
    "mmtagexclude0": 0x1E02,
    "mmtagexclude1": 0,
    "menvmtagexclude0": 0x3302,
    "menvmtagexclude1": 0,
    "mvitt": 0x8000_9000,
}
STATEEN_MT_WRITTEN = {
    "senvmtagexclude0": 0x0A50,
    "senvmtagexclude1": 0,
    "svitts": 0x8000_5000,
    "svittu": 0x8000_6000,
    "henvmtagexclude0": 0x0C30,
    "henvmtagexclude1": 0,
    "vsvitts": 0x8000_7000,
    "vsvittu": 0x8000_8000,
    "mmtagexclude0": 0x2184,
    "mmtagexclude1": 0,
    "menvmtagexclude0": 0x0CC8,
    "menvmtagexclude1": 0,
    "mvitt": 0x8000_A000,
}
# With 7-bit tags (TAG7), the high exclusion masks hold the bits of the tags 64-127: (known value, written value)
STATEEN_MT_TAG7_VALUES = {
    "senvmtagexclude1": (0x0000_0F00_0000_00F0, 0x00F0_0000_0F00_0000),
    "henvmtagexclude1": (0x0000_3C00_0000_0C00, 0x0C00_0000_3C00_0000),
    "mmtagexclude1": (0x0000_0300_0000_0030, 0x0030_0000_0300_0000),
    "menvmtagexclude1": (0x0000_C000_0000_000C, 0x000C_0000_C000_0000),
}
STATEEN_MT_MODES = ("M", "S", "U", "VS", "VU")
# The states of the MT bits that the accesses run in: (name, mstateen0.MT, hstateen0.MT, modes). hstateen0.MT is
# written while mstateen0.MT = 1, as it is read-only zero while mstateen0.MT = 0: with mstateen0.MT = 0, it was written
# 1 (m0_h1) or 0 (m0_h0) before, which only VS-mode and VU-mode could tell apart (an illegal instruction exception in
# both, which a hart that decides on hstateen0.MT alone would make a virtual one in m0_h0)
STATEEN_MT_STATES = (
    ("m0_h1", 0, 1, STATEEN_MT_MODES),
    ("m0_h0", 0, 0, ("VS", "VU")),
    ("m1_h0", 1, 0, STATEEN_MT_MODES),
    ("m1_h1", 1, 1, STATEEN_MT_MODES),
)
STATEEN_MT_MODE_GUARDS = {"VS": "defined(H_SUPPORTED)", "VU": "defined(H_SUPPORTED)"}


def _stateen_mt_outcome(mode: str, level: str, m: int, h: int) -> tuple[str, str]:
    """The exception that an access to a CSR of level raises in mode with mstateen0.MT = m and hstateen0.MT = h, and
    the coverpoint of the access."""
    if level == "m":
        return "none", "cp_stateen_mt_m_level"
    if mode == "M":
        return "none", "cp_stateen_mt_m"
    if mode == "U":
        return "illegal instruction", "cp_stateen_mt_u"
    if not m:
        return "illegal instruction", "cp_stateen_mt_s_off" if mode == "S" else "cp_stateen_mt_v_off"
    if mode == "S":
        return "none", "cp_stateen_mt_s_on"
    if mode == "VU":
        return "virtual instruction", "cp_stateen_mt_vu_on"
    if level == "h":
        return "virtual instruction", "cp_stateen_mt_vs_hcsr"
    return ("none", "cp_stateen_mt_vs_h_on") if h else ("virtual instruction", "cp_stateen_mt_vs_h_off")


def _stateen_mt_warl_tests(test_data: TestData, cg: str) -> list[str]:
    """Set and clear mstateen0.MT, and hstateen0.MT with mstateen0.MT = 1 and = 0, recording the bit after each write.

    hstateen0.MT reads 0 once mstateen0.MT is cleared while it is 1. Whether it reads 1 again once mstateen0.MT is set
    again is not specified, so it is cleared then, and set while mstateen0.MT = 0 after it was cleared, so a hart
    that keeps it while it reads as zero shows the same.
    """
    mt, val = test_data.int_regs.get_registers(2)

    def record(csr: str) -> list[str]:
        return [f"csrr x{val}, {csr}", f"and x{val}, x{val}, x{mt}", write_sigupd(val, test_data)]

    lines = [
        comment_banner(
            "cp_mstateen0_mt_write, cp_hstateen0_mt_write, cp_hstateen0_mt_masked",
            "Set and clear mstateen0.MT (bit 53, the placeholder of the Sail model) and record it: writable.\n"
            "With H, set and clear hstateen0.MT with mstateen0.MT = 1 (writable); clear mstateen0.MT while\n"
            "hstateen0.MT = 1 (read-only zero); then set it with mstateen0.MT = 0 (read-only zero) and record it",
        ),
        f"LI(x{mt}, MSTATEEN0_MT)",
    ]
    for op, state in (("csrc", "clear"), ("csrs", "set")):
        lines += [
            test_data.add_testcase(f"mstateen0_mt_{state}", "cp_mstateen0_mt_write", cg),
            f"{op} mstateen0, x{mt}",
            *record("mstateen0"),
        ]

    def write_h(op: str, state: str) -> list[str]:
        return [
            test_data.add_testcase(f"hstateen0_mt_{state}", "cp_hstateen0_mt_write", cg),
            f"{op} hstateen0, x{mt}",
            *record("hstateen0"),
        ]

    h_lines = [
        *write_h("csrc", "clear"),
        *write_h("csrs", "set"),
        f"csrc mstateen0, x{mt}    # with hstateen0.MT = 1, which reads 0 then",
        test_data.add_testcase("hstateen0_mt_masked", "cp_hstateen0_mt_masked", cg),
        *record("hstateen0"),
        f"csrs mstateen0, x{mt}    # hstateen0.MT reads 1 or 0: not recorded",
        *write_h("csrc", "clear_again"),
    ]
    h_lines += [
        f"csrc mstateen0, x{mt}    # mstateen0.MT = 0: hstateen0.MT reads 0",
        test_data.add_testcase("hstateen0_mt_set_m0", "cp_hstateen0_mt_write", cg),
        f"csrs hstateen0, x{mt}",
        *record("hstateen0"),
        f"csrs mstateen0, x{mt}",
        f"csrs hstateen0, x{mt}",
    ]
    lines += gated(h_lines, "defined(H_SUPPORTED)")
    test_data.int_regs.return_registers([mt, val])
    return lines


# The set and clear forms of the accesses, on one S-level and one H-level CSR: csrrs and csrrc with rs1 != x0 (bit 8),
# csrrwi, and csrrsi and csrrci with uimm != 0. Performed after the csrrw, they leave 2 (bit 1) in the CSR
STATEEN_MT_FORM_CSRS = ("senvmtagexclude0", "henvmtagexclude0")
STATEEN_MT_FORMS = (
    ("csrrs", "csrrs x{reg}, {macro}, x{bits}"),
    ("csrrc", "csrrc x{reg}, {macro}, x{bits}"),
    ("csrrwi", "csrrwi x{reg}, {macro}, 4"),
    ("csrrsi", "csrrsi x{reg}, {macro}, 2"),
    ("csrrci", "csrrci x{reg}, {macro}, 4"),
)


def _stateen_mt_value(reg: int, name: str, written: bool) -> list[str]:
    """x{reg} = the known (STATEEN_MT_VALUES) or written (STATEEN_MT_WRITTEN) value of the CSR name."""
    value = (STATEEN_MT_WRITTEN if written else STATEEN_MT_VALUES)[name]
    if name not in STATEEN_MT_TAG7_VALUES:
        return [f"LI(x{reg}, {value:#x})"]
    return [
        f"#ifdef {TAG7}",
        f"LI(x{reg}, {STATEEN_MT_TAG7_VALUES[name][written]:#x})",
        "#else",
        f"LI(x{reg}, {value:#x})",
        "#endif",
    ]


def _stateen_mt_access_tests(test_data: TestData, cg: str) -> list[str]:
    """Read and write each CSR that the MT bits gate from M, S, U, VS and VU-mode, in each state of the MT bits.

    Before the accesses of each mode, M-mode writes known values to the CSRs. Each access is a csrr, whose register
    starts with a value that a trapping read leaves, then a csrrw of another value, which a trapping write leaves in
    its register; the trap signature records the illegal and virtual instruction exceptions. After them, M-mode reads
    every CSR back, so the signature shows which writes were performed and which CSR each one reached.
    """
    mt, reg, bits = test_data.int_regs.get_registers(3)
    lines = [
        comment_banner(
            "cp_stateen_mt_*",
            "Before the accesses of each mode, write known values to the CSRs that mstateen0.MT gates (from\n"
            "M-mode); then read each one and write another value to it from M, S, U, VS and VU-mode, with\n"
            "mstateen0.MT = 0 (and hstateen0.MT written 1 before; VS and VU-mode also with it written 0 before),\n"
            "with mstateen0.MT = 1 and hstateen0.MT = 0, and with both 1, and read them all back from M-mode.\n"
            "M-mode: no exception. Below M-mode with mstateen0.MT = 0, and\n"
            "U-mode: illegal instruction. S-mode with mstateen0.MT = 1: no exception. VS-mode with mstateen0.MT = 1:\n"
            "virtual instruction for the H-level CSRs and, with hstateen0.MT = 0, the S-level ones, which it\n"
            "accesses with hstateen0.MT = 1 (svitts and svittu reach vsvitts and vsvittu). VU-mode with\n"
            "mstateen0.MT = 1: virtual instruction. A write that traps changes no CSR. M-mode also accesses the\n"
            "M-level CSRs (mmtagexclude0/1, menvmtagexclude0/1, mvitt), which the MT bits do not gate. The set and\n"
            "clear forms (csrrs, csrrc, csrrwi, csrrsi, csrrci) access senvmtagexclude0 and henvmtagexclude0 too",
        ),
        f"LI(x{mt}, MSTATEEN0_MT)",
    ]
    for state, m, h, modes in STATEEN_MT_STATES:
        lines += [
            f"\n# mstateen0.MT = {m}, hstateen0.MT {'= ' + str(h) if m else 'written ' + str(h) + ' before'}",
            f"csrs mstateen0, x{mt}",
            *gated([f"{'csrs' if h else 'csrc'} hstateen0, x{mt}"], "defined(H_SUPPORTED)"),
        ]
        if not m:
            lines.append(f"csrc mstateen0, x{mt}")
        for mode in modes:
            known, body, readback = [f"\n# {mode}-mode: known values"], [], [f"\n# {mode}-mode: read back"]
            for name, macro, level, guard in STATEEN_MT_CSRS + (STATEEN_MT_M_CSRS if mode == "M" else ()):
                outcome, coverpoint = _stateen_mt_outcome(mode, level, m, h)
                known += gated([*_stateen_mt_value(reg, name, written=False), f"csrw {macro}, x{reg}"], guard)
                body += gated(
                    [
                        f"LI(x{reg}, 42)    # a trapping read leaves it",
                        test_data.add_testcase(f"{mode}_{state}_{name}_read", coverpoint, cg),
                        f"csrr x{reg}, {macro}    # {outcome}",
                        write_sigupd(reg, test_data),
                        *_stateen_mt_value(reg, name, written=True),
                        test_data.add_testcase(f"{mode}_{state}_{name}_write", coverpoint, cg),
                        f"csrrw x{reg}, {macro}, x{reg}    # {outcome}; a trapping write leaves x{reg}",
                        write_sigupd(reg, test_data),
                    ],
                    guard,
                )
                if name in STATEEN_MT_FORM_CSRS:
                    forms = [f"LI(x{bits}, 0x100)"]
                    for form, instr in STATEEN_MT_FORMS:
                        forms += [
                            f"LI(x{reg}, 42)",
                            test_data.add_testcase(f"{mode}_{state}_{name}_{form}", "cp_stateen_mt_forms", cg),
                            f"{instr.format(reg=reg, macro=macro, bits=bits)}    # {outcome}",
                            write_sigupd(reg, test_data),
                        ]
                    body += gated(forms, guard)
                readback += gated([f"csrr x{reg}, {macro}", write_sigupd(reg, test_data)], guard)
            if mode != "M":
                body = [f"\nRVTEST_TSBI_GOTO_{mode}MODE", *body, "\nRVTEST_TSBI_GOTO_MMODE"]
            lines += gated([*known, *body, *readback], STATEEN_MT_MODE_GUARDS.get(mode))
    lines += [f"csrs mstateen0, x{mt}", *gated([f"csrs hstateen0, x{mt}"], "defined(H_SUPPORTED)")]
    for _, macro, _, guard in STATEEN_MT_CSRS + STATEEN_MT_M_CSRS:
        lines += gated([f"csrw {macro}, x0"], guard)
    test_data.int_regs.return_registers([mt, reg, bits])
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


# The M-mode CSRs of _configure and _restore
M_MODE_CSRS = ("menvcfg", *MTAGEXCLUDE["m"], *MTAGEXCLUDE["menv"])


def _via_tsbi(lines: list[str]) -> list[str]:
    """lines of S-mode code, with their CSR instructions on M-mode CSRs (M_MODE_CSRS) made T-SBI calls."""
    return [
        tsbi_call(line)
        if line.startswith("csr") and set(line.replace(",", " ").split()[1:]) & set(M_MODE_CSRS)
        else line
        for line in lines
    ]


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
# tag table base is a multiple of 4 KiB with both tag widths. The zero-extended one depends on PMLEN. The
# sign-extended one is the lowest Sv39 address of the upper half: its tags start the S-mode tag storage range, which
# then lies above the test image, where S-mode accesses would raise access faults.
SIGN_EXTENDED_BASE = 0xFFFF_FFC0_0000_0000
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


def _record_tags(
    test_data: TestData, base: int, val: int, window: list[int], base_offset: int = 0, label: str | None = None
) -> list[str]:
    """Record the doublewords of window, labeled with label (default: the current testcase); x{base} holds the tag
    table base plus base_offset."""
    return [
        line
        for offset in window
        for line in (f"ld x{val}, {offset - base_offset}(x{base})", write_sigupd(val, test_data, label=label))
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
    g_stage = []
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
        g_stage += _h_guest_settag_case(
            test_data, cg, mt_mode, case, "cp_settag_g_stage", int(SV39X4.data_va, 16), setup
        )
    g_stage += _h_guest_settag_case(
        test_data, cg, mt_mode, "g_stage_gpa_too_wide", "cp_settag_g_stage", H_GPA_TOO_WIDE, []
    )
    # The G stage only: VS-mode's first-stage translation is Bare
    lines += gated(g_stage, NO_BARE_VITT_RANGE)
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
# ...also over two pages: performed byte by byte (MISALIGNED_SPLIT_STRATEGY sequential_bytes), so that the access of
# each page is translated, and a fault on the second page is reported at its first byte
PAGE_CROSSING_GATE = "defined(UDB_MISALIGNED_LDST) && defined(UDB_MISALIGNED_SPLIT_STRATEGY_SEQUENTIAL_BYTES)"
# The parts of the S-mode and HS-mode tests that run in M-mode (RVTEST_TSBI_GOTO_MMODE) and take traps there: a DUT
# without standard M-mode runs the rest, and their coverpoints are in Zimt_Sm_cg, which EXCLUDE_SM drops
STANDARD_SM_GATE = "defined(STANDARD_SM_SUPPORTED)"
# The data chunk of the accesses that implicit tag checks do not cover, which starts a cache block of 64 bytes
UNCHECKED_CHUNK = 52
# The data chunks of the regular accesses that implicit tag checks cover besides loads and stores (cp_checked_regular):
# LR/SC on the first doubleword of REGULAR_CHUNK, amoadd.d on its second one and amoswap.w on the next chunk; vector
# loads and stores on VECTOR_CHUNK and the next one (stride 16); and cbo.zero on the cache block of 64 bytes from
# CBO_ZERO_CHUNK
REGULAR_CHUNK = 56
VECTOR_CHUNK = 58
CBO_ZERO_CHUNK = 60
# The doublewords of the cache block of cbo.zero before it, so that a cbo.zero that is not performed shows
CBO_ZERO_PATTERN = 0x5A5A_5A5A_5A5A_5A5A
# The doublewords of VECTOR_CHUNK and the next chunk before the MPRV vector accesses
VECTOR_PATTERN = (0x5050505050505050, 0x5151515151515151, 0x5252525252525252, 0x5353535353535353)
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
    label) is in the page at table (the first tag table page by default, another one of its pages, or a constant
    address): csr = table - its tag offset rounded down to 4 KiB. x{regs[0]} = the address of that tag."""
    tags, t1, t2 = regs
    return [
        f"LA(x{t1}, {base})" if label else load_constant(f"x{t1}", base),
        f"srli x{t1}, x{t1}, {4 if mt_mode == MT_TAG7 else 5}",
        f"srli x{t2}, x{t1}, 12",
        f"slli x{t2}, x{t2}, 12",
        f"sub x{t1}, x{t1}, x{t2}",
        f"LA(x{tags}, {table})" if table.startswith(TAG_TABLE) else load_constant(f"x{tags}", table),
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


def _fill_via_sp(ptr: int, val: int, save: int, values: tuple[tuple[int, int], ...]) -> list[str]:
    """Store each (offset, value) of values as the doubleword at x{ptr} + offset, through sp as _record_via_sp."""
    lines = [f"mv x{save}, sp", f"slli sp, x{ptr}, 7", "srli sp, sp, 7"]
    for offset, value in values:
        lines += [f"LI(x{val}, {value:#x})", f"sd x{val}, {offset}(sp)"]
    return [*lines, f"mv sp, x{save}"]


def _record_vreg(test_data: TestData, val: int, vreg: int, elements: int = 2) -> list[str]:
    """Record the first elements (1 or 2) 64-bit elements of v{vreg}, element 1 through v25 (vl = 2)."""
    lines = [
        ".option push",
        ".option arch, +v",
        f"vmv.x.s x{val}, v{vreg}",
        ".option pop",
        write_sigupd(val, test_data),
    ]
    if elements > 1:
        lines += [
            ".option push",
            ".option arch, +v",
            f"vslidedown.vi v25, v{vreg}, 1",
            f"vmv.x.s x{val}, v25",
            ".option pop",
            write_sigupd(val, test_data),
        ]
    return lines


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
    """Accesses that implicit tag checks do not cover, of data chunk UNCHECKED_CHUNK, whose tag is GOOD_TAG, with a
    pointer tag that does not match: prefetch.r and prefetch.w through a pointer with BAD_TAG and, in M-mode, cbo.clean
    and cbo.flush and HLV/HSV through one without a pointer tag (pointer masking need not apply to them). HLV/HSV are
    checked with the memory tagging of their guest mode, not M-mode's: VU-mode's (hstatus.SPVP = 0), senvcfg.MT_MODE,
    which stays disabled here. No exception. In M-mode, record the value that hlv.d loads and memory (the prefetches,
    which access no memory, record nothing)."""
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
            "pointer tag that does not match: prefetches"
            + (
                ", cbo.clean, cbo.flush and HLV/HSV (whose VU-mode memory\ntagging is disabled). No exception. Record "
                "the value that hlv.d loads and memory"
                if m_mode
                else ". No exception"
            ),
        ),
        *gated(
            [
                *_check_pointer(ptr, tmp, mt_mode, UNCHECKED_CHUNK, BAD_TAG[mt_mode]),
                *accesses(
                    [("prefetch_r", f"prefetch.r 0(x{ptr})"), ("prefetch_w", f"prefetch.w 0(x{ptr})")], "+zicbop"
                ),
            ],
            "defined(ZICBOP_SUPPORTED)",
        ),
    ]
    if m_mode:
        lines += [
            f"LA(x{ptr}, {base})",
            # Each record is inside the gate of the testcase it is labeled with
            *gated(
                [
                    *accesses([("cbo_clean", f"cbo.clean (x{ptr})"), ("cbo_flush", f"cbo.flush (x{ptr})")], "+zicbom"),
                    *_record_via_sp(test_data, ptr, 0, val, save),
                ],
                "defined(ZICBOM_SUPPORTED)",
            ),
            # V-mode loads and stores with Bare translation (vsatp and hgatp) in the VU-mode of hstatus.SPVP = 0, whose
            # memory tagging (senvcfg.MT_MODE) is disabled: M-mode's does not apply to them
            *gated(
                [
                    "csrw CSR_VSATP, x0",
                    "csrw CSR_HGATP, x0",
                    f"LI(x{tmp}, {1 << 8:#x})    # hstatus.SPVP",
                    f"csrc CSR_HSTATUS, x{tmp}",
                    f"LI(x{val}, 0x0123456789abcdef)",
                    *accesses([("hsv", f"hsv.d x{val}, (x{ptr})"), ("hlv", f"hlv.d x{tmp}, (x{ptr})")], "+h"),
                    write_sigupd(tmp, test_data),
                    *_record_via_sp(test_data, ptr, 0, val, save),
                ],
                "defined(H_SUPPORTED)",
            ),
        ]
    test_data.int_regs.return_registers([ptr, val, tmp, save])
    return lines


def _regular_access(
    test_data: TestData,
    cg: str,
    coverpoint: str,
    case: str,
    arch: str,
    instructions: list[str],
    mt: tuple[list[str], list[str]] = NO_MT,
) -> list[str]:
    """instructions, assembled with the extensions arch between the lines of mt, the first one labeled as the testcase
    case of coverpoint."""
    mt_on, mt_off = mt
    return [
        ".option push",
        f".option arch, {arch}",
        *mt_on,
        test_data.add_testcase(case, coverpoint, cg),
        *instructions,
        *mt_off,
        ".option pop",
    ]


def _checked_regular_tests(
    test_data: TestData,
    cg: str,
    mode: str,
    mt_mode: int,
    mismatch: bool,
    mt: tuple[list[str], list[str]] = NO_MT,
    m_mode: bool = False,
) -> list[str]:
    """The regular accesses that implicit tag checks cover besides loads and stores, of data chunks REGULAR_CHUNK and
    the next one, whose tag is GOOD_TAG: with the matching pointer tag an LR/SC pair (which succeeds), amoadd.d and
    amoswap.w are performed, and cbo.zero of the cache block of CBO_ZERO_CHUNK (filled with CBO_ZERO_PATTERN), through a
    pointer into its second chunk; and, if mismatch, with BAD_TAG LR, SC (without a reservation, and after an LR through
    the matching pointer tag), the AMOs and cbo.zero raise a software-check exception that writes neither rd nor
    memory. In M-mode (m_mode) also vector loads and stores (unit-stride, masked, strided, indexed and fault-only-first)
    of VECTOR_CHUNK and the next one, with the matching pointer tag. Record rd and memory."""
    name = MT_NAMES[mt_mode]
    ptr, good, val, tmp, save = test_data.int_regs.get_registers(5)

    def access(case: str, arch: str, instructions: list[str]) -> list[str]:
        return _regular_access(test_data, cg, "cp_checked_regular", f"{mode}_{name}_{case}", arch, instructions, mt)

    lines = [
        comment_banner(
            f"cp_checked_regular ({mode}, {name})",
            f"In {mode}-mode with {TAG_BITS[mt_mode]}-bit tags, the regular accesses that implicit tag checks cover\n"
            "besides loads and stores, with the matching pointer tag: an LR/SC pair, amoadd.d, amoswap.w, cbo.zero"
            + (" and\nvector loads and stores" if m_mode else "")
            + ", performed"
            + (
                f". Then with a mismatching pointer tag: LR, SC (without\na reservation, and after an LR with the "
                f"matching pointer tag), the AMOs and cbo.zero: {SW_CHECK_TEXT},\nrd and memory unchanged"
                if mismatch
                else ""
            )
            + ". Record rd and memory",
        ),
    ]
    lr_sc = [
        *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK, GOOD_TAG[mt_mode]),
        f"LI(x{val}, {RD_CANARY:#x})",
        f"LI(x{save}, 0x0123456789abcdef)",
        *access("lr_sc", "+zalrsc", [f"lr.d x{val}, (x{good})", f"sc.d x{tmp}, x{save}, (x{good})"]),
        write_sigupd(val, test_data),
        write_sigupd(tmp, test_data),
        *_record_via_sp(test_data, good, 0, val, save),
    ]
    amo = [
        *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK, GOOD_TAG[mt_mode], 8),
        f"LI(x{val}, {RD_CANARY:#x})",
        f"LI(x{tmp}, 0x0101010101010101)",
        *access("amoadd_d", "+zaamo", [f"amoadd.d x{val}, x{tmp}, (x{good})"]),
        write_sigupd(val, test_data),
        *_record_via_sp(test_data, good, 0, val, save),
        *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK + 1, GOOD_TAG[mt_mode], 4),
        f"LI(x{val}, {RD_CANARY:#x})",
        f"LI(x{tmp}, 0x55aa55aa)",
        *access("amoswap_w", "+zaamo", [f"amoswap.w x{val}, x{tmp}, (x{good})"]),
        write_sigupd(val, test_data),
        *_record_via_sp(test_data, good, -4, val, save),
    ]
    if mismatch:
        lr_sc += [
            *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, BAD_TAG[mt_mode]),
            f"LI(x{val}, {RD_CANARY:#x})",
            *access("lr_mismatch", "+zalrsc", [f"lr.d x{val}, (x{ptr})"]),
            write_sigupd(val, test_data),
            f"LI(x{tmp}, {RD_CANARY:#x})",
            f"LI(x{save}, 0xfedcba9876543210)",
            *access("sc_mismatch", "+zalrsc", [f"sc.d x{tmp}, x{save}, (x{ptr})"]),
            write_sigupd(tmp, test_data),
            *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK, GOOD_TAG[mt_mode]),
            f"LI(x{tmp}, {RD_CANARY:#x})",
            *access("lr_sc_mismatch", "+zalrsc", [f"lr.d x{val}, (x{good})", f"sc.d x{tmp}, x{save}, (x{ptr})"]),
            write_sigupd(val, test_data),
            write_sigupd(tmp, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
        ]
        amo += [
            *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, BAD_TAG[mt_mode], 8),
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, 0x0101010101010101)",
            *access("amoadd_d_mismatch", "+zaamo", [f"amoadd.d x{val}, x{tmp}, (x{ptr})"]),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, ptr, 0, val, save),
            *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK + 1, BAD_TAG[mt_mode], 4),
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, 0x33cc33cc)",
            *access("amoswap_w_mismatch", "+zaamo", [f"amoswap.w x{val}, x{tmp}, (x{ptr})"]),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, ptr, -4, val, save),
        ]
    lines += [*gated(lr_sc, "defined(ZALRSC_SUPPORTED)"), *gated(amo, "defined(ZAAMO_SUPPORTED)")]

    def cbo_zero(case: str, tag: int) -> list[str]:
        """The cache block of CBO_ZERO_CHUNK filled with CBO_ZERO_PATTERN, then cbo.zero through a pointer into its second
        chunk with the pointer tag tag. Record the block."""
        return [
            *_check_pointer(ptr, tmp, mt_mode, CBO_ZERO_CHUNK + 1, tag, 4),
            f"LA(x{tmp}, {CHECK_DATA} + {16 * CBO_ZERO_CHUNK})",
            *_fill_via_sp(tmp, val, save, tuple((dword, CBO_ZERO_PATTERN) for dword in range(0, 64, 8))),
            *access(case, "+zicboz", [f"cbo.zero (x{ptr})"]),
            *[line for dword in range(0, 64, 8) for line in _record_via_sp(test_data, tmp, dword, val, save)],
        ]

    lines += gated(
        [
            *cbo_zero("cbo_zero", GOOD_TAG[mt_mode]),
            *(cbo_zero("cbo_zero_mismatch", BAD_TAG[mt_mode]) if mismatch else []),
        ],
        "defined(ZICBOZ_SUPPORTED)",
    )
    if m_mode:

        def records(*offsets: int) -> list[str]:
            return [line for offset in offsets for line in _record_via_sp(test_data, good, offset, val, save)]

        def vload(case: str, instruction: str) -> list[str]:
            """v24 = RD_CANARY, then instruction: record both elements of v24."""
            return [
                f"LI(x{val}, {RD_CANARY:#x})",
                ".option push",
                ".option arch, +v",
                f"vmv.v.x v24, x{val}",
                ".option pop",
                *access(case, "+v", [instruction]),
                *_record_vreg(test_data, val, 24),
            ]

        # Two 64-bit elements: at the pointer and 8 bytes on (unit-stride), 16 bytes on (stride and indices 0, 16), or at
        # 8 and 24 (indices). Each store has data of its own (v8-v11), and memory is recorded after it; vd holds a
        # canary before each load, and a masked load leaves its masked-off element undisturbed (mu)
        lines += gated(
            [
                f"LI(x{tmp}, MSTATUS_VS)",
                f"csrs mstatus, x{tmp}",
                ".option push",
                ".option arch, +v",
                "vsetivli x0, 2, e64, m1, ta, mu",
                f"LI(x{val}, 0x1122334455667788)",
                f"vmv.v.x v8, x{val}",
                "vid.v v16",
                "vsll.vi v16, v16, 4",
                "vadd.vv v8, v8, v16",
                "vadd.vi v9, v8, 1",
                "vadd.vi v10, v8, 2",
                "vadd.vi v11, v8, 3",
                "vadd.vi v17, v16, 8",
                "vmv.v.i v0, 1",
                ".option pop",
                *_check_pointer(good, tmp, mt_mode, VECTOR_CHUNK, GOOD_TAG[mt_mode]),
                *_fill_via_sp(good, val, save, ((0, 0), (8, 0), (16, 0), (24, 0))),
                f"LI(x{tmp}, 16)",
                *access("vse", "+v", [f"vse64.v v8, (x{good})"]),
                *records(0, 8),
                *access("vsse", "+v", [f"vsse64.v v9, (x{good}), x{tmp}"]),
                *records(0, 8, 16),
                *access("vsuxei", "+v", [f"vsuxei64.v v10, (x{good}), v16"]),
                *records(0, 16),
                *access("vse_masked", "+v", [f"vse64.v v11, (x{good}), v0.t"]),
                *records(0, 8),
                *vload("vle", f"vle64.v v24, (x{good})"),
                *vload("vle_masked", f"vle64.v v24, (x{good}), v0.t"),
                *vload("vlse", f"vlse64.v v24, (x{good}), x{tmp}"),
                *vload("vluxei", f"vluxei64.v v24, (x{good}), v17"),
                *vload("vleff", f"vle64ff.v v24, (x{good})"),
                f"csrr x{val}, vl",
                write_sigupd(val, test_data),
            ],
            "defined(V_SUPPORTED)",
        )
    test_data.int_regs.return_registers([ptr, good, val, tmp, save])
    return lines


def _m_checked_mprv_regular_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """The regular accesses that implicit tag checks cover besides loads and stores, in M-mode with mstatus.MPRV = 1 and
    MPP = S: checked with the MT_MODE (menvcfg) and tag table (svitts) of S-mode, whose address translation is Bare,
    while mseccfg.MT_MODE = 00. LR/SC, amoadd.d, amoswap.w and cbo.zero with a mismatching pointer tag raise a
    software-check exception, which M-mode takes, that writes neither rd nor memory, and with the matching one are
    performed; cbo.zero whose block mismatches only in its last chunk, through a pointer with the matching tag into its
    first chunk, raises one too. A misaligned LR and AMO with a mismatching pointer tag raise one, as the tag check
    comes before their address-misaligned exception (Bare translation). Vector loads and stores: vle64.v, vse64.v and
    vle64ff.v with a mismatching pointer tag raise one at element 0, and, with the tag of chunk VECTOR_CHUNK + 1
    mismatching, vsse64.v with stride 16 raises one at element 1 after storing element 0 (vstart = 1), and vle64ff.v
    from VECTOR_CHUNK + 8 trims vl to 1; masked unit-stride, strided and indexed loads and stores whose element 1 is
    there: not checked when it is masked off, a software-check exception at element 1 when it is active (and the
    unmasked strided and indexed ones). Record rd, memory, vd, vstart and vl."""
    name = MT_NAMES[mt_mode]
    ptr, good, val, tmp, mprv, save = test_data.int_regs.get_registers(6)
    mt = f"{mt_mode << MT_MODE_LSB:#x}"
    good_tag, bad_tag = GOOD_TAG[mt_mode], BAD_TAG[mt_mode]

    def with_mprv(case: str, arch: str, instructions: list[str]) -> list[str]:
        return _regular_access(
            test_data,
            cg,
            "cp_checked_regular_mprv",
            f"M_{name}_mprv_{case}",
            arch,
            instructions,
            ([f"csrs mstatus, x{mprv}"], [f"csrc mstatus, x{mprv}"]),
        )

    def set_chunk_tag(chunk: int, tag: int) -> list[str]:
        """The tag of data chunk chunk, the other chunk of its tag byte keeping good_tag with 4-bit tags (x{save} holds
        the address of the tag of data chunk 0)."""
        if mt_mode == MT_TAG7:
            return [f"LI(x{tmp}, {tag:#x})", f"sb x{tmp}, {chunk}(x{save})"]
        byte = good_tag | (tag << 4) if chunk % 2 else tag | (good_tag << 4)
        return [f"LI(x{tmp}, {byte:#x})", f"sb x{tmp}, {chunk // 2}(x{save})"]

    def set_vector_tag(tag: int) -> list[str]:
        """The tag of chunk VECTOR_CHUNK + 1."""
        return set_chunk_tag(VECTOR_CHUNK + 1, tag)

    lines = [
        comment_banner(
            f"cp_checked_regular_mprv (M, {name})",
            f"In M-mode with mstatus.MPRV = 1 and MPP = S, and {TAG_BITS[mt_mode]}-bit tags in S-mode (menvcfg.MT_MODE,\n"
            "svitts) and memory tagging disabled in M-mode: LR/SC, AMOs and cbo.zero with a mismatching pointer tag:\n"
            f"{SW_CHECK_TEXT}, which M-mode takes, rd and memory unchanged; with the matching\n"
            "one: performed; cbo.zero mismatching only in the last chunk of its block, and a misaligned LR and AMO with\n"
            "a mismatching pointer tag (checked before their misaligned exception): the same exception. Vector loads\n"
            "and stores: element 0 mismatching, or element 1 of a strided store and of a fault-only-first load (vstart\n"
            "= 1, vl = 1); masked, strided and indexed forms whose element 1 mismatches: not checked when it is masked\n"
            "off, the exception at element 1 when it is active. Record rd, memory, vd, vstart and vl",
        ),
        *_check_vitt("CSR_SVITTS", mt_mode, (mprv, tmp, val)),
        *_set_pmm(tmp, "SMNPM"),
        f"LI(x{val}, {mt})",
        f"or x{tmp}, x{tmp}, x{val}",
        f"csrs menvcfg, x{tmp}",
        f"LI(x{tmp}, MSTATUS_MPP)",
        f"csrc mstatus, x{tmp}",
        f"LI(x{mprv}, MSTATUS_MPRV | {1 << 11:#x})    # MPP = S",
        *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK, good_tag),
        *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, bad_tag),
    ]
    lines += gated(
        [
            f"LI(x{val}, {RD_CANARY:#x})",
            *with_mprv("lr_mismatch", "+zalrsc", [f"lr.d x{val}, (x{ptr})"]),
            write_sigupd(val, test_data),
            f"LI(x{tmp}, {RD_CANARY:#x})",
            f"LI(x{val}, 0xfedcba9876543210)",
            *with_mprv("sc_mismatch", "+zalrsc", [f"sc.d x{tmp}, x{val}, (x{ptr})"]),
            write_sigupd(tmp, test_data),
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, 0x0123456789abcdef)",
            *with_mprv("lr_sc", "+zalrsc", [f"lr.d x{val}, (x{good})", f"sc.d x{tmp}, x{tmp}, (x{good})"]),
            write_sigupd(val, test_data),
            write_sigupd(tmp, test_data),
            *_record_via_sp(test_data, good, 0, val, tmp),
        ],
        "defined(ZALRSC_SUPPORTED)",
    )
    lines += gated(
        [
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, 0x0101010101010101)",
            *with_mprv("amoadd_d_mismatch", "+zaamo", [f"amoadd.d x{val}, x{tmp}, (x{ptr})"]),
            write_sigupd(val, test_data),
            *with_mprv("amoadd_d", "+zaamo", [f"amoadd.d x{val}, x{tmp}, (x{good})"]),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, tmp),
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, 0x33cc33cc)",
            *with_mprv("amoswap_w_mismatch", "+zaamo", [f"amoswap.w x{val}, x{tmp}, (x{ptr})"]),
            write_sigupd(val, test_data),
            *with_mprv("amoswap_w", "+zaamo", [f"amoswap.w x{val}, x{tmp}, (x{good})"]),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, tmp),
        ],
        "defined(ZAAMO_SUPPORTED)",
    )
    # A misaligned LR and AMO (REGULAR_CHUNK + 4) with a mismatching pointer tag: with Bare translation their tag check
    # comes before their address-misaligned exception
    lines += gated(
        [
            *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, bad_tag, 4),
            f"LI(x{val}, {RD_CANARY:#x})",
            *with_mprv("lr_misaligned_mismatch", "+zalrsc", [f"lr.d x{val}, (x{ptr})"]),
            write_sigupd(val, test_data),
        ],
        "defined(ZALRSC_SUPPORTED)",
    )
    lines += gated(
        [
            *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, bad_tag, 4),
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, 0x0101010101010101)",
            *with_mprv("amoadd_d_misaligned_mismatch", "+zaamo", [f"amoadd.d x{val}, x{tmp}, (x{ptr})"]),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, ptr, -4, val, save),
            *_record_via_sp(test_data, ptr, 4, val, save),
        ],
        "defined(ZAAMO_SUPPORTED)",
    )
    # cbo.zero: a pattern in the block, through sp, then a mismatching pointer tag (no byte zeroed) and the matching one
    lines += gated(
        [
            *_check_pointer(ptr, tmp, mt_mode, CBO_ZERO_CHUNK, bad_tag),
            *_check_pointer(good, tmp, mt_mode, CBO_ZERO_CHUNK, good_tag),
            f"LI(x{val}, {CBO_ZERO_PATTERN:#x})",
            f"mv x{save}, sp",
            f"LA(sp, {CHECK_DATA} + {16 * CBO_ZERO_CHUNK})",
            *[f"sd x{val}, {dword}(sp)" for dword in range(0, 64, 8)],
            f"mv sp, x{save}",
            *with_mprv("cbo_zero_mismatch", "+zicboz", [f"cbo.zero (x{ptr})"]),
            *[line for dword in (0, 56) for line in _record_via_sp(test_data, good, dword, val, save)],
            *with_mprv("cbo_zero", "+zicboz", [f"cbo.zero (x{good})"]),
            *[line for dword in (0, 56) for line in _record_via_sp(test_data, good, dword, val, save)],
            # Only the last chunk of the block mismatching, through a pointer into its first chunk with the matching tag
            *_fill_via_sp(good, val, save, tuple((dword, CBO_ZERO_PATTERN) for dword in range(0, 64, 8))),
            *_check_tags(mt_mode, save, tmp),
            *set_chunk_tag(CBO_ZERO_CHUNK + 3, bad_tag),
            *with_mprv("cbo_zero_last_chunk_mismatch", "+zicboz", [f"cbo.zero (x{good})"]),
            *set_chunk_tag(CBO_ZERO_CHUNK + 3, good_tag),
            *[line for dword in (0, 56) for line in _record_via_sp(test_data, good, dword, val, save)],
        ],
        "defined(ZICBOZ_SUPPORTED)",
    )

    def records(*offsets: int) -> list[str]:
        return [line for offset in offsets for line in _record_via_sp(test_data, good, offset, val, save)]

    def canary() -> list[str]:
        return [
            f"LI(x{val}, {RD_CANARY:#x})",
            ".option push",
            ".option arch, +v",
            f"vmv.v.x v24, x{val}",
            ".option pop",
        ]

    def vstart() -> list[str]:
        """Record vstart, and clear it."""
        return [f"csrr x{val}, vstart", write_sigupd(val, test_data), "csrw vstart, x0"]

    def vector(*instructions: str) -> list[str]:
        return [".option push", ".option arch, +v", *instructions, ".option pop"]

    # A pattern in the doublewords at good + 0, 8, 16 and 24 (through sp), and data of its own for each store (v8-v10).
    # A load that traps may write vd, so vd is recorded after the others only, which first get a canary in it
    lines += gated(
        [
            f"LI(x{tmp}, MSTATUS_VS)",
            f"csrs mstatus, x{tmp}",
            ".option push",
            ".option arch, +v",
            "vsetivli x0, 2, e64, m1, ta, ma",
            f"LI(x{val}, 0x0f0e0d0c0b0a0908)",
            f"vmv.v.x v8, x{val}",
            "vid.v v9",
            "vadd.vv v8, v8, v9",
            "vadd.vi v9, v8, 2",
            "vadd.vi v10, v8, 4",
            ".option pop",
            *_check_pointer(ptr, tmp, mt_mode, VECTOR_CHUNK, bad_tag),
            *_check_pointer(good, tmp, mt_mode, VECTOR_CHUNK, good_tag),
            *_fill_via_sp(good, val, save, tuple((8 * i, VECTOR_PATTERN[i]) for i in range(4))),
            *with_mprv("vle_mismatch", "+v", [f"vle64.v v24, (x{ptr})"]),
            *canary(),
            *with_mprv("vle", "+v", [f"vle64.v v24, (x{good})"]),
            *_record_vreg(test_data, val, 24),
            *with_mprv("vse_mismatch", "+v", [f"vse64.v v8, (x{ptr})"]),
            *records(0, 8),
            *with_mprv("vse", "+v", [f"vse64.v v8, (x{good})"]),
            *records(0, 8),
            *with_mprv("vleff_mismatch", "+v", [f"vle64ff.v v24, (x{ptr})"]),
            f"csrr x{val}, vl",
            write_sigupd(val, test_data),
            # The tag of chunk VECTOR_CHUNK + 1 mismatching (M-mode does not check its own stores here)
            *_check_tags(mt_mode, save, tmp),
            *set_vector_tag(bad_tag),
            f"LI(x{tmp}, 16)",
            *with_mprv("vsse_partial", "+v", [f"vsse64.v v9, (x{good}), x{tmp}"]),
            f"csrr x{val}, vstart",
            write_sigupd(val, test_data),
            "csrw vstart, x0",
            *canary(),
            f"addi x{val}, x{good}, 8",
            *with_mprv("vleff_trimmed", "+v", [f"vle64ff.v v24, (x{val})"]),
            f"csrr x{val}, vl",
            write_sigupd(val, test_data),
            *_record_vreg(test_data, val, 24, 1),
            *set_vector_tag(good_tag),
            # vsse_partial stored element 0 at good + 0, and not element 1 at good + 16
            *records(0, 16),
            ".option push",
            ".option arch, +v",
            "vsetivli x0, 2, e64, m1, ta, ma",
            ".option pop",
            f"LI(x{tmp}, 16)",
            *with_mprv("vsse", "+v", [f"vsse64.v v10, (x{good}), x{tmp}"]),
            *records(0, 8, 16),
            *canary(),
            *with_mprv("vleff", "+v", [f"vle64ff.v v24, (x{good})"]),
            f"csrr x{val}, vl",
            write_sigupd(val, test_data),
            *_record_vreg(test_data, val, 24),
            # Masked, strided and indexed forms whose element 1 is in chunk VECTOR_CHUNK + 1, with its tag mismatching:
            # masked off (v0 = 1), not checked; active (v0 = 2, or unmasked), a software-check exception at element 1
            # (vstart = 1). The unit-stride ones from good + 8 (x{ptr}), the indexed ones with indices 0 and 16 (v16),
            # the stores with data of their own (v9-v12) over the pattern
            *vector(
                "vsetivli x0, 2, e64, m1, ta, mu",
                "vid.v v16",
                "vsll.vi v16, v16, 4",
                "vadd.vi v11, v8, 6",
                "vadd.vi v12, v8, 8",
                "vmv.v.i v0, 1",
            ),
            f"addi x{ptr}, x{good}, 8",
            *_fill_via_sp(good, val, save, tuple((8 * i, VECTOR_PATTERN[i]) for i in range(4))),
            *_check_tags(mt_mode, save, tmp),
            *set_vector_tag(bad_tag),
            *canary(),
            *with_mprv("vle_masked", "+v", [f"vle64.v v24, (x{ptr}), v0.t"]),
            *_record_vreg(test_data, val, 24),
            *canary(),
            f"LI(x{tmp}, 16)",
            *with_mprv("vlse_masked", "+v", [f"vlse64.v v24, (x{good}), x{tmp}, v0.t"]),
            *_record_vreg(test_data, val, 24),
            *canary(),
            *with_mprv("vluxei_masked", "+v", [f"vluxei64.v v24, (x{good}), v16, v0.t"]),
            *_record_vreg(test_data, val, 24),
            *with_mprv("vse_masked", "+v", [f"vse64.v v11, (x{ptr}), v0.t"]),
            *records(8, 16),
            f"LI(x{tmp}, 16)",
            *with_mprv("vsse_masked", "+v", [f"vsse64.v v12, (x{good}), x{tmp}, v0.t"]),
            *records(0, 16),
            *with_mprv("vsuxei_masked", "+v", [f"vsuxei64.v v10, (x{good}), v16, v0.t"]),
            *records(0, 16),
            *vector("vmv.v.i v0, 2"),
            *with_mprv("vle_masked_mismatch", "+v", [f"vle64.v v24, (x{ptr}), v0.t"]),
            *vstart(),
            *with_mprv("vse_masked_mismatch", "+v", [f"vse64.v v12, (x{ptr}), v0.t"]),
            *vstart(),
            *records(8, 16),
            f"LI(x{tmp}, 16)",
            *with_mprv("vlse_partial", "+v", [f"vlse64.v v24, (x{good}), x{tmp}"]),
            *vstart(),
            *with_mprv("vluxei_partial", "+v", [f"vluxei64.v v24, (x{good}), v16"]),
            *vstart(),
            *with_mprv("vsuxei_partial", "+v", [f"vsuxei64.v v9, (x{good}), v16"]),
            *vstart(),
            *records(0, 16),
            *_check_tags(mt_mode, save, tmp),
            *set_vector_tag(good_tag),
            *vector("vsetivli x0, 2, e64, m1, ta, ma"),
        ],
        "defined(V_SUPPORTED)",
    )
    lines += [
        f"LI(x{tmp}, {mt})",
        f"csrc menvcfg, x{tmp}",
        f"LI(x{tmp}, {0b11 << PMM_LSB:#x})",
        f"csrc menvcfg, x{tmp}",
        "csrw CSR_SVITTS, x0",
    ]
    test_data.int_regs.return_registers([ptr, good, val, tmp, mprv, save])
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
    (svitts) of S-mode, whose address translation is Bare, while mseccfg.MT_MODE = 00, and not checked with
    mstatus.MTAG_I = 1; and checktag, which uses those of M-mode."""
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
            f"cp_checked_mprv, cp_checked_mprv_mtag_i, cp_checktag_mprv (M, {name})",
            f"In M-mode with mstatus.MPRV = 1 and MPP = S, and {TAG_BITS[mt_mode]}-bit tags in S-mode (menvcfg.MT_MODE,\n"
            "svitts) and memory tagging disabled in M-mode: a load with the matching pointer tag, and a load and a\n"
            f"store with a mismatching one: {SW_CHECK_TEXT}, which M-mode takes; with\n"
            "mstatus.MTAG_I = 1 too, a load and a store with a mismatching one: no check. checktag uses\n"
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
        # mstatus.MTAG_I = 1, set and cleared with MPRV: not checked
        f"LI(x{mprv}, MSTATUS_MPRV | {1 << 11:#x} | {1 << MSTATUS_MTAG_I_BIT:#x})    # MPP = S, MTAG_I",
        f"LI(x{val}, {RD_CANARY:#x})",
        *with_mprv("mtag_i", "cp_checked_mprv_mtag_i", f"ld x{val}, 0(x{ptr})"),
        write_sigupd(val, test_data),
        f"LI(x{val}, 0xfedcba9876543210)",
        *with_mprv("mtag_i_store", "cp_checked_mprv_mtag_i", f"sd x{val}, 0(x{ptr})"),
        *_record_via_sp(test_data, ptr, 0, val, save),
        f"LI(x{mprv}, MSTATUS_MPRV | {1 << 11:#x})    # MPP = S",
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


# mcontrol6 (tdata1.type = 6) with the breakpoint action (0), match = 0 (equal) and any size (0); its load (bit 0) or
# store (bit 1) bit selects the accesses it matches. ZIMT_MCONTROL6 (_trigger_defines) also sets m (bit 6), and s
# (bit 4) where it is writable, so that the trigger matches whether a hart takes the privilege of an MPRV access as M
# or as MPP = S (nothing runs in S-mode while it is armed).
TRIGGER_LOAD, TRIGGER_STORE = 0b01, 0b10
# The cbo.zero of the trigger tests goes through the base of its block, at a data chunk 256-byte aligned, so that the
# three compare values that the Debug spec allows for cache operations (every address of the block, its base, the
# effective address) give the same address for blocks of up to 256 bytes. Every data chunk has the matching tag, so a
# block of any of those sizes mismatches its pointer, and the breakpoint keeps cbo.zero from zeroing the data of the
# other trigger cases (REGULAR_CHUNK, VECTOR_CHUNK) that a larger block holds
TRIGGER_CBO_CHUNK = 48
# The Sdtrig tests cover the triggers 0-15 (SdtrigCommon.SDTRIG_MAX_TRIGGERS); the trigger tests use the first of them
# that supports mcontrol6, ZIMT_MCONTROL6_TRIGGER, on a hart whose mcontrol6 triggers can match M-mode loads and
# stores with match = 0, and that has tdata2 (as the Sdtrig tests' gates, which leave no WARL field value to chance)
TRIGGER_CANDIDATES = 16
TRIGGER_CAPABLE = (
    "defined(ZIMT_MCONTROL6_TRIGGER) && defined(UDB_SDTRIG_M_WRITABLE) && defined(UDB_SDTRIG_MCONTROL6_LOAD_WRITABLE)"
    " && defined(UDB_SDTRIG_MCONTROL6_STORE_WRITABLE) && defined(UDB_SDTRIG_MCONTROL6_MATCH_LEGAL_VALUES_0)"
    " && defined(UDB_TDATA2_IMPLEMENTED)"
)


def _trigger_defines() -> list[str]:
    """Define ZIMT_MCONTROL6_TRIGGER, the first trigger that supports mcontrol6, and ZIMT_MCONTROL6."""
    lines = []
    for n in range(TRIGGER_CANDIDATES):
        lines += [
            f"#{'if' if n == 0 else 'elif'} defined(UDB_SDTRIG_MCONTROL6_SUPPORTED_TRIGGERS_{n})",
            f"#define ZIMT_MCONTROL6_TRIGGER {n}",
        ]
    return [
        *lines,
        "#endif",
        "#ifdef UDB_SDTRIG_S_WRITABLE",
        "#define ZIMT_MCONTROL6 ((6 << 60) | (1 << 6) | (1 << 4))",
        "#else",
        "#define ZIMT_MCONTROL6 ((6 << 60) | (1 << 6))",
        "#endif",
    ]


def _m_trigger_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """Sdtrig and the implicit tag checks, in M-mode with mstatus.MPRV = 1 and MPP = S: the accesses are checked with
    S-mode's MT_MODE (menvcfg) and tag table (svitts), whose address translation is Bare, while M-mode, whose trap
    handler takes their exceptions, keeps memory tagging disabled; triggers match them in M-mode, the mode the hart is
    in. The first mcontrol6 trigger (ZIMT_MCONTROL6_TRIGGER), of M-mode (and S-mode where its s bit is writable) with
    the breakpoint action, on the address of an access with a mismatching pointer tag: a breakpoint exception (cause 3,
    xtval the address), as a data address breakpoint has priority over the tag check. A load trigger for ld, lr.d,
    amoadd.d, vle64.v, and vlse64.v, vluxei64.v and vle64ff.v on element 0; a store trigger for sd, sc.d, amoadd.d,
    vse64.v and cbo.zero, through and on the 256-byte aligned base of its block. The sc.d holds the reservation of an
    lr.d through the matching pointer tag just before it, as the Debug spec leaves it unspecified whether a failing sc
    matches store triggers. A load trigger on the tag byte of the chunk of ld, sd and amoadd.d: none with the matching
    pointer tag, a software-check exception with a mismatching one, as the tag loads of the check are not matched by
    triggers; also none for a matching LR/SC pair, vse64.v and cbo.zero. Record rd and memory.

    Like the Sdtrig tests, these assume that load and store address triggers fire before the access, the timing that
    the Debug spec suggests: mcontrol6 triggers may fire whenever it is convenient, and the priority of a breakpoint
    over the exceptions of the access, and so over its tag check, holds only for a trigger that fires before it."""
    name = MT_NAMES[mt_mode]
    ptr, good, val, tmp, mprv, save = test_data.int_regs.get_registers(6)
    mt = f"{mt_mode << MT_MODE_LSB:#x}"
    good_tag, bad_tag = GOOD_TAG[mt_mode], BAD_TAG[mt_mode]

    def arm(xsl: int, address: list[str]) -> list[str]:
        """Arm the trigger on the address that the lines address put in x{tmp}."""
        return [*address, f"csrw tdata2, x{tmp}", f"LI(x{tmp}, ZIMT_MCONTROL6 | {xsl:#x})", f"csrw tdata1, x{tmp}"]

    def data_address(chunk: int) -> list[str]:
        return [f"LA(x{tmp}, {CHECK_DATA} + {16 * chunk})"]

    def tag_address(chunk: int) -> list[str]:
        """The tag byte of data chunk chunk (x{save} holds that of data chunk 0)."""
        return [f"addi x{tmp}, x{save}, {chunk if mt_mode == MT_TAG7 else chunk // 2}"]

    def triggered(
        case: str, coverpoint: str, arch: str, xsl: int, address: list[str], instr: str, before: tuple[str, ...] = ()
    ) -> list[str]:
        """Arm the trigger, then instr (the testcase) with MPRV, after the lines before."""
        return [
            *arm(xsl, address),
            *_regular_access(
                test_data,
                cg,
                coverpoint,
                f"M_{name}_{case}",
                arch,
                [instr],
                ([f"csrs mstatus, x{mprv}", *before], [f"csrc mstatus, x{mprv}"]),
            ),
            "csrw tdata1, x0    # disarm",
        ]

    lines = [
        comment_banner(
            f"cp_trigger_before_check, cp_trigger_amo_xsl, cp_trigger_tag_load (M, {name})",
            f"In M-mode with mstatus.MPRV = 1 and MPP = S, and {TAG_BITS[mt_mode]}-bit tags in S-mode\n"
            "(menvcfg.MT_MODE, svitts), with the first mcontrol6 trigger, of M-mode, with the breakpoint action: on\n"
            "the address of ld, sd, lr.d, sc.d, amoadd.d (a store and a load trigger), cbo.zero, vle64.v, vse64.v,\n"
            "vlse64.v, vluxei64.v and vle64ff.v with a mismatching pointer tag, a breakpoint exception (cause 3,\n"
            "mtval the address) before the tag check, rd, vd and memory unchanged (the sc.d holds the reservation\n"
            "of an lr.d through the matching pointer tag); a load trigger on the tag byte of the chunk of ld, sd\n"
            f"and amoadd.d: none with the matching pointer tag, a {SW_CHECK_TEXT} with a\n"
            "mismatching one, as the tag loads of the tag check do not match triggers; none for a matching LR/SC\n"
            "pair, vse64.v and cbo.zero either. Record rd and memory. Load and store address triggers are assumed\n"
            "to fire before the access (the suggested timing)",
        ),
        *_check_vitt("CSR_SVITTS", mt_mode, (save, tmp, val)),
        *_check_fill(mt_mode, save, tmp),
        *_check_tags(mt_mode, save, tmp),
        *_set_pmm(tmp, "SMNPM"),
        f"LI(x{val}, {mt})",
        f"or x{tmp}, x{tmp}, x{val}",
        f"csrs menvcfg, x{tmp}",
        f"LI(x{tmp}, MSTATUS_MPP)",
        f"csrc mstatus, x{tmp}",
        f"LI(x{mprv}, MSTATUS_MPRV | {1 << 11:#x})    # MPP = S",
        *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK, good_tag),
        *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, bad_tag),
        f"LI(x{tmp}, ZIMT_MCONTROL6_TRIGGER)",
        f"csrw tselect, x{tmp}",
        "csrw tdata1, x0",
        "#ifdef UDB_TDATA3_IMPLEMENTED",
        "csrw tdata3, x0    # no textra condition",
        "#endif",
        "csrsi mstatus, 0x8    # MIE = 1: M-mode breakpoints need it (or tcontrol.MTE)",
        "#ifdef UDB_SDTRIG_BREAKPOINT_REENTRANCY_USE_TCONTROL",
        "csrsi tcontrol, 0x8    # MTE = 1",
        "#endif",
        # A data address breakpoint has priority over the tag check
        f"LI(x{val}, {RD_CANARY:#x})",
        *triggered(
            "ld_trigger",
            "cp_trigger_before_check",
            "+zicsr",
            TRIGGER_LOAD,
            data_address(REGULAR_CHUNK),
            f"ld x{val}, 0(x{ptr})",
        ),
        write_sigupd(val, test_data),
        f"LI(x{val}, 0xfedcba9876543210)",
        *triggered(
            "sd_trigger",
            "cp_trigger_before_check",
            "+zicsr",
            TRIGGER_STORE,
            data_address(REGULAR_CHUNK),
            f"sd x{val}, 0(x{ptr})",
        ),
        *_record_via_sp(test_data, good, 0, val, save),
        *_check_tags(mt_mode, save, tmp),
    ]
    lines += gated(
        [
            f"LI(x{val}, {RD_CANARY:#x})",
            *triggered(
                "lr_trigger",
                "cp_trigger_before_check",
                "+zalrsc",
                TRIGGER_LOAD,
                data_address(REGULAR_CHUNK),
                f"lr.d x{val}, (x{ptr})",
            ),
            write_sigupd(val, test_data),
            f"LI(x{val}, {RD_CANARY:#x})",
            # A successful sc is a store for triggers, a failing one may not be (Debug spec): the sc holds the
            # reservation of an lr.d through the matching pointer tag just before it (a constrained LR/SC
            # sequence), which the store trigger does not match
            *triggered(
                "sc_trigger",
                "cp_trigger_before_check",
                "+zalrsc",
                TRIGGER_STORE,
                data_address(REGULAR_CHUNK),
                f"sc.d x{val}, x{val}, (x{ptr})",
                (f"lr.d x{tmp}, (x{good})    # the reservation",),
            ),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(ZALRSC_SUPPORTED)",
    )
    lines += gated(
        [
            f"LI(x{val}, {RD_CANARY:#x})",
            *triggered(
                "amoadd_trigger",
                "cp_trigger_before_check",
                "+zaamo",
                TRIGGER_STORE,
                data_address(REGULAR_CHUNK),
                f"amoadd.d x{val}, x{val}, (x{ptr})",
            ),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
            *_check_tags(mt_mode, save, tmp),
            # An AMO is a load too: a load trigger matches it as well
            f"LI(x{val}, {RD_CANARY:#x})",
            *triggered(
                "amoadd_load_trigger",
                "cp_trigger_amo_xsl",
                "+zaamo",
                TRIGGER_LOAD,
                data_address(REGULAR_CHUNK),
                f"amoadd.d x{val}, x{val}, (x{ptr})",
            ),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(ZAAMO_SUPPORTED)",
    )
    lines += gated(
        [
            *_check_pointer(ptr, tmp, mt_mode, TRIGGER_CBO_CHUNK, bad_tag),
            *_check_pointer(good, tmp, mt_mode, TRIGGER_CBO_CHUNK, good_tag),
            *_fill_via_sp(good, val, save, tuple((dword, CBO_ZERO_PATTERN) for dword in range(0, 64, 8))),
            *triggered(
                "cbo_zero_trigger",
                "cp_trigger_before_check",
                "+zicboz",
                TRIGGER_STORE,
                data_address(TRIGGER_CBO_CHUNK),
                f"cbo.zero (x{ptr})",
            ),
            *[line for dword in (0, 56) for line in _record_via_sp(test_data, good, dword, val, save)],
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(ZICBOZ_SUPPORTED)",
    )
    lines += gated(
        [
            f"LI(x{tmp}, MSTATUS_VS)",
            f"csrs mstatus, x{tmp}",
            *_check_pointer(ptr, tmp, mt_mode, VECTOR_CHUNK, bad_tag),
            f"LI(x{val}, {RD_CANARY:#x})",
            ".option push",
            ".option arch, +v",
            "vsetivli x0, 2, e64, m1, ta, ma",
            f"vmv.v.x v24, x{val}",
            ".option pop",
            *triggered(
                "vle_trigger",
                "cp_trigger_before_check",
                "+v",
                TRIGGER_LOAD,
                data_address(VECTOR_CHUNK),
                f"vle64.v v24, (x{ptr})",
            ),
            f"csrr x{val}, vstart",
            write_sigupd(val, test_data),
            "csrw vstart, x0",
            *_record_vreg(test_data, val, 24),
            *_check_tags(mt_mode, save, tmp),
            # The other vector forms, on their element 0: a store trigger on vse64.v (its memory unchanged), and a load
            # trigger on the strided vlse64.v (stride 16), the indexed vluxei64.v (offsets 0 and 16 in v28) and the
            # fault-only-first vle64ff.v (vl unchanged), vd unchanged
            *_check_pointer(good, tmp, mt_mode, VECTOR_CHUNK, good_tag),
            *triggered(
                "vse_trigger",
                "cp_trigger_before_check",
                "+v",
                TRIGGER_STORE,
                data_address(VECTOR_CHUNK),
                f"vse64.v v24, (x{ptr})",
            ),
            f"csrr x{val}, vstart",
            write_sigupd(val, test_data),
            "csrw vstart, x0",
            *[line for dword in (0, 8) for line in _record_via_sp(test_data, good, dword, val, save)],
            *_check_tags(mt_mode, save, tmp),
            ".option push",
            ".option arch, +v",
            "vid.v v28",
            "vsll.vi v28, v28, 4",
            ".option pop",
            *triggered(
                "vlse_trigger",
                "cp_trigger_before_check",
                "+v",
                TRIGGER_LOAD,
                data_address(VECTOR_CHUNK),
                f"vlse64.v v24, (x{ptr}), x{tmp}",
                (f"LI(x{tmp}, 16)    # stride",),
            ),
            *triggered(
                "vluxei_trigger",
                "cp_trigger_before_check",
                "+v",
                TRIGGER_LOAD,
                data_address(VECTOR_CHUNK),
                f"vluxei64.v v24, (x{ptr}), v28",
            ),
            *triggered(
                "vleff_trigger",
                "cp_trigger_before_check",
                "+v",
                TRIGGER_LOAD,
                data_address(VECTOR_CHUNK),
                f"vle64ff.v v24, (x{ptr})",
            ),
            f"csrr x{val}, vl",
            write_sigupd(val, test_data),
            f"csrr x{val}, vstart",
            write_sigupd(val, test_data),
            "csrw vstart, x0",
            *_record_vreg(test_data, val, 24),
        ],
        "defined(V_SUPPORTED)",
    )
    # The tag loads of the check do not match triggers
    lines += [
        *_check_pointer(good, tmp, mt_mode, REGULAR_CHUNK, good_tag),
        *_check_pointer(ptr, tmp, mt_mode, REGULAR_CHUNK, bad_tag),
        f"LI(x{val}, {RD_CANARY:#x})",
        *triggered(
            "ld_tag_trigger_match",
            "cp_trigger_tag_load",
            "+zicsr",
            TRIGGER_LOAD,
            tag_address(REGULAR_CHUNK),
            f"ld x{val}, 0(x{good})",
        ),
        write_sigupd(val, test_data),
        f"LI(x{val}, {RD_CANARY:#x})",
        *triggered(
            "ld_tag_trigger_mismatch",
            "cp_trigger_tag_load",
            "+zicsr",
            TRIGGER_LOAD,
            tag_address(REGULAR_CHUNK),
            f"ld x{val}, 0(x{ptr})",
        ),
        write_sigupd(val, test_data),
        f"LI(x{val}, 0x0123456789abcdef)",
        *triggered(
            "sd_tag_trigger_mismatch",
            "cp_trigger_tag_load",
            "+zicsr",
            TRIGGER_LOAD,
            tag_address(REGULAR_CHUNK),
            f"sd x{val}, 0(x{ptr})",
        ),
        *_record_via_sp(test_data, good, 0, val, save),
        *_check_tags(mt_mode, save, tmp),
        f"LI(x{val}, 0x0123456789abcdef)",
        *triggered(
            "sd_tag_trigger_match",
            "cp_trigger_tag_load",
            "+zicsr",
            TRIGGER_LOAD,
            tag_address(REGULAR_CHUNK),
            f"sd x{val}, 0(x{good})",
        ),
        *_record_via_sp(test_data, good, 0, val, save),
        *_check_tags(mt_mode, save, tmp),
    ]
    lines += gated(
        [
            f"LI(x{val}, 3)",
            *triggered(
                "amoadd_tag_trigger_match",
                "cp_trigger_tag_load",
                "+zaamo",
                TRIGGER_LOAD,
                tag_address(REGULAR_CHUNK),
                f"amoadd.d x{val}, x{val}, (x{good})",
            ),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
            *_check_tags(mt_mode, save, tmp),
            f"LI(x{val}, {RD_CANARY:#x})",
            *triggered(
                "amoadd_tag_trigger_mismatch",
                "cp_trigger_tag_load",
                "+zaamo",
                TRIGGER_LOAD,
                tag_address(REGULAR_CHUNK),
                f"amoadd.d x{val}, x{val}, (x{ptr})",
            ),
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(ZAAMO_SUPPORTED)",
    )
    # A matching LR/SC pair (a constrained sequence; the sc rewrites the value loaded, and whether it succeeds is not
    # recorded), vse64.v and cbo.zero (last: it zeroes its block) with the load trigger on their tag byte: performed
    lines += gated(
        [
            f"LI(x{val}, {RD_CANARY:#x})",
            *arm(TRIGGER_LOAD, tag_address(REGULAR_CHUNK)),
            ".option push",
            ".option arch, +zalrsc",
            f"csrs mstatus, x{mprv}",
            test_data.add_testcase(f"M_{name}_lr_tag_trigger_match", "cp_trigger_tag_load", cg),
            f"lr.d x{val}, (x{good})",
            test_data.add_testcase(f"M_{name}_sc_tag_trigger_match", "cp_trigger_tag_load", cg),
            f"sc.d x{tmp}, x{val}, (x{good})",
            f"csrc mstatus, x{mprv}",
            ".option pop",
            "csrw tdata1, x0    # disarm",
            write_sigupd(val, test_data),
            *_record_via_sp(test_data, good, 0, val, save),
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(ZALRSC_SUPPORTED)",
    )
    lines += gated(
        [
            f"LI(x{tmp}, MSTATUS_VS)",
            f"csrs mstatus, x{tmp}",
            *_check_pointer(good, tmp, mt_mode, VECTOR_CHUNK, good_tag),
            f"LI(x{val}, {RD_CANARY:#x})",
            ".option push",
            ".option arch, +v",
            "vsetivli x0, 2, e64, m1, ta, ma",
            f"vmv.v.x v24, x{val}",
            ".option pop",
            *triggered(
                "vse_tag_trigger_match",
                "cp_trigger_tag_load",
                "+v",
                TRIGGER_LOAD,
                tag_address(VECTOR_CHUNK),
                f"vse64.v v24, (x{good})",
            ),
            *[line for dword in (0, 8) for line in _record_via_sp(test_data, good, dword, val, save)],
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(V_SUPPORTED)",
    )
    lines += gated(
        [
            *_check_pointer(good, tmp, mt_mode, TRIGGER_CBO_CHUNK, good_tag),
            *_fill_via_sp(good, val, save, tuple((dword, CBO_ZERO_PATTERN) for dword in range(0, 64, 8))),
            *_check_tags(mt_mode, save, tmp),
            *triggered(
                "cbo_zero_tag_trigger_match",
                "cp_trigger_tag_load",
                "+zicboz",
                TRIGGER_LOAD,
                tag_address(TRIGGER_CBO_CHUNK),
                f"cbo.zero (x{good})",
            ),
            *[line for dword in (0, 56) for line in _record_via_sp(test_data, good, dword, val, save)],
            *_check_tags(mt_mode, save, tmp),
        ],
        "defined(ZICBOZ_SUPPORTED)",
    )
    lines += [
        "csrci mstatus, 0x8    # MIE = 0",
        "#ifdef UDB_SDTRIG_BREAKPOINT_REENTRANCY_USE_TCONTROL",
        "csrci tcontrol, 0x8    # MTE = 0",
        "#endif",
        f"LI(x{tmp}, {mt})",
        f"csrc menvcfg, x{tmp}",
        f"LI(x{tmp}, {0b11 << PMM_LSB:#x})",
        f"csrc menvcfg, x{tmp}",
        "csrw CSR_SVITTS, x0",
    ]
    test_data.int_regs.return_registers([ptr, good, val, tmp, mprv, save])
    return lines


def _m_checked_mprv_v_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """Loads and stores in M-mode with mstatus.MPRV = 1 and MPV = 1, checked with the MT_MODE and tag table of VS-mode
    (MPP = S: henvcfg, vsvitts) or VU-mode (MPP = U: senvcfg, vsvittu), whose address translation (vsatp and hgatp)
    is Bare, while mseccfg.MT_MODE = 00 and the tag tables of S-mode and U-mode (svitts, svittu) are 0, and not
    checked with mstatus.MTAG_I = 1."""
    name = MT_NAMES[mt_mode]
    ptr, val, tmp, mprv, save = test_data.int_regs.get_registers(5)
    mt = f"{mt_mode << MT_MODE_LSB:#x}"
    lines = [
        comment_banner(
            f"cp_checked_mprv_v, cp_checked_mprv_v_mtag_i (M, {name})",
            f"In M-mode with mstatus.MPRV = 1, MPV = 1 and MPP = S, and {TAG_BITS[mt_mode]}-bit tags in VS-mode\n"
            "(henvcfg.MT_MODE, vsvitts), then MPP = U with them in VU-mode (senvcfg.MT_MODE, vsvittu), and Bare\n"
            "translation: a load and a store with the matching pointer tag, and with a mismatching one: "
            f"{SW_CHECK_TEXT},\nwhich M-mode takes with GVA = 0; with mstatus.MTAG_I = 1 too, a load and a store with\n"
            "a mismatching one: no check. Record rd and memory",
        ),
        "csrw CSR_VSATP, x0",
        "csrw CSR_HGATP, x0",
        "csrw CSR_SVITTS, x0",
        "csrw CSR_SVITTU, x0",
    ]
    for vmode, mpp, env, csr in (("VS", 1, "CSR_HENVCFG", "CSR_VSVITTS"), ("VU", 0, "CSR_SENVCFG", "CSR_VSVITTU")):

        def with_mprv(
            case: str, instruction: str, vmode: str = vmode, coverpoint: str = "cp_checked_mprv_v"
        ) -> list[str]:
            return [
                f"csrs mstatus, x{mprv}",
                test_data.add_testcase(f"M_{name}_mprv_{vmode.lower()}_{case}", coverpoint, cg),
                instruction,
                f"csrc mstatus, x{mprv}",
            ]

        mpv = f"MSTATUS_MPRV | MSTATUS_MPV | {mpp << 11:#x}"
        lines += [
            *_check_vitt(csr, mt_mode, (mprv, tmp, val)),
            *_set_pmm(tmp, "SSNPM"),
            f"LI(x{val}, {mt})",
            f"or x{tmp}, x{tmp}, x{val}",
            f"csrs {env}, x{tmp}",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{mprv}, {mpv})    # MPP = {'S' if mpp else 'U'}",
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
            # mstatus.MTAG_I = 1, set and cleared with MPRV: not checked
            f"LI(x{mprv}, {mpv} | {1 << MSTATUS_MTAG_I_BIT:#x})    # MTAG_I",
            f"LI(x{val}, {RD_CANARY:#x})",
            *with_mprv("mtag_i", f"ld x{val}, 0(x{ptr})", coverpoint="cp_checked_mprv_v_mtag_i"),
            write_sigupd(val, test_data),
            f"LI(x{val}, 0xfedcba9876543210)",
            *with_mprv("mtag_i_store", f"sd x{val}, 0(x{ptr})", coverpoint="cp_checked_mprv_v_mtag_i"),
            *_record_via_sp(test_data, ptr, 0, val, save),
            f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc {env}, x{tmp}",
            f"csrw {csr}, x0",
        ]
    test_data.int_regs.return_registers([ptr, val, tmp, mprv, save])
    return lines


def _s_mtag_i_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """In S-mode with Bare translation and memory tagging enabled, mstatus.MTAG_I = 1, which makes only the loads and
    stores of M-mode with mstatus.MPRV = 1 unchecked: a load and a store with a mismatching pointer tag raise a
    software-check exception. M-mode takes it (medeleg[18] = 0), as the trap handler of S-mode would be tag checked,
    and its trap handler reads the trapping instruction with MPRV = 1 and MPP = S, which MTAG_I makes unchecked (S-mode
    otherwise takes no exception with memory tagging and Bare translation)."""
    name = MT_NAMES[mt_mode]
    ptr, val, tmp, save, deleg = test_data.int_regs.get_registers(5)
    mtag_i = f"{1 << MSTATUS_MTAG_I_BIT:#x}"
    lines = [
        comment_banner(
            f"cp_checked_mtag_i (S, {name})",
            "In S-mode with Bare translation and mstatus.MTAG_I = 1, which only affects loads and stores with\n"
            f"mstatus.MPRV = 1: a load and a store with a mismatching pointer tag: {SW_CHECK_TEXT},\n"
            "which M-mode takes (medeleg[18] = 0). Record rd and memory",
        ),
        "RVTEST_TSBI_GOTO_MMODE",
        f"csrr x{deleg}, medeleg",
        f"LI(x{tmp}, {1 << SW_CHECK:#x})",
        f"csrc medeleg, x{tmp}",
        f"LI(x{tmp}, {mtag_i})",
        f"csrs mstatus, x{tmp}",
        "RVTEST_TSBI_GOTO_SMODE",
        *_check_pointer(ptr, tmp, mt_mode, 3, BAD_TAG[mt_mode]),
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"S_{name}_mtag_i_load", "cp_checked_mtag_i", cg),
        f"ld x{val}, 0(x{ptr})",
        write_sigupd(val, test_data),
        f"LI(x{val}, 0xfedcba9876543210)",
        test_data.add_testcase(f"S_{name}_mtag_i_store", "cp_checked_mtag_i", cg),
        f"sd x{val}, 0(x{ptr})",
        *_record_via_sp(test_data, ptr, 0, val, save),
        "RVTEST_TSBI_GOTO_MMODE",
        f"LI(x{tmp}, {mtag_i})",
        f"csrc mstatus, x{tmp}",
        f"csrw medeleg, x{deleg}",
        "RVTEST_TSBI_GOTO_SMODE",
    ]
    test_data.int_regs.return_registers([ptr, val, tmp, save, deleg])
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
    cross from the first tag table page into the second one; then loads and stores of a page without PTE.MTAG, which
    are not tag checked. The S-mode trap handler takes the exceptions."""
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
            "With address translation, loads and stores of a page without PTE.MTAG are not tag checked: a load and a\n"
            "store of the first tag table page through SETTAG_VA with a mismatching pointer tag, whose tags are not\n"
            "mapped. Record both",
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
# Implicit tag checks with first-stage paging: PTE.MTAG
# ---------------------------------------------------------------------------------------------------------------

# PTE.MTAG (rvtest_experimental.h): with first-stage paging, a leaf PTE with it and X = 0 maps a tagged-data page,
# whose loads and stores are tag checked, and one with it and X = 1 a tagcheck-exempt code page, whose instructions'
# loads and stores are not. A load or store over two pages checks both if either is a tagged-data page, and a supervisor
# access does not check user pages. PTE.MTAG is reserved in non-leaf PTEs and in G-stage PTEs, and ignored with memory
# tagging disabled.
PTE_MTAG = "PTE_MTAG"


class _MtagPage(NamedTuple):
    """A 4 KiB page of the S-mode tests with PTE.MTAG, at MTAG_PAGE_VA + 4 KiB * slot."""

    slot: int
    flags: PteFlags
    physical: str  # a label expression


# The pages of the S-mode tests with Sv39 and PTE.MTAG are in the 2 MiB region of SETTAG_VA, whose level-0 page table
# also maps the tag table pages of the checktag tests. MTAG_PAGE_VA is a multiple of 128 KiB, so the tag table base that
# puts the tags of their chunks at the start of the tags page is a multiple of 4 KiB with both tag widths. The data
# pages map MTAG_DATA, the code pages the first or the second page of MTAG_CODE. Zimt_coverage.svh identifies the pages
# by their slots.
MTAG_PAGE_VA = SETTAG_VA + 0x2_0000
MTAG_DATA = "zimt_mtag_data"
MTAG_TAGS = "zimt_mtag_tags"
MTAG_CODE = "zimt_mtag_code"
MTAG_TAGGED_FLAGS = PteFlags(execute=False, extra=(PTE_MTAG,))
# The chunk of the LR/SC and AMO tests in the pages of MTAG_PAGES, and the cache block (chunks 4-7) of the cbo.zero ones
MTAG_REGULAR_OFFSET = 0x30
MTAG_CBO_ZERO_OFFSET = 0x40
MTAG_EXEMPT_FLAGS = PteFlags(write=False, extra=(PTE_MTAG,))
MTAG_PAGES = {
    # A tagged-data page; one without PTE.MTAG after it; a user tagged-data page, which supervisor accesses do not
    # check; a tagged-data page after it; and one with PTE.MTAG and X = 1, a tagcheck-exempt code page
    "tagged": _MtagPage(0, MTAG_TAGGED_FLAGS, MTAG_DATA),
    "untagged": _MtagPage(1, PteFlags(execute=False), MTAG_DATA),
    "user": _MtagPage(2, PteFlags(user=True, execute=False, extra=(PTE_MTAG,)), MTAG_DATA),
    "tagged_after_user": _MtagPage(3, MTAG_TAGGED_FLAGS, MTAG_DATA),
    "executable": _MtagPage(4, PteFlags(extra=(PTE_MTAG,)), MTAG_DATA),
    "tags": _MtagPage(5, PteFlags(execute=False), MTAG_TAGS),
    # A tagged-data page before slot 7, which is not mapped
    "tagged_before_unmapped": _MtagPage(6, MTAG_TAGGED_FLAGS, MTAG_DATA),
    # The first code page tagcheck-exempt, followed by the second one without PTE.MTAG; both tagcheck-exempt; and the
    # first one without PTE.MTAG
    "exempt": _MtagPage(8, MTAG_EXEMPT_FLAGS, MTAG_CODE),
    "normal_after_exempt": _MtagPage(9, PteFlags(write=False), f"{MTAG_CODE} + 0x1000"),
    "exempt2": _MtagPage(10, MTAG_EXEMPT_FLAGS, MTAG_CODE),
    "exempt_after_exempt": _MtagPage(11, MTAG_EXEMPT_FLAGS, f"{MTAG_CODE} + 0x1000"),
    "normal_code": _MtagPage(12, PteFlags(write=False), MTAG_CODE),
    # The first code page tagcheck-exempt and execute-only (R = 0)
    "exempt_execute_only": _MtagPage(13, PteFlags(read=False, write=False, extra=(PTE_MTAG,)), MTAG_CODE),
    # A user page without PTE.MTAG
    "user_untagged": _MtagPage(14, PteFlags(user=True, execute=False), MTAG_DATA),
    # The tags page again, as a user page, for the tag loads of U-mode
    "user_tags": _MtagPage(15, PteFlags(user=True, execute=False), MTAG_TAGS),
}
# The data pages again, behind a level-1 non-leaf PTE with PTE.MTAG, 4 MiB above
MTAG_NONLEAF_VA = MTAG_PAGE_VA + 0x40_0000
# The pages again (each mode has one page table per level, indexed by the bits of the level: a level-1 PTE of this
# 2 MiB region to the level-0 table of MTAG_PAGES maps them), for the user tags page of svittu: the VITT range of U-mode
# (Svatag), from svittu, which then lies above the pages of the tests (with both tag widths), protects only the tags
MTAG_ALIAS_VA = MTAG_PAGE_VA + 0x1460_0000
# Svatag: with Sv39 the VITT range of U-mode (VU-mode) starts at svittu (vsvittu), and that of S-mode (VS-mode) at
# svitts (vsvitts) + VITT_RANGE_S_OFFSET, (2^64 - 2^38) >> 5 with 4-bit tags and >> 4 with 8-bit tags; both are
# VITT_RANGE_SIZE bytes, 2^38 >> 5 or >> 4. The 1 GiB region of MTAG_PAGES is mapped again that many bytes up (a root
# PTE to its level-1 table), so that a range that starts at one of the pages ends with the page before it again, and
# the page after the range is that page again.
VITT_RANGE_S_OFFSET = {MT_TAG4: ((1 << 64) - (1 << 38)) >> 5, MT_TAG7: ((1 << 64) - (1 << 38)) >> 4}
VITT_RANGE_SIZE = {MT_TAG4: 1 << 33, MT_TAG7: 1 << 34}
# The chunk of the user tagged-data page of the tag check in the VITT range of U-mode (_s_vitt_tests)
USER_VITT_OFFSET = 0x60
# A user alias of the code region (a gigapage, in a root slot that the other tests do not use), from which U-mode runs
# in _s_vitt_tests. It lies below the VITT ranges of U-mode there, which do not protect fetches anyway; S-mode takes the
# traps (the framework delegates them) and reads the trapping instructions with its own privilege, which has no range
U_CODE_VA = 0x1_0000_0000
# Svukte, which Svatag depends on: the lowest address of the upper half of the Sv39 address space, 2^64 - 2^38, with bit
# 63 set. _mtag_mapping maps the 1 GiB region of MTAG_PAGES again UPPER_HALF bytes up (a root PTE to its level-1 table)
# and _h_svukte_tests that of the guest pages, so that a tag table base UPPER_HALF above one of the lower half puts the
# same tags in the upper half
UPPER_HALF = (1 << 64) - (1 << 38)
# Entry points of MTAG_CODE, each followed by a return through the third register of the code: a load into the second
# register and a store of it through the first one, a checktag of the first one, and a load at the end of its first
# page, which straddles its two pages
MTAG_CODE_LOAD, MTAG_CODE_STORE, MTAG_CODE_CHECKTAG, MTAG_CODE_STRADDLE = 0x0, 0x8, 0x10, 0xFFE


def _mtag_va(page: str, offset: int = 0) -> int:
    """The virtual address of offset in page of MTAG_PAGES."""
    return MTAG_PAGE_VA + 0x1000 * MTAG_PAGES[page].slot + offset


def _mtag_pointer(page: str, offset: int, tag: int, mt_mode: int) -> int:
    """A pointer to offset in page with the pointer tag tag."""
    return _tag_field(tag, mt_mode) | _mtag_va(page, offset)


def _mtag_tag(page: str, offset: int, tag: int, mt_mode: int, regs: tuple[int, int]) -> list[str]:
    """Set the memory tag of the chunk at offset in page to tag, through the identity mapping of MTAG_TAGS. With 4-bit
    tags, the other chunk of its tag byte gets it too."""
    addr, val = regs
    byte = _tag_offset((_mtag_va(page, offset) - MTAG_PAGE_VA) >> 4, mt_mode)
    return [
        f"LA(x{addr}, {MTAG_TAGS} + {byte:#x})",
        f"LI(x{val}, {tag if mt_mode == MT_TAG7 else tag * 0x11:#x})",
        f"sb x{val}, 0(x{addr})",
    ]


def _mtag_mapping(test_data: TestData) -> list[str]:
    """Map the pages of MTAG_PAGES, and again MTAG_NONLEAF_VA through a level-1 non-leaf PTE with PTE.MTAG and
    MTAG_ALIAS_VA through one without it, which point to their level-0 page table, and their 1 GiB region
    VITT_RANGE_SIZE bytes up and UPPER_HALF bytes up, through root PTEs to its level-1 table. The checktag tests wrote
    the non-leaf PTEs above that table for SETTAG_VA."""
    a, b, c = test_data.int_regs.get_registers(3)
    regs = (a, b, c)
    lines = [
        comment_banner(
            "PTE.MTAG pages",
            f"Map the pages of the PTE.MTAG tests from {MTAG_PAGE_VA:#x}, and the data pages again behind a level-1\n"
            f"non-leaf PTE with PTE.MTAG from {MTAG_NONLEAF_VA:#x} and behind one without it from {MTAG_ALIAS_VA:#x}",
        ),
    ]
    for page in MTAG_PAGES.values():
        lines += write_pte(
            SV39,
            level=0,
            flags=page.flags,
            virtual_address=hex(MTAG_PAGE_VA + 0x1000 * page.slot),
            physical_address=page.physical,
            regs=regs,
        )
    lines += [
        *write_pte(
            SV39,
            level=1,
            flags=PteFlags.nonleaf(PTE_MTAG),
            virtual_address=hex(MTAG_NONLEAF_VA),
            physical_address=SV39.page_table_label(0),
            regs=regs,
        ),
        *write_pte(
            SV39,
            level=1,
            flags=PteFlags.nonleaf(),
            virtual_address=hex(MTAG_ALIAS_VA),
            physical_address=SV39.page_table_label(0),
            regs=regs,
        ),
        *[
            line
            for up in (*VITT_RANGE_SIZE.values(), UPPER_HALF)
            for line in write_pte(
                SV39,
                level=2,
                flags=PteFlags.nonleaf(),
                virtual_address=hex((MTAG_PAGE_VA + up) & MASK64),
                physical_address=SV39.page_table_label(1),
                regs=regs,
            )
        ],
        "sfence.vma",
    ]
    test_data.int_regs.return_registers(list(regs))
    return lines


def _mtag_data(code: tuple[int, int, int]) -> list[str]:
    """The pages of the PTE.MTAG tests, once per file: the data page, with the pattern of the check data where the tests
    access it (its first 80 bytes and last 16), the tags page, and the two code pages of MTAG_CODE, whose instructions
    use the registers code (pointer, value, return address)."""
    ptr, val, ret = code
    return [
        f".ifndef {MTAG_DATA}",
        ".p2align 12",
        f"{MTAG_DATA}:",
        *[f".dword {_check_data_dword(chunk, dword):#018x}" for chunk in range(5) for dword in range(2)],
        f".skip {0x1000 - 80 - 16}",
        *[f".dword {_check_data_dword(255, dword):#018x}" for dword in range(2)],
        f"{MTAG_TAGS}:",
        ".skip 0x1000",
        f"{MTAG_CODE}:",
        ".option push",
        ".option norvc",
        f"ld x{val}, 0(x{ptr})",
        f"jalr x0, 0(x{ret})",
        f"sd x{val}, 0(x{ptr})",
        f"jalr x0, 0(x{ret})",
        f"checktag x{ptr}, 0",
        f"jalr x0, 0(x{ret})",
        f".skip {MTAG_CODE_STRADDLE - 0x18}",
        f"ld x{val}, 0(x{ptr})",
        f"jalr x0, 0(x{ret})",
        ".option pop",
        f".skip {0x2000 - MTAG_CODE_STRADDLE - 8}",
        ".endif",
    ]


def _s_mtag_tests(test_data: TestData, cg: str, mt_mode: int, code: tuple[int, int, int]) -> list[str]:
    """Loads and stores in S-mode with Sv39 and memory tagging enabled with mt_mode, of the pages of MTAG_PAGES, whose
    tags svitts puts in the tags page: checked in a tagged-data page, not in a page with PTE.MTAG and X = 1 nor, with
    sstatus.SUM = 1, in a user tagged-data page; over two pages (with hardware misaligned loads and stores), checked in
    both if either is a supervisor tagged-data page; and not from a tagcheck-exempt code page, while checktag is. With
    4-bit tags also PTE.MTAG in a non-leaf PTE, and in a leaf PTE with memory tagging disabled. The S-mode trap handler,
    whose loads and stores are of pages without PTE.MTAG, takes the exceptions. code holds the registers of MTAG_CODE."""
    name = MT_NAMES[mt_mode]
    ptr, val, ret = code
    addr, tmp = test_data.int_regs.get_registers(2)
    good, bad = GOOD_TAG[mt_mode], BAD_TAG[mt_mode]
    # The tags of the user pages in the alias of the user tags page, so that the VITT range of U-mode, from svittu, is
    # above them
    svittu = _extended_vitt(_mtag_va("user_tags") + MTAG_ALIAS_VA - MTAG_PAGE_VA, MTAG_PAGE_VA, mt_mode)

    def tag(page: str, offset: int, value: int) -> list[str]:
        return _mtag_tag(page, offset, value, mt_mode, (addr, tmp))

    def load(case: str, coverpoint: str, page: str, offset: int, pointer_tag: int) -> list[str]:
        """ptr = a pointer to offset in page with pointer_tag; a load from it into val, which holds RD_CANARY before.
        Record val."""
        return [
            f"LI(x{ptr}, {_mtag_pointer(page, offset, pointer_tag, mt_mode):#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase(f"S_{name}_{case}", coverpoint, cg),
            f"ld x{val}, 0(x{ptr})",
            write_sigupd(val, test_data),
        ]

    def store(case: str, coverpoint: str, value: int, disp: int = 8) -> list[str]:
        """A store of value to ptr + disp."""
        return [
            f"LI(x{val}, {value:#x})",
            test_data.add_testcase(f"S_{name}_{case}", coverpoint, cg),
            f"sd x{val}, {disp}(x{ptr})",
        ]

    def record(offset: int) -> list[str]:
        """Record the doubleword at offset in MTAG_DATA, through the identity mapping."""
        return [f"LA(x{addr}, {MTAG_DATA} + {offset:#x})", f"ld x{tmp}, 0(x{addr})", write_sigupd(tmp, test_data)]

    def call(case: str, coverpoint: str, page: str, entry: int, value: int = RD_CANARY) -> list[str]:
        """Call entry of the code page page, with val = value."""
        return [
            f"LI(x{val}, {value:#x})",
            f"LI(x{tmp}, {_mtag_va(page, entry):#x})",
            test_data.add_testcase(f"S_{name}_{case}", coverpoint, cg),
            f"jalr x{ret}, 0(x{tmp})",
        ]

    sum_on = [f"LI(x{tmp}, SSTATUS_SUM)", f"csrs sstatus, x{tmp}"]
    sum_off = [f"LI(x{tmp}, SSTATUS_SUM)", f"csrc sstatus, x{tmp}"]
    lines = [
        comment_banner(
            f"cp_checked_tagged_page, cp_unchecked_page (S, {name})",
            f"In S-mode with Sv39, {TAG_BITS[mt_mode]}-bit tags and svitts putting the tags of the PTE.MTAG pages in\n"
            "their tags page: a load and a store of a tagged-data page (PTE.MTAG = 1, X = 0) with a mismatching\n"
            f"pointer tag: {SW_CHECK_TEXT}; with the matching one: performed. With a\n"
            "mismatching one, of a page with PTE.MTAG = 1 and X = 1, and (sstatus.SUM = 1) of a user tagged-data\n"
            "page: not checked. Record rd and memory",
        ),
        f"LI(x{tmp}, {_extended_vitt(_mtag_va('tags'), MTAG_PAGE_VA, mt_mode):#x})",
        f"csrw CSR_SVITTS, x{tmp}",
        *_set_pmm(tmp, "SMNPM"),
        f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{tmp}, x{tmp}, x{addr}",
        tsbi_call(f"csrs menvcfg, x{tmp}"),
        *tag("tagged", 0x10, good),
        *load("tagged_load_mismatch", "cp_checked_tagged_page", "tagged", 0x10, bad),
        *store("tagged_store_mismatch", "cp_checked_tagged_page", 0xFEDC_BA98_7654_3210),
        *record(0x18),
        *load("tagged_load_match", "cp_checked_tagged_page", "tagged", 0x10, good),
        *store("tagged_store_match", "cp_checked_tagged_page", 0x0123_4567_89AB_CDEF),
        *record(0x18),
        *tag("executable", 0x20, good),
        *load("executable_load", "cp_unchecked_page", "executable", 0x20, bad),
        *store("executable_store", "cp_unchecked_page", 0x1111_2222_3333_4444),
        *record(0x28),
        *sum_on,
        *tag("user", 0x20, good),
        *load("user_load", "cp_unchecked_page", "user", 0x20, bad),
        *store("user_store", "cp_unchecked_page", 0x5555_6666_7777_8888),
        *sum_off,
        *record(0x28),
    ]

    def regular(
        case: str, coverpoint: str, page: str, pointer_tag: int, arch: str, instructions: list[str]
    ) -> list[str]:
        """ptr = a pointer to MTAG_REGULAR_OFFSET in page with pointer_tag, val = RD_CANARY, then instructions (LR/SC or
        an AMO), assembled with arch. Record val."""
        return [
            f"LI(x{ptr}, {_mtag_pointer(page, MTAG_REGULAR_OFFSET, pointer_tag, mt_mode):#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            *_regular_access(test_data, cg, coverpoint, f"S_{name}_{case}", arch, instructions),
            write_sigupd(val, test_data),
        ]

    def cbo_zero(case: str, coverpoint: str, page: str, offset: int, pointer_tag: int) -> list[str]:
        """The cache block at MTAG_CBO_ZERO_OFFSET filled with CBO_ZERO_PATTERN (through the identity mapping), then
        cbo.zero through a pointer to offset in page with pointer_tag. Record its first and last doublewords."""
        return [
            f"LA(x{addr}, {MTAG_DATA} + {MTAG_CBO_ZERO_OFFSET:#x})",
            f"LI(x{tmp}, {CBO_ZERO_PATTERN:#x})",
            *[f"sd x{tmp}, {dword}(x{addr})" for dword in range(0, 64, 8)],
            f"LI(x{ptr}, {_mtag_pointer(page, offset, pointer_tag, mt_mode):#x})",
            *_regular_access(test_data, cg, coverpoint, f"S_{name}_{case}", "+zicboz", [f"cbo.zero (x{ptr})"]),
            *record(MTAG_CBO_ZERO_OFFSET),
            *record(MTAG_CBO_ZERO_OFFSET + 0x38),
        ]

    tagged, unchecked = "cp_checked_regular_tagged_page", "cp_unchecked_regular_page"
    # The SC stores the loaded value plus 1, so that the recorded memory shows that it is performed
    lr_sc = [f"lr.d x{tmp}, (x{ptr})", f"addi x{tmp}, x{tmp}, 1", f"sc.d x{val}, x{tmp}, (x{ptr})"]
    lines += [
        comment_banner(
            f"cp_checked_regular_tagged_page, cp_unchecked_regular_page (S, {name})",
            "LR, SC, the AMOs amoadd.d and amoswap.w and cbo.zero of the tagged-data page with a mismatching pointer\n"
            f"tag (cbo.zero also with only the last chunk of its block mismatching): {SW_CHECK_TEXT},\n"
            "rd and memory unchanged; with the matching one, an LR/SC pair, the AMOs and cbo.zero: performed. With a\n"
            "mismatching one, of the page with PTE.MTAG = 1 and X = 1: not checked. A misaligned amoadd.d with a\n"
            "mismatching pointer tag: its address-misaligned exception comes first, not checked. Record rd and memory",
        ),
        *tag("tagged", MTAG_REGULAR_OFFSET, good),
        *tag("executable", MTAG_REGULAR_OFFSET, good),
        *gated(
            [
                *regular("tagged_lr_mismatch", tagged, "tagged", bad, "+zalrsc", [f"lr.d x{val}, (x{ptr})"]),
                *regular("tagged_sc_mismatch", tagged, "tagged", bad, "+zalrsc", [f"sc.d x{val}, x{val}, (x{ptr})"]),
                *record(MTAG_REGULAR_OFFSET),
                *regular("tagged_lr_sc", tagged, "tagged", good, "+zalrsc", lr_sc),
                *record(MTAG_REGULAR_OFFSET),
                *regular("executable_lr_sc", unchecked, "executable", bad, "+zalrsc", lr_sc),
                *record(MTAG_REGULAR_OFFSET),
            ],
            "defined(ZALRSC_SUPPORTED)",
        ),
        *gated(
            [
                *regular(
                    "tagged_amoadd_d_mismatch", tagged, "tagged", bad, "+zaamo", [f"amoadd.d x{val}, x{val}, (x{ptr})"]
                ),
                *regular(
                    "tagged_amoswap_w_mismatch",
                    tagged,
                    "tagged",
                    bad,
                    "+zaamo",
                    [f"amoswap.w x{val}, x{val}, (x{ptr})"],
                ),
                *record(MTAG_REGULAR_OFFSET),
                *regular("tagged_amoadd_d", tagged, "tagged", good, "+zaamo", [f"amoadd.d x{val}, x{val}, (x{ptr})"]),
                *regular("tagged_amoswap_w", tagged, "tagged", good, "+zaamo", [f"amoswap.w x{val}, x{val}, (x{ptr})"]),
                *regular(
                    "executable_amoadd_d",
                    unchecked,
                    "executable",
                    bad,
                    "+zaamo",
                    [f"amoadd.d x{val}, x{val}, (x{ptr})"],
                ),
                *regular(
                    "executable_amoswap_w",
                    unchecked,
                    "executable",
                    bad,
                    "+zaamo",
                    [f"amoswap.w x{val}, x{val}, (x{ptr})"],
                ),
                *record(MTAG_REGULAR_OFFSET),
                # A misaligned AMO: with first-stage paging its address-misaligned exception (or, where misaligned AMOs
                # are supported, the access) comes before the tag check
                f"LI(x{ptr}, {_mtag_pointer('tagged', MTAG_REGULAR_OFFSET + 4, bad, mt_mode):#x})",
                f"LI(x{val}, {RD_CANARY:#x})",
                *_regular_access(
                    test_data,
                    cg,
                    tagged,
                    f"S_{name}_tagged_amoadd_d_misaligned_mismatch",
                    "+zaamo",
                    [f"amoadd.d x{val}, x{val}, (x{ptr})"],
                ),
                write_sigupd(val, test_data),
                *record(MTAG_REGULAR_OFFSET),
                *record(MTAG_REGULAR_OFFSET + 8),
            ],
            "defined(ZAAMO_SUPPORTED)",
        ),
        *gated(
            [
                *[
                    line
                    for offset in range(MTAG_CBO_ZERO_OFFSET, MTAG_CBO_ZERO_OFFSET + 64, 16)
                    for line in tag("tagged", offset, good)
                ],
                *cbo_zero("tagged_cbo_zero_mismatch", tagged, "tagged", MTAG_CBO_ZERO_OFFSET + 0x10, bad),
                *tag("tagged", MTAG_CBO_ZERO_OFFSET + 0x30, bad),
                *cbo_zero("tagged_cbo_zero_last_chunk_mismatch", tagged, "tagged", MTAG_CBO_ZERO_OFFSET, good),
                *tag("tagged", MTAG_CBO_ZERO_OFFSET + 0x30, good),
                *cbo_zero("tagged_cbo_zero", tagged, "tagged", MTAG_CBO_ZERO_OFFSET + 0x10, good),
                *cbo_zero("executable_cbo_zero", unchecked, "executable", MTAG_CBO_ZERO_OFFSET + 0x10, bad),
            ],
            "defined(ZICBOZ_SUPPORTED)",
        ),
    ]
    if mt_mode == MT_TAG4:
        lines += [
            comment_banner(
                "cp_mtag_nonleaf, cp_mtag_mt_disabled (S)",
                "A load and a store of the tagged-data page behind a level-1 non-leaf PTE with PTE.MTAG, which is\n"
                "reserved there: a load page fault and a store/AMO page fault. Then with memory tagging disabled\n"
                "(menvcfg.MT_MODE = 00), which ignores PTE.MTAG, a load and a store of the tagged-data page with a\n"
                "mismatching pointer tag: performed. Record rd and memory",
            ),
            f"LI(x{ptr}, {MTAG_NONLEAF_VA + 0x1000 * MTAG_PAGES['tagged'].slot + 0x10:#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase("S_nonleaf_load", "cp_mtag_nonleaf", cg),
            f"ld x{val}, 0(x{ptr})",
            write_sigupd(val, test_data),
            test_data.add_testcase("S_nonleaf_store", "cp_mtag_nonleaf", cg),
            f"sd x{val}, 8(x{ptr})",
            f"LI(x{tmp}, {0b11 << MT_MODE_LSB:#x})",
            tsbi_call(f"csrc menvcfg, x{tmp}"),
            *load("mt_disabled_load", "cp_mtag_mt_disabled", "tagged", 0x10, bad),
            *store("mt_disabled_store", "cp_mtag_mt_disabled", 0x9999_AAAA_BBBB_CCCC),
            *record(0x18),
            f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
            tsbi_call(f"csrs menvcfg, x{tmp}"),
        ]
    lines += gated(
        [
            comment_banner(
                f"cp_checked_straddle, cp_unchecked_straddle, cp_checked_straddle_fault (S, {name})",
                "Loads and stores over two pages: of a tagged-data page and a page without PTE.MTAG, which checks both,\n"
                "with the chunk in the second page mismatching, then matching; (sstatus.SUM = 1) of a user tagged-data\n"
                "page and a tagged-data page, which checks only the second one, with the chunk in the first page\n"
                "mismatching, then also the one in the second page; of a page without PTE.MTAG and a user\n"
                f"tagged-data page, which checks neither, with both mismatching: none, or a {SW_CHECK_TEXT}\n"
                "with no byte stored; and of the tags page, without PTE.MTAG, and a tagged-data page, which checks both,\n"
                "with the chunk in the first page mismatching, then matching. A load over a tagged-data page, with its\n"
                "chunk mismatching, and an unmapped page: the load page fault of the second page, at its first byte,\n"
                "as the check needs both pages. Record rd and memory",
            ),
            *tag("tagged", 0xFF0, good),
            *tag("untagged", 0x000, bad),
            *load("straddle_tagged_untagged_mismatch", "cp_checked_straddle", "tagged", 0xFFC, good),
            *store("straddle_tagged_untagged_store_mismatch", "cp_checked_straddle", 0xFEDC_BA98_7654_3210, 0),
            *record(0xFF8),
            *record(0x000),
            *tag("untagged", 0x000, good),
            *load("straddle_tagged_untagged", "cp_checked_straddle", "tagged", 0xFFC, good),
            *store("straddle_tagged_untagged_store", "cp_checked_straddle", 0x0123_4567_89AB_CDEF, 0),
            *record(0xFF8),
            *record(0x000),
            *sum_on,
            *tag("user", 0xFF0, bad),
            *tag("tagged_after_user", 0x000, good),
            *load("straddle_user_tagged", "cp_checked_straddle", "user", 0xFFC, good),
            *tag("tagged_after_user", 0x000, bad),
            *load("straddle_user_tagged_mismatch", "cp_checked_straddle", "user", 0xFFC, good),
            *tag("untagged", 0xFF0, bad),
            *tag("user", 0x000, bad),
            *load("straddle_untagged_user", "cp_unchecked_straddle", "untagged", 0xFFC, good),
            *sum_off,
            *tag("tags", 0xFF0, bad),
            *tag("tagged_before_unmapped", 0x000, good),
            *load("straddle_untagged_tagged_mismatch", "cp_checked_straddle", "tags", 0xFFC, good),
            *store("straddle_untagged_tagged_store_mismatch", "cp_checked_straddle", 0x2468_ACE0_1357_9BDF, 0),
            f"LA(x{addr}, {MTAG_TAGS} + 0xFF8)",
            f"ld x{tmp}, 0(x{addr})",
            write_sigupd(tmp, test_data),
            *record(0x000),
            *tag("tags", 0xFF0, good),
            *load("straddle_untagged_tagged", "cp_checked_straddle", "tags", 0xFFC, good),
            *tag("tagged_before_unmapped", 0xFF0, bad),
            *load("straddle_unmapped", "cp_checked_straddle_fault", "tagged_before_unmapped", 0xFFC, good),
        ],
        PAGE_CROSSING_GATE,
    )
    lines += [
        comment_banner(
            f"cp_mtag_code_access, cp_mtag_code_checktag, cp_mtag_code_straddle (S, {name})",
            "Through a pointer with a mismatching tag to the tagged-data page: a load and a store from a\n"
            "tagcheck-exempt code page (PTE.MTAG = 1, X = 1): not checked; checktag from it: a software-check\n"
            "exception; the same load and store from a code page without PTE.MTAG: checked, and from an\n"
            "execute-only tagcheck-exempt code page (R = 0): not checked. Then (Zca) the load at the end of the first\n"
            "code page, which straddles it and the next one: checked if that one has no PTE.MTAG, not if it is\n"
            "tagcheck-exempt too. Record rd and memory",
        ),
        *tag("tagged", 0x30, good),
        f"LI(x{ptr}, {_mtag_pointer('tagged', 0x30, bad, mt_mode):#x})",
        *call("exempt_load", "cp_mtag_code_access", "exempt", MTAG_CODE_LOAD),
        write_sigupd(val, test_data),
        *call("exempt_store", "cp_mtag_code_access", "exempt", MTAG_CODE_STORE, 0x1357_9BDF_0246_8ACE),
        *record(0x30),
        *call("exempt_checktag", "cp_mtag_code_checktag", "exempt", MTAG_CODE_CHECKTAG),
        *call("normal_code_load", "cp_mtag_code_access", "normal_code", MTAG_CODE_LOAD),
        write_sigupd(val, test_data),
        *call("normal_code_store", "cp_mtag_code_access", "normal_code", MTAG_CODE_STORE, 0x0246_8ACE_1357_9BDF),
        *record(0x30),
        *call("exempt_execute_only_load", "cp_mtag_code_access", "exempt_execute_only", MTAG_CODE_LOAD),
        write_sigupd(val, test_data),
        *call(
            "exempt_execute_only_store",
            "cp_mtag_code_access",
            "exempt_execute_only",
            MTAG_CODE_STORE,
            0x0F1E_2D3C_4B5A_6978,
        ),
        *record(0x30),
        *gated(
            [
                *call("straddle_exempt_normal", "cp_mtag_code_straddle", "exempt", MTAG_CODE_STRADDLE),
                write_sigupd(val, test_data),
                *call("straddle_exempt_exempt", "cp_mtag_code_straddle", "exempt2", MTAG_CODE_STRADDLE),
                write_sigupd(val, test_data),
            ],
            "defined(ZCA_SUPPORTED)",
        ),
        f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        tsbi_call(f"csrc menvcfg, x{tmp}"),
    ]

    def mprv_u_load(case: str, page: str, pointer_tag: int) -> list[str]:
        """In M-mode, a load with mstatus.MPRV = 1 and MPP = U from offset 0x40 in page with pointer_tag. Record rd."""
        return [
            f"LI(x{ptr}, {_mtag_pointer(page, 0x40, pointer_tag, mt_mode):#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{tmp}, MSTATUS_MPRV)",
            f"csrs mstatus, x{tmp}",
            test_data.add_testcase(f"M_{name}_{case}", "cp_checked_mprv_u_page", "Zimt_Sm_cg"),
            f"ld x{val}, 0(x{ptr})",
            f"csrc mstatus, x{tmp}",
            write_sigupd(val, test_data),
        ]

    lines += gated(
        [
            comment_banner(
                f"cp_checked_mprv_u_page (M, {name})",
                "In M-mode with mstatus.MPRV = 1 and MPP = U, so with the Sv39 translation, memory tagging\n"
                "(senvcfg.MT_MODE) and tag table (svittu, the tags page as a user page, at MTAG_ALIAS_VA) of U-mode:\n"
                "a load of the user\n"
                f"tagged-data page with a mismatching pointer tag: {SW_CHECK_TEXT}, which M-mode\n"
                "takes; with the matching one: performed; and with a mismatching one, of a user page without\n"
                "PTE.MTAG: not checked. Record rd",
            ),
            f"LI(x{tmp}, {svittu:#x})",
            f"csrw CSR_SVITTU, x{tmp}",
            *_set_pmm(tmp, "SSNPM"),
            f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{tmp}, x{tmp}, x{addr}",
            f"csrs senvcfg, x{tmp}",
            *tag("user", 0x40, good),
            *tag("user_untagged", 0x40, good),
            "RVTEST_TSBI_GOTO_MMODE",
            *mprv_u_load("mprv_u_mismatch", "user", bad),
            *mprv_u_load("mprv_u_match", "user", good),
            *mprv_u_load("mprv_u_untagged", "user_untagged", bad),
            "RVTEST_TSBI_GOTO_SMODE",
            f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{tmp}",
            "csrw CSR_SVITTU, x0",
        ],
        "defined(U_SUPPORTED) && defined(SSNPM_SUPPORTED) && defined(STANDARD_SM_SUPPORTED)",
    )
    test_data.int_regs.return_registers([addr, tmp])
    return lines


def _u_code_alias(regs: tuple[int, int, int]) -> list[str]:
    """Map U_CODE_VA, a user alias of the code region, and register it as the alias of the code region in the S save
    area of the trap handler: RVTEST_TSBI_GOTO_UMODE then resumes there, and RVTEST_TSBI_GOTO_SMODE back in the code
    region, until _u_code_alias_off."""
    pte, addr, tmp = regs
    shift = SV39.page_offset_bits(SV39.levels - 1)
    return [
        *write_pte(
            SV39,
            level=SV39.levels - 1,
            flags=PteFlags(user=True, write=False),
            virtual_address=hex(U_CODE_VA),
            physical_address="rvtest_code_begin",
            regs=regs,
            superpage=True,
        ),
        "sfence.vma",
        f"LI(x{pte}, {U_CODE_VA:#x})",
        f"LA(x{tmp}, rvtest_code_begin)",
        f"slli x{tmp}, x{tmp}, {64 - shift}",
        f"srli x{tmp}, x{tmp}, {64 - shift}",
        f"or x{pte}, x{pte}, x{tmp}",
        f"LA(x{addr}, Stramptbl_sv)",
        f"SREG x{pte}, code_bgn_off(x{addr})",
    ]


def _u_code_alias_off(regs: tuple[int, int]) -> list[str]:
    """Unregister the alias of the code region of _u_code_alias."""
    addr, tmp = regs
    return [f"LA(x{addr}, rvtest_code_begin)", f"LA(x{tmp}, Stramptbl_sv)", f"SREG x{addr}, code_bgn_off(x{tmp})"]


def _s_vitt_tests(test_data: TestData, cg: str, mt_mode: int, code: tuple[int, int, int]) -> list[str]:
    """Protection of tag storage (Svatag) in S-mode with Sv39 and memory tagging enabled with mt_mode: svitts puts the
    VITT range of S-mode at the tags page of MTAG_PAGES, so that the executable page before it is not in it, its last
    page is the executable page again (VITT_RANGE_SIZE bytes up), and the page after it the tags page again. A load and
    a store in its first page, a load through sp there, LR, SC (reserved by an LR of the same address through the page
    after, which is performed), amoadd.d and cbo.zero there, a load in its last page, and (with hardware misaligned
    loads) loads from the page before into the first page and from the last page into the page after raise the access
    fault of their kind, with the address of their first byte in the range; loads in the page before and in the page
    after are performed. In the tagged-data page after the first one the tag check comes first (its tag address is not
    canonical: a load page fault on it), and in the unmapped page after that its page fault. settag of a chunk in the
    first page, of the last chunk of the page before and the first one of the range, or of the last chunk of the range
    and the first one of the page after, raises a store/AMO access fault with its address, and so does settag of 16
    chunks from the page before, of which only the last one is in the range; of the last chunk of the page before alone,
    it raises the store/AMO page fault of its tag store, whose address is not canonical. A store from the page before
    into the first page (with hardware misaligned stores performed byte by byte, which store its bytes in the page
    before first) raises the store/AMO access fault at the first page. With memory tagging disabled, a load in the first
    page is performed. Then, in M-mode with mstatus.MPRV = 1 and MPP = U, with svittu putting the VITT range of U-mode
    at the user tags page: the same loads, the user page without PTE.MTAG before it, a load in the first page with
    mstatus.MTAG_I = 1 (a load access fault), and (V) vle64.v and vse64.v there (a load and a store/AMO access fault at
    element 0); then, with svittu putting the range over the MTAG pages, a load of the user tagged-data page in it with
    the matching pointer tag (its tag check passes: the access fault), with a mismatching one (the software-check
    exception) and with a mismatching one and mstatus.MTAG_I = 1 (unchecked: the access fault). Then U-mode itself,
    from a user alias of the code region (U_CODE_VA), with svittu putting the range at the user tags page again: settag
    and a load in its first page raise a store/AMO and a load access fault. The pages that these accesses perform are
    not tagged-data pages. The load, store, cbo.zero and settag in the first page of the S-mode range, and the first
    load, vle64.v and the U-mode settag and load of the U-mode range use a pointer with a pointer tag, which pointer
    masking ignores. Record rd, the memory that the faulting sd, sc.d, amoadd.d and cbo.zero (whose cache block holds a pattern
    before) would write, through the page after the range, vd of vle64.v (which holds a pattern) and the memory of
    vse64.v. code holds the registers of MTAG_CODE."""
    name = MT_NAMES[mt_mode]
    ptr, val, _ = code
    addr, tmp = test_data.int_regs.get_registers(2)
    up = VITT_RANGE_SIZE[mt_mode]
    first, before = _mtag_va("tags"), _mtag_va("executable")
    tagged, unmapped = _mtag_va("tagged_before_unmapped"), _mtag_va("tagged_before_unmapped") + 0x1000
    # The pointer tag of some cases, which pointer masking ignores: the range applies to the masked address
    tag = SETTAG_TAG[mt_mode]

    def access(
        case: str, coverpoint: str, cgroup: str, va: int, instruction: str, arch: str = "", tag: int = 0
    ) -> list[str]:
        """ptr = va with pointer tag tag, val = RD_CANARY, then instruction (assembled with the extensions arch, if
        any) labeled as the testcase case. Record val."""
        lines = [f"LI(x{ptr}, {_tag_field(tag, mt_mode) | va:#x})", f"LI(x{val}, {RD_CANARY:#x})"]
        if arch:
            lines += _regular_access(test_data, cgroup, coverpoint, case, arch, [instruction])
        else:
            lines += [test_data.add_testcase(case, coverpoint, cgroup), instruction]
        return [*lines, write_sigupd(val, test_data)]

    def s(case: str, va: int, instruction: str = f"ld x{val}, 0(x{ptr})", arch: str = "", tag: int = 0) -> list[str]:
        return access(f"S_{name}_vitt_{case}", "cp_vitt", cg, va, instruction, arch, tag)

    def record(offset: int) -> list[str]:
        """Record the doubleword at offset in the tags page, through the page after the range: whether a store that
        faulted wrote it. Its tags page offsets 0x18-0x27 and 0x840-0x87F hold no tags."""
        return [f"LI(x{tmp}, {first + up + offset:#x})", f"ld x{val}, 0(x{tmp})", write_sigupd(val, test_data)]

    def cbo_zero() -> list[str]:
        """cbo.zero in the first page, whose cache block, through the page after the range, holds a nonzero pattern
        before, is recorded after, and holds zeros again."""
        block = first + up + 0x840
        case = [
            f"LI(x{tmp}, {block:#x})",
            f"LI(x{val}, {CBO_ZERO_PATTERN:#x})",
            *[f"sd x{val}, {8 * i}(x{tmp})" for i in range(8)],
            *s("cbo_zero_first", first + 0x848, f"cbo.zero (x{ptr})", "+zicboz", tag=tag),
            f"LI(x{tmp}, {block:#x})",
        ]
        case += [line for i in range(8) for line in (f"ld x{val}, {8 * i}(x{tmp})", write_sigupd(val, test_data))]
        return [*case, *[f"sd x0, {8 * i}(x{tmp})" for i in range(8)]]

    def s_sp(case: str, va: int) -> list[str]:
        """A load through sp = va, which the protection does not exempt (the trap handlers swap sp). Record val."""
        return [
            f"LI(x{ptr}, {va:#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            f"mv x{addr}, sp",
            f"mv sp, x{ptr}",
            test_data.add_testcase(f"S_{name}_vitt_{case}", "cp_vitt", cg),
            f"ld x{val}, 0(sp)",
            f"mv sp, x{addr}",
            write_sigupd(val, test_data),
        ]

    lines = [
        comment_banner(
            f"cp_vitt (S, {name})",
            f"In S-mode with Sv39 and {TAG_BITS[mt_mode]}-bit tags, with svitts putting the VITT range of S-mode\n"
            f"({VITT_RANGE_SIZE[mt_mode]:#x} bytes from svitts + {VITT_RANGE_S_OFFSET[mt_mode]:#x}) at the tags page:\n"
            "regular accesses in the range raise the access fault of their kind, after their page fault and their\n"
            "tag check, and those before and after it none; settag of chunks in it a store/AMO access fault. Record rd",
        ),
        *_set_pmm(tmp, "SMNPM"),
        f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{tmp}, x{tmp}, x{addr}",
        tsbi_call(f"csrs menvcfg, x{tmp}"),
        f"LI(x{tmp}, {(first - VITT_RANGE_S_OFFSET[mt_mode]) & MASK64:#x})",
        f"csrw CSR_SVITTS, x{tmp}",
        *s("ld_first", first + 0x10, tag=tag),
        *s("sd_first", first + 0x18, f"sd x{val}, 0(x{ptr})", tag=tag),
        *record(0x18),
        *s_sp("ld_sp_first", first + 0x28),
        *s("ld_before", before + 0xFF8),
        *s("ld_last", before + up + 0xFF8),
        *s("ld_after", first + up + 0x10),
        *s("ld_tag_check", tagged + 0x10),
        *s("ld_unmapped", unmapped + 0x10),
        *gated(
            [
                *s("ld_into_first", before + 0xFFC),
                *s("ld_out_of_last", before + up + 0xFFC),
                # Its bytes in the page before are stored first (byte by byte): record them and restore the data
                *s("sd_into_first", before + 0xFFC, f"sd x{val}, 0(x{ptr})"),
                f"LI(x{tmp}, {before + 0xFF8:#x})",
                f"ld x{val}, 0(x{tmp})",
                write_sigupd(val, test_data),
                f"LI(x{val}, {_check_data_dword(255, 1):#x})",
                f"sd x{val}, 0(x{tmp})",
            ],
            PAGE_CROSSING_GATE,
        ),
        *gated(
            [
                *s("lr_first", first + 0x20, f"lr.d x{val}, (x{ptr})", "+zalrsc"),
                # The SC has a reservation, from an LR of the same physical address through the page after the range,
                # so that it may not fail without the access fault ("a failed SC may be treated like a store")
                *s("lr_after", first + up + 0x20, f"lr.d x{val}, (x{ptr})", "+zalrsc"),
                *s("sc_first", first + 0x20, f"sc.d x{val}, x{val}, (x{ptr})", "+zalrsc"),
                *record(0x20),
            ],
            "defined(ZALRSC_SUPPORTED)",
        ),
        *gated(
            [*s("amoadd_d_first", first + 0x20, f"amoadd.d x{val}, x{val}, (x{ptr})", "+zaamo"), *record(0x20)],
            "defined(ZAAMO_SUPPORTED)",
        ),
        *gated(cbo_zero(), "defined(ZICBOZ_SUPPORTED)"),
        *s("settag_first", first + 0x10, f"settag x{ptr}, 0", tag=tag),
        *s("settag_into_first", before + 0xFF8, f"settag x{ptr}, 1"),
        *s("settag_out_of_last", before + up + 0xFF8, f"settag x{ptr}, 1"),
        *s("settag_before", before + 0xFF8, f"settag x{ptr}, 0"),
        *s("settag_16_into_first", before + 0xF10, f"settag x{ptr}, 15"),
        # With memory tagging disabled, there is no VITT range
        f"LI(x{tmp}, {0b11 << MT_MODE_LSB:#x})",
        tsbi_call(f"csrc menvcfg, x{tmp}"),
        *access(
            f"S_{name}_vitt_ld_first_mt_disabled", "cp_vitt_mt_disabled", cg, first + 0x10, f"ld x{val}, 0(x{ptr})"
        ),
        "csrw CSR_SVITTS, x0",
        f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        tsbi_call(f"csrc menvcfg, x{tmp}"),
    ]

    def mprv_u_load(
        case: str,
        va: int,
        instruction: str = f"ld x{val}, 0(x{ptr})",
        arch: str = "",
        coverpoint: str = "cp_vitt_mprv_u",
        mtag_i: bool = False,
        ptag: int = 0,
    ) -> list[str]:
        """In M-mode, instruction (a load by default; assembled with the extensions arch, if any) with mstatus.MPRV = 1
        and MPP = U (and with mtag_i mstatus.MTAG_I = 1, which only disables tag checks) through ptr = va with pointer
        tag ptag. Record val."""
        mstatus = f"MSTATUS_MPRV{f' | {1 << MSTATUS_MTAG_I_BIT:#x}' if mtag_i else ''}"
        lines = [
            f"LI(x{ptr}, {_tag_field(ptag, mt_mode) | va:#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{tmp}, {mstatus})",
            f"csrs mstatus, x{tmp}",
        ]
        if arch:
            lines += _regular_access(
                test_data, "Zimt_Sm_cg", coverpoint, f"M_{name}_vitt_u_{case}", arch, [instruction]
            )
        else:
            lines += [test_data.add_testcase(f"M_{name}_vitt_u_{case}", coverpoint, "Zimt_Sm_cg"), instruction]
        return [*lines, f"csrc mstatus, x{tmp}", write_sigupd(val, test_data)]

    u_first, u_before = _mtag_va("user_tags"), _mtag_va("user_untagged")
    lines += gated(
        [
            comment_banner(
                f"cp_vitt_mprv_u (M, U, {name})",
                "In M-mode with mstatus.MPRV = 1 and MPP = U, with Sv39, memory tagging (senvcfg.MT_MODE) and svittu\n"
                "putting the VITT range of U-mode at the user tags page: loads in its first and last pages, and from\n"
                "the page before into the first one and from the last one into the page after, raise a load access\n"
                "fault, which M-mode takes; those in the user page before it and in the page after it none. Record rd",
            ),
            f"LI(x{tmp}, {u_first:#x})",
            f"csrw CSR_SVITTU, x{tmp}",
            *_set_pmm(tmp, "SSNPM"),
            f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{tmp}, x{tmp}, x{addr}",
            f"csrs senvcfg, x{tmp}",
            "RVTEST_TSBI_GOTO_MMODE",
            *mprv_u_load("first", u_first + 0x10, ptag=tag),
            *mprv_u_load("before", u_before + 0xFF8),
            *mprv_u_load("last", u_before + up + 0xFF8),
            *mprv_u_load("after", u_first + up + 0x10),
            *gated(
                [*mprv_u_load("into_first", u_before + 0xFFC), *mprv_u_load("out_of_last", u_before + up + 0xFFC)],
                PAGE_CROSSING_GATE,
            ),
            *mprv_u_load("first_mtag_i", u_first + 0x18, coverpoint="cp_vitt_mtag_i", mtag_i=True),
            # A tag check that passes in the range comes before the access fault: svittu without the alias of
            # _mtag_mapping puts the range over the MTAG pages and the tags of their chunks in the user tags page. A
            # load of the user tagged-data page with the matching pointer tag raises the load access fault, with a
            # mismatching one the software-check exception
            f"LI(x{tmp}, {_extended_vitt(u_first, MTAG_PAGE_VA, mt_mode):#x})",
            f"csrw CSR_SVITTU, x{tmp}",
            *_mtag_tag("user", USER_VITT_OFFSET, GOOD_TAG[mt_mode], mt_mode, (addr, tmp)),
            *mprv_u_load("tagged_match", _mtag_va("user", USER_VITT_OFFSET), ptag=GOOD_TAG[mt_mode]),
            *mprv_u_load("tagged_mismatch", _mtag_va("user", USER_VITT_OFFSET), ptag=BAD_TAG[mt_mode]),
            *mprv_u_load(
                "tagged_mtag_i",
                _mtag_va("user", USER_VITT_OFFSET),
                coverpoint="cp_vitt_mtag_i",
                mtag_i=True,
                ptag=BAD_TAG[mt_mode],
            ),
            f"LI(x{tmp}, {u_first:#x})",
            f"csrw CSR_SVITTU, x{tmp}",
            *gated(
                [
                    f"LI(x{tmp}, MSTATUS_VS)",
                    f"csrs mstatus, x{tmp}",
                    ".option push",
                    ".option arch, +v",
                    "vsetivli x0, 2, e64, m1, ta, ma",
                    f"LI(x{val}, {VECTOR_PATTERN[0]:#x})",
                    f"vmv.v.x v24, x{val}",
                    ".option pop",
                    *mprv_u_load("vle_first", u_first + 0x20, f"vle64.v v24, (x{ptr})", "+v", ptag=tag),
                    *_record_vreg(test_data, val, 24),
                    *mprv_u_load("vse_first", u_first + 0x30, f"vse64.v v24, (x{ptr})", "+v"),
                    # The doublewords of vse64.v, through the identity mapping of the tags page
                    f"LA(x{tmp}, {MTAG_TAGS} + 0x30)",
                    *[line for i in range(2) for line in (f"ld x{val}, {8 * i}(x{tmp})", write_sigupd(val, test_data))],
                ],
                "defined(V_SUPPORTED)",
            ),
            "RVTEST_TSBI_GOTO_SMODE",
            f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{tmp}",
            "csrw CSR_SVITTU, x0",
        ],
        "defined(U_SUPPORTED) && defined(SSNPM_SUPPORTED) && defined(STANDARD_SM_SUPPORTED)",
    )
    # U-mode itself runs from U_CODE_VA, the alias of the code region meanwhile (_u_code_alias). The signature is not a
    # user page, so S-mode records rd
    lines += gated(
        [
            comment_banner(
                f"cp_vitt_u (U, {name})",
                "In U-mode with Sv39 and memory tagging (senvcfg.MT_MODE), from a user alias of the code region, with\n"
                "svittu putting the VITT range of U-mode at the user tags page: settag and a load in its first page\n"
                "raise a store/AMO and a load access fault. Record rd",
            ),
            *_u_code_alias((addr, tmp, val)),
            f"LI(x{tmp}, {u_first:#x})",
            f"csrw CSR_SVITTU, x{tmp}",
            *_set_pmm(tmp, "SSNPM"),
            f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{tmp}, x{tmp}, x{addr}",
            f"csrs senvcfg, x{tmp}",
            "RVTEST_TSBI_GOTO_UMODE",
            f"LI(x{ptr}, {_tag_field(tag, mt_mode) | (u_first + 0x28):#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase(f"U_{name}_vitt_settag_first", "cp_vitt_u", "Zimt_U_cg"),
            f"settag x{ptr}, 0",
            test_data.add_testcase(f"U_{name}_vitt_ld_first", "cp_vitt_u", "Zimt_U_cg"),
            f"ld x{val}, 0(x{ptr})",
            "RVTEST_TSBI_GOTO_SMODE",
            write_sigupd(val, test_data),
            f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{tmp}",
            "csrw CSR_SVITTU, x0",
            *_u_code_alias_off((addr, tmp)),
        ],
        "defined(U_SUPPORTED) && defined(SSNPM_SUPPORTED)",
    )
    test_data.int_regs.return_registers([addr, tmp])
    return lines


def _s_svukte_tests(test_data: TestData, cg: str, mt_mode: int, code: tuple[int, int, int]) -> list[str]:
    """Svukte, which Svatag depends on: Svatag assumes the even split of the address space that Svukte enforces, U-mode
    in the lower half and S-mode in the upper half (the VITT ranges of _s_vitt_tests). The tag accesses of the loads,
    stores, checktag and settag of U-mode are explicit accesses, which Svukte qualifies: with senvcfg.UKTE, one in the
    upper half raises the page fault of its kind (a load page fault, a store/AMO page fault for settag) at the tag
    address, so the tag table of U-mode must be in the lower half. In U-mode, from U_CODE_VA, with Sv39, memory tagging
    enabled with mt_mode and svittu putting the tags of the user tagged-data page of MTAG_PAGES in the upper alias of the
    user tags page (UPPER_HALF above the svittu of _s_mtag_tests): checktag, a load and settag of a chunk there are
    performed with UKTE = 0 (settag storing the mismatching tag), and raise the page faults with UKTE = 1 (settag storing
    no tag); with that svittu, in the lower half, the load is performed with UKTE = 1. A load of the upper alias of the
    page raises the load page fault at its own address with UKTE = 1, before its tag check, and with UKTE = 0 at its tag
    address, which is not canonical: the tag table of U-mode holds the tags of the lower half only. Then in M-mode with
    mstatus.MPRV = 1 and MPP = U, a load there raises the page fault at its tag address in the upper half with UKTE = 1,
    and is performed with UKTE = 0. Record rd, and the tag of the chunk after each settag. code holds the registers of
    MTAG_CODE."""
    name = MT_NAMES[mt_mode]
    ptr, val, _ = code
    addr, tmp = test_data.int_regs.get_registers(2)
    good, bad = GOOD_TAG[mt_mode], BAD_TAG[mt_mode]
    offset = 0x40
    va = _mtag_va("user", offset)
    svittu = _extended_vitt(_mtag_va("user_tags") + MTAG_ALIAS_VA - MTAG_PAGE_VA, MTAG_PAGE_VA, mt_mode)
    svittu_up = (svittu + UPPER_HALF) & MASK64
    tag_byte = _tag_offset((va - MTAG_PAGE_VA) >> 4, mt_mode)

    def ukte(on: bool) -> list[str]:
        return [f"LI(x{tmp}, SENVCFG_UKTE)", f"csr{'s' if on else 'c'} senvcfg, x{tmp}"]

    def svittu_is(value: int) -> list[str]:
        return [f"LI(x{tmp}, {value:#x})", f"csrw CSR_SVITTU, x{tmp}"]

    def u(case: str, instruction: str, pointer: int) -> list[str]:
        """In U-mode, instruction with ptr = pointer and val = RD_CANARY."""
        return [
            f"LI(x{ptr}, {pointer:#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase(f"U_{name}_svukte_{case}", "cp_svukte_tag", "Zimt_U_cg"),
            instruction,
        ]

    def record_tag() -> list[str]:
        """Record the tag byte of the chunk, through the identity mapping of the tags page."""
        return [f"LA(x{addr}, {MTAG_TAGS} + {tag_byte:#x})", f"lbu x{tmp}, 0(x{addr})", write_sigupd(tmp, test_data)]

    good_ptr, bad_ptr = _tag_field(good, mt_mode) | va, _tag_field(bad, mt_mode) | va
    up_ptr = (va + UPPER_HALF) & MASK64
    load, check, set_ = f"ld x{val}, 0(x{ptr})", f"checktag x{ptr}, 0", f"settag x{ptr}, 0"
    lines = gated(
        [
            comment_banner(
                f"cp_svukte_tag (U, {name})",
                "In U-mode with Sv39 and memory tagging, from a user alias of the code region, with svittu putting the\n"
                "tags of the user tagged-data page in the upper half: checktag, a load and settag of a chunk there are\n"
                "performed with senvcfg.UKTE = 0, and raise the page fault of their tag access with UKTE = 1; with the\n"
                "tag table in the lower half, the load is performed. A load of the upper alias of the page: with\n"
                "UKTE = 1 a page fault at its address, with UKTE = 0 at its tag address (not canonical). Record rd\n"
                "and the tag",
            ),
            *_u_code_alias((addr, tmp, val)),
            *svittu_is(svittu_up),
            *_set_pmm(tmp, "SSNPM"),
            f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
            f"or x{tmp}, x{tmp}, x{addr}",
            f"csrs senvcfg, x{tmp}",
            *ukte(False),
            *_mtag_tag("user", offset, good, mt_mode, (addr, tmp)),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("checktag_upper", check, good_ptr),
            *u("ld_upper", load, good_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            write_sigupd(val, test_data),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("settag_upper", set_, bad_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            *record_tag(),
            *_mtag_tag("user", offset, good, mt_mode, (addr, tmp)),
            *ukte(True),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("checktag_upper_ukte", check, good_ptr),
            *u("ld_upper_ukte", load, good_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            write_sigupd(val, test_data),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("settag_upper_ukte", set_, bad_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            *record_tag(),
            *svittu_is(svittu),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("ld_lower_ukte", load, good_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            write_sigupd(val, test_data),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("ld_upper_address_ukte", load, up_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            write_sigupd(val, test_data),
            *ukte(False),
            "RVTEST_TSBI_GOTO_UMODE",
            *u("ld_upper_address", load, up_ptr),
            "RVTEST_TSBI_GOTO_SMODE",
            write_sigupd(val, test_data),
            *_u_code_alias_off((addr, tmp)),
        ],
        "defined(U_SUPPORTED) && defined(SSNPM_SUPPORTED)",
    )

    def mprv_u_load(case: str) -> list[str]:
        """In M-mode, a load with mstatus.MPRV = 1 and MPP = U of the chunk, with val = RD_CANARY. Record val."""
        return [
            f"LI(x{ptr}, {good_ptr:#x})",
            f"LI(x{val}, {RD_CANARY:#x})",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{tmp}, MSTATUS_MPRV)",
            f"csrs mstatus, x{tmp}",
            test_data.add_testcase(f"M_{name}_svukte_{case}", "cp_svukte_tag_mprv", "Zimt_Sm_cg"),
            load,
            f"csrc mstatus, x{tmp}",
            write_sigupd(val, test_data),
        ]

    lines += gated(
        [
            comment_banner(
                f"cp_svukte_tag_mprv (M, {name})",
                "In M-mode with mstatus.MPRV = 1 and MPP = U, with svittu putting the tags of the user tagged-data page\n"
                "in the upper half: a load of a chunk there raises the page fault of its tag access with\n"
                "senvcfg.UKTE = 1, and is performed with UKTE = 0. Record rd",
            ),
            *svittu_is(svittu_up),
            *ukte(True),
            "RVTEST_TSBI_GOTO_MMODE",
            *mprv_u_load("mprv_u_ld_upper_ukte"),
            *ukte(False),
            *mprv_u_load("mprv_u_ld_upper"),
            "RVTEST_TSBI_GOTO_SMODE",
        ],
        "defined(U_SUPPORTED) && defined(SSNPM_SUPPORTED) && defined(STANDARD_SM_SUPPORTED)",
    )
    lines += gated(
        [
            f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            f"csrc senvcfg, x{tmp}",
            "csrw CSR_SVITTU, x0",
        ],
        "defined(U_SUPPORTED) && defined(SSNPM_SUPPORTED)",
    )
    test_data.int_regs.return_registers([addr, tmp])
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
    """With two-stage translation, whose first-stage paging makes only PTE.MTAG pages tagged-data pages: in VS-mode, a
    load and a store of the valid tag page, whose VS-stage leaf PTE has no PTE.MTAG, with a mismatching pointer tag,
    which are not tag checked."""
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


# The VS-stage tagged-data page of the two-stage tests: a guest virtual page after VS_SV39.data_va, which maps a guest
# physical page that the G stage maps to the check data. vsvitts puts the tags of its chunks in the tag page of the
# two-stage checktag tests, which VS_SV39.data_va maps. Zimt_coverage.svh identifies it by its address.
VS_MTAG_VA = int(VS_SV39.data_va, 16) + 0x1000
# The guest page before it, the tag page, which has no PTE.MTAG
VS_TAG_PAGE_VA = int(VS_SV39.data_va, 16)
VS_MTAG_GPA = int(SV39X4.data_va, 16) + 0x2000
VS_MTAG_CHUNK = 5
# A guest physical page whose G-stage leaf PTE has PTE.MTAG, which is reserved there. Zimt_coverage.svh identifies it by
# its address.
G_MTAG_GPA = int(SV39X4.data_va, 16) + 0x1000
# The guest pages of the HLV/HSV tests with two-stage translation, of MPRV with MPV = 1 and MPP = U, and of the VS-stage
# code pages, after VS_MTAG_VA: a page without PTE.MTAG right after it (for an access over both); a user tagged-data
# page and a user page without PTE.MTAG; a page that the VS stage does not map, and one whose guest physical page
# G_FAULT_GPA the G stage does not map (the tag pages of tag-load faults); and the VS-stage code pages, tagcheck-exempt
# and without PTE.MTAG, which map VS_CODE_GPA, the guest physical page that the G stage maps to the code page of
# _vs_code_page. The data pages map VS_MTAG_GPA. vsvitts and vsvittu put the tags of all their chunks in the tag page
# that VS_SV39.data_va maps. Zimt_coverage.svh identifies the pages by their addresses.
VS_PLAIN_VA = VS_MTAG_VA + 0x1000
VS_USER_MTAG_VA = VS_MTAG_VA + 0x2000
VS_USER_VA = VS_MTAG_VA + 0x3000
VS_FAULT_VA = VS_MTAG_VA + 0x4000
VS_G_FAULT_VA = VS_MTAG_VA + 0x5000
VS_EXEMPT_CODE_VA = VS_MTAG_VA + 0x6000
VS_NORMAL_CODE_VA = VS_MTAG_VA + 0x7000
# The tag page that VS_SV39.data_va maps, again as a user page, for the tag loads of VU-mode; it is in another 2 MiB
# region, whose VS-stage level-1 PTE points to the level-0 table of the guest pages (VS_SV39 has one table per level),
# so that the VITT range of VU-mode (Svatag), from vsvittu, lies above the guest pages with both tag widths
VS_USER_TAGS_VA = VS_MTAG_VA + 0x8000 + 0x1420_0000
VS_CODE_GPA = int(SV39X4.data_va, 16) + 0x3000
G_FAULT_GPA = int(SV39X4.data_va, 16) + 0x4000
# A virtual page whose VS-stage level-1 PTE points to a page table at G_FAULT_GPA: its VS-stage walk takes a guest-page
# fault in an implicit access, with htval = (G_FAULT_GPA + 8 * its level-0 index) >> 2 and htinst = 0x3000. It is in
# the 2 MiB after the other guest pages, whose level-1 PTE no other mapping writes.
VS_IMPLICIT_VA = VS_MTAG_VA + 0x20_0000
# The data chunk of these tests in each data page
VS_PAGE_CHUNK = 2
# The code page that VS_CODE_GPA maps, in the code of each tag width: its instructions at MTAG_CODE_LOAD and
# MTAG_CODE_STORE are those of MTAG_CODE
VS_CODE = "zimt_vs_code"


def _vs_code_page(label: str, code: tuple[int, int, int]) -> list[str]:
    """The VS-stage code page label, in the code, which the code before it jumps over. Its instructions use the
    registers code (pointer, value, return address): a load into the second register and a store of it through the
    first one, each followed by a return through the third."""
    ptr, val, ret = code
    return [
        "j 1f",
        ".p2align 12",
        f"{label}:",
        ".option push",
        ".option norvc",
        f"ld x{val}, 0(x{ptr})",
        f"jalr x0, 0(x{ret})",
        f"sd x{val}, 0(x{ptr})",
        f"jalr x0, 0(x{ret})",
        ".option pop",
        ".p2align 12",
        "1:",
    ]


def _vs_tag_vitt(mt_mode: int, page: int = int(VS_SV39.data_va, 16)) -> int:
    """The tag table base that puts the tags of the chunks of the guest pages from VS_MTAG_VA in the guest page page."""
    return page - (_tag_offset(VS_MTAG_VA >> 4, mt_mode) & ~0xFFF)


def _vs_tag(va: int, tag: int, mt_mode: int, regs: tuple[int, int]) -> list[str]:
    """Set the memory tag of the chunk at the guest virtual address va to tag, in the second tag table page, which
    VS_SV39.data_va maps. With 4-bit tags, the other chunk of its tag byte gets it too."""
    addr, val = regs
    byte = _tag_offset(va >> 4, mt_mode) - (_tag_offset(VS_MTAG_VA >> 4, mt_mode) & ~0xFFF)
    assert 0 <= byte < 0x1000, "the tags of the guest pages must be in one tag page"
    return [
        f"LA(x{addr}, {TAG_TABLE} + {0x1000 + byte:#x})",
        f"LI(x{val}, {tag if mt_mode == MT_TAG7 else tag * 0x11:#x})",
        f"sb x{val}, 0(x{addr})",
    ]


def _h_two_stage_mtag_tests(test_data: TestData, cg: str, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """With two-stage translation, a VS-stage leaf PTE with PTE.MTAG maps a tagged-data page, whose loads and stores
    are tag checked: in VS-mode, a load and a store of its chunk VS_MTAG_CHUNK, whose tag HS-mode sets to GOOD_TAG,
    with the matching and with a mismatching pointer tag. HS-mode takes the traps, records the doubleword the stores
    write and restores it. Needs the mapping of VS_SV39.data_va to the second tag table page through both stages."""
    _, addr, tmp = regs
    name = MT_NAMES[mt_mode]
    good = GOOD_TAG[mt_mode]
    first = _tag_offset(VS_MTAG_VA >> 4, mt_mode) & ~0xFFF
    byte = _tag_offset((VS_MTAG_VA >> 4) + VS_MTAG_CHUNK, mt_mode) - first
    lines = [
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=MTAG_TAGGED_FLAGS,
            virtual_address=hex(VS_MTAG_VA),
            physical_address=hex(VS_MTAG_GPA),
            regs=regs,
            pa_is_label=False,
        ),
        *create_page_mapping(
            SV39X4,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False),
            virtual_address=hex(VS_MTAG_GPA),
            physical_address=CHECK_DATA,
            regs=regs,
        ),
        "hfence.vvma",
        "hfence.gvma",
        f"LI(x{tmp}, {int(VS_SV39.data_va, 16) - first:#x})",
        f"csrw CSR_VSVITTS, x{tmp}",
        f"LA(x{addr}, {TAG_TABLE} + {0x1000 + byte:#x})",
        f"LI(x{tmp}, {good if mt_mode == MT_TAG7 else good * 0x11:#x})",
        f"sb x{tmp}, 0(x{addr})",
        "RVTEST_TSBI_GOTO_VSMODE",
    ]
    for case, tag in (("match", good), ("mismatch", BAD_TAG[mt_mode])):
        lines += [
            f"LI(x{addr}, {_tag_field(tag, mt_mode) | (VS_MTAG_VA + 16 * VS_MTAG_CHUNK):#x})",
            f"LI(x{tmp}, {RD_CANARY:#x})",
            test_data.add_testcase(f"VS_{name}_mtag_{case}_load", "cp_checked_vs_tagged_page", cg),
            f"ld x{tmp}, 0(x{addr})",
            write_sigupd(tmp, test_data),
            f"LI(x{tmp}, {G_STAGE_STORE_DATA[case]:#x})",
            test_data.add_testcase(f"VS_{name}_mtag_{case}_store", "cp_checked_vs_tagged_page", cg),
            f"sd x{tmp}, 8(x{addr})",
        ]
    return [
        *lines,
        "RVTEST_TSBI_GOTO_SMODE",
        f"LA(x{addr}, {CHECK_DATA} + {16 * VS_MTAG_CHUNK + 8})",
        f"ld x{tmp}, 0(x{addr})",
        write_sigupd(tmp, test_data),
        f"LI(x{tmp}, {_check_data_dword(VS_MTAG_CHUNK, 1):#x})",
        f"sd x{tmp}, 0(x{addr})",
    ]


def _h_hlsv_paging_tests(test_data: TestData, cg: str, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """HLV and HSV in HS-mode with hstatus.SPVP = 1 and two-stage translation, where only VS-stage PTE.MTAG pages are
    tagged-data pages: of VS_MTAG_VA with the matching pointer tag and with a mismatching one; with a mismatching one, of
    a page without PTE.MTAG and (vsstatus.SUM = 1) of a user tagged-data page, which a supervisor access does not check;
    over VS_MTAG_VA and the page after it, checked in both, with the chunk in the second one mismatching, and over the
    page without PTE.MTAG before it and it, also checked in both, with the chunk in the first one mismatching, then
    matching (with byte by byte misaligned accesses); and with vsvitts putting the tags in a guest page that the VS stage
    does not map, then in one whose guest physical page the G stage does not map: a load page fault and a load
    guest-page fault on the tag, also for HSV. Needs the VS_MTAG_VA mapping and vsvitts of _h_two_stage_mtag_tests."""
    _, addr, tmp = regs
    rec = test_data.int_regs.get_register()
    name = MT_NAMES[mt_mode]
    good, bad = GOOD_TAG[mt_mode], BAD_TAG[mt_mode]
    offset = 16 * VS_PAGE_CHUNK

    def access(case: str, va: int, tag: int, restore: bool = True) -> list[str]:
        """hlv.d and hsv.d of va with the pointer tag tag; record rd, and the doubleword of VS_MTAG_GPA (the check data)
        that va maps, which the store writes, and restore it."""
        lines = [
            f"LI(x{addr}, {_tag_field(tag, mt_mode) | va:#x})",
            f"LI(x{tmp}, {RD_CANARY:#x})",
            test_data.add_testcase(f"HS_{name}_paged_{case}_hlv", "cp_hlsv_paged", cg),
            f"hlv.d x{tmp}, (x{addr})",
            write_sigupd(tmp, test_data),
            f"LI(x{tmp}, 0x0123456789abcdef)",
            test_data.add_testcase(f"HS_{name}_paged_{case}_hsv", "cp_hlsv_paged", cg),
            f"hsv.d x{tmp}, (x{addr})",
        ]
        if not restore:
            return lines
        return [
            *lines,
            f"LA(x{rec}, {CHECK_DATA} + {va & 0xFFF:#x})",
            f"ld x{tmp}, 0(x{rec})",
            write_sigupd(tmp, test_data),
            f"LI(x{tmp}, {_check_data_dword((va & 0xFFF) >> 4, (va >> 3) & 1):#x})",
            f"sd x{tmp}, 0(x{rec})",
        ]

    def vsvitts(page: int) -> list[str]:
        return [f"LI(x{tmp}, {_vs_tag_vitt(mt_mode, page):#x})", f"csrw CSR_VSVITTS, x{tmp}"]

    def vs_page(va: int, flags: PteFlags, gpa: int) -> list[str]:
        return create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=flags,
            virtual_address=hex(va),
            physical_address=hex(gpa),
            regs=regs,
            pa_is_label=False,
        )

    lines = [
        comment_banner(
            f"cp_hlsv_paged (HS, {name})",
            "In HS-mode with hstatus.SPVP = 1 and two-stage translation: hlv.d and hsv.d of the VS-stage tagged-data\n"
            "page with the matching pointer tag, and with a mismatching one: a software-check exception (cause 18,\n"
            "stval 4) with hstatus.GVA = 1; with a mismatching one, of a page without PTE.MTAG and (vsstatus.SUM = 1)\n"
            "of a user tagged-data page: not checked; (byte by byte misaligned accesses) over the tagged-data page and\n"
            "the page after it, whose chunk mismatches: checked in both; over the page without PTE.MTAG before it and\n"
            "it, whose chunk in the first page mismatches, then matches: checked in both; and with vsvitts putting the\n"
            "tag in a guest page that the VS stage does not map, then in one whose guest physical page the G stage does\n"
            "not map: a load page fault, then a load guest-page fault, on the tag, also for hsv.d. Record rd and memory",
        ),
        *vs_page(VS_PLAIN_VA, PteFlags(execute=False), VS_MTAG_GPA),
        *vs_page(VS_USER_MTAG_VA, PteFlags(user=True, execute=False, extra=(PTE_MTAG,)), VS_MTAG_GPA),
        *vs_page(VS_G_FAULT_VA, PteFlags(execute=False), G_FAULT_GPA),
        "hfence.vvma",
        *_vs_tag(VS_MTAG_VA + offset, good, mt_mode, (rec, tmp)),
        *_vs_tag(VS_PLAIN_VA + offset, good, mt_mode, (rec, tmp)),
        *_vs_tag(VS_USER_MTAG_VA + offset, good, mt_mode, (rec, tmp)),
        *_vs_tag(VS_MTAG_VA + 0xFF0, good, mt_mode, (rec, tmp)),
        *_vs_tag(VS_PLAIN_VA, bad, mt_mode, (rec, tmp)),
        f"LI(x{tmp}, HSTATUS_SPVP)",
        f"csrs hstatus, x{tmp}",
        *access("tagged_match", VS_MTAG_VA + offset, good),
        *access("tagged_mismatch", VS_MTAG_VA + offset, bad),
        *access("untagged", VS_PLAIN_VA + offset, bad),
        f"LI(x{tmp}, SSTATUS_SUM)",
        f"csrs vsstatus, x{tmp}",
        *access("user_sum", VS_USER_MTAG_VA + offset, bad),
        f"LI(x{tmp}, SSTATUS_SUM)",
        f"csrc vsstatus, x{tmp}",
        *gated(access("straddle", VS_MTAG_VA + 0xFFC, good, restore=False), PAGE_CROSSING_GATE),
        *gated(
            [
                *_vs_tag(VS_TAG_PAGE_VA + 0xFF0, bad, mt_mode, (rec, tmp)),
                *_vs_tag(VS_MTAG_VA, good, mt_mode, (rec, tmp)),
                *access("straddle_untagged_mismatch", VS_TAG_PAGE_VA + 0xFFC, good, restore=False),
                *_vs_tag(VS_TAG_PAGE_VA + 0xFF0, good, mt_mode, (rec, tmp)),
                *access("straddle_untagged_match", VS_TAG_PAGE_VA + 0xFFC, good, restore=False),
                f"LA(x{rec}, {CHECK_DATA})",
                f"ld x{tmp}, 0(x{rec})",
                write_sigupd(tmp, test_data),
                f"LI(x{tmp}, {_check_data_dword(0, 0):#x})",
                f"sd x{tmp}, 0(x{rec})",
            ],
            PAGE_CROSSING_GATE,
        ),
        *vsvitts(VS_FAULT_VA),
        *access("tag_page_fault", VS_MTAG_VA + offset, good, restore=False),
        *vsvitts(VS_G_FAULT_VA),
        *access("tag_guest_page_fault", VS_MTAG_VA + offset, good, restore=False),
        *vsvitts(int(VS_SV39.data_va, 16)),
        f"LI(x{tmp}, HSTATUS_SPVP)",
        f"csrc hstatus, x{tmp}",
    ]
    test_data.int_regs.return_register(rec)
    return lines


def _h_vs_code_tests(test_data: TestData, cg: str, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """In VS-mode with two-stage translation, code in a VS-stage tagcheck-exempt code page (PTE.MTAG = 1, X = 1) and in
    one without PTE.MTAG, which map the same code page of _vs_code_page, loads and stores with a mismatching pointer tag
    in VS_MTAG_VA: not checked from the first one, checked from the second one. HS-mode takes the traps, and records
    and restores the doubleword. Then a load of VS_IMPLICIT_VA from each code page: a guest-page fault in an implicit
    access of the VS-stage walk, whose trap to HS-mode writes the pseudoinstruction to htinst and so deposits the MTAG
    bit of the code page in hstatus.MTAG_I, which HS-mode records. The code page uses regs (pointer, value, return
    address) after the mappings."""
    ptr, val, ret = regs
    name = MT_NAMES[mt_mode]
    label = f"{VS_CODE}_{name}"
    offset = 16 * VS_PAGE_CHUNK
    mtag_i = f"{1 << HSTATUS_MTAG_I_BIT:#x}"

    def call(
        case: str, va: int, entry: int, value: int = RD_CANARY, coverpoint: str = "cp_vs_mtag_code_access"
    ) -> list[str]:
        return [
            f"LI(x{val}, {value:#x})",
            f"LI(x{ret}, {va + entry:#x})",
            test_data.add_testcase(f"VS_{name}_{case}", coverpoint, cg),
            f"jalr x{ret}, 0(x{ret})",
        ]

    def record() -> list[str]:
        return [
            "RVTEST_TSBI_GOTO_SMODE",
            f"LA(x{ret}, {CHECK_DATA} + {offset:#x})",
            f"ld x{val}, 0(x{ret})",
            write_sigupd(val, test_data),
            f"LI(x{val}, {_check_data_dword(VS_PAGE_CHUNK, 0):#x})",
            f"sd x{val}, 0(x{ret})",
            "RVTEST_TSBI_GOTO_VSMODE",
        ]

    def deposit(case: str, va: int, before: bool) -> list[str]:
        """From HS-mode, with hstatus.MTAG_I = before: in VS-mode, the load of VS_IMPLICIT_VA from the code page va;
        then hstatus.MTAG_I in HS-mode, recorded and cleared."""
        return [
            f"LI(x{val}, {mtag_i})",
            f"csr{'s' if before else 'c'} hstatus, x{val}",
            "RVTEST_TSBI_GOTO_VSMODE",
            f"LI(x{ptr}, {VS_IMPLICIT_VA:#x})",
            *call(case, va, MTAG_CODE_LOAD, coverpoint="cp_mtag_i_deposit"),
            "RVTEST_TSBI_GOTO_SMODE",
            f"csrr x{val}, hstatus",
            f"srli x{val}, x{val}, {HSTATUS_MTAG_I_BIT}",
            f"andi x{val}, x{val}, 1",
            write_sigupd(val, test_data),
            f"LI(x{val}, {mtag_i})",
            f"csrc hstatus, x{val}",
        ]

    return [
        *_vs_code_page(label, regs),
        comment_banner(
            f"cp_vs_mtag_code_access (VS, {name})",
            "In VS-mode with two-stage translation, through a pointer with a mismatching tag to the VS-stage\n"
            "tagged-data page: a load and a store from a VS-stage tagcheck-exempt code page (PTE.MTAG = 1, X = 1): not\n"
            f"checked; from a VS-stage code page without PTE.MTAG: a {SW_CHECK_TEXT}, which\n"
            "HS-mode takes. Record rd and memory",
        ),
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=MTAG_EXEMPT_FLAGS,
            virtual_address=hex(VS_EXEMPT_CODE_VA),
            physical_address=hex(VS_CODE_GPA),
            regs=regs,
            pa_is_label=False,
        ),
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=PteFlags(write=False),
            virtual_address=hex(VS_NORMAL_CODE_VA),
            physical_address=hex(VS_CODE_GPA),
            regs=regs,
            pa_is_label=False,
        ),
        *create_page_mapping(
            SV39X4,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, write=False),
            virtual_address=hex(VS_CODE_GPA),
            physical_address=label,
            regs=regs,
        ),
        "hfence.vvma",
        "hfence.gvma",
        *_vs_tag(VS_MTAG_VA + offset, GOOD_TAG[mt_mode], mt_mode, (val, ret)),
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{ptr}, {_tag_field(BAD_TAG[mt_mode], mt_mode) | (VS_MTAG_VA + offset):#x})",
        *call("exempt_load", VS_EXEMPT_CODE_VA, MTAG_CODE_LOAD),
        write_sigupd(val, test_data),
        *call("exempt_store", VS_EXEMPT_CODE_VA, MTAG_CODE_STORE, 0x1357_9BDF_0246_8ACE),
        *record(),
        *call("normal_code_load", VS_NORMAL_CODE_VA, MTAG_CODE_LOAD),
        write_sigupd(val, test_data),
        *call("normal_code_store", VS_NORMAL_CODE_VA, MTAG_CODE_STORE, 0x0246_8ACE_1357_9BDF),
        *record(),
        "RVTEST_TSBI_GOTO_SMODE",
        comment_banner(
            f"cp_mtag_i_deposit (VS, {name})",
            "In VS-mode with two-stage translation, a load whose VS-stage walk reads a page table at a guest physical\n"
            "page that the G stage does not map: a load guest-page fault, which HS-mode takes, with htval = the\n"
            "address of the PTE >> 2 and htinst = 0x3000, a pseudoinstruction, so it deposits the MTAG bit of the code\n"
            "page in hstatus.MTAG_I: 1 from the tagcheck-exempt code page (0 before), 0 from the other one (1 before).\n"
            "Record hstatus.MTAG_I",
        ),
        *write_pte(
            VS_SV39,
            level=1,
            flags=PteFlags.nonleaf(),
            virtual_address=hex(VS_IMPLICIT_VA),
            physical_address=hex(G_FAULT_GPA),
            regs=regs,
            pa_is_label=False,
        ),
        "hfence.vvma",
        *deposit("deposit_exempt", VS_EXEMPT_CODE_VA, before=False),
        *deposit("deposit_normal", VS_NORMAL_CODE_VA, before=True),
        f"LA(x{ret}, {VS_SV39.pte_address(1, hex(VS_IMPLICIT_VA))})",
        f"SREG x0, 0(x{ret})",
        "hfence.vvma",
    ]


def _h_mprv_vu_paging_tests(test_data: TestData, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """In M-mode with mstatus.MPRV = 1, MPV = 1 and MPP = U, so with the two-stage translation, memory tagging
    (senvcfg.MT_MODE) and tag table (vsvittu) of VU-mode: a load of a VS-stage user tagged-data page with a mismatching
    pointer tag (a software-check exception with GVA = 0, which M-mode takes) and with the matching one, and of a
    VS-stage user page without PTE.MTAG with a mismatching one (not checked). Needs the mappings of
    _h_hlsv_paging_tests."""
    pte, addr, tmp = regs
    name = MT_NAMES[mt_mode]
    good, bad = GOOD_TAG[mt_mode], BAD_TAG[mt_mode]
    offset = 16 * VS_PAGE_CHUNK
    lines = [
        comment_banner(
            f"cp_checked_mprv_vu_page (M, {name})",
            "In M-mode with mstatus.MPRV = 1, MPV = 1 and MPP = U, and two-stage translation, with vsvittu putting the\n"
            "tags in the tag page as a user page: a load of a VS-stage user tagged-data page with a mismatching\n"
            f"pointer tag: a {SW_CHECK_TEXT} with GVA = 0, which M-mode takes; with the\n"
            "matching one: performed; and with a mismatching one, of a VS-stage user page without PTE.MTAG: not\n"
            "checked. Record rd",
        ),
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False),
            virtual_address=hex(VS_USER_VA),
            physical_address=hex(VS_MTAG_GPA),
            regs=regs,
            pa_is_label=False,
        ),
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False),
            virtual_address=hex(VS_USER_TAGS_VA),
            physical_address=SV39X4.data_va,
            regs=regs,
            pa_is_label=False,
        ),
        "hfence.vvma",
        *_vs_tag(VS_USER_MTAG_VA + offset, good, mt_mode, (addr, tmp)),
        *_vs_tag(VS_USER_VA + offset, good, mt_mode, (addr, tmp)),
        f"LI(x{tmp}, {_vs_tag_vitt(mt_mode, VS_USER_TAGS_VA):#x})",
        f"csrw CSR_VSVITTU, x{tmp}",
        *_set_pmm(tmp, "SSNPM"),
        f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{tmp}, x{tmp}, x{addr}",
        f"csrs senvcfg, x{tmp}",
        "RVTEST_TSBI_GOTO_MMODE",
    ]
    for case, va, tag in (
        ("mismatch", VS_USER_MTAG_VA, bad),
        ("match", VS_USER_MTAG_VA, good),
        ("untagged", VS_USER_VA, bad),
    ):
        lines += [
            f"LI(x{addr}, {_tag_field(tag, mt_mode) | (va + offset):#x})",
            f"LI(x{pte}, {RD_CANARY:#x})",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{tmp}, MSTATUS_MPRV | MSTATUS_MPV)",
            f"csrs mstatus, x{tmp}",
            test_data.add_testcase(f"M_{name}_mprv_vu_{case}", "cp_checked_mprv_vu_page", "Zimt_Sm_cg"),
            f"ld x{pte}, 0(x{addr})",
            f"csrc mstatus, x{tmp}",
            write_sigupd(pte, test_data),
        ]
    return [
        *lines,
        "RVTEST_TSBI_GOTO_SMODE",
        f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        f"csrc senvcfg, x{tmp}",
        "csrw CSR_VSVITTU, x0",
    ]


def _h_mprv_vitt_tests(test_data: TestData, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """Protection of tag storage (Svatag) of the loads in M-mode with mstatus.MPRV = 1 and MPV = 1, with two-stage
    translation: with MPP = S (VS-mode, henvcfg.MT_MODE), vsvitts puts the VITT range of VS-mode at the guest page
    without PTE.MTAG after VS_MTAG_VA, and with MPP = U (VU-mode, senvcfg.MT_MODE) vsvittu that of VU-mode at the user
    page without PTE.MTAG: a load there, through a pointer with a pointer tag, which pointer masking (henvcfg.PMM,
    senvcfg.PMM) ignores, raises a load access fault with GVA = 1, which M-mode takes; one in the tagged-data page
    before it, unchecked with mstatus.MTAG_I = 1, none. Needs the mappings of _h_mprv_vu_paging_tests, and
    henvcfg.MT_MODE and PMM of the caller, which it keeps."""
    rd, addr, tmp = regs
    name = MT_NAMES[mt_mode]
    offset = 16 * VS_PAGE_CHUNK
    lines = [
        comment_banner(
            f"cp_vitt_mprv_v (M, VS, VU, {name})",
            "In M-mode with mstatus.MPRV = 1 and MPV = 1, and two-stage translation: with MPP = S, vsvitts putting\n"
            "the VITT range of VS-mode at the guest page without PTE.MTAG, a load there raises a load access fault\n"
            "with GVA = 1, and one in the tagged-data page before it (unchecked with mstatus.MTAG_I = 1) none; with\n"
            "MPP = U and vsvittu the same for VU-mode, at the user page without PTE.MTAG. Record rd",
        ),
        f"LI(x{tmp}, {(VS_PLAIN_VA - VITT_RANGE_S_OFFSET[mt_mode]) & MASK64:#x})",
        f"csrw CSR_VSVITTS, x{tmp}",
        f"LI(x{tmp}, {VS_USER_VA:#x})",
        f"csrw CSR_VSVITTU, x{tmp}",
        *_set_pmm(tmp, "SSNPM"),
        f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{tmp}, x{tmp}, x{addr}",
        f"csrs senvcfg, x{tmp}",
        "RVTEST_TSBI_GOTO_MMODE",
    ]
    for case, mpp, va, mtag_i in (
        ("vs_first", 1, VS_PLAIN_VA, False),
        ("vs_before", 1, VS_MTAG_VA + 0xFF0, True),
        ("vu_first", 0, VS_USER_VA, False),
        ("vu_before", 0, VS_USER_MTAG_VA + 0xFF0, True),
    ):
        mstatus = f"MSTATUS_MPRV | MSTATUS_MPV{f' | {1 << MSTATUS_MTAG_I_BIT:#x}' if mtag_i else ''}"
        # In the range, with a pointer tag, which pointer masking ignores
        pointer = va if mtag_i else _tag_field(SETTAG_TAG[mt_mode], mt_mode) | (va + offset)
        lines += [
            f"LI(x{addr}, {pointer:#x})",
            f"LI(x{rd}, {RD_CANARY:#x})",
            f"LI(x{tmp}, MSTATUS_MPP)",
            f"csrc mstatus, x{tmp}",
            f"LI(x{tmp}, {mstatus}{f' | {1 << 11:#x}' if mpp else ''})    # MPP = {'S' if mpp else 'U'}",
            f"csrs mstatus, x{tmp}",
            test_data.add_testcase(f"M_{name}_vitt_{case}", "cp_vitt_mprv_v", "Zimt_Sm_cg"),
            f"ld x{rd}, 0(x{addr})",
            f"csrc mstatus, x{tmp}",
            write_sigupd(rd, test_data),
        ]
    return [
        *lines,
        "RVTEST_TSBI_GOTO_SMODE",
        f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        f"csrc senvcfg, x{tmp}",
        "csrw CSR_VSVITTS, x0",
        "csrw CSR_VSVITTU, x0",
    ]


def _h_hlsv_vitt_tests(test_data: TestData, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """Protection of tag storage (Svatag) of VS-mode, whose load and settag in the first page of its range raise a load
    and a store/AMO access fault, which HS-mode takes, and of HLV and HSV, in HS-mode with two-stage translation: with
    hstatus.SPVP = 1 (VS-mode, henvcfg.MT_MODE), vsvitts puts the VITT range of VS-mode at the guest page without
    PTE.MTAG, and with SPVP = 0 (VU-mode, senvcfg.MT_MODE) vsvittu that of VU-mode at the VS-stage user tagged-data
    page, while svitts, the tag table base of HS-mode, is 32 GiB above that page, so that neither of its ranges holds
    those pages: hlv.d and hsv.d there, through a pointer with a pointer tag, which pointer masking (henvcfg.PMM,
    senvcfg.PMM, and hstatus.HUPMM in HU-mode below) ignores, raise a load and a store/AMO access fault with GVA = 1,
    with hstatus.MTAG_I = 1, which only disables their tag checks. hstatus.MTAG_I is set right before each of them: a
    trap that writes a nonzero htinst (a transformed instruction, which a hart may write for these access faults)
    deposits 0 in it, the MTAG bit of the code page of an instruction executed at V = 0, and the VU cases at the
    tagged-data page would then be checked. hlvx.wu, which is not a regular access, at a VS-stage code page in the range
    of VS-mode is performed. Then, with vsvittu putting the range of VU-mode at the VS-stage user page without PTE.MTAG,
    VU-mode's own settag and load there raise a store/AMO and a load access fault, which HS-mode takes (VU-mode runs
    from the guest code alias, which is a user page meanwhile); and in HU-mode (hstatus.HU = 1) with SPVP = 0, whose HLV
    and HSV use hstatus.VUMT_MODE for VU-mode, hlv.d and hsv.d there raise them with VUMT_MODE set and senvcfg.MT_MODE =
    00, and none with senvcfg.MT_MODE set instead (which U-mode then uses, with Bare translation). Record rd, and in
    HS-mode the check data that the accesses map, which hsv.d keeps. Needs the mappings of _h_hlsv_paging_tests, and
    henvcfg.MT_MODE and PMM of the caller, which it keeps."""
    rd, addr, tmp = regs
    save = test_data.int_regs.get_register()
    name = MT_NAMES[mt_mode]
    lines = [
        comment_banner(
            f"cp_vitt_v, cp_vitt_hlsv, cp_vitt_hlvx, cp_vitt_hlsv_hu (VS, HS, VU, HU, {name})",
            "In VS-mode, a load and settag in the first page of its VITT range: a load and a store/AMO access fault.\n"
            "In HS-mode with two-stage translation and hstatus.MTAG_I = 1: hlv.d and hsv.d with hstatus.SPVP = 1 at\n"
            "the guest page without PTE.MTAG and with SPVP = 0 at the VS-stage user tagged-data page, the first pages\n"
            "of the VITT ranges of their guest modes (vsvitts, vsvittu; not svitts): a load access fault and a\n"
            "store/AMO access fault with GVA = 1; hlvx.wu in the range of VS-mode is performed. With vsvittu at the\n"
            "VS-stage user page without PTE.MTAG: VU-mode's settag and load there raise the access faults, and in\n"
            "HU-mode with SPVP = 0 hlv.d and hsv.d with hstatus.VUMT_MODE set, none with senvcfg.MT_MODE set instead.\n"
            "Record rd",
        ),
        f"LI(x{tmp}, {(VS_PLAIN_VA - VITT_RANGE_S_OFFSET[mt_mode]) & MASK64:#x})",
        f"csrw CSR_VSVITTS, x{tmp}",
        f"LI(x{tmp}, {VS_USER_MTAG_VA:#x})",
        f"csrw CSR_VSVITTU, x{tmp}",
        f"LI(x{tmp}, {VS_USER_MTAG_VA + (1 << 35):#x})",
        f"csrw CSR_SVITTS, x{tmp}",
        *_set_pmm(tmp, "SSNPM"),
        f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{tmp}, x{tmp}, x{addr}",
        f"csrs senvcfg, x{tmp}",
        f"csrr x{save}, hstatus",
        # VS-mode itself: a load and a settag in the first page of its range, whose traps HS-mode takes
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{addr}, {_tag_field(SETTAG_TAG[mt_mode], mt_mode) | (VS_PLAIN_VA + 16 * VS_PAGE_CHUNK + 8):#x})",
        f"LI(x{rd}, {RD_CANARY:#x})",
        test_data.add_testcase(f"VS_{name}_vitt_ld_first", "cp_vitt_v", "Zimt_H_cg"),
        f"ld x{rd}, 0(x{addr})",
        write_sigupd(rd, test_data),
        test_data.add_testcase(f"VS_{name}_vitt_settag_first", "cp_vitt_v", "Zimt_H_cg"),
        f"settag x{addr}, 0",
        "RVTEST_TSBI_GOTO_SMODE",
    ]
    mtag_i = [f"LI(x{tmp}, {1 << HSTATUS_MTAG_I_BIT:#x})", f"csrs hstatus, x{tmp}"]

    def record() -> list[str]:
        """In HS-mode, record the doubleword of the check data that the guest pages of the accesses map: whether hsv.d
        wrote it."""
        return [
            f"LA(x{tmp}, {CHECK_DATA} + {16 * VS_PAGE_CHUNK + 8:#x})",
            f"ld x{rd}, 0(x{tmp})",
            write_sigupd(rd, test_data),
        ]

    for case, spvp, va in (("vs", True, VS_PLAIN_VA), ("vu", False, VS_USER_MTAG_VA)):
        lines += [
            f"LI(x{tmp}, HSTATUS_SPVP)",
            f"csr{'s' if spvp else 'c'} hstatus, x{tmp}",
            f"LI(x{addr}, {_tag_field(SETTAG_TAG[mt_mode], mt_mode) | (va + 16 * VS_PAGE_CHUNK + 8):#x})",
            f"LI(x{rd}, {RD_CANARY:#x})",
            *mtag_i,
            test_data.add_testcase(f"HS_{name}_vitt_hlv_{case}_first", "cp_vitt_hlsv", "Zimt_H_cg"),
            f"hlv.d x{rd}, (x{addr})",
            write_sigupd(rd, test_data),
            *mtag_i,
            test_data.add_testcase(f"HS_{name}_vitt_hsv_{case}_first", "cp_vitt_hlsv", "Zimt_H_cg"),
            f"hsv.d x{rd}, (x{addr})",
            *record(),
        ]

    # HLVX is not a regular access: with vsvitts putting the range of VS-mode at the VS-stage code page without
    # PTE.MTAG, hlvx.wu there is performed
    lines += [
        f"LI(x{tmp}, {(VS_NORMAL_CODE_VA - VITT_RANGE_S_OFFSET[mt_mode]) & MASK64:#x})",
        f"csrw CSR_VSVITTS, x{tmp}",
        f"LI(x{tmp}, HSTATUS_SPVP)",
        f"csrs hstatus, x{tmp}",
        f"LI(x{addr}, {VS_NORMAL_CODE_VA:#x})",
        f"LI(x{rd}, {RD_CANARY:#x})",
        test_data.add_testcase(f"HS_{name}_vitt_hlvx_first", "cp_vitt_hlvx", "Zimt_H_cg"),
        f"hlvx.wu x{rd}, (x{addr})",
        write_sigupd(rd, test_data),
        f"LI(x{tmp}, {(VS_PLAIN_VA - VITT_RANGE_S_OFFSET[mt_mode]) & MASK64:#x})",
        f"csrw CSR_VSVITTS, x{tmp}",
    ]

    def hu_access(case: str) -> list[str]:
        """In HU-mode, hlv.d and hsv.d at the first chunk of VS_PAGE_CHUNK of the user page without PTE.MTAG."""
        return [
            "RVTEST_TSBI_GOTO_UMODE",
            f"LI(x{addr}, {_tag_field(SETTAG_TAG[mt_mode], mt_mode) | (VS_USER_VA + 16 * VS_PAGE_CHUNK + 8):#x})",
            f"LI(x{rd}, {RD_CANARY:#x})",
            test_data.add_testcase(f"HU_{name}_vitt_hlv_{case}", "cp_vitt_hlsv_hu", "Zimt_H_cg"),
            f"hlv.d x{rd}, (x{addr})",
            write_sigupd(rd, test_data),
            test_data.add_testcase(f"HU_{name}_vitt_hsv_{case}", "cp_vitt_hlsv_hu", "Zimt_H_cg"),
            f"hsv.d x{rd}, (x{addr})",
            "RVTEST_TSBI_GOTO_SMODE",
            *record(),
        ]

    # vsvittu puts the VITT range of VU-mode at the user page without PTE.MTAG (mapped as _h_mprv_vu_paging_tests maps
    # it), so that the accesses there are not tag checked
    lines += [
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False),
            virtual_address=hex(VS_USER_VA),
            physical_address=hex(VS_MTAG_GPA),
            regs=regs,
            pa_is_label=False,
        ),
        "hfence.vvma",
        f"LI(x{tmp}, {VS_USER_VA:#x})",
        f"csrw CSR_VSVITTU, x{tmp}",
        # VU-mode itself (senvcfg.MT_MODE): settag and a load there, from the guest code alias, which is a user page
        # meanwhile (VS-mode does not run then). The alias is in the VITT range of VU-mode, which does not protect its
        # fetches, nor the HLVX with which HS-mode, which takes the traps, reads the trapping instructions. The
        # signature is not a user page, so HS-mode records rd
        *write_pte(
            VS_SV39,
            level=VS_SV39.levels - 1,
            flags=PteFlags(user=True),
            virtual_address=VS_SV39.code_va,
            physical_address=SV39X4.code_va,
            regs=regs,
            pa_is_label=False,
            superpage=True,
        ),
        "hfence.vvma",
        "RVTEST_TSBI_GOTO_VUMODE",
        f"LI(x{addr}, {_tag_field(SETTAG_TAG[mt_mode], mt_mode) | (VS_USER_VA + 16 * VS_PAGE_CHUNK + 8):#x})",
        f"LI(x{rd}, {RD_CANARY:#x})",
        test_data.add_testcase(f"VU_{name}_vitt_settag_first", "cp_vitt_v", "Zimt_H_cg"),
        f"settag x{addr}, 0",
        test_data.add_testcase(f"VU_{name}_vitt_ld_first", "cp_vitt_v", "Zimt_H_cg"),
        f"ld x{rd}, 0(x{addr})",
        "RVTEST_TSBI_GOTO_SMODE",
        write_sigupd(rd, test_data),
        *write_pte(
            VS_SV39,
            level=VS_SV39.levels - 1,
            flags=PteFlags(),
            virtual_address=VS_SV39.code_va,
            physical_address=SV39X4.code_va,
            regs=regs,
            pa_is_label=False,
            superpage=True,
        ),
        "hfence.vvma",
        # HU-mode (hstatus.HU = 1) with SPVP = 0: HLV and HSV use hstatus.VUMT_MODE, not senvcfg.MT_MODE, for the
        # memory tagging of VU-mode
        f"LI(x{tmp}, {0b11 << MT_MODE_LSB:#x})",
        f"csrc senvcfg, x{tmp}",
        f"LI(x{tmp}, HSTATUS_SPVP)",
        f"csrc hstatus, x{tmp}",
        *_set_pmm(tmp, "SSNPM"),
        f"slli x{tmp}, x{tmp}, {HUPMM_LSB - PMM_LSB}",
        f"csrs hstatus, x{tmp}",
        f"LI(x{tmp}, HSTATUS_HU | {mt_mode << VUMT_MODE_LSB:#x})",
        f"csrs hstatus, x{tmp}",
        *hu_access("vumt"),
    ]
    # With senvcfg.MT_MODE set instead, they have no VITT range; U-mode then has memory tagging, with Bare translation
    lines += gated(
        [
            f"LI(x{tmp}, {0b11 << VUMT_MODE_LSB:#x})",
            f"csrc hstatus, x{tmp}",
            f"LI(x{tmp}, {mt_mode << MT_MODE_LSB:#x})",
            f"csrs senvcfg, x{tmp}",
            *hu_access("senvcfg"),
        ],
        NO_BARE_VITT_RANGE,
    )
    lines += [
        f"csrw hstatus, x{save}",
        f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        f"csrc senvcfg, x{tmp}",
        "csrw CSR_SVITTS, x0",
        "csrw CSR_VSVITTS, x0",
        "csrw CSR_VSVITTU, x0",
    ]
    test_data.int_regs.return_registers([save])
    return lines


def _h_svukte_tests(test_data: TestData, mt_mode: int, regs: tuple[int, int, int]) -> list[str]:
    """Svukte, which Svatag depends on, with two-stage translation: the tag accesses of VU-mode, and of HLV and HSV with
    hstatus.SPVP = 0, are Svukte-qualified, with senvcfg.UKTE, or hstatus.HUKTE for HLV and HSV in HU-mode. A VS-stage
    root PTE maps the guest pages again UPPER_HALF bytes up, and vsvittu puts the tags of the VS-stage user tagged-data
    page in the upper alias of the user tags page: in VU-mode (from the guest code alias as a user page), a load and
    settag of a chunk there raise the page fault of their tag access (a load and a store/AMO page fault with GVA = 1,
    which HS-mode takes) with UKTE = 1, and the load is performed with UKTE = 0; hlv.d in HU-mode (hstatus.HU, SPVP = 0,
    VUMT_MODE and HUPMM) raises the load page fault with HUKTE = 1, and is performed with UKTE = 1 alone; hlv.d in
    HS-mode raises it with UKTE = 1, and is performed with HUKTE = 1 alone. Record rd. Needs the mappings of
    _h_hlsv_paging_tests and the two-stage translation of the caller."""
    rd, addr, tmp = regs
    name = MT_NAMES[mt_mode]
    good = GOOD_TAG[mt_mode]
    pointer = _tag_field(good, mt_mode) | (VS_USER_MTAG_VA + 16 * VS_PAGE_CHUNK)
    mtag_i = 1 << HSTATUS_MTAG_I_BIT

    def ukte(on: bool) -> list[str]:
        return [f"LI(x{tmp}, SENVCFG_UKTE)", f"csr{'s' if on else 'c'} senvcfg, x{tmp}"]

    def hukte(on: bool) -> list[str]:
        return [f"LI(x{tmp}, HSTATUS_HUKTE)", f"csr{'s' if on else 'c'} hstatus, x{tmp}"]

    def access(case: str, coverpoint: str, instruction: str, mode: str) -> list[str]:
        """instruction with addr = pointer and rd = RD_CANARY, hstatus.MTAG_I = 0 for HLV, in mode."""
        return [
            *([f"LI(x{tmp}, {mtag_i:#x})", f"csrc hstatus, x{tmp}"] if instruction.startswith("hlv") else []),
            *([f"RVTEST_TSBI_GOTO_{mode}MODE"] if mode != "S" else []),
            f"LI(x{addr}, {pointer:#x})",
            f"LI(x{rd}, {RD_CANARY:#x})",
            test_data.add_testcase(
                f"{'HS' if mode == 'S' else 'HU' if mode == 'U' else mode}_{name}_svukte_{case}",
                coverpoint,
                "Zimt_H_cg",
            ),
            instruction,
            *(["RVTEST_TSBI_GOTO_SMODE"] if mode != "S" else []),
            write_sigupd(rd, test_data),
        ]

    def code_alias(user: bool) -> list[str]:
        """The guest code alias, as a user page or not."""
        return [
            *write_pte(
                VS_SV39,
                level=VS_SV39.levels - 1,
                flags=PteFlags(user=user),
                virtual_address=VS_SV39.code_va,
                physical_address=SV39X4.code_va,
                regs=regs,
                pa_is_label=False,
                superpage=True,
            ),
            "hfence.vvma",
        ]

    load, store_tag = f"ld x{rd}, 0(x{addr})", f"settag x{addr}, 0"
    hlv = f"hlv.d x{rd}, (x{addr})"
    return [
        comment_banner(
            f"cp_svukte_tag_v, cp_svukte_tag_hu, cp_svukte_tag_hs (VU, HU, HS, {name})",
            "With two-stage translation and vsvittu putting the tags of the VS-stage user tagged-data page in the\n"
            "upper half: in VU-mode, a load and settag of a chunk there raise the page fault of their tag access\n"
            "(GVA = 1) with senvcfg.UKTE = 1, and the load is performed with UKTE = 0; hlv.d with hstatus.SPVP = 0\n"
            "raises it in HU-mode with hstatus.HUKTE = 1 and in HS-mode with UKTE = 1, and is performed with the\n"
            "other one alone. Record rd",
        ),
        *create_page_mapping(
            VS_SV39,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False),
            virtual_address=hex(VS_USER_TAGS_VA),
            physical_address=SV39X4.data_va,
            regs=regs,
            pa_is_label=False,
        ),
        *write_pte(
            VS_SV39,
            level=VS_SV39.levels - 1,
            flags=PteFlags.nonleaf(),
            virtual_address=hex((VS_USER_TAGS_VA + UPPER_HALF) & MASK64),
            physical_address=VS_SV39.page_table_label(1),
            regs=regs,
        ),
        *code_alias(True),
        *_vs_tag(VS_USER_MTAG_VA + 16 * VS_PAGE_CHUNK, good, mt_mode, (addr, tmp)),
        f"LI(x{tmp}, {(_vs_tag_vitt(mt_mode, VS_USER_TAGS_VA) + UPPER_HALF) & MASK64:#x})",
        f"csrw CSR_VSVITTU, x{tmp}",
        *_set_pmm(tmp, "SSNPM"),
        f"LI(x{addr}, {mt_mode << MT_MODE_LSB:#x})",
        f"or x{tmp}, x{tmp}, x{addr}",
        f"csrs senvcfg, x{tmp}",
        *ukte(True),
        *access("ld_upper_ukte", "cp_svukte_tag_v", load, "VU"),
        *access("settag_upper_ukte", "cp_svukte_tag_v", store_tag, "VU"),
        *ukte(False),
        *access("ld_upper", "cp_svukte_tag_v", load, "VU"),
        *code_alias(False),
        # HU-mode: HLV with SPVP = 0 uses hstatus.VUMT_MODE and HUPMM, and HUKTE
        f"LI(x{tmp}, HSTATUS_SPVP)",
        f"csrc hstatus, x{tmp}",
        *_set_pmm(tmp, "SSNPM"),
        f"slli x{tmp}, x{tmp}, {HUPMM_LSB - PMM_LSB}",
        f"csrs hstatus, x{tmp}",
        f"LI(x{tmp}, HSTATUS_HU | {mt_mode << VUMT_MODE_LSB:#x})",
        f"csrs hstatus, x{tmp}",
        *hukte(True),
        *access("hlv_upper_hukte", "cp_svukte_tag_hu", hlv, "U"),
        *hukte(False),
        *ukte(True),
        *access("hlv_upper_ukte", "cp_svukte_tag_hu", hlv, "U"),
        f"LI(x{tmp}, HSTATUS_HU | {(0b11 << VUMT_MODE_LSB) | (0b11 << HUPMM_LSB):#x})",
        f"csrc hstatus, x{tmp}",
        # HS-mode: HLV with SPVP = 0 uses senvcfg.MT_MODE and PMM, and UKTE
        *access("hlv_upper_ukte", "cp_svukte_tag_hs", hlv, "S"),
        *ukte(False),
        *hukte(True),
        *access("hlv_upper_hukte", "cp_svukte_tag_hs", hlv, "S"),
        *hukte(False),
        f"LI(x{tmp}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
        f"csrc senvcfg, x{tmp}",
        "csrw CSR_VSVITTU, x0",
    ]


def _h_g_stage_mtag_tests(test_data: TestData, cg: str, regs: tuple[int, int, int]) -> list[str]:
    """With the G stage only and memory tagging disabled in VS-mode, a G-stage leaf PTE with PTE.MTAG, which is reserved
    there: in VS-mode, a load and a store of its guest physical page raise a load and a store/AMO guest-page fault,
    which HS-mode takes."""
    _, addr, tmp = regs
    return [
        *create_page_mapping(
            SV39X4,
            leaf_level=0,
            leaf_flags=PteFlags(user=True, execute=False, extra=(PTE_MTAG,)),
            virtual_address=hex(G_MTAG_GPA),
            physical_address=CHECK_DATA,
            regs=regs,
        ),
        "hfence.gvma",
        f"LI(x{tmp}, {0b11 << MT_MODE_LSB:#x})",
        f"csrc henvcfg, x{tmp}",
        "RVTEST_TSBI_GOTO_VSMODE",
        f"LI(x{addr}, {G_MTAG_GPA + 16 * G_STAGE_CHUNK:#x})",
        f"LI(x{tmp}, {RD_CANARY:#x})",
        test_data.add_testcase("VS_g_stage_mtag_load", "cp_mtag_g_stage", cg),
        f"ld x{tmp}, 0(x{addr})",
        write_sigupd(tmp, test_data),
        test_data.add_testcase("VS_g_stage_mtag_store", "cp_mtag_g_stage", cg),
        f"sd x{tmp}, 8(x{addr})",
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
    """checktag in VS-mode with two-stage translation and with the G stage only, and loads and stores: with two-stage
    translation tag checked in a VS-stage PTE.MTAG page only, also HLV and HSV, and not from a VS-stage tagcheck-exempt
    code page; with MPRV, MPV = 1 and MPP = U tag checked in a VS-stage user PTE.MTAG page; tag checked with the G stage
    only, and with 4-bit tags a G-stage leaf PTE with PTE.MTAG, which is reserved there. With two-stage translation,
    also the protection of the tag storage (Svatag): the loads and settags of VS-mode and VU-mode, HLV and HSV (also in
    HU-mode) and, through MPRV with MPV = 1, the loads of VS-mode and VU-mode in the VITT ranges of their modes raise
    access faults, and HLVX none (_h_hlsv_vitt_tests, _h_mprv_vitt_tests); and with Svukte, which Svatag depends on,
    the tag accesses of VU-mode and of HLV with SPVP = 0 at a tag address in the upper half raise page faults with
    senvcfg.UKTE, or hstatus.HUKTE for HLV in HU-mode (_h_svukte_tests)."""
    name = MT_NAMES[mt_mode]
    pte, addr, tmp = test_data.int_regs.get_registers(3)
    regs = (pte, addr, tmp)
    lines = [
        comment_banner(
            "cp_checktag_two_stage, cp_checktag_g_stage, cp_checked_translated, cp_checked_vs_tagged_page, "
            f"cp_checked_g_stage, cp_mtag_g_stage (VS, {name})",
            f"In VS-mode with {TAG_BITS[mt_mode]}-bit tags, checktags with two-stage translation whose tag page is\n"
            "valid with matching or mismatching tags, execute-only in the VS stage (load page fault), or\n"
            "execute-only or invalid in the G stage (load guest-page fault), and with the G stage only whose tag\n"
            "page is valid or execute-only, or whose tag table base is above the guest physical addresses of\n"
            "Sv39x4. HS-mode takes the traps. With two-stage translation, a load and a store with a mismatching\n"
            "pointer tag of a page whose VS-stage leaf PTE has no PTE.MTAG: not tag checked; with the matching and a\n"
            "mismatching one of a page whose VS-stage leaf PTE has PTE.MTAG: tag checked. With the G stage only,\n"
            "loads and stores with the matching and a mismatching pointer tag, and with their tags in a page that\n"
            "the G stage maps execute-only (load guest-page fault, also for the store): tag checked. Then with\n"
            "4-bit tags, with memory tagging disabled, a load and a store of a page whose G-stage leaf PTE has\n"
            "PTE.MTAG, which is reserved there: load and store/AMO guest-page faults",
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
    lines += _h_two_stage_mtag_tests(test_data, cg, mt_mode, regs)
    lines += _h_hlsv_paging_tests(test_data, cg, mt_mode, regs)
    lines += _h_vs_code_tests(test_data, cg, mt_mode, regs)
    lines += _h_hlsv_vitt_tests(test_data, mt_mode, regs)
    lines += gated(_h_svukte_tests(test_data, mt_mode, regs), "defined(SVUKTE_SUPPORTED)")
    lines += gated(_h_mprv_vu_paging_tests(test_data, mt_mode, regs), STANDARD_SM_GATE)
    lines += gated(_h_mprv_vitt_tests(test_data, mt_mode, regs), STANDARD_SM_GATE)
    lines += [*guest_translation_teardown(test_data), *guest_translation_setup(test_data, SV39X4, None, "VSmode")]
    g_stage = []
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
        g_stage += _h_guest_checktag_case(
            test_data, cg, mt_mode, case, "cp_checktag_g_stage", int(SV39X4.data_va, 16), setup
        )
    g_stage += _h_guest_checktag_case(
        test_data, cg, mt_mode, "g_stage_gpa_too_wide", "cp_checktag_g_stage", H_GPA_TOO_WIDE, []
    )
    g_stage += _h_g_stage_checked_tests(test_data, cg, mt_mode, regs)
    # The G stage only: VS-mode's first-stage translation is Bare
    lines += gated(g_stage, NO_BARE_VITT_RANGE)
    if mt_mode == MT_TAG4:
        lines += _h_g_stage_mtag_tests(test_data, cg, regs)
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
            *_mtag_i_write_tests(test_data, cg, "mstatus", MSTATUS_MTAG_I_BIT, "sstatus"),
        ]
    )
    chunks.append(test_data.end_test_chunk())

    tc = test_data.begin_test_chunk("Sm_mt")
    tc.code.extend(gated(_m_mt_tests(test_data, cg), NO_M_VITT_RANGE))
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

    # S-mode uses menvcfg.MT_MODE and menvmtagexclude, which it sets through T-SBI. The M-mode exclusion mask and the
    # U-mode MT_MODE and mask hold other values; mseccfg.MT_MODE stays 00 for the M-mode trap handler.
    tc = test_data.begin_test_chunk("S_mt")
    lines = []
    val, tmp = test_data.int_regs.get_registers(2)
    for mt_mode, other in MT_ITERATIONS:
        iteration = _via_tsbi(_configure([("menvcfg", mt_mode), ("senvcfg", other)], ["m", "menv", "senv"], val, tmp))
        test_data.int_regs.return_registers([val, tmp])
        iteration += _mt_mode_tests(test_data, cg, "S", mt_mode, ENV_TAG["menv"])
        lines += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
        val, tmp = test_data.int_regs.get_registers(2)
    lines += _via_tsbi(_restore(["menvcfg", "senvcfg"], ["m", "menv", "senv"], val, tmp))
    test_data.int_regs.return_registers([val, tmp])
    tc.code += gated(lines, NO_BARE_VITT_RANGE)
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
    lines = []
    val, tmp = test_data.int_regs.get_registers(2)
    for mt_mode, _ in MT_ITERATIONS:
        iteration = [
            "RVTEST_TSBI_GOTO_SMODE",
            *_configure([("senvcfg", mt_mode)], ["senv"], val, tmp),
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_registers([val, tmp])
        iteration += _mt_mode_tests(test_data, cg, "U", mt_mode, ENV_TAG["senv"])
        lines += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
        val, tmp = test_data.int_regs.get_registers(2)
    lines += [
        "RVTEST_TSBI_GOTO_SMODE",
        *_restore(["senvcfg"], ["senv"], val, tmp),
        "RVTEST_TSBI_GOTO_UMODE",
    ]
    test_data.int_regs.return_registers([val, tmp])
    tc.code += gated(lines, NO_BARE_VITT_RANGE)
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
            *_mtag_i_write_tests(test_data, cg, "hstatus", HSTATUS_MTAG_I_BIT),
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
    lines = []
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
            lines += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    lines += _restore([], ["senv", "henv"], val, tmp)
    test_data.int_regs.return_registers([val, tmp])
    tc.code += gated(lines, NO_BARE_VITT_RANGE)
    chunks.append(test_data.end_test_chunk())
    return chunks


@add_priv_test_generator(
    "Zimt",
    required_extensions=["Zimt", "Zimop", "Sm", "S", "Smstateen"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_MMODE"],
)
def make_zimt_sm_stateen(test_data: TestData) -> list[TestChunk]:
    """Generate the tests of mstateen0.MT and hstateen0.MT, which gate the S-level and H-level Zimt and Svatag CSRs.

    M-mode writes mstateen0 and hstateen0, and the CSRs are accessed from M, S, U, VS and VU-mode through T-SBI mode
    changes. The boot code sets both MT bits, which the tests set again at their end.
    """
    cg = "Zimt_Sm_cg"
    tc = test_data.begin_test_chunk("Sm_stateen")
    tc.code += [*_stateen_mt_warl_tests(test_data, cg), *_stateen_mt_access_tests(test_data, cg)]
    return [test_data.end_test_chunk()]


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
    lines = [
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
        lines += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    val, tmp = test_data.int_regs.get_registers(2)
    lines += [
        comment_banner("Restore", "mseccfg.PMM = 00 and mvitt = 0"),
        *_write_field("mseccfg", PMM_LSB, 0, val, tmp),
        "csrw CSR_MVITT, x0",
    ]
    test_data.int_regs.return_registers([val, tmp])
    tc.code += gated(lines, NO_M_VITT_RANGE)
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
        # The records follow the gated access-fault case: label them with a testcase outside the gate
        record_label = test_data.current_testcase_label
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
            *_record_tags(test_data, base, val, window, label=record_label),
            "RVTEST_TSBI_GOTO_UMODE",
        ]
        test_data.int_regs.return_registers([base, val, tmp])
        tc.code += gated(_tag7(iteration) if mt_mode == MT_TAG7 else iteration, NO_BARE_VITT_RANGE)
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
        iteration = gated(iteration, NO_BARE_VITT_RANGE)
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


def _h_mtag_i_access_tests(test_data: TestData, cg: str, mode: str, mt_mode: int) -> list[str]:
    """In VS-mode or VU-mode with Bare translation and memory tagging enabled, hstatus.MTAG_I = 1, which only makes HLV
    and HSV unchecked: a load and a store with a mismatching pointer tag raise a software-check exception."""
    name = MT_NAMES[mt_mode]
    ptr, val, tmp, save = test_data.int_regs.get_registers(4)
    mtag_i = f"{1 << HSTATUS_MTAG_I_BIT:#x}"
    lines = [
        comment_banner(
            f"cp_checked_hstatus_mtag_i ({mode}, {name})",
            f"In {mode}-mode with hstatus.MTAG_I = 1, which only affects HLV and HSV: a load and a store with a\n"
            f"mismatching pointer tag: {SW_CHECK_TEXT}. Record rd and memory",
        ),
        "RVTEST_TSBI_GOTO_SMODE",
        f"LI(x{tmp}, {mtag_i})",
        f"csrs hstatus, x{tmp}",
        f"RVTEST_TSBI_GOTO_{mode}MODE",
        *_check_pointer(ptr, tmp, mt_mode, 3, BAD_TAG[mt_mode]),
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"{mode}_{name}_hstatus_mtag_i_load", "cp_checked_hstatus_mtag_i", cg),
        f"ld x{val}, 0(x{ptr})",
        write_sigupd(val, test_data),
        f"LI(x{val}, 0xfedcba9876543210)",
        test_data.add_testcase(f"{mode}_{name}_hstatus_mtag_i_store", "cp_checked_hstatus_mtag_i", cg),
        f"sd x{val}, 0(x{ptr})",
        *_record_via_sp(test_data, ptr, 0, val, save),
        "RVTEST_TSBI_GOTO_SMODE",
        f"LI(x{tmp}, {mtag_i})",
        f"csrc hstatus, x{tmp}",
        f"RVTEST_TSBI_GOTO_{mode}MODE",
    ]
    test_data.int_regs.return_registers([ptr, val, tmp, save])
    return lines


# The data chunk of the HLV and HSV tests, whose memory tag is GOOD_TAG
HLSV_CHUNK = 6
HUPMM_LSB = 48  # hstatus.HUPMM: bits 49:48


def _h_hlsv_tests(test_data: TestData, cg: str, mt_mode: int) -> list[str]:
    """HLV and HSV in HS-mode and HU-mode with Bare vsatp and hgatp, which make all guest pages tagged-data pages: they
    are checked with the MT_MODE, tag table and pointer masking of their guest mode, VS-mode with hstatus.SPVP = 1
    (henvcfg, vsvitts) and VU-mode with SPVP = 0 (vsvittu; senvcfg in HS-mode, hstatus.VUMT_MODE and HUPMM in HU-mode),
    and a mismatch raises a software-check exception with hstatus.GVA = 1, which HS-mode takes. Not with
    hstatus.MTAG_I = 1, and never HLVX. The tag table of the other guest mode is the second tag table page, where the
    chunk of the accesses has the mismatching tag, so that with it the outcome of each case differs. Memory tagging
    stays disabled in HS-mode, and in HU-mode but for the case with senvcfg.MT_MODE set, whose U-mode code accesses
    memory only through sp and HLV."""
    name = MT_NAMES[mt_mode]
    ptr, val, tmp, save = test_data.int_regs.get_registers(4)
    mt = mt_mode << MT_MODE_LSB
    data = f"{CHECK_DATA} + {16 * HLSV_CHUNK}"
    other_table = f"{TAG_TABLE} + 0x1000"

    def access(case: str, coverpoint: str, tag: int, store: bool = True) -> list[str]:
        """hlv.d and, if store, hsv.d of HLSV_CHUNK through a pointer with tag. Record rd, and the doubleword through
        sp, and restore it."""
        lines = [
            *_check_pointer(ptr, tmp, mt_mode, HLSV_CHUNK, tag),
            f"LI(x{val}, {RD_CANARY:#x})",
            test_data.add_testcase(f"{case}_hlv", coverpoint, cg),
            f"hlv.d x{val}, (x{ptr})",
            write_sigupd(val, test_data),
        ]
        if not store:
            return lines
        return [
            *lines,
            f"LI(x{val}, 0x0123456789abcdef)",
            test_data.add_testcase(f"{case}_hsv", coverpoint, cg),
            f"hsv.d x{val}, (x{ptr})",
            *_record_via_sp(test_data, ptr, 0, val, save),
            f"LA(x{tmp}, {data})",
            f"LI(x{val}, {_check_data_dword(HLSV_CHUNK, 0):#x})",
            f"sd x{val}, 0(x{tmp})",
        ]

    def enable(csr: str) -> list[str]:
        """Set MT_MODE and PMM in csr (henvcfg or senvcfg), or VUMT_MODE and HUPMM in hstatus."""
        shift = HUPMM_LSB - PMM_LSB if csr == "hstatus" else 0
        return [
            *_set_pmm(tmp, "SSNPM"),
            *([f"slli x{tmp}, x{tmp}, {shift}"] if shift else []),
            f"LI(x{val}, {mt << shift:#x})",
            f"or x{tmp}, x{tmp}, x{val}",
            f"csrs {csr}, x{tmp}",
        ]

    def write(op: str, csr: str, value: str) -> list[str]:
        return [f"LI(x{tmp}, {value})", f"{op} {csr}, x{tmp}"]

    lines = [
        comment_banner(
            f"cp_hlsv_checked, cp_hlsv_mtag_i, cp_hlvx (HS, {name})",
            f"In HS-mode with Bare vsatp and hgatp, {TAG_BITS[mt_mode]}-bit tags in VS-mode (henvcfg.MT_MODE, vsvitts)\n"
            "and hstatus.SPVP = 1: hlv.d and hsv.d with the matching pointer tag, and with a mismatching one: a\n"
            f"{SW_CHECK_TEXT} with hstatus.GVA = 1; with hstatus.MTAG_I = 1: not\n"
            "checked. vsvittu points to the second tag table page, where the chunk has the mismatching tag. Through a\n"
            "pointer without a pointer tag to a chunk whose tag is not 0: hlv.wu, checked, and hlvx.wu, never\n"
            "checked. Record rd and memory",
        ),
        "csrw CSR_VSATP, x0",
        "csrw CSR_HGATP, x0",
        *_check_vitt("CSR_VSVITTU", mt_mode, (save, tmp, val), table=other_table),
        *_check_fill(mt_mode, save, tmp, (HLSV_CHUNK,)),
        *_check_vitt("CSR_VSVITTS", mt_mode, (save, tmp, val)),
        *_check_fill(mt_mode, save, tmp, BAD_CHUNKS),
        *enable("henvcfg"),
        *write("csrs", "hstatus", "HSTATUS_SPVP"),
        *access(f"HS_{name}_vs_match", "cp_hlsv_checked", GOOD_TAG[mt_mode]),
        *access(f"HS_{name}_vs_mismatch", "cp_hlsv_checked", BAD_TAG[mt_mode]),
        *write("csrs", "hstatus", f"{1 << HSTATUS_MTAG_I_BIT:#x}"),
        *access(f"HS_{name}_mtag_i", "cp_hlsv_mtag_i", BAD_TAG[mt_mode]),
        *write("csrc", "hstatus", f"{1 << HSTATUS_MTAG_I_BIT:#x}"),
        f"LA(x{ptr}, {data})",
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"HS_{name}_hlv_wu", "cp_hlvx", cg),
        f"hlv.wu x{val}, (x{ptr})",
        write_sigupd(val, test_data),
        f"LI(x{val}, {RD_CANARY:#x})",
        test_data.add_testcase(f"HS_{name}_hlvx_wu", "cp_hlvx", cg),
        f"hlvx.wu x{val}, (x{ptr})",
        write_sigupd(val, test_data),
        *write("csrc", "henvcfg", f"{(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x}"),
        comment_banner(
            f"cp_hlsv_checked, cp_hlsv_vu_field_hs, cp_hlsv_vu_field_hu (HS, HU, {name})",
            "With hstatus.SPVP = 0 (VU-mode) and vsvittu, and vsvitts pointing to the second tag table page. In HS-mode,\n"
            "with senvcfg.MT_MODE set: hlv.d and hsv.d with the matching pointer tag, and with a mismatching one,\n"
            "checked; with hstatus.VUMT_MODE set instead: hlv.d with a mismatching one, not checked. In HU-mode\n"
            "(hstatus.HU = 1, hstatus.HUPMM), hlv.d with a mismatching pointer tag: checked with hstatus.VUMT_MODE\n"
            "set, not with senvcfg.MT_MODE set instead. Record rd and memory",
        ),
        *write("csrc", "hstatus", "HSTATUS_SPVP"),
        *_check_vitt("CSR_VSVITTS", mt_mode, (save, tmp, val), table=other_table),
        *_check_vitt("CSR_VSVITTU", mt_mode, (save, tmp, val)),
        *enable("senvcfg"),
        *access(f"HS_{name}_vu_match", "cp_hlsv_checked", GOOD_TAG[mt_mode]),
        *access(f"HS_{name}_vu_mismatch", "cp_hlsv_checked", BAD_TAG[mt_mode]),
        *write("csrc", "senvcfg", f"{0b11 << MT_MODE_LSB:#x}"),
        *write("csrs", "hstatus", f"{mt_mode << VUMT_MODE_LSB:#x}"),
        *access(f"HS_{name}_vu_vumt", "cp_hlsv_vu_field_hs", BAD_TAG[mt_mode], store=False),
        *enable("hstatus"),
        *write("csrs", "hstatus", "HSTATUS_HU"),
        "RVTEST_TSBI_GOTO_UMODE",
        *access(f"HU_{name}_vumt", "cp_hlsv_vu_field_hu", BAD_TAG[mt_mode], store=False),
        "RVTEST_TSBI_GOTO_SMODE",
        *write("csrc", "hstatus", f"{0b11 << VUMT_MODE_LSB:#x}"),
        *write("csrs", "senvcfg", f"{mt:#x}"),
        "RVTEST_TSBI_GOTO_UMODE",
        *access(f"HU_{name}_senvcfg", "cp_hlsv_vu_field_hu", BAD_TAG[mt_mode], store=False),
        "RVTEST_TSBI_GOTO_SMODE",
        *write("csrc", "hstatus", f"HSTATUS_HU | {0b11 << HUPMM_LSB:#x}"),
        *write("csrc", "senvcfg", f"{(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x}"),
        "csrw CSR_VSVITTS, x0",
        "csrw CSR_VSVITTU, x0",
    ]
    test_data.int_regs.return_registers([ptr, val, tmp, save])
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
    LR/SC and AMOs, checktag with sp as rs1, and with 7-bit tags a memory tag with bit 7 set."""
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
        *_checked_regular_tests(test_data, cg, mode, mt_mode, True),
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
    this needs S-mode pointer masking and tag table. With mstatus.MTAG_I = 1 too, they are not checked.
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
        iteration += gated(
            [
                f"LI(x{mt}, {mt_mode << MT_MODE_LSB:#x})",
                *_checked_access_tests(test_data, cg, "M", mt_mode, (*INT_ACCESSES, *FP_ACCESSES), False, mt_lines),
                *gated(_two_chunk_tests(test_data, cg, "M", mt_mode, False, mt_lines), MISALIGNED_LDST_GATE),
                *_sp_base_tests(test_data, cg, "M", mt_mode, mt_lines),
                *_order_tests(test_data, cg, "M", mt_mode, False, mt_lines),
                *_unchecked_access_tests(test_data, cg, "M", mt_mode, mt_lines, m_mode=True),
                *_checked_regular_tests(test_data, cg, "M", mt_mode, False, mt_lines, m_mode=True),
                *_checktag_sp_tests(test_data, cg, "M", mt_mode, False, mt_lines),
            ],
            NO_M_VITT_RANGE,
        )
        test_data.int_regs.return_register(mt)
        # With MPRV, the effective mode's translation is Bare; _m_checked_mprv_tests also enables memory tagging in
        # M-mode around loads and stores
        iteration += gated(
            gated(_m_checked_mprv_tests(test_data, cg, mt_mode), f"({NO_M_VITT_RANGE}) && ({NO_BARE_VITT_RANGE})"),
            SM_MPRV_GATE,
        )
        iteration += gated(
            gated(_m_checked_mprv_regular_tests(test_data, cg, mt_mode), NO_BARE_VITT_RANGE), SM_MPRV_GATE
        )
        iteration += gated(gated(_m_checked_mprv_v_tests(test_data, cg, mt_mode), NO_BARE_VITT_RANGE), SM_MPRV_V_GATE)
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
    required_extensions=["Zimt", "Zimop", "Sm", "S", "Svatag", "Smnpm", "Sdtrig"],
    march_extensions=["Zimop"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_MMODE"],
)
def make_zimt_sm_trigger(test_data: TestData) -> list[TestChunk]:
    """Generate the tests of the implicit tag checks with Sdtrig triggers, in M-mode with mstatus.MPRV = 1 and MPP = S.

    The accesses are checked with S-mode's memory tagging (menvcfg.MT_MODE, svitts, Smnpm), with Bare translation, so
    the tests exist only without Svatag's Bare VITT range; M-mode, whose trap handler takes the breakpoint and
    software-check exceptions, keeps memory tagging disabled. Like the Sdtrig tests, they assume that load and store
    address triggers fire before the access.
    """
    _check_sig_reg(test_data)
    cg = "Zimt_Sm_cg"
    tc = test_data.begin_test_chunk("Sm_trigger")
    lines = []
    for mt_mode in (MT_TAG4, MT_TAG7):
        iteration = _m_trigger_tests(test_data, cg, mt_mode)
        lines += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.code += [*_trigger_defines(), *gated(lines, f"({NO_BARE_VITT_RANGE}) && {TRIGGER_CAPABLE}")]
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
    translation, then the checktag tests with Sv39 translation, loads and stores of a page without PTE.MTAG, which are
    not tag checked, and the PTE.MTAG tests: tagged-data pages, pages with PTE.MTAG that are not (X = 1, or user pages
    for S-mode), loads and stores over two pages (also into an unmapped page), tagcheck-exempt code pages (also
    execute-only), PTE.MTAG in a non-leaf PTE and with memory tagging disabled, and U-mode's loads through MPRV in M-mode.
    Last, the protection of the tag storage (Svatag), with Sv39: the regular accesses and settags of S-mode in its VITT
    range, at its edges, and of U-mode, through MPRV in M-mode and in U-mode itself, raise access faults
    (_s_vitt_tests); and with Svukte, which Svatag depends on, the tag accesses of U-mode (also through MPRV) at a tag
    address in the upper half raise page faults with senvcfg.UKTE (_s_svukte_tests).

    With Bare translation and memory tagging enabled in S-mode (menvcfg), the tests raise no exception, as in M-mode:
    the trap handler of S-mode would be tag checked, and so would the read of the trapping instruction by the trap
    handler of M-mode, which uses mstatus.MPRV = 1 with MPP = S. The mismatches of S-mode's loads and stores are those
    of Zimt_Sm_checktag with MPRV, but for those with mstatus.MTAG_I = 1, which makes that read unchecked and not the
    loads and stores of S-mode, and which M-mode takes. With Sv39, the trap handlers access pages without PTE.MTAG,
    which are not checked.
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
            *_checked_regular_tests(test_data, cg, "S", mt_mode, False),
            *_checktag_sp_tests(test_data, cg, "S", mt_mode, False),
            *gated(_s_mtag_i_tests(test_data, "Zimt_Sm_cg", mt_mode), STANDARD_SM_GATE),
        ]
        val = test_data.int_regs.get_register()
        iteration += [
            f"LI(x{val}, {(0b11 << MT_MODE_LSB) | (0b11 << PMM_LSB):#x})",
            tsbi_call(f"csrc menvcfg, x{val}"),
            "csrw CSR_SVITTS, x0",
        ]
        test_data.int_regs.return_register(val)
        iteration = gated(iteration, NO_BARE_VITT_RANGE)
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
    # The registers of the code pages (pointer, value, return address), which both tag widths use
    p, v, r = test_data.int_regs.get_registers(3)
    code = (p, v, r)
    tc.code += _mtag_mapping(test_data)
    tc.code += _s_mtag_tests(test_data, cg, MT_TAG4, code)
    tc.code += _tag7(_s_mtag_tests(test_data, cg, MT_TAG7, code))
    tc.code += _s_vitt_tests(test_data, cg, MT_TAG4, code)
    tc.code += _tag7(_s_vitt_tests(test_data, cg, MT_TAG7, code))
    tc.code += gated(_s_svukte_tests(test_data, cg, MT_TAG4, code), "defined(SVUKTE_SUPPORTED)")
    tc.code += gated(_tag7(_s_svukte_tests(test_data, cg, MT_TAG7, code)), "defined(SVUKTE_SUPPORTED)")
    test_data.int_regs.return_registers(list(code))
    tc.code += [
        comment_banner("Restore", "satp = 0 and svitts = 0"),
        "csrw satp, x0",
        "sfence.vma",
        "csrw CSR_SVITTS, x0",
    ]
    tc.raw_data += [*_tag_table_data(), *_check_data(), *lower_table_data(SV39), *_mtag_data(code)]
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
        tc.code += gated(_tag7(iteration) if mt_mode == MT_TAG7 else iteration, NO_BARE_VITT_RANGE)
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
    vsvittu, and of HLV and HSV in HS-mode and HU-mode.

    With Bare translation (vsatp and hgatp), VS-mode uses henvcfg.MT_MODE and henvcfg.PMM, VU-mode senvcfg.MT_MODE and
    senvcfg.PMM, which HS-mode sets, as the tags. HS-mode, which takes the exceptions, keeps memory tagging disabled,
    and so does VS-mode while VU-mode runs. The loads and stores are integer ones; hstatus.MTAG_I does not make them
    unchecked. HLV and HSV are checked with the
    memory tagging of their guest mode: VS-mode's with hstatus.SPVP = 1; with SPVP = 0 VU-mode's, senvcfg.MT_MODE in
    HS-mode and hstatus.VUMT_MODE in HU-mode; not with hstatus.MTAG_I = 1, and HLVX never. Then, with Sv39, VS-mode
    checktags with guest translation, whose page faults and guest-page faults HS-mode takes, loads and stores of a page
    whose VS-stage leaf PTE has PTE.MTAG or not, also HLV and HSV and from VS-stage code pages with PTE.MTAG or not,
    VU-mode's through MPRV in M-mode, and of a page whose G-stage leaf PTE has it, which is reserved there; and the
    protection of the tag storage (Svatag) with two-stage translation: the regular accesses and settags of VS-mode and
    VU-mode, HLV and HSV (also in HU-mode) and the loads of VS-mode and VU-mode through MPRV in the VITT ranges of their
    modes raise access faults, and HLVX none; and with Svukte, which Svatag depends on, the page faults of the tag
    accesses of VU-mode and of HLV at a tag address in the upper half with senvcfg.UKTE or hstatus.HUKTE.
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
            iteration += _h_mtag_i_access_tests(test_data, cg, mode, mt_mode)
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
        iteration += _h_hlsv_tests(test_data, cg, mt_mode)
        iteration = gated(iteration, NO_BARE_VITT_RANGE)
        iteration += gated(_h_guest_checktag_tests(test_data, cg, mt_mode), "defined(SV39_SUPPORTED)")
        tc.code += _tag7(iteration) if mt_mode == MT_TAG7 else iteration
    tc.raw_data += [*_tag_table_data(), *_check_data(), *guest_table_data()]
    return [test_data.end_test_chunk()]
