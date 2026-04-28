#!/usr/bin/env python3
r"""manual_ae_classifications.py — Hand-curated category map for the 106
items that fix_stock_ae_items.py's keyword rules couldn't classify.

Decisions made by the assistant from folder names + general knowledge of
AE template / plugin naming conventions (no DeepSeek round-trip).

Usage:
    python manual_ae_classifications.py --apply
    python manual_ae_classifications.py --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent
RESULTS = REPO / "fix_stock_ae_results.json"

# folder_name → (canonical category, clean_name | None to keep folder_name)
MANUAL: dict[str, tuple[str, str | None]] = {
    # ── Cinematic FX & Overlays (visual FX overlays, muzzle flashes, glass)
    "Cracked Glass Effect":             ("Cinematic FX & Overlays", None),
    "Front Gun Muzzle Flashes":         ("Cinematic FX & Overlays", None),
    "Rifle Front Muzzle Flashes":       ("Cinematic FX & Overlays", None),
    "Premium Overlays Dust Smoke":      ("Cinematic FX & Overlays", "Premium Overlays - Dust & Smoke"),
    "BAT PACK 2":                       ("Cinematic FX & Overlays", None),

    # ── Plugins & Extensions (every BAO/aescripts plugin and similar)
    "AI Color Match":                   ("Plugins & Extensions", None),
    "DeepClear":                        ("Plugins & Extensions", None),
    "Auto Crop":                        ("Plugins & Extensions", None),
    "BAO Bones V1.5.10":                ("Plugins & Extensions", "BAO Bones"),
    "BAO Layer Sculptor v1.2.2":        ("Plugins & Extensions", "BAO Layer Sculptor"),
    "BAO Mask Avenger 2.7.5":           ("Plugins & Extensions", "BAO Mask Avenger"),
    "BG Renderer MAX":                  ("Plugins & Extensions", None),
    "Blace AI Face Detection":          ("Plugins & Extensions", None),
    "BRAW Studio v3.0.4":               ("Plugins & Extensions", "BRAW Studio"),
    "Buena Depth Cue v2.5.8":           ("Plugins & Extensions", "Buena Depth Cue"),
    "Captioneer":                       ("Plugins & Extensions", None),
    "Cell Division":                    ("Plugins & Extensions", None),
    "Circle Rig Pro":                   ("Plugins & Extensions", None),
    "Color Shift v1.0.3":               ("Plugins & Extensions", "Color Shift"),
    "CompsFromSpreadsheet":             ("Plugins & Extensions", None),
    "Deep Glow v1.6":                   ("Plugins & Extensions", "Deep Glow"),
    "Diffusae":                         ("Plugins & Extensions", None),
    "EasyRulers":                       ("Plugins & Extensions", None),
    "Fast Camera Lens Blur":            ("Plugins & Extensions", None),
    "Find My AEP V2.6":                 ("Plugins & Extensions", "Find My AEP"),
    "Geometric Filter v1.2.0":          ("Plugins & Extensions", "Geometric Filter"),
    "GeoTracker 2024.2.0 Win":          ("Plugins & Extensions", "GeoTracker"),
    "Lockdown v3.1.0":                  ("Plugins & Extensions", "Lockdown"),
    "Look Designer V3.1.1":             ("Plugins & Extensions", "Look Designer"),
    "m's Halftone v150":                ("Plugins & Extensions", "m's Halftone"),
    "MB Plotter 1.0":                   ("Plugins & Extensions", "MB Plotter"),
    "Memleak v1.1.1 Win":               ("Plugins & Extensions", "Memleak"),
    "MonkeyCam Pro v1.09":              ("Plugins & Extensions", "MonkeyCam Pro"),
    "Motion v4.3.4.4708":               ("Plugins & Extensions", "Motion (mt-mograph)"),
    "Optical Flow Creator Essentials Bundle": ("Plugins & Extensions", None),
    "Pixel Encoder":                    ("Plugins & Extensions", None),
    "Pixel Stretch":                    ("Plugins & Extensions", None),
    "Pixelfan":                         ("Plugins & Extensions", None),
    "Quick Depth v2.1.5":               ("Plugins & Extensions", "Quick Depth"),
    "Rubberhose 3.1.0":                 ("Plugins & Extensions", "Rubberhose"),
    "Shadow Studio 3":                  ("Plugins & Extensions", None),
    "ShapeMonkey":                      ("Plugins & Extensions", None),
    "Signal":                           ("Plugins & Extensions", None),
    "Soft Body 2.0":                    ("Plugins & Extensions", "Soft Body"),
    "Split Blur v1.3.2":                ("Plugins & Extensions", "Split Blur"),
    "Stipple":                          ("Plugins & Extensions", None),
    "StyleX V1.0.2.2":                  ("Plugins & Extensions", "StyleX"),
    "Super Shine v1.0":                 ("Plugins & Extensions", "Super Shine"),
    "Superluminal Stardust v1.6.0c Win":("Plugins & Extensions", "Superluminal Stardust"),
    "SuperposeAE v2.2":                 ("Plugins & Extensions", "SuperposeAE"),
    "Time Bend V1.0.1":                 ("Plugins & Extensions", "Time Bend"),
    "AE Face Tools":                    ("Plugins & Extensions", None),
    "LINGO PACK V3 DELUXE":             ("Plugins & Extensions", "Lingo Pack v3 Deluxe"),
    "Designer Sound FX":                ("Sound Effects & SFX", None),

    # ── AE - Logo Reveal
    "Backward Logo Timelapse":          ("After Effects - Logo Reveal", None),

    # ── AE - Title & Typography (Type kits)
    "Tropic Colour CRT Type Kit":       ("After Effects - Title & Typography", None),

    # ── AE - Slideshow (slides templates)
    "Slides for Life":                  ("After Effects - Slideshow", None),
    "Simple Slides Gfxtra Simple Slides": ("After Effects - Slideshow", "Simple Slides"),
    "Quick Slides":                     ("After Effects - Slideshow", None),

    # ── AE - Motion Graphics Pack (shape packs)
    "Shapes and Lines":                 ("After Effects - Motion Graphics Pack", None),
    "Fun Shapes":                       ("After Effects - Motion Graphics Pack", None),
    "Fusion Shapes":                    ("After Effects - Motion Graphics Pack", None),

    # ── AE - Product Promo (food / menu / restaurant promos)
    "Menu Restaurant Cooking":          ("After Effects - Product Promo", None),
    "Cook With Us Cooking Pack":        ("After Effects - Product Promo", None),
    "Food Menu Food Menu":              ("After Effects - Product Promo", "Food Menu"),
    "Street Food":                      ("After Effects - Product Promo", None),
    "Delicious Food":                   ("After Effects - Product Promo", None),
    "Cutting and Displaying Foods AE Templates": ("After Effects - Product Promo", "Cutting and Displaying Foods"),
    "Food Menu":                        ("After Effects - Product Promo", None),
    "Electronic Menu Display":          ("After Effects - Product Promo", None),
    "Glossy Magazine":                  ("After Effects - Product Promo", None),

    # ── AE - Corporate & Business (themed business/services/fashion AE promos)
    "Beach":                            ("After Effects - Corporate & Business", None),
    "Beauty, Fashion, Spa":             ("After Effects - Corporate & Business", None),
    "IT Services Flyer":                ("After Effects - Corporate & Business", None),
    "Fitness, Gym":                     ("After Effects - Corporate & Business", None),
    "Discover the Difference Discover the Difference": ("After Effects - Corporate & Business", "Discover the Difference"),
    "Discover the Difference":          ("After Effects - Corporate & Business", None),
    "Retirement Home":                  ("After Effects - Corporate & Business", None),

    # ── AE - Wedding & Romance
    "High End Greeting Card":           ("After Effects - Wedding & Romance", None),
    "Anniversary":                      ("After Effects - Wedding & Romance", None),
    "It's Your Birthday":               ("After Effects - Wedding & Romance", None),
    "P5 Hearts Love":                   ("After Effects - Wedding & Romance", None),
    "Ceremony":                         ("After Effects - Wedding & Romance", None),

    # ── AE - Christmas & Holiday (every named holiday/seasonal item)
    "Memorial Day":                     ("After Effects - Christmas & Holiday", None),
    "Colorful Ramadan":                 ("After Effects - Christmas & Holiday", None),
    "Day Of The Dead":                  ("After Effects - Christmas & Holiday", None),
    "Mothers Day Share AE Com Aftereffects Cc13": ("After Effects - Christmas & Holiday", "Mothers Day"),
    "Xmas I Ds Xmas I Ds Universilizer":("After Effects - Christmas & Holiday", "Xmas IDs Universilizer"),
    "Travel Postcard":                  ("After Effects - Map & Location", None),

    # ── AE - Other (book/year-book — no specific subcat fits)
    "Book Cover":                       ("After Effects - Other", None),
    "Books":                            ("After Effects - Other", None),
    "My Golden Book":                   ("After Effects - Other", None),
    "My Life My Rules":                 ("After Effects - Other", None),
    "Year Book":                        ("After Effects - Other", None),
    "Minimal Resume":                   ("After Effects - Corporate & Business", None),
    "Golden Fortune":                   ("After Effects - Other", None),

    # ── AE - Other / unknown VH templates (no clear subject)
    "VideoHive One View 21991027 - One View":      ("After Effects - Other", "One View"),
    "VH-23360402 - AB_blue (CS5.5)":               ("After Effects - Other", None),
    "VH-3536887 - BLUE":                           ("After Effects - Other", None),
    "Ultimate Ocean for Credits":                  ("After Effects - Title & Typography", None),
    "VideoHive Historical Outstanding People 21972677 - Historical - Outstanding People":
                                                   ("After Effects - Cinematic & Film",
                                                    "Historical - Outstanding People"),
    "VH-9019611 - Points_In_Time_CS6":             ("After Effects - Other", "Points In Time"),
    "Videohive Hot Time 22870273 - Hot Time":      ("After Effects - Other", "Hot Time"),
    "Summer & Tropical":                           ("After Effects - Other", None),
    "Video Editing General":                       ("After Effects - Other", None),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Patch fix_stock_ae_results.json in place")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change without writing")
    args = ap.parse_args()

    if not (args.apply or args.dry_run):
        ap.print_help()
        return

    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    patched = unmatched = already = 0
    still_manual: list[str] = []

    for r in results:
        if r.get("method") != "manual_review":
            continue
        name = r["folder_name"]
        if name in MANUAL:
            cat, clean = MANUAL[name]
            if not args.dry_run:
                r["new_category"] = cat
                r["clean_name"] = clean or name
                r["confidence"] = 80
                r["method"] = "manual_curation"
            patched += 1
        else:
            still_manual.append(name)
            unmatched += 1

    if not args.dry_run:
        RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                           encoding="utf-8")

    print(f"Patched: {patched}, still unmatched: {unmatched}")
    if still_manual:
        print("\nStill manual:")
        for n in still_manual:
            print(f"  {n}")


if __name__ == "__main__":
    main()
