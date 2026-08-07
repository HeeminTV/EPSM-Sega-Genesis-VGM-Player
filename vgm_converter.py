import sys
import struct
import os

class VGMConverter:
    def __init__(self, in_file, out_file):
        self.in_file = in_file
        self.out_file = out_file
        
        # 딜레이 변환 설정
        # 1.79MHz / 5 cycles per loop = 357954.4 Hz
        self.delay_ratio = ((315000000/176)/5) / 44100
        self.error_acc = 0.0  # 오차 피드백 누산기

        self.delay_acc = 0
        
        self.dac_old = -1
        self.reg27_old = -1

        # 클럭 변환 설정 (SN76489 -> YM2608 SSG)
        self.sn_clock = 3579545
        self.ssg_clock = 2000000*0.95880675
        # 주기(Period) 계산 비례 상수
        self.ssg_freq_ratio = (self.ssg_clock / self.sn_clock) * 2

        # 상태 에뮬레이션
        self.sn_regs = [0] * 8  # 0,2,4: Tone, 1,3,5: Vol, 6: Noise Ctrl, 7: Noise Vol
        self.sn_latched_ch = 0
        self.sn_latched_type = 0
        for i in [1, 3, 5, 7]: self.sn_regs[i] = 15 # 초기 볼륨은 모두 0 (Silence)
        
        self.ssg_cache = [-1]*16 # SSG 중복 기록 방지용 캐시
        
        # PCM 데이터 관리
        self.pcm_data = bytearray()
        self.pcm_pointer = 0

        self.out_data = bytearray()

    def emit_cmd(self, *bytes_vals):
        """명령어를 출력 버퍼에 추가"""
        self.out_data.extend(bytes_vals)
        
    def write_ym(self, reg, val, a1):
        self.emit_cmd(int(a1)&0x01, int(reg)&0xFF, int(val)&0xFF)
        self.delay_acc+=55
        
    def handle_dacwrite(self, dacval):
        actual_dac_val = dacval>>1
        if actual_dac_val < 0x03:
            actual_dac_val = 0x03
            
        if actual_dac_val != self.dac_old:
            self.emit_cmd(actual_dac_val)
            self.dac_old = actual_dac_val
            self.delay_acc+=40

    def write_ssg(self, reg, val):
        """값이 변경되었을 때만 YM2608(0x00 포트)에 SSG 값 기록"""
        if self.ssg_cache[reg] != val:
            self.write_ym(reg, val, 0)
            self.ssg_cache[reg] = val

    # def write_ssg_freq(self, ssg_ch, period):
        # """12비트 SSG 주파수를 2개의 레지스터에 기록"""
        # fine = period & 0xFF
        # coarse = (period >> 8) & 0x0F
        # self.write_ssg(ssg_ch * 2, fine)
        # self.write_ssg(ssg_ch * 2 + 1, coarse)

    def handle_delay(self, samples):
        """샘플 수를 사이클로 변환 및 오차 피드백 처리"""
        if samples == 0:
            return

        # 1. 필요 틱(5cy) 계산 및 오차 누적
        exact_ticks = (samples * self.delay_ratio) + self.error_acc
        int_ticks = int(exact_ticks)
        self.error_acc = exact_ticks - int_ticks
        
        # 2. 명령어 실행으로 이미 소모한 틱을 차감
        ticks_to_wait = int_ticks - (self.delay_acc // 5)
        self.delay_acc = 0  # 누산기 초기화
        
        # 3. 기다려야 할 틱이 5틱(25 마스터 사이클) 미만이면
        # 0x80 커맨드의 최소 단위(5틱)조차 쓸 수 없으므로 다음번으로 이월합니다.
        if ticks_to_wait < 5:
            self.error_acc += ticks_to_wait
            return

        # 4. 5틱 이상 기다려야 한다면 루프를 돌며 쪼개서 기록
        while ticks_to_wait >= 5:
            # 한 번의 0x80~0xFF 커맨드로 최대로 기다릴 수 있는 틱은 132틱 (chunk=127일 때 127 + 5)
            wait_this_cmd = min(ticks_to_wait, 132)
            
            # chunk 값은 실제로 기다릴 틱에서 기본값 5를 뺀 값 (0 ~ 127)
            chunk = wait_this_cmd - 5
            low_byte = 0x80 | (chunk & 0x7F)
            self.emit_cmd(low_byte)
            
            # 처리한 틱만큼 전체 대기 틱에서 차감
            ticks_to_wait -= wait_this_cmd
            
        # 5. 루프를 다 돌고 남은 자투리 틱 (1~4틱)
        # 당장 기다릴 수 없으므로 다시 오차(error_acc)로 돌려보내어 다음 번에 마저 기다리게 합니다.
        if ticks_to_wait > 0:
            self.error_acc += ticks_to_wait

    def update_ssg(self):
        """SN76489 레지스터 상태를 읽어 AY-3-8910 레지스터로 에뮬레이션 출력"""
        
        # SN_TO_AY_VOLUME = [15, 14, 13, 12, 11, 11, 10,  9,  9,  8,  8,  7,  6,  6,  5,  0]
        SN_TO_AY_VOLUME = [15, 15, 14, 13, 12, 12, 11, 10, 10,  9,  9,  8,  7,  7,  6,  0]

        ay_vol_a = SN_TO_AY_VOLUME[self.sn_regs[1]]
        ay_vol_b = SN_TO_AY_VOLUME[self.sn_regs[3]]
        ay_vol_c_tone = SN_TO_AY_VOLUME[self.sn_regs[5]]
        noise_vol = SN_TO_AY_VOLUME[self.sn_regs[7]]

        freq_a = int(self.sn_regs[0] * self.ssg_freq_ratio)
        freq_b = int(self.sn_regs[2] * self.ssg_freq_ratio)
        freq_c = int(self.sn_regs[4] * self.ssg_freq_ratio)
        
        self.write_ssg(0, freq_a&0xFF)
        self.write_ssg(1, freq_a>>8)
        self.write_ssg(2, freq_b&0xFF)
        self.write_ssg(3, freq_b>>8)
        self.write_ssg(4, freq_c&0xFF)
        self.write_ssg(5, freq_c>>8)

        if noise_vol == 0: # 노이즈 볼륨이 0(무음)이면 사각파 3개 전부 활성화
            mixer = 0b00111000 # Tones(A,B,C) Enable(0), Noise(A,B,C) Disable(1)
            vol_c = ay_vol_c_tone
        else: # 노이즈 볼륨이 0이 아니면 채널 C를 노이즈 채널로 사용
            mixer = 0b00011100 # Tone(A,B) Enable, Tone(C) Disable(1), Noise(C) Enable(0)
            vol_c = noise_vol
            
            # SN76489 노이즈 속도를 SSG 노이즈 주파수(0~31)로 대략적 맵핑
            noise_ctrl = self.sn_regs[6] & 0x03
            if noise_ctrl == 0: ay_noise_freq = 0x04
            elif noise_ctrl == 1: ay_noise_freq = 0x08
            elif noise_ctrl == 2: ay_noise_freq = 0x10
            else: ay_noise_freq = max(1, (freq_c >> 4) & 0x1F) 
            self.write_ssg(6, ay_noise_freq)
            
            # disable channel completely when vol = 0 for PCM
        if freq_a < 4: mixer |= 0b00001001
        if freq_b < 4: mixer |= 0b00010010
        if (freq_c < 4) and (noise_vol == 0): mixer |= 0b00100100

        self.write_ssg(7, mixer)
        self.write_ssg(8, ay_vol_a)
        self.write_ssg(9, ay_vol_b)
        self.write_ssg(10, vol_c)

    def convert(self):
        with open(self.in_file, 'rb') as f:
            data = f.read()

        if data[:4] != b'Vgm ':
            print("Invalid")
            return

        # VGM 데이터 오프셋 추출
        data_offset = struct.unpack_from('<I', data, 0x34)[0]
        pos = 0x34 + data_offset if data_offset > 0 else 0x40

        # 메인 파싱 루프
        while pos < len(data):
            cmd = data[pos]
            pos += 1

            if cmd == 0x50: # SN76489 Write
                val = data[pos]; pos += 1
                if val & 0x80:
                    self.sn_latched_ch = (val >> 5) & 0x03
                    self.sn_latched_type = (val >> 4) & 0x01
                    idx = self.sn_latched_ch * 2 + self.sn_latched_type
                    if self.sn_latched_type == 1:
                        self.sn_regs[idx] = val & 0x0F
                    else:
                        self.sn_regs[idx] = (self.sn_regs[idx] & 0x3F0) | (val & 0x0F)
                else:
                    idx = self.sn_latched_ch * 2 + self.sn_latched_type
                    if self.sn_latched_type == 1:
                        self.sn_regs[idx] = val & 0x0F
                    else:
                        self.sn_regs[idx] = (self.sn_regs[idx] & 0x0F) | ((val & 0x3F) << 4)
                
                self.update_ssg()

            elif cmd == 0x52: # YM2612 Port 0 Write
                aa = data[pos]; dd = data[pos+1]; pos += 2

                if aa == 0x2A:
                    self.handle_dacwrite(dd)
                elif aa == 0x24 or aa == 0x25 or aa == 0x26 or aa == 0x29:
                    pass
                elif aa == 0x27:
                    if (dd&0xC0) != (self.reg27_old&0xC0):
                        self.write_ym(0x27, dd&0xC0, 0)
                        self.reg27_old = dd
                else:
                    self.write_ym(aa, dd, 0)

            elif cmd == 0x53: # YM2612 Port 1 Write
                aa = data[pos]; dd = data[pos+1]; pos += 2
                self.write_ym(aa, dd, 1)

            elif cmd == 0x61: # Wait n samples
                samples = struct.unpack_from('<H', data, pos)[0]
                pos += 2
                self.handle_delay(samples)

            elif cmd == 0x62: # Wait 735 samples
                self.handle_delay(735)

            elif cmd == 0x63: # Wait 882 samples
                self.handle_delay(882)

            elif 0x70 <= cmd <= 0x7F: # Wait n+1 samples
                self.handle_delay((cmd & 0x0F) + 1)

            elif 0x80 <= cmd <= 0x8F: # YM2612 PCM DAC write + Wait n samples
                n = cmd & 0x0F # 대기 샘플 수는 n+1이 아닌 n
                if self.pcm_pointer < len(self.pcm_data):
                    val = self.pcm_data[self.pcm_pointer]
                    self.pcm_pointer += 1
                    
                    # if val != self.reg2A_old:
                        # self.emit_cmd(0x02, val>>1)
                    self.handle_dacwrite(val)
                self.handle_delay(n)

            elif cmd == 0xE0: # Seek PCM data pointer
                self.pcm_pointer = struct.unpack_from('<I', data, pos)[0]
                pos += 4

            elif cmd == 0x67: # Data block
                if data[pos] == 0x66:
                    pos += 1
                    block_type = data[pos]; pos += 1
                    block_size = struct.unpack_from('<I', data, pos)[0]; pos += 4
                    if block_type == 0x00: # YM2612 PCM Data
                        self.pcm_data.extend(data[pos : pos+block_size])
                    pos += block_size

            elif cmd == 0x66: # End of sound data
                break

            # 알려진 타 칩셋/길이 스킵(예외 처리)
            elif cmd == 0x4F: pos += 1
            elif 0x51 <= cmd <= 0x5F: pos += 2
            elif 0x90 <= cmd <= 0x95: pos += 4
            else:
                pass # 지원되지 않는 기타 커맨드 스킵

        with open(self.out_file, 'wb') as f:
            padded_data = self.out_data.ljust((4096*1024)-(16*1024), b'\xFF')
            f.write(padded_data)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python vgm_converter.py <.vgm> <output.bin>")
        sys.exit(1)
        
    converter = VGMConverter(sys.argv[1], sys.argv[2])
    converter.convert()