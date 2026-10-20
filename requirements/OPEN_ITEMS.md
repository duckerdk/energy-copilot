# Nierozstrzygnięte kwestie implementacyjne

**Stan 20.10.2026.** To nie jest lista pytań do użytkownika. Potwierdzone decyzje są wyłącznie w [REQUIREMENTS.md](REQUIREMENTS.md). Wszystkie pozycje poniżej realizuje **Codex w odpowiednim etapie**; nie pytać ponownie o znaki mocy, limit 0 A, minimum SOC, TOU, degradację, awarię HA czy cel optymalizacji. P0 blokuje wyłącznie odpowiednie fizyczne działanie, nie M1–M5.

## P0 — przed danym zapisem na urządzeniu
- [ ] **HA pomiary:** zweryfikować mapowanie DC/AC, napięcie×prąd baterii wobec mocy, spójność i świeżość próbek; kierunki znaków są już ustalone. **M2/M6, Codex**.
- [ ] **Akcje i TOU:** implementacyjnie potwierdzić kroki encji, odczyt po zapisie, interakcję trzech limitów z Grid Charge/TOU/SOC/BMS, częściową aktualizację sześciu okien, ich powtarzalność i recovery. Użytkownik potwierdził ogólną skuteczność nastaw. **M6, Codex + osobny zatwierdzony test fizyczny**.
- [ ] **PV / bateria:** sprawdzić, że Solar Sell przy dozwolonych zmianach TOU nie uruchamia niezamierzonego eksportu baterii. **M6, Codex + zatwierdzony test**.
- [ ] **Trwałość i bezpieczeństwo:** ograniczenia BMS/sprzętu, min SOC 20%, restart/utrata HA, poprawne odczytanie ostatnich nastaw. **Ekonomiczne ryzyko braku korekty po awarii jest zaakceptowane**; brak potrzeby dodatkowego sprzętu tylko z tego powodu. **M6, Codex**.
- [ ] **Eksport baterii (odrębna opcjonalna zdolność):** fizyczna separacja, pomiar baterii→sieci, indywidualna zgoda/limit kWh i mechanizm niezależnego zakończenia przy awarii HA. Bez tego tylko `proposal_only`. **M6, Codex + zatwierdzenie każdej operacji przez użytkownika**.

## P1 — jakość planu i ekonomii
- [ ] Cena przy progu PV 0,40: surowe zaokrąglone sloty kontra dokładniejsza bieżąca cena; `PRICE_THRESHOLD_AMBIGUOUS`, DST, restart. **M2, Codex**.
- [ ] Forecast.Solar: realna odpowiedź `forecast_solar.get_forecast`, config entry, sloty i UTC; rozpoznanie curtailment. **M2, Codex**.
- [ ] Recorder: retencja/rozdzielczość trzech składowych `home_energy_consumption` i historyczne fałszywe zera `float(0)`. **M2, Codex**.
- [ ] Sprawność torów AC/DC, wiarygodność SOC i moc rzeczywiście dostępna przy BMS; parametry 0,9487/0,97 są tylko założeniami. **M3/M5, Codex**.
- [ ] Model wykonalnych akcji i dynamicznego TOU, wartość końcowego SOC, backtest walk-forward na prawdziwych migawkach prognoz, bez future leakage. **M3/M5, Codex**.

## P2 — przed dystrybucją
- [ ] Trwały rejestr decyzji, bezpieczna retencja, UX STOP, zgody i dashboard. **M4/M5, Codex**.
- [ ] Test kompatybilności HA, dokument instalacji, ewentualna dystrybucja HACS. **M5/M6, Codex**.
