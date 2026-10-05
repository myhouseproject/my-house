# Oficjalne modele 3D producenta Omnires (seria Y)

Katalog zawiera oficjalne pliki CAD / BIM pobrane bezpośrednio z portalu producenta Omnires dla architektów i projektantów wnętrz.

## Zawartość katalogu

1. **`Y1233BSB/`**: Bateria wannowa wolnostojąca wysoka z rączką prysznicową (wykończenie: mosiądz szczotkowany BSB)
   - Formaty: `.obj`, `.mtl`, `.fbx`, `.3ds`, `.dwg`, wizualizacje producenta `.jpg`
2. **`Y1212BSB/`**: Bateria umywalkowa wysoka (nablatowa) (wykończenie: mosiądz szczotkowany BSB)
   - Formaty: `.obj`, `.mtl`, `.fbx`, `.3ds`, `.dwg`, wizualizacje producenta `.jpg`
3. **`Y1244SUBSB/`**: Termostatyczny system prysznicowy natynkowy (wykończenie: mosiądz szczotkowany BSB)
   - Formaty: `.obj`, `.mtl`, `.fbx`, `.3ds`, `.dwg`, wizualizacje producenta `.jpg`
4. **`SYSYBI2BSB/`**: System bidetowy podtynkowy z rączką BIDETTA2-RBSB (wykończenie: mosiądz szczotkowany BSB)
   - Formaty: `.obj`, `.mtl`, `.fbx`, `.3ds`, `.dwg`, wizualizacje producenta `.jpg`

## Uwagi dotyczące integracji z modelem sceny WebGL

- Surowe pliki CAD producenta posiadają łącznie ponad 540 000 ścianek, liczne niepołączone komponenty wewnętrzne oraz otwarte krawędzie nie spełniające wymogu bryłowości (`is_watertight`).
- W modelu sceny przeglądarkowej (`bathroom_geometry.py`) wykorzystano precyzyjne cyfrowe bliźniaki zachowujące identyczne wymiary, proporcje, profile wylewek i osprzęt, przy zapewnieniu pełnej szczelności bryłowej (`is_watertight == True`) i budżetu poniżej 40 000 trójkątów dla płynnego działania 60 FPS w WebGL.
