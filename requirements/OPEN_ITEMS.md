# Otwarte kwestie techniczne

**Stan przeglądu dokumentacji: 29.10.2026, manifest 1.16.17.** To lista prac **niepotwierdzonych jako zakończone na rzeczywistym HA**. Testy CI nie zastępują pomiarów falownika. Decyzje użytkownika: [REQUIREMENTS.md](REQUIREMENTS.md). Wersje i rozwiązane błędy: historia GitHub Releases, nie ten plik.

## P0 — bezpieczeństwo i zgodność rzeczywistego sterowania

- [ ] **Walidacja fizyczna:** porównać bieżący plan SOC/PV/dom/sieć z pomiarami falownika w następujących po sobie kwadransach, również w szczycie cenowym; sprawdzić brak niezamierzonego ograniczenia rozładowania.
- [ ] **TOU i recovery:** potwierdzić zapis i odczyt aktywnego slotu, zmianę SOC w krokach 1%, granicę kwadransa, restart HA, częściowy zapis oraz status `recovery_required` — bez utraty kwadransów. Nie utożsamiać testów kodu z testem urządzenia.
- [ ] **Bezpieczeństwo Deye:** przy istniejącym dodatnim prądzie rozładowania integracja nie może zmieniać jego limitu; 0 A wymaga ręcznej korekty, bo w tej instalacji zatrzymuje PV. Potwierdzić brak eksportu baterii przy Solar Sell/TOU, niezależnie od eksportu PV.
- [ ] **Prądy ładowania:** na rzeczywistej instalacji potwierdzić, że limiter nie dławi nieplanowanie PV, a zmiany są uzasadnione wyłącznie rozłożeniem ładowania z sieci lub przesunięciem ładowania PV.
- [ ] **SOC i PV:** sprawdzić skutki zmian 1.16.17: rzeczywisty nadmiar PV może ładować ponad prognozowany SOC. Odróżnić działanie zaimplementowane od potwierdzonego pomiarem.

## P1 — jakość prognoz i opłacalność

- [ ] **Prognozy:** ocenić MAE/bias PV i domu oraz 7-dniowy holdout na żywych danych; rozdzielić błędy pogody od curtailment i niepełnych danych.
- [ ] **Ceny/DST:** zweryfikować lokalny czas Europe/Copenhagen, 23/25 h przy zmianie czasu i moment otrzymania nowych cen na rzeczywistym HA.
- [ ] **Efekty ekonomiczne:** porównać plan z realnym baseline Deye, uwzględniając sprawność i ograniczenia; weryfikować pełen horyzont zamiast izolowanych kwadransów.
- [ ] **Kontrfaktyczne uzasadnienia:** istnieje porównanie dla wybranych akcji, ale brak niezależnego wariantu `grid_import` z **wymuszonym dodatnim rozładowaniem**. Nie przedstawiać takiego porównania jako obliczonego.

## P2 — użyteczność i szersze wydanie

- [ ] Odbiór czytelności logbook w rzeczywistym HA, zwłaszcza blokad, rewizji i efektów zapisów bez komentarzy-zapychaczy.
- [ ] Dashboard wyszukiwania historii oraz osobne zatwierdzanie każdej operacji eksportu baterii; funkcja eksportu nadal zablokowana bez odrębnej zgody.
- [ ] Testy kompatybilności kolejnych wersji HA i dłuższa walidacja pracy ciągłej (dzień, noc, utrata i odzyskanie źródła).

Kryteria regresji: [VALIDATION.md](VALIDATION.md). Bezpieczeństwo wykonania: [EXECUTION.md](EXECUTION.md).
