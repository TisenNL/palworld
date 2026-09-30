# Análise Técnica Completa — op.gg/palworld/map

> Documento gerado por inspeção ao vivo do site op.gg usando Playwright.
> Todos os assets foram baixados e confirmados funcionando.

---

## 1. Stack do op.gg

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js App Router + React + Turbopack |
| Mapa | **Leaflet 1.9.4** com **CRS.Simple** |
| Estilo | Tailwind CSS + tema dark customizado |
| Ícones | Lucide React |
| CDN | `https://s-stats-platform-cdn.op.gg` |

---

## 2. Tiles do Mapa

### URLs definitivas

```
# Palpagos Islands
https://s-stats-platform-cdn.op.gg/palworld/images/tiles/{z}-{x}-{y}.png
  ?image=q_auto:good,f_webp,w_512&v=2026081102

# World Tree
https://s-stats-platform-cdn.op.gg/palworld/images/tiles-tree/{z}x{x}x{y}.png
  ?image=q_auto:good,f_webp,w_512&v=2026081102
```

### Especificações

| Parâmetro | Valor |
|---|---|
| Formato base | PNG (CDN converte para WebP automaticamente) |
| Largura final | 512px (após conversão CDN) |
| Leaflet tileSize | 256 (o Leaflet usa 256, mas o arquivo é 512px → sharp) |
| Zoom nativo | 0–4 (`maxNativeZoom: 4`) |
| Zoom visual | 1–8 (`minZoom: 1`, `maxZoom: 8`) |
| Tiles por zoom | z0=1, z1=4, z2=16, z3=64, z4=256 — total 341 por mapa |

### Assets baixados localmente

```
public/opgg-map-tiles/palpagos/z{0-4}/x{col}y{row}.webp   (341 tiles)
public/opgg-map-tiles/world-tree/z{0-4}/x{col}y{row}.webp  (341 tiles)
```

Para atualizar: `py -3 download_opgg_data.py`

---

## 3. Configuração do Leaflet

```typescript
// Exato do código-fonte do op.gg (02vzr4rrfn1be.js)
L.map(container, {
  crs: L.CRS.Simple,
  minZoom: 1,
  maxZoom: 8,
  zoomSnap: 0,
  zoomDelta: 1,
  zoomAnimation: true,
  fadeAnimation: !isSoftwareRenderer,
  inertia: !isSoftwareRenderer,
  scrollWheelZoom: false,       // usa handler de scroll suave customizado
  zoomControl: false,           // controles customizados
  attributionControl: false,
  maxBounds: [
    [-WORLD_SIZE - 24, -24],    // southwest
    [24, WORLD_SIZE + 24],      // northeast
  ],
})

const WORLD_SIZE = 256   // unidade do CRS.Simple

// TileLayer
L.tileLayer(TILE_URL_TEMPLATE, {
  tileSize: 256,
  updateWhenZooming: false,
  minZoom: 0,
  maxZoom: 8,
  maxNativeZoom: 4,
  noWrap: true,
  bounds: [[-WORLD_SIZE, 0], [0, WORLD_SIZE]],
})
```

---

## 4. Sistema de Coordenadas

O op.gg usa **coordenadas de motor de jogo** (Unreal Engine 5, escala 1:1 em unidades UE) — **não** as coordenadas "ipos" do pause menu.

### mapWindow (bounds do mapa em coordenadas UE5)

```typescript
const MAP_WINDOW_PALPAGOS = {
  minX: -1_099_400, maxX: 349_400,
  minY: -724_400,   maxY: 724_400,
}

const MAP_WINDOW_WORLD_TREE = {
  minX: 347_351.5, maxX: 689_148.5,
  minY: -818_197,  maxY: -476_400,
}
```

### Funções de conversão (código exato do op.gg)

```typescript
// UE5 game coords → Leaflet LatLng
function toLatLng(mapWindow, gameX: number, gameY: number): [number, number] {
  const n = (gameY - mapWindow.minY) / (mapWindow.maxY - mapWindow.minY)
  const lat = -(256 * ((mapWindow.maxX - gameX) / (mapWindow.maxX - mapWindow.minX)))
  const lng = 256 * n
  return [lat, lng]
}

// In-game pause menu coords → UE5 game coords
function toGamePoint(ingameX: number, ingameY: number) {
  return {
    gameX: 459 * ingameY + (-123_888),
    gameY: 459 * ingameX + 158_000,
  }
}

// UE5 game coords → in-game pause menu coords (display)
function toIngamePoint(gameX: number, gameY: number, gameZ: number) {
  return {
    ingameX: Math.round((gameY - 158_000) / 459),
    ingameY: Math.round((gameX - (-123_888)) / 459),
    ingameZ: Math.round(gameZ / 100),
  }
}

// Detecta se ponto pertence ao mapa World Tree
function isTreePoint(x: number, y: number): boolean {
  return x >= 347_351.5 && x <= 689_148.5
      && y >= -818_197  && y <= -476_400
}
```

---

## 5. Dados dos Marcadores

### URL do arquivo completo

```
https://s-stats-platform-cdn.op.gg/palworld/meta/points.json?v=2026091501
```

Baixado em: `public/opgg-data/points.json` (818KB, ~16.000 pontos)

### Estrutura do JSON

Cada tipo de ponto é uma chave no objeto raiz com um array de itens:

```typescript
interface PointsJson {
  // Recursos coletáveis
  LifmunkEffigy: EffigyPoint[]      // 407 — inclui todos os tipos (t = tipo da criatura)
  LootTower: SimplePoint[]           // 106 — Ancient Ruins
  Note: NotePoint[]                  // 64  — Journals
  
  // Ovos
  Eggs: EggPoint[]                   // 1816 — todos os tipos de ovos
  
  // Inimigos
  FieldBoss: BossPoint[]             // 90
  Bounty: BountyPoint[]              // 33
  Predator: PredatorPoint[]          // 29
  EnemyCamp: TypedPoint[]            // 47
  AntiAir: SimplePoint[]             // 11
  Incident: SimplePoint[]            // 97
  BossTower: TowerPoint[]            // 13
  
  // Localização
  FastTravels: NamedPoint[]          // 152
  WatchTower: NamedPoint[]           // 22
  DungeonPortal: NamedPoint[]        // 170
  DungeonFixed: NamedPoint[]         // 18
  CaveEntrance: CavePoint[]          // 17
  Respawn: SimplePoint[]             // 8
  SkylandWarpAltar: SimplePoint[]    // 20
  Home: SimplePoint[]                // 32
  RegionName: RegionPoint[]          // 121
  Quest: NamedPoint[]                // 169
  TreasureMap: SimplePoint[]         // 42
  HeatArea: HeatPoint[]              // 21
  
  // Minério
  OreMetal: SimplePoint[]            // 1438
  OreCoal: SimplePoint[]             // 520
  OreQuartz: SimplePoint[]           // 523
  OreQuartzCluster: SimplePoint[]    // 11
  OreSulfur: SimplePoint[]           // 280
  Chromites: SimplePoint[]           // 257
  RainbowCrystal: SimplePoint[]      // 349
  SkyIslandOre: SimplePoint[]        // 208
  WorldTreeOre: SimplePoint[]        // 80
  HardWood: SimplePoint[]            // 2371
  AncientLava: SimplePoint[]         // 10
  AncientWood: SimplePoint[]         // 10
  AncientBeastBone: SimplePoint[]    // 10
  
  // Recursos
  Chestbox: ChestPoint[]             // 1501 (inclui oilrig, element, etc.)
  ElementTreasure: TypedPoint[]      // 109
  Supply: TypedPoint[]               // 480
  Junk: SimplePoint[]                // 670
  SkillFruits: TypedPoint[]          // 43
  Peach: SimplePoint[]               // 22
  BeautifulFlower: SimplePoint[]     // 27
  CrudeOil: SimplePoint[]            // 185
  NightStone: SimplePoint[]          // 271
  
  // Pesca
  FishingSpot: FishingPoint[]        // 506
  RareFishingSpot: FishingPoint[]    // 131
  Salvage: SalvagePoint[]            // 2763
  
  // NPCs
  NpcSalesPerson: NpcPoint[]         // 8
  NpcPalDealer: NpcPoint[]           // 10
  NpcDarkTrader: NpcPoint[]          // 4
  NpcMedalTrader: NpcPoint[]         // 4
  NpcPalDisplay: NpcPoint[]          // 9
  NpcEmote: NpcPoint[]               // 17
  NpcPresenter: NpcPoint[]           // 1
  NpcBountyTrader: NpcPoint[]        // 4
  NpcOther: NpcPoint[]               // 107
}

// Tipos base
interface SimplePoint   { l: [number, number, number] }  // [gameX, gameY, gameZ]
interface NamedPoint    extends SimplePoint { name?: string }
interface TypedPoint    extends SimplePoint { t?: string }
interface EffigyPoint   extends SimplePoint { t: string }  // effigy creature name
interface EggPoint      extends SimplePoint { t: string; k?: string }
interface BossPoint     extends SimplePoint { id: string; lv: number; name: string }
interface BountyPoint   extends SimplePoint { name: string; lv: number }
interface PredatorPoint extends SimplePoint { id?: string; lv?: number }
interface TowerPoint    { ref: string; bossType: string; loc: [number, number, number] }
interface CavePoint     extends SimplePoint { id: string }
interface ChestPoint    extends SimplePoint { t?: string }
interface FishingPoint  extends SimplePoint { type: string; t?: string }
interface SalvagePoint  extends SimplePoint { type: 'Rank1' | 'Rank2' }
interface RegionPoint   extends SimplePoint { id: string }
interface HeatPoint     extends SimplePoint { extent: [number, number]; day: number; night: number }
interface NpcPoint      extends SimplePoint { name: string; lv?: number }
```

### Tipos de efígie (`t` field em LifmunkEffigy)
```
Carbunclo → Lifmunk    (140 no mundo)
SheepBall → Lamball    (30)
Penguin   → Pengullet  (30)
IceCrocodile → Munchill (30)
FlameBambi → Rooby     (30)
LeafMomonga → Herbil   (30)
Monkey    → Tanzee     (30)
NegativeKoala → Depresso (30)
PinkCat   → Cattiva    (30 na World Tree)
LazyDragon → Lunaris   (4)
Mutant    → Relaxaurus (4)
GuardianDog → Yakumo   (2)
```

### Separação Palpagos / World Tree
O campo `l[0]` (gameX) determina o mapa: `isTreePoint(l[0], l[1])`.

---

## 6. Ícones dos Marcadores

### URLs no CDN op.gg

```
# Ícones de itens (effigies, eggs, recursos)
https://s-stats-platform-cdn.op.gg/palworld/images/icons/{name}.png
  ?image=q_auto:good,f_webp,w_48&v=1790736170

# Ícones de marcadores (enemies, locations)
https://s-stats-platform-cdn.op.gg/palworld/images/markers/{name}.png
  ?image=q_auto:good,f_webp,w_48&v=1790736170

# Ícones de Pals individuais (Alpha Pals portrait)
https://s-stats-platform-cdn.op.gg/palworld/images/icons/{palId}.png
  ?image=q_auto:good,f_webp,w_48&v=1790736170
```

### Assets baixados localmente
```
public/opgg-icons/effigies/      (13 ícones: lifmunk.webp ... mimog.webp)
public/opgg-icons/eggs/          (10 ícones: grass.webp ... worldtree.webp)
public/opgg-icons/markers/       (19 ícones: field-boss.webp ... quest.webp)
public/opgg-icons/resources/     (2 ícones: hardwood.webp, human.webp)
public/opgg-icons/index.json     (mapeamento completo)
```

### HTML do marcador (código exato do op.gg)
```html
<span 
  aria-hidden="true" 
  class="palworld-map-marker-image palworld-map-image-silhouette"
  style="
    width: {size}px;
    height: {size}px;
    border-color: {ringColor};
    background-color: {bgColor};
    background-image: url('{iconUrl}');
  "
></span>
```

---

## 7. Grupos / Categorias da Sidebar

Definido no `index.json` (`POINTS_INDEX_URL`):

| Grupo | Categorias | Total Palpagos |
|---|---|---|
| `collectibles` | effigies, lootTower, note | 577 |
| `eggs` | egg:grass, egg:desert, egg:volcano, egg:snow, egg:sakurajima, egg:darkIsland, egg:skyIsland, egg:worldTree | 1816 |
| `enemies` | bossTower, fieldBoss, bounty, predator, enemyCamp, antiAir, incident | 320 |
| `fishing` | fishingSpot, salvage | 3400 |
| `locations` | fastTravel, respawn, skylandWarpAltar, home, watchTower, regionName, dungeon, caveEntrance, treasureMap, heatArea, quest | 792 |
| `mine` | oreMetal, oreCoal, oreQuartz, oreQuartzCluster, oreSulfur, chromite, rainbowCrystal, skyIslandOre, worldTreeOre, hardWood, ancientLava, ancientWood, ancientBeastBone | 6067 |
| `npc` | npcSalesPerson, npcPalDealer, npcDarkTrader, npcMedalTrader, npcPalDisplay, npcEmote, npcPresenter, npcBountyTrader, npcOther | 164 |
| `oilrig` | chestOilrig, chestOilrigGoal | 51 |
| `resources` | chest, elementChest, supply, junk, skillFruit, peach, beautifulFlower, crudeOil, nightStone | 3257 |

---

## 8. Persistência de Progresso (localStorage)

```typescript
// Chave de armazenamento
const STORAGE_KEY = 'palworld:map:checked-collectibles'

// Formato do item armazenado
interface CheckedItem {
  key: string   // identificador único do marcador
  x: number     // lat do Leaflet (não gameX)
  y: number     // lng do Leaflet (não gameY)
}

// Formato da chave por tipo
const effigyKey    = (p) => `effigy:${p.x}:${p.y}`
const collectKey   = (type, p) => `collectible:${type}:${p.x}:${p.y}`

// Os valores x,y aqui são as coordenadas Leaflet (output de toLatLng()),
// NÃO as coordenadas UE5 do points.json
```

O sistema suporta exportação comprimida (deflate + base64) dos dados de progresso via URL share.

---

## 9. Funcionalidades da UI

### Sidebar (`.palworld-scrollbar`)
- Largura: `w-[22rem]` / `xl:w-96` (escondida em mobile, visível em `lg:block`)
- Cabeçalho sticky com botões: **All**, **Reset filters**, **Collapse all**, **Hide filters**
- Grupos expansíveis (`aria-expanded`) com botão "All" por grupo
- Cada item: ícone + label + contador `realizado/total`
- Seletor de mapa no topo: **Palpagos Islands** | **World Tree**

### Mapa
- Slider de tamanho dos marcadores (CSS variable `--range-progress`)
- Botão **Fullscreen**
- Controles de zoom (+/−) no canto inferior direito
- Coordenadas X/Y exibidas no rodapé (atualizadas em `mousemove`)
- Input de "Go to coordinates" (form com MapPin icon)
- Scroll suave customizado (não usa o scroll nativo do Leaflet)

### Popup do marcador
- Aparece ao clicar num marcador
- Mostra: ícone, título, coordenadas formatadas
- Botão "Discovered" / "Not discovered" (toggle com ícone Eye/EyeOff)
- Animação de abertura/fechamento

---

## 10. Cores e Tema

```css
/* Paleta principal do op.gg (Palworld) */
--color-background: #0c1822;          /* fundo do mapa */
--color-card: #141c24;                /* bg da sidebar e cards */
--color-darkpurple-900: #1a1a28;      /* fundo de itens */
--color-darkpurple-850: #1e1e30;
--color-darkpurple-400: #8888aa;      /* texto secundário */
--color-darkpurple-300: #aaaacc;      /* texto terciário */
--color-darkpurple-200: #ccccee;
--color-primary: #6c5ce7;             /* cor de destaque (violet) */
--color-border: #3c3c4d;

/* Cores de spawn */
--color-spawn-both:  #6cff63;
--color-spawn-day:   #fd9b00;
--color-spawn-night: #76d2fd;
```

---

## 11. Arquivos Locais Disponíveis

```
public/
  opgg-map-tiles/
    palpagos/z{0-4}/x{col}y{row}.webp     (341 tiles)
    world-tree/z{0-4}/x{col}y{row}.webp   (341 tiles)
  opgg-icons/
    effigies/{name}.webp                   (13 ícones)
    eggs/{name}.webp                       (10 ícones)
    markers/{name}.webp                    (19 ícones)
    resources/{name}.webp                  (2 ícones)
    index.json                             (mapeamento)
  opgg-data/
    points.json                            (818KB — todos os marcadores)
    index.json                             (5KB — índice de grupos e contagens)
    egg-loot.json                          (46KB — dados de loot de ovos)
    category-map.json                      (mapeamento categoria → grupo)
```

---

## 12. Plano de Implementação

Com base nessa análise, a reimplementação deve:

1. **Substituir `MapCanvas.vue`** pelo componente Leaflet com CRS.Simple usando a configuração exata acima
2. **Substituir os tiles** de `public/map-tiles/` pelos tiles em `public/opgg-map-tiles/`
3. **Substituir `public/data.json`** com dados convertidos do `public/opgg-data/points.json` (usando a função `toIngamePoint` para converter UE5 → ipos)
4. **Substituir os ícones** pelos de `public/opgg-icons/`
5. **Replicar o sistema de localStorage** com as chaves `palworld:map:checked-collectibles`
6. **Replicar a sidebar** com os grupos, contadores e filtros do op.gg
7. **Manter** a integração com o servidor helper Python (OCR, HUD, mark-in-game)
