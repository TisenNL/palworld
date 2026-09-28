# Offline Maps Setup

Os mapas (Palpagos Islands e The World Tree) usam os tiles reais do paldb.cc,
baixados uma vez e servidos como arquivos estáticos — sem MapGenie, sem
servidor Python, sem dependência de internet em runtime.

## Setup inicial (primeira vez / atualização)

```bash
python tools/download_paldb_tiles.py
```

Esse script baixa a pirâmide de tiles CRS.Simple do paldb.cc (512px webp,
zoom 0-4, ~11 MB no total) para:

- `public/map-tiles/palpagos/z{0..4}/x{x}y{y}.webp`
- `public/map-tiles/world-tree/z{0..4}/x{x}y{y}.webp`

É resumível (tiles já baixados são pulados).

## Como funciona

- `src/domain/coordinates.ts` e `src/domain/worldTreeCoordinates.ts` implementam
  a projeção linear (CRS.Simple) do paldb.cc, calibrada a partir da própria
  configuração do site (bounds reais + fatores `perPixel`), então os
  marcadores (incluindo World Tree) ficam alinhados corretamente.
- `src/services/api.ts` (`mapTileUrl`/`mapTileUrlWt`) aponta direto para os
  arquivos estáticos em `public/map-tiles/`, sem passar pelo servidor Python.
- Como esses arquivos ficam em `public/`, o Vite os serve normalmente tanto em
  dev quanto em build — funciona 100% offline após o download.

## Legado

Os scripts `tools/download_map_tiles.py`, `tools/download_essential_tiles.py`
e o proxy MapGenie em `server/coord_tooltip.py` não são mais usados pelo mapa
(ficaram obsoletos com a migração para os tiles do paldb.cc).
