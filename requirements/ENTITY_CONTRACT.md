# Kontrakt encji Home Assistant

**Status: część identyfikatorów i stanów potwierdzona odczytem HA z 19.10.2026, pozostałe historyczne.** Szczegółowy aktualny odczyt, bilans i lista sterowań: [HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md). Sam fakt istnienia encji i jej wartość nie są dowodem semantyki fizycznej ani bezpiecznego skutku zapisu. W integracji wybór źródeł przez UI i walidacja jednostek oraz punktu pomiaru.

## Znane historycznie identyfikatory

| Rola | Historyczne ID | Wymagane sprawdzenie |
| --- | --- | --- |
| Cena spot teraz | sensor.energi_data_spotpris | Waluta, DKK/kWh, bieżący stan, czas |
| Prognoza cen / zakup z opłatami | sensor.energi_data_service | Czy zawiera pełną cenę zakupu i przyszłe sloty; atrybuty, jednostki, daty |
| SOC | sensor.sun12k_battery_capacity | Czy to SOC %, 0–100, aktualność |
| Moc PV | sensor.pv_sum | W czy kW; znak; aktualność |
| Moc domu | sensor.home_energy_consumption | W czy kW; definicja; aktualność |
| Prognoza PV dziś | sensor.energy_production_today | kWh; pełny dzień czy od teraz |
| Prognoza PV jutro | sensor.energy_production_tomorrow | kWh; horyzont; nazwa aktualna |
| Pozwolenie na eksport | switch.sun12k_solar_sell | Dokładny skutek; czy obejmuje również eksport z baterii |
| Pozwolenie na ładowanie z sieci | switch.sun12k_grid_charge | Skutek fizyczny, tryby Deye, odczyt zwrotny |
| Limit prądu ładowania | number.sun12k_maximum_battery_grid_charge_current | **NIE WYKORZYSTYWAĆ DO ZAPISU** bez weryfikacji opisanej poniżej |
| Powiadomienie mobilne | notify.mobile_app_pixel_7dk | Historyczna usługa/akcja, nie encja ze stanem; jej aktualna dostępność |

**Konflikt krytyczny:** oryginalna logika opisuje number.sun12k_maximum_battery_grid_charge_current jako limit ładowania **z sieci**, a późniejsza korekta użytkownika opisywała ograniczenie ładowania **z PV** (historyczne wartości 1 A / 40 A). Nazwa encji nie rozstrzyga semantyki. Żadnej z tych wartości nie wolno przyjąć jako bezpiecznej ani jako sposobu wyłączenia ładowania. Wymagane sprawdzenie rzeczywistej funkcji, zakresu min/max/step, priorytetów oraz skutku przy obu kierunkach przepływu energii.


## Dodatkowe identyfikatory z archiwalnego logu HA

W logu Home Assistant z **03.08.2026** (nie z bieżącego odczytu stanów) występują również poniższe entity_id. Traktować je jako **istniejące historycznie kandydaty do mapowania**, a nie potwierdzenie obecnej dostępności, aktualności, jednostki lub semantyki. Nie są to polecenia zapisu.

| Entity ID z logu | Sugerowana rola do weryfikacji |
| --- | --- |
| `sensor.sun12k_daily_energy_bought` | Dzienna zakupiona energia kWh; sprawdzić reset i punkt pomiaru |
| `sensor.sun12k_daily_energy_sold` | Dzienna sprzedana energia kWh; sprawdzić reset i punkt pomiaru |
| `sensor.sun12k_daily_energy_bought_cost` | Historyczny koszt zakupu dziennego; sprawdzić walutę, opłaty i sposób naliczania |
| `sensor.sun12k_daily_energy_sold_compensation` | Historyczny przychód z eksportu; sprawdzić prowizję i taryfę |
| `sensor.sun12k_daily_production` | Dzienna produkcja PV; czy uwzględnia DC→bateria i curtailment |
| `sensor.sun12k_total_pv_production` | Narastająca produkcja PV; w logu **ostrzeżenie o niezgodności `state_class=measurement` z `device_class=energy`** |
| `sensor.sun12k_today_charge_of_the_battery` | Dzienna energia ładowania magazynu; sprawdzić jednostkę, straty i źródła PV/sieć |
| `sensor.sun12k_today_discharge_of_the_battery` | Dzienna energia rozładowania magazynu; sprawdzić stronę DC/AC |

**Ograniczenie:** log potwierdza użycie tych nazw w sierpniu 2026, lecz **nie** dostarcza aktualnej listy encji, sposobu ich działania, serii cen ani zdolności zapisu. Wymagany jest bieżący odczyt `state` + istotnych `attributes` w HA.

## Zweryfikowane istniejące role z pliku wynik.txt (odczyt 19.10.2026)

Wymagane normalizacje i stan faktyczny:

| Rola | Encja | Odczyt i znaczenie |
| --- | --- | --- |
| PV | `sensor.pv_sum` | 3034 W; suma `sun12k_pv1_power` 2387 W + `sun12k_pv2_power` 647 W |
| Pobór domu | `sensor.home_energy_consumption` | 583 W; `sun12k_load_totalpower` = 532 W to **odrębne** wskazanie |
| Moc sieci netto | `sensor.sun12k_total_grid_power` | −2470 W, spójne z eksportem w tym stanie; do sprawdzenia znak w okresach importu |
| Moc baterii | `sensor.sun12k_battery_output_power` | +19 W, w tym stanie spójne z dodatnią mocą oddawaną do bilansu, ale brak testu obu kierunków |
| SOC | `sensor.sun12k_battery_capacity` | 97% |
| Prąd i napięcie baterii | `sensor.sun12k_battery_output_current`, `sensor.sun12k_battery_voltage` | 0,35 A / 56,69 V; sprawdzić znak i punkt pomiaru |
| Cena spot | `sensor.energi_data_spotpris` | 1,75508376559425 DKK/kWh |
| Cena zakupu — kandydat | `sensor.energi_data_service` | 2,23828751559425 DKK/kWh; kompletność opłat i profil przyszły **niepotwierdzone** |
| Produkcja PV dziś | `sensor.sun12k_daily_production` | 23,5 kWh; sprawdzić reset i DC/AC |
| Ładowanie/rozładowanie dziś | `sensor.sun12k_today_charge_of_the_battery`, `sensor.sun12k_today_discharge_of_the_battery` | 8,6 kWh / 1,2 kWh; strona pomiaru nieznana |
| Prognoza PV | `sensor.energy_production_today`, `sensor.energy_production_tomorrow`, `sensor.energy_production_today_remaining` | 15,865 / 7,536 / 4,431 kWh; nie zastępują godzinowych slotów |

Kontrola jednej migawki: **3034 W PV + 19 W bateria = 583 W dom + 2470 W eksport = 3053 W**; to weryfikacja spójności arytmetycznej, nie walidacja całego modelu AC/DC. Stan `last_updated` nie musi być timestampem ostatniej raportowanej próbki; do oceny świeżości potrzebna jest semantyka aktualizacji źródła lub `last_reported`.

**Bieżące encje Deye potwierdzone jako istniejące, ale NIE jako bezpieczne funkcje zapisu:** `switch.sun12k_solar_sell`, `switch.sun12k_grid_charge`, `switch.sun12k_time_of_use`, sześć `switch.sun12k_time_point_N_charge_enable`; `number.sun12k_maximum_battery_charge_current`, `number.sun12k_maximum_battery_discharge_current`, `number.sun12k_maximum_battery_grid_charge_current`; po sześć `number.sun12k_time_point_N_start`, `_power`, `_capacity`. Udokumentowane przez HA min/max prądów ±16 777 220 A **są niewiarygodne jako granice sprzętowe**.

**Pozostałości po starej integracji:** zgodnie z informacją użytkownika z 20.10.2026 encje `battery_controller.*` są osieroconymi pozostałościami; Energy Co-Pilot **ignoruje je całkowicie** (nie używa danych, decyzji, statusu przełączników ani nie blokuje działania z ich powodu). Nie zmienia to obowiązku wykrycia **rzeczywiście aktywnego**, zewnętrznego sterowania tymi samymi nastawami Deye, jeśli kiedyś zostanie zaobserwowane.

Więcej szczegółów i zastrzeżeń: [HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md).

## Nieznane, lecz wymagane do planowania i wykonania

- **Częściowo ustalone ID mocy i liczników:** znamy `sun12k_total_grid_power`, `sun12k_battery_output_power`, liczniki energii dziennej i całkowitej. Nadal trzeba potwierdzić **konwencję znaków w obu kierunkach**, stronę AC/DC, świeżość pomiaru, przejścia import/eksport i ładowanie/rozładowanie; nie przyjmować, że jeden bilans w stanie eksportowym jest kompletną kalibracją.
- Godzinowa / kwartalna seria cen zakupu i sprzedaży z kompletnymi timestampami; profil PV w slotach; prognoza zużycia.
- **Produkcja PV i curtailment:** potwierdzić, czy encja mocy/energii PV obejmuje również ładowanie po DC; jeśli dostępne, wskazać sygnał aktywnego ograniczenia produkcji (limit eksportu, MPPT, status curtailment) i zweryfikować jego znaczenie. Pełna bateria + wyłączony eksport to jedynie przesłanki; nie dają pomiaru niewyprodukowanych kWh. Migawki prognoz muszą mieć czas pobrania i daty/sloty ważności, aby porównanie z późniejszą produkcją nie wykorzystywało zaktualizowanej prognozy.
- ID i znaczenie sterowań **docelowym SOC, limitem mocy ładowania, wymuszonym rozładowaniem, kierunkiem eksportu z baterii, harmonogramem Deye i przywróceniem trybu fabrycznego**. Nie wiadomo, czy HA udostępnia wszystkie te funkcje.
- Warunki i możliwości niezależnego potwierdzania rezultatów poleceń.

## Minimalny test kontraktu (wyłącznie odczyt)

Dla każdej wybranej pozycji ustalić: entity_id, domain, bieżący state, attributes (w tym unit_of_measurement i granice), czas ostatniej wiarygodnej próbki, źródło fizyczne, częstotliwość aktualizacji, znak, typ, zakres, wariant unknown/unavailable. Dla serii: układ atrybutów, strefę czasową, brakujące i powtarzające się sloty, zmianę czasu (DST), cenę importu **z opłatami** i cenę spot **bez opłat**.

Przypadek testowy jakości PV: prognoza 60 kWh, pomiar 35 kWh, część dnia pełna bateria i eksport wyłączony. Nie obliczać automatycznie błędu prognozy −25 kWh; najpierw oznaczyć okresy podejrzane lub potwierdzone jako ograniczone. Szczegóły: [ARCHITECTURE.md](ARCHITECTURE.md#wiarygodność-prognoz-pv-przy-ograniczeniu-produkcji).

Test każdej **akcji zapisu** wymaga dodatkowo odrębnej, świadomie nadzorowanej procedury na urządzeniu: stan początkowy, dozwolone wartości, wywołana usługa HA, rzeczywisty odczyt zwrotny i reakcja na błąd, reset/restart i utratę komunikacji. Samo HTTP 200 lub zmiana stanu encji nie potwierdza skutku fizycznego.

**Nie wykonywać takich testów zapisu przez Codexa ani automatycznie.** Brak jednej kluczowej funkcji blokuje odpowiednią automatyzację; nie zastępować jej inną, podobnie nazwaną encją.


Aktualne stany, jednostki i źródła należy odczytać według [HA_READONLY_CAPTURE.md](HA_READONLY_CAPTURE.md); listy historycznych nazw nie zastępują odczytu.

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
| `spot_price_slots` | `start_utc, end_utc, value_dkk_kwh` | Przyszłe rzeczywiście opublikowane spot, bez uzupełniania fikcyjnymi godzinami |
| `buy_price_slots` | Takie same przedziały, cena **końcowa** z opłatami | HA udostępnia cenę końcową wg użytkownika; historyczne `sensor.energi_data_service` jest kandydatem dla prognozy cen, lecz komplet taryfy i format trzeba zweryfikować |
| `sell_price_slots` | DKK/kWh, wyliczana | `spot_price_slots - 0,0215 DKK/kWh` (ustalona prowizja Vindstød); osobna encja nie jest konieczna |
| `battery_soc` | Procent oraz energia z jawnie przyjętej pojemności | Historyczne `sensor.sun12k_battery_capacity`; zakres SOC, aktualność, dostępna energia vs nominalna |
| `battery_charge_power` / `battery_discharge_power` | Dwie nieujemne moce [kW] z ustaloną stroną AC/DC | Pomiary istnieją wg użytkownika; identyfikatory jeszcze nie zapisane w bieżącym rejestrze; znak i fizyczny punkt pomiaru krytyczne |
| `grid_import_power` / `grid_export_power` | Dwie nieujemne moce [kW] na punkcie przyłącza | Pomiary istnieją wg użytkownika, nazwy w bieżącym rejestrze nieznane |
| `pv_actual_power` | kW, jawnie DC lub AC | Historyczne `sensor.pv_sum`; potwierdzić, czy obejmuje ładowanie baterii po DC; nie liczyć tego dwa razy |
| `house_load_power` | kW na AC, bez ładowania baterii | Historyczne `sensor.home_energy_consumption`; zweryfikować definicję |
| `pv_forecast_slots` | kW lub kWh na każdy slot, z czasem wydania i horyzontem | Forecast.Solar; historyczne `sensor.energy_production_today` i `sensor.energy_production_tomorrow` pokazują dobowe sumy, ale samym sumom brakuje rozkładu godzinowego |
| `house_load_forecast_slots` | kW średnie na slot, czas i jakość | Do opracowania na bazie historii HA, bez przecieku przyszłych danych |
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

## Mapa akcji HA — do potwierdzenia, nie do zgadywania

| Intencja | Znany identyfikator lub brak | Co trzeba potwierdzić |
| --- | --- | --- |
| Zezwól na ładowanie z sieci | `switch.sun12k_grid_charge` — historyczne | Czy `on/off` rzeczywiście steruje tylko tą funkcją i w jakim trybie |
| Ogranicz ładowanie | `number.sun12k_maximum_battery_grid_charge_current` — **sporne znaczenie** | PV/sieć, jednostki A, min/max/step, skutek i zakres przed jakimkolwiek zapisem |
| Zezwól na eksport | `switch.sun12k_solar_sell` — historyczne | Czy zezwala na eksport z PV i baterii, co robi `off`, jaki jest odczyt skutku |
| Docelowy SOC / minimalny SOC | **Brak potwierdzonego ID** | Rozdzielić życzenie planisty od ustawienia ochronnego sprzętu |
| Wymuś rozładowanie na potrzeby domu | **Brak potwierdzonego ID** | Możliwość wykonania bez eksportu z baterii |
| Eksport energii z baterii | **Brak osobnego potwierdzonego sterowania** | Izolacja od PV, zgoda na konkretny plan, kWh, czas, brak zgody = brak eksportu |
| Harmonogram i priorytety sterowania | **Brak potwierdzonych ID** | Priorytety i trwałość zapisanych wartości; konflikt z własnym planistą |
| Przywróć pracę standardową | **Brak zweryfikowanej ścieżki** | Bezpieczny wynik także przy braku HA/Wi-Fi, bez polegania na samym zapisie w encji |

### Karta weryfikacji działania pojedynczej akcji

Przed implementacją executor każda operacja wymaga jawnego rekordu: `logical_action`, istniejące `entity_id`, domena i usługa HA, dopuszczalne wartości i jednostka, stan przed, warunki, oczekiwany **fizyczny** rezultat, niezależny odczyt zwrotny, timeout, procedura anulowania i bezpieczny stan po błędzie. Z nazwy encji nie wywodzić jej sprzętowego znaczenia.

**Sekwencja:** sprawdź aktualność planu i danych → zweryfikuj dostępne sterowanie i zgodę → zweryfikuj limit → wywołaj usługę HA → odczytaj efekt fizyczny → oznacz `confirmed` albo `failed`. Brak któregokolwiek krytycznego warunku oznacza blokadę tej akcji, nie zastąpienie nieznanej funkcji inną encją.

### Granica gotowości

- **Dokument wystarcza do implementacji:** konfiguracji wyboru encji, odczytów, normalizacji, tworzenia planu, prezentacji, diagnostyki i trybu dry-run.
- **Nie wystarcza jeszcze do uruchomienia automatycznych poleceń:** szczególnie dynamicznego SOC jako nastawy sprzętu, rozdziału PV/baterii w eksporcie i gwarancji bezpiecznego powrotu po utracie HA. To wymagania walidacyjne, a nie prośba o ponowne przekazanie już udokumentowanych 11 nazw.
- Niedostępne lub nieudowodnione sterowanie oznacza w wyniku planera `missing_capabilities` i plan niewykonalny w tej części — nie arbitralny zamiennik komendy.
