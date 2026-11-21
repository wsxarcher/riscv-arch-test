///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Covergroups
//
// Svatag tag table base CSRs svitts, svittu, vsvitts and vsvittu: their WARL behavior, the VS-mode access to
// svitts and svittu, which reaches vsvitts and vsvittu, and the access from U, VS and VU modes.
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////

`define COVER_SVATAG

`ifdef S_SUPPORTED
covergroup Svatag_S_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Vatag_coverpoints.svh"

    s_vitt_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins svitts = {12'h5C2};
        bins svittu = {12'h5C3};
    }
    vitt_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins svitts  = {12'h5C2};
        bins svittu  = {12'h5C3};
        bins vsvitts = {12'h6C2};
        bins vsvittu = {12'h6C3};
    }

    cp_vitt_warl:   cross priv_mode_s, csrrw, s_vitt_csr, vitt_written;
    cp_vitt_access: cross priv_mode_u, csr_access_op, vitt_csr;

endgroup
`endif

`ifdef H_SUPPORTED
covergroup Svatag_H_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Vatag_coverpoints.svh"

    s_vitt_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins svitts = {12'h5C2};
        bins svittu = {12'h5C3};
    }
    vs_vitt_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins vsvitts = {12'h6C2};
        bins vsvittu = {12'h6C3};
    }
    vitt_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins svitts  = {12'h5C2};
        bins svittu  = {12'h5C3};
        bins vsvitts = {12'h6C2};
        bins vsvittu = {12'h6C3};
    }
    // svitts or svittu and its VS-level copy, vsvitts or vsvittu (0x100 above), hold different bases, so the result
    // of a VS-mode access shows which one it reached
    vitt_copies_differ: coverpoint (get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, ins.current.insn[31:20]) !=
                                    get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, ins.current.insn[31:20] + 12'h100)) {
        type_option.weight = 0;
        bins differ = {1'b1};
    }

    cp_vitt_warl:        cross priv_mode_hs, csrrw, vs_vitt_csr, vitt_written;
    cp_vitt_vs_redirect: cross priv_mode_vs, csr_access_op, s_vitt_csr, vitt_copies_differ;
    cp_vitt_access:      cross priv_mode_vs_vu, csr_access_op, vitt_csr;

endgroup
`endif

function void svatag_sample(int hart, int issue, ins_t ins);
    `ifdef S_SUPPORTED
        Svatag_S_cg.sample(ins);
    `endif
    `ifdef H_SUPPORTED
        Svatag_H_cg.sample(ins);
    `endif
endfunction
