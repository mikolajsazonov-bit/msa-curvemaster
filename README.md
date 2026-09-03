# MSA: CurveMaster — Wtyczka do QGIS 3.x

Wtyczka do interaktywnej korekty kształtów geometrii wektorowych (polilinii oraz poligonów) poprzez tworzenie zinterpolowanych łuków o zadanej gęstości.

---

## 🚀 Główne funkcjonalności

### 1. Wyginanie odcinka (*Bend Segment / Arc Drag*)
* **Jak używać:**
  1. Upewnij się, że warstwa liniowa lub poligonowa jest w trybie edycji (ikona ołówka).
  2. Aktywuj narzędzie **Wyginanie odcinka** na pasku narzędzi.
  3. Najedź na odcinek między dwoma węzłami (zostanie podświetlony na niebiesko).
  4. Kliknij i przeciągnij myszą — w czasie rzeczywistym pojawi się czerwony podgląd łuku.
  5. Kliknij ponownie, aby zatwierdzić zmianę geometrii.
  6. *Prawy przycisk myszy lub klawisz `Escape` anuluje operację.*

### 2. Zaokrąglanie wierzchołka (*Corner Fillet*)
* **Jak używać:**
  1. Aktywuj narzędzie **Zaokrąglanie wierzchołka** na pasku narzędzi.
  2. Najedź na wierzchołek narożnika/załamania (podświetli się punkt).
  3. **Tryb interaktywny:** Kliknij i przeciągnij myszą, aby dynamicznie ustalić promień zaokrąglenia i kliknij ponownie, aby zatwierdzić (lub wpisz wartość w okienku CAD i naciśnij `Enter`).
  4. **Tryb stałego promienia:** W menu rozwijanym lub po rozwinięciu opcji odznacz *Interaktywny*, wpisz żądany promień (np. `5.0 m`) i kliknij narożnik — zaokrąglenie zostanie wykonane natychmiastowo.

### 3. Prosty offset (*Parallel Offset Tool*) [NOWOŚĆ v1.1.0]
* **Jak używać:**
  1. Włącz tryb edycji dla warstwy liniowej lub poligonowej (do niej trafi nowo utworzony obiekt).
  2. Aktywuj narzędzie **Prosty offset** na pasku narzędzi.
  3. Najedź na obiekt (linia, polilinia lub granica poligonu z aktywnej lub widocznej warstwy) — podświetli się na niebiesko:
     - **Cały obiekt / granica:** standardowe najechanie i kliknięcie.
     - **Tylko kliknięty segment:** przytrzymaj klawisz `Ctrl` podczas najeżdżania i kliknięcia.
  4. Kliknij obiekt i odsuwaj kursor — na płótnie mapy pojawi się dynamiczny, czerwony podgląd offsetu w czasie rzeczywistym, a obok kursora pływające okienko CAD z aktualną odległością w metrach.
  5. **Zatwierdzenie:**
     - Kliknij lewym przyciskiem myszy pod żądaną odległością, **LUB**
     - Wpisz z klawiatury dokładną odległość (np. `15.0`) i naciśnij klawisz `Enter` lub `Tab`.
     - **CAD powtarzanie odległości:** Po wykonaniu jednego offsetu przy kolejnych obiektach wystarczy wskazać myszą stronę i nacisnąć `Enter` lub `Tab` — offset zostanie natychmiast utworzony z poprzednią zadaną odległością!
  6. Zostanie narysowany nowy obiekt w aktywnej warstwie edytowalnej.
  7. *Prawy przycisk myszy lub klawisz `Escape` anuluje operację.*

---

### 4. Rysowanie z Polar Trackingiem (*CAD Polar Digitize*) [NOWOŚĆ v1.2.0]
* **Jak używać:**
  1. Włącz tryb edycji dla warstwy liniowej lub poligonowej.
  2. Aktywuj narzędzie **Rysuj z Polar Trackingiem** na pasku narzędzi.
  3. **Wybór punktu początkowego $V_0$:**
     - Kliknij w dowolnym miejscu mapy, **LUB**
     - Najedź na istniejącą linię lub granicę poligonu — krawędź podświetli się na błękitno, a jej azymut w terenie zostanie automatycznie zablokowany jako baza $0^\circ$!
  4. **Śledzenie biegunowe (AutoCAD-style):**
     - Przesuwając myszą, narzędzie wyświetla zielony promień prowadzący (`Qt.DashLine`) w chwili zbliżenia do zadanego kąta (np. 15°, 30°, 45°, 90°).
     - Kąt $90^\circ$ względem krawędzi początkowej wyznacza idealną prostopadłą (kąt prosty), a $180^\circ$ – idealną równoległą.
  5. **Odmierzanie odległości (CAD Overlay):**
     - W pływającym okienku obok kursora wpisz z klawiatury żądaną długość (np. `25`) i naciśnij `Enter` lub `Tab` — wierzchołek zostanie natychmiast postawiony na zadaną odległość wzdłuż przyciągniętego promienia!
     - Alternatywnie kliknij lewym przyciskiem myszy, aby postawić wierzchołek w bieżącej pozycji.
  6. **Korekta i zakończenie:**
     - Klawisz `Backspace` cofa ostatnio postawiony wierzchołek.
     - `Prawy przycisk myszy` lub klawisz `Enter` kończy rysowanie i tworzy obiekt w aktywnej warstwie (dla poligonów następuje automatyczne domknięcie obrysu).
* **Asystent w tle (dla narzędzi QGIS):**
  - Włączenie Polar Trackingu synchronizuje krok kąta w tle z mechanizmem Zaawansowanej Digitalizacji QGIS. Dzięki temu standardowe narzędzia QGIS **Zmień kształt** (`Reshape`) oraz **Rozdziel obiekty** (`Split`) również korzystają z przyciągania do kątów bez otwierania ciężkiego panelu dokującego.

---

## 📐 Kompaktowy pasek narzędzi i rozwijane menu

Pasek narzędzi wtyczki został zoptymalizowany pod kątem oszczędności miejsca:
* **Stan spoczynku:** Na pasku widoczne są 4 zwięzłe ikony narzędzi: `[Wygnij]`, `[Zaokrąglij]`, `[Offset]`, `[Polar]`.
* **Rozwijane menu pod przyciskami (strzałka MenuButtonPopup):**
  - **Wygnij odcinek & Zaokrąglij wierzchołek:** Szybki wybór metody próbkowania i opcji.
  - **Prosty offset:** Wybór zakresu wykrywanych obiektów (wszystkie, tylko linie, tylko aktywna warstwa).
  - **Polar Tracking:** Włącznik śledzenia, wybór kroku kąta (11 presetów), pomiar kąta (Względny do krawędzi vs Bezwzględny) oraz okno dialogowe własnych kątów (*Additional angles* np. 147°).
* **Automatyczne rozwijanie parametrów:** Po aktywacji danego narzędzia pasek automatycznie rozwija odpowiednie dla niego kontrolki, a po wyłączeniu narzędzia natychmiast zwija je z powrotem.

## ⚙️ Tryby próbkowania łuku (Dyskretyzacja)

W podręcznym pasku narzędzi dostępny jest wybór jednego z 3 trybów próbkowania:

1. **Długość odcinka (m):**
   * Dzieli łuk na równe proste odcinki o długości nieprzekraczającej zadanej wartości (np. co `1.0 m`, `5.0 m`).
   * Posiada wbudowany bezpiecznik (min. 4 segmenty), aby małe łuki nie zostały spłaszczone.
2. **Krok kątowy (°):**
   * Dzieli kąt środkowy łuku co zadaną liczbę stopni (np. `5.0°`, `10.0°`).
   * Zapewnia stałą, idealną gładkość wizualną niezależnie od promienia łuku.
3. **Maksymalna odchyłka / Strzałka ugięcia (m):**
   * Metoda inżynierska CAD/GIS — dobiera liczbę segmentów tak, aby odchylenie cięciwy od idealnego okręgu nie przekroczyło zadanej tolerancji (np. `0.02 m` = 2 cm).

---

## 🛠️ Instalacja w QGIS

1. Skopiuj folder `msa_curvemaster` do katalogu wtyczek QGIS:
   * **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   * **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   * **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
2. Uruchom lub zrestartuj QGIS.
3. Otwórz menu `Wtyczki` -> `Zarządzaj wtyczkami...` -> w zakładce `Zainstalowane` zaznacz **MSA: CurveMaster**.
4. Pasek narzędzi wtyczki pojawi się w oknie głównym QGIS.

---

## ↩️ Pełne wsparcie transakcji (Undo / Redo)

Każda operacja wykonana za pomocą wtyczki integruje się z systemem historii edycji QGIS (`Ctrl + Z` / `Ctrl + Y` lub `Cmd + Z` / `Cmd + Y` na macOS).

---

## 👨‍💻 Autor
* **Mikołaj Sazonov**
* Projekt wykonany w ramach prac dyplomowych / badań Urban & Transport (UiT).
