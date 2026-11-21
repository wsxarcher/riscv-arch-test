##################################
# priv/extensions/Svatag.py
#
# Svatag (tag table base CSRs of S-mode, U-mode, VS-mode and VU-mode) test generators for the S and H groups.
# SPDX-License-Identifier: Apache-2.0
##################################

"""Svatag test generators.

Svatag defines the virtually indexed tag table (VITT) base CSRs svitts (S/HS-mode), svittu (U-mode), vsvitts
(VS-mode) and vsvittu (VU-mode). When V=1, svitts and svittu access vsvitts and vsvittu. Both groups boot to S-mode
(HS-mode with H):

- S: the WARL behavior of svitts and svittu, and the access to the four CSRs from U-mode.
- H: the WARL behavior of vsvitts and vsvittu, the VS-mode access to svitts and svittu, which reaches vsvitts and
  vsvittu, and the access to the four CSRs from VS-mode and VU-mode.
"""

from testgen.asm.helpers import comment_banner, write_sigupd
from testgen.asm.tsbi import tsbi_call
from testgen.data.state import TestData
from testgen.data.test_chunk import TestChunk
from testgen.priv.extensions.VatagCommon import S_VITT, VS_VITT, vitt_access_tests, vitt_warl_tests
from testgen.priv.registry import add_priv_test_generator


def _vs_redirect_tests(test_data: TestData, cg: str) -> list[str]:
    """In VS-mode, write and then read svitts and svittu, which reach vsvitts and vsvittu.

    HS-mode first writes a different base to each of the four CSRs. After each VS-mode write, T-SBI calls read the CSR
    and its VS-level copy from HS-mode: the S-level CSR keeps its base, and the VS-level one holds the base written.
    """
    coverpoint = "cp_vitt_vs_redirect"
    reg = test_data.int_regs.get_register()
    hs_bases = (0x8000_1000, 0x8000_2000, 0x8000_3000, 0x8000_4000)
    vs_bases = (0x8000_5000, 0x8000_6000)
    lines = [comment_banner(coverpoint, "In VS-mode, svitts and svittu access vsvitts and vsvittu")]
    for (_, csr, _), base in zip([*S_VITT, *VS_VITT], hs_bases, strict=True):
        lines += [f"LI(x{reg}, {base:#x})", f"csrw {csr}, x{reg}"]
    lines.append("RVTEST_TSBI_GOTO_VSMODE")
    for (name, csr, _), (_, vs_csr, _), base in zip(S_VITT, VS_VITT, vs_bases, strict=True):
        lines += [
            f"LI(x{reg}, {base:#x})",
            test_data.add_testcase(f"VS_{name}_write", coverpoint, cg),
            f"csrrw x{reg}, {csr}, x{reg}    # writes vs{name}; x{reg} = its old value",
            write_sigupd(reg, test_data),
            tsbi_call(f"csrr x{reg}, {csr}    # {name}, read from HS-mode: its base"),
            write_sigupd(reg, test_data),
            tsbi_call(f"csrr x{reg}, {vs_csr}    # vs{name}: the base written"),
            write_sigupd(reg, test_data),
            f"LI(x{reg}, 42)",
            test_data.add_testcase(f"VS_{name}_read", coverpoint, cg),
            f"csrr x{reg}, {csr}    # reads vs{name}",
            write_sigupd(reg, test_data),
        ]
    lines.append("RVTEST_TSBI_GOTO_SMODE")
    lines += [f"csrw {csr}, zero" for _, csr, _ in [*S_VITT, *VS_VITT]]
    test_data.int_regs.return_register(reg)
    return lines


@add_priv_test_generator(
    "Svatag",
    required_extensions=["Svatag", "Zimt", "S"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_svatag_s(test_data: TestData) -> list[TestChunk]:
    """Generate the Svatag tests in S-mode and U-mode."""
    cg = "Svatag_S_cg"
    tc = test_data.begin_test_chunk("S")
    tc.code += [
        *vitt_warl_tests(test_data, cg, "S", S_VITT),
        "RVTEST_TSBI_GOTO_UMODE",
        *vitt_access_tests(test_data, cg, "U", [*S_VITT, *VS_VITT]),
        "RVTEST_TSBI_GOTO_SMODE",
    ]
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Svatag",
    required_extensions=["Svatag", "Zimt", "H"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_svatag_h(test_data: TestData) -> list[TestChunk]:
    """Generate the Svatag tests in HS-mode, VS-mode and VU-mode."""
    cg = "Svatag_H_cg"
    tc = test_data.begin_test_chunk("H")
    tc.code += [
        *vitt_warl_tests(test_data, cg, "HS", VS_VITT),
        *_vs_redirect_tests(test_data, cg),
    ]
    for mode in ("VS", "VU"):
        tc.code += [
            f"RVTEST_TSBI_GOTO_{mode}MODE",
            *vitt_access_tests(test_data, cg, mode, [*S_VITT, *VS_VITT]),
            "RVTEST_TSBI_GOTO_SMODE",
        ]
    return [test_data.end_test_chunk()]
