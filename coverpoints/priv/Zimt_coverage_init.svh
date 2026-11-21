///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Covergroups Initialization File
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////
`ifndef EXCLUDE_SM
    Zimt_Sm_cg = new();     Zimt_Sm_cg.set_inst_name("obj_Zimt_Sm");
`endif
`ifdef S_SUPPORTED
    Zimt_S_cg = new();      Zimt_S_cg.set_inst_name("obj_Zimt_S");
`endif
`ifdef U_SUPPORTED
    Zimt_U_cg = new();      Zimt_U_cg.set_inst_name("obj_Zimt_U");
`endif
`ifdef H_SUPPORTED
    Zimt_H_cg = new();      Zimt_H_cg.set_inst_name("obj_Zimt_H");
`endif
