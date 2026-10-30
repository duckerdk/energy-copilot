# Otwarte kwestie techniczne

**Stan przeglądu dokumentacji: 29.10.2026, manifest 2.0.2.** To lista prac **niepotwierdzonych jako zakończone na rzeczywistym HA**. Testy CI nie zastępują pomiarów falownika. Decyzje użytkownika: [REQUIREMENTS.md](REQUIREMENTS.md). Wersje i rozwiązane błędy: historia GitHub Releases, nie ten plik.

## P0 — bezpieczeństwo i zgodność rzeczywistego sterowania

- [ ] **Walidacja fizyczna:** porównać bieżący plan SOC/PV/dom/sieć z pomiarami falownika w następujących po sobie kwadransach, również w szczycie cenowym; sprawdzić brak niezamierzonego ograniczenia rozładowania.
- [ ] **TOU i recovery:** potwierdzić zapis i odczyt aktywnego slotu, zmianę SOC w krokach 1%, granicę kwadransa, restart HA, częściowy zapis oraz status `recovering`, odczyty co 2 s i samoczynne odzyskanie sterowania bez utraty kwadransów. Nie utożsamiać testów kodu z testem urządzenia.
- [ ] **Bezpieczeństwo Deye:** potwierdzić w integracji całkowity brak odniesień do nastawy maksymalnego prądu rozładowania (odczytu, zapisu, modelu, diagnostyki). Falownik/BMS odpowiada za sprzętowe limity; osobno potwierdzić brak eksportu baterii przy Solar Sell/TOU.
- [ ] **Prądy ładowania:** potwierdzić, że jedynym powodem zmiany jest celowe przesunięcie albo rozciągnięcie w czasie ładowania; prognozy prądu i SOC nie są poleceniem. Potwierdzić przywrócenie 50 A z dawnego ograniczenia 1 A po restarcie, z zachowaniem ręcznych ustawień, oraz brak nieplanowanego dławienia PV.
- [ ] **SOC i PV:** sprawdzić skutki zmian 1.16.17: rzeczywisty nadmiar PV może ładować ponad prognozowany SOC. Odróżnić działanie zaimplementowane od potwierdzonego pomiarem.

## P1 — jakość prognoz i opłacalność

- [ ] **Prognozy:** porównać 45 dni z mocną wagą ostatnich 7/14 dni z dawnym oknem 365 dni; ocenić MAE/bias oraz wieczorne P75 w 7-dniowym holdoucie na żywych danych; rozdzielić błędy pogody od curtailment i niepełnych danych.
- [ ] **Polityka 2.0.1 na żywym HA:** zweryfikować poprawkę wyceny dodatkowego importu przy niedoszacowaniu zużycia, przejście w aktywnym kwadransie z SOC 83% na 96%, wykonawcze ustawienie TOU 20% po decyzji o rozładowaniu oraz jakość krótkoterminowego nowcastu PV i domu przy asynchronicznych raportach.
- [ ] **Polityka 2.0.0 na żywym HA:** sprawdzić wspólną ocenę niedoszacowania zużycia i potencjalnej PV, doładowanie przed szczytem zamiast za wczesnego zakupu, brak zapełnienia wyłącznie przez sztuczną cenę końcową oraz eliminację nieopłacalnych mikrocykli; wagi scenariuszy 0,65/0,55 i niepewność PV wymagają kalibracji.
- [ ] **2.0.3 — kolejność godzin ładowania:** potwierdzić na nowych planach HA, że korekta nie przenosi zakupów z tańszej godziny do droższej wyłącznie z powodu progu mikrooperacji; sprawdzić `charge_relocations_preserved`, `minor_charges_rejected` i kwadransowe przepływy, z uwzględnieniem SOC/PV/ograniczenia 50 A.
- [ ] **Ceny/DST:** zweryfikować lokalny czas Europe/Copenhagen, 23/25 h przy zmianie czasu i moment otrzymania nowych cen na rzeczywistym HA.
- [ ] **Efekty ekonomiczne:** porównać plan z realnym baseline Deye, uwzględniając sprawność i ograniczenia; weryfikować pełen horyzont zamiast izolowanych kwadransów.
- [ ] **Kontrfaktyczne uzasadnienia:** istnieje porównanie dla wybranych akcji, ale brak niezależnego wariantu `grid_import` z **wymuszonym dodatnim rozładowaniem**. Nie przedstawiać takiego porównania jako obliczonego.

## P2 — użyteczność i szersze wydanie

- [ ] Odbiór czytelności krótkich wpisów z cenami w Aktywności HA oraz zapisów recovery. W diagnostyce potwierdzić pełny audyt, ograniczoną liczbę zapisów i wznowienie przy opóźnionym odświeżeniu encji.
- [ ] Dashboard wyszukiwania historii oraz osobne zatwierdzanie każdej operacji eksportu baterii; funkcja eksportu nadal zablokowana bez odrębnej zgody.
- [ ] Testy kompatybilności kolejnych wersji HA i dłuższa walidacja pracy ciągłej (dzień, noc, utrata i odzyskanie źródła).

Kryteria regresji: [VALIDATION.md](VALIDATION.md). Bezpieczeństwo wykonania: [EXECUTION.md](EXECUTION.md).
