# Benchmarks — Mark in game

Scripts isolados para medir gargalos. **Não alteram** o fluxo de produção.

## Instrumentação do fluxo real

```bat
set PALWORLD_MARKER_TIMING=1
py -3 run.py
```

Cada Mark in game grava `.cache/timing/run-<timestamp>-<pid>.jsonl`.

Depois das 10 runs:

```bat
py -3 tools/bench_mark_in_game/aggregate_runs.py
```

Gera/atualiza `tools/bench_mark_in_game/report.md`.

## Protocolo das 10 runs (Parte B)

1. Reinicie o helper com `PALWORLD_MARKER_TIMING=1` (run **cold**).
2. Mapa aberto no Palworld, HUD de coordenadas visível.
3. **5 longe** (erro inicial > 100 u) e **5 perto** (< 30 u).
4. Anote se cada run foi cold/quente e a distância aproximada.
5. Rode `aggregate_runs.py`.

## Scripts (da raiz do repo)

| Script | Precisa do jogo? | Saída |
|--------|------------------|-------|
| `collect_env.py` | Não | `.cache/timing/env.json` |
| `bench_onnx_info.py` | Não | `.cache/timing/onnx_info.json` |
| `bench_capture.py` | ROI na tela | `.cache/timing/capture_bench.json` |
| `bench_ocr_profile.py` | Idealmente sim (ou `last-capture.png`) | `.cache/timing/ocr_profile.json` |
| `bench_hud_latency.py` | **Sim** | `.cache/timing/hud_latency.json` |
| `bench_physics.py` | **Sim** | `.cache/timing/physics.json` |
| `collect_ocr_crops.py` | **Sim** | `.cache/ocr-bench/` |
| `bench_fps_hud.py` | **Sim** | `.cache/timing/fps_hud.json` |
| `aggregate_runs.py` | Não | `report.md` |

### Capture: mss / dxcam (venv temporária, fora do deps do projeto)

```bat
py -3 -m venv .cache/bench-venv
.cache\bench-venv\Scripts\pip install mss dxcam pillow
.cache\bench-venv\Scripts\python tools\bench_mark_in_game\bench_capture.py
```

Não commite `.cache/bench-venv`.
