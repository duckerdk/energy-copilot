# Energy Co-Pilot — repozytorium projektu

**Stan: poprzednia koncepcja (v1–v5.4) zamknięta do archiwum; nowa definicja celów nie została jeszcze ustalona.**

Repozytorium zostało zachowane, aby nie stracić danych technicznych i historii prac. **Nie ma tutaj uruchamialnego kodu sterowania ani nowego projektu optymalizatora.**

## Archiwum dotychczasowych prac

- [archive/energy-copilot-v5/](archive/energy-copilot-v5/) — zachowana poprzednia dokumentacja, rejestr encji HA, parametry, architektura, testy i źródłowe pliki logic/snapshot.
- [Archiwalny README](archive/energy-copilot-v5/README.md) — oryginalny punkt wejścia do wcześniejszej dokumentacji.
- [Katalog archiwalny — objaśnienia](archive/README.md) — zakres i ograniczenia archiwum.

Archiwum to **historia i źródło danych**, a nie bieżące wymagania ani automatyka do uruchomienia.

## Porządki po starym projekcie — wyłącznie plany, niczego nie usunięto

- [Lista kontrolna Home Assistant](cleanup/HOME_ASSISTANT.md)
- [Lista kontrolna serwera Linux](cleanup/SERVER.md)

**Nie usuwać encji PV, baterii, cen i integracji falownika tylko dlatego, że korzystał z nich Energy Co-Pilot.** Potrzebują ich również Home Assistant i ewentualne przyszłe rozwiązanie. Potwierdzono wcześniejsze ręczne uruchomienia Pythona; nie potwierdzono automatyzacji HA ani usługi działającej w tle.

## Następny etap

Osobno ustalić od podstaw **cele, ograniczenia i kryteria sukcesu** nowego rozwiązania, a dopiero później wybrać technologię. Nie wybrano jeszcze żadnego optymalizatora ani architektury.
