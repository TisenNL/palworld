# Posição live do jogador (leitura de memória, sem Overwolf)

Documento de referência para retomar/refazer o trabalho sem começar do zero.
Nunca registre coordenadas reais em logs/commits; use apenas `status`, `mapZone` e presença.

## Resumo

O helper Python lê, **somente leitura** (`PROCESS_VM_READ`, nunca escreve), a memória de
`Palworld-Win64-Shipping.exe` e expõe `GET /player-position/state`. O frontend faz polling,
desenha um marcador azul no Leaflet e centraliza o mapa (`panTo`, sem animação) no jogador.
Não depende do Overwolf nem de anticheat bypass. Só funciona na build validada.

## Fluxo de dados

1. [server/player_position.py](../server/player_position.py) `read_palworld_position()` → dict de status.
2. [server/coord_tooltip.py](../server/coord_tooltip.py) serve `/player-position/state` (valida Host/Origin como as demais rotas).
3. [vite.config.ts](../vite.config.ts): rota `/player-position` no proxy de dev (rota nova de helper = adicionar lá).
4. [src/services/api.ts](../src/services/api.ts) `getPlayerPositionState()`; schema Zod em [src/types/server.ts](../src/types/server.ts).
5. [src/stores/serverHud.ts](../src/stores/serverHud.ts): `pollPlayerPosition` (250 ms se `ready`, senão 1,5 s; auto-reagenda).
6. [src/views/MapView.vue](../src/views/MapView.vue): mostra status e passa `:player-position`.
7. [src/components/map/LeafletMapView.vue](../src/components/map/LeafletMapView.vue) `syncPlayerPosition()`: converte
   `gameX/gameY` com `toLatLng(getMapWindow(zone), …)`, cria/move o marcador e `panTo`. Observa `[mapZone, playerPosition]`;
   remove o marcador se a zona do jogador ≠ zona exibida.

## Status retornados

`ready`, `not_running`, `access_denied`, `unsupported_build`, `waiting_for_player` (no menu/carregando),
`unsupported` (não-Windows ou Python 32-bit), `probe_error`. Em `ready` há `mapZone` (`palpagos` | `world-tree`),
`gameX`, `gameY`, `gameZ`.

## Algoritmo de leitura (build validada)

Build: Steam `25246127`, SHA-256 do exe
`e590b5e7bfaa3fea40fab1a02cc72c8fc5fd6f8631ef2308e95ac56c25195837`
(`SUPPORTED_EXECUTABLE_SHA256`). Hash diferente → `unsupported_build`, sem ler nada.

1. Acha o processo (`Module32*`/toolhelp) e abre com `PROCESS_VM_READ | QUERY_INFORMATION`.
2. Confere o hash do exe em disco (cacheado por path/size/mtime).
3. Procura **no exe em disco**, só em seções executáveis, a assinatura única
   `48 8B 05 ?? ?? ?? ?? EB 05` (`mov rax,[rip+rel32]; jmp +5`). Deve haver exatamente 1 ocorrência.
   O rel32 resolve o RVA do ponteiro `GWorld` (cacheado em `_GWORLD_RVA_CACHE`).
4. Pega a base do módulo no processo e **valida os 9 bytes da assinatura em memória**.
5. Lê `GWorld` e segue a cadeia (cada ponteiro validado: 0x10000..0x7FFF_FFFF_FFFF, alinhado a 8):

| Passo | Offset |
|---|---|
| World → OwningGameInstance | `+0x1B8` |
| GameInstance → `TArray LocalPlayers` (data, count, capacity; exige 1≤count≤capacity≤8) | `+0x38` |
| LocalPlayer[0] → PlayerController | `+0x30` |
| PlayerController → Pawn (actor) | `+0x330` |
| Actor → ponteiro 1 | `+0x30` |
| objeto 1 → ponteiro 2 | `+0x2D0` |
| objeto 2 → vetor de 3 `double` (x, y, z; unidades UE em cm) | `+0xA18` |

6. Sanidade: valores finitos, `-100_000 ≤ z ≤ 1_000_000`, e (x,y) dentro de uma das caixas:
   - Palpagos `x∈[-1_099_400, 349_400]`, `y∈[-724_400, 724_400]`
   - World Tree `x∈[347_351.5, 689_148.5]`, `y∈[-818_197, -476_400]`

   (World Tree é testada primeiro porque as caixas se sobrepõem em x.)

Constantes ficam no topo de `player_position.py`.

## Como foi descoberto (metodologia, para repetir após update do jogo)

1. Havia só uma coordenada antiga no log do Overwolf; o acesso read-only ao processo foi confirmado.
2. Calibração incremental com o usuário parado/andando em locais conhecidos ("pronto" a cada passo), lendo
   um ator de referência (via Overwolf app) e achando o vetor de 3 doubles em `+0xA18` (cadeia `+0x30 → +0x2D0 → +0xA18`).
3. Validação de movimento: coordenada muda ao andar e fica estável parado; valores dentro das caixas dos mapas.
4. Remoção do Overwolf: achar `GWorld` por assinatura estática no exe (em vez de endereço do ator), seguir a
   cadeia UE padrão até o pawn local e **comparar com o ator de referência anterior no processo ativo**; bateu.
5. Só então o hash da build foi fixado como guarda.

### Após atualização do Palworld (build nova → `unsupported_build`)

1. Calcular o novo SHA-256 do exe (nunca ler memória antes de validar).
2. Reencontrar a assinatura `GWorld` (as constantes `GWORLD_SIGNATURE_*`); se não for única, achar outra
   instrução `mov reg,[rip+rel32]` que referencia o ponteiro global do `UWorld` (ex.: via dump de UE4SS/offset dumper).
3. Revalidar cada offset da tabela com o jogo parado e depois andando (coordenada coerente com o mapa).
4. Atualizar hash + constantes, rodar `py -3 -m unittest tests.test_player_position` e o E2E.
   Não usar varredura indiscriminada da memória.

## Bugs já corrigidos (não repetir)

- `L.Marker` não tem `bringToFront` → usar `setZIndexOffset`.
- Marcador não sumia ao trocar de zona → watcher precisa observar `mapZone` **e** `playerPosition`.
- Polling parava após a 1ª consulta: `pollPlayerPosition` chamava `stopPlayerPositionPolling()` (desliga o polling). Não chamar.
  Teste de regressão em `tests/batchMark.spec.ts`.
- ESLint `vue/return-in-computed-property`: switch de computed precisa de `default`.

## Testes

- `py -3 -m unittest tests.test_player_position` (também em `npm run test:server`) — assinatura, cadeia de ponteiros, zonas, guardas.
- `npx vitest run tests/batchMark.spec.ts` — polling contínuo do store.
- `npx playwright test tests/e2e/map-locations.spec.ts` — marcador só na zona certa e centralizado (<3 px do centro).
- Verificação manual: com o jogo aberto em mundo, `curl http://127.0.0.1:8765/player-position/state` deve dar `ready`
  (imprimir só `status`/`mapZone`).

## Requisitos e limites

- Windows, Python **64-bit**, helper rodando (`py -3 run.py`), jogo em um mundo carregado.
- Se o jogo rodar elevado e o helper não, pode retornar `access_denied`.
- Sem escrita em memória, sem injeção; mantenha assim.
