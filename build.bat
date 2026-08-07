@ECHO OFF
REM python .\vgm_converter.py '.\13 - Bad' test.bin
asm6f_32.exe -m vgm_player.asm vgm_player.nes
TIMEOUT /T 15
EXIT /B