# Mark in game — relatório de otimização (pós-correções de review)

## Fluxo canônico (atual)

1. Focus Palworld → cursor no centro → OCR inicial (**2** leituras iguais).
2. Calibração WASD: memória → disco (validação 1×W) → calibração fresca.
   Mouse cache: só após **validação** (nudge + alinhamento); senão recalibra.
3. Loop: `_read_after_action` (poll OCR até 2 iguais, teto = sleep antigo).
   Far field: dual-axis se `||erro|| >= 60`; senão 1 tecla; `max_duration` ≤ 0.22 s.
   Near field (≤ 12): mouse + `solve_mouse_delta`.
   Adaptação online dos vetores **somente** com 1 tecla.
4. Gate: `current == target` estável (2×) → opcionalmente E + Add.
5. Confirmação: default sleep **0.5 s**. Pixel settle opcional (`PALWORLD_MARKER_ADAPTIVE_CONFIRM=1`):
   min 0.12 s + 2 frames consecutivos diferentes do baseline na ROI do Add.

## Posição do jogador como dica inicial

O mapa do jogo abre **centrado no jogador**: com o cursor no centro, o OCR e a posição lida da memória
(`server/player_position.py`, convertida em `player_ingame_coordinate`) diferem em ≤ 1 unidade (medido no jogo).
`GameMarkerController._read_initial` faz **1** leitura OCR e a aceita se estiver a ≤ `PLAYER_HINT_TOLERANCE` (3)
da dica; senão (mapa já movido, leitor indisponível/build não suportada) cai na leitura estável de 2 OCRs.
A dica só substitui a leitura inicial; o loop e o gate final continuam com OCR.

## Invalidação de cache

Invalida memória+disco em: divergência, limite de iterações, OCR instável/ausente,
falha de calibração WASD, jump implausível.

**Não** invalida em: cancel/Esc, perda de foco, timeout global.

## Flags (env; `0`/`false`/`off` desliga)

| Flag | Default | Papel |
|------|---------|--------|
| `PALWORLD_MARKER_ADAPTIVE_SLEEP` | 1 | Esperas adaptativas / `_read_after_action` |
| `PALWORLD_MARKER_DISK_CALIBRATION` | 1 | Cache WASD/mouse em `.cache/game-marker-calibration.json` |
| `PALWORLD_MARKER_MOUSE_CACHE` | 1 | Reuso de mouse (com validação) |
| `PALWORLD_MARKER_DUAL_AXIS` | 1 | Dual-axis se erro ≥ 60 |
| `PALWORLD_MARKER_ADAPTIVE_CONFIRM` | **0** | Confirm por pixel (ligar após validar no jogo) |
| `PALWORLD_MARKER_TIMING` | 0 | Log de fases / OCR / sleeps |

Removida: `PALWORLD_MARKER_ADAPTIVE_OCR` (atalho de 1 leitura).

Chave de cache: `v{version}:{left},{top},{width}x{height}` via `largest_monitor_bounds()`.

## Baseline simulado (alvo 80/−60, cold, confirm on)

| Métrica | Pré-otimização (opts off) | Pós-otimização (antes do review) | Pós-correções (atual) |
|---------|---------------------------|----------------------------------|------------------------|
| Soma sleeps | ~5.09 s | ~1.19 s | ~1.3–2.0 s* |
| OCR reads | ~34 | ~24 | ~24–30 |
| Loop iters | ~12 | ~9 | ~7–9 |
| Click Add | 1 | 1 | 1 |

\*Confirm default voltou a 0.5 s de sleep (flag off); calibração/loop adaptativos e dual-axis
com limiar 60 mantêm a maior parte do ganho. Warm start (cache disco validado) remove
quase toda a calibração WASD.

Instrumentação: `PALWORLD_MARKER_TIMING=1`.

## Checklist manual

1. 5× Mark in game **longe** do alvo
2. 5× Mark in game **perto**
3. dry-run (`dryRun: true`) — sem Add
4. Esc no meio do movimento — cancel + teclas liberadas
5. Reiniciar helper → 2ª run com cache disco (mais rápida, ainda exata)
6. Resolução/monitor diferente → miss de cache / recalibra
7. `PALWORLD_MARKER_ADAPTIVE_CONFIRM=1` → validar dialog Add no jogo

## Movimento fino por mouse (zoom maximo)

- Zoom maximo: 1 unidade ~ 12,3 px; o cursor no centro equivale a posicao do jogador.
- Calibracao de mouse com sonda de 240 px (ate 3 tentativas) e espera do HUD (que atrasa em saltos grandes); `_read_toward` aguarda o valor previsto.
- WASD so leva a <=40 unidades (`NEAR_FIELD`); o resto usa passos de mouse de ate 480 px, e com erro <=2,5 passos de 0,6x (a coordenada exibida e truncada, evita oscilar +-1).
- Medido (dry-run, mapa aberto): alvos de 3 a ~180 unidades em 3-11 s, 5-14 iteracoes.

- O controller abre o mapa sozinho (`_prepare_map`: M so se o OCR nao le nada, pois M alterna) e aplica 12 giros de roda para zoom maximo antes de ler a posicao. Testado com mapa fechado e aberto (dry-run).
