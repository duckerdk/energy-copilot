# Otwarte kwestie techniczne

Stan: **08.11.2026**, docelowy manifest **2.0.5**. Poniższe zadania **nie zostały potwierdzone na rzeczywistym Home Assistant i falowniku**. Testy CI nie zastępują odbioru fizycznego. Zatwierdzone reguły: [REQUIREMENTS](REQUIREMENTS.md). Historia napraw: [GitHub Releases](https://github.com/duckerdk/energy-copilot/releases).

## P0 — sterowanie i bezpieczeństwo

- [ ] **Plan kontra wykonanie:** porównać plan i rzeczywiste SOC, PV, zużycie domu oraz sieć przez kolejne kwadranse, również w szczycie; wykluczyć niezamierzone ograniczanie rozładowania.
- [ ] **TOU i recovery:** zweryfikować sześć slotów, kroki SOC 1%, przekazanie między kwadransami, restart HA, częściowy zapis, odczyty potwierdzające co 2 s i samoczynne odzyskanie sterowania bez utraty kwadransów.
- [ ] **Bezpieczeństwo Deye:** potwierdzić brak odczytu, zapisu i modelowania maksymalnego prądu rozładowania; sprawdzić brak eksportu energii z baterii przy Solar Sell/TOU.
- [ ] **Prądy ładowania:** potwierdzić zmianę tylko dla przesunięcia/rozciągnięcia ładowania, przywracanie wcześniejszych nastaw (w tym po restarcie), poszanowanie ręcznych zmian oraz brak dławienia nadwyżek PV.
- [ ] **Nieplanowany nadmiar PV:** sprawdzić, czy rzeczywiste ładowanie może przekroczyć prognozowany SOC bez ograniczania produkcji.

## P1 — wiarygodność i ekonomia planu

- [ ] **Prognozy domu i PV:** porównać model 45 dni (wagi ostatnich 7/14 dni) ze starszym oknem 365 dni; ocenić MAE, bias i wieczorne P75 z podziałem na błędy prognozy, curtailment i braki danych.
- [ ] **Bieżący kwadrans (2.0.1):** potwierdzić replan na aktualnym SOC (w tym przypadek 83→96%), poprawne TOU 20% przy rozładowaniu, szacowanie kosztu brakującego importu i działanie nowcastu przy asynchronicznych odczytach.
- [ ] **Ryzyko i bufor PV (2.0.0):** zweryfikować wspólny scenariusz obciążenia/PV, termin ładowania przed szczytem, wycenę końcowego SOC i eliminację mikrocykli; skalibrować wagi 0,65/0,55 oraz niepewność PV na danych HA.
- [ ] **Kolejność godzin zakupu (2.0.3):** potwierdzić, że próg mikrooperacji nie przenosi zakupu z tańszych na droższe kwadranse. Sprawdzić `charge_relocations_preserved`, `minor_charges_rejected`, SOC, PV i ograniczenie 50 A.
- [ ] **Ceny i czas:** potwierdzić publikację cen, lokalny czas Europe/Copenhagen oraz dni DST z 23/25 godzinami.
- [ ] **Oszczędność:** porównać cały plan z rzeczywistym baseline Deye, z uwzględnieniem strat, ograniczeń sprzętu i niepewności.
- [ ] **Uzasadnienia kontrfaktyczne:** dodać niezależne porównanie `grid_import` z wymuszonym dodatnim rozładowaniem; do tego czasu nie przedstawiać go jako obliczonego.

## P2 — eksploatacja

- [ ] Ocenić czytelność wpisów w Aktywności HA (ceny, zapisy, recovery), kompletność diagnostyki i ograniczenie zbędnych komend.
- [ ] Ocenić potrzebę dashboardu historii oraz odrębnego zatwierdzania każdej operacji eksportu baterii; eksport pozostaje niedostępny bez zgody.
- [ ] Przeprowadzić testy kolejnych wersji HA i dłuższą obserwację pracy (dzień, noc, utrata i powrót danych).

Kryteria regresji: [VALIDATION](VALIDATION.md). Zasady wykonania: [EXECUTION](EXECUTION.md).

- [ ] **Po aktualizacji HA 2026.11:** na realnym systemie zweryfikować, czy nocne godziny przed wschodem otrzymują ciągły plan przy pierwszym `wh_period` różnym od zera, a Grid Charge wykonuje zaplanowany kwadrans. Zgłoszony 08.11.2026 błąd jednego kwadransa jest odtwarzany w teście syntetycznym po poprawce walidacji. **Brak możliwości pobrania pełnej diagnostyki nadal wymaga logów Core i odrębnej diagnozy**; nie uznawać tego problemu za naprawiony.
