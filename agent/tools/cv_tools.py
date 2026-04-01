import cv2
import numpy as np
import json
import workspace as ws
from pathlib import Path

def _get_image_path(filename: str) -> Path:
    """Szuka pliku w output/ i cache/ workspace'u.
    Akceptuje nazwy z opcjonalnym prefixem 'cache/' lub 'output/'."""
    # Odetnij potencjalny prefix podkatalogu, który mógł przekazać agent
    for prefix in ("cache/", "output/", "cache\\", "output\\"):
        if filename.startswith(prefix):
            filename = filename[len(prefix):]
            break
    for subdir in ("output", "cache"):
        path = ws.root() / subdir / filename
        if path.exists():
            return path
    raise FileNotFoundError(f"Nie znaleziono obrazu: {filename}")

def split_image_grid(filename: str, rows: int, cols: int, prefix: str = "tile", auto_crop: bool = True) -> str:
    """
    Znajduje główny obszar na obrazie i dzieli go na siatkę R x C.
    Zapisuje wycięte fragmenty do katalogu output/ z podanym prefixem.
    """
    try:
        path = _get_image_path(filename)
        img = cv2.imread(str(path))
        if img is None:
            return f"BŁĄD: Nie można zdekodować obrazu {filename}."

        # Opcjonalne: automatyczne przycięcie do największego obiektu (np. samej tabeli/siatki)
        if auto_crop:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Binaryzacja (zakładamy ciemne linie na jasnym tle)
            _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if contours:
                # Bierzemy największy kontur (zazwyczaj jest to nasza siatka)
                c = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(c)
                img = img[y:y+h, x:x+w]

        # Podział na grid
        h, w = img.shape[:2]
        cell_h = h // rows
        cell_w = w // cols
        
        saved_files = []
        for r in range(rows):
            for c in range(cols):
                tile = img[r*cell_h : (r+1)*cell_h, c*cell_w : (c+1)*cell_w]
                
                # Ucięcie 5 pikseli z każdej strony, aby pozbyć się czarnych krawędzi siatki
                margin = 5
                th, tw = tile.shape[:2]
                if th > 2*margin and tw > 2*margin:
                    tile = tile[margin:th-margin, margin:tw-margin]
                
                # Zapis fragmentu
                out_name = f"{prefix}_{r+1}x{c+1}.png"
                out_path = ws.root() / "output" / out_name
                cv2.imwrite(str(out_path), tile)
                saved_files.append(out_name)
                
        ws.log("CV_SPLIT_GRID", f"Podzielono {filename} na {rows}x{cols} z prefixem {prefix}")
        return json.dumps({"status": "sukces", "saved_files": saved_files}, ensure_ascii=False)
        
    except Exception as e:
        return f"BŁĄD CV: {str(e)}"

def compare_image_rotations(target_file: str, source_file: str) -> str:
    """
    Porównuje piksel po pikselu obraz 'target' z obrazem 'source'.
    Obraca 'source' o 0, 90, 180, 270 stopni i zwraca informację, 
    który obrót w prawo daje najmniejszą różnicę.
    """
    try:
        p_tgt = _get_image_path(target_file)
        p_src = _get_image_path(source_file)
        
        tgt = cv2.imread(str(p_tgt), cv2.IMREAD_GRAYSCALE)
        src = cv2.imread(str(p_src), cv2.IMREAD_GRAYSCALE)
        
        if tgt is None or src is None:
            return "BŁĄD: Brak obrazu do wczytania."

        best_rot = 0
        min_diff = float('inf')
        
        for rot in range(4):
            if rot == 0:
                t_rot = src
            elif rot == 1:
                t_rot = cv2.rotate(src, cv2.ROTATE_90_CLOCKWISE)
            elif rot == 2:
                t_rot = cv2.rotate(src, cv2.ROTATE_180)
            elif rot == 3:
                t_rot = cv2.rotate(src, cv2.ROTATE_90_COUNTERCLOCKWISE)
                
            # Wyrównanie wymiarów w razie różnic 1-2 px przy podziale
            t_rot = cv2.resize(t_rot, (tgt.shape[1], tgt.shape[0]))
            
            # Sum of Absolute Differences (SAD)
            diff = np.sum(np.abs(tgt.astype(float) - t_rot.astype(float)))
            
            if diff < min_diff:
                min_diff = diff
                best_rot = rot
                
        ws.log("CV_COMPARE", f"Zbadano {target_file} vs {source_file} -> {best_rot} obrotów")
        return json.dumps({
            "target": target_file, 
            "source": source_file, 
            "required_clockwise_rotations": best_rot
        })
        
    except Exception as e:
        return f"BŁĄD CV: {str(e)}"

DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "split_image_grid",
            "description": (
                "Pobiera obraz z zapisanego pliku, znajduje na nim główny obszar (np. siatkę) "
                "i tnie go na podaną liczbę wierszy (rows) i kolumn (cols). "
                "Zapisuje kawałki do plików o nazwach {prefix}_{r}x{c}.png."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa pliku z cache/ lub output/"},
                    "rows": {"type": "integer", "description": "Liczba wierszy"},
                    "cols": {"type": "integer", "description": "Liczba kolumn"},
                    "prefix": {"type": "string", "description": "Prefiks zapisywanych plików, np. 'solved' lub 'current'"},
                    "auto_crop": {"type": "boolean", "description": "Czy automatycznie dociąć do zawartości", "default": True}
                },
                "required": ["filename", "rows", "cols", "prefix"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_image_rotations",
            "description": (
                "Porównuje dwa obrazy o podobnej treści. Zwraca informację, "
                "o ile obrotów o 90 stopni W PRAWO należy obrócić 'source_file', "
                "aby wyglądał tak jak 'target_file'. Zwraca JSON z kluczem 'required_clockwise_rotations'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_file": {"type": "string", "description": "Plik docelowy (wzór)"},
                    "source_file": {"type": "string", "description": "Plik wejściowy (do obrócenia)"}
                },
                "required": ["target_file", "source_file"]
            },
        },
    }
]
