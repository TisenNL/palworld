# Mark in game — relatório de medições

Gerado por `aggregate_runs.py`. Runs JSONL encontrados: **0**.

## Parte B — Runs

**PENDENTE:** rode 10 Marks com `PALWORLD_MARKER_TIMING=1` (5 longe, 5 perto, 1º cold).

## Parte C — Respostas

### 1. Custo de uma leitura OCR

- total **138.595 ms** (captura 71.176, pré-proc 16.813, inferência 50.606); variantes=8

### 2. Primeira variante já correta?

- perfil único: first_variant_won=True

### 3. Score de confiança RapidOCR

**PENDENTE:** coletar runs reais; RapidOCR retorna `item[2]` por caixa de texto.

### 4. ONNX Runtime

- versão: 1.27.0 · providers: ['AzureExecutionProvider', 'CPUExecutionProvider']
- CUDA: False · DirectML: False
- intra_op=0 inter_op=0
- RapidOCR roda sob OcrSelector._recognition_lock (serializa OCR).
- O mesmo processo Python serve HTTP (ThreadingHTTPServer) e Tkinter overlay.
- GameMarkerController roda em thread daemon; OCR é chamado dessa thread.
- Inferência ONNX CPU compete com o jogo (GPU dedicada não usada pelo ONNX neste setup).

### 5. Captura ImageGrab vs mss vs dxcam

- **ImageGrab**: mediana 65.885 ms · p95 69.413 ms (n=200)
- **mss**: mediana 16.717 ms · p95 17.467 ms (n=200)
- **dxcam**: erro — No module named 'dxcam'
- ROI: {'left': 275, 'top': 199, 'right': 453, 'bottom': 241, 'w': 178, 'h': 42}

### 6. Latência do HUD pós-tecla

- hold 0.012s → settled_at_ms=276.5919000012218 samples=4
- hold 0.06s → settled_at_ms=254.38070000018342 samples=4
- hold 0.22s → settled_at_ms=260.37040000119305 samples=4

### 7. Física do movimento

- W @0.06s: None u/s (stdev 0.0)
- A @0.06s: None u/s (stdev 0.0)
- S @0.06s: None u/s (stdev 0.0)
- D @0.06s: None u/s (stdev 0.0)
- linearidade: {}

### 8. Near-field (‖erro‖≤12 → alvo exato)

**PENDENTE:** runs TIMING.

### 9. Overhead validação de cache

**PENDENTE:** run quente com cache disco.

### 10. Dataset OCR bench

**PENDENTE:** `0/300` — `py -3 tools/bench_mark_in_game/collect_ocr_crops.py`

### 11. FPS jogo / HUD

- sample_hz=17.66 · change_hz=1.33 · notas: ['FPS do jogo não é lido pela API; use contador do jogo ou NVIDIA overlay.', 'change_hz aproxima a taxa em que o HUD (ou anti-aliasing) muda na ROI.', 'Com mapa parado, change_hz deve ser baixo; mova o mapa para medir refresh do texto.']

## Parte D — Ambiente

- CPU: 13th Gen Intel(R) Core(TM) i5-13400F (10c/16t)
- GPU: NVIDIA GeForce RTX 4060 Ti
- RAM: ~31.8 GB
- OS: Microsoft Windows 11 Pro 10.0.26200
- Python: 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)]
- onnxruntime: 1.27.0 providers=['AzureExecutionProvider', 'CPUExecutionProvider']
- rapidocr: {'module': 'C:\\Users\\TisenNL\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\rapidocr_onnxruntime\\__init__.py', 'version': '?'}
- largest_monitor: [0, 0, 2560, 1440] key=v1:0,0,2560x1440
- modo do jogo / Hz / nº monitores: {'game_display_mode': 'PENDENTE: borderless/fullscreen (preencher manualmente)', 'monitor_refresh_hz': 'PENDENTE', 'monitor_count': 'PENDENTE'}

## Como repetir

Ver `tools/bench_mark_in_game/README.md`.
