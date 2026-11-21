///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Svatag/Smvatag Shared Coverpoints
//
// Building blocks shared by the Svatag and Smvatag covergroups: the tag table base CSRs and their accesses.
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////

    // CSR instructions: csrr (csrrs with rs1 = x0) and csrrw, as the tests use them
    csr_access_op: coverpoint ins.current.insn {
        type_option.weight = 0;
        wildcard bins read  = {32'b????????????_00000_010_?????_1110011};
        wildcard bins write = {CSRRW};
    }
    csrrw: coverpoint ins.current.insn {
        type_option.weight = 0;
        wildcard bins csrrw = {CSRRW};
    }

    // Base written to a tag table base CSR: whether it is 4 KiB aligned
    vitt_written: coverpoint (ins.current.rs1_val[11:0] == 12'h0) {
        type_option.weight = 0;
        bins unaligned = {1'b0};
        bins aligned   = {1'b1};
    }
