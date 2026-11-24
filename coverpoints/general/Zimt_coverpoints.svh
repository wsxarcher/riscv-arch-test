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
    // exception. Prefetches, and in M-mode also cbo.clean, cbo.flush and HLV/HSV (whose VU-mode memory tagging,
    // senvcfg.MT_MODE, is disabled there; M-mode's does not apply to them)
    unchecked_access: coverpoint zimt_unchecked_access(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
`ifdef ZICBOP_SUPPORTED
        bins prefetch_r = {3'd1};
        bins prefetch_w = {3'd2};
`endif
    }
    unchecked_access_m: coverpoint zimt_unchecked_access(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
`ifdef ZICBOP_SUPPORTED
        bins prefetch_r = {3'd1};
        bins prefetch_w = {3'd2};
`endif
`ifdef ZICBOM_SUPPORTED
        bins cbo_clean = {3'd3};
        bins cbo_flush = {3'd4};
`endif
`ifdef H_SUPPORTED
        bins hlv = {3'd5};
        bins hsv = {3'd6};
`endif
    }
    // The regular accesses that implicit tag checks cover besides loads and stores (zimt_regular_access): LR/SC, AMOs
    // and cbo.zero
    checked_regular: coverpoint zimt_regular_access(ins) {
        type_option.weight = 0;
`ifdef ZALRSC_SUPPORTED
        bins lr = {4'd1};
        bins sc = {4'd2};
`endif
`ifdef ZAAMO_SUPPORTED
        bins amoadd_d  = {4'd3};
        bins amoswap_w = {4'd4};
`endif
`ifdef ZICBOZ_SUPPORTED
        bins cbo_zero = {4'd5};
`endif
    }
    // ...in M-mode, with memory tagging enabled there and the matching pointer tag: also cbo.zero, and vector loads and
    // stores (unit-stride, masked, strided, indexed and fault-only-first); no exception
    checked_regular_m: coverpoint zimt_regular_access(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
`ifdef ZALRSC_SUPPORTED
        bins lr = {4'd1};
        bins sc = {4'd2};
`endif
`ifdef ZAAMO_SUPPORTED
        bins amoadd_d  = {4'd3};
        bins amoswap_w = {4'd4};
`endif
`ifdef ZICBOZ_SUPPORTED
        bins cbo_zero = {4'd5};
`endif
`ifdef V_SUPPORTED
        bins vle        = {4'd6};
        bins vle_masked = {4'd7};
        bins vlse       = {4'd8};
        bins vluxei     = {4'd9};
        bins vleff      = {4'd10};
        bins vse        = {4'd11};
        bins vse_masked = {4'd12};
        bins vsse       = {4'd13};
        bins vsuxei     = {4'd14};
`endif
    }
    // ...in M-mode with mstatus.MPRV = 1 and MPP = S: LR/SC, AMOs, cbo.zero, and vector loads and stores (unit-stride,
    // masked, strided, indexed and fault-only-first)
    checked_regular_mprv: coverpoint zimt_regular_access(ins) {
        type_option.weight = 0;
`ifdef ZALRSC_SUPPORTED
        bins lr = {4'd1};
        bins sc = {4'd2};
`endif
`ifdef ZAAMO_SUPPORTED
        bins amoadd_d  = {4'd3};
        bins amoswap_w = {4'd4};
`endif
`ifdef ZICBOZ_SUPPORTED
        bins cbo_zero = {4'd5};
`endif
`ifdef V_SUPPORTED
        bins vle        = {4'd6};
        bins vle_masked = {4'd7};
        bins vlse       = {4'd8};
        bins vluxei     = {4'd9};
        bins vleff      = {4'd10};
        bins vse        = {4'd11};
        bins vse_masked = {4'd12};
        bins vsse       = {4'd13};
        bins vsuxei     = {4'd14};
`endif
    }
    // Their outcome: none (the tags match, or no tag check), or a software-check exception
    checked_regular_result: coverpoint zimt_exception(ins) iff (zimt_regular_access(ins) != 4'd0) {
        type_option.weight = 0;
        bins none           = {8'h00};
        bins software_check = {8'h52};
    }
    // In M-mode with mstatus.MPRV = 1 and MPP = S
    regular_mprv_s: coverpoint zimt_mprv_mpp(ins) iff (zimt_regular_access(ins) != 4'd0) {
        type_option.weight = 0;
        bins mprv_s = {4'b1001};
    }
    // Without address translation in S-mode (satp Bare), with no exception (S-mode tests only matching pointer tags)
    regular_satp_bare: coverpoint (zimt_atp_mode(ins, CSR_SATP) == 4'd0)
        iff ((zimt_regular_access(ins) != 4'd0) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins bare = {1'b1};
    }
    // With first-stage paging, LR/SC, an AMO or cbo.zero (the crosses take the access from checked_regular) of a page
    // of zimt_mtag_page (zimt_regular_page): of a tagged-data page, which is checked (the outcome is
    // checked_regular_result)...
    regular_tagged_page: coverpoint zimt_regular_page(ins) {
        type_option.weight = 0;
        bins tagged_data = {3'd1};
    }
    // ...of a page with PTE.MTAG = 1 and X = 1, through a pointer with a pointer tag: no tag check, no exception
    regular_unchecked_page: coverpoint zimt_regular_page(ins)
        iff ((ins.current.rs1_val[63:57] != 7'd0) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins executable = {3'd4};
    }
    // A misaligned LR/SC or AMO (zimt_regular_misaligned) with a mismatching pointer tag: with Bare translation the tag
    // check comes before its address-misaligned exception (a software-check exception)...
    regular_misaligned_bare: coverpoint zimt_exception(ins) iff (zimt_regular_misaligned(ins)) {
        type_option.weight = 0;
        bins software_check = {8'h52};
    }
    // ...with first-stage paging its address-misaligned exception comes first (store/AMO address misaligned), the
    // access not checked; where misaligned AMOs are supported, it is checked
    regular_misaligned_paged: coverpoint zimt_exception(ins) iff (zimt_regular_misaligned(ins)) {
        type_option.weight = 0;
`ifdef UDB_MISALIGNED_AMO
        bins software_check = {8'h52};
`else
        bins misaligned = {8'h46};
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
    // With first-stage address translation, satp (S-mode) or vsatp (VS-mode) not Bare, of a page without PTE.MTAG
    // (none of zimt_mtag_page, or its page without PTE.MTAG, and not the VS-stage tagged-data page), not from a code
    // page of zimt_code_page and without sp as the base register, and a pointer tag: no tag check, no exception
    checked_satp_translated: coverpoint (zimt_atp_mode(ins, CSR_SATP) != 4'd0)
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0) &&
             (zimt_exception(ins) == 8'h00) && (zimt_mtag_page(ins.current.virt_adr_d) inside {3'd0, 3'd2}) &&
             (zimt_code_page(ins) == 3'd0) && (ins.current.insn[19:15] != 5'd2)) {
        type_option.weight = 0;
        bins translated = {1'b1};
    }
    checked_vsatp_translated: coverpoint (zimt_atp_mode(ins, CSR_VSATP) != 4'd0)
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0) &&
             (zimt_exception(ins) == 8'h00) && (ins.current.virt_adr_d[38:12] != `ZIMT_VS_MTAG_VPN) &&
             (ins.current.insn[19:15] != 5'd2)) {
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

    // With first-stage paging (satp not Bare), a load or store of one page of zimt_mtag_page: of a tagged-data page,
    // which is checked (the outcome is checked_result)...
    mtag_tagged_page: coverpoint zimt_mtag_single(ins) {
        type_option.weight = 0;
        bins tagged_data = {3'd1};
    }
    // ...of a page that a supervisor access does not check, through a pointer with a pointer tag: no exception
    mtag_unchecked_page: coverpoint zimt_mtag_single(ins)
        iff ((ins.current.rs1_val[63:57] != 7'd0) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins user       = {3'd3};
        bins executable = {3'd4};
    }
    // ...of a tagged-data page with memory tagging disabled, which ignores PTE.MTAG: no exception
    mtag_ignored: coverpoint zimt_mtag_single(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
        bins tagged_data = {3'd1};
    }
    // ...of a data page behind a non-leaf PTE with PTE.MTAG, which is reserved there: a page fault
    mtag_nonleaf_fault: coverpoint zimt_exception(ins) iff (zimt_mtag_single(ins) == 3'd5) {
        type_option.weight = 0;
        bins load_page_fault  = {8'h4D};
        bins store_page_fault = {8'h4F};
    }
    // A load or store over two pages (zimt_mtag_straddle) that the hart checks, in both pages or in the supervisor
    // one (the outcome is checked_result)...
    mtag_straddle_checked: coverpoint zimt_mtag_straddle(ins) {
        type_option.weight = 0;
        bins tagged_untagged = {3'd1};
        bins user_tagged     = {3'd2};
        bins untagged_tagged = {3'd4};
    }
    // ...and one that it does not check: no exception
    mtag_straddle_unchecked: coverpoint zimt_mtag_straddle(ins) iff (zimt_exception(ins) == 8'h00) {
        type_option.weight = 0;
        bins untagged_user = {3'd3};
    }
    // A load over a tagged-data page, whose chunk mismatches, and an unmapped page (zimt_straddle_unmapped): the load
    // page fault of the second page, not a software-check exception
    mtag_straddle_fault: coverpoint zimt_exception(ins) iff (zimt_straddle_unmapped(ins)) {
        type_option.weight = 0;
        bins load_page_fault = {8'h4D};
    }
    // A load or store through a pointer with a pointer tag, which mismatches in the tests, from a code page
    // (zimt_code_page): not checked from a tagcheck-exempt code page (no exception), checked from one without PTE.MTAG
    // (a software-check exception). {code page, software-check exception, no exception}
    mtag_code_access: coverpoint {zimt_code_page(ins), zimt_exception(ins) == 8'h52, zimt_exception(ins) == 8'h00}
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins exempt              = {5'b001_01};
        bins normal              = {5'b010_10};
        bins exempt_execute_only = {5'b101_01};
    }
    // ...and a load of a 32-bit instruction over two code pages: checked unless both are tagcheck-exempt
    mtag_code_straddle: coverpoint {zimt_code_page(ins), zimt_exception(ins) == 8'h52, zimt_exception(ins) == 8'h00}
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins exempt_normal = {5'b011_10};
        bins exempt_exempt = {5'b100_01};
    }
    // checktag from a tagcheck-exempt code page, with a mismatching pointer tag: a software-check exception
    mtag_code_checktag: coverpoint zimt_code_page(ins) iff (zimt_is_checktag(ins) && (zimt_exception(ins) == 8'h52)) {
        type_option.weight = 0;
        bins exempt = {3'd1};
    }
    // With two-stage translation (vsatp not Bare), a load or store of the page whose VS-stage leaf PTE has PTE.MTAG,
    // a tagged-data page (the outcome is checked_result), not from a VS-stage code page of zimt_vs_code_page
    vs_mtag_page: coverpoint (ins.current.virt_adr_d[38:12] == `ZIMT_VS_MTAG_VPN)
        iff ((zimt_checked_access(ins) != 5'd31) && (zimt_atp_mode(ins, CSR_VSATP) != 4'd0) &&
             (zimt_vs_code_page(ins) == 2'd0)) {
        type_option.weight = 0;
        bins tagged_data = {1'b1};
    }
    // A load or store through a pointer with a pointer tag, which mismatches in the tests, from a VS-stage code page
    // (zimt_vs_code_page): not checked from the tagcheck-exempt one (no exception), checked from the other one (a
    // software-check exception). {code page, software-check exception, no exception}
    vs_mtag_code_access: coverpoint {zimt_vs_code_page(ins), zimt_exception(ins) == 8'h52, zimt_exception(ins) == 8'h00}
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins exempt = {4'b01_01};
        bins normal = {4'b10_10};
    }
    // A load from a VS-stage code page (zimt_vs_code_page) whose VS-stage walk reads a page table that the G stage
    // does not map: a load guest-page fault that HS-mode takes with the pseudoinstruction 0x3000 in htinst
    // (zimt_trap_vs_pte_read), depositing the MTAG bit of the code page in hstatus.MTAG_I: 1 from the tagcheck-exempt
    // code page, 0 from the other one. {code page, hstatus.MTAG_I after the trap}
    mtag_i_deposit: coverpoint {zimt_vs_code_page(ins), zimt_trap_hstatus_mtag_i(ins)}
        iff ((zimt_exception(ins) == 8'h55) && zimt_trap_vs_pte_read(ins)) {
        type_option.weight = 0;
        bins exempt = {3'b01_1};
        bins normal = {3'b10_0};
    }
    // With the G stage only, a load or store of the guest physical page whose G-stage leaf PTE has PTE.MTAG, which is
    // reserved there: a guest-page fault
    mtag_g_stage_fault: coverpoint zimt_exception(ins)
        iff ((zimt_checked_access(ins) != 5'd31) && (ins.current.virt_adr_d[40:12] == `ZIMT_G_MTAG_GPN) &&
             (zimt_atp_mode(ins, CSR_VSATP) == 4'd0) && (zimt_atp_mode(ins, CSR_HGATP) != 4'd0)) {
        type_option.weight = 0;
        bins load_guest_page_fault  = {8'h55};
        bins store_guest_page_fault = {8'h57};
    }

    // mstatus.MTAG_I and hstatus.MTAG_I: set (csrs) or cleared (csrc), mstatus.MTAG_I before a read of sstatus, and
    // loads and stores with mstatus.MPRV = 1 and MTAG_I = 1 through a pointer with a pointer tag: not checked, no
    // exception, with MPP = S, or MPV = 1 with MPP = S (VS-mode) or U (VU-mode)
    mstatus_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mstatus = {CSR_MSTATUS};
    }
    sstatus_csr: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins sstatus = {CSR_SSTATUS};
    }
    mtag_i_m_written: coverpoint ins.current.rs1_val[40] {
        type_option.weight = 0;
        bins mtag_i = {1'b1};
    }
    mtag_i_h_written: coverpoint ins.current.rs1_val[10] {
        type_option.weight = 0;
        bins mtag_i = {1'b1};
    }
    mtag_i_m_set: coverpoint zimt_mstatus_mtag_i(ins) {
        type_option.weight = 0;
        bins set = {1'b1};
    }
    mprv_mtag_i_s: coverpoint zimt_mprv_mpp(ins) iff (zimt_mtag_i_unchecked(ins)) {
        type_option.weight = 0;
        bins mprv_s = {4'b1001};
    }
    mprv_mtag_i_v: coverpoint zimt_mprv_mpp(ins) iff (zimt_mtag_i_unchecked(ins)) {
        type_option.weight = 0;
        bins mprv_vs = {4'b1101};
        bins mprv_vu = {4'b1100};
    }
    // The MT_MODE of VS-mode (MPP = S) or VU-mode (MPP = U) for MPRV with MPV = 1, enabled
    mprv_v_mt: coverpoint zimt_mprv_v_mt(ins) {
        type_option.weight = 0;
        bins tag4 = {2'b10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {2'b11};
`endif
    }
    // A load with MPRV = 1, MPV = 0 and MPP = U (U-mode's translation and memory tagging) and first-stage paging,
    // through a pointer with a pointer tag (zimt_mtag_single): of the user tagged-data page, with a mismatching tag (a
    // software-check exception) or the matching one (none); of the user page without PTE.MTAG (not checked: none).
    // {page, software-check exception, no exception}
    mprv_u_page: coverpoint {zimt_mtag_single(ins), zimt_exception(ins) == 8'h52, zimt_exception(ins) == 8'h00}
        iff ((zimt_mprv_mpp(ins) == 4'b1000) && (ins.current.insn[19:15] != 5'd2) &&
             (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins user_mismatch = {5'b011_10};
        bins user_match    = {5'b011_01};
        bins user_untagged = {5'b111_01};
    }
    // ...and with MPV = 1 (VU-mode's) and first-stage paging (zimt_vs_user_page)
    mprv_vu_page: coverpoint {zimt_vs_user_page(ins), zimt_exception(ins) == 8'h52, zimt_exception(ins) == 8'h00}
        iff ((zimt_mprv_mpp(ins) == 4'b1100) && (ins.current.insn[19:15] != 5'd2) &&
             (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins user_mismatch = {4'b01_10};
        bins user_match    = {4'b01_01};
        bins user_untagged = {4'b10_01};
    }
    // Protection of tag storage (Svatag; zimt_vitt: {kind, page, outcome}). In S-mode with the VITT range from the tags
    // page of MTAG_PAGES: a load and a store in its first page, and LR, SC (reserved by an LR of the same address
    // through the page after, which is performed), amoadd.d and cbo.zero there, a load in its last page and (with
    // misaligned loads performed byte by byte) from the page before into its first page and from its last page into
    // the page after, raise the access fault of their kind; a load in the page before or the page after none; in a
    // tagged-data page of the range its tag check comes first (a page fault on its tag address), in an unmapped page
    // its page fault. settag of a chunk in its first page, of chunks from the page before into it, or of chunks from its
    // last page into the page after raises a store/AMO access fault, and of the last chunk before it alone the page
    // fault of its tag store. A load through sp in its first page raises a load access fault too.
    vitt_s: coverpoint zimt_vitt(ins) {
        type_option.weight = 0;
        bins ld_first           = {{4'd1, 3'd1, 2'd1}};
        bins sd_first           = {{4'd2, 3'd1, 2'd1}};
        bins ld_before          = {{4'd1, 3'd4, 2'd0}};
        bins ld_last            = {{4'd1, 3'd2, 2'd1}};
        bins ld_after           = {{4'd1, 3'd5, 2'd0}};
        bins ld_tag_check       = {{4'd1, 3'd3, 2'd3}};
        bins ld_unmapped        = {{4'd1, 3'd3, 2'd2}};
        bins settag_first       = {{4'd7, 3'd1, 2'd1}};
        bins settag_into_first  = {{4'd7, 3'd6, 2'd1}};
        bins settag_out_of_last = {{4'd7, 3'd7, 2'd1}};
        bins settag_before      = {{4'd7, 3'd4, 2'd3}};
        bins ld_sp_first        = {{4'd12, 3'd1, 2'd1}};
`ifdef UDB_MISALIGNED_LDST
`ifdef UDB_MISALIGNED_SPLIT_STRATEGY_SEQUENTIAL_BYTES
        bins ld_into_first      = {{4'd1, 3'd6, 2'd1}};
        bins ld_out_of_last     = {{4'd1, 3'd7, 2'd1}};
        bins sd_into_first      = {{4'd2, 3'd6, 2'd1}};
`endif
`endif
`ifdef ZALRSC_SUPPORTED
        bins lr_first           = {{4'd3, 3'd1, 2'd1}};
        bins lr_after           = {{4'd3, 3'd5, 2'd0}};
        bins sc_first           = {{4'd4, 3'd1, 2'd1}};
`endif
`ifdef ZAAMO_SUPPORTED
        bins amoadd_d_first     = {{4'd5, 3'd1, 2'd1}};
`endif
`ifdef ZICBOZ_SUPPORTED
        bins cbo_zero_first     = {{4'd6, 3'd1, 2'd1}};
`endif
    }
    // ...in M-mode with mstatus.MPRV = 1 and MPP = U, with the VITT range of U-mode from the user tags page: loads in
    // its first and last pages (and from the page before into the first one and from the last one into the page
    // after) raise a load access fault; in the page before and the page after none; vle64.v and vse64.v in its first
    // page a load and a store/AMO access fault at element 0. With the range over the MTAG pages, a load of the user
    // tagged-data page in it: with the matching pointer tag the access fault, with a mismatching one the
    // software-check exception of its tag check
    vitt_mprv_u: coverpoint zimt_vitt(ins) {
        type_option.weight = 0;
        bins ld_first       = {{4'd1, 3'd1, 2'd1}};
        bins ld_before      = {{4'd1, 3'd4, 2'd0}};
        bins ld_last        = {{4'd1, 3'd2, 2'd1}};
        bins ld_after       = {{4'd1, 3'd5, 2'd0}};
        bins ld_tagged_match    = {{4'd1, 3'd3, 2'd1}};
        bins ld_tagged_mismatch = {{4'd1, 3'd3, 2'd3}};
`ifdef UDB_MISALIGNED_LDST
`ifdef UDB_MISALIGNED_SPLIT_STRATEGY_SEQUENTIAL_BYTES
        bins ld_into_first  = {{4'd1, 3'd6, 2'd1}};
        bins ld_out_of_last = {{4'd1, 3'd7, 2'd1}};
`endif
`endif
`ifdef V_SUPPORTED
        bins vle_first      = {{4'd8, 3'd1, 2'd1}};
        bins vse_first      = {{4'd9, 3'd1, 2'd1}};
`endif
    }
    // ...and with MPV = 1, in the VITT range of VS-mode (MPP = S) or VU-mode (MPP = U): a load in its first page
    // raises a load access fault, one in the page before it none
    vitt_mprv_v: coverpoint zimt_vitt(ins) {
        type_option.weight = 0;
        bins ld_first  = {{4'd1, 3'd1, 2'd1}};
        bins ld_before = {{4'd1, 3'd4, 2'd0}};
    }
    // ...and with mstatus.MTAG_I = 1, which only disables the tag checks: a load in the first page of the VITT range of
    // U-mode still raises a load access fault
    vitt_mtag_i: coverpoint zimt_vitt(ins) iff (zimt_mstatus_mtag_i(ins)) {
        type_option.weight = 0;
        bins ld_first  = {{4'd1, 3'd1, 2'd1}};
        // ...also in a user tagged-data page in the range, with a mismatching pointer tag
        bins ld_tagged = {{4'd1, 3'd3, 2'd1}};
    }
    // In S-mode, settag of 16 chunks from the page before the VITT range, of which only the last one is in it: a
    // store/AMO access fault
    vitt_settag_16: coverpoint zimt_vitt(ins) iff (ins.current.insn[23:20] == 4'hF) {
        type_option.weight = 0;
        bins into_first = {{4'd7, 3'd6, 2'd1}};
    }
    // In S-mode with memory tagging disabled, a load in the first page of the range that its tag table base would give
    // with 4-bit tags: performed
    vitt_mt_disabled: coverpoint zimt_vitt_mt_disabled(ins) {
        type_option.weight = 0;
        bins ld_first = {{4'd1, 3'd1, 2'd0}};
    }
    // In U-mode with Sv39, and in VS-mode and VU-mode with two-stage translation, a load and a settag in the first page
    // of the VITT range of the mode: a load and a store/AMO access fault
    vitt_direct: coverpoint zimt_vitt(ins) {
        type_option.weight = 0;
        bins ld_first     = {{4'd1, 3'd1, 2'd1}};
        bins settag_first = {{4'd7, 3'd1, 2'd1}};
    }
    // In HS-mode, hlvx.wu, which is not a regular access, in the first page of the VITT range of its guest mode:
    // performed
    vitt_hlvx: coverpoint zimt_vitt(ins) {
        type_option.weight = 0;
        bins hlvx_first = {{4'd13, 3'd1, 2'd0}};
    }
    // In HS-mode, hlv.d and hsv.d in the first page of the VITT range of their guest mode (hstatus.SPVP): a load
    // access fault and a store/AMO access fault
    vitt_hlsv: coverpoint zimt_vitt(ins) {
        type_option.weight = 0;
        bins hlv_first = {{4'd10, 3'd1, 2'd1}};
        bins hsv_first = {{4'd11, 3'd1, 2'd1}};
    }
    // The GVA bit of the access fault of a regular access or settag in the VITT range of its mode, which HS-mode or
    // M-mode takes (zimt_trap_gva): set at effective V = 1 (VS-mode and VU-mode, also through MPRV with MPV = 1, and
    // HLV and HSV)...
    vitt_fault_gva: coverpoint zimt_trap_gva(ins) iff (zimt_vitt(ins)[1:0] == 2'd1) {
        type_option.weight = 0;
        bins gva = {1'b1};
    }
    // ...and clear at V = 0
    vitt_fault_no_gva: coverpoint zimt_trap_gva(ins) iff (zimt_vitt(ins)[1:0] == 2'd1) {
        type_option.weight = 0;
        bins no_gva = {1'b0};
    }
    // Svukte, which Svatag depends on (zimt_svukte_tag: {kind, address bit 63, HUKTE, UKTE, tag table base bit 63,
    // outcome}): in U-mode, with the tag table of U-mode in the upper half, checktag, ld and settag are performed with
    // senvcfg.UKTE = 0 and raise the page fault of their tag access with UKTE = 1; with the tag table in the lower half
    // ld is performed with UKTE = 1; ld of an address in the upper half raises a page fault at its address with UKTE = 1
    // and at its tag address (not canonical) with UKTE = 0
    svukte_tag_u: coverpoint zimt_svukte_tag(ins) {
        type_option.weight = 0;
        bins checktag_upper      = {{3'd2, 1'b0, 1'b0, 1'b0, 1'b1, 2'd0}};
        bins checktag_upper_ukte = {{3'd2, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
        bins ld_upper            = {{3'd1, 1'b0, 1'b0, 1'b0, 1'b1, 2'd0}};
        bins ld_upper_ukte       = {{3'd1, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
        bins settag_upper        = {{3'd3, 1'b0, 1'b0, 1'b0, 1'b1, 2'd0}};
        bins settag_upper_ukte   = {{3'd3, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
        bins ld_lower_ukte       = {{3'd1, 1'b0, 1'b0, 1'b1, 1'b0, 2'd0}};
        bins ld_upper_address_ukte = {{3'd1, 1'b1, 1'b0, 1'b1, 1'b0, 2'd2}};
        bins ld_upper_address    = {{3'd1, 1'b1, 1'b0, 1'b0, 1'b0, 2'd1}};
    }
    // ...in M-mode with mstatus.MPRV = 1 and MPP = U: ld with the tag table in the upper half
    svukte_tag_mprv: coverpoint zimt_svukte_tag(ins) {
        type_option.weight = 0;
        bins ld_upper      = {{3'd1, 1'b0, 1'b0, 1'b0, 1'b1, 2'd0}};
        bins ld_upper_ukte = {{3'd1, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
    }
    // ...in VU-mode: ld and settag with the tag table in the upper half
    svukte_tag_v: coverpoint zimt_svukte_tag(ins) {
        type_option.weight = 0;
        bins ld_upper          = {{3'd1, 1'b0, 1'b0, 1'b0, 1'b1, 2'd0}};
        bins ld_upper_ukte     = {{3'd1, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
        bins settag_upper_ukte = {{3'd3, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
    }
    // ...hlv.d with hstatus.SPVP = 0 in HU-mode, which hstatus.HUKTE qualifies, not senvcfg.UKTE...
    svukte_tag_hu: coverpoint zimt_svukte_tag(ins) {
        type_option.weight = 0;
        bins hlv_upper_hukte = {{3'd4, 1'b0, 1'b1, 1'b0, 1'b1, 2'd1}};
        bins hlv_upper_ukte  = {{3'd4, 1'b0, 1'b0, 1'b1, 1'b1, 2'd0}};
    }
    // ...and in HS-mode, which senvcfg.UKTE qualifies, not hstatus.HUKTE
    svukte_tag_hs: coverpoint zimt_svukte_tag(ins) {
        type_option.weight = 0;
        bins hlv_upper_ukte  = {{3'd4, 1'b0, 1'b0, 1'b1, 1'b1, 2'd1}};
        bins hlv_upper_hukte = {{3'd4, 1'b0, 1'b1, 1'b0, 1'b1, 2'd0}};
    }
    // The tag width of the VITT range (zimt_vitt_range)
    vitt_width: coverpoint zimt_vitt_range(ins)[65:64] {
        type_option.weight = 0;
        bins tag4 = {2'b10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {2'b11};
`endif
    }
    // {mstatus.MPRV, MPV, MPP}: MPP = U; and MPV = 1 with MPP = U or S
    vitt_mprv_u_mode: coverpoint zimt_mprv_mpp(ins) {
        type_option.weight = 0;
        bins u = {4'b1000};
    }
    vitt_mprv_v_mode: coverpoint zimt_mprv_mpp(ins) {
        type_option.weight = 0;
        bins vu = {4'b1100};
        bins vs = {4'b1101};
    }
    // senvcfg.MT_MODE (U-mode's and VU-mode's), enabled
    senvcfg_mt: coverpoint zimt_senvcfg_mt(ins) {
        type_option.weight = 0;
        bins tag4 = {2'b10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {2'b11};
`endif
    }
    // The GVA bit of the software-check exception of a mismatch that HS-mode or M-mode takes (zimt_trap_gva): set for
    // HLV and HSV...
    hlsv_swcheck_gva: coverpoint zimt_trap_gva(ins)
        iff ((zimt_hlsv(ins) inside {3'd1, 3'd2}) && (zimt_exception(ins) == 8'h52) &&
             !ins.current.csr_wb[CSR_VSCAUSE]) {
        type_option.weight = 0;
        bins gva = {1'b1};
    }
    // ...and clear for the loads and stores of a guest mode, also through MPRV with MPV = 1
    swcheck_gva_clear: coverpoint zimt_trap_gva(ins)
        iff ((zimt_checked_access(ins) != 5'd31) && (zimt_exception(ins) == 8'h52) &&
             !ins.current.csr_wb[CSR_VSCAUSE]) {
        type_option.weight = 0;
        bins no_gva = {1'b0};
    }
    // A load or store that does not use sp as the base register with mstatus.MTAG_I = 1 and no MPRV (S-mode), or with
    // hstatus.MTAG_I = 1 (VS-mode and VU-mode), which only affect loads and stores with MPRV and HLV and HSV: still
    // checked, a software-check exception with a mismatching pointer tag
    mtag_i_checked: coverpoint zimt_exception(ins)
        iff ((zimt_checked_access(ins) != 5'd31) && zimt_mstatus_mtag_i(ins) && (ins.current.insn[19:15] != 5'd2)) {
        type_option.weight = 0;
        bins software_check = {8'h52};
    }
    hstatus_mtag_i_checked: coverpoint zimt_exception(ins)
        iff ((zimt_checked_access(ins) != 5'd31) && zimt_hstatus_mtag_i(ins) && (ins.current.insn[19:15] != 5'd2)) {
        type_option.weight = 0;
        bins software_check = {8'h52};
    }

    // HLV and HSV (zimt_hlsv) with the MT_MODE of their guest mode enabled (zimt_hlsv_mt_mode) and hstatus.MTAG_I = 0:
    // by tag width, guest mode (hstatus.SPVP) and kind, and their outcome (none, or a software-check exception)
    hlsv_access: coverpoint zimt_hlsv(ins)
        iff ((zimt_hlsv_mt_mode(ins) != 2'b00) && !zimt_hstatus_mtag_i(ins)) {
        type_option.weight = 0;
        bins hlv = {3'd1};
        bins hsv = {3'd2};
    }
    // The same with vsatp = Bare, where every guest page is a tagged-data page: the outcomes of cp_hlsv_checked come
    // from the tag check alone, not from a page without PTE.MTAG (cp_hlsv_paged)
    hlsv_access_bare: coverpoint zimt_hlsv(ins)
        iff ((zimt_hlsv_mt_mode(ins) != 2'b00) && !zimt_hstatus_mtag_i(ins) &&
             (zimt_atp_mode(ins, CSR_VSATP) == 4'd0)) {
        type_option.weight = 0;
        bins hlv = {3'd1};
        bins hsv = {3'd2};
    }
    hlsv_mt: coverpoint zimt_hlsv_mt_mode(ins) {
        type_option.weight = 0;
        bins tag4 = {2'b10};
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
        bins tag7 = {2'b11};
`endif
    }
    hlsv_spvp: coverpoint zimt_spvp(ins) {
        type_option.weight = 0;
        bins vu = {1'b0};
        bins vs = {1'b1};
    }
    hlsv_result: coverpoint zimt_exception(ins) iff (zimt_hlsv(ins) != 3'd0) {
        type_option.weight = 0;
        bins none           = {8'h00};
        bins software_check = {8'h52};
    }
    // hlv.d with hstatus.SPVP = 0 (VU-mode) and MTAG_I = 0, through a pointer with a mismatching tag, with one of the
    // fields that hold the MT_MODE of VU-mode enabled (zimt_hlsv_vu_fields): in HS-mode senvcfg.MT_MODE, which it
    // uses (checked: a software-check exception), or hstatus.VUMT_MODE (not checked: no exception)...
    hlsv_vu_hs: coverpoint zimt_hlsv_vu_fields(ins)
        iff ((zimt_hlsv(ins) == 3'd1) && !zimt_spvp(ins) && !zimt_hstatus_mtag_i(ins) &&
             (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins senvcfg = {4'b10_10};
        bins vumt    = {4'b01_01};
    }
    // ...in HU-mode hstatus.VUMT_MODE, which it uses (checked), or senvcfg.MT_MODE (not checked)
    hlsv_vu_hu: coverpoint zimt_hlsv_vu_fields(ins)
        iff ((zimt_hlsv(ins) == 3'd1) && !zimt_spvp(ins) && !zimt_hstatus_mtag_i(ins) &&
             (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins vumt    = {4'b01_10};
        bins senvcfg = {4'b10_01};
    }
    // HLV and HSV with hstatus.MTAG_I = 1 and the MT_MODE of their guest mode enabled, through a pointer with a pointer
    // tag: not checked, no exception
    hlsv_mtag_i: coverpoint zimt_hlsv(ins)
        iff (zimt_hstatus_mtag_i(ins) && (zimt_hlsv_mt_mode(ins) != 2'b00) &&
             (ins.current.rs1_val[63:57] != 7'd0) && (zimt_exception(ins) == 8'h00)) {
        type_option.weight = 0;
        bins hlv = {3'd1};
        bins hsv = {3'd2};
    }
    // hlv.d and hsv.d with hstatus.SPVP = 1 and first-stage paging (zimt_hlsv_page), through a pointer with a pointer
    // tag: of the VS-stage tagged-data page, with the matching tag (none), a mismatching one (a software-check
    // exception), and with the tags in a guest page that the VS stage does not map (a load page fault) or whose guest
    // physical page the G stage does not map (a load guest-page fault); of a page without PTE.MTAG and (vsstatus.SUM =
    // 1) of a user tagged-data page (not checked: none); and over the tagged-data page and the page after it, checked
    // in both (a software-check exception), and over the page without PTE.MTAG before it and it, also checked in both
    // (a software-check exception, then none). {page, exception}
    hlsv_paged: coverpoint {zimt_hlsv_page(ins), zimt_exception(ins)}
        iff (zimt_spvp(ins) && (ins.current.rs1_val[63:57] != 7'd0)) {
        type_option.weight = 0;
        bins tagged_match         = {11'h1_00};
        bins tagged_mismatch      = {11'h1_52};
        bins tag_page_fault       = {11'h1_4D};
        bins tag_guest_page_fault = {11'h1_55};
        bins untagged             = {11'h2_00};
        bins user_sum             = {11'h3_00};
`ifdef UDB_MISALIGNED_LDST
`ifdef UDB_MISALIGNED_SPLIT_STRATEGY_SEQUENTIAL_BYTES
        bins straddle             = {11'h4_52};
        bins straddle_untagged_mismatch = {11'h5_52};
        bins straddle_untagged_match    = {11'h5_00};
`endif
`endif
    }
    // hlv.wu and hlvx.wu with the MT_MODE of their guest mode enabled and hstatus.MTAG_I = 0, of a chunk whose tag
    // mismatches: HLV is checked (a software-check exception), HLVX never (no exception). {kind, software-check
    // exception, no exception}
    hlvx_checked: coverpoint {zimt_hlsv(ins), zimt_exception(ins) == 8'h52, zimt_exception(ins) == 8'h00}
        iff ((zimt_hlsv_mt_mode(ins) != 2'b00) && !zimt_hstatus_mtag_i(ins)) {
        type_option.weight = 0;
        bins hlv_wu  = {5'b011_10};
        bins hlvx_wu = {5'b100_01};
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
