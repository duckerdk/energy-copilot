# Instrukcje dla Codexa — Energy Co-Pilot

## Pierwsze kroki

1. Przeczytaj [README.md](README.md), [requirements/GOALS_AND_REQUIREMENTS.md](requirements/GOALS_AND_REQUIREMENTS.md), [requirements/SYSTEM_BASELINE.md](requirements/SYSTEM_BASELINE.md) i [requirements/OPEN_ITEMS.md](requirements/OPEN_ITEMS.md).
2. Czytaj **tylko właściwe dla zadania** kontrakty z tabeli w README. Nie wczytuj automatycznie całego repozytorium do jednego kontekstu.
3. Gdy dwa kontrakty są sprzeczne, **nie wybieraj arbitralnie**: podaj ścieżki, sprzeczne reguły i proponowaną korektę. Oznacz status dowodu: `observed`, `user_confirmed`, `assumed`, `unverified`.
4. Wykonuj wyłącznie wyraźnie zamówiony zakres. Nie uruchamiaj M6 ani nie wykonuj testów zapisu na realnym HA z własnej inicjatywy.

## Niezmienniki

- Buduj natywną integrację HA `custom_components/energy_copilot`; UI config flow/options flow, typed `ConfigEntry.runtime_data`, poprawne `async_setup_entry`/`async_unload_entry`, natywne API stanów/usług oraz Recorder. Bez klienta Modbus, zmian ESPHome/YAML/firmware, osobnego serwera ani LLM w decyzjach.
- `sensor.energi_data_service` = cena zakupu, `sensor.energi_data_spotpris` = cena sprzedaży; wartości HA **bez przeliczeń i dodatkowych opłat**. Parsowanie UTC/DST, właściwy horyzont tylko opublikowanych cen: [kontrakt cen](requirements/HA_PRICE_SERIES_CONTRACT.md).
- Eksport PV jest dozwolony od ceny sprzedaży **0,40 DKK/kWh**; przełącznik `switch.sun12k_solar_sell` nie dowodzi rozdzielenia energii PV i baterii. Bez potwierdzenia tego rozdzielenia **brak zapisu**. Celowy eksport baterii wymaga odrębnej zgody dla niezmiennej propozycji.
- `forecast_solar.get_forecast` to usługa z `config_entry` i wynikiem `wh_period`; użytkownik potwierdził widoczność akcji w UI, **ale odpowiedź w tej instalacji nie została przetestowana**. W M2 sprawdź interfejs i odpowiedź; nie twórz profilu z dobowej sumy.
- Dom: `sensor.home_energy_consumption = sensor.pv_sum + sensor.sun12k_total_grid_power + sensor.sun12k_battery_output_power`. To **pochodna**, z `float(0)` przy brakach danych; zerowy residual nie potwierdza fizycznego pomiaru. Waliduj składniki także **historycznie**, nie tylko w aktualnym stanie: [pomiary](requirements/MEASUREMENT_CONTRACT.md).
- `number.sun12k_maximum_battery_charge_current` 0–50 A, `number.sun12k_maximum_battery_discharge_current` 0–100 A, `number.sun12k_maximum_battery_grid_charge_current` 0–50 A: granice **polityki** użytkownika, nie dowód wsparcia przez urządzenie. Wartość 0 A i fizyczne skutki wymagają nadzorowanych testów. Limit A ≠ zadana moc ani gwarantowany SOC.
- Podstawowy backend: **current-first** przy niezmienionym TOU. Wszystkie komendy mają skutki trwałe po utracie HA; nie dopuszczaj czasowo niebezpiecznej operacji bez niezależnego mechanizmu zakończenia.
- Zasada `monitor/dry_run` od pierwszego uruchomienia. Plan, zaplanowany zapis, potwierdzony odczyt encji i zaobserwowany fizyczny skutek to odrębne stany. Nie udawaj, że uruchomienie usługi jest dowodem wykonania.
- Każda decyzja (także `idle`, `blocked`) ma od początku rejestr: wersje cen i prognoz, stan wejść, koszt rozważanych wariantów, powód i wykonalność. Bez tajnych danych, surowych prywatnych historii i połączeń do internetu poza standardowym HA.
- Osierocone `battery_controller.*` są nieaktywnymi pozostałościami i **nie służą** jako wejścia ani blokery. Konflikty zgłaszaj tylko po zaobserwowaniu faktycznie aktywnego konkurencyjnego wykonawcy.

## Implementacja i odbiór

- Kolejne etapy M1–M6 opisuje README; **M1–M5 bez jakiegokolwiek zapisu do urządzeń**. Przy implementacji najpierw testy fikcyjnych danych i regresji (`requirements/TEST_SCENARIOS.md` i testy `PRICE/PVF/LOAD/MTR/CUR/EXE` w kontraktach).
- Uwzględnij `unknown/unavailable`, nieaktualne dane, braki slotów, 23/25 godzin DST `Europe/Copenhagen`, restart, unload, kwantyzację limitu prądu i różnicę stron AC/DC.
- Walidacja `walk-forward`: prognozy wydane przed `t0`, nie używać wiedzy przyszłej i nie przypisywać curtailment błędowi prognozy.
- Dla każdej zmiany przedstaw testy faktycznie wykonane (pytest/lint/typing, gdy istnieje kod), ograniczenia testów, brakujące dowody i aktualizację odpowiednich specyfikacji. Nie opisuj planowanych testów jako zaliczonych. Nie dopisuj nowego pliku specyfikacji, jeżeli istniejący kontrakt wystarcza.
