"""
Calculate the World Tree coordinate projection.

Known in-game coordinates (from wiki.gg and allthings.how):
  Sealed Sanctum fast travel:    (-1979, 1361)
  World Tree Holy Water item:    (-1536, 1368)
  Mycora alpha pal:              (-35,    731)
  Aegidron alpha pal:            (-59,    756)
  Celesdir Noct alpha pal:       (-60,    777)
  Moldron Cryst alpha pal:       (-64,    816)
  Renjishi alpha pal:            (56,     838)

Raw OP.GG Unreal Engine coordinates for WorldTreeOre:
  X range: 408215 to 627885
  Y range: -753512 to -521557

The main map uses:
  LAND_MIN = (-1099400, -724400)
  LAND_MAX  = ( 349400,  724400)
  PER_PIXEL = 459.0
  INGAME_X_START = 1000 + (-582888 - LAND_MIN[0]) / PER_PIXEL
  INGAME_Y_START = 1000 + (-301000 - LAND_MIN[1]) / PER_PIXEL

We need to find the World Tree map's equivalent constants.
Strategy: use the known in-game coords as anchors to calibrate the WT projection.
"""

import json
import pathlib

# Known in-game coordinates for World Tree locations
KNOWN_INGAME = {
    "Mycora":        (-35,   731),
    "Aegidron":      (-59,   756),
    "Celesdir Noct": (-60,   777),
    "Moldron Cryst": (-64,   816),
    "Renjishi":      (56,    838),
    "Sealed Sanctum":(-1979, 1361),
}

# Main map projection constants
MAIN_LAND_MIN = (-1099400.0, -724400.0)
MAIN_LAND_MAX = (349400.0, 724400.0)
MAIN_PER_PIXEL = 459.0
MAIN_INGAME_X_START = 1000.0 + (-582888.0 - MAIN_LAND_MIN[0]) / MAIN_PER_PIXEL
MAIN_INGAME_Y_START = 1000.0 + (-301000.0 - MAIN_LAND_MIN[1]) / MAIN_PER_PIXEL

print("=== Main map projection ===")
print(f"  INGAME_X_START = {MAIN_INGAME_X_START:.3f}")
print(f"  INGAME_Y_START = {MAIN_INGAME_Y_START:.3f}")
print(f"  Map width (pixels): {(MAIN_LAND_MAX[0]-MAIN_LAND_MIN[0])/MAIN_PER_PIXEL:.0f}")
print(f"  Map height (pixels): {(MAIN_LAND_MAX[1]-MAIN_LAND_MIN[1])/MAIN_PER_PIXEL:.0f}")

# Load World Tree Ore raw Unreal coords
data_path = pathlib.Path(__file__).parent / "data" / "opgg_mine.json"
if data_path.exists():
    data = json.loads(data_path.read_text())
    wt_pts = data.get("points", {}).get("WorldTreeOre", [])
    wt_locs = [r["l"] for r in wt_pts if r.get("l") and len(r["l"]) >= 2]
    wt_raw_x = [float(l[0]) for l in wt_locs]
    wt_raw_y = [float(l[1]) for l in wt_locs]
    
    print(f"\n=== World Tree Ore raw Unreal coordinates ===")
    print(f"  X range: {min(wt_raw_x):.0f} to {max(wt_raw_x):.0f}")
    print(f"  Y range: {min(wt_raw_y):.0f} to {max(wt_raw_y):.0f}")
    print(f"  Center: ({(min(wt_raw_x)+max(wt_raw_x))/2:.0f}, {(min(wt_raw_y)+max(wt_raw_y))/2:.0f})")
    
    # The World Tree Ore clusters are scattered across the map
    # The in-game coordinates span roughly:
    # X: -2000 to +500 (based on Sealed Sanctum at -1979 and Renjishi at +56)
    # Y: 700 to 1400 (based on alpha pals and Sealed Sanctum)
    
    # Calculate scale: WT_raw_range / WT_ingame_range
    # In-game X range from known data: -1979 to +56 ~ 2035 units
    # In-game Y range from known data: 731 to 1368 ~ 637 units (but probably more)
    
    # Use the main map's PER_PIXEL as a starting point
    # but scale it by the ratio of raw coord extents
    # Main raw X range: LAND_MAX[0]-LAND_MIN[0] = 349400 - (-1099400) = 1448800
    # WT raw X range: 627885 - 408215 = 219670
    # This only covers ore positions, not the full map extent
    
    wt_raw_width = max(wt_raw_x) - min(wt_raw_x)
    wt_raw_height = max(wt_raw_y) - min(wt_raw_y)
    
    print(f"\n  WT Ore spread: {wt_raw_width:.0f} x {wt_raw_height:.0f}")
    
    # Main map: 1448800 unreal units -> ~3157 in-game units wide
    # Scale per unreal unit for main map: 3157 / 1448800 = 0.002179
    main_scale_x = (MAIN_INGAME_X_START * 2) / (MAIN_LAND_MAX[0] - MAIN_LAND_MIN[0])
    main_ingame_range_x = (MAIN_LAND_MAX[0] - MAIN_LAND_MIN[0]) / MAIN_PER_PIXEL
    main_ingame_range_y = (MAIN_LAND_MAX[1] - MAIN_LAND_MIN[1]) / MAIN_PER_PIXEL
    
    print(f"\n  Main map in-game coord range: {main_ingame_range_x:.1f} x {main_ingame_range_y:.1f}")
    
    # Estimate WT PER_PIXEL assuming same unreal-to-ingame scale
    # If PER_PIXEL_WT = PER_PIXEL_MAIN = 459, then we can calculate WT LAND bounds
    # from the known in-game coords and the known raw coords
    
    # From Ore data + known in-game range:
    # The WT zone seems to have:
    #   In-game X: roughly -2000 to +500 (2500 units wide)
    #   In-game Y: roughly 700 to 1400 (700 units tall, but likely larger)
    
    # Try to figure out WT LAND_MIN/MAX by using same PER_PIXEL
    # WT raw center: (518050, -637535)
    # If in-game 0,0 is at some offset...
    # Using the main map formula: ingame = (raw - LAND_MIN) / PER_PIXEL - INGAME_START + 1000
    
    # Let's find WT LAND_MIN_X such that the ore positions map correctly
    # We know Mycora is at in-game (-35, 731) but we don't know its Unreal coords yet
    
    print("\n=== Attempting reverse calibration ===")
    print("  Using main-map PER_PIXEL=459 as starting assumption...")
    
    # The WT uses same PER_PIXEL assumption:
    # ingame_x = (raw_x - WT_LAND_MIN_X) / 459 - WT_INGAME_X_START + 1000
    # ingame_y = (raw_y - WT_LAND_MIN_Y) / 459 - WT_INGAME_Y_START + 1000
    
    # Without known raw <-> ingame pairs for WT, we can't solve this exactly.
    # However, the ore data center suggests WT center raw ~ (518050, -637535)
    
    wt_center_raw_x = (min(wt_raw_x) + max(wt_raw_x)) / 2
    wt_center_raw_y = (min(wt_raw_y) + max(wt_raw_y)) / 2
    
    print(f"  WT Ore raw center: ({wt_center_raw_x:.0f}, {wt_center_raw_y:.0f})")
    
    # Load eggs data for more data points
    eggs_path = pathlib.Path(__file__).parent / "data" / "opgg_eggs.json"
    if eggs_path.exists():
        eggs_data = json.loads(eggs_path.read_text())
        egg_pts = eggs_data.get("points", {}).get("Eggs", [])
        wt_eggs = [r for r in egg_pts if r.get("t") == "worldTree"]
        wt_egg_locs = [r["l"] for r in wt_eggs if r.get("l") and len(r["l"]) >= 2]
        if wt_egg_locs:
            ex = [float(l[0]) for l in wt_egg_locs]
            ey = [float(l[1]) for l in wt_egg_locs]
            print(f"\n=== World Tree Eggs raw coords ===")
            print(f"  Count: {len(wt_egg_locs)}")
            print(f"  X range: {min(ex):.0f} to {max(ex):.0f}")
            print(f"  Y range: {min(ey):.0f} to {max(ey):.0f}")
            all_wt_x = wt_raw_x + ex
            all_wt_y = wt_raw_y + ey
            print(f"\n  Combined WT raw extent: X {min(all_wt_x):.0f}..{max(all_wt_x):.0f}  Y {min(all_wt_y):.0f}..{max(all_wt_y):.0f}")
    
    print("\n=== Summary for implementation ===")
    print("The World Tree zone is a separate coordinate space.")
    print("Raw Unreal X: ~408000 to ~630000")
    print("Raw Unreal Y: ~-755000 to ~-520000")
    print("")
    print("In-game known positions:")
    for name, (x, y) in KNOWN_INGAME.items():
        print(f"  {name}: ({x}, {y})")
    print("")
    print("These in-game coords (X: -2000 to +500, Y: 700 to 1400) confirm")
    print("this is a completely different coordinate space from Palpagos.")
    print("A dedicated map projection is needed.")
