# Current-first: model nastaw, harmonogramu i wykonalności

**Status:** normatywny algorytm translacji intencji ekonomicznej na istniejące **encje Home Assistant**. Brak dostępu do Modbus i brak modyfikacji ESPHome. Wszystkie testy w tym dokumencie są **fiksturami symulacji**, nie testami wykonanymi na falowniku.
Powiązania: [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md), [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md), [DECISION_LOGGING.md](DECISION_LOGGING.md).

## 1. Zamknięte założenia

- Użytkownik potwierdza, że Deye **precyzyjnie i deterministycznie respektuje przyjęty limit prądu**. Nie dodawać losowego „błędu wysterowania falownika”.
- Nastawa maksimum nie wymusza przepływu, jeśli źródło energii, SOC, BMS, napięcie lub tryb urządzenia ograniczają pracę. To **ograniczenie fizyczne**, nie błąd falownika.
- Sterowanie ograniczeniami odbywa się przez trzy istniejące encje HA:
  - `number.sun12k_maximum_battery_charge_current`: ogólny limit ładowania baterii, **0–50 A**, wpływa także na PV;
  - `number.sun12k_maximum_battery_discharge_current`: limit rozładowania, **0–100 A**;
  - `number.sun12k_maximum_battery_grid_charge_current`: dodatkowy limit ładowania z sieci, **0–50 A**.
- Projektowo zakładamy poprawną semantykę nazw; nie wracać do adresów rejestrów. Numer rejestru **nie jest** wejściem, poleceniem ani ustawieniem Co-Pilot.
- Sterowanie bezpośrednio przez HA trwa tylko, gdy HA jest dostępny. **Wszystkie nastawy pozostają w falowniku po utracie HA**; TOU powtarza swój 6-okienkowy profil każdego dnia.
- SOC okresu TOU **nie** ogranicza ładowania z PV: ogranicza głównie rozładowanie, a przy Grid Charge jest także celem ładowania z sieci.
- Eksport baterii obecnie wyłączony; brak ważnej zgody na konkretny plan = brak celowego eksportu baterii.
- Co-Pilot używa ceny zakupu **wprost** z `sensor.energi_data_service` oraz ceny sprzedaży **wprost** z `sensor.energi_data_spotpris`, bez liczenia prowizji i taryf. Eksport PV przy cenie z HA co najmniej 0,40 DKK/kWh; [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md).

## 2. Co planujemy, a co rzeczywiście ustawiamy

Planner pracuje na slotach UTC, domyślnie `Δt = 0,25 h`, i maksymalizuje korzyść netto/minimalizuje koszt aż do ostatniego opublikowanego slotu ceny. Daje intencję energetyczną `P_bat_charge_target_dc_kw` / `P_bat_discharge_target_dc_kw` wraz z SOC, źródłem, kierunkiem i uzasadnieniem; nie „gotowy prąd” bez warunków urządzenia.

**Translator** buduje plan nastaw HA z osobno zapisanymi:
- `I_charge_cap_A`, `I_discharge_cap_A`, `I_grid_charge_cap_A` (obowiązkowo jednostka A, legalny zakres i stan aktywnej konfiguracji);
- `target_flow_dc_kw` (założona fizyczna moc przy rzeczywistym napięciu i dostępności energii);
- `capability_status` (czy intencja jest osiągalna przy bieżącym TOU i przełącznikach);
- `expected_effect` / `observed_effect` (bez mylenia propozycji i potwierdzenia działania);
- `persistent_after_ha_loss`, `expected_recovery_action` oraz `blocked_reason`.

**Niezmiennik:** nie twierdzić, że Co-Pilot potrafi osiągnąć dowolny profil SOC wyłącznie przez zmianę trzech limitów prądu. Limit rozładowania nie jest poleceniem eksportu ani minimalnym SOC. TOU nadal może ograniczyć realizację celu; niemożliwe warianty mają `not_executable`, a nie zastępczy zmyślony zapis.

## 3. Dokładne przeliczenie prądu na moc baterii

Dla `V_bat(t)` [V] i prądu [A], na zaciskach DC magazynu:

`P_cap_dc_kw(t) = V_bat(t) × I_cap_A(t) / 1000`.

Nie wstawiać na stałe 51,2 V lub 56 V; używać aktualnego napięcia z `sensor.sun12k_battery_voltage`, po kontroli jakości i czasu pomiaru. Przy 56 V:
- `5 A → 0,280 kW DC`;
- `50 A → 2,800 kW DC`;
- `100 A → 5,600 kW DC`.

**To maksima prądowe, nie gwarantowane moce**. Jeśli użytkownik zadeklarował także limit zdolności ładowania 2,5 kW i rozładowania 5 kW, plan musi dotrzymać **obu** ograniczeń, chyba że późniejsze pomiary potwierdzą zmianę odpowiedniego limitu. Nie zakładać, że ten sam limit mocy jest po tej samej stronie AC/DC co zaciski baterii — wymagane jawne dopasowanie.

**Gdy planner podaje moc po stronie zacisków baterii**, matematyczny kandydat limitu wynosi:

`I_raw = 1000 × P_target_bat_dc_kw / V_bat_V`.

Następnie wybrać **legalną nastawę** z dostępnego, udokumentowanego kroku encji oraz indywidualnego zakresu 0–50/0–100/0–50 A. Dla rzeczywiście wymaganej *górnej* granicy mocy **nie zaokrąglać w górę**, bo przekroczyłoby planowy maksymalny przepływ. Jeśli odchylenie po kwantyzacji jest istotne, planner musi ponownie wycenić plan przy dostępnych wartościach nastaw. **Nie przycinać po cichu** nielegalnej prośby do granicy; błąd planera to osobny `CURRENT_LIMIT_OUT_OF_RANGE`.

**Wartość 0 A:** użytkownik 20.10.2026 potwierdził działanie zadawanych nastaw w falowniku. Przyjąć 0 A jako dopuszczalną wartość graniczną polityki, bez ponownego pytania o zasadę regulacji. Przy integracji HA nadal potwierdzić rzeczywisty odczyt/efekt i nie utożsamiać limitu prądu z wymuszeniem konkretnego przepływu.

`I_grid_effective_limit_A = min(I_charge_cap_A, I_grid_charge_cap_A, I_BMS_charge_limit_A)` — **tylko kiedy ładowanie z sieci jest zezwolone przez faktycznie aktywne tryby**. Dodatkowe ograniczenie mocy lub napięcia również obowiązuje. Samo ustawienie `I_grid_charge_cap_A` nie uruchamia grid charge.

## 4. Jak modelować PV, dom, baterię i eksport przy ograniczeniu prądu

**Syntetyczna, uproszczona fikstura DC/AC** (wyłącznie dla testów; `η = 1`, brak strat i równoczesnego grid charge, brak eksportu baterii, PV najpierw pokrywa dom):

- `P_surplus_PV = max(0, P_PV − P_house)`;
- `P_charge_possible = min(P_surplus_PV, V_bat·I_charge_cap/1000, P_BMS, P_charger_hardware, P_SOC_headroom)`;
- `P_PV_export = P_surplus_PV − P_charge_possible`, **wyłącznie** jeśli włączony i bezpieczny eksport samego PV; w przeciwnym razie pozostała energia może podlegać ograniczaniu PV.

**To nie jest ogólny wzór topologii falownika:** w produkcyjnym modelu uwzględnić `η_pv_ac`, `η_pv_bat`, pomiar `sensor.pv_sum` DC, definicję `sensor.home_energy_consumption` AC, własne tory DC↔AC i BMS. Nie sumować dwa razy energii PV DC skierowanej do magazynu.

### Przykład 1 — dwa limity, ten sam dostępny nadmiar PV

Przyjmij `V_bat = 56 V`, `PV = 3,0 kW`, `dom = 0,5 kW`, bateria niepełna, eksport PV do sieci włączony i fizycznie odseparowany od eksportu baterii, zdolność ładowania ≤ 2,5 kW.

| Nastawa HA | Ładowanie baterii | Eksport PV |
| --- | ---: | ---: |
| `I_charge_cap = 5 A` | `0,28 kW` | `2,22 kW` |
| `I_charge_cap = 50 A` | `2,50 kW` | `0,00 kW` |

Jeśli `PV = 0,1 kW` i `dom = 0`, przy nastawie 5 A ładowanie wyniesie **0,1 kW**, nie 0,28 kW. Falownik zachowuje dokładnie limit, ale fizycznie nie ma więcej PV.

### Przykład 2 — ekonomia opóźnionego ładowania

Dwa osobne okresy godziny po 1 h, w każdym dostępne `2,5 kWh` nadwyżki PV, bateria ma miejsce. Sprzedaż rano `0,80 DKK/kWh`, po południu `0,50 DKK/kWh`; potrzeba **2,5 kWh** w baterii na noc. Test z `η = 1` i zerową degradacją izoluje tylko alokację w czasie.

- **Wariant matematycznie idealny:** rano `0 A` i eksport `2,5 kWh`, popołudniu `2,5 kWh` do magazynu → przychód **2,00 DKK**.
- **Użytkowy wariant z rano 5 A:** rano magazyn `0,28 kWh` i eksport `2,22 kWh`, po południu magazyn `2,22 kWh` i eksport `0,28 kWh` → przychód **1,916 DKK**.
- **Wariant odwrotny:** rano magazyn `2,5 kWh`, po południu eksport `2,5 kWh` → przychód **1,25 DKK**.

**Warunek porównywalności:** wszystkie trzy warianty kończą z **identycznym SOC**, zawierają tę samą energię nocną i nie eksportują baterii. Dla niezerowych strat, degradacji i realnej topologii wynik musi zostać policzony ponownie. Fizyczna obsługa 0 A została zadeklarowana przez użytkownika. Trzy warianty ilustrują plan przy założeniu identycznego końcowego SOC, lecz przykład nie dowodzi globalnego optimum ani zgodności z wszystkimi trybami TOU.

## 5. Reguła decyzji w każdym slocie

1. Zbierz opublikowane ceny zakupu i sprzedaży, prognozy PV/zużycia, SOC, napięcie, moce i aktywny okres TOU. Źródła i ich aktualność zgodnie z [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md).
2. Zbuduj **zbiór dostępnych nastaw** z granic polityki Co-Pilot i rzeczywiście potwierdzonego kroku encji. Nie używać absurdalnych metadanych HA jako fizycznych granic.
3. Policz dla każdego wykonalnego limitu prognozowany rozdział PV→dom/bateria/eksport/ograniczenie i przyszły SOC. Ładowanie z sieci wolno modelować tylko, gdy rzeczywiście jest aktywna pełna ścieżka zezwolenia (`switch.sun12k_grid_charge` + TOU, jeśli wymagane).
4. Minimalizuj **koszt netto całego znanego horyzontu**, nie koszt najbliższego kwadransa; uwzględnij wartość końcowego SOC, marginesy fizyczne, niepewność PV/popytu i marginalny koszt degradacji. Nie ustawiaj stałego progu 5 A, 50 A ani arbitralnego ceny/soc.
5. Wybierz **pierwszą** nastawę wybranego planu, z ograniczeniem zbędnych zmian oraz uwzględnieniem **trwałości nastawy przy utracie HA**. Nie przepisywać pozostałej trajektorii jako 96 poleceń bez walidacji.
6. Publikuj `candidate_current_A`, `expected_flow_kw`, `expected_cost_dkk`, `alternative_cost_dkk`, powód i ograniczenia. To ma działać od pierwszego `dry_run`.
7. Przy przyszłym executorze po spełnieniu P0: przed wysłaniem każdej usługi HA sprawdź aktualny plan, prąd i napięcie, legalność nastawy, fizyczne ograniczenia, zgodę i warunki czasowe; **nie wysyłaj** gdy jest blokada.
8. Weryfikuj efekt względem **maksimum prądu** i fizycznie możliwej energii. Nie wymagaj dokładnego osiągnięcia limitu przy braku nadwyżki PV, pełnej baterii lub działania BMS. Nie wymyślaj losowego błędu wykonania nastawy.
9. Jeżeli plan i rzeczywistość różnią się z powodu zmiany pogody lub obciążenia — nowy **replan**; jeśli nie działa sama nastawa mimo fizycznie możliwych warunków — diagnostyka `ACTUATION_MISMATCH`.

## 6. Sterowanie rozładowaniem, SOC i siecią: oddzielne zdolności

| Intencja | Dostępna encja | Czy wystarcza sama? |
| --- | --- | --- |
| Zmniejszyć przyjmowanie energii PV przy wysokiej cenie sprzedaży | `number.sun12k_maximum_battery_charge_current` | Tak **jako limit**, jeżeli PV może trafić do sieci, SOC/BMS i topologia pozwalają |
| Zwiększyć możliwość przyjmowania energii PV przy niższej cenie sprzedaży | Ta sama encja, do 50 A | Tak **jako limit**; fizyczna dostępność PV nadal ogranicza przepływ |
| Ograniczyć tempo rozładowania | `number.sun12k_maximum_battery_discharge_current` | Tak jako maksymalny prąd, nie żądana moc |
| Gwarantować **dynamiczne** minimalne SOC | TOU/SOC lub osobny zweryfikowany mechanizm | **Nie** samym limitem prądu; bez dostępnej zdolności `not_executable` |
| Ładować z sieci | `number.sun12k_maximum_battery_grid_charge_current` **i** ogólny limit oraz `switch.sun12k_grid_charge` i warunki aktywnego TOU | **Nie** samym limitem sieci |
| Wymusić eksport z baterii | Nie ma osobnego potwierdzonego sterowania | **Nie**, potrzebna odrębna funkcja + zgoda na plan |
| Zrealizować 15-minutową zmianę SOC lub mocy przez 6 TOU | Opcjonalny backend TOU | Nie gwarantować 96 swobodnych nastaw; nie zmieniać TOU w bazowym wariancie |

**Istotne ograniczenie current-first:** jeżeli plan wymaga wymuszenia ładowania z sieci do danego SOC w konkretnej godzinie albo ochrony SOC niezależnej od HA, obecny backend nie powinien udawać posiadania tych możliwości. Wtedy dokumentować `missing_capabilities` i równolegle rozważyć *bezpieczną* obsługę istniejącego TOU.

## 7. Utrata HA i trwałe nastawy

Zarówno zdalne, jak i ręczne nastawy Deye pozostają aktywne w falowniku. **Nie zakładać automatycznego powrotu po 15 minutach**. Każdy kandydat ma dwie oceny:

- **Bezpieczeństwo fizyczne bez HA:** limit prądu nie przekracza polityki oraz istniejących zabezpieczeń BMS/falownika, a stan pozostaje akceptowalny przez czas nieokreślony, albo funkcja jest blokowana do uzyskania niezależnego kończenia.
- **Ryzyko ekonomiczne bez HA:** pozostawiony limit 5 A może ograniczać przyszłe magazynowanie PV; utrzymanie ładowania z sieci może kosztować energię po zmianie ceny. To nie są te same klasy konsekwencji.

Dla eksportu baterii ograniczonego indywidualną zgodą w kWh/czasie przyszły `turn_off` w HA **nie** zapewnia egzekucji granicy po awarii: potrzebny niezależny mechanizm zakończenia. Dla `grid_charge` użytkownik 20.10.2026 **zaakceptował pozostanie ostatnich nastaw po awarii HA i ryzyko ekonomiczne**; wystarczają niezależne zabezpieczenia fizyczne falownika/BMS i zgodność z twardą granicą SOC 20%. Po odzyskaniu HA odczytać stan i przeliczyć plan.

Po restarcie: najpierw odczytać **aktualne** nastawy i stany, zbudować nowy plan; nie odtwarzać poprzedniej komendy wyłącznie z trwałych logów.

## 8. Dane do logowania i testowania

Każda decyzja powinna zawierać: `decision_id`, slot UTC, ceny końcowe kupna i netto sprzedaży, dostępne PV, dom, SOC, napięcie baterii, aktywny TOU, proponowany limit A (wartość/krok), oczekiwany przepływ DC/AC, przewidywany koszt i alternatywę, czas ważności oraz przyczynę wyboru. Oddzielny wpis `command_applied` i `physical_observation` tylko po rzeczywistych działaniach. Więcej: [DECISION_LOGGING.md](DECISION_LOGGING.md).

## 9. Testy jednostkowe translatora (fikstury, jeszcze niewykonane)

- `CUR-01`: napięcie 56 V, 5 A → limit 0,280 kW DC; 50 A → 2,800 kW DC, a zadeklarowany limit ładowania 2,5 kW ma pierwszeństwo.
- `CUR-02`: PV 3,0 kW, dom 0,5 kW, η=1, eksport PV dopuszczony, ładowanie max 2,5 kW: dla 5 A → magazyn 0,28 kW i eksport 2,22 kW.
- `CUR-03`: jak CUR-02, lecz limit 50 A → magazyn 2,50 kW i eksport 0 kW.
- `CUR-04`: PV 0,1 kW, dom 0, bateria 56 V, limit 5 A → ładowanie **0,1 kW**, a nie oczekiwane zawsze 0,28 kW.
- `CUR-05`: rano sprzedaż 0,80, po południu 0,50 DKK/kWh (obie ceny spełniają próg 0,40), potrzeba magazynować 2,5 kWh, η=1 → poranne 5 A i popołudniowa korekta daje przychód **1,916 DKK**, a odwrotna alokacja **1,25 DKK**.
- `CUR-06`: dla tych samych warunków matematyczny wariant 0 A rano daje **2,00 DKK**, a przed trybem live wymaga zwykłego sprawdzenia stanu wykonawcy/HA, nie ponownego pytania użytkownika o 0 A.
- `CUR-07`: ogólny limit ładowania 5 A + limit grid charge 50 A → efektywny limit sieci 5 A, jeśli ładowanie z sieci jest aktywne; odwrotnie 50 A + 5 A → limit 5 A.
- `CUR-08`: wyłączony Grid Charge w aktywnym TOU, limit sieci 50 A → brak wnioskowania, że bateria musi ładować z sieci.
- `CUR-09`: planowane 75% jako minimum, aktywne TOU 20%, brak mechanizmu zmiany → `missing_capabilities` i brak obietnicy utrzymania SOC.
- `CUR-10`: ceny jutra jeszcze nieopublikowane → granica horyzontu na ostatniej znanej cenie, bez dopisywania ceny na „potrzebny” okres.
- `CUR-11`: limit 5 A pozostaje po utracie HA o planowanej godzinie przełączenia → modeluje stratę ekonomiczną, nie sztuczny powrót do 50 A.
- `CUR-12`: user policy 0–50 / 0–100 / 0–50 A i nielegalne 51 A, 101 A → odpowiednie prośby odrzucone, bez cichego przycięcia.
- `CUR-13`: niedostępne napięcie baterii albo nieznany krok nastawy → brak pozornie dokładnej konwersji kW na A.
- `CUR-14`: sam sukces `number.set_value` nie jest pomiarem rzeczywistego prądu; jeśli ładowanie fizycznie możliwe, a odczyt nadal wykazuje poprzednią nastawę lub przekroczenie limitu → diagnostyka, nie podwójny zapis w ciemno.
- `CUR-15`: zakup i sprzedaż pobierane z odpowiednich encji HA bez jakichkolwiek korekt; żadnych prowizji ani taryf w Co-Pilot; próg PV export 0,40 DKK/kWh według [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md).
- `CUR-16`: wariant z wyższą ceną sprzedaży rano, ale niepewną jutrzejszą PV i dynamicznym celem SOC → algorytm optymalizuje cały horyzont, nie sztywną regułę „rano 5 A, w południe 50 A”.
- `CUR-17`: eksport PV wyłączony, bateria pełna → zmniejszenie prądu ładowania nie tworzy przychodu, a może skutkować ograniczeniem PV.
- `CUR-18`: przy awarii HA plan `grid_charge` wymagający przyszłego wyłączenia jest zablokowany bez niezależnego sposobu zakończenia, mimo dodatniego zysku prognozy.
- `CUR-19`: brak aktywnego `battery_controller.*` → osierocone encje historyczne ignorowane, nie tworzyć konfliktu.
- `CUR-20`: odwrócone źródło limitów PV/grid charge w mapowaniu → testy asercji ról HA nie pozwalają zamienić encji ładowania ogólnego z sieciowym.

**Warunek przekazania Codexowi:** każda testowana nastawa musi przejść kontrolę jednostek A↔kW, bilans SOC i energii, znane ograniczenia bieżącego TOU oraz rejestr decyzji. Dla wariantów bez danych fizycznych raportować `simulation_assumption`, nigdy `physically_verified`.
