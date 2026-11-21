##################################
# priv/extensions/VatagCommon.py
#
# Shared helpers for the Svatag and Smvatag (tag table base CSR) test generators.
# SPDX-License-Identifier: Apache-2.0
##################################

"""Shared helpers for the Svatag and Smvatag test generators.

Svatag and Smvatag define the virtually indexed tag table (VITT) base CSRs: mvitt (M-mode, Smvatag), svitts (S/HS),
svittu (U), vsvitts (VS) and vsvittu (VU) (Svatag). The CSR addresses are named in rvtest_experimental.h. A base must
be 4 KiB aligned, so its bits 11:0 read 0.
"""

from testgen.asm.csr import gen_csr_write_sigupd
from testgen.asm.helpers import comment_banner, gated, write_sigupd
from testgen.asm.tsbi import tsbi_call
from testgen.data.state import TestData

MASK64 = (1 << 64) - 1
# A tag table base CSR: (name, CSR, preprocessor condition under which the CSR exists, or None)
VittCsr = tuple[str, str, str | None]
M_VITT: list[VittCsr] = [("mvitt", "CSR_MVITT", None)]
S_VITT: list[VittCsr] = [("svitts", "CSR_SVITTS", None), ("svittu", "CSR_SVITTU", None)]
VS_VITT: list[VittCsr] = [
    ("vsvitts", "CSR_VSVITTS", "defined(H_SUPPORTED)"),
    ("vsvittu", "CSR_VSVITTU", "defined(H_SUPPORTED)"),
]
# 4 KiB aligned bases, which read back as written: canonical Sv39 addresses, which every address width holds
VITT_ALIGNED = (0x0000_0000_8000_0000, 0xFFFF_FFC0_0000_1000, 0x0000_003F_FFFF_F000, 0xFFFF_FFFF_FFFF_F000, 0)
# Bases that are not 4 KiB aligned, which are illegal. Their legalization is implementation-defined: only check that
# bits 11:0 read 0.
VITT_UNALIGNED = (0x0000_0000_8000_0FFF, 0x0000_0000_0000_0001, MASK64)


def vitt_warl_tests(test_data: TestData, cg: str, mode: str, csrs: list[VittCsr]) -> list[str]:
    """Write bases to each (name, CSR, condition) from mode and read them back."""
    coverpoint = "cp_vitt_warl"
    save, val = test_data.int_regs.get_registers(2)
    lines = [
        comment_banner(
            f"{coverpoint} ({mode}-mode)",
            "Write 4 KiB aligned bases and read them back.  As written\n"
            "Write bases that are not aligned and record whether bits 11:0 read 0.  1",
        )
    ]
    for name, csr, _ in csrs:
        lines.append(f"csrr x{save}, {csr}")
        for value in VITT_ALIGNED:
            lines += [
                f"LI(x{val}, {value:#x})",
                test_data.add_testcase(f"{mode}_{name}_{value:016x}", coverpoint, cg),
                gen_csr_write_sigupd(val, csr, test_data),
            ]
        for value in VITT_UNALIGNED:
            lines += [
                f"LI(x{val}, {value:#x})",
                test_data.add_testcase(f"{mode}_{name}_{value:016x}", coverpoint, cg),
                f"csrw {csr}, x{val}",
                f"csrr x{val}, {csr}",
                f"slli x{val}, x{val}, 52",
                f"seqz x{val}, x{val}    # 1 if bits 11:0 read 0",
                write_sigupd(val, test_data),
            ]
        lines.append(f"csrw {csr}, x{save}")
    test_data.int_regs.return_registers([save, val])
    return lines


def vitt_access_tests(test_data: TestData, cg: str, mode: str, csrs: list[VittCsr]) -> list[str]:
    """Read each (name, CSR, condition) from mode, write an aligned base with csrrw and read it again.

    An access the mode may not make raises an illegal-instruction or virtual-instruction exception, which the trap
    signature records. T-SBI calls, which access the CSRs from M-mode or HS-mode, write a base to each CSR first and
    read it after the write: a write that raised an exception leaves that base. From VS-mode, a write to svitts or
    svittu reaches vsvitts or vsvittu, so the T-SBI read of svitts or svittu, from HS-mode, also reads the base
    written first.
    """
    coverpoint = "cp_vitt_access"
    reg = test_data.int_regs.get_register()
    lines = [
        comment_banner(
            f"{coverpoint} ({mode}-mode)",
            f"In {mode}-mode, read each tag table base CSR, write it with csrrw and read it again.\n"
            "Illegal or virtual instruction for the CSRs that the mode may not access. After the write,\n"
            "read the CSR with a T-SBI call: the base written before, unless the write reached the CSR",
        )
    ]
    for i, (_, csr, gate) in enumerate(csrs):
        lines += gated([f"LI(x{reg}, {0xC000_0000 + (i + 1) * 0x1000:#x})", tsbi_call(f"csrw {csr}, x{reg}")], gate)
    for i, (name, csr, gate) in enumerate(csrs):
        lines += [
            f"LI(x{reg}, 42)    # known value; a trapping access leaves it unchanged",
            test_data.add_testcase(f"{mode}_{name}_read", coverpoint, cg),
            f"csrr x{reg}, {csr}",
            write_sigupd(reg, test_data),
            f"LI(x{reg}, {0x8000_0000 + (i + 1) * 0x1000:#x})",
            test_data.add_testcase(f"{mode}_{name}_write", coverpoint, cg),
            f"csrrw x{reg}, {csr}, x{reg}    # x{reg} = the old value",
            write_sigupd(reg, test_data),
            *gated([tsbi_call(f"csrr x{reg}, {csr}"), write_sigupd(reg, test_data)], gate),
            f"LI(x{reg}, 42)",
            test_data.add_testcase(f"{mode}_{name}_reread", coverpoint, cg),
            f"csrr x{reg}, {csr}",
            write_sigupd(reg, test_data),
        ]
    test_data.int_regs.return_register(reg)
    return lines
