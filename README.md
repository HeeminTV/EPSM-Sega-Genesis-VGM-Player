# EPSM Sega Genesis VGM Player

Sega Genesis VGM Player for [NES EPSM](https://www.nesdev.org/wiki/Expansion_Port_Sound_Module)

## Notable features

- SN76489 \-\> SSG conversion
- No clock drift
- PCM

## Notable missing features

- VGM looping

## Usage

1. Put [asm6f](https://github.com/freem/asm6f/releases/tag/v1.6_f03) into the same folder with source files.
2. Convert your [`.vgm`](https://vgmrips.net/packs/system/sega/mega-drive) file using [`vgm_converter.py`](https://github.com/HeeminTV/EPSM-Sega-Genesis-VGM-Player/blob/main/vgm_converter.py), with output namde of `test.bin`.
3. Build the ROM using [`build.bat`](https://github.com/HeeminTV/EPSM-Sega-Genesis-VGM-Player/blob/main/build.bat).