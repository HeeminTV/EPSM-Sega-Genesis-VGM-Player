		HEX 4E 45 53 1A 00 00 28 0B 00 01 00 07 00 04 00 01
		
; .base 0
		incbin "test.bin"
; .pad 2097152,$FF

; .base 0
; .pad 1024*1024,$FF

; .base 0
; .pad 1008*1024,$FF

; ======================================================================================================

enum 0
		data_ptr: .dsb 3
		wait_msb: .dsb 1
		zp07byte: .dsb 1
		msbprev: .dsb 1
ende

; ======================================================================================================

.base $C000
chr:	incbin "chr.chr"
nam:	incbin "nam.nam"
pal:	.BYTE $0F, $00, $10, $20
		.BYTE $0F, $0F, $0F, $0F
		.BYTE $0F, $0F, $0F, $0F
		.BYTE $0F, $0F, $0F, $0F
		
scroll_x = -40
scroll_y = 240-56
scroll_y_msb = 1

RESET:	LDX #0
		STX $2000
		SEI
		
		BIT $2002
@poll1:	BIT $2002
		BPL @poll1
@poll2:	BIT $2002
		BPL @poll2
		STX $2000
		
		LDA #<chr
		STA data_ptr+0
		LDA #>chr
		STA data_ptr+1
		LDY #0
		STY $2006
		STY $2006
		LDX #16
@chrcpy:LDA (data_ptr),Y
		INY
		STA $2007
		BNE @chrcpy
		INC data_ptr+1
		DEX
		BNE @chrcpy
		
		LDA #<nam
		STA data_ptr+0
		LDA #>nam
		STA data_ptr+1
		LDA #$20
		STA $2006
		STY $2006
		LDX #4
@namcpy:LDA (data_ptr),Y
		INY
		STA $2007
		BNE @namcpy
		INC data_ptr+1
		DEX
		BNE @namcpy
		
		LDA #$24
		STA $2006
		STY $2006
@clrntb:STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		STX $2007
		INY
		BNE @clrntb
		
@poll3:	BIT $2002
		BPL @poll3
		
		DEX
		STX $2006
		INX
		STX $2006
@palcpy:LDA pal,X
		STA $2007
		INX
		CPX #16
		BCC @palcpy
		
		STY $2006
		STY $2006
		LDA #<scroll_x
		STA $2005
		LDA #<scroll_y
		STA $2005
		LDA #(((>scroll_x)&1)|((scroll_y_msb&1)<<1))
		STA $2000
		LDA #$0E
		STA $2001

		STY data_ptr+0
		STY data_ptr+2
		
		STY msbprev
	
		LDA #$29
		STA $401C
		LDA #$80
		STA $401D
		STA data_ptr+1
		LDA #$09
		STA $4015
		STA $400F
		LDA #$07
		STA zp07byte
		
		STY $8000
		
		JMP play_loop
		
; ======================================================================================================

MACRO INY_check
		INY
		BNE @nohinc
		INC data_ptr+1
		BIT data_ptr+1
		BVC @nohinc
		INC data_ptr+2
		PHA
		LDA data_ptr+2
		STA $8000
		LDA #$80
		STA data_ptr+1
		PLA
@nohinc:
ENDM

.align 256,$FF
		; 55 cycles per $00/$01 commands
		; 60 cycles per $02 command
		; 90 cycles per $03 command
		; 40 cycles per $05-$7F commands
		; $80-$FF = wait for `(param-128)*5+25` cycles
		
play_loop:
		LAX (data_ptr),Y		; 5
		BPL @regwrites
		INY_check				; 2+5
		NOP						; 2
		NOP						; 2
		NOP						; 2
@dloop:	DEX
		BMI @dloop
		BPL play_loop ; always

@regwrites:
		NOP						; 3+2
		NOP						; 2
		INY_check				; 5
		CMP #1					; 2
		BCC @ym1
		BEQ @ym2				; 2

		CMP #3					; 2+2
		BCC @noi_j
		BEQ @pul_j				; 2
		
		CMP #4					; 2+2
		BEQ @end_j

		STA $4011				; 2+4
		BNE play_loop ; always	; 3
		
@noi_j:	JMP @noi
@pul_j: JMP @pul
@end_j:	JMP @end
		
@ym1:	NOP
		LDA (data_ptr),Y
		INY_check
		STA $401C
		LDA (data_ptr),Y
		INY_check
		STA $401D
		JMP play_loop

@ym2:	LDA (data_ptr),Y
		INY_check
		STA $401E
		LDA (data_ptr),Y
		INY_check
		STA $401F
		JMP play_loop
		
@noi:	LAX (data_ptr),Y
		INY_check
		LDA lsr4ora30tbl,X
		STA $400C
		TXA
		AND #$0F
		STA $400E
		JMP play_loop
		
@pul:	
		; first byte : VVVV1PPP
		; second byte: PPPPPPPP
		LAX (data_ptr),Y		; 5
		INY_check				; 5
		
		AND zp07byte			; 3
		CMP msbprev				; 3
		BEQ @same

		STA msbprev				; 2+3
		STX $4003				; 4
		BNE @wrdone ; always	; 3

@same:	PHA						; 3+3
		PLA						; 4
		NOP						; 2

@wrdone:

		LDA lsr4ora30tbl,X		; 4
		STA $4000				; 4
		LDA (data_ptr),Y		; 5
		INY_check				; 5
		STA $4002				; 4
		NOP						; 2
		NOP						; 2
		JMP play_loop			; 3
		
@end:
		
.align 256,$FF
		i=0
lsr4ora30tbl:
REPT 256
		.BYTE (i>>4)|$30
		i=i+1
ENDR
		
.pad $FFFC,$FF
		.WORD RESET
		.WORD $FFFF