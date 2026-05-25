# Orca-Style PA-Pattern Layout (Spec)

**Status:** Implementiert in Task 2-11.

## Anforderungen (aus User-Befunden 2026-05-25)

1. **Frame um Chevrons**: umlaufender Rahmen mit `wall_count`
   konzentrischen Wandlinien, KEIN Infill. Aktuell ist es ein
   "[" 2-Linien-Frame (links + unten). Soll wie Orca's `draw_box`
   mit `is_filled=false` werden.

2. **Top-Bar**: oberhalb des Frames mit ~0.5 mm Lücke; gleiche
   X-Breite wie Frame. Innen `wall_count` Perimeter + 45°-Infill
   (solide gefüllt). Soll wie Orca's `draw_box` mit
   `is_filled=true`. Aktuell ist es Boustrophedon-Stadion-Linien
   (diagonal-streifig im Slicer-Preview).

3. **Labels**: pro Chevron ein PA-Label. Position:
   - X = `glyph_start_x(j)` (zentriert über dem Chevron-Anker
     am oberen Frame-Rand, NICHT über der Chevron-Mitte)
   - Y = Top-Bar-Bottom + glyph_padding (= AUF der Top-Bar als
     Relief)
   - Rotation 90° (hochkant, Lesrichtung von oben nach unten)
   - Aktive PA = 0 (separates SET_PRESSURE_ADVANCE vor Labels)
   - Speed = `first_layer_speed` (langsam für saubere Glyphen)

4. **Settings (Flow, Accel)**: nach den PA-Labels rechts auf
   derselben Top-Bar. X-Position via `glyph_start_x(num_patterns
   + 2)` für Flow und `glyph_start_x(num_patterns + 4)` für Accel
   (= 2 bzw. 4 Slots nach dem letzten PA-Label).

5. **Anker-Marker entfällt**: Orca hat keinen separaten Asymmetrie-
   Anker. Der Frame selbst ist asymmetrisch durch die nur-oben
   liegende Top-Bar.

6. **Layer-Verteilung**:
   - Frame + Top-Bar nur in Layer 0 (Z=0.2)
   - Labels nur in Layer 1 (Z=0.4)
   - Chevrons in jedem Layer (4× wiederholt)

7. **Pattern-Geometrie unverändert**: wall_side_length=30 mm,
   pattern_spacing=18 mm, pa_step=0.005, pa_end=0.04 wie v4.

## Geometrische Konstanten

Aus `reference/orca_reference.gcode` extrahiert:
- `line_spacing = line_width − layer_height × (1 − π/4)`
  (Versatz zwischen Perimetern, auch zwischen Frame-Top und
  Top-Bar-Bottom)
- `spacing_45 = line_spacing / sin(45°)`
  (Infill-Linien-Abstand im 45°-Pattern)
- `pattern_shift = (wall_count−1) × line_spacing + line_width +
  glyph_padding_horizontal`
  (Padding vor erstem Chevron, für Labels-Platz)
