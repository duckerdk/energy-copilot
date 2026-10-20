# Kontrakt encji Home Assistant

**Status: część identyfikatorów i stanów potwierdzona odczytem HA z 19.10.2026, pozostałe historyczne.** Szczegółowy aktualny odczyt, bilans i lista sterowań: [HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md). Sam fakt istnienia encji i jej wartość nie są dowodem semantyki fizycznej ani bezpiecznego skutku zapisu. W integracji wybór źródeł przez UI i walidacja jednostek oraz punktu pomiaru.

## Granica integracji: wyłącznie encje i usługi Home Assistant

**Zasada obowiązująca:** Energy Co-Pilot odczytuje stany/atrybuty encji HA i steruje wyłącznie poprzez natywne usługi HA na zweryfikowanych encjach (np. `number.set_value`, `switch.turn_on/off`). Integracja **nie** odczytuje ani nie zapisuje rejestrów Modbus, nie otwiera połączenia z falownikiem i nie modyfikuje ESPHome, YAML, firmware ani istniejącego mostka. Opis istniejącego mostka ESPHome, jeżeli jest dostępny poza repo, może służyć wyłącznie do objaśnienia encji; nie jest kontraktem sterowania i nie powinien być wymaganym plikiem projektu.

**Przyjęte semantyki na etapie projektowania (zgodnie z dyspozycją użytkownika):**

| Encja HA | Rola w Co-Pilot | Limit polityki |
| --- | --- | --- |
| `number.sun12k_maximum_battery_charge_current` | Ogólny maksymalny prąd ładowania baterii, także ładowania z PV | 0–50 A |
| `number.sun12k_maximum_battery_discharge_current` | Maksymalny prąd rozładowania baterii | 0–100 A |
| `number.sun12k_maximum_battery_grid_charge_current` | Dodatkowy maksymalny prąd ładowania z sieci | 0–50 A |

Przyjmujemy, że **właściwe encje wykonują właściwe funkcje**. To **założenie projektowe**, nie wynik testu fizycznego. Nie blokuje projektowania algorytmu i mapowania akcji, ale nie upoważnia do uruchomienia zapisów; semantykę oraz skutek `0 A` zweryfikować dopiero w osobno uzgodnionym teście. Więcej: [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md).

## Aktualne role — obserwacja z 19.10.2026

[HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md) przechowuje pojedynczy historyczny odczyt jednostek, kandydatów sterowania i pomiarów. Dla Codexa **nie jest** to aktualna konfiguracja: `entity_id` mapuj przez UI, sprawdzaj jednostkę, znak, źródło, dostępność i stan w chwili działania. Nie przenoś list z archiwalnych logów ani nie korzystaj z encji `battery_controller.*`.

## Nieznane, lecz wymagane do planowania i wykonania

- **Mapa pomiarów:** znane `sun12k_total_grid_power`, `sun12k_battery_output_power`, `pv_sum` i **potwierdzony pochodny** `home_energy_consumption`; bez dodatkowych liczników. Wzór i kontrola brakujących składowych: [MEASUREMENT_CONTRACT.md](MEASUREMENT_CONTRACT.md). **Znaki potwierdzone przez użytkownika (20.10.2026):** sieć + import / - eksport, bateria + rozładowanie / - ładowanie. Nadal do sprawdzenia: strona AC/DC, aktualność i spójność fizyczna; nie przyjmować, że jeden bilans w stanie eksportowym jest kompletną kalibracją.
- **Ceny: rozwiązane.** Timestampowane serie zakupu i spot: [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md). **PV: kontrakt dostępu określony** — preferowana natywna akcja HA `forecast_solar.get_forecast` zwraca godzinowy lub 15-minutowy profil `wh_period`/`watts`: [PV_FORECAST_CONTRACT.md](PV_FORECAST_CONTRACT.md). Do sprawdzenia przy uruchomieniu przez Codexa: dostępność akcji w tej instalacji i wybór wpisu konfiguracji; nie wymaga ręcznego kopiowania prognozy. Prognoza zużycia: profil tworzony lokalnie na danych Recorder `sensor.home_energy_consumption`, według [LOAD_FORECAST_CONTRACT.md](LOAD_FORECAST_CONTRACT.md).
- **Produkcja PV i curtailment:** potwierdzić, czy encja mocy/energii PV obejmuje również ładowanie po DC; jeśli dostępne, wskazać sygnał aktywnego ograniczenia produkcji (limit eksportu, MPPT, status curtailment) i zweryfikować jego znaczenie. Pełna bateria + wyłączony eksport to jedynie przesłanki; nie dają pomiaru niewyprodukowanych kWh. Migawki prognoz muszą mieć czas pobrania i daty/sloty ważności, aby porównanie z późniejszą produkcją nie wykorzystywało zaktualizowanej prognozy.
- ID i znaczenie sterowań **docelowym SOC, limitem mocy ładowania, wymuszonym rozładowaniem, kierunkiem eksportu z baterii, harmonogramem Deye i przywróceniem trybu fabrycznego**. Nie wiadomo, czy HA udostępnia wszystkie te funkcje.
- Warunki i możliwości niezależnego potwierdzania rezultatów poleceń.

## Minimalny test kontraktu (wyłącznie odczyt)

Dla każdej wybranej pozycji ustalić: entity_id, domain, bieżący state, attributes (w tym unit_of_measurement i granice), czas ostatniej wiarygodnej próbki, źródło fizyczne, częstotliwość aktualizacji, znak, typ, zakres, wariant unknown/unavailable. Dla serii: układ atrybutów, strefę czasową, brakujące i powtarzające się sloty, zmianę czasu (DST), cenę importu **z opłatami** i cenę spot **bez opłat**.

Przypadek testowy jakości PV: prognoza 60 kWh, pomiar 35 kWh, część dnia pełna bateria i eksport wyłączony. Nie obliczać automatycznie błędu prognozy −25 kWh; najpierw oznaczyć okresy podejrzane lub potwierdzone jako ograniczone. Szczegóły: [ARCHITECTURE.md](ARCHITECTURE.md#wiarygodność-prognoz-pv-przy-ograniczeniu-produkcji).

Test każdej **akcji zapisu** wymaga dodatkowo odrębnej, świadomie nadzorowanej procedury na urządzeniu: stan początkowy, dozwolone wartości, wywołana usługa HA, rzeczywisty odczyt zwrotny i reakcja na błąd, reset/restart i utratę komunikacji. Samo HTTP 200 lub zmiana stanu encji nie potwierdza skutku fizycznego.

**Nie wykonywać takich testów zapisu przez Codexa ani automatycznie.** Brak jednej kluczowej funkcji blokuje odpowiednią automatyzację; nie zastępować jej inną, podobnie nazwaną encją.


Aktualne stany, jednostki i źródła odczytać przez API encji HA w M2; migawka z 19.10 jest dowodem historycznym, nie bieżącym.

## Limity prądów ustalone przez użytkownika — obowiązujące dla Energy Co-Pilot

Energy Co-Pilot stosuje **własne zakresy dozwolonych nastaw w amperach**, całkowicie niezależne od błędnych metadanych `min/max` istniejących encji HA:

| Sterowanie | `entity_id` | Zakres Co-Pilot (włącznie) |
| --- | --- | --- |
| Maksymalny prąd ładowania baterii | `number.sun12k_maximum_battery_charge_current` | **0–50 A** |
| Maksymalny prąd rozładowania baterii | `number.sun12k_maximum_battery_discharge_current` | **0–100 A** |
| Maksymalny prąd ładowania baterii z sieci | `number.sun12k_maximum_battery_grid_charge_current` | **0–50 A** |

**Ustalenie z 20.10.2026:** są to limity polityki Energy Co-Pilot (własna walidacja konfiguracji i planu), a **nie** potwierdzone granice sprzętowe Deye/BMS. Moduł wykonawczy odrzuca propozycje nastaw poza zakresami i nie korzysta z niewiarygodnych `min/max = ±16 777 220 A` ogłaszanych przez encje. Mniejszy limit wynikający ze sprzętu/BMS ma zawsze pierwszeństwo. Nie wolno przekładać amperów na sztywne kW bez aktualnego napięcia i ustalonej strony AC/DC.

**Ważne:** przyjęcie **0 A jako dozwolonej wartości liczbowej** nie jest dowodem, że `number.set_value: 0` jest przez falownik akceptowane lub że wyłącza konkretny tor. Semantyka `0 A`, znaczenie regulatora `grid_charge_current`, granice faktycznie obsługiwane i bezpieczna procedura wyłączenia pozostają do nadzorowanego sprawdzenia **przed** jakimkolwiek zapisem. Brak pozytywnego testu oznacza pozostawienie tej zdolności w `read_only`/`disabled`.

**Reguła implementacji:** osobno walidować zakres przy konfiguracji, tworzeniu planu, przed wykonaniem akcji i po odczycie stanu. Nie podmieniać nieprawidłowej komendy przez ciche przycięcie do granicy; odrzucić ją i wyjaśnić powód w rejestrze decyzji.

## Kontrakt logiczny wejść

**Zasada:** nazwy ról poniżej są wewnętrznymi kluczami optymalizatora, **nie** nazwami istniejących encji. Każdą rolę użytkownik mapuje przez UI na istniejące źródło HA; przed wykorzystaniem normalizator sprawdza jednostkę, znaczenie, aktualność i źródło. Nie zgadywać identyfikatorów.

| Rola | Znormalizowane dane | Status mapowania i walidacja |
| --- | --- | --- |
| `spot_price` | DKK/kWh, czas obowiązywania | Historyczne `sensor.energi_data_spotpris`; sprawdzić taryfę DK1, jednostki, daty |
| `spot_price_slots` | `start_utc, end_utc, value_dkk_kwh` | `sensor.energi_data_spotpris.attributes.raw_today/raw_tomorrow[*].hour/price`; publikacja jutra wyłącznie przy poprawnym `tomorrow_valid`; [parser](HA_PRICE_SERIES_CONTRACT.md) |
| `buy_price_slots` | Te same przedziały, cena **końcowa** z opłatami | `sensor.energi_data_service.attributes.raw_today/raw_tomorrow[*].hour/price`; **format już potwierdzony**; opłaty/taryfy już w wartości, nie doliczać ponownie |
| `sell_price_slots` | DKK/kWh, **bez przeliczeń** | `sensor.energi_data_spotpris.attributes.raw_today/raw_tomorrow[*].price` wprost z HA; próg eksportu PV 0,40 DKK/kWh [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md) |
| `battery_soc` | Procent oraz energia z jawnie przyjętej pojemności | Historyczne `sensor.sun12k_battery_capacity`; zakres SOC, aktualność, dostępna energia vs nominalna |
| `battery_charge_power` / `battery_discharge_power` | Dwie nieujemne moce [kW] z ustaloną stroną AC/DC | `sensor.sun12k_battery_output_power` już istnieje; projektowy podział `max(0,−P_bat)`/`max(0,+P_bat)` po potwierdzeniu znaków obu kierunków; [MEASUREMENT_CONTRACT.md](MEASUREMENT_CONTRACT.md) |
| `grid_import_power` / `grid_export_power` | Dwie nieujemne moce [kW] na punkcie przyłącza | `sensor.sun12k_total_grid_power` już istnieje; roboczo `max(0,+P_grid)`/`max(0,−P_grid)` po potwierdzeniu znaków obu kierunków; [MEASUREMENT_CONTRACT.md](MEASUREMENT_CONTRACT.md) |
| `pv_actual_power` | kW, jawnie DC lub AC | Historyczne `sensor.pv_sum`; potwierdzić, czy obejmuje ładowanie baterii po DC; nie liczyć tego dwa razy |
| `house_load_power` | W z istniejącej encji, normalizowane do kW | `sensor.home_energy_consumption` = `pv_sum + total_grid_power + battery_output_power`; **wzór potwierdzony**, bez niezależnego pomiaru domu. Nie polegać na nim, jeśli którakolwiek składowa ma `unknown/unavailable` (szablon stosuje `float(0)`) |
| `pv_forecast_slots` | `start_utc`, `end_utc`, `energy_wh`, rozdzielczość i czas pobrania | **Natywna akcja** `forecast_solar.get_forecast` z `resolution: raw` lub `hourly` zwraca `wh_period` i `watts`; szczegóły [PV_FORECAST_CONTRACT.md](PV_FORECAST_CONTRACT.md). Dobowe sensory wyłącznie do diagnostyki; gdy akcja niedostępna, stan `unavailable`, nie fikcyjny profil |
| `house_load_forecast_slots` | średnie kW, energia kWh, jakość pokrycia, czas i wersja modelu | **Algorytm zdefiniowany** w [LOAD_FORECAST_CONTRACT.md](LOAD_FORECAST_CONTRACT.md): lokalny Recorder dla `sensor.home_energy_consumption`, bez przyszłych danych; dostępność historycznych próbek zostanie sprawdzona w HA |
| `curtailment_status` | `uncurtailed` / `curtailed_confirmed` / `curtailment_unknown` | Potrzebny zweryfikowany sygnał ograniczenia PV lub jawna klasyfikacja niepewności; pełna bateria i eksport OFF nie dowodzą ilości straconych kWh |

**Granice baterii:** 10,24 kWh to suma nominalna; zakres SOC 20–100% reprezentuje nominalnie 8,192 kWh między granicami, **nie** gwarantowaną energię dostarczoną po AC.

### Schemat pojedynczego slotu

Każda próbka prognozy i ceny: `start_utc`, `end_utc` (koniec wyłączny), `value`, `unit`, `source`, `obtained_at_utc`; prognoza historyczna także `issued_at_utc` i opcjonalny status jakości. Czas Europe/Copenhagen jest do prezentacji, obliczenia i dopasowanie przedziałów w UTC, obsługa 23/25 godzin w dni zmiany czasu. Cena godzinowa może zostać jawnie przypisana do czterech kwadransów tylko w granicach **znanego** okresu obowiązywania; nie interpolować brakującej ceny.

Horyzont cen: do końca najpóźniejszego kompletnego **opublikowanego** slotu. Zwykle około 13:00 dochodzi jutrzejsza doba; nie zakładać, że sama godzina 13:00 oznacza publikację, ani nie tworzyć prognozy ceny na 48 godzin. Prognozy PV i zużycia mogą wykraczać poza horyzont cen na potrzeby oszacowania niepewności rezerwy energii, ale nie do kalkulacji transakcji po nieznanych cenach.

## Kontrakt logiczny wyjść optymalizatora

**Poniższe nazwy są roboczym schematem wyniku planera, a nie fizycznymi encjami sterującymi.** Wyniki prezentuje warstwa HA (sensory i atrybuty planu); stabilne `entity_id` nowych encji zostaną dobrane podczas implementacji.

| Wyjście | Semantyka |
| --- | --- |
| `plan_id`, `generated_at`, `valid_until`, `price_horizon_end` | Wersja planu, czas UTC i zakres rzeczywiście znanych cen |
| `plan_status` | `valid` / `partial` / `blocked` / `expired`; nie używać częściowego planu do automatycznego sterowania |
| `charge_source` | `pv` / `grid` / `mixed` / `none` — zamierzony udział źródeł, nie potwierdzony przepływ |
| `charge_power_kw`, `discharge_power_kw` | Osobne nieujemne moce; zakaz jednoczesnego ładowania i rozładowania baterii w planie wykonawczym |
| `discharge_destination` | `home` / `export` / `mixed` / `none`; bez zgody nie wolno celowo eksportować energii z baterii |
| `target_soc_pct`, `soc_forecast_pct` | Dynamiczny cel i przyszła trajektoria SOC, **nie** twarda stała SOC |
| `pv_export_intent`, `pv_curtailment_intent` | Intencja eksportu PV lub ograniczenia produkcji, bez założenia że istnieje fizyczna regulacja |
| `grid_import_kw`, `grid_export_kw`, `pv_flow_kw` | Zaplanowane przepływy, oddzielone od pomiarów |
| `expected_net_cost_dkk`, `expected_degradation_dkk`, `expected_risk_dkk` | Oddzielne koszty fakturowe i wewnętrzne; strat konwersji nie liczyć podwójnie |
| `decision_reason`, `data_quality`, `missing_capabilities` | Uzasadnienie, jakość wejścia i blokery dla konkretnej intencji |

W każdym slocie planu: zakres UTC, ceny, prognozy, rozbicie PV na dom/baterię/sieć/ograniczenie oraz baterii na dom/eksport, import i eksport sieci, SOC przed/po, koszt, warunki zgody i status wykonalności. Plan nie jest pojedynczym poleceniem mocy; **executor** mapuje zamiary na akcje zgodnie ze zweryfikowanym kontraktem.

Implementacja i weryfikacja kolejności działań: [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md). Zasady prezentowania statusów: [HA_DASHBOARD.md](HA_DASHBOARD.md).

**Strategia czasu i wybór kanału wykonawczego:** [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md). Plan 15-minutowy nie zakłada, że można dokładnie sterować mocą przez sam limit prądu, a TOU nie jest domyślnie przepisywany. Zgodnie z obserwacją użytkownika SOC okresu TOU głównie ogranicza rozładowanie; z Grid Charge wyznacza poziom ładowania z sieci, **nie** steruje ładowaniem PV. Ostatnie nastawy falownika pozostają aktywne po utracie HA.

**Dostępne obecnie encje TOU:** `switch.sun12k_time_of_use` (włączenie); dla każdego N = 1..6: `number.sun12k_time_point_N_start` (czas), `number.sun12k_time_point_N_power` (moc), `number.sun12k_time_point_N_capacity` (SOC), `switch.sun12k_time_point_N_charge_enable` (Grid Charge). Są to encje HA już obecne w odczycie z 19.10.2026; działanie przy zapisach nie było testowane. Harmonogram powtarza się dobę, jest wrażliwy na nakładanie okien i granicę 00:00.

## Mapa akcji HA — do potwierdzenia, nie do zgadywania

| Intencja | Znany identyfikator lub brak | Co trzeba potwierdzić |
| --- | --- | --- |
| Zezwól na ładowanie z sieci | `switch.sun12k_grid_charge` — historyczne | Czy `on/off` rzeczywiście steruje tylko tą funkcją i w jakim trybie |
| Ogranicz ładowanie baterii, w tym z PV | `number.sun12k_maximum_battery_charge_current` | Projektowo: ogólny limit 0–50 A; przed realnym zapisem wymagany test skutku przez encję HA |
| Ogranicz ładowanie z sieci | `number.sun12k_maximum_battery_grid_charge_current` | Projektowo: dodatkowy limit 0–50 A; przed realnym zapisem wymagany test skutku przez encję HA |
| Ogranicz rozładowanie baterii | `number.sun12k_maximum_battery_discharge_current` | Projektowo: 0–100 A; przed realnym zapisem wymagany test skutku przez encję HA |
| Zezwól na eksport | `switch.sun12k_solar_sell` — historyczne | Czy zezwala na eksport z PV i baterii, co robi `off`, jaki jest odczyt skutku |
| Docelowy SOC / minimalny SOC | **Brak potwierdzonego ID** | Rozdzielić życzenie planisty od ustawienia ochronnego sprzętu |
| Wymuś rozładowanie na potrzeby domu | **Brak potwierdzonego ID** | Możliwość wykonania bez eksportu z baterii |
| Eksport energii z baterii | **Brak osobnego potwierdzonego sterowania** | Izolacja od PV, zgoda na konkretny plan, kWh, czas, brak zgody = brak eksportu |
| Harmonogram TOU (6 okresów) | `switch.sun12k_time_of_use`, `number.sun12k_time_point_N_start/_power/_capacity`, `switch.sun12k_time_point_N_charge_enable` (N=1..6) | Encje obecne; skutki fizyczne, granica doby, priorytety i trwałość **znane z relacji użytkownika tylko częściowo**; current-first nie zmienia tych encji |
| Przywróć pracę standardową | **Brak zweryfikowanej ścieżki** | Bezpieczny wynik także przy braku HA/Wi-Fi, bez polegania na samym zapisie w encji |

### Karta weryfikacji działania pojedynczej akcji

Przed implementacją executor każda operacja wymaga jawnego rekordu: `logical_action`, istniejące `entity_id`, domena i usługa HA, dopuszczalne wartości i jednostka, stan przed, warunki, oczekiwany **fizyczny** rezultat, niezależny odczyt zwrotny, timeout, procedura anulowania i bezpieczny stan po błędzie. Z nazwy encji nie wywodzić jej sprzętowego znaczenia.

**Sekwencja:** sprawdź aktualność planu i danych → zweryfikuj dostępne sterowanie i zgodę → zweryfikuj limit → wywołaj usługę HA → odczytaj efekt fizyczny → oznacz `confirmed` albo `failed`. Brak któregokolwiek krytycznego warunku oznacza blokadę tej akcji, nie zastąpienie nieznanej funkcji inną encją.

### Granica gotowości

- **Dokument wystarcza do implementacji:** konfiguracji wyboru encji, odczytów, normalizacji, tworzenia planu, prezentacji, diagnostyki i trybu dry-run.
- **Nie wystarcza jeszcze do uruchomienia automatycznych poleceń:** szczególnie dynamicznego SOC jako nastawy sprzętu, rozdziału PV/baterii w eksporcie i gwarancji bezpiecznego powrotu po utracie HA. To wymagania walidacyjne, a nie prośba o ponowne przekazanie już udokumentowanych 11 nazw.
- Niedostępne lub nieudowodnione sterowanie oznacza w wyniku planera `missing_capabilities` i plan niewykonalny w tej części — nie arbitralny zamiennik komendy.
