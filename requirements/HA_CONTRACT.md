# Home Assistant — pomiary, encje, ceny i prognoza PV

**Decyzje użytkownika obowiązują wyłącznie według [REQUIREMENTS.md](REQUIREMENTS.md).** Poniższe części są techniczną dokumentacją implementacyjną; starsze opinie o uprawnieniach do TOU, 0 A i stałym koszcie degradacji nie są normatywne.


---

## ENTITY CONTRACT


**Status: część identyfikatorów i stanów potwierdzona odczytem HA z 19.10.2026, pozostałe historyczne.** Szczegółowy aktualny odczyt, bilans i lista sterowań: [HA_CONTRACT.md](HA_CONTRACT.md). Sam fakt istnienia encji i jej wartość nie są dowodem semantyki fizycznej ani bezpiecznego skutku zapisu. W integracji wybór źródeł przez UI i walidacja jednostek oraz punktu pomiaru.

## Granica integracji: wyłącznie encje i usługi Home Assistant

**Zasada obowiązująca:** Energy Co-Pilot odczytuje stany/atrybuty encji HA i steruje wyłącznie poprzez natywne usługi HA na zweryfikowanych encjach (np. `number.set_value`, `switch.turn_on/off`). Integracja **nie** odczytuje ani nie zapisuje rejestrów Modbus, nie otwiera połączenia z falownikiem i nie modyfikuje ESPHome, YAML, firmware ani istniejącego mostka. Opis istniejącego mostka ESPHome, jeżeli jest dostępny poza repo, może służyć wyłącznie do objaśnienia encji; nie jest kontraktem sterowania i nie powinien być wymaganym plikiem projektu.

**Przyjęte semantyki na etapie projektowania (zgodnie z dyspozycją użytkownika):**

| Encja HA | Rola w Co-Pilot | Limit polityki |
| --- | --- | --- |
| `number.sun12k_maximum_battery_charge_current` | Ogólny maksymalny prąd ładowania baterii, także ładowania z PV | 0–50 A |
| `number.sun12k_maximum_battery_discharge_current` | Maksymalny prąd rozładowania baterii | 0–100 A |
| `number.sun12k_maximum_battery_grid_charge_current` | Dodatkowy maksymalny prąd ładowania z sieci | 0–50 A |

Użytkownik potwierdził 20.10.2026, że falownik przyjmuje zadane wartości i rzeczywiście na nie reaguje. To potwierdzenie działania regulacji od użytkownika, nie dowód poprawności dowolnej akcji automatyki. Nie pytać o każdy parametr osobno; przy integracji wykonać zwykłą kontrolę odczytu i skutku oraz walidację fizycznych limitów. Więcej: [EXECUTION.md](EXECUTION.md).

## Aktualne role — obserwacja z 19.10.2026

[HA_CONTRACT.md](HA_CONTRACT.md) przechowuje pojedynczy historyczny odczyt jednostek, kandydatów sterowania i pomiarów. Dla Codexa **nie jest** to aktualna konfiguracja: `entity_id` mapuj przez UI, sprawdzaj jednostkę, znak, źródło, dostępność i stan w chwili działania. Nie przenoś list z archiwalnych logów ani nie korzystaj z encji `battery_controller.*`.

## Nieznane, lecz wymagane do planowania i wykonania

- **Mapa pomiarów:** znane `sun12k_total_grid_power`, `sun12k_battery_output_power`, `pv_sum` i **potwierdzony pochodny** `home_energy_consumption`; bez dodatkowych liczników. Wzór i kontrola brakujących składowych: [HA_CONTRACT.md](HA_CONTRACT.md). **Znaki potwierdzone przez użytkownika (20.10.2026):** sieć + import / - eksport, bateria + rozładowanie / - ładowanie. Nadal do sprawdzenia: strona AC/DC, aktualność i spójność fizyczna; nie przyjmować, że jeden bilans w stanie eksportowym jest kompletną kalibracją.
- **Ceny: rozwiązane.** Timestampowane serie zakupu i spot: [HA_CONTRACT.md](HA_CONTRACT.md). **PV: kontrakt dostępu określony** — preferowana natywna akcja HA `forecast_solar.get_forecast` zwraca godzinowy lub 15-minutowy profil `wh_period`/`watts`: [HA_CONTRACT.md](HA_CONTRACT.md). Do sprawdzenia przy uruchomieniu przez Codexa: dostępność akcji w tej instalacji i wybór wpisu konfiguracji; nie wymaga ręcznego kopiowania prognozy. Prognoza zużycia: profil tworzony lokalnie na danych Recorder `sensor.home_energy_consumption`, według [OPTIMIZATION.md](OPTIMIZATION.md).
- **Produkcja PV i curtailment:** potwierdzić, czy encja mocy/energii PV obejmuje również ładowanie po DC; jeśli dostępne, wskazać sygnał aktywnego ograniczenia produkcji (limit eksportu, MPPT, status curtailment) i zweryfikować jego znaczenie. Pełna bateria + wyłączony eksport to jedynie przesłanki; nie dają pomiaru niewyprodukowanych kWh. Migawki prognoz muszą mieć czas pobrania i daty/sloty ważności, aby porównanie z późniejszą produkcją nie wykorzystywało zaktualizowanej prognozy.
- ID i znaczenie sterowań **docelowym SOC, limitem mocy ładowania, wymuszonym rozładowaniem, kierunkiem eksportu z baterii, harmonogramem Deye i przywróceniem trybu fabrycznego**. Nie wiadomo, czy HA udostępnia wszystkie te funkcje.
- Warunki i możliwości niezależnego potwierdzania rezultatów poleceń.

## Minimalny test kontraktu (wyłącznie odczyt)

Dla każdej wybranej pozycji ustalić: entity_id, domain, bieżący state, attributes (w tym unit_of_measurement i granice), czas ostatniej wiarygodnej próbki, źródło fizyczne, częstotliwość aktualizacji, znak, typ, zakres, wariant unknown/unavailable. Dla serii: układ atrybutów, strefę czasową, brakujące i powtarzające się sloty, zmianę czasu (DST), cenę importu **z opłatami** i cenę spot **bez opłat**.

Przypadek testowy jakości PV: prognoza 60 kWh, pomiar 35 kWh, część dnia pełna bateria i eksport wyłączony. Nie obliczać automatycznie błędu prognozy −25 kWh; najpierw oznaczyć okresy podejrzane lub potwierdzone jako ograniczone. Szczegóły: [EXECUTION.md](EXECUTION.md).

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

**Ważne:** wartość `0 A` jest dopuszczona w polityce i użytkownik potwierdził działanie nastaw. Nie utożsamiać jednak ogólnego limitu prądu z aktywacją Grid Charge ani nastawą SOC. Podczas wdrożenia sprawdzać na HA stan i fizyczny skutek komend oraz bezpieczną procedurę wyjścia bez dodatkowej ankiety użytkownika.

**Reguła implementacji:** osobno walidować zakres przy konfiguracji, tworzeniu planu, przed wykonaniem akcji i po odczycie stanu. Nie podmieniać nieprawidłowej komendy przez ciche przycięcie do granicy; odrzucić ją i wyjaśnić powód w rejestrze decyzji.

## Kontrakt logiczny wejść

**Zasada:** nazwy ról poniżej są wewnętrznymi kluczami optymalizatora, **nie** nazwami istniejących encji. Każdą rolę użytkownik mapuje przez UI na istniejące źródło HA; przed wykorzystaniem normalizator sprawdza jednostkę, znaczenie, aktualność i źródło. Nie zgadywać identyfikatorów.

| Rola | Znormalizowane dane | Status mapowania i walidacja |
| --- | --- | --- |
| `spot_price` | DKK/kWh, czas obowiązywania | Historyczne `sensor.energi_data_spotpris`; sprawdzić taryfę DK1, jednostki, daty |
| `spot_price_slots` | `start_utc, end_utc, value_dkk_kwh` | `sensor.energi_data_spotpris.attributes.raw_today/raw_tomorrow[*].hour/price`; publikacja jutra wyłącznie przy poprawnym `tomorrow_valid`; [HA_CONTRACT.md](HA_CONTRACT.md) |
| `buy_price_slots` | Te same przedziały, cena **końcowa** z opłatami | `sensor.energi_data_service.attributes.raw_today/raw_tomorrow[*].hour/price`; **format już potwierdzony**; opłaty/taryfy już w wartości, nie doliczać ponownie |
| `sell_price_slots` | DKK/kWh, **bez przeliczeń** | `sensor.energi_data_spotpris.attributes.raw_today/raw_tomorrow[*].price` wprost z HA; próg eksportu PV 0,40 DKK/kWh [REQUIREMENTS.md](REQUIREMENTS.md) |
| `battery_soc` | Procent oraz energia z jawnie przyjętej pojemności | Historyczne `sensor.sun12k_battery_capacity`; zakres SOC, aktualność, dostępna energia vs nominalna |
| `battery_charge_power` / `battery_discharge_power` | Dwie nieujemne moce [kW] z ustaloną stroną AC/DC | `sensor.sun12k_battery_output_power` już istnieje; projektowy podział `max(0,−P_bat)`/`max(0,+P_bat)` po potwierdzeniu znaków obu kierunków; [HA_CONTRACT.md](HA_CONTRACT.md) |
| `grid_import_power` / `grid_export_power` | Dwie nieujemne moce [kW] na punkcie przyłącza | `sensor.sun12k_total_grid_power` już istnieje; roboczo `max(0,+P_grid)`/`max(0,−P_grid)` po potwierdzeniu znaków obu kierunków; [HA_CONTRACT.md](HA_CONTRACT.md) |
| `pv_actual_power` | kW, jawnie DC lub AC | `sensor.pv_sum`: potwierdzona suma na wejściach PV DC falownika, przed rozdziałem mocy na AC/baterię; nie dodawać osobno PV kierowanego do baterii ani nie utożsamiać z potencjałem przed curtailment |
| `house_load_power` | W z istniejącej encji, normalizowane do kW | `sensor.home_energy_consumption` = `pv_sum + total_grid_power + battery_output_power`; **wzór potwierdzony**, bez niezależnego pomiaru domu. Nie polegać na nim, jeśli którakolwiek składowa ma `unknown/unavailable` (szablon stosuje `float(0)`) |
| `pv_forecast_slots` | `start_utc`, `end_utc`, `energy_wh`, rozdzielczość i czas pobrania | **Natywna akcja** `forecast_solar.get_forecast` z `resolution: raw` lub `hourly` zwraca `wh_period` i `watts`; szczegóły [HA_CONTRACT.md](HA_CONTRACT.md). Dobowe sensory wyłącznie do diagnostyki; gdy akcja niedostępna, stan `unavailable`, nie fikcyjny profil |
| `house_load_forecast_slots` | średnie kW, energia kWh, jakość pokrycia, czas i wersja modelu | **Algorytm zdefiniowany** w [OPTIMIZATION.md](OPTIMIZATION.md): lokalny Recorder dla `sensor.home_energy_consumption`, bez przyszłych danych; dostępność historycznych próbek zostanie sprawdzona w HA |
| `curtailment_status` | `uncurtailed` / `curtailed_confirmed` / `curtailment_unknown` | Potrzebny zweryfikowany sygnał ograniczenia PV lub jawna klasyfikacja niepewności; pełna bateria i eksport OFF nie dowodzą ilości straconych kWh |

**Granice baterii:** 10,24 kWh to suma nominalna; twarda polityka minimum SOC **20%** oznacza zakres planowania 20–100% i nominalnie 8,192 kWh między granicami, **nie** gwarantowaną energię dostarczoną po AC. Nie planować rozładowania poniżej 20%; wyższy limit BMS/urządzenia ma pierwszeństwo.

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

Implementacja i weryfikacja kolejności działań: [EXECUTION.md](EXECUTION.md). Zasady prezentowania statusów: [EXECUTION.md](EXECUTION.md).

**Strategia czasu i wybór kanału wykonawczego:** [EXECUTION.md](EXECUTION.md). Plan 15-minutowy nie zakłada, że można dokładnie sterować mocą przez sam limit prądu, a TOU nie jest domyślnie przepisywany. Zgodnie z obserwacją użytkownika SOC okresu TOU głównie ogranicza rozładowanie; z Grid Charge wyznacza poziom ładowania z sieci, **nie** steruje ładowaniem PV. Ostatnie nastawy falownika pozostają aktywne po utracie HA.

**Dostępne obecnie encje TOU:** `switch.sun12k_time_of_use` (włączenie); dla każdego N = 1..6: `number.sun12k_time_point_N_start` (czas), `number.sun12k_time_point_N_power` (moc), `number.sun12k_time_point_N_capacity` (SOC), `switch.sun12k_time_point_N_charge_enable` (Grid Charge). Są to encje HA już obecne w odczycie z 19.10.2026; działanie przy zapisach nie było testowane. Harmonogram powtarza się dobę, jest wrażliwy na nakładanie okien i granicę 00:00.

## Mapa akcji HA — do potwierdzenia, nie do zgadywania

| Intencja | Znany identyfikator lub brak | Co trzeba potwierdzić |
| --- | --- | --- |
| Zezwól na ładowanie z sieci | `switch.sun12k_grid_charge` — historyczne | Czy `on/off` rzeczywiście steruje tylko tą funkcją i w jakim trybie |
| Ogranicz ładowanie baterii, w tym z PV | `number.sun12k_maximum_battery_charge_current` | Projektowo: ogólny limit 0–50 A; przed realnym zapisem wymagany test skutku przez encję HA |
| Ogranicz ładowanie z sieci | `number.sun12k_maximum_battery_grid_charge_current` | Projektowo: dodatkowy limit 0–50 A; przed realnym zapisem wymagany test skutku przez encję HA |
| Ogranicz rozładowanie baterii | `number.sun12k_maximum_battery_discharge_current` | Projektowo: 0–100 A; przed realnym zapisem wymagany test skutku przez encję HA |
| Zezwól na eksport | `switch.sun12k_solar_sell` | Użytkownik potwierdził 20.10.2026: w obecnej konfiguracji zezwala na eksport wyłącznie nadwyżki PV; eksport baterii jest wyłączony. Efekt ON/OFF i izolację po zmianie TOU sprawdzić przed live |
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


---

## MEASUREMENT CONTRACT


**Cel:** jedna definicja pomiarów wejściowych do planera, diagnostyki i backtestów. **Status danych:** użytkownik potwierdził dokładny szablon `sensor.home_energy_consumption` jako sumę PV, sieci i baterii. Korzystamy z istniejących encji HA; nie projektujemy nowych liczników ani przekładników. Nie odczytywać rejestrów Modbus; korzystać z istniejących encji Home Assistant.

Źródła projektu: [HA_CONTRACT.md](HA_CONTRACT.md), [HA_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION.md](OPTIMIZATION.md), [OPTIMIZATION.md](OPTIMIZATION.md), [VALIDATION.md](VALIDATION.md).

## 1. Jedna mapa wejść, bez zdublowanych kanałów

| Rola logiczna | Podstawowa encja HA | Zaobserwowane | Interpretacja do przyjęcia projektowo |
| --- | --- | --- | --- |
| Moc PV rzeczywista | `sensor.pv_sum` | +3034 W | **Potwierdzone przez użytkownika:** suma mocy dostarczanej na wejścia PV DC falownika (MPPT1 + MPPT2), przed rozdziałem na baterię/dom/eksport. Nie mierzy niewykorzystanego potencjału PV |
| PV wejście MPPT 1 | `sensor.sun12k_pv1_power` | +2387 W | Składnik agregatu, **nie dodawać ponownie** do `pv_sum` |
| PV wejście MPPT 2 | `sensor.sun12k_pv2_power` | +647 W | Składnik agregatu, **nie dodawać ponownie** do `pv_sum` |
| Zużycie domu | `sensor.home_energy_consumption` | +583 W | **Potwierdzony template:** `pv_sum + total_grid_power + battery_output_power`; wejście operacyjne, **nie niezależny pomiar** |
| Inna moc LOAD | `sensor.sun12k_load_totalpower` | +532 W | Osobny punkt pomiarowy; nie podmieniać nim automatycznie mocy całego domu i nie dodawać do domu |
| Moc netto na sieci | `sensor.sun12k_total_grid_power` | −2470 W | **Hipoteza znaków:** dodatnia = zakup, ujemna = eksport; przy zakupie jeszcze niepotwierdzona |
| Inny pomiar sieci | `sensor.sun12k_out_of_grid_total_power_2` | −2483 W | Alternatywny sygnał/kanał; **nie sumować** z `total_grid_power` |
| Moc baterii | `sensor.sun12k_battery_output_power` | +19 W | **Hipoteza znaków:** dodatnia = rozładowanie, ujemna = ładowanie; przy ujemnym jeszcze niepotwierdzona |
| Napięcie baterii | `sensor.sun12k_battery_voltage` | 56,69 V | Pomiary DC; walidować czas i jednostkę |
| Prąd baterii | `sensor.sun12k_battery_output_current` | +0,35 A | Hipoteza znaku zgodnego z mocą; sprawdzić obie strony i to, czy jest wejściem do obliczenia mocy |
| SOC | `sensor.sun12k_battery_capacity` | 97% | Jedna miara SOC; 20–100% to robocze granice polityki, nie potwierdzenie rzeczywistej pojemności użytecznej |

**Zabronione źródła:** encje `battery_controller.*` są pozostałościami i zostały przez użytkownika wykluczone. Prognoza Forecast.Solar (`forecast_solar.get_forecast`) nie jest pomiarem produkcji rzeczywistej. Moc PV już skierowana po DC do baterii **należy do całkowitej produkcji PV**, nie jest drugim niezależnym zyskiem energetycznym.

## 2. Konwencja normalizacji — hipoteza do symulacji i testów

Przy znaku `P_grid_signed_W > 0` jako zakupie, `P_batt_signed_W > 0` jako rozładowaniu:

```text
pv_kw              = max(0, P_pv_W / 1000)
house_kw           = max(0, P_house_W / 1000)   # wyłącznie poprawny, zweryfikowany odczyt
grid_import_kw     = max(0, P_grid_signed_W / 1000)
grid_export_kw     = max(0, -P_grid_signed_W / 1000)
battery_discharge_kw = max(0, P_batt_signed_W / 1000)
battery_charge_kw    = max(0, -P_batt_signed_W / 1000)
```

Wszystkie wartości kW są **nieujemne** po podziale na kierunki; surowy znak zachować w diagnostyce. Przy braku potwierdzonej konwencji dla **obu** stron status `sign_assumption_only`. Nie przepisywać wartości `abs(P)` bez określonego kierunku. Jeżeli obie składowe import/eksport powstają z *jednego* kanału mocy netto, nie raportować równoczesnego importu i eksportu jako osobnych fizycznych zdarzeń z tej samej próbki.

## 3. Przykładowa kontrola chwilowego bilansu — i jej granice

Dla przybliżonego, **stratami nieobjętego** sprawdzenia orientacyjnego:

```text
residual_W = PV_W + battery_output_W + grid_signed_W - house_W
           = 3034 + 19 - 2470 - 583 = 0 W
```

Podana migawka numerycznie pasuje. Dodatkowe sprawdzenia:
- `PV1 + PV2 = 2387 + 647 = 3034 W` — potwierdza **agregację**, nie niezależny trzeci pomiar;
- `V_batt × I_batt = 56,69 × 0,35 ≈ 19,84 W`, blisko stanu sensora baterii `19 W`; zgodność jest pomocnicza, może też wynikać z pochodnych encji;
- `sun12k_load_totalpower = 532 W` różni się od `home_energy_consumption = 583 W` o **51 W**. Nie wolno uznać ich za ten sam pomiar.

**Rozstrzygnięte przez użytkownika:** wzór encji jest dokładnie następujący:

```jinja
{{ (states('sensor.pv_sum') | float(0)) +
   (states('sensor.sun12k_total_grid_power') | float(0)) +
   (states('sensor.sun12k_battery_output_power') | float(0))
}}
```

**Zerowy residual jest tożsamością wynikającą z tego wzoru.** Nie jest niezależnym testem sprawności i nie wymaga dodatkowej infrastruktury. Używamy tej encji jako istniejącego operacyjnego pomiaru poboru domu i historycznego wejścia do prognozy. Istotna praktyczna kwestia: `float(0)` zastępuje wartością zero brak lub błąd jednego ze źródeł. Co-Pilot sprawdza, czy **trzy istniejące encje składowe** nie są `unknown/unavailable` przed uznaniem wyniku za wiarygodny. Nie dodajemy sensorów.

**Granice bilansu:** `PV` prawdopodobnie po DC, `grid` i `house` prawdopodobnie po AC. Przy niezerowym ładowaniu/rozładowaniu występują straty falownika, przewodów i torów baterii, więc surowe równanie `PV + batt + grid = house` **nie jest ogólną tożsamością fizyczną** i nie wolno wymuszać residual 0 w każdym slocie. Produkcyjny model przepływów DC/AC z odrębnymi sprawnościami opisuje [OPTIMIZATION.md](OPTIMIZATION.md).

**Synchronizacja:** migawka 19.10 obejmowała wartości z przesunięciem rzędu kilku sekund. Suma asynchronicznych wartości może nie być spójna przy zmianach PV czy obciążenia. `last_updated` w HA jest czasem zmiany stanu, a nie zawsze czasem ostatniego pomiaru. Kod powinien odróżnić `last_reported` (jeżeli dostępne), realną datę próbki w atrybutach oraz brak wiarygodnego czasu; dla porównania ograniczać odstęp czasowy i jawnie flagować `snapshot_not_synchronous`.

## 4. Model licznika energii i rachunku — bez podwójnego liczenia

| Kanał do statystyki | Encja | Odczyt 19.10.2026 | Znaczenie/warunek |
| --- | --- | --- | --- |
| Zakup energii dzisiaj | `sensor.sun12k_daily_energy_bought` | 4,3 kWh | Historia **importu**, nie wielkość dodatkowa do importu wyliczonego z mocy |
| Sprzedaż energii dzisiaj | `sensor.sun12k_daily_energy_sold` | 4,3 kWh | Historia **eksportu** |
| PV produkcja dzisiaj | `sensor.sun12k_daily_production` | 23,5 kWh | Może obejmować DC→baterię; nie dodawać jej do chwilowego PV przy agregacji |
| Magazyn ładowanie dzisiaj | `sensor.sun12k_today_charge_of_the_battery` | 8,6 kWh | Nie liczyć jako osobny zakup albo produkcję bez znajomości źródła ładowania |
| Magazyn rozładowanie dzisiaj | `sensor.sun12k_today_discharge_of_the_battery` | 1,2 kWh | Nie jest równoznaczne ze sprzedażą do sieci |
| Cena zakupu dzisiaj (licznik pomocniczy) | `sensor.sun12k_daily_energy_bought_cost` | 0 DKK przy 4,3 kWh importu | **Podejrzane**; nie przyjmować jako rzeczywistej ceny/kosztu |
| Wynagrodzenie za sprzedaż (pomocnicze) | `sensor.sun12k_daily_energy_sold_compensation` | 7,136... DKK | Tylko porównanie kontrolne; stawki mogą mieć inny czas, reset i model opłat |

**Rachunek netto:** osobno wyliczać koszt **faktycznego importu** według `sensor.energi_data_service.raw_today/raw_tomorrow` i przychód **faktycznego eksportu** według `sensor.energi_data_spotpris.raw_today/raw_tomorrow` — **bez jakichkolwiek korekt cen**. Do przyszłych decyzji pracować na prognozowanym eksporcie/importie, nie na liczniku dziennym jako pomiarze mocy.

**Dwa tryby obliczania rzeczywistych kWh:** (a) przyrost **zweryfikowanego**, nierestartowanego licznika `kWh`, lub (b) całka z mocy z rzeczywistymi odstępami próbek. **Nie sumować** wyników obu metod jako dwóch energii. Porównywać je jako **kontrolę** po dopasowaniu tych samych przedziałów. Liczniki dobowe mają reset — różnica po północy nie jest ujemnym importem/eksportem.

**Wymaganie kalibracyjne:** bieżąca moc PV, domu i baterii to próbki [W], nie narastające kWh. Nie mnożyć każdej próbki przez stałe 15 min, jeżeli próbki pojawiają się częściej/rzadziej lub występuje przerwa; potrzebna jawna metoda interpolacji/integracji i status pokrycia. Unikać podwójnego liczenia przepływu PV→bateria: do modelu używać **jednego** przepływu `s_b` po DC, nie dodawać go drugi raz do `PV`.

## 5. Reguły jakości i obsługi niezgodności

1. `unknown`, `unavailable`, `NaN`, brak jednostki lub konflikt jednostek = **brak wiarygodnego wejścia**, nie zero.
2. Stan `sensor.sun12k_total_grid_power < 0` w zaobserwowanym eksporcie to **silna wskazówka**, nie dowód działania tego znaku podczas importu; analogicznie `battery_output_power > 0` dla rozładowania i wartość ujemna przy ładowaniu.
3. Weryfikację fizycznych znaków oprzeć na **niewymagających zapisu** porównaniach różnych naturalnie występujących stanów: dzień PV→eksport, noc importu, rzeczywiste ładowanie baterii, rozładowanie baterii. Jeśli takich historii brak, status `unverified_direction`, model nie może potajemnie przedefiniować znaków.
4. Status `derived_confirmed` dla `home_energy_consumption`: pochodność jest **potwierdzona wzorem użytkownika**. Nie powtarzać testu niezależności, który z konstrukcji daje zero; kontrolować dostępność jego trzech składowych.
5. Każde porównanie odczytów wymaga **podobnego czasu pomiaru** i jawnego dopuszczalnego odchylenia względem realnej rozdzielczości sensorów; brak daty ostatniego raportu oznaczyć i ograniczyć diagnozę.
6. Błąd bilansu nie jest automatycznie błędem falownika ani powodem „uczenia korekty mocy”. Najpierw kierunki znaków, punkty AC/DC, pochodność szablonów, rozdzielczość, asynchroniczność i straty.
7. Gdy pomiary importu/eksportu nie są zweryfikowane w obu kierunkach, monitor/dry-run nadal działa z ograniczoną diagnostyką; **nie raportować oszczędności z dokładnością do groszy jako empirycznie dowiedzionych**.

### Historia sensora pochodnego — kontrola jakości po czasie

`sensor.home_energy_consumption` jest wyliczany z trzech źródeł przy użyciu `float(0)`. Weryfikacja tylko **aktualnych** `pv_sum`, `total_grid_power` i `battery_output_power` **nie oczyszcza danych historycznych**. Dla każdego interwału uczenia i backtestu ustalić, czy źródła były wtedy dostępne i zsynchronizowane; historyczny template o stanie liczbowym może być błędny mimo obecnie poprawnych encji. Jeśli Recorder nie zachował niezbędnych historii źródeł, oznaczyć `historical_quality_unverifiable`, wyłączyć te sloty z walidacji kosztów i nie raportować empirycznej dokładności. Nie imputować po cichu 0 kW.

**Regresja MTR-23:** szablon historii pokazuje 2 kW, podczas gdy historyczny stan składowej `grid_power` to `unavailable` → slot nie jest wiarygodną obserwacją `home_energy_consumption` do modelu lub backtestu, nawet gdy bieżąca moc sieci jest już poprawna.

## 6. Testy do zaimplementowania — fikcyjne serie

- `MTR-01`: migawka PV=3034 W, bateria=+19 W, sieć=−2470 W, dom=583 W → residual=0 W i **status `single_snapshot_only`**, nie `verified_independent_balance`.
- `MTR-02`: MPPT1=2387 W, MPPT2=647 W, PV_sum=3034 W → nie sumować `PV_sum + PV1 + PV2`.
- `MTR-03`: `home_energy_consumption` jest potwierdzonym template `PV + grid_signed + battery_signed` → `independent_meter=false`; wynik domu nadal jest wejściem prognozy.
- `MTR-21`: 3034 W PV, −2470 W sieć i +19 W bateria → encja domu 583 W zgodnie z definicją; brak wymogu niezależnego potwierdzenia.
- `MTR-22`: `sun12k_total_grid_power = unavailable`, template z `float(0)` nadal zwraca liczbę → Co-Pilot oznacza wynik domu jako `invalid_input` ze względu na brak składowej.
- `MTR-04`: bateria 56,69 V i 0,35 A → 19,8415 W, zgodność pomocnicza z +19 W, nie potwierdza niezależnego pomiaru.
- `MTR-05`: export: grid_signed=−2,470 kW → import=0, export=2,470 kW.
- `MTR-06`: import: grid_signed=+1,200 kW → import=1,200 kW, export=0; znak musi być oznaczony jako potwierdzony testem/historycznym odczytem.
- `MTR-07`: charge: batt_signed=−1,500 kW → charge=1,500 kW, discharge=0; kierunek potwierdzić przed użyciem operacyjnym.
- `MTR-08`: discharge: batt_signed=+0,500 kW → discharge=0,500 kW, charge=0.
- `MTR-09`: PV=5000 W, home=1000 W, bateria=−2000 W, sieć=−2000 W, idealne η=1 → residual=0; nie dodawać do PV ponownie 2000 W przepływu PV→bateria.
- `MTR-10`: noc, PV=0, home=1000 W, bateria=−1000 W, sieć=+2000 W, η=1 → residual=0, grid_charge pozostaje **ładowaniem baterii**, nie poborem domu.
- `MTR-11`: noc, PV=0, home=1000 W, bateria=+1500 W, sieć=−500 W, η=1 → residual=0, ale **eksport baterii** wymaga osobnej zgody, nawet gdy przełącznik PV export jest ON.
- `MTR-12`: moc LOAD=532 W i dom=583 W w tej samej próbce → różnica 51 W, bez automatycznej podmiany.
- `MTR-13`: kupiono dziś 4,3 kWh przy `daily_energy_bought_cost=0` → oznaczyć koszt historyczny `untrusted`, nie zastępować nim bieżącej taryfy.
- `MTR-14`: skok licznika dobowego z 9,8 na 0,1 kWh po północy → oznaczyć reset, nie ujemną energię.
- `MTR-15`: 1 kW przez 5 min, 2 kW przez 10 min → energia=0,4166667 kWh, nie suma mocy i nie dwie pełne ćwierćgodziny.
- `MTR-16`: `PV` i `grid` z pomiarów oddalonych o 20 s podczas dużej zmiany produkcji → `snapshot_not_synchronous`, bez twardego żądania residual 0.
- `MTR-17`: `last_updated` sprzed 30 min bez zmiany SOC, lecz `last_reported` aktualny → nie traktować samego SOC jako przestarzałego.
- `MTR-18`: dwie encje siatki `total_grid_power` i `out_of_grid_total_power_2` prawie równe → nie dodawać ich do jednej sumy sieci.
- `MTR-19`: ujemny wynik ceny sprzedaży i prawdziwy eksport kWh → zachować ujemny przychód, nie obcinać do 0.
- `MTR-20`: `battery_controller.*` zawiera dane pogodowe i setpoint 0 → całkowicie pominąć w źródłach planera i detekcji aktywnego konkurencyjnego sterowania.

**Warunek dla Codexa:** uznaj podany wzór i wynik encji domu za obowiązujące źródło operacyjne. Nie wymagaj dodatkowych liczników. Nie licz niezależności bilansu z tożsamości matematycznej. Kontroluj jakość istniejących wejść `PV`, `grid`, `battery` i rozdzielaj znane pomiary AC/DC bez podwójnego liczenia.


---

## HA PRICE SERIES CONTRACT


**Status: struktura danych potwierdzona przez użytkownika 20.10.2026 na pełnych atrybutach dwóch encji.** Kontrakt implementacyjny; nie wymaga pytania o sposób publikowania cen. Nie utrwala odczytanych stawek jako konfiguracji lub prognozy. Powiązania: [HA_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION.md](OPTIMIZATION.md), [VALIDATION.md](VALIDATION.md).

## 1. Źródło prawdy — wyłącznie istniejące encje HA

| Znaczenie | Encja HA | Wartość planera |
| --- | --- | --- |
| Końcowa cena zakupu **ze wszystkimi opłatami i taryfami** | `sensor.energi_data_service` | `raw_today[*].price` / `raw_tomorrow[*].price` [DKK/kWh] |
| Cena sprzedaży (bez korekt) | `sensor.energi_data_spotpris` | `raw_today[*].price` / `raw_tomorrow[*].price` [DKK/kWh] |
| Cena wykorzystywana do planowania | Bez obliczeń pomocniczych | **`C_sell = cena z sensor.energi_data_spotpris`**, bez modyfikacji; [REQUIREMENTS.md](REQUIREMENTS.md) |
| Bieżąca cena diagnostyczna | Atrybut `current_price` obu encji | Wartość o większej precyzji niż lista godzinowa; nie zastępuje pełnego szeregu |
| Publikacja jutra | `tomorrow_valid` w **każdej** encji | Akceptuj jutro dopiero, gdy źródło ją oznaczyło jako dostępną **i** lista jest poprawna |
| Kolejny termin odświeżenia źródła | `next_data_update` | Informacja diagnostyczna, **nie** pewny czas publikacji jutra ani sygnał pojawienia się nowych cen |
| Metadane | `currency`, `region_code`, `unit_of_measurement` | Oczekiwane `DKK`, `DK1`, `DKK/kWh`; błąd jednostki/regionu blokuje użycie |
| Rozkład składników ceny zakupu | `net_operator`, `tariffs` (w tym `additional_tariffs`) | Wyłącznie diagnostyka. **Nie dodawać żadnej z tych kwot po raz drugi** do `raw_*.price` |

**Nie przeliczać cen z obu encji HA. Co-Pilot nie zajmuje się prowizjami, podatkami ani taryfami.** Użytkownik potwierdził, że `sensor.energi_data_service` już publikuje ostateczną cenę. Odmienna cena zakupu i spot jest oczekiwana. `state_class: total`, `unit: kWh` i `device_class: monetary` są metadanymi encji; planner waliduje szczególnie `currency` i `unit_of_measurement`, **nie** traktuje ceny jako licznika narastającego.

## 2. Format — potwierdzony na rzeczywistym odczycie

Atrybuty obu encji:

- `today` — lista cen bez znaczników czasu. Przydatna diagnostycznie, **nieużywana jako podstawowe źródło czasu**, bo przy zmianie czasu doba może mieć 23 lub 25 godzin.
- `raw_today` — lista obiektów `{"hour":"2026-10-20T08:00:00+02:00","price":2.406}` dla ceny zakupu; analogicznie `1.922` dla spot. Pole `hour` ma strefę/offset, `price` jest liczbą w DKK/kWh.
- `tomorrow` — lista bez timestampów albo `null`, zgodnie z dostępnością.
- `raw_tomorrow` — timestampowane obiekty po publikacji albo `null` przed publikacją.
- `tomorrow_valid` — `false` przed publikacją; sam upływ godziny 13:00 nie zastępuje tej flagi.
- `next_data_update` — przykład: zakup `13:25:40`, spot `13:28:03`; **oddzielny** czas następnego odświeżenia, może się różnić.
- `today_min/max/mean`, `tomorrow_min/max/mean` i `today_remaining_*` — wskaźniki informacyjne; **nie** budować szeregu na podstawie wartości średnich lub minimalnych.

**Snapshot 20.10.2026, przed cenami jutrzejszymi:** obie encje miały po **24** pozycji w `raw_today` (00:00–23:00, offset +02:00); obie miały `tomorrow_valid: false`, `tomorrow: null` i `raw_tomorrow: null`. To pełna dostępna seria na dziś i **normalny** brak serii na jutro. **Ściśle:** rekordy `raw_today` i istnienie klucza `raw_tomorrow` są potwierdzone; zawartości niepustego `raw_tomorrow` jeszcze nie obserwowano. Parser projektowo oczekuje identycznego schematu `hour`/`price` i sam zweryfikuje pierwszą opublikowaną listę — bez dodatkowego pytania do użytkownika i bez fikcyjnych cen.

Wybrane potwierdzone pary godzinowe (ilustracyjne **migawki danych z 20.10**, nie stałe programu):

| Czas lokalny | Cena zakupu z HA DKK/kWh | Cena sprzedaży z HA DKK/kWh | Cena sprzedaży w plannerze DKK/kWh |
| --- | ---: | ---: | ---: |
| 08:00 | 2.406 | 1.922 | 1.922 |
| 13:00 | 1.838 | 1.355 | 1.355 |
| 18:00 | 3.151 | 2.008 | 2.008 |

W tej samej migawce `current_price` miał precyzyjniejsze wartości: zakup `2.405502871680312`, spot `1.9222991216803123`; różnica do `raw_today[08:00]` wynika z **zaokrąglenia** cen w liście do trzech miejsc. Przy przetwarzaniu planu używać jednej, jawnie opisanej podstawy (`raw_*`) dla **wszystkich godzin**, bez ukrytego mieszania precyzji. Bieżące `current_price` służy do kontroli spójności i wyświetlania.

## 3. Kontrakt parsera i normalizacji

Wejście: **dwa** bieżące stany HA oraz ich atrybuty. Parser jest deterministyczny i nie korzysta z internetu, bezpośredniego Modbus ani własnego klienta API.

1. Dla każdej encji sprawdź jej dostępność, `currency = "DKK"`, `region_code = "DK1"`, `unit_of_measurement = "DKK/kWh"` oraz istnienie `raw_today`.
2. Każdy rekord parsuj z `hour` do świadomego offsetu timestampu, następnie przekonwertuj do UTC. `price` musi być skończoną liczbą; **nie** odrzucać cen zerowych lub ujemnych. Nie używać indeksów `today` jako identyfikatora godziny.
3. Nadaj godzinowemu rekordowi `start_utc` i `end_utc = start_utc + 1h` (prawy koniec wyłączny). Posortuj po UTC, sprawdź unikalność, kolejność, brak luk lub nakładania w okresie przeznaczonym do planu. Godzina powtórzona lokalnie podczas jesiennej zmiany czasu to **dwa różne** przedziały UTC.
4. Dodaj `raw_tomorrow` tylko, jeśli `tomorrow_valid === true` **dla tej encji**, `raw_tomorrow` jest listą z poprawnymi rekordami daty kolejnej doby lokalnej i jest spójna czasowo z końcem dziś. W przeciwnym razie nie bierz jutra, bez dosztukowywania listy ani interpolowania.
5. Znormalizuj oba źródła do `start_utc/end_utc`. **Dla ceny eksportu potrzebny jest rekord spot; dla importu rekord zakupu w tym samym przedziale.** Horyzont pełnej optymalizacji dwukierunkowej ogranicza **wspólny ciągły fragment** obu źródeł od bieżącej chwili. Źródła mogą opublikować jutro o różnych minutach; ich zakresów nie wolno bezrefleksyjnie utożsamiać.
6. Każda cena godzinowa obowiązuje w swoich czterech kwadransach planu 15-minutowego (z uwzględnieniem częściowo rozpoczętego pierwszego slotu). **Nie tworzyć sztucznych nowych cen** po końcu ostatniego kompletnego opublikowanego przedziału.
7. Gdy `tomorrow_valid` zmienia się z `false` na `true` i dochodzi poprawny wspólny szereg, opublikuj nową wersję danych i przelicz plan. Zmiana treści `raw_*` bez zmiany flagi też wymaga odświeżenia planu; śledzić faktyczną wersję listy/timestamp, nie samą godzinę `next_data_update`.
8. Przy `unknown/unavailable`, niekompletnym źródle, DST lub luce danych ogranicz plan do spójnego znanego fragmentu albo jawnie `blocked/partial`; nie zastępować brakującej ceny kupna spot ani odwrotnie.
9. Pojedyncze wartości diagnostyczne `current_price` porównać z rekordem dla aktywnej godziny (tolerancja odpowiada udokumentowanemu zaokrągleniu, np. `0.001 DKK/kWh`). Znaczna rozbieżność: diagnostyka; nie nadpisywać całej przyszłej serii.
10. Wynik mappera dla każdej godziny: `{start_utc,end_utc,buy_dkk_kwh,spot_dkk_kwh,sell_net_dkk_kwh,source_buy,source_spot,obtained_at_utc}`; godzina z danymi tylko z jednego źródła ma oddzielny status brakującego składnika.

`next_data_update` jest **czasem bez daty**, dlatego nie interpretować go jako dowodu publikacji ani jako znacznika czasu każdej ceny. Śledzić nową zawartość encji i flagi. Przy zmianie czasu i lokalnym dniu 23/25 h obliczenia i deduplikacja odbywają się **wyłącznie w UTC**, prezentacja w `Europe/Copenhagen`.

### Granica progu 0,40 przy różnych precyzjach

W zaobserwowanych danych `raw_today[*].price` jest zaokrąglone do trzech miejsc po przecinku, a `current_price` może mieć większą precyzję. Nie wolno **zakładać**, że porównanie `raw_*.price >= 0.400` odpowiada porównaniu niezaokrąglonej ceny przy granicy 0,40. W planowaniu pozostaje jednolite źródło `raw_*`. W bieżącym sterowaniu eksportem PV:
- jeśli `current_price` jest aktualny, zgodny z aktywnym slotem i jego porównanie z 0,40 **różni się** od wyniku `raw_*.price`, oznacz `PRICE_THRESHOLD_AMBIGUOUS`, **nie wydawaj komendy ON** i nie raportuj pewnego spełnienia progu;
- jeśli nie można ustalić precyzji/świeżości obu pól, status porównania oznacz jako niezweryfikowany; nie maskuj zaokrąglenia arbitralną tolerancją;
- wartość 0,400 dokładnie w źródle **bez konfliktu** nadal oznacza próg włączny, zgodnie z polityką użytkownika.

**Regresja PRICE-19:** `raw_today.price=0.400`, `current_price=0.3996` dla tej samej bieżącej godziny → brak automatycznej komendy ON, `PRICE_THRESHOLD_AMBIGUOUS`. Dla `0.400` i `0.4000` → próg włączny.

## 4. Reguła ekonomiczna

`C_buy[t] = buy_raw_price[t]` (wszystkie opłaty już zawarte).

`C_sell[t] = spot_raw_price[t]` (**dokładnie wartość z encji HA**, bez przeliczeń). Próg samodzielnego eksportu PV: `C_sell[t] >= 0.40 DKK/kWh` według [REQUIREMENTS.md](REQUIREMENTS.md).

Nawet jeśli `C_sell[t]` jest ujemna, zachować jej znak. Rachunek za zakup, przychód ze sprzedaży i koszt degradacji pozostają odrębnymi pozycjami funkcji celu. Nie przeliczać samych danych z atrybutu `tariffs` na drugą dopłatę.

Przykład **chwilowy** z atrybutów `current_price` (nie z serii zaokrąglonej): zakup `2.405502871680312 DKK/kWh`, sprzedaż **bezpośrednio z HA** `1.9222991216803123 DKK/kWh`. Obie wartości przechodzą do planera bez korekt. Próg eksportu `0,40` porównujemy **bezpośrednio** z wartością sprzedaży w HA.

## 5. Scenariusze testowe mappera (symulacja, nie uruchomione)

- `PRICE-01`: `raw_today` z 24 godzinami, `raw_tomorrow = null`, `tomorrow_valid = false` → 24 godziny cen dla danej doby; brak jutra nie jest błędem.
- `PRICE-02`: godzina 08:00 20.10, zakup 2,406, sprzedaż z HA 1,922 → `C_sell = 1,922 DKK/kWh` z serii, bez modyfikacji.
- `PRICE-03`: `current_price` 2,405502871680312 i 1,9222991216803123 vs seria 2,406 i 1,922 → kontrola spójności PASS w granicy precyzji listy, brak fikcyjnej korekty szeregu.
- `PRICE-04`: zakup ma `tomorrow_valid=true`, spot jeszcze `false` → brak kompletnego wspólnego planu transakcji na jutro.
- `PRICE-05`: obie flagi `true`, ale jedna lista `raw_tomorrow` jest `null` → jutro nie jest gotowe do planowania.
- `PRICE-06`: godzina 13:00 po nadejściu poprawnych danych jutra → plan przedłuża się tylko do końca **rzeczywiście** dostępnych cen, bez wpisywania 48h.
- `PRICE-07`: `next_data_update` zakupu 13:25:40 i spot 13:28:03, flagi `false` → czas nie jest dowodem nowych cen.
- `PRICE-08`: w czasie DST lokalna doba 23/25 h → parser akceptuje poprawne 23/25 rekordów, nie narzuca 24.
- `PRICE-09`: dwie lokalne godziny 02:00 przy jesiennej zmianie czasu, różne offsety → pozostają **dwoma** poprawnymi slotami UTC.
- `PRICE-10`: brak godziny wewnątrz `raw_today` → oznaczenie luki, bez imputacji i arbitrażu na nieznanej cenie.
- `PRICE-11`: cena sprzedaży z HA −0,10 → `C_sell = −0,10 DKK/kWh`; zachować bez modyfikacji.
- `PRICE-12`: niepoprawna waluta, region, jednostka, timestamp bez offsetu lub `price=NaN` → odrzucenie danych z kodem przyczyny.
- `PRICE-13`: po przejściu z 23:59 na 00:00 aktualizuje się horyzont przy użyciu odpowiadających nowemu dniu list HA, bez zachowania przestarzałego `raw_today` jako przyszłej ceny.
- `PRICE-14`: wśród atrybutów zakupu są `tariffs` i `additional_tariffs` → wynik ceny wciąż równy `raw_*.price`, brak podwójnego naliczenia.
- `PRICE-15`: tablica `today` długości 25 podczas jesiennego DST → mapper nie identyfikuje godziny indeksami pozycji, tylko `raw_today[*].hour`.
- `PRICE-16`: listy kupna i spot różnią się momentem aktualizacji; nowe dane z jednej encji, stara druga → nowy plan tylko dla zweryfikowanego wspólnego horyzontu.
- `PRICE-17`: zmiana cen dziś w `raw_today` bez zmiany flagi jutra → nowa wersja cen i replan, mimo `tomorrow_valid=false`.
- `PRICE-18`: kwadrans 08:15–08:30 otrzymuje tę samą opublikowaną stawkę co przedział 08:00–09:00; indeksacja po UTC, bez interpolacji.

**Odbiór:** testy `PRICE` stanowią kontrakt do zaimplementowania przez Codexa, a nie zatwierdzenie działającego kodu. Format publikacji jest **ustalony** i nie powinien pozostawać zadaniem „dopiero ustalić z użytkownikiem”.


---

## PV FORECAST CONTRACT


**Status:** oficjalny kontrakt usługi HA zweryfikowany w dokumentacji. **Użytkownik potwierdził obecność akcji w swojej liście HA, lecz nie przetestowano odpowiedzi ani wyboru config_entry.** M2 sprawdza odpowiedź lokalnie; nie żąda ręcznego przepisywania atrybutów.

**Źródła:** [oficjalna akcja Forecast.Solar: Get forecast](https://www.home-assistant.io/actions/forecast_solar.get_forecast/); [oficjalna integracja Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/).

## 1. Źródło pełnego profilu

**Preferowana droga (warunkowa):** `forecast_solar.get_forecast` to **akcja/usługa Home Assistant, NIE encja** — szuka się jej w **Narzędzia deweloperskie → Akcje**, nie w Stanach. Jest opisana oficjalnie i użytkownik potwierdził jej widoczność w swojej instancji, ale faktycznej odpowiedzi nadal nie sprawdzono. Zanim Codex oprze na niej prognozę, musi sprawdzić obecność akcji w aktualnej instalacji i w razie braku przewidzieć inne zweryfikowane źródło. Akcja zwraca dane w odpowiedzi (response data). Co-Pilot pobiera ją przez **wewnętrzne API usług HA**, bez połączenia do zewnętrznego Forecast.Solar, bez osobnego klienta HTTP i bez modyfikowania integracji Forecast.Solar.

| Element | Znaczenie |
| --- | --- |
| Akcja HA | `forecast_solar.get_forecast` |
| Parametr wymagany | `config_entry`: wybrany wpis konfiguracji Forecast.Solar, **nie** identyfikator sensora |
| `resolution: raw` | Natywna rozdzielczość: 15 minut (jeżeli dostawca udostępnia) albo 1 godzina (np. plan bezpłatny) |
| `resolution: hourly` | Agregacja do pełnych godzin |
| `start` / `end` | Opcjonalny zakres żądanych danych, koniec wyłączny |
| `watts` | Mapa `ISO timestamp z offsetem → prognozowana moc W`; przy `hourly`: średnia moc godzinowa |
| `wh_period` | Mapa `ISO timestamp z offsetem → prognozowana energia Wh w okresie`; przy `hourly`: energia całej godziny |

Oficjalny format odpowiedzi jest następujący (wyłącznie **przykład schematu**, nie dane instalacji):

```yaml
watts:
  "2026-09-30T08:00:00+02:00": 412
  "2026-09-30T09:00:00+02:00": 1350
wh_period:
  "2026-09-30T08:00:00+02:00": 395
  "2026-09-30T09:00:00+02:00": 1312
```

**Kluczowa zaleta:** HA zwraca **swoją już pobraną prognozę**, a nie odpytuje serwisu Forecast.Solar przy każdym wywołaniu akcji. Nie generujemy sztucznie większej rozdzielczości prognozy przez częstsze odpytywanie. Prognozy co do zasady nie są pomiarami i nie muszą zgadzać się w 100% z uzyskiem.

## 2. Wybór wpisu i kontrola dostępności

Codex musi:
1. Przy M2 potwierdzić działanie akcji `forecast_solar.get_forecast` (jej obecność w UI została potwierdzona przez użytkownika), konfigurację, format odpowiedzi i pokrycie przedziałów. Nie zakładać, że sama obecność akcji oznacza poprawne dane.
2. Przez HA wykryć dostępne wpisy `forecast_solar`; gdy jest jeden, użyć go; gdy więcej niż jeden, pozwolić użytkownikowi wybrać wpis w config/options flow. **Nie hardkodować** `config_entry`, ID sensora, lokalizacji, tokenu ani instalacji.
3. Pobierać wynik jako **response data**, nie stan nowej encji i nie zakładać, że profil jest w atrybutach `sensor.energy_production_today`.
4. Wykazać w diagnostyce: `forecast_source = forecast_solar.get_forecast`, wybrany wpis, rozdzielczość, liczbę okresów, pierwszy/ostatni okres, czas uzyskania, ostatnio zarejestrowaną wersję prognozy i ewentualny błąd.
5. Jeżeli akcja **nie istnieje**, zastosować `pv_hourly_forecast = unavailable` i jawny `missing_capabilities`. **Nie** tworzyć profilu godzinowego z samej sumy dziennej ani wymyślać krzywej produkcji. Możliwy osobny wariant mapowania rzeczywiście potwierdzonych atrybutów innych encji, ale nie jest warunkiem specyfikacji bazowej.
6. Przy czasowej awarii usługi można prezentować archiwalną prognozę z oznaczeniem wieku, ale nie wolno podawać jej jako świeżej prognozy do automatycznych decyzji. Starzenie i ważność mają być jawne i testowane.

**Brak twardo zakodowanego interwału publikacji:** według dokumentacji integracja bezpłatna zwykle aktualizuje dane co godzinę, z kluczem API około co 30 minut; dostępność nowych danych w HA trzeba wykrywać na podstawie wersji i momentu uzyskania, a nie deklarować każdą decyzję 15-minutową jako nową prognozę.

## 3. Jednostki, okresy, UTC i energia

- Pierwotną, zachowującą bilans podstawą jest **`wh_period`**, czyli energia [Wh] danego okresu. `watts` to prognozowana moc [W] i przy `raw` nie musi równać się średniej energii w danym odcinku — nie zastępować `wh_period` przez `watts × czas` bez potwierdzenia interpretacji.
- Klucz `timestamp` oznacza **początek okresu** i ma offset strefowy. Parsować do UTC i dopiero łączyć z cenami. Zachować dobowy przełom i DST (23/25 godzin).
- Okres w `raw` może mieć 15 albo 60 minut: rozpoznawać po kolejnych początkach okresów / trybie źródła; ostatni interwał musi mieć znaną długość zgodną z udokumentowaną rozdzielczością. Nie zakładać arbitralnie 1h dla każdej instalacji.
- Na okres `[HA_CONTRACT.md](HA_CONTRACT.md).

## 4. Powiązanie z instalacją i bilansem

Potwierdzone encje odczytowe:
- `sensor.energy_production_today` — prognozowana produkcja dziś, **15,865 kWh** w migawce z 19.10.2026.
- `sensor.energy_production_today_remaining` — prognoza pozostała dziś, **4,431 kWh**.
- `sensor.energy_production_tomorrow` — prognoza jutro, **7,536 kWh**.
- `sensor.pv_sum` — bieżący agregat MPPT: **3034 W** = `sensor.sun12k_pv1_power` + `sensor.sun12k_pv2_power` w tej samej migawce.
- `sensor.pv_forecast_next_24h` = **51,72 bez jednostki**: **nie** używać jako energii, mocy ani zastępczego źródła prognozy, dopóki semantyka nie jest udokumentowana.
- Encje `battery_controller.*` to osierocone pozostałości, ignorowane jako wejścia i sterowania.

Dla celu optymalizatora forecast.solar jest prognozą **potencjalnej produkcji**, a `sensor.pv_sum` obserwacją rzeczywistej mocy PV (punkt DC/AC wymaga jawnego zmapowania). Nie odejmować od `wh_period` automatycznie ładowania baterii, jeśli prognoza już opisuje całość uzysku. Model DC/AC i parametry Forecast.Solar (moc szczytowa, płaszczyzny, tłumienie, ograniczenie przez falownik) potrzebują kalibracji na danych **bez curtailment**.

## 5. Historia prognoz i ocena jakości

- Utrwalać **migawkę odpowiedzi** `wh_period` pobranej **przed** prognozowanym okresem; `obtained_at` i wersja danych muszą rozróżniać zmiany. Nie nadpisywać starych prognoz.
- Tylko taka migawka umożliwia prawidłowe testy `walk-forward` bez później poznanej pogody. W ramach jednego slotu zachować jakość prognozy i horyzont wyprzedzenia.
- Potencjalnego PV **nie da się dokładnie odtworzyć** z produkcji ograniczonej przez sterowanie. Przedziały `curtailed_confirmed` lub `curtailment_unknown` wyłączyć z kalibracji dokładności (nie twierdzić, że „prognoza się nie zgadza”, jeśli PV ograniczono).
- 100% zgodności z uzyskiem nie jest wymagane; ma znaczenie **wpływ rozkładu błędów prognozy na decyzje ekonomiczne**. Przed kalibracją używać jawnie oznaczonej prognozy punktowej i testów wrażliwości, bez wymyślonego „90% zaufania”.
- Aktualne `sensor.energy_production_today` i dawne `sensor.sun12k_daily_production` pokazujące inne wartości **nie** są dowodem awarii prognozy ani błędnego sterowania.

## 6. Testy kontraktu — do zaimplementowania przez Codexa (nie wykonano)

- `PVF-01`: akcja `forecast_solar.get_forecast` dostępna, jeden config entry → poprawny wybór i mapowanie.
- `PVF-02`: dwa wpisy Forecast.Solar → wymagany jawny wybór, brak nieprzewidzianego podwójnego zsumowania.
- `PVF-03`: akcja niedostępna → `missing_capabilities`, brak wymyślonej prognozy godzinowej.
- `PVF-04`: `watts` i `wh_period` pokazują różne wartości zgodnie ze swoją definicją → podstawą bilansu jest `wh_period`, bez podwójnego mnożenia przez 1h.
- `PVF-05`: 1000 Wh w godzinie → cztery kwadranse po 250 Wh **z oznaczeniem aproksymacji**; suma dokładnie 1000 Wh.
- `PVF-06`: 250 Wh w autentycznym okresie 15 min → 250 Wh przypisane temu slotowi, nie podzielone ponownie.
- `PVF-07`: brakuje okresu pośród mapy → luka jawna i ograniczona wykonalność; bez interpolowania dobowej sumy.
- `PVF-08`: powtórzona lokalnie godzina 02:00 w DST jesienią, różne offsety → różne interwały UTC.
- `PVF-09`: `issued_at` nie jest dostępny w odpowiedzi → pole `not_provided`, bez sfabrykowania czasu publikacji.
- `PVF-10`: na kolejny cykl HA zwraca tę samą prognozę → nie tworzyć fałszywej nowej wersji ani nie twierdzić, że wzrosła precyzja forecastu.
- `PVF-11`: awaria akcji → dane przestarzałe jawnie oznaczone; brak automatycznej decyzji opartej na nieznanym profilu PV.
- `PVF-12`: pomiar PV został sztucznie ograniczony przez pełną baterię i eksport OFF → nie poprawiać modelu według różnicy „prognoza − produkcja”.
- `PVF-13`: profil PV sięga dalej niż znane ceny → plan wyceniany tylko na horyzoncie opublikowanych cen.
- `PVF-14`: bieżący kwadrans 10:30–10:45, prognoza godzinna 10:00–11:00 → nie traktować energii minionych 30 min jako przyszłej.
- `PVF-15`: brak jednostki na `sensor.pv_forecast_next_24h` → nie używać jako kWh.
- `PVF-16`: prognoza godzinowa suma dziś różna od sensora `energy_production_today` z powodu chwili pobrania / innej agregacji → zgłosić diagnostykę rozbieżności, nie odrzucać automatycznie całej prognozy.
- `PVF-17`: user confirmed precise inverter current limit, prognoza PV za niska → różnica to błąd prognozy wejściowej, nie sztuczny błąd sterowania Deye.
- `PVF-18`: brak `wh_period` albo uszkodzone timestampy → status danych `invalid`, nie wyprowadzać fałszywego godzinowego profilu z `watts`.

**Warunek odbioru:** Codex potrafi pobrać profil jako natywną odpowiedź HA, udokumentować jakość i źródło oraz oznaczyć brak akcji bez zgadywania. Do startu implementacji modułu prognoz nie jest potrzebne ręczne kopiowanie atrybutów dwóch encji cen ani sensorów dziennych Forecast.Solar.
