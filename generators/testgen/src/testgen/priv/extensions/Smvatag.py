##################################
# priv/extensions/Smvatag.py
#
# Smvatag (M-mode tag table base CSR) test generators for the Sm, S and H groups.
# SPDX-License-Identifier: Apache-2.0
##################################

"""Smvatag test generators.

Smvatag defines mvitt, the virtually indexed tag table (VITT) base CSR of M-mode.

- Sm: the WARL behavior of mvitt.
- S: the access to mvitt from S-mode, which raises an illegal-instruction exception.
- U: the access to mvitt from U-mode, which raises an illegal-instruction exception, also without S-mode.
- H: the access to mvitt from VS-mode and VU-mode, which raises an illegal-instruction exception.
"""

from testgen.data.state import TestData
from testgen.data.test_chunk import TestChunk
from testgen.priv.extensions.VatagCommon import M_VITT, vitt_access_tests, vitt_warl_tests
from testgen.priv.registry import add_priv_test_generator


@add_priv_test_generator(
    "Smvatag",
    required_extensions=["Smvatag", "Zimt", "Sm"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_MMODE"],
)
def make_smvatag_sm(test_data: TestData) -> list[TestChunk]:
    """Generate the Smvatag tests in M-mode."""
    tc = test_data.begin_test_chunk("Sm")
    tc.code += vitt_warl_tests(test_data, "Smvatag_Sm_cg", "M", M_VITT)
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Smvatag",
    required_extensions=["Smvatag", "Zimt", "S"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_smvatag_s(test_data: TestData) -> list[TestChunk]:
    """Generate the Smvatag access tests in S-mode."""
    tc = test_data.begin_test_chunk("S")
    tc.code += vitt_access_tests(test_data, "Smvatag_S_cg", "S", M_VITT)
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Smvatag",
    required_extensions=["Smvatag", "Zimt", "U"],
    params=["MXLEN: 64"],
)
def make_smvatag_u(test_data: TestData) -> list[TestChunk]:
    """Generate the Smvatag access tests in U-mode."""
    tc = test_data.begin_test_chunk("U")
    tc.code += vitt_access_tests(test_data, "Smvatag_U_cg", "U", M_VITT)
    return [test_data.end_test_chunk()]


@add_priv_test_generator(
    "Smvatag",
    required_extensions=["Smvatag", "Zimt", "H"],
    params=["MXLEN: 64"],
    extra_defines=["#define BOOT_TO_SMODE"],
)
def make_smvatag_h(test_data: TestData) -> list[TestChunk]:
    """Generate the Smvatag access tests in VS-mode and VU-mode."""
    cg = "Smvatag_H_cg"
    tc = test_data.begin_test_chunk("H")
    for mode in ("VS", "VU"):
        tc.code += [
            f"RVTEST_TSBI_GOTO_{mode}MODE",
            *vitt_access_tests(test_data, cg, mode, M_VITT),
            "RVTEST_TSBI_GOTO_SMODE",
        ]
    return [test_data.end_test_chunk()]
