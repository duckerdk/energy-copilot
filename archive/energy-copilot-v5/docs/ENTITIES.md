# Rejestr encji Home Assistant — Energy Co-Pilot

**Źródła:** oryginalna logika v5.1 (14.06.2025), późniejsze doprecyzowanie v5.1.1 w rozmowie oraz historyczna lista pól CSV.  
**Ostrzeżenie:** lista stanowi **kontrakt historycznego projektu**, NIE wynik aktualnego odczytu instalacji. Nie znamy aktualnych wartości, atrybutów, dostępności ani nawet ciągłości nazw encji.

## 1. Wszystkie znane identyfikatory

| ID / usługa | Rola w projekcie | Typ danych / jednostka | Przeznaczenie | Pochodzenie |
| --- | --- | --- | --- | --- |
| `sensor.energi_data_service` | Prognoza cen energii na dobę do przodu | Lista godzinowa; struktura/atrybuty **nieznane** | Odczyt / plan zakupu | logika v5.1 |
| `sensor.energi_data_spotpris` | Aktualna cena spot | liczba, zakładana DKK/kWh (jednostka encji do sprawdzenia) | Odczyt / próg sprzedaży | logika v5.1; CSV |
| `sensor.sun12k_battery_capacity` | Stan naładowania (SOC) | liczba, % | Odczyt / rezerwa na noc | logika v5.1; CSV |
| `sensor.pv_sum` | Moc produkcji PV | liczba, kW | Odczyt / bilans energii | logika v5.1; CSV |
| `sensor.home_energy_consumption` | Chwilowy pobór mocy przez dom | liczba, kW | Odczyt / zużycie, profil nocny | logika v5.1; CSV |
| `sensor.energy_production_today` | Prognoza uzysku PV na dziś | liczba, kWh | Odczyt / plan ładowania | logika v5.1; CSV |
| `sensor.energy_production_tomorrow` | Prognoza uzysku PV na jutro | liczba, kWh | Odczyt / plan dobowy | logika v5.1; CSV |
| `switch.sun12k_solar_sell` | Zezwolenie na eksport/sprzedaż PV | `on` / `off` | Zapis — sterowanie sprzedażą | logika v5.1 |
| `switch.sun12k_grid_charge` | **Zezwolenie na ładowanie magazynu z sieci** | `on` / `off` | Zapis — sterowanie zakupem/ładowaniem z sieci | korekta użytkownika v5.1.1 |
| `number.sun12k_maximum_battery_grid_charge_current` | **Ograniczenie ładowania PV według ustaleń v5.1.1** | liczba, A; wymieniono 1 A i 40 A | Zapis — regulacja prądu; **nierozstrzygnięta semantyka rzeczywistego urządzenia** | rozbieżność v5.1 / v5.1.1 |
| `notify.mobile_app_pixel_7dk` | Kanał powiadomień o decyzjach/akcjach | usługa powiadomień, nie sensor | Wywołanie usługi | logika v5.1 |

**11 zidentyfikowanych identyfikatorów**: 7 sensorów, 2 przełączniki, 1 encja typu number i 1 identyfikator usługi powiadomień. Nie należy traktować `notify.mobile_app_pixel_7dk` jako encji mającej stan w `/api/states`.

## 2. Najważniejsze rozdzielenie funkcji: v5.1.1

Użytkownik poprawił pierwotną specyfikację:

- `switch.sun12k_grid_charge` **włącza/wyłącza ładowanie z sieci**.
- `number.sun12k_maximum_battery_grid_charge_current` według tej korekty **ogranicza ładowanie z PV**, żeby przesunąć je na tańsze godziny; wartość `1 A` służyła maksymalnemu ograniczeniu ładowania PV i sprzedawaniu nadwyżki.
- W pierwotnym tekście v5.1 ta sama encja `number` została nazwana limitem **ładowania z sieci** oraz posłużyła do jego „wyłączania” przez `1 A`. **To sprzeczne opisy.** Nazwa samej encji sugeruje coś innego niż ustalenia użytkownika; bez potwierdzenia mapowania sprzętowego i zachowania w HA nie można wybrać interpretacji za pomocą zgadywania.
- Ustawienie `1 A` **nie jest równoważne** `switch.sun12k_grid_charge=off`. Nie wolno zastąpić przełącznika limitem liczbowym.

Dla przyszłego sterownika obie funkcje muszą mieć **odrębne nazwy logiczne, akcje i testy**. Na razie nie wykonujemy żadnych zapisów do falownika.

## 3. Techniczna mapa odczytów i zapisów (REST HA)

| Zamiar | Przewidywane wywołanie | Stan w projekcie |
| --- | --- | --- |
| Odczyt pojedynczej encji | `GET /api/states/{entity_id}` | API HA udokumentowane; historyczny klient nie miał pełnego odczytu |
| Odczyt wszystkich encji | `GET /api/states` | Techniczna możliwość HA, bez testu w tym projekcie |
| Sprzedaż ON/OFF | `POST /api/services/switch/turn_on` / `turn_off`, `entity_id: switch.sun12k_solar_sell` | Zaplanowane, niepotwierdzone |
| Ładowanie z sieci ON/OFF | `POST /api/services/switch/turn_on` / `turn_off`, `entity_id: switch.sun12k_grid_charge` | Zaplanowane, niepotwierdzone |
| Ustawienie limitu prądu | `POST /api/services/number/set_value` z `entity_id` i `value` | Przewidziane przez typ encji; aktualnego wsparcia urządzenia nie zweryfikowano |
| Powiadomienie | Usługa HA o nazwie historycznej `notify.mobile_app_pixel_7dk` | Zaplanowane, niepotwierdzone |

**Ważne:** `POST /api/states/{entity_id}` **nie steruje fizycznym urządzeniem**, lecz modyfikuje reprezentację stanu w HA. Sterowanie rzeczywiste wymaga wywołania odpowiedniej usługi — zobacz [HA API](HA_API.md).

## 4. Minimalny kontrakt danych wymagany do implementacji

| Pole | Interpretacja źródłowa | Warunek walidacji do przyszłej implementacji |
| --- | --- | --- |
| `spot_price` | obecna cena, historycznie próg 0,4 DKK/kWh | Liczba; potwierdzić walutę, jednostkę i znaki opłat |
| `soc` | procent naładowania magazynu | Liczba w zakresie fizycznie sensownym; odrzucać `unknown`/`unavailable` |
| `pv_power` / `home_power` | chwilowe wartości mocy kW | Nie traktować sum mocy jako kWh |
| `pv_today` / `pv_tomorrow` | prognozy energii kWh | Odróżnić produkcję pozostałą do końca dnia od pełnodobowej |
| `hourly_prices` | przyszła seria godzinowa | Zbadać rzeczywisty JSON w `attributes`, strefy czasowe i horyzont |
| `control_*` | wymagane wyjścia sterowania | Rozdzielić odczyt stanu, komendę i potwierdzenie wykonania |

**Warunki walidacji powyżej są wymaganiami do opracowania, a nie udokumentowanymi funkcjami starego kodu.**

## 5. Co trzeba ustalić bezpośrednio z HA

- Czy każda encja nadal istnieje; jaka jest jej wartość, `unit_of_measurement`, `device_class` i `state_class`.
- Jak dokładnie wygląda `sensor.energi_data_service.attributes`, w szczególności lista cen i timestampy.
- Jak działają eksport i ograniczenie ładowania po zmianie przełączników; czy falownik potwierdza akcję.
- Jakie są `min`, `max` i `step` dla `number.sun12k_maximum_battery_grid_charge_current` oraz *rzeczywiste* skutki 1 A i 40 A.
- Jak świeże są pomiary, czy integracja aktualizuje stany i czy istnieje limit częstotliwości poleceń.
- Czy `notify.mobile_app_pixel_7dk` jest dostępne w aktualnej instancji.

Machine-readable lista historycznych identyfikatorów: [config/entities.yaml](../config/entities.yaml).
