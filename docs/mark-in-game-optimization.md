# Mark in game — relatório de otimização
#
# Baseline vs resultado (reader simulado dos testes; sleep contabilizado;
# OCR real do jogo não medido aqui). Alvo simulado (80, -60), cold start
# (sem cache em disco), confirmação ligada.
#
# | Métrica              | Baseline (opts off) | Otimizado (opts on) | Δ        |
# |----------------------|---------------------|---------------------|----------|
# | status               | completed           | completed           | —        |
# | soma sleeps (s)      | ~5.09               | ~1.0–2.0            | ≈ -60%+  |
# | leituras OCR         | ~34                 | ~10–20              | ↓        |
# | iterações do loop    | ~12                 | ~5–9                | ↓        |
# | clicks Add           | 1                   | 1                   | igual    |
#
# Estimativa de tempo real no jogo (ordem de grandeza):
# - Baseline: sleeps ~5.1s + OCR×34×(~80–200ms) + focus 0.25s → tipicamente 8–15s+
# - Otimizado cold: sleeps menores + menos iters; OCR pode variar com settle
# - Otimizado warm (cache memória/disco): calibração WASD quase eliminada (~0.5–1s)
#
# Instrumentação: PALWORLD_MARKER_TIMING=1
# Flags (default=1; 0 desliga):
#   PALWORLD_MARKER_ADAPTIVE_SLEEP
#   PALWORLD_MARKER_ADAPTIVE_OCR
#   PALWORLD_MARKER_DISK_CALIBRATION
#   PALWORLD_MARKER_MOUSE_CACHE
#   PALWORLD_MARKER_DUAL_AXIS
#   PALWORLD_MARKER_ADAPTIVE_CONFIRM
#
# Aplicadas:
# 1. Sleeps → _read_after_action / settle adaptativo (teto = sleep antigo)
# 2. OCR estabilidade adaptativa (1 leitura longe; 2 perto/final)
# 4. Cache WASD em .cache/game-marker-calibration.json + validação 1×W
# 5. Cache mouse no mesmo arquivo / memória
# 6. Dual-axis WASD no far field + duração maior se ||erro||≥150
# 8. Confirm: min 0.12s + poll de pixels na área Add (fallback 0.5s)
#
# Descartadas:
# 3. OCR mais barato / mss / dxcam — risco de precisão sem gargalo de captura medido
# 7. Sobrepor OCR com input — complexidade vs _recognition_lock; risco de race
#
# Checklist manual:
# [ ] 10 runs Mark in game (5 perto, 5 longe do alvo)
# [ ] 1 dryRun (se exposto) ou confirmar sem Add via API dryRun=true
# [ ] 1 cancelamento com Esc no meio do movimento
# [ ] Reiniciar helper e 2ª run usando cache em disco (mensagem "Using disk WASD calibration")
# [ ] Conferir Marker placed só com current==target
