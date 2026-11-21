///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Covergroups Initialization File
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////
`ifndef EXCLUDE_SM
    Smvatag_Sm_cg = new();  Smvatag_Sm_cg.set_inst_name("obj_Smvatag_Sm");
`endif
`ifdef S_SUPPORTED
    Smvatag_S_cg = new();   Smvatag_S_cg.set_inst_name("obj_Smvatag_S");
`endif
`ifdef U_SUPPORTED
    Smvatag_U_cg = new();   Smvatag_U_cg.set_inst_name("obj_Smvatag_U");
`endif
`ifdef H_SUPPORTED
    Smvatag_H_cg = new();   Smvatag_H_cg.set_inst_name("obj_Smvatag_H");
`endif
