///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Covergroups Initialization File
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////
`ifdef S_SUPPORTED
    Svatag_S_cg = new();    Svatag_S_cg.set_inst_name("obj_Svatag_S");
`endif
`ifdef H_SUPPORTED
    Svatag_H_cg = new();    Svatag_H_cg.set_inst_name("obj_Svatag_H");
`endif
