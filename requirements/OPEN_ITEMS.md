# Nierozstrzygnięte kwestie implementacyjne

**Stan 20.10.2026.** To nie jest lista pytań do użytkownika. Potwierdzone decyzje są wyłącznie w [REQUIREMENTS.md](REQUIREMENTS.md). Wszystkie pozycje poniżej realizuje **Codex w odpowiednim etapie**; nie pytać ponownie o znaki mocy, limit 0 A, minimum SOC, TOU, degradację, awarię HA czy cel optymalizacji. P0 blokuje wyłącznie odpowiednie fizyczne działanie, nie M1–M5.

## P0 — przed danym zapisem na urządzeniu
- [ ] **HA pomiary:** zweryfikować mapowanie DC/AC, napięcie×prąd baterii wobec mocy, spójność i świeżość próbek; kierunki znaków są już ustalone. **M2/M6, Codex**.
- [ ] **Akcje i TOU:** implementacyjnie potwierdzić kroki encji, odczyt po zapisie, interakcję trzech limitów z Grid Charge/TOU/SOC/BMS, częściową aktualizację sześciu okien, ich powtarzalność i recovery. Użytkownik potwierdził ogólną skuteczność nastaw. **M6, Codex + osobny zatwierdzony test fizyczny**.
- [ ] **PV / bateria:** sprawdzić, że Solar Sell przy dozwolonych zmianach TOU nie uruchamia niezamierzonego eksportu baterii. **M6, Codex + zatwierdzony test**.
- [ ] **Trwałość i bezpieczeństwo:** ograniczenia BMS/sprzętu, min SOC 20%, restart/utrata HA, poprawne odczytanie ostatnich nastaw. **Ekonomiczne ryzyko braku korekty po awarii jest zaakceptowane**; brak potrzeby dodatkowego sprzętu tylko z tego powodu. **M6, Codex**.
- [ ] **Eksport baterii (odrębna opcjonalna zdolność):** fizyczna separacja, pomiar baterii→sieci, indywidualna zgoda/limit kWh i mechanizm niezależnego zakończenia przy awarii HA. Bez tego tylko `proposal_only`. **M6, Codex + zatwierdzenie każdej operacji przez użytkownika**.

## P1 — jakość planu i ekonomii
- [ ] Cena przy progu PV 0,40: walidator i testy offline `PRICE_THRESHOLD_AMBIGUOUS`, UTC/DST 23/25 h są zaimplementowane; pozostaje potwierdzenie rzeczywistych danych encji i zachowania po restarcie prywatnej instalacji. **M2, Codex; observed: testy, unverified: instalacja**.
- [ ] Forecast.Solar: natywna usługa Core 2026.10.2 została przetestowana z kontrolowanym estymatem (config entry, `wh_period` w Wh od początku interwału, UTC). Retencja jest ograniczona wiekiem, liczbą i rozmiarem, zachowuje pierwotne wartości i czas pierwszego odczytu oraz umożliwia odtworzenie obserwacji dostępnej w chwili decyzji; czas generacji u dostawcy nie jest dostępny w usłudze HA. Stare znormalizowane wersje nie odzyskują utraconych surowych danych. Podejrzenie curtailment jest diagnostyką, nie pomiarem utraconej produkcji. Pozostaje potwierdzenie odpowiedzi i pokrycia na prywatnej instalacji. **M2, Codex; observed: test kontraktu, unverified: instalacja**.
- [ ] Recorder: adapter i odrzucanie zamaskowanych zer/nieweryfikowalnych okresów mają testy z rzeczywistym Recorder SQLite w pamięci. Dłuższe zakresy można czytać na żądanie porcjami do 24 h (maksymalnie 366 dni), bez kopii bazy ani automatycznego wielomiesięcznego odczytu; diagnostyka rozróżnia retencję ustawioną od pokrycia. Pozostaje potwierdzenie retencji/rozdzielczości i jakości trzech składowych `home_energy_consumption` na prywatnej instalacji; niezmienne stare próbki są konserwatywnie odrzucane. **M2, Codex; observed: testy, unverified: instalacja**.
- [ ] Sprawność torów AC/DC, wiarygodność SOC i moc rzeczywiście dostępna przy BMS; parametry 0,9487/0,97 są tylko założeniami. **M3/M5, Codex**.
- [ ] Model wykonalnych akcji i dynamicznego TOU, wartość końcowego SOC, backtest walk-forward na prawdziwych migawkach prognoz, bez future leakage. **M3/M5, Codex**.

## P2 — przed dystrybucją
- [ ] Trwały rejestr decyzji, bezpieczna retencja, UX STOP, zgody i dashboard. **M4/M5, Codex**.
- [ ] Test kompatybilności HA, dokument instalacji, ewentualna dystrybucja HACS. **M5/M6, Codex**.

## P1 — ustalenia z diagnostyki HA 20.10.2026, 13:31 CEST
- [ ] **Recorder, krytyczne dla M2/M3:** 96/96 kwadransów zwróconych; 0 poprawnych. Powody wg źródła: `home:snapshot_not_synchronous=48`, `home:invalid_input=60`, `pv:historical_quality_unverifiable=51`, `pv:stale_input=51`, `pv:invalid_input=1`, `battery:invalid_input=1`, `grid:invalid_input=1`. Liczby się nakładają. Najpierw sprawdzić rzeczywiste zmiany i znaczniki czasu, pochodzenie `home` jako sumy PV+grid+battery, aktualizacje template/Recorder oraz właściwe rozróżnienie braku danych od stałego pomiaru. Nie ukrywać błędów przez luzowanie progów lub wpisywanie zera. Dodać testy regresyjne i dowód z nowej diagnostyki. **Codex M2; observed: prywatna diagnostyka, cause: unverified**.
- [ ] **Forecast.Solar i horyzont:** opublikowane ceny obejmują 35 godzin: 20.10.2026 11:00 UTC–21.10.2026 22:00 UTC; `raw_today=24`, `raw_tomorrow=24`, `tomorrow_valid=true`. Przedziały prognozy: 20.10 12:00 UTC–21.10 16:06:30 UTC. Ustalić czy brak pokrycia do 22:00 UTC wynika z godzin nocnych, a także zbadać brak pierwszej godziny; nie zakładać tego bez dowodu z usługi. Dopiero potem zdefiniować regułę brakujących godzin i testy DST. **Codex M2; observed: zakresy, przyczyna: unverified**.

## P2 — wersjonowanie wydawanej integracji
- [ ] **Obowiązkowe wydania:** wdrożyć SemVer w manifeście, tag `vX.Y.Z`, GitHub Release, walidację CI, rozpoznawalną zainstalowaną wersję w diagnostyce/HA i instrukcję HACS. Kolejna publikacja musi mieć wersję różną od `0.1.0`; nie podawać arbitralnego numeru bez procesu. Ostatni raport z rzeczywistym nowym kodem pokazał nadal `0.1.0`. **Codex + release workflow; observed: manifest 0.1.0, versioning missing**.
