///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Zimt Shared Coverpoints
//
// Building blocks shared by the Zimt covergroups (M, S, U, VS/VU).
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////

    // xMT_MODE of the mode the instruction executes in
    mt_disabled: coverpoint zimt_mt_mode(ins) {
        type_option.weight = 0;
        bins disabled = {2'b00};
    }

    // gentag rd: MOP.RR.1 with bit 24 = 0, imm4 = 0, rs1 = x0 and rd != x0
    gentag_rd: coverpoint ins.current.insn[11:7]
        iff (ins.current.insn ==? MOP_RR_1 && ins.current.insn[24:15] == 0) {
        type_option.weight = 0;
        bins rd[] = {[1:31]};
    }

    // addtag rd, rs1, imm4: MOP.RR.1 with bit 24 = 0, imm4 != 0 and rd != x0
    addtag_imm: coverpoint ins.current.insn[23:20]
        iff (ins.current.insn ==? MOP_RR_1 && !ins.current.insn[24] && ins.current.insn[11:7] != 0) {
        type_option.weight = 0;
        bins imm4[] = {[1:15]};
    }
    addtag_rd: coverpoint ins.current.insn[11:7]
        iff (ins.current.insn ==? MOP_RR_1 && !ins.current.insn[24] && ins.current.insn[23:20] != 0) {
        type_option.weight = 0;
        bins rd[] = {[1:31]};
    }
    addtag_rs1: coverpoint ins.current.insn[19:15]
        iff (ins.current.insn ==? MOP_RR_1 && !ins.current.insn[24] && ins.current.insn[23:20] != 0 &&
             ins.current.insn[11:7] != 0) {
        type_option.weight = 0;
        bins rs1[] = {[0:31]};
    }
    addtag_rd_rs1: coverpoint ins.current.insn[11:7] == ins.current.insn[19:15]
        iff (ins.current.insn ==? MOP_RR_1 && !ins.current.insn[24] && ins.current.insn[23:20] != 0 &&
             ins.current.insn[11:7] != 0) {
        type_option.weight = 0;
        bins rd_eq_rs1 = {1'b1};
    }

    // checktag rs1, imm4: MOP.RR.1 with bit 24 = 0, rd = x0 and rs1 != x0
    checktag_imm: coverpoint ins.current.insn[23:20]
        iff (ins.current.insn ==? MOP_RR_1 && !ins.current.insn[24] && ins.current.insn[11:7] == 0 &&
             ins.current.insn[19:15] != 0) {
        type_option.weight = 0;
        bins imm4[] = {[0:15]};
    }
    checktag_rs1: coverpoint ins.current.insn[19:15]
        iff (ins.current.insn ==? MOP_RR_1 && !ins.current.insn[24] && ins.current.insn[11:7] == 0) {
        type_option.weight = 0;
        bins rs1[] = {[1:31]};
    }

    // settag rs1, imm4: MOP.RR.0 with bit 24 = 0, rd = x0 and rs1 != x0
    settag_imm: coverpoint ins.current.insn[23:20]
        iff (ins.current.insn ==? MOP_RR_0 && !ins.current.insn[24] && ins.current.insn[11:7] == 0 &&
             ins.current.insn[19:15] != 0) {
        type_option.weight = 0;
        bins imm4[] = {[0:15]};
    }
    settag_rs1: coverpoint ins.current.insn[19:15]
        iff (ins.current.insn ==? MOP_RR_0 && !ins.current.insn[24] && ins.current.insn[11:7] == 0) {
        type_option.weight = 0;
        bins rs1[] = {[1:31]};
    }

    // settag with memory tagging enabled. First chunk: bits 7:4 of rs1, which with 4-bit tags put its tag in either
    // half of each byte of a doubleword, and bits 6:4, which with 7-bit tags put it in each byte
    settag_chunk4: coverpoint ins.current.rs1_val[7:4] iff (zimt_is_settag(ins)) {
        type_option.weight = 0;
        bins chunk[] = {[0:15]};
    }
    settag_chunk7: coverpoint ins.current.rs1_val[6:4] iff (zimt_is_settag(ins)) {
        type_option.weight = 0;
        bins chunk[] = {[0:7]};
    }
    // settag with any registers, and its exception: none, store/AMO access fault or store/AMO page fault
    settag: coverpoint zimt_is_settag(ins) {
        type_option.weight = 0;
        bins settag = {1'b1};
    }
    settag_exception: coverpoint zimt_exception(ins) iff (zimt_is_settag(ins)) {
        type_option.weight = 0;
        bins none               = {8'h00};
`ifdef ZIMT_SETTAG_S_ACCESS_FAULT
        bins store_access_fault = {8'h47};
`endif
        bins store_page_fault   = {8'h4F};
    }
    // settag without address translation: no exception or a store/AMO access fault
    settag_bare_exception: coverpoint zimt_exception(ins) iff (zimt_is_settag(ins)) {
        type_option.weight = 0;
        bins none               = {8'h00};
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_STORE
        bins store_access_fault = {8'h47};
`endif
    }
    // settag with guest translation and its exception: two-stage (VS stage: store/AMO page fault, G stage: store/AMO
    // guest-page fault), or the G stage only
    settag_two_stage_exception: coverpoint zimt_exception(ins)
        iff (zimt_is_settag(ins) && zimt_atp_mode(ins, CSR_VSATP) != 0 && zimt_atp_mode(ins, CSR_HGATP) != 0) {
        type_option.weight = 0;
        bins none                   = {8'h00};
        bins store_page_fault       = {8'h4F};
        bins store_guest_page_fault = {8'h57};
    }
    settag_g_stage_exception: coverpoint zimt_exception(ins)
        iff (zimt_is_settag(ins) && zimt_atp_mode(ins, CSR_VSATP) == 0 && zimt_atp_mode(ins, CSR_HGATP) != 0) {
        type_option.weight = 0;
        bins none                   = {8'h00};
        bins store_guest_page_fault = {8'h57};
    }
    // settag through a pointer with bit 56 and bit 47 set: bit 63 - PMLEN of its address for PMLEN 7 and 16, which
    // pointer masking sign-extends with address translation and zero-extends without
    settag_addr_msb: coverpoint (ins.current.rs1_val[56] && ins.current.rs1_val[47]) iff (zimt_is_settag(ins)) {
        type_option.weight = 0;
        bins set = {1'b1};
    }
    // settag in M-mode with mstatus.MPRV = 1 and MPP = S
    settag_mprv_s: coverpoint zimt_mprv_mpp(ins) iff (zimt_is_settag(ins)) {
        type_option.weight = 0;
        bins mprv_s = {4'b1001};
    }
    // checktag with memory tagging enabled. First chunk: as for settag
    checktag_chunk4: coverpoint ins.current.rs1_val[7:4] iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins chunk[] = {[0:15]};
    }
    checktag_chunk7: coverpoint ins.current.rs1_val[6:4] iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins chunk[] = {[0:7]};
    }
    // checktag and its exception: none, a software-check exception (tag mismatch), a load access fault or a load page
    // fault
    checktag_exception: coverpoint zimt_exception(ins) iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins none              = {8'h00};
        bins software_check    = {8'h52};
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
        bins load_access_fault = {8'h45};
`endif
        bins load_page_fault   = {8'h4D};
    }
    // checktag without address translation: no exception, a software-check exception or a load access fault
    checktag_bare_exception: coverpoint zimt_exception(ins) iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins none              = {8'h00};
        bins software_check    = {8'h52};
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
        bins load_access_fault = {8'h45};
`endif
    }
    // checktag with guest translation and its exception: two-stage (VS stage: load page fault, G stage: load guest-page
    // fault), or the G stage only
    checktag_two_stage_exception: coverpoint zimt_exception(ins)
        iff (zimt_is_checktag(ins) && zimt_atp_mode(ins, CSR_VSATP) != 0 && zimt_atp_mode(ins, CSR_HGATP) != 0) {
        type_option.weight = 0;
        bins none                  = {8'h00};
        bins software_check        = {8'h52};
        bins load_page_fault       = {8'h4D};
        bins load_guest_page_fault = {8'h55};
    }
    checktag_g_stage_exception: coverpoint zimt_exception(ins)
        iff (zimt_is_checktag(ins) && zimt_atp_mode(ins, CSR_VSATP) == 0 && zimt_atp_mode(ins, CSR_HGATP) != 0) {
        type_option.weight = 0;
        bins none                  = {8'h00};
        bins load_guest_page_fault = {8'h55};
    }
    // checktag through a pointer with bits 56 and 47 set (see settag_addr_msb)
    checktag_addr_msb: coverpoint (ins.current.rs1_val[56] && ins.current.rs1_val[47]) iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins set = {1'b1};
    }
    // checktag in M-mode with mstatus.MPRV = 1 and MPP = S
    checktag_mprv_s: coverpoint zimt_mprv_mpp(ins) iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins mprv_s = {4'b1001};
    }
    // checktag with sp as rs1, which the exemption of the loads and stores with sp as the base register does not
    // cover, and the outcome of checktag: none, or a software-check exception
    checktag_sp: coverpoint (ins.current.insn[19:15] == 5'd2) iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins sp = {1'b1};
    }
    checktag_result: coverpoint zimt_exception(ins) iff (zimt_is_checktag(ins)) {
        type_option.weight = 0;
        bins none           = {8'h00};
        bins software_check = {8'h52};
    }

    // The loads and stores that implicit tag checks cover (zimt_checked_access), by kind: the floating-point and
    // compressed ones with their extensions
    checked_access: coverpoint zimt_checked_access(ins) {
        type_option.weight = 0;
        bins lb  = {5'd0};
        bins lh  = {5'd1};
        bins lw  = {5'd2};
        bins ld  = {5'd3};
        bins lbu = {5'd4};
        bins lhu = {5'd5};
        bins lwu = {5'd6};
        bins sb  = {5'd8};
        bins sh  = {5'd9};
        bins sw  = {5'd10};
        bins sd  = {5'd11};
`ifdef ZFHMIN_SUPPORTED
        bins flh = {5'd12};
        bins fsh = {5'd16};
`endif
`ifdef F_SUPPORTED
        bins flw = {5'd13};
        bins fsw = {5'd17};
`endif
`ifdef D_SUPPORTED
        bins fld = {5'd14};
        bins fsd = {5'd18};
`endif
`ifdef ZCA_SUPPORTED
        bins c_lw = {5'd20};
        bins c_ld = {5'd21};
        bins c_sw = {5'd22};
        bins c_sd = {5'd23};
`endif
`ifdef ZCB_SUPPORTED
        bins c_lbu = {5'd26};
        bins c_lh  = {5'd27};
        bins c_lhu = {5'd28};
        bins c_sb  = {5'd29};
        bins c_sh  = {5'd30};
`endif
`ifdef ZCD_SUPPORTED
        bins c_fld = {5'd24};
        bins c_fsd = {5'd25};
`endif
    }
    // Their integer kinds (VS-mode and VU-mode tests)
    checked_int_access: coverpoint zimt_checked_access(ins) {
        type_option.weight = 0;
        bins lb  = {5'd0};
        bins lh  = {5'd1};
        bins lw  = {5'd2};
        bins ld  = {5'd3};
        bins lbu = {5'd4};
        bins lhu = {5'd5};
        bins lwu = {5'd6};
        bins sb  = {5'd8};
        bins sh  = {5'd9};
        bins sw  = {5'd10};
        bins sd  = {5'd11};
`ifdef ZCA_SUPPORTED
        bins c_lw = {5'd20};
        bins c_ld = {5'd21};
        bins c_sw = {5'd22};
        bins c_sd = {5'd23};
`endif
`ifdef ZCB_SUPPORTED
        bins c_lbu = {5'd26};
        bins c_lh  = {5'd27};
        bins c_lhu = {5'd28};
        bins c_sb  = {5'd29};
        bins c_sh  = {5'd30};
`endif
    }
    checked_load_store: coverpoint zimt_checked_store(zimt_checked_access(ins)) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
        bins load  = {1'b0};
        bins store = {1'b1};
    }
    // Their outcome: none (the tags match, or no tag check), or a software-check exception
    checked_result: coverpoint zimt_exception(ins) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
        bins none           = {8'h00};
        bins software_check = {8'h52};
    }
    // A misaligned load or store over two chunks
    checked_two_chunks: coverpoint zimt_two_chunks(ins) {
        type_option.weight = 0;
        bins two_chunks = {1'b1};
    }
    // The outcome of one: the tags match, and the hart performs it or, without hardware misaligned loads and stores,
    // raises its address-misaligned or access-fault exception; or a software-check exception
    checked_two_chunk_result: coverpoint zimt_exception(ins) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
`ifdef UDB_MISALIGNED_LDST
        bins tags_match     = {8'h00};
`else
        bins tags_match     = {8'h44, 8'h45, 8'h46, 8'h47};
`endif
        bins software_check = {8'h52};
    }
    // A load or store with sp as the base register, which no tag check covers, and a pointer tag in sp: no exception
    checked_sp_base: coverpoint ((ins.current.insn[19:15] == 5'd2) && (ins.current.rs1_val[63:57] != 7'd0))
        iff ((zimt_checked_access(ins) < 5'd20) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins sp = {1'b1};
    }
    // A compressed load or store with sp as the base register (zimt_sp_compressed) and a pointer tag in sp: no tag
    // check, no exception. All kinds, and the integer ones (VS-mode and VU-mode tests)
    checked_sp_compressed: coverpoint zimt_sp_compressed(ins)
        iff ((ins.prev.x_wdata[2][63:57] != 7'd0) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins c_lwsp = {3'd1};
        bins c_ldsp = {3'd2};
        bins c_swsp = {3'd3};
        bins c_sdsp = {3'd4};
`ifdef ZCD_SUPPORTED
        bins c_fldsp = {3'd5};
        bins c_fsdsp = {3'd6};
`endif
    }
    checked_sp_int_compressed: coverpoint zimt_sp_compressed(ins)
        iff ((ins.prev.x_wdata[2][63:57] != 7'd0) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins c_lwsp = {3'd1};
        bins c_ldsp = {3'd2};
        bins c_swsp = {3'd3};
        bins c_sdsp = {3'd4};
    }
    // The accesses that implicit tag checks do not cover (zimt_unchecked_access), whose pointer tags do not match: no
    // exception. LR/SC and AMOs, and in M-mode also CMOs, HLV/HSV and vector loads and stores
    unchecked_access: coverpoint zimt_unchecked_access(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
`ifdef ZALRSC_SUPPORTED
        bins lr  = {4'd1};
        bins sc  = {4'd2};
`endif
`ifdef ZAAMO_SUPPORTED
        bins amo = {4'd3};
`endif
    }
    unchecked_access_m: coverpoint zimt_unchecked_access(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
`ifdef ZALRSC_SUPPORTED
        bins lr  = {4'd1};
        bins sc  = {4'd2};
`endif
`ifdef ZAAMO_SUPPORTED
        bins amo = {4'd3};
`endif
`ifdef ZICBOM_SUPPORTED
        bins cbo_clean = {4'd4};
        bins cbo_flush = {4'd5};
`endif
`ifdef ZICBOZ_SUPPORTED
        bins cbo_zero  = {4'd6};
`endif
`ifdef H_SUPPORTED
        bins hlv = {4'd7};
        bins hsv = {4'd8};
`endif
`ifdef V_SUPPORTED
        bins vse        = {4'd9};
        bins vse_masked = {4'd10};
        bins vsse       = {4'd11};
        bins vsuxei     = {4'd12};
        bins vle        = {4'd13};
        bins vlse       = {4'd14};
        bins vluxei     = {4'd15};
`endif
    }
    // The instruction right before it: a byte store through sp (to a tag byte) or settag
    checked_order: coverpoint zimt_order_prev(ins) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
        bins after_tag_store = {2'd1};
        bins after_settag    = {2'd2};
    }
    // Their access faults (zimt_checked_fault): of the data, or of the tag load of a store
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
    checked_fault: coverpoint zimt_checked_fault(ins) {
        type_option.weight = 0;
        bins load_access_fault     = {2'd1};
        bins tag_load_access_fault = {2'd2};
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_STORE
        bins store_access_fault    = {2'd3};
`endif
    }
    // The load access faults of tag loads, of a load and of a store
    checked_tag_fault: coverpoint zimt_checked_fault(ins) {
        type_option.weight = 0;
        bins load_access_fault     = {2'd1};
        bins tag_load_access_fault = {2'd2};
    }
`endif
    // In M-mode with mstatus.MPRV = 1 and MPP = S
    checked_mprv_s: coverpoint zimt_mprv_mpp(ins) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
        bins mprv_s = {4'b1001};
    }
    // In M-mode with mstatus.MPRV = 1 and MPV = 1: MPP = S (VS-mode) or U (VU-mode)
    checked_mprv_v: coverpoint zimt_mprv_mpp(ins) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
        bins mprv_vs = {4'b1101};
        bins mprv_vu = {4'b1100};
    }
    // mseccfg.PMM = 00: M-mode does not mask pointers
    m_pmm_off: coverpoint (2'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, CSR_MSECCFG) >> 32) == 2'b00) {
        type_option.weight = 0;
        bins off = {1'b1};
    }
    // With it, memory tagging in S-mode only (menvcfg, while mseccfg disables it) or in M-mode only, by tag width
    mprv_s_mt: coverpoint zimt_mprv_mt(ins) {
        type_option.weight = 0;
        bins tag4 = {4'b10_00};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {4'b11_00};
`endif
    }
    mprv_m_mt: coverpoint zimt_mprv_mt(ins) {
        type_option.weight = 0;
        bins tag4 = {4'b00_10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {4'b00_11};
`endif
    }
    mprv_mt: coverpoint zimt_mprv_mt(ins) {
        type_option.weight = 0;
        bins s_tag4 = {4'b10_00};
        bins m_tag4 = {4'b00_10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins s_tag7 = {4'b11_00};
        bins m_tag7 = {4'b00_11};
`endif
    }
    // Without address translation in S-mode (satp Bare)
    checked_satp_bare: coverpoint (zimt_atp_mode(ins, CSR_SATP) == 4'd0) iff (zimt_checked_access(ins) != 5'd31) {
        type_option.weight = 0;
        bins bare = {1'b1};
    }
    // A software-check exception of checktag or of a load or store that VS-mode takes (hedeleg[18] = 1)
    swcheck_to_vs: coverpoint {zimt_is_checktag(ins), (zimt_checked_access(ins) != 5'd31)}
        iff ((zimt_exception(ins) == 8'h52) && ins.current.csr_wb[CSR_VSCAUSE]) {
        type_option.weight = 0;
        bins checktag = {2'b10};
        bins access   = {2'b01};
    }
    // With address translation, satp (S-mode) or vsatp (VS-mode) not Bare, and a pointer tag: no tag check, no
    // exception
    checked_satp_translated: coverpoint (zimt_atp_mode(ins, CSR_SATP) != 4'd0)
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0) &&
             (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins translated = {1'b1};
    }
    checked_vsatp_translated: coverpoint (zimt_atp_mode(ins, CSR_VSATP) != 4'd0)
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0) &&
             (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins translated = {1'b1};
    }
    // With the G stage only (vsatp Bare, hgatp not Bare), which does not prevent tag checks: the outcome, none (the
    // tags match), a software-check exception, or a load guest-page fault of a tag load (also for a store)
    checked_g_stage_result: coverpoint zimt_exception(ins)
        iff ((zimt_checked_access(ins) != 5'd31) && (zimt_atp_mode(ins, CSR_VSATP) == 4'd0) &&
             (zimt_atp_mode(ins, CSR_HGATP) != 4'd0)) {
        type_option.weight = 0;
        bins none                  = {8'h00};
        bins software_check        = {8'h52};
        bins load_guest_page_fault = {8'h55};
    }

    // MOP.RR.1 and MOP.RR.0 encodings that miss one condition of a Zimt instruction
    mop_rr_not_zimt: coverpoint zimt_mop_rr_not_zimt(ins) {
        type_option.weight = 0;
        bins rr1_bit24_imm[] = {[0:15]};
        bins rr1_imm0        = {16};
        bins rr1_rd0_bit24   = {17};
        bins rr1_rd0_rs1_0   = {18};
        bins rr0_rd          = {19};
        bins rr0_rd0_bit24   = {20};
        bins rr0_rd0_rs1_0   = {21};
    }

    // Memory tagging enabled in the mode the instruction executes in, by pointer tag width (7-bit tags are optional)
    mt_enabled: coverpoint zimt_mt_mode(ins) {
        type_option.weight = 0;
        bins tag4 = {2'b10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {2'b11};
`endif
    }
    mt_tag4: coverpoint zimt_mt_mode(ins) {
        type_option.weight = 0;
        bins tag4 = {2'b10};
    }
    mt_tag7: coverpoint zimt_mt_mode(ins) {
        type_option.weight = 0;
        bins tag7 = {2'b11};
    }

    // gentag and addtag, with any registers
    gentag: coverpoint zimt_is_gentag(ins) {
        type_option.weight = 0;
        bins gentag = {1'b1};
    }
    // addtag: whether the pointer tag wraps (tag + imm4 >= 2^pointer_tag_width)
    addtag_wrap: coverpoint zimt_addtag_wraps(ins) iff (zimt_is_addtag(ins)) {
        type_option.weight = 0;
        bins no_wrap = {1'b0};
        bins wrap    = {1'b1};
    }

    // gentag result: the pointer tag, with 4-bit and 7-bit tags
    gentag_tag4: coverpoint zimt_pointer_tag(ins.current.rd_val, 4) iff (zimt_is_gentag(ins)) {
        type_option.weight = 0;
        bins tag[] = {[0:15]};
    }
    gentag_tag7_low: coverpoint zimt_pointer_tag(ins.current.rd_val, 7) iff (zimt_is_gentag(ins)) {
        type_option.weight = 0;
        bins tag[] = {[0:15]};
    }
    // The first and last 7-bit tag of each group of 16 tags above 15
    gentag_tag7_high: coverpoint zimt_pointer_tag(ins.current.rd_val, 7) iff (zimt_is_gentag(ins)) {
        type_option.weight = 0;
        bins tag[] = {16, 31, 32, 47, 48, 63, 64, 79, 80, 95, 96, 111, 112, 127};
    }
    // gentag: the active exclusion mask permits several tags, more than the 0 and the one other tag that the
    // high-tag tests permit
    gentag_several: coverpoint zimt_permitted_tags(ins) iff (zimt_is_gentag(ins)) {
        type_option.weight = 0;
        bins several = {[3:128]};
    }

    // CSR instructions: csrr (csrrs with rs1 = x0) and csrrw, as the CSR access tests use them
    csr_access_op: coverpoint ins.current.insn {
        type_option.weight = 0;
        wildcard bins read  = {32'b????????????_00000_010_?????_1110011};
        wildcard bins write = {CSRRW};
    }
    csrr: coverpoint ins.current.insn {
        type_option.weight = 0;
        wildcard bins csrr = {32'b????????????_00000_010_?????_1110011};
    }
    csrrw: coverpoint ins.current.insn {
        type_option.weight = 0;
        wildcard bins csrrw = {CSRRW};
    }
    csrs_csrc: coverpoint ins.current.insn {
        type_option.weight = 0;
        wildcard bins csrrs = {CSRRS};
        wildcard bins csrrc = {CSRRC};
    }

    // Tag generation exclusion mask CSRs: those of S/HS and U need S-mode, and those of VS need H
    mtagexclude_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mmtagexclude0    = {12'h7C0};
        bins mmtagexclude1    = {12'h7C1};
`ifdef S_SUPPORTED
        bins menvmtagexclude0 = {12'h7C2};
        bins menvmtagexclude1 = {12'h7C3};
        bins senvmtagexclude0 = {12'h5C0};
        bins senvmtagexclude1 = {12'h5C1};
`endif
`ifdef H_SUPPORTED
        bins henvmtagexclude0 = {12'h6C0};
        bins henvmtagexclude1 = {12'h6C1};
`endif
    }
    // Value written to a low exclusion mask CSR: whether it excludes all of the tags 0-15, which is illegal
    mtagexclude0_written: coverpoint (ins.current.rs1_val[15:0] == 16'hFFFF) {
        type_option.weight = 0;
        bins legal         = {1'b0};
        bins excludes_0_15 = {1'b1};
    }
    // Value written to a high exclusion mask CSR: zero or not
    mtagexclude1_written: coverpoint (ins.current.rs1_val != 0) {
        type_option.weight = 0;
        bins zero    = {1'b0};
        bins nonzero = {1'b1};
    }

    // MT_MODE (or hstatus.VUMT_MODE) write: the field before the write, and the value written
    // The field holds 11 only with 7-bit tags; 11 is written either way
    mt_mode_before: coverpoint zimt_mt_field(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, ins.current.insn[31:20]), ins) {
        type_option.weight = 0;
        bins disabled = {2'b00};
        bins tag4     = {2'b10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7     = {2'b11};
`endif
    }
    mt_mode_written: coverpoint zimt_mt_field(ins.current.rs1_val, ins) {
        type_option.weight = 0;
        bins disabled = {2'b00};
        bins reserved = {2'b01};
        bins tag4     = {2'b10};
        bins tag7     = {2'b11};
    }

    // Software-check exception (cause 18): its bit set in a delegation CSR write, and its code written to xcause
    swcheck_bit: coverpoint ins.current.rs1_val[18] {
        type_option.weight = 0;
        bins set = {1'b1};
    }
    swcheck_cause: coverpoint ins.current.rs1_val {
        type_option.weight = 0;
        bins software_check = {18};
    }
