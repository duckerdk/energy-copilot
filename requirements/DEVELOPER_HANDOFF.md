# Pakiet przekazania projektu programiście — Energy Co-Pilot

**Cel:** zwięzły przewodnik po obowiązującej dokumentacji i kryteriach odbioru. Bez implementacji, bez ingerencji w działającą instalację Home Assistant. Ta lista **nie zastępuje** pełnych specyfikacji.

## 1. Co budujemy

Lokalną, własną integrację Home Assistant (`custom_components/energy_copilot`), docelowo możliwą do dystrybucji przez HACS. Priorytet to minimalny **faktyczny koszt netto energii w DKK**, a nie maksymalizacja autokonsumpcji. Planowanie deterministyczne (MPC), wejścia i przyszłe wykonanie wyłącznie przez zweryfikowane encje HA.

**Zasady nienegocjowalne:**

- dynamiczny docelowy SOC, brak stałych progów sprzedaży/rezerwy;
- cena eksportu = spot minus `0,0215 DKK/kWh` prowizji Vindstød; cena zakupu to oddzielna cena końcowa z opłatami;
- opublikowane ceny na kolejną dobę zwykle docierają około 13:00 poprzedniego dnia; koniec planu wyznacza ostatni **rzeczywiście opublikowany** slot, nie stałe 48 h;
- rozróżnienie PV potencjalnego, uzyskanego i ograniczonego; nie uczyć błędu prognozy na sztucznie ograniczonej produkcji;
- bez indywidualnej ważnej zgody **zakaz celowego eksportu energii z baterii**;
- standardowo `monitor/dry_run`; automatyka dopiero po technicznej walidacji zapisów i niezależnego fail-safe;
- plan, polecenie HA i fizyczny rezultat są osobnymi stanami.

## 2. Dokumenty w zalecanej kolejności

| Kolejność | Plik | Zakres |
| --- | --- | --- |
| 1 | [README.md](../README.md) i [AGENTS.md](../AGENTS.md) | Status, zasady pracy Codexa, ograniczenia |
| 2 | [GOALS_AND_REQUIREMENTS.md](GOALS_AND_REQUIREMENTS.md) | Cel ekonomiczny i reguły decyzji |
| 3 | [SYSTEM_BASELINE.md](SYSTEM_BASELINE.md) | Fakty o instalacji, stopień potwierdzenia |
| 4 | [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md) | Bilans PV/dom/sieć/bateria, funkcja kosztu, prognozy, końcowy SOC |
| 5 | [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md) | Logiczne wejścia/wyjścia, historyczne HA ID, walidacja fizycznych akcji |
| 6 | [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md) | Current-first przez encje HA, trwały TOU, porównanie backendów, 16 testów CTRL |
| 6a | [CURRENT_CONTROLLER_MODEL.md](CURRENT_CONTROLLER_MODEL.md) | Algorytm konwersji prądu, przewidywanego przepływu, SOC i 20 testów CUR |
| 7 | [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md) | Kolejność zapisu, potwierdzenie, zgody, konflikty i fail-safe |
| 8 | [HA_DASHBOARD.md](HA_DASHBOARD.md) | Prezentacja planu, pomiarów, kosztów, propozycji i diagnostyki |
| 9 | [TEST_SCENARIOS.md](TEST_SCENARIOS.md) | 40 szczegółowych scenariuszy obliczeń i mapowania; dodatkowo testy EXE i UI w dokumentach tematycznych |
| 10 | [FORECAST_POLICY.md](FORECAST_POLICY.md) | Niepewność prognoz, nieantycypacyjność i wartość SOC na końcu opublikowanych cen |
| 11 | [DECISION_LOGGING.md](DECISION_LOGGING.md) | Log każdej decyzji i powód wyboru widoczne od pierwszego uruchomienia |
| 12 | [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md) | Testy na historii bez przyszłych danych i uczciwy benchmark finansowy |
| 13 | [CALIBRATION_POLICY.md](CALIBRATION_POLICY.md) | Zasady weryfikacji sprawności, degradacji i prognoz — wartości startowe nie są pomiarami |
| 14 | [HA_READONLY_CAPTURE.md](HA_READONLY_CAPTURE.md) | Jednorazowa lista aktualnych encji i jednostek HA; bez sterowania |
| 15 | [HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md) | Wynik tego odczytu: potwierdzone ID, bilans, niezweryfikowane sterowania i konflikty |
| 16 | [HA_TIMESERIES_CAPTURE.md](HA_TIMESERIES_CAPTURE.md) | Wąski odczyt przyszłych cen i profilu PV z atrybutów źródeł |
| 17 | [OPEN_ITEMS.md](OPEN_ITEMS.md) | Aktualne P0/P1/P2 — nie udawać, że wszystkie są już rozwiązane |

Jeżeli dokumenty zawierają sprzeczność, nie rozwiązywać jej przez arbitralne założenie: zgłosić konkretny fragment, zaproponować rozwiązanie i zaktualizować po potwierdzeniu.

## 3. Etapy prac programisty (dopiero po formalnym rozpoczęciu kodowania)

| Etap | Zakres | Warunek odbioru |
| --- | --- | --- |
| **M1** | Szkielet integracji, config/options flow, obsługa HA setup/unload, diagnostyka | Integracja uruchamia się w HA, nie wykonuje żadnego zapisu sprzętowego; testy jednostkowe |
| **M2** | Mapowanie ról na encje, normalizacja cen/prognoz/AC/DC, walidacja czasu, jednostek i jakości | Testy MAP/TIME/PHY przechodzą; niedostępne dane są jawne |
| **M3** | Planner MPC, bilans i koszt, dynamiczny SOC, kalibracja prognoz z curtailment, symulator i **rejestr KAŻDEJ decyzji od startu** | Testy PHY/ECO/SOC/PVQ/UNC/LOG, porównywalna alternatywa i konkretne liczby w przyczynie decyzji |
| **M4** | Sensory/atrybuty i natywny dashboard HA, propozycje sprzedaży, status i historia decyzji | Testy UI/LOG, bieżące i dawne powody każdej decyzji w HA, bez ręcznego eksportowania JSON |
| **M5** | Historia, walk-forward (bez wiedzy o przyszłości), baseline Deye, testy regresyjne, aktualizacja dokumentacji | Testy BKT, jawna niepewność i porównywalny końcowy SOC; brak niesprawdzonych deklaracji oszczędności |
| **M6** | Opcjonalny executor po P0, osobna zgoda na aktywację funkcji i nadzorowany test fizyczny | Każda akcja ma własną kartę, odczyt zwrotny, pełny fail-safe i przechodzi EXE; użytkownik uruchamia świadomie |

**M1–M5 mogą być realizowane przed kompletnym P0** bez sztucznego blokowania rozwoju projektu. **M6 nie może** zostać uruchomiony na podstawie samej dokumentacji lub nazw encji.

## 4. Czego brakuje, aby wynik był wiarygodny na rzeczywistych danych

Nie są to wzory, których ma dostarczyć użytkownik. Programista i projekt muszą je **pozyskać / zweryfikować** w sposób zgodny z warunkami dostępu:

1. **Mapowanie rzeczywistych encji i atrybutów HA** — zwłaszcza końcowej ceny zakupu, profili spot i PV, importu/eksportu oraz mocy baterii po AC/DC. Znamy historycznie 11 identyfikatorów, nie zakładać pełności listy.
2. **Dokładność punktów pomiarowych** — uwzględnienie ładowania DC i rozpoznawanie ograniczania produkcji.
3. **Krzywe sprawności i koszt degradacji** — kalibracja na danych z instalacji, bez wymyślania uniwersalnych parametrów.
4. **Statystyczny model niepewności PV i zużycia** — aktualizacja po zgromadzeniu archiwum dawnych prognoz, bez nadpisywania migawek.
5. **Wartość energii na końcu horyzontu cenowego** — model musi chronić przed sztucznym opróżnianiem baterii, ale nie wymyślać nieopublikowanych cen.
6. **Karty zweryfikowanych sterowań** — oddzielna kontrola ładowania, eksportu PV, eksportu baterii, SOC oraz sposobu zatrzymania/odzyskiwania po utracie HA.
7. **Rozliczenie rzeczywiste** — potwierdzenie kompletności ceny kupna/sprzedaży na rachunku, zgodnie z [OPEN_ITEMS.md](OPEN_ITEMS.md).

Punkty 1–5 i 7 wpływają na jakość planu; punkt 6 i sprzętowy fail-safe **blokują rzeczywiste sterowanie**. Nie traktować braku tych danych jako zaproszenia do zgadywania.

## 5. Przekazanie do wdrożenia — definicja ukończenia

- Dokumentacja, pliki konfiguracji i zależności są spójne; wszystkie nowe założenia mają źródło i status „potwierdzone / modelowe / niepotwierdzone”.
- Każdy przypadek z [TEST_SCENARIOS.md](TEST_SCENARIOS.md) oraz testy LOG, UNC i BKT w dokumentach tematycznych mają automatyczny test `PASS/FAIL` albo udokumentowany `BLOCKED`; brak nieudokumentowanych wyjątków.
- Scenariusze EXE i UI z ich specyfikacji mają testy na danych symulowanych i uzasadniony wynik; nie mylić testu fikcyjnych encji z walidacją rzeczywistego urządzenia.
- Raport symulacji oddziela koszt faktury, degradację, ryzyko, prognozę i wykonanie; rzetelnie odnosi się do scenariusza bazowego.
- Operator widzi w HA **powód każdej decyzji i jej historię**, liczby wejściowe, alternatywę, wynik DKK, horyzont dostępnych cen, status danych i zgody; żadna akceptacja nie jest domyślna.
- Zmiany w kodzie nie nadpisują ograniczeń i nie wydają komend sprzętowych bez wcześniej zatwierdzonej zdolności.
- Nie deklarować pełnej „gotowości do automatyki”, dopóki nie zostaną zamknięte P0 i przeprowadzone nadzorowane testy fizyczne.

## 6. Ostatni etap dokumentacyjny — bilans gotowości

**Gotowe do przekazania programiście do M1–M5:** cele, struktura, model planera, kontrakty logiczne, panel, scenariusze i ograniczenia.  
**Pozostaje materiałem do zebrania przed M6:** rzeczywiste dane i dowody sterowania na konkretnej instalacji.

Nie rozpoczynać kodowania na podstawie samej decyzji o kompletności dokumentacji — decyzja o starcie implementacji należy do właściciela projektu.


## 7. Kontrola spójności dokumentacji

**Audyt dokumentów (aktualizacja 2026-10-20):**
- Sprawdzenie odwołań względnych między plikami Markdown: **brak zerwanych odwołań do plików**.
- Testy opisane w dokumentacji: **40** scenariuszy PHY/ECO/SOC/TIME/PVQ/SAFE/MAP + **16** CTRL + **20** CUR + **12** EXE + **11** UI + **10** LOG + **10** UNC + **12** BKT + **7** CAL = **138** przypadków specyfikacyjnych.
- Nowe testy **ECO-08 i ECO-09** weryfikują rachunek marginalny i porównanie opłacalności bez dobierania celu 65% z góry; ECO-08 przewiduje wynik **+0,4152 DKK** przy jawnie określonych stratach i degradacji. To wzorzec analityczny, nie wynik pracy kodu.
- Nadal **nieweryfikowane** są: rzeczywista semantyka sterowania i torów AC/DC, struktura przyszłych przedziałów cen w HA (pełne taryfy zakupu potwierdzone przez użytkownika), realne krzywe sprawności, koszt degradacji, historyczne migawki prognoz, funkcja terminalnej wartości energii i niezależny fail-safe. Zapisanie wzorów **nie zamyka** tych kwestii.
- Testy zapisano jako przypadki do zaimplementowania; dopóki nie powstanie kod, nie należy ich nazywać „wykonanymi”.
