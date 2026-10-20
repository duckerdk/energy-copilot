# Energy Co-Pilot

**Status:** specyfikacja natywnej integracji Home Assistant `custom_components/energy_copilot`; repozytorium nie zawiera jeszcze działającej integracji. Wszystkie testy w dokumentacji to **przypadki do zaimplementowania**, nie wykonane testy.

**Cel:** minimalizować całkowity koszt energii na całym dostępnym horyzoncie opublikowanych cen. Źródłem wszystkich zatwierdzonych decyzji jest [REQUIREMENTS.md](requirements/REQUIREMENTS.md). Nie rekonstruować decyzji użytkownika ze starych komentarzy ani z `OPEN_ITEMS`.

## Dokumenty — jedna rola na plik

| Plik | Jedyna odpowiedzialność |
| --- | --- |
| [REQUIREMENTS](requirements/REQUIREMENTS.md) | Cel, instalacja, polityka cen/SOC/degradacji, uprawnienia użytkownika |
| [HA_CONTRACT](requirements/HA_CONTRACT.md) | Encje, znaki, jednostki, dostępność, ceny, dane PV/Recorder |
| [OPTIMIZATION](requirements/OPTIMIZATION.md) | Bilans, funkcja celu, prognozowanie, wykonalny plan |
| [EXECUTION](requirements/EXECUTION.md) | HA executor, bezpieczeństwo, TOU, zgody i awarie |
| [VALIDATION](requirements/VALIDATION.md) | Testy do napisania, benchmark, log i dashboard |
| [OPEN_ITEMS](requirements/OPEN_ITEMS.md) | **Wyłącznie niewyjaśnione dowody techniczne**, z właścicielem i etapem |

Dodatkowo [AGENTS.md](AGENTS.md) zawiera instrukcje wykonawcze dla Codexa. Nie tworzyć nowych plików specyfikacji bez rzeczywistej nowej odpowiedzialności; poprawiać właściwy istniejący plik. Brak archiwum — historia jest dostępna przez Git.

## Implementacja

1. M1: manifest, config/options flow, typed runtime data, setup/unload, testy — zero zapisów.
2. M2: mapowanie encji, walidacja cen/UTC/DST/Recorder/Forecast.Solar.
3. M3: planner minimalnego kosztu, realistyczne możliwości Deye, `dry_run`, rejestr decyzji.
4. M4: HA encje, dashboard, zgody eksportu baterii, STOP.
5. M5: testy, walk-forward, walidacja alternatyw i jakości danych.
6. M6: **dopiero po świadomym włączeniu live i testach** — autonomiczne prądy, Grid Charge, sześć TOU, Solar Sell PV; eksport baterii tylko przy indywidualnej zgodzie.

Odbiór iteracji: kod i pliki, testy naprawdę wykonane, testy nieprzeprowadzone, istotne ryzyka i aktualne [OPEN_ITEMS](requirements/OPEN_ITEMS.md). Bez udawania, że symulacja jest oszczędnością z urządzenia.
