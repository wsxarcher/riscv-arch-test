///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Covergroups
//
// Smvatag tag table base CSR mvitt: its WARL behavior, and the access from S, U, VS and VU modes.
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////

`define COVER_SMVATAG

// Sm tests are not part of a certificate without Sm (EXCLUDE_SM), so neither is their covergroup
`ifndef EXCLUDE_SM
covergroup Smvatag_Sm_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Vatag_coverpoints.svh"

    mvitt: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mvitt = {12'h7C4};
    }

    cp_vitt_warl: cross priv_mode_m, csrrw, mvitt, vitt_written;

endgroup
`endif

`ifdef S_SUPPORTED
covergroup Smvatag_S_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Vatag_coverpoints.svh"

    mvitt: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mvitt = {12'h7C4};
    }

    cp_vitt_access: cross priv_mode_s, csr_access_op, mvitt;

endgroup
`endif

`ifdef U_SUPPORTED
covergroup Smvatag_U_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Vatag_coverpoints.svh"

    mvitt: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mvitt = {12'h7C4};
    }

    cp_vitt_access: cross priv_mode_u, csr_access_op, mvitt;

endgroup
`endif

`ifdef H_SUPPORTED
covergroup Smvatag_H_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Vatag_coverpoints.svh"

    mvitt: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mvitt = {12'h7C4};
    }

    cp_vitt_access: cross priv_mode_vs_vu, csr_access_op, mvitt;

endgroup
`endif

function void smvatag_sample(int hart, int issue, ins_t ins);
    `ifndef EXCLUDE_SM
        Smvatag_Sm_cg.sample(ins);
    `endif
    `ifdef S_SUPPORTED
        Smvatag_S_cg.sample(ins);
    `endif
    `ifdef U_SUPPORTED
        Smvatag_U_cg.sample(ins);
    `endif
    `ifdef H_SUPPORTED
        Smvatag_H_cg.sample(ins);
    `endif
endfunction
