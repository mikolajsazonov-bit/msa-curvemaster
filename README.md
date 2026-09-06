# MSA: CurveMaster 📐🪣

**MSA: CurveMaster** to zaawansowany zestaw precyzyjnych narzędzi inżynierskich CAD dla **QGIS 3.x**, stworzony z myślą o projektantach dróg, architektach krajobrazu, urbanistach i inżynierach GIS. Przenosi ergonomię i płynność pracy znaną z programów AutoCAD czy MicroStation bezpośrednio do środowiska QGIS.

> **GitHub Repository About / Description:**  
> *EN:* CAD engineering toolkit for QGIS: interactive corner/two-line fillet rounding, AutoCAD-style Trim/Extend, parallel offset, Polar Tracking digitizing, and CAD Smart Pour pavement filling between curbs with auto-merge and live styling sync.  
> *PL:* Inżynierski zestaw narzędzi CAD dla QGIS: zaokrąglanie łukami (fillet), docinanie i wydłużanie (Trim/Extend), offset równoległy, rysowanie z Polar Trackingiem oraz interaktywne wylewanie nawierzchni (Smart Pour) między krawężnikami z automatycznym scalaniem.

---

### ✨ Główne moduły i funkcjonalności:
* **🪣 CAD Smart Pour (Zalej nawierzchnię):** interaktywne wypełnianie poligonami korytarzy i przestrzeni między krawężnikami w skali 1:500 z dynamicznym promieniem odcięcia, automatycznym scalaniem (*Auto-Merge*) nawierzchni tej samej kategorii, bezpośrednią synchronizacją ze stylizacją warstwy oraz elastycznym wyborem atrybutu kategoryzacji.
* **🎯 Zaokrąglanie i łuki (Fillet):** dynamiczne wyginanie segmentów w łuki oraz zaokrąglanie narożników obiektów i dwóch niezależnych linii z automatycznym docinaniem i podglądem na żywo.
* **✂️ Trim / Extend:** szybkie docinanie i wydłużanie linii do krawędzi obiektów z dowolnych warstw projektu (dokładnie jak w AutoCAD).
* **📐 Prosty offset równoległy:** dynamiczny podgląd odsunięcia z zapamiętywaniem zadanej odległości CAD i błyskawicznym powtarzaniem operacji.
* **🧭 Rysowanie z Polar Trackingiem:** precyzyjna digitalizacja ze śledzeniem kątów biegunowych (np. 15°, 45°, 90°) i blokowaniem azymutu krawędzi odniesienia.
* **⌨️ Pływające nakładki CAD HUD:** wprowadzanie precyzyjnych wartości (promienie, odległości, kąty) bezpośrednio z klawiatury w trakcie rysowania.
* **↩️ Pełna obsługa Undo/Redo:** bezpieczna obsługa transakcji i edycji geometrii bez kolizji kluczy `fid` (zgodność z GeoPackage, PostGIS, Shapefile).

---

## 🚀 Opis szczegółowy narzędzi

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
  3. **Tryb interaktywny:** Kliknij i przeciągnij myszą, aby dynamicznie ustalić promień zaokrąglenia i kliknij ponownie, aby zatwierdzić (lub wpisz wartość w okienku CAD HUD i naciśnij `Enter`).
  4. **Tryb stałego promienia:** W menu rozwijanym odznacz *Interaktywny*, wpisz żądany promień (np. `5.0 m`) i kliknij narożnik — zaokrąglenie zostanie wykonane natychmiastowo.

---

### 3. Zaokrąglanie dwóch linii (*Two-Line Fillet*)
* **Jak używać:**
  1. Aktywuj narzędzie **Zaokrąglij dwie linie** na pasku narzędzi.
  2. Wskaż pierwszą linię (zostanie podświetlona na niebiesko).
  3. Wskaż drugą linię — narzędzie wyznaczy wirtualny lub rzeczywisty punkt przecięcia prostych.
  4. Dynamicznie wskaż promień łuku myszą lub wpisz dokładną wartość w okienku CAD HUD.
  5. Narzędzie automatycznie wstawi łuk styczny do obu prostych, dociąwszy nadmiarowe ramiona narożnika (*Auto-Trim*) lub łącząc je w jedną ciągłą polilinię.

---

### 4. Utnij / Wydłuż (*AutoCAD-style Trim / Extend*)
* **Jak używać:**
  1. Włącz tryb edycji dla modyfikowanej warstwy liniowej.
  2. Aktywuj narzędzie **Trim / Extend** na pasku narzędzi.
  3. **Wydłużanie (Extend — domyślnie):** Najedź na końcówkę linii i kliknij lewym przyciskiem myszy — odcinek zostanie przedłużony wzdłuż swojej geometrii aż do najbliższej krawędzi obiektu na dowolnej widocznej warstwie.
  4. **Przycinanie (Trim — z klawiszem `Shift`):** Przytrzymaj klawisz `Shift` i kliknij fragment linii przecinającej inne obiekty — wskazany odcinek zostanie natychmiast odcięty do najbliższego punktu przecięcia.

---

### 5. Prosty offset (*Parallel Offset Tool*)
* **Jak używać:**
  1. Włącz tryb edycji dla warstwy liniowej lub poligonowej (do niej trafi nowo utworzony obiekt).
  2. Aktywuj narzędzie **Prosty offset** na pasku narzędzi.
  3. Najedź na obiekt (linia, polilinia lub granica poligonu z aktywnej lub widocznej warstwy) — podświetli się na niebiesko:
     - **Cały obiekt / granica:** standardowe najechanie i kliknięcie.
     - **Tylko kliknięty segment:** przytrzymaj klawisz `Ctrl` podczas najeżdżania i kliknięcia.
  4. Kliknij obiekt i odsuwaj kursor — na płótnie mapy pojawi się dynamiczny podgląd offsetu w czasie rzeczywistym, a obok kursora pływające okienko CAD z aktualną odległością w metrach.
  5. **Zatwierdzenie:**
     - Kliknij lewym przyciskiem myszy pod żądaną odległością, **LUB**
     - Wpisz z klawiatury dokładną odległość (np. `15.0`) i naciśnij klawisz `Enter` lub `Tab`.
     - **CAD powtarzanie odległości:** Po wykonaniu jednego offsetu przy kolejnych obiektach wystarczy wskazać myszą stronę i nacisnąć `Enter` lub `Tab` — offset zostanie natychmiast utworzony z poprzednią zadaną odległością!
  6. *Prawy przycisk myszy lub klawisz `Escape` anuluje operację.*

---

### 6. Rysowanie z Polar Trackingiem (*CAD Polar Digitize*)
* **Jak używać:**
  1. Włącz tryb edycji dla warstwy liniowej lub poligonowej.
  2. Aktywuj narzędzie **Rysuj z Polar Trackingiem** na pasku narzędzi.
  3. **Wybór punktu początkowego $V_0$:**
     - Kliknij w dowolnym miejscu mapy, **LUB**
     - Najedź na istniejącą linię lub granicę poligonu — krawędź podświetli się na błękitno, a jej azymut w terenie zostanie automatycznie zablokowany jako baza $0^\circ$!
  4. **Śledzenie biegunowe (AutoCAD-style):**
     - Przesuwając myszą, narzędzie wyświetla zielony promień prowadzący w chwili zbliżenia do zadanego kąta (np. 15°, 30°, 45°, 90°).
     - Kąt $90^\circ$ względem krawędzi początkowej wyznacza idealną prostopadłą (kąt prosty), a $180^\circ$ – idealną równoległą.
  5. **Odmierzanie odległości (CAD Overlay):**
     - W pływającym okienku obok kursora wpisz z klawiatury żądaną długość (np. `25`) i naciśnij `Enter` lub `Tab` — wierzchołek zostanie natychmiast postawiony na zadaną odległość wzdłuż przyciągniętego promienia!
     - Alternatywnie kliknij lewym przyciskiem myszy, aby postawić wierzchołek w bieżącej pozycji.
  6. **Korekta i zakończenie:**
     - Klawisz `Backspace` cofa ostatnio postawiony wierzchołek.
     - `Prawy przycisk myszy` lub klawisz `Enter` kończy rysowanie i tworzy obiekt w aktywnej warstwie (dla poligonów następuje automatyczne domknięcie obrysu).
* **Asystent w tle (dla narzędzi QGIS):**
  - Włączenie Polar Trackingu synchronizuje krok kąta w tle ze standardowymi narzędziami QGIS (*Zmień kształt / Reshape*, *Rozdziel obiekty / Split*).

---

### 7. Zalej / Wytnij nawierzchnię (*CAD Smart Pour & Erase*) [NOWOŚĆ v1.5.0]
* **Jak używać — Tryb Wylewania (Zwykłe kliknięcie):**
  1. Włącz tryb edycji dla warstwy poligonowej (np. `Nawierzchnie`, `Chodniki`, `Jezdnie`).
  2. Aktywuj narzędzie **Zalej nawierzchnię** na pasku narzędzi.
  3. **Wybór atrybutu kategoryzacji (Pole / Field):**
     - Na pasku narzędzi oraz w rozwijanym menu narzędzia dostępny jest selektor pola.
     - Jeśli warstwa posiada stylizację unikalnymi wartościami (*Categorized*), odpowiednie pole i zdefiniowane kategorie zostaną odczytane automatycznie.
     - Jeśli kategoryzacja nie jest potrzebna, wybierz `[Brak]` — poligon zostanie wylany bez sztucznych atrybutów i bez modyfikacji struktury tabeli.
  4. **Wskazanie punktu startowego $P_0$:**
     - Kliknij lewym przyciskiem myszy w korytarzu pomiędzy liniami krawężników lub granicami innych nawierzchni.
  5. **Dynamiczny promień odcięcia ($R$) i podgląd na żywo:**
     - Przesuwaj kursor myszy — poligon rozlewa się wzdłuż krawężników w czasie rzeczywistym.
     - Jeśli korytarz jest otwarty, odcięcie następuje łukiem w odległości zadanej promieniem $R$.
     - W pływającym okienku CAD HUD widać aktualny promień oraz plakietkę kategorii zsynchronizowaną z kolorystyką legendy QGIS.
  6. **Przełączanie kategorii w locie (Klawisz `Tab`):**
     - Wciśnij `Tab` lub `Shift+Tab` w trakcie wskazywania promienia, aby błyskawicznie przełączać kategorie zdefiniowane w stylu warstwy bez przerywania pracy.
  7. **Zatwierdzenie i Auto-Merge:**
     - Kliknij lewym przyciskiem myszy pod zadanym promieniem lub naciśnij `Enter` (możesz też wpisać promień z klawiatury, np. `50.0`).
     - Jeśli wybrano `[➕ Nowa kategoria...]`, w okienku wpisz nazwę nowej nawierzchni.
     - **Automatyczne scalanie (Auto-Merge):** Jeśli nowo wylana nawierzchnia styka się z istniejącym poligonem tej samej kategorii, zostaje z nim bezszwowo połączona w jeden, spójny obiekt wielokątny.

* **Jak używać — Tryb Gumki CAD / Wycinania fragmentu (`Shift + Klik`):**
  1. Przytrzymaj klawisz `Shift` i kliknij lewym przyciskiem myszy na istniejącym poligonie nawierzchni w aktywnej warstwie (np. na asfalcie jezdni).
  2. Narzędzie natychmiast przełącza się w **Tryb Gumki CAD** — na płótnie mapy pojawia się czerwony, półprzezroczysty podgląd dokładnie tego wycinka, który zostanie usunięty:
     $$\text{Geometria do usunięcia} = \text{Poligon} \cap \text{Dysk}(P_0, R)$$
  3. Nakładka CAD HUD zmienia kolor na czerwony ostrzegawczy z plakietką `[Gumka CAD / Usuń]` i polem zadanego promienia wycięcia.
  4. Odsuwając mysz lub wpisując promień z klawiatury (np. `15.0`), ustal żądany zasięg wycięcia i naciśnij `Enter` lub kliknij lewym przyciskiem myszy.
  5. **Efekt:** Fragment nawierzchni zostaje precyzyjnie wycięty w granicach danego poligonu (sąsiednie chodniki i warstwy pozostają nienaruszone). Jeśli wycięto cały obiekt, zostaje on usunięty z warstwy.
  6. **Rewizja CAD:** Po wycięciu fragmentu możesz skorygować linie krawężników, a następnie zalać powstałą lukę zwykłym Smart Pour — funkcja *Auto-Merge* automatycznie scali nową nawierzchnię z resztą drogi!
  7. *Prawy przycisk myszy lub klawisz `Escape` anuluje operację.*

---

## 📐 Kompaktowy pasek narzędzi i rozwijane menu

Pasek narzędzi wtyczki został zoptymalizowany pod kątem oszczędności miejsca:
* **Stan spoczynku:** Na pasku widoczne są zwięzłe ikony narzędzi: `[Wygnij]`, `[Zaokrąglij]`, `[Offset]`, `[Polar]`, `[Zalej nawierzchnię]`.
* **Rozwijane menu pod przyciskami (strzałka MenuButtonPopup):**
  - **Wygnij odcinek & Zaokrąglij wierzchołek:** Szybki wybór metody próbkowania i opcji.
  - **Prosty offset:** Wybór zakresu wykrywanych obiektów (wszystkie, tylko linie, tylko aktywna warstwa).
  - **Polar Tracking:** Włącznik śledzenia, wybór kroku kąta (11 presetów), pomiar kąta (Względny do krawędzi vs Bezwzględny) oraz okno dialogowe własnych kątów (*Additional angles* np. 147°).
  - **Zalej nawierzchnię:** Wybór warstw stanowiących krawędzie (Wszystkie widoczne linie vs Tylko wybrane warstwy z listy), okno wyboru warstw (`Krawędzie...`) oraz opcja uwzględniania granic już wylanych nawierzchni w aktywnej warstwie.
* **Automatyczne rozwijanie parametrów:** Po aktywacji danego narzędzia pasek automatycznie rozwija odpowiednie dla niego kontrolki (np. wybór nawierzchni oraz przycisk `Krawędzie...` dla Smart Pour), a po wyłączeniu narzędzia natychmiast zwija je z powrotem.

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
