"""
Solves the World Tree coordinate projection constants by calibrating
against known in-game positions from the wiki and allthings.how.

The main map uses:
  ingame_x = (raw_x - LAND_MIN_X) / PER_PIXEL - INGAME_X_START + 1000
  ingame_y = (raw_y - LAND_MIN_Y) / PER_PIXEL - INGAME_Y_START + 1000

But we don't have raw Unreal coords for the known WT in-game positions.
Instead, we derive the projection from two anchor points:

Anchor 1 - Ore/egg bounding box mapped to approximate in-game extent:
  The WT ore/egg raw X range is 408215..627885 (spread ~220k)
  The WT ore/egg raw Y range is -753780..-521557 (spread ~232k)

  The main map has PER_PIXEL=459, giving 459 Unreal units per in-game unit.
  Assuming same scale: WT ore spreads ~479 in-game X, ~505 in-game Y.
  These ores are in the interior of the map so they don't define the full extent.

Anchor 2 - Known in-game positions from wiki:
  Mycora alpha:        (-35,   731)
  Aegidron alpha:      (-59,   756)
  Celesdir Noct alpha: (-60,   777)
  Moldron Cryst alpha: (-64,   816)
  Renjishi alpha:      (56,    838)
  Sealed Sanctum:      (-1979, 1361)

The alpha pal cluster is tightly grouped around (-64..56, 731..838).
Sealed Sanctum is far away at (-1979, 1361).

The WT in-game coordinate system has:
  X: roughly -2000 to +500 (2500 units wide)
  Y: roughly 700 to 1500 (800 units tall, possibly more below 700)

Since PER_PIXEL_MAIN = 459, and raw Unreal coords show the WT zone is
about the same spatial scale, we use PER_PIXEL_WT = 459.

For the in-game coordinate formula, we need LAND_MIN and INGAME_START.
The main map uses INGAME_X_START = 2125 which puts (0,0) near the map center.
The WT map appears to use a different offset.

We can back-calculate LAND_MIN from known anchor points IF we know the
corresponding raw coords. We don't have exact raw-to-ingame pairs,
but we can estimate using WT bounding box + known in-game extent.

Approach: Use the ore bounding box center as anchor.
  Raw ore center: (518050, -637535)
  The ores are scattered across the WT interior. Their in-game positions
  are unknown individually, but their spatial spread gives us the scale.

  Spread in raw: 219670 x 231955 Unreal units
  At PER_PIXEL=459: 479 x 505 in-game units

  The entire WT map must be larger. Based on known in-game coords:
  - Total X span at least: |-1979| + 56 = 2035 units
  - Total Y span at least: 1361 - 700 = 661 units (conservative)

  At 459 per pixel: 2035 * 459 = 934065 raw X units, 661 * 459 = 303399 raw Y units

  Main map raw extent: 1448800 x 1448800 units
  WT raw extent (estimated): ~950000 x ~700000 units

Calibration using the WT tile pyramid:
  MapGenie uses tile pyramid z8-z16 for the main map.
  For WT, if they use the same pyramid, the projection must map
  the WT coordinate space to the same [0, 256*2^16] pixel space.

  The key insight: we need the projection constants so that
  gameToImageWT(x, y) produces pixel coordinates in [0, 16M] range
  that correspond to the correct tile positions on the WT tile set.

  Since we can't fetch the WT tiles directly (403), we derive the
  projection mathematically from the known data and the main map's
  approach, then verify by checking that the ore positions cluster
  in a reasonable area of the tile space.

SOLUTION:
  Use same PER_PIXEL = 459.
  
  Define WT LAND_MIN/MAX to encompass all known data with padding:
  Raw ore extent: X 408215..627885, Y -753780..-521557
  
  The in-game coords suggest the map extends beyond the ore area.
  Known in-game X minimum: -1979 (Sealed Sanctum)
  Known in-game Y maximum: ~1400
  
  The relationship for the main map:
    ingame_x = (raw_x - LAND_MIN_X) / PER_PIXEL - INGAME_X_START + 1000
  
  If we assume INGAME_X_START for WT = 1000 (simpler origin):
    ingame_x = (raw_x - WT_LAND_MIN_X) / 459
    raw_x = ingame_x * 459 + WT_LAND_MIN_X
  
  For Sealed Sanctum at in-game (-1979, 1361):
    If raw_x = some_value, then WT_LAND_MIN_X = raw_x - (-1979) * 459
    
  This is underdetermined without a raw<->ingame pair.
  
  BEST APPROACH: Use the WT as a fixed-size image map.
  The World Tree is a dungeon-like zone, not an open world.
  Use a simple linear projection based on estimated bounds.
"""

# WT in-game coordinate bounds from all known data:
WT_INGAME_X_MIN = -2000  # Sealed Sanctum at -1979, add margin
WT_INGAME_X_MAX = 200    # Renjishi at 56, add margin  
WT_INGAME_Y_MIN = 700    # Lowest known: Mycora at 731, assume more below
WT_INGAME_Y_MAX = 1450   # Sealed Sanctum at 1361, add margin

# Raw Unreal WT bounds (from ore + egg data, extended proportionally):
WT_RAW_X_MIN = 408215
WT_RAW_X_MAX = 627885
WT_RAW_Y_MIN = -753780
WT_RAW_Y_MAX = -521557

# The raw X range covers ore/egg positions only (interior of the map)
# Extend to cover the full in-game range
# In-game X range: 200 - (-2000) = 2200 units
# Raw ore X range: 219670 units
# Scale: 219670 / 2200 ≈ 99.8 Unreal units per in-game unit (NOT 459!)
# This is very different from main map! The WT has a different scale.

ingame_x_range = WT_INGAME_X_MAX - WT_INGAME_X_MIN  # 2200
ingame_y_range = WT_INGAME_Y_MAX - WT_INGAME_Y_MIN  # 750

raw_x_range = WT_RAW_X_MAX - WT_RAW_X_MIN  # 219670
raw_y_range = WT_RAW_Y_MAX - WT_RAW_Y_MIN  # 232223

# But ore/eggs don't cover the full ingame range. Let's estimate PER_PIXEL:
# The ore center raw (518050) should map to some in-game x.
# The ore x span (219670) covers some fraction of the in-game x span.
# Without an exact anchor, we can estimate by assuming the ore/eggs
# cover the "interior" of the map (roughly 60-70% of the full extent).

# Estimate: ore/eggs span ~60% of WT width
ESTIMATED_COVERAGE = 0.60
ESTIMATED_RAW_TOTAL_X = raw_x_range / ESTIMATED_COVERAGE  # ~366k
ESTIMATED_RAW_TOTAL_Y = raw_y_range / ESTIMATED_COVERAGE  # ~387k

# PER_PIXEL for WT:
PER_PIXEL_WT_X = ESTIMATED_RAW_TOTAL_X / ingame_x_range
PER_PIXEL_WT_Y = ESTIMATED_RAW_TOTAL_Y / ingame_y_range

print(f"Estimated PER_PIXEL (X): {PER_PIXEL_WT_X:.1f}")
print(f"Estimated PER_PIXEL (Y): {PER_PIXEL_WT_Y:.1f}")
print(f"Average: {(PER_PIXEL_WT_X + PER_PIXEL_WT_Y) / 2:.1f}")

# Use uniform PER_PIXEL (average)
PER_PIXEL_WT = (PER_PIXEL_WT_X + PER_PIXEL_WT_Y) / 2

# Calculate LAND_MIN for WT:
# The ore center raw (518050, -637535) should map to approximate in-game center
# In-game center: ((-2000+200)/2, (700+1450)/2) = (-900, 1075)
WT_CENTER_RAW_X = (WT_RAW_X_MIN + WT_RAW_X_MAX) / 2  # 518050
WT_CENTER_RAW_Y = (WT_RAW_Y_MIN + WT_RAW_Y_MAX) / 2  # -637668
WT_CENTER_INGAME_X = (WT_INGAME_X_MIN + WT_INGAME_X_MAX) / 2  # -900
WT_CENTER_INGAME_Y = (WT_INGAME_Y_MIN + WT_INGAME_Y_MAX) / 2  # 1075

# ingame_x = (raw_x - LAND_MIN_X) / PER_PIXEL - INGAME_X_START + 1000
# Using INGAME_X_START = ingame_range/2 + 1000 (map is centered around 0):
# Actually for WT, let's use simpler: ingame_x = (raw_x - LAND_MIN_X) / PER_PIXEL
# i.e., INGAME_X_START = 1000 and offset 0 (just direct scaling)

# From center constraint:
# WT_CENTER_INGAME_X = (WT_CENTER_RAW_X - LAND_MIN_X) / PER_PIXEL - INGAME_X_START + 1000
# Let INGAME_X_START = 0 for WT (simplified):
# WT_CENTER_INGAME_X = (WT_CENTER_RAW_X - LAND_MIN_X) / PER_PIXEL

WT_LAND_MIN_X = WT_CENTER_RAW_X - WT_CENTER_INGAME_X * PER_PIXEL_WT
WT_LAND_MIN_Y = WT_CENTER_RAW_Y - WT_CENTER_INGAME_Y * PER_PIXEL_WT

print(f"\nWT_LAND_MIN_X = {WT_LAND_MIN_X:.0f}")
print(f"WT_LAND_MIN_Y = {WT_LAND_MIN_Y:.0f}")

# Verify known positions
def wt_rpos_to_ipos(raw_x, raw_y):
    x = (raw_x - WT_LAND_MIN_X) / PER_PIXEL_WT
    y = (raw_y - WT_LAND_MIN_Y) / PER_PIXEL_WT
    return x, y

# Test with ore center
cx, cy = wt_rpos_to_ipos(WT_CENTER_RAW_X, WT_CENTER_RAW_Y)
print(f"\nOre center maps to in-game: ({cx:.1f}, {cy:.1f})")
print(f"  Expected center: ({WT_CENTER_INGAME_X}, {WT_CENTER_INGAME_Y})")

# The key insight: We need the ACTUAL PER_PIXEL value
# Let's use the main map's PER_PIXEL=459 and figure out what in-game coords
# the ore positions would produce, then see if they're reasonable.

print("\n=== Testing with main PER_PIXEL=459 ===")
PER_PIXEL_MAIN = 459.0

# Ore raw center: (518050, -637535)
# In-game known positions: X range -2000 to +56, Y range 700 to 1361
# If PER_PIXEL=459, then ore span 219670/459 = 478 in-game units
# That's 478 out of ~2056 total X range = 23% of the map. 
# That seems too small - ores should cover most of the map.

# Trying with the actual scale:
# The WT is a dungeon zone. It might be much smaller than Palpagos.
# Alpha pal positions: X -64..56 (120 units wide), Y 731..838 (107 units tall)
# These alphas are spread around the entrance of the WT.
# The total WT zone is probably 2000-3000 units total (similar to Palpagos).

# Let's assume the WT uses the SAME PER_PIXEL=459
# and derive LAND_MIN from the ore data:
# Ore raw center (518050, -637535) should map to some in-game (cx_gt, cy_gt)
# We don't know cx_gt exactly, but given the alpha distribution,
# the ores might be around in-game x=-500..-100, y=800..900

# Most likely the WT coordinate system has:
# Ore center in-game X: around -200 (roughly middle of the map's inhabited area)
# Ore center in-game Y: around 850 (where the alphas are)

# Test this hypothesis with PER_PIXEL=459:
ASSUMED_ORE_INGAME_X = -200.0
ASSUMED_ORE_INGAME_Y = 850.0

WT_LAND_MIN_X_v2 = WT_CENTER_RAW_X - ASSUMED_ORE_INGAME_X * PER_PIXEL_MAIN
WT_LAND_MIN_Y_v2 = WT_CENTER_RAW_Y - ASSUMED_ORE_INGAME_Y * PER_PIXEL_MAIN

print(f"WT_LAND_MIN_X (v2, PER_PIXEL=459) = {WT_LAND_MIN_X_v2:.0f}")
print(f"WT_LAND_MIN_Y (v2, PER_PIXEL=459) = {WT_LAND_MIN_Y_v2:.0f}")

def wt_rpos_v2(rx, ry):
    return (rx - WT_LAND_MIN_X_v2) / PER_PIXEL_MAIN, (ry - WT_LAND_MIN_Y_v2) / PER_PIXEL_MAIN

# Ore range in this projection:
ore_x_min_v2, _ = wt_rpos_v2(WT_RAW_X_MIN, 0)
ore_x_max_v2, _ = wt_rpos_v2(WT_RAW_X_MAX, 0)
_, ore_y_min_v2 = wt_rpos_v2(0, WT_RAW_Y_MIN)
_, ore_y_max_v2 = wt_rpos_v2(0, WT_RAW_Y_MAX)
print(f"Ore positions in-game X range: {ore_x_min_v2:.0f} to {ore_x_max_v2:.0f}")
print(f"Ore positions in-game Y range: {ore_y_min_v2:.0f} to {ore_y_max_v2:.0f}")

# These should be reasonable compared to the known alpha positions (-64..56, 731..838)
# and Sealed Sanctum at (-1979, 1361)

print("\n=== FINAL RECOMMENDATION ===")
print("Use PER_PIXEL = 459 (same as main map)")
print("WT is a separate smaller zone on its own tile set")
print("LAND_MIN_X for WT needs to be calibrated from actual MapGenie tile positions")
print("")
print("For the implementation, use a linear (non-mercator) projection for WT")
print("since it's a dungeon interior, not a spherical earth surface.")
print("Scale: 1 in-game unit = 1 pixel at some base resolution")
print("")
print("Practical approach:")
print("  - Use WT in-game coords directly as image coords (linear map)")
print("  - Define WT_MAP_WIDTH = 2800 in-game units (X: -2200 to +600)")
print("  - Define WT_MAP_HEIGHT = 1200 in-game units (Y: 600 to 1800)")
print("  - Image size = 2800 x 1200 at 1:1 scale")
print("  - Convert: imgX = gameX - WT_X_OFFSET, imgY = gameY - WT_Y_OFFSET")
print("")
print("Constants:")
WT_X_OFFSET = -2200  # in-game coord at left edge
WT_Y_OFFSET = 600    # in-game coord at top edge
WT_IMG_W = 2800      # total width in game units
WT_IMG_H = 1200      # total height in game units
print(f"  WT_X_OFFSET = {WT_X_OFFSET}")
print(f"  WT_Y_OFFSET = {WT_Y_OFFSET}")
print(f"  WT_IMG_W = {WT_IMG_W}")
print(f"  WT_IMG_H = {WT_IMG_H}")

# Verify known positions in this space:
print("\nKnown positions in tile space:")
known = [
    ("Mycora", -35, 731),
    ("Aegidron", -59, 756),
    ("Celesdir Noct", -60, 777),
    ("Moldron Cryst", -64, 816),
    ("Renjishi", 56, 838),
    ("Sealed Sanctum", -1979, 1361),
    ("WT Holy Water", -1536, 1368),
]
for name, gx, gy in known:
    ix = gx - WT_X_OFFSET
    iy = gy - WT_Y_OFFSET
    pct_x = ix / WT_IMG_W * 100
    pct_y = iy / WT_IMG_H * 100
    print(f"  {name:20} game({gx:6},{gy:5}) -> img({ix:5},{iy:5}) = ({pct_x:.1f}%, {pct_y:.1f}%)")
