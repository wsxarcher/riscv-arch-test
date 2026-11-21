///////////////////////////////////////////
//
// RISC-V Architectural Functional Coverage Covergroups
//
// Zimt memory tagging: the Zimt instructions and the MOP.RR encodings around them, with memory tagging
// disabled and enabled, in M, S, U, VS and VU modes; settag and checktag with memory tagging enabled, which store
// and check tags in the tag tables of Svatag and Smvatag; the implicit tag checks of loads and stores; the MT_MODE
// fields and tag generation exclusion mask CSRs; and the software-check exception (cause 18) in the delegation and
// cause CSRs.
//
// SPDX-License-Identifier: Apache-2.0
//
////////////////////////////////////////////////////////////////////////////////////////////////

`define COVER_ZIMT

// xMT_MODE of the mode the instruction executes in: MT_MODE (bits 35:34) of mseccfg (M), menvcfg (S/HS),
// henvcfg (VS) or senvcfg (U and VU)
function automatic logic [1:0] zimt_mt_mode(ins_t ins);
    logic [11:0] csr;
    case ({ins.prev.mode_virt, ins.prev.mode})
        3'b011:  csr = CSR_MSECCFG;
        3'b001:  csr = CSR_MENVCFG;
        3'b101:  csr = CSR_HENVCFG;
        default: csr = CSR_SENVCFG;
    endcase
    return 2'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, csr) >> 34);
endfunction

// The MOP.RR.1 or MOP.RR.0 encodings of cp_mop_rr_not_zimt, which each miss one condition of a Zimt instruction:
//   0-15: MOP.RR.1, rd != x0, bit 24 = 1, by imm4 (neither gentag nor addtag)
//   16:   MOP.RR.1, rd != x0, rs1 != x0, bits 24:20 = 0 (neither gentag nor addtag)
//   17:   MOP.RR.1, rd = x0, rs1 != x0, bit 24 = 1 (not checktag)
//   18:   MOP.RR.1, rd = rs1 = x0 (not checktag)
//   19:   MOP.RR.0, rd != x0 (not settag)
//   20:   MOP.RR.0, rd = x0, rs1 != x0, bit 24 = 1 (not settag)
//   21:   MOP.RR.0, rd = rs1 = x0 (not settag)
//   31:   any other instruction
function automatic logic [4:0] zimt_mop_rr_not_zimt(ins_t ins);
    logic [31:0] insn = ins.current.insn;
    logic rd_x0 = (insn[11:7] == 5'd0);
    logic rs1_x0 = (insn[19:15] == 5'd0);
    if (insn ==? MOP_RR_1) begin
        if (!rd_x0 && insn[24]) return {1'b0, insn[23:20]};
        if (!rd_x0 && !rs1_x0 && insn[24:20] == 5'd0) return 5'd16;
        if (rd_x0 && !rs1_x0 && insn[24]) return 5'd17;
        if (rd_x0 && rs1_x0) return 5'd18;
    end else if (insn ==? MOP_RR_0) begin
        if (!rd_x0) return 5'd19;
        if (!rs1_x0 && insn[24]) return 5'd20;
        if (rs1_x0) return 5'd21;
    end
    return 5'd31;
endfunction

// gentag: MOP.RR.1 with bit 24 = 0, imm4 = 0, rs1 = x0 and rd != x0
function automatic bit zimt_is_gentag(ins_t ins);
    return (ins.current.insn ==? MOP_RR_1) && (ins.current.insn[24:15] == 10'd0) && (ins.current.insn[11:7] != 5'd0);
endfunction

// addtag: MOP.RR.1 with bit 24 = 0, imm4 != 0 and rd != x0
function automatic bit zimt_is_addtag(ins_t ins);
    return (ins.current.insn ==? MOP_RR_1) && !ins.current.insn[24] && (ins.current.insn[23:20] != 4'd0) &&
           (ins.current.insn[11:7] != 5'd0);
endfunction

// settag: MOP.RR.0 with bit 24 = 0, rd = x0 and rs1 != x0
function automatic bit zimt_is_settag(ins_t ins);
    return (ins.current.insn ==? MOP_RR_0) && !ins.current.insn[24] && (ins.current.insn[11:7] == 5'd0) &&
           (ins.current.insn[19:15] != 5'd0);
endfunction

// checktag: MOP.RR.1 with bit 24 = 0, rd = x0 and rs1 != x0
function automatic bit zimt_is_checktag(ins_t ins);
    return (ins.current.insn ==? MOP_RR_1) && !ins.current.insn[24] && (ins.current.insn[11:7] == 5'd0) &&
           (ins.current.insn[19:15] != 5'd0);
endfunction

// The loads and stores that implicit tag checks cover, by kind: 0 lb, 1 lh, 2 lw, 3 ld, 4 lbu, 5 lhu, 6 lwu, 8 sb,
// 9 sh, 10 sw, 11 sd, 12 flh, 13 flw, 14 fld, 16 fsh, 17 fsw, 18 fsd, 20 c.lw, 21 c.ld, 22 c.sw, 23 c.sd, 24 c.fld,
// 25 c.fsd, 26 c.lbu, 27 c.lh, 28 c.lhu, 29 c.sb, 30 c.sh; 31 for any other instruction
function automatic logic [4:0] zimt_checked_access(ins_t ins);
    logic [31:0] insn = ins.current.insn;
    if (insn ==? LB)    return 5'd0;
    if (insn ==? LH)    return 5'd1;
    if (insn ==? LW)    return 5'd2;
    if (insn ==? LD)    return 5'd3;
    if (insn ==? LBU)   return 5'd4;
    if (insn ==? LHU)   return 5'd5;
    if (insn ==? LWU)   return 5'd6;
    if (insn ==? SB)    return 5'd8;
    if (insn ==? SH)    return 5'd9;
    if (insn ==? SW)    return 5'd10;
    if (insn ==? SD)    return 5'd11;
    if (insn ==? FLH)   return 5'd12;
    if (insn ==? FLW)   return 5'd13;
    if (insn ==? FLD)   return 5'd14;
    if (insn ==? FSH)   return 5'd16;
    if (insn ==? FSW)   return 5'd17;
    if (insn ==? FSD)   return 5'd18;
    if (insn ==? C_LW)  return 5'd20;
    if (insn ==? C_LD)  return 5'd21;
    if (insn ==? C_SW)  return 5'd22;
    if (insn ==? C_SD)  return 5'd23;
    if (insn ==? C_FLD) return 5'd24;
    if (insn ==? C_FSD) return 5'd25;
    if (insn ==? C_LBU) return 5'd26;
    if (insn ==? C_LH)  return 5'd27;
    if (insn ==? C_LHU) return 5'd28;
    if (insn ==? C_SB)  return 5'd29;
    if (insn ==? C_SH)  return 5'd30;
    return 5'd31;
endfunction

// Whether a kind of zimt_checked_access is a store
function automatic bit zimt_checked_store(logic [4:0] kind);
    return kind inside {[5'd8:5'd11], [5'd16:5'd18], 5'd22, 5'd23, 5'd25, 5'd29, 5'd30};
endfunction

// A 32-bit load or store over two chunks: its bytes, from rs1 + imm, cross a 16-byte boundary
function automatic bit zimt_two_chunks(ins_t ins);
    logic [31:0] insn = ins.current.insn;
    logic [11:0] imm  = insn[5] ? {insn[31:25], insn[11:7]} : insn[31:20];  // STORE and STORE-FP: S-type
    logic [63:0] addr = ins.current.rs1_val + {{52{imm[11]}}, imm};
    if (zimt_checked_access(ins) >= 5'd20) return 1'b0;
    return ({1'b0, addr[3:0]} + (5'd1 << insn[13:12]) - 5'd1) > 5'd15;
endfunction

// Exception that the instruction raised: {2'b01, exception code} from the cause CSR of the mode that took the trap
// (VS-mode, S-mode or M-mode), 0 without a trap, and 8'hff for an interrupt or an exception code above 63
function automatic logic [7:0] zimt_exception(ins_t ins);
    logic [11:0]     cause_csr;
    logic [XLEN-1:0] cause;
    if (!ins.current.trap) return 8'h00;
    if (ins.current.csr_wb[CSR_VSCAUSE])     cause_csr = CSR_VSCAUSE;
    else if (ins.current.csr_wb[CSR_SCAUSE]) cause_csr = CSR_SCAUSE;
    else                                     cause_csr = CSR_MCAUSE;
    cause = get_csr_val(ins.hart, ins.issue, `SAMPLE_AFTER, cause_csr);
    if (cause[XLEN-1] || (cause[XLEN-2:0] > 63)) return 8'hff;
    return {2'b01, cause[5:0]};
endfunction

// {mstatus.MPRV, mstatus.MPV, mstatus.MPP} before the instruction
function automatic logic [3:0] zimt_mprv_mpp(ins_t ins);
    logic [XLEN-1:0] mstatus = get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, CSR_MSTATUS);
    return {mstatus[17], mstatus[39], mstatus[12:11]};
endfunction

// The compressed loads and stores with sp as the base register: 1 c.lwsp, 2 c.ldsp, 3 c.swsp, 4 c.sdsp, 5 c.fldsp,
// 6 c.fsdsp; 0 for any other instruction
function automatic logic [2:0] zimt_sp_compressed(ins_t ins);
    logic [31:0] insn = ins.current.insn;
    if (insn ==? C_LWSP)  return 3'd1;
    if (insn ==? C_LDSP)  return 3'd2;
    if (insn ==? C_SWSP)  return 3'd3;
    if (insn ==? C_SDSP)  return 3'd4;
    if (insn ==? C_FLDSP) return 3'd5;
    if (insn ==? C_FSDSP) return 3'd6;
    return 3'd0;
endfunction

// The accesses that implicit tag checks do not cover (cp_unchecked_access): 1 lr.d, 2 sc.d, 3 amoadd.d, 4 cbo.clean,
// 5 cbo.flush, 6 cbo.zero, 7 hlv.d, 8 hsv.d, 9 vse64.v, 10 masked vse64.v, 11 vsse64.v, 12 vsuxei64.v, 13 vle64.v,
// 14 vlse64.v, 15 vluxei64.v; 0 for any other instruction
function automatic logic [3:0] zimt_unchecked_access(ins_t ins);
    logic [31:0] insn = ins.current.insn;
    if (insn ==? LR_D)       return 4'd1;
    if (insn ==? SC_D)       return 4'd2;
    if (insn ==? AMOADD_D)   return 4'd3;
    if (insn ==? CBO_CLEAN)  return 4'd4;
    if (insn ==? CBO_FLUSH)  return 4'd5;
    if (insn ==? CBO_ZERO)   return 4'd6;
    if (insn ==? HLV_D)      return 4'd7;
    if (insn ==? HSV_D)      return 4'd8;
    if (insn ==? VSE64_V)    return insn[25] ? 4'd9 : 4'd10;
    if (insn ==? VSSE64_V)   return 4'd11;
    if (insn ==? VSUXEI64_V) return 4'd12;
    if (insn ==? VLE64_V)    return 4'd13;
    if (insn ==? VLSE64_V)   return 4'd14;
    if (insn ==? VLUXEI64_V) return 4'd15;
    return 4'd0;
endfunction

// The tests of the accesses that implicit tag checks do not cover need at least one of their extensions: LR/SC or AMOs
// in all modes, and also CMOs, H or V in M-mode
`ifdef ZAAMO_SUPPORTED
    `define ZIMT_UNCHECKED_ACCESS
`elsif ZALRSC_SUPPORTED
    `define ZIMT_UNCHECKED_ACCESS
`endif
`ifdef ZIMT_UNCHECKED_ACCESS
    `define ZIMT_UNCHECKED_ACCESS_M
`elsif ZICBOM_SUPPORTED
    `define ZIMT_UNCHECKED_ACCESS_M
`elsif ZICBOZ_SUPPORTED
    `define ZIMT_UNCHECKED_ACCESS_M
`elsif H_SUPPORTED
    `define ZIMT_UNCHECKED_ACCESS_M
`elsif V_SUPPORTED
    `define ZIMT_UNCHECKED_ACCESS_M
`endif

// MT_MODE of S-mode (menvcfg, bits 3:2) and of M-mode (mseccfg, bits 1:0) before the instruction
function automatic logic [3:0] zimt_mprv_mt(ins_t ins);
    return {2'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, CSR_MENVCFG) >> 34),
            2'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, CSR_MSECCFG) >> 34)};
endfunction

// The instruction right before a load or store: 1 a byte store with sp as the base register (the tests' store of a
// tag byte), 2 settag; 0 otherwise
function automatic logic [1:0] zimt_order_prev(ins_t ins);
    logic [31:0] insn = ins.prev.insn;
    if ((insn ==? SB) && (insn[19:15] == 5'd2)) return 2'd1;
    if ((insn ==? MOP_RR_0) && !insn[24] && (insn[11:7] == 5'd0) && (insn[19:15] != 5'd0)) return 2'd2;
    return 2'd0;
endfunction

// MODE (bits 63:60) of satp, vsatp or hgatp before the instruction
function automatic logic [3:0] zimt_atp_mode(ins_t ins, logic [11:0] csr);
    return 4'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, csr) >> 60);
endfunction

// The access fault of a load or store of zimt_checked_access: 1 a load access fault of a load, 2 a load access fault of
// a store (its tag load faults), 3 a store/AMO access fault of a store; 0 otherwise
function automatic logic [1:0] zimt_checked_fault(ins_t ins);
    logic [4:0] kind = zimt_checked_access(ins);
    logic [7:0] exc  = zimt_exception(ins);
    if (kind == 5'd31) return 2'd0;
    if (exc == 8'h45)  return zimt_checked_store(kind) ? 2'd2 : 2'd1;
    if (exc == 8'h47)  return 2'd3;
    return 2'd0;
endfunction

// The S-mode settag tests raise store/AMO access faults in the faulting regions of RVMODEL_ACCESS_FAULT_ADDRESS_STORE
// and RVMODEL_ACCESS_FAULT_ADDRESS_LOAD (a page-table walk), and in Svpbmt IO memory
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_STORE
    `define ZIMT_SETTAG_S_ACCESS_FAULT
`elsif RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
    `define ZIMT_SETTAG_S_ACCESS_FAULT
`elsif SVPBMT_SUPPORTED
    `define ZIMT_SETTAG_S_ACCESS_FAULT
`endif

// Pointer tag of a pointer: its top width bits (4 or 7)
function automatic logic [6:0] zimt_pointer_tag(logic [63:0] ptr, int unsigned width);
    return 7'(ptr >> (64 - width));
endfunction

// addtag: whether the tag of rs1 plus imm4 wraps around the pointer tag width of the mode
function automatic bit zimt_addtag_wraps(ins_t ins);
    int unsigned width = (zimt_mt_mode(ins) == 2'b11) ? 7 : 4;
    return (int'(zimt_pointer_tag(ins.current.rs1_val, width)) + int'(ins.current.insn[23:20])) >= (1 << width);
endfunction

// Active tag generation exclusion mask {high CSR, low CSR} of the mode the instruction executes in:
// mmtagexclude (M), menvmtagexclude (S/HS), henvmtagexclude (VS) or senvmtagexclude (U and VU)
function automatic logic [127:0] zimt_exclusion_mask(ins_t ins);
    logic [11:0] low;
    case ({ins.prev.mode_virt, ins.prev.mode})
        3'b011:  low = 12'h7C0;
        3'b001:  low = 12'h7C2;
        3'b101:  low = 12'h6C0;
        default: low = 12'h5C0;
    endcase
    return {64'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, low + 12'h1)),
            64'(get_csr_val(ins.hart, ins.issue, `SAMPLE_BEFORE, low))};
endfunction

// Number of tags that the active exclusion mask permits, with the pointer tag width of the mode
function automatic int zimt_permitted_tags(ins_t ins);
    logic [127:0] mask = zimt_exclusion_mask(ins);
    return (zimt_mt_mode(ins) == 2'b11) ? $countones(~mask) : $countones(~mask[15:0]);
endfunction

// MT_MODE field of a value of the CSR that the instruction accesses: VUMT_MODE (bits 51:50) of hstatus,
// MT_MODE (bits 35:34) of mseccfg, menvcfg, senvcfg and henvcfg
function automatic logic [1:0] zimt_mt_field(logic [63:0] value, ins_t ins);
    return 2'(value >> ((ins.current.insn[31:20] == CSR_HSTATUS) ? 50 : 34));
endfunction

// Sm tests are not part of a certificate without Sm (EXCLUDE_SM), so neither is their covergroup
`ifndef EXCLUDE_SM
covergroup Zimt_Sm_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Zimt_coverpoints.svh"

    // Memory tagging disabled (M-mode, mseccfg.MT_MODE = 00)
    cp_gentag_mt_disabled:        cross priv_mode_m, mt_disabled, gentag_rd;
    cp_addtag_mt_disabled_imm:    cross priv_mode_m, mt_disabled, addtag_imm;
    cp_addtag_mt_disabled_rd:     cross priv_mode_m, mt_disabled, addtag_rd;
    cp_addtag_mt_disabled_rs1:    cross priv_mode_m, mt_disabled, addtag_rs1;
    cp_addtag_mt_disabled_rd_rs1: cross priv_mode_m, mt_disabled, addtag_rd_rs1;
    cp_checktag_mt_disabled_imm:  cross priv_mode_m, mt_disabled, checktag_imm;
    cp_checktag_mt_disabled_rs1:  cross priv_mode_m, mt_disabled, checktag_rs1;
    cp_settag_mt_disabled_imm:    cross priv_mode_m, mt_disabled, settag_imm;
    cp_settag_mt_disabled_rs1:    cross priv_mode_m, mt_disabled, settag_rs1;
    cp_mop_rr_not_zimt:           cross priv_mode_m, mt_disabled, mop_rr_not_zimt;

    // CSRs written in M-mode: menvcfg exists only with U-mode, and menvmtagexclude and medeleg only with S-mode
    mt_mode_csr_m: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mseccfg = {CSR_MSECCFG};
`ifdef U_SUPPORTED
        bins menvcfg = {CSR_MENVCFG};
`endif
    }
    mtagexclude0_csr_m: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mmtagexclude0    = {12'h7C0};
`ifdef S_SUPPORTED
        bins menvmtagexclude0 = {12'h7C2};
`endif
    }
    mtagexclude1_csr_m: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mmtagexclude1    = {12'h7C1};
`ifdef S_SUPPORTED
        bins menvmtagexclude1 = {12'h7C3};
`endif
    }
`ifdef S_SUPPORTED
    medeleg: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins medeleg = {CSR_MEDELEG};
    }
`endif
    mcause: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins mcause = {CSR_MCAUSE};
    }
    cp_mtagexclude_reset:  cross priv_mode_m, csrr, mtagexclude_csr;
    cp_mt_mode_warl:       cross priv_mode_m, csrrw, mt_mode_csr_m, mt_mode_before, mt_mode_written;
    cp_mtagexclude0_warl:  cross priv_mode_m, csrrw, mtagexclude0_csr_m, mtagexclude0_written;
    cp_mtagexclude1_write: cross priv_mode_m, csrrw, mtagexclude1_csr_m, mtagexclude1_written;
`ifdef S_SUPPORTED
    cp_swcheck_deleg:      cross priv_mode_m, csrs_csrc, medeleg, swcheck_bit;
`endif
    cp_swcheck_cause:      cross priv_mode_m, csrrw, mcause, swcheck_cause;

    // Memory tagging enabled (mseccfg.MT_MODE = 10, or 11 with 7-bit tags)
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
    // gentag with 4-bit tags, with the exclusion mask bits above 15, which it ignores, all clear or not. Only with
    // 7-bit tags must a hart keep those bits.
    mask_high_clear: coverpoint (zimt_exclusion_mask(ins)[127:16] == '0) iff (zimt_is_gentag(ins)) {
        type_option.weight = 0;
        bins clear     = {1'b1};
        bins not_clear = {1'b0};
    }
    cp_gentag_mt_tag4_tag:         cross priv_mode_m, mt_tag4, gentag_tag4, mask_high_clear;
`else
    cp_gentag_mt_tag4_tag:         cross priv_mode_m, mt_tag4, gentag_tag4;
`endif
    cp_gentag_mt_several:          cross priv_mode_m, mt_enabled, gentag_several;
    cp_gentag_mt_tag4:             cross priv_mode_m, mt_tag4, gentag_rd;
    cp_addtag_mt_tag4_imm:         cross priv_mode_m, mt_tag4, addtag_imm;
    cp_addtag_mt_tag4_rd:          cross priv_mode_m, mt_tag4, addtag_rd;
    cp_addtag_mt_tag4_rs1:         cross priv_mode_m, mt_tag4, addtag_rs1;
    cp_addtag_mt_tag4_rd_rs1:      cross priv_mode_m, mt_tag4, addtag_rd_rs1;
    cp_addtag_mt_enabled:          cross priv_mode_m, mt_enabled, addtag_wrap;
    cp_mop_rr_not_zimt_mt_tag4:    cross priv_mode_m, mt_tag4, mop_rr_not_zimt;
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
    cp_gentag_mt_tag7_tag:         cross priv_mode_m, mt_tag7, gentag_tag7_low;
    cp_gentag_mt_tag7_high:        cross priv_mode_m, mt_tag7, gentag_tag7_high;
    cp_gentag_mt_tag7:             cross priv_mode_m, mt_tag7, gentag_rd;
    cp_addtag_mt_tag7_imm:         cross priv_mode_m, mt_tag7, addtag_imm;
    cp_addtag_mt_tag7_rd:          cross priv_mode_m, mt_tag7, addtag_rd;
    cp_addtag_mt_tag7_rs1:         cross priv_mode_m, mt_tag7, addtag_rs1;
    cp_addtag_mt_tag7_rd_rs1:      cross priv_mode_m, mt_tag7, addtag_rd_rs1;
    cp_mop_rr_not_zimt_mt_tag7:    cross priv_mode_m, mt_tag7, mop_rr_not_zimt;
`endif
    // settag with the tag table mvitt and pointer masking (mseccfg.PMM)
`ifdef SMVATAG_SUPPORTED
`ifdef SMMPM_SUPPORTED
    cp_settag_mt_tag4_chunks:      cross priv_mode_m, mt_tag4, settag_chunk4, settag_imm;
    cp_settag_mt_tag4_rs1:         cross priv_mode_m, mt_tag4, settag_rs1;
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
    cp_settag_mt_tag7_chunks:      cross priv_mode_m, mt_tag7, settag_chunk7, settag_imm;
`endif
    cp_settag_addr_msb:            cross priv_mode_m, mt_enabled, settag_addr_msb;
    // MPRV with MPP = S, which needs S-mode pointer masking (menvcfg.PMM) and tag table (svitts, which settag ignores)
`ifdef S_SUPPORTED
`ifdef SMNPM_SUPPORTED
`ifdef SVATAG_SUPPORTED
    cp_settag_mprv:                cross priv_mode_m, mt_enabled, settag_mprv_s;
`endif
`endif
`endif
    // checktag and the implicit tag checks of loads and stores, which raise no exception with memory tagging enabled
    // in M-mode, where its trap handler runs: checktag of chunks with the matching tags, between chunks with a
    // mismatching one, and each kind of load and store
    cp_checktag_mt_tag4_chunks:    cross priv_mode_m, mt_tag4, checktag_chunk4, checktag_imm;
`ifdef UDB_ZIMT_POINTER_TAG_WIDTH_7
    cp_checktag_mt_tag7_chunks:    cross priv_mode_m, mt_tag7, checktag_chunk7, checktag_imm;
`endif
    cp_checked_access:             cross priv_mode_m, mt_enabled, checked_access;
`ifdef UDB_MISALIGNED_LDST
    cp_checked_two_chunks:         cross priv_mode_m, mt_enabled, checked_load_store, checked_two_chunks;
`endif
    cp_checked_sp:                 cross priv_mode_m, mt_enabled, checked_load_store, checked_sp_base;
    cp_checked_order:              cross priv_mode_m, mt_enabled, checked_load_store, checked_order;
`ifdef ZCA_SUPPORTED
    cp_checked_sp_compressed:      cross priv_mode_m, mt_enabled, checked_sp_compressed;
`endif
`ifdef ZIMT_UNCHECKED_ACCESS_M
    cp_unchecked_access:           cross priv_mode_m, mt_enabled, unchecked_access_m;
`endif
    cp_checktag_sp:                cross priv_mode_m, mt_enabled, checktag_sp;
    // MPRV with MPP = S: loads and stores are checked with S-mode's MT_MODE and tag table, checktag with M-mode's
`ifdef S_SUPPORTED
`ifdef SMNPM_SUPPORTED
`ifdef SVATAG_SUPPORTED
    cp_checked_mprv:               cross priv_mode_m, checked_mprv_s, mprv_s_mt, checked_load_store, checked_result;
    cp_checked_mprv_m_mt:          cross priv_mode_m, checked_mprv_s, mprv_m_mt, checked_load_store;
    cp_checktag_mprv:              cross priv_mode_m, checktag_mprv_s, mprv_mt;
    cp_checktag_mprv_m_pmm:        cross priv_mode_m, checktag_mprv_s, mprv_m_mt, m_pmm_off;
`endif
`endif
`endif
    // MPRV with MPV = 1: loads and stores are checked with VS-mode's or VU-mode's MT_MODE and tag table
`ifdef H_SUPPORTED
`ifdef SSNPM_SUPPORTED
`ifdef SVATAG_SUPPORTED
    cp_checked_mprv_v:             cross priv_mode_m, checked_mprv_v, checked_load_store, checked_result;
`endif
`endif
`endif
`endif
`endif

endgroup
`endif

`ifdef S_SUPPORTED
covergroup Zimt_S_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Zimt_coverpoints.svh"

    // Memory tagging disabled (S-mode, menvcfg.MT_MODE = 00)
    cp_gentag_mt_disabled:        cross priv_mode_s, mt_disabled, gentag_rd;
    cp_addtag_mt_disabled_imm:    cross priv_mode_s, mt_disabled, addtag_imm;
    cp_addtag_mt_disabled_rd:     cross priv_mode_s, mt_disabled, addtag_rd;
    cp_addtag_mt_disabled_rs1:    cross priv_mode_s, mt_disabled, addtag_rs1;
    cp_addtag_mt_disabled_rd_rs1: cross priv_mode_s, mt_disabled, addtag_rd_rs1;
    cp_checktag_mt_disabled_imm:  cross priv_mode_s, mt_disabled, checktag_imm;
    cp_checktag_mt_disabled_rs1:  cross priv_mode_s, mt_disabled, checktag_rs1;
    cp_settag_mt_disabled_imm:    cross priv_mode_s, mt_disabled, settag_imm;
    cp_settag_mt_disabled_rs1:    cross priv_mode_s, mt_disabled, settag_rs1;
    cp_mop_rr_not_zimt:           cross priv_mode_s, mt_disabled, mop_rr_not_zimt;

    // CSRs written in S-mode, and the access to the exclusion mask CSRs from S-mode
    senvcfg: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins senvcfg = {CSR_SENVCFG};
    }
    senvmtagexclude0: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins senvmtagexclude0 = {12'h5C0};
    }
    senvmtagexclude1: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins senvmtagexclude1 = {12'h5C1};
    }
    scause: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins scause = {CSR_SCAUSE};
    }
    cp_mt_mode_warl:       cross priv_mode_s, csrrw, senvcfg, mt_mode_before, mt_mode_written;
    cp_mtagexclude0_warl:  cross priv_mode_s, csrrw, senvmtagexclude0, mtagexclude0_written;
    cp_mtagexclude1_write: cross priv_mode_s, csrrw, senvmtagexclude1, mtagexclude1_written;
    cp_swcheck_cause:      cross priv_mode_s, csrrw, scause, swcheck_cause;
    cp_csr_access:         cross priv_mode_s, csr_access_op, mtagexclude_csr;

    // Memory tagging enabled (menvcfg.MT_MODE = 10, or 11 with 7-bit tags)
    cp_gentag_mt_enabled:  cross priv_mode_s, mt_enabled, gentag;
    cp_addtag_mt_enabled:  cross priv_mode_s, mt_enabled, addtag_wrap;
    // settag with Sv39 translation, the tag table svitts and pointer masking (menvcfg.PMM)
`ifdef SVATAG_SUPPORTED
`ifdef SMNPM_SUPPORTED
`ifdef SV39_SUPPORTED
    cp_settag_mt_enabled:  cross priv_mode_s, mt_enabled, settag_exception;
    cp_settag_addr_msb:    cross priv_mode_s, mt_enabled, settag_addr_msb;
    // checktag with Sv39 translation, and loads and stores, which are not tag checked with address translation
    cp_checktag_mt_enabled: cross priv_mode_s, mt_enabled, checktag_exception;
    cp_checktag_addr_msb:   cross priv_mode_s, mt_enabled, checktag_addr_msb;
    cp_checked_translated:  cross priv_mode_s, mt_enabled, checked_load_store, checked_satp_translated;
    // checktag and the implicit tag checks of loads and stores with Bare translation (satp), which raise no
    // exception, as in M-mode: the M-mode trap handler reads the trapping instruction with MPRV and MPP = S
    cp_checked_access:      cross priv_mode_s, mt_enabled, checked_satp_bare, checked_access;
`ifdef UDB_MISALIGNED_LDST
    cp_checked_two_chunks:  cross priv_mode_s, mt_enabled, checked_satp_bare, checked_load_store, checked_two_chunks;
`endif
    cp_checked_sp:          cross priv_mode_s, mt_enabled, checked_satp_bare, checked_load_store, checked_sp_base;
`ifdef ZCA_SUPPORTED
    cp_checked_sp_compressed: cross priv_mode_s, mt_enabled, checked_sp_compressed;
`endif
    cp_checked_order:       cross priv_mode_s, mt_enabled, checked_satp_bare, checked_load_store, checked_order;
`ifdef ZIMT_UNCHECKED_ACCESS
    cp_unchecked_access:    cross priv_mode_s, mt_enabled, unchecked_access;
`endif
    cp_checktag_sp:         cross priv_mode_s, mt_enabled, checktag_sp;
`endif
`endif
`endif

endgroup
`endif

`ifdef U_SUPPORTED
covergroup Zimt_U_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Zimt_coverpoints.svh"

    // Memory tagging disabled (U-mode, senvcfg.MT_MODE = 00)
    cp_gentag_mt_disabled:        cross priv_mode_u, mt_disabled, gentag_rd;
    cp_addtag_mt_disabled_imm:    cross priv_mode_u, mt_disabled, addtag_imm;
    cp_addtag_mt_disabled_rd:     cross priv_mode_u, mt_disabled, addtag_rd;
    cp_addtag_mt_disabled_rs1:    cross priv_mode_u, mt_disabled, addtag_rs1;
    cp_addtag_mt_disabled_rd_rs1: cross priv_mode_u, mt_disabled, addtag_rd_rs1;
    cp_checktag_mt_disabled_imm:  cross priv_mode_u, mt_disabled, checktag_imm;
    cp_checktag_mt_disabled_rs1:  cross priv_mode_u, mt_disabled, checktag_rs1;
    cp_settag_mt_disabled_imm:    cross priv_mode_u, mt_disabled, settag_imm;
    cp_settag_mt_disabled_rs1:    cross priv_mode_u, mt_disabled, settag_rs1;
    cp_mop_rr_not_zimt:           cross priv_mode_u, mt_disabled, mop_rr_not_zimt;

    // Access to the exclusion mask CSRs from U-mode
    cp_csr_access:         cross priv_mode_u, csr_access_op, mtagexclude_csr;

    // Memory tagging enabled (senvcfg.MT_MODE = 10, or 11 with 7-bit tags), which needs S-mode
`ifdef S_SUPPORTED
    cp_gentag_mt_enabled:  cross priv_mode_u, mt_enabled, gentag;
    cp_addtag_mt_enabled:  cross priv_mode_u, mt_enabled, addtag_wrap;
    // settag with the tag table svittu and pointer masking (senvcfg.PMM)
`ifdef SVATAG_SUPPORTED
`ifdef SSNPM_SUPPORTED
    cp_settag_mt_enabled:  cross priv_mode_u, mt_enabled, settag_bare_exception;
    // checktag and the implicit tag checks of loads and stores, without address translation
    cp_checktag_mt_enabled: cross priv_mode_u, mt_enabled, checktag_bare_exception;
    cp_checked_access:      cross priv_mode_u, mt_enabled, checked_access, checked_result;
    cp_checked_two_chunks:  cross priv_mode_u, mt_enabled, checked_load_store, checked_two_chunks, checked_two_chunk_result;
    cp_checked_sp:          cross priv_mode_u, mt_enabled, checked_load_store, checked_sp_base;
    cp_checked_order:       cross priv_mode_u, mt_enabled, checked_load_store, checked_order, checked_result;
`ifdef ZCA_SUPPORTED
    cp_checked_sp_compressed: cross priv_mode_u, mt_enabled, checked_sp_compressed;
`endif
`ifdef ZIMT_UNCHECKED_ACCESS
    cp_unchecked_access:    cross priv_mode_u, mt_enabled, unchecked_access;
`endif
    cp_checktag_sp:         cross priv_mode_u, mt_enabled, checktag_sp, checktag_result;
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
    cp_checked_fault:       cross priv_mode_u, mt_enabled, checked_fault;
`endif
`endif
`endif
`endif

endgroup
`endif

`ifdef H_SUPPORTED
covergroup Zimt_H_cg with function sample(ins_t ins);
    option.per_instance = 0;
    `include "general/RISCV_coverage_standard_coverpoints.svh"
    `include "general/Zimt_coverpoints.svh"

    // Memory tagging disabled (VS-mode with henvcfg.MT_MODE = 00, VU-mode with senvcfg.MT_MODE = 00)
    cp_gentag_mt_disabled:        cross priv_mode_vs_vu, mt_disabled, gentag_rd;
    cp_addtag_mt_disabled_imm:    cross priv_mode_vs_vu, mt_disabled, addtag_imm;
    cp_addtag_mt_disabled_rd:     cross priv_mode_vs_vu, mt_disabled, addtag_rd;
    cp_addtag_mt_disabled_rs1:    cross priv_mode_vs_vu, mt_disabled, addtag_rs1;
    cp_addtag_mt_disabled_rd_rs1: cross priv_mode_vs_vu, mt_disabled, addtag_rd_rs1;
    cp_checktag_mt_disabled_imm:  cross priv_mode_vs_vu, mt_disabled, checktag_imm;
    cp_checktag_mt_disabled_rs1:  cross priv_mode_vs_vu, mt_disabled, checktag_rs1;
    cp_settag_mt_disabled_imm:    cross priv_mode_vs_vu, mt_disabled, settag_imm;
    cp_settag_mt_disabled_rs1:    cross priv_mode_vs_vu, mt_disabled, settag_rs1;
    cp_mop_rr_not_zimt:           cross priv_mode_vs_vu, mt_disabled, mop_rr_not_zimt;

    // CSRs written in HS-mode, and the access to the exclusion mask CSRs from VS-mode and VU-mode
    henvcfg: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins henvcfg = {CSR_HENVCFG};
    }
    hstatus: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins hstatus = {CSR_HSTATUS};
    }
    henvmtagexclude0: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins henvmtagexclude0 = {12'h6C0};
    }
    henvmtagexclude1: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins henvmtagexclude1 = {12'h6C1};
    }
    hedeleg: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins hedeleg = {CSR_HEDELEG};
    }
    vscause: coverpoint ins.current.insn[31:20] {
        type_option.weight = 0;
        bins vscause = {CSR_VSCAUSE};
    }
    cp_mt_mode_warl:       cross priv_mode_hs, csrrw, henvcfg, mt_mode_before, mt_mode_written;
    cp_vumt_mode_warl:     cross priv_mode_hs, csrrw, hstatus, mt_mode_before, mt_mode_written;
    cp_mtagexclude0_warl:  cross priv_mode_hs, csrrw, henvmtagexclude0, mtagexclude0_written;
    cp_mtagexclude1_write: cross priv_mode_hs, csrrw, henvmtagexclude1, mtagexclude1_written;
    cp_swcheck_deleg:      cross priv_mode_hs, csrs_csrc, hedeleg, swcheck_bit;
    cp_swcheck_cause:      cross priv_mode_hs, csrrw, vscause, swcheck_cause;
    cp_csr_access:         cross priv_mode_vs_vu, csr_access_op, mtagexclude_csr;

    // Memory tagging enabled (VS-mode: henvcfg.MT_MODE, VU-mode: senvcfg.MT_MODE = 10, or 11 with 7-bit tags)
    cp_gentag_mt_enabled:  cross priv_mode_vs_vu, mt_enabled, gentag;
    cp_addtag_mt_enabled:  cross priv_mode_vs_vu, mt_enabled, addtag_wrap;
    // settag with the tag tables vsvitts (VS-mode) and vsvittu (VU-mode), and pointer masking (henvcfg.PMM,
    // senvcfg.PMM)
`ifdef SVATAG_SUPPORTED
`ifdef SSNPM_SUPPORTED
    cp_settag_mt_enabled:  cross priv_mode_vs_vu, mt_enabled, settag;
    // VS-mode with guest translation: two-stage (vsatp = Sv39, hgatp = Sv39x4) or the G stage only
`ifdef SV39_SUPPORTED
    cp_settag_two_stage:   cross priv_mode_vs, mt_enabled, settag_two_stage_exception;
    cp_settag_g_stage:     cross priv_mode_vs, mt_enabled, settag_g_stage_exception;
`endif
    // checktag and the implicit tag checks of integer loads and stores, with Bare vsatp and hgatp
    cp_checktag_mt_enabled: cross priv_mode_vs_vu, mt_enabled, checktag_bare_exception;
    cp_checked_access:      cross priv_mode_vs_vu, mt_enabled, checked_int_access, checked_result;
    cp_checked_two_chunks:  cross priv_mode_vs_vu, mt_enabled, checked_load_store, checked_two_chunks, checked_two_chunk_result;
    cp_checked_sp:          cross priv_mode_vs_vu, mt_enabled, checked_load_store, checked_sp_base;
    cp_checked_order:       cross priv_mode_vs_vu, mt_enabled, checked_load_store, checked_order, checked_result;
`ifdef ZCA_SUPPORTED
    cp_checked_sp_compressed: cross priv_mode_vs_vu, mt_enabled, checked_sp_int_compressed;
`endif
`ifdef ZIMT_UNCHECKED_ACCESS
    cp_unchecked_access:    cross priv_mode_vs_vu, mt_enabled, unchecked_access;
`endif
    cp_checktag_sp:         cross priv_mode_vs_vu, mt_enabled, checktag_sp, checktag_result;
    cp_swcheck_to_vs:       cross priv_mode_vu, mt_enabled, swcheck_to_vs;
`ifdef RVMODEL_ACCESS_FAULT_ADDRESS_LOAD
    cp_checked_fault:       cross priv_mode_vs_vu, mt_enabled, checked_tag_fault;
`endif
    // checktag in VS-mode with guest translation; loads and stores, which are not tag checked with two-stage
    // translation (first-stage paging), and are with the G stage only
`ifdef SV39_SUPPORTED
    cp_checktag_two_stage:  cross priv_mode_vs, mt_enabled, checktag_two_stage_exception;
    cp_checktag_g_stage:    cross priv_mode_vs, mt_enabled, checktag_g_stage_exception;
    cp_checked_translated:  cross priv_mode_vs, mt_enabled, checked_load_store, checked_vsatp_translated;
    cp_checked_g_stage:     cross priv_mode_vs, mt_enabled, checked_load_store, checked_g_stage_result;
`endif
`endif
`endif

endgroup
`endif

function void zimt_sample(int hart, int issue, ins_t ins);
    `ifndef EXCLUDE_SM
        Zimt_Sm_cg.sample(ins);
    `endif
    `ifdef S_SUPPORTED
        Zimt_S_cg.sample(ins);
    `endif
    `ifdef U_SUPPORTED
        Zimt_U_cg.sample(ins);
    `endif
    `ifdef H_SUPPORTED
        Zimt_H_cg.sample(ins);
    `endif
endfunction
