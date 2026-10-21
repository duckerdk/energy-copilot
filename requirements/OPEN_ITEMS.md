# Otwarte kwestie techniczne

**Stan: v0.1.9, 21.10.2026.** Tylko sprawy nadal wymagające implementacji lub potwierdzenia; nie powtarzać zamkniętych decyzji użytkownika. Ich źródłem jest [REQUIREMENTS.md](REQUIREMENTS.md). Właściciel implementacji: Codex, chyba że wskazano inaczej. Testy offline i pojedynczy eksport HA nie zastępują walidacji pracy ciągłej.

## P0 — przed fizycznym sterowaniem (M6)

- [ ] **Bilans i ograniczenia sprzętu:** zweryfikować stronę DC/AC pomiarów, relację P≈V×I baterii, wiarygodność SOC i rzeczywiste limity BMS. Potwierdzone znaki i encje pozostają bez zmian.
- [ ] **Zapis nastaw:** sprawdzić zakresy i odczyt po zapisie limitów prądu, Grid Charge oraz wszystkich 6 okresów TOU; przetestować przerwanie zapisu, ponowienie, restart i odtwarzanie aktualnego stanu. Test fizyczny wymaga osobnej zgody.
- [ ] **Bezpieczeństwo eksportu:** potwierdzić, że Solar Sell i zmiany TOU nie powodują niezamierzonego eksportu baterii. Dla opcjonalnego eksportu baterii wymagane są fizyczne potwierdzenie kierunku przepływu, limit energii, niezależny stop i osobna zgoda na **każdą** operację.
- [ ] **Awaria HA:** sprawdzić bezpieczne limity i zachowanie falownika po utracie/restartcie HA, bez cofania zaakceptowanego przez użytkownika ryzyka ekonomicznego pozostawienia ostatnich nastaw.

## P1 — jakość danych przed M3/M5

- [ ] **Dzień i noc na prawdziwym HA:** zebrać minimum 30 minut ciągłej diagnostyki w obu warunkach dla **v0.1.9**. Sprawdzić `pv_available`, `home_available`, przyjęcia/odrzucenia w `live_measurement_window` oraz epizody `unknown/unavailable` i recovery. Eksport v0.1.6 ujawnił fałszywy `stale_input` SOC, który naprawiono w 0.1.7. Testy offline obejmują 8 h niezmiennych stanów; nadal potrzeba ciągłej obserwacji prawdziwej instalacji w dzień i w nocy.
- [ ] **Forecast.Solar:** rozwiązać politykę brakujących przedziałów prognozy o zmierzchu i pozostałej części już rozpoczętego okresu. `forecast_state=incomplete` i `unresolved_forecast_seconds>0` pozostają jawnymi ograniczeniami; nie dopisywać fikcyjnych Wh. Kontrakt `wh_period[end]` jest już potwierdzony — nie implementować go ponownie.
- [ ] **Recorder i profil domu:** ocenić rzeczywiste pokrycie kwadransów po normalizacji `max(0, home)`, wpływ luk oraz błąd fizycznego bilansu domu (w tym dodatnich anomalii). Diagnostyka v0.1.6 pokazała 88/96 kompletnych kwadransów, ale nie stanowi walidacji dokładności ani pełnej historii pauz Recorder.
- [ ] **Ceny i DST:** przetestować na rzeczywistym HA precyzję `raw_*` kontra `current_price` przy progu 0,40 DKK/kWh, zachowanie po restarcie i zmianę czasu. Testy offline `PRICE_THRESHOLD_AMBIGUOUS` i 23/25 h istnieją.
- [ ] **Sprawności i BMS:** oszacować osobno sprawności PV→bateria, sieć→bateria, bateria→AC, PV→AC; historyczne współczynniki 0,9487/0,97 są założeniami, nie zmierzonymi wynikami.
- [ ] **Planner i backtest:** w M3 zaimplementowano weryfikację fizycznych wariantów 15-minutowych i ich wycenę z SOC, prądami, stratami, degradacją i wartością końcową (bez komend). Zaimplementowano również rygorystyczny adapter cen/Forecast.Solar/Recorder, który odmawia wytwarzania fikcyjnych kwadransów; tymczasowy profil domu to poprzednie 24 h UTC i wymaga walidacji. Od v0.1.8 dostępny jest test HA w trybie `dry_run`: `planning_status`, `modeled_saving` i jawne powody blokady; wyniki są tylko eksperymentalnym porównaniem pojedynczego cyklu grid→bateria→dom z wariantem bez cykli. Następne: zweryfikować na realnym HA pokrycie przyszłych kwadransów, skalibrować podstawę AC/DC prognozy i profil domu, zweryfikować jawny model stałej mocy PV w grubych okresach z v0.1.9 przeciw rzeczywistym pomiarom, zoptymalizować sześć rzeczywistych TOU oraz porównać z rzeczywistym baseline Deye w walk-forward bez future leakage.

## P2 — przed automatyzacją i szerszą dystrybucją

- [ ] **M4/M5:** dziennik decyzji, retencja, dashboard, STOP oraz interfejs indywidualnej zgody na eksport baterii.
- [ ] **M5/M6:** testy zgodności kolejnych wersji HA i odbiór działań fizycznych. Publikowanie do HACS działa; nie jest otwartym zadaniem.

Kryteria odbioru i regresje: [VALIDATION.md](VALIDATION.md). Polityka wykonania: [EXECUTION.md](EXECUTION.md).
