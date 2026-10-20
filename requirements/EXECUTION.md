# Wykonanie przez HA, bezpieczeństwo i sterowanie

**Decyzje użytkownika: [REQUIREMENTS.md](REQUIREMENTS.md).** Nie kopiować poniższych wcześniejszych ograniczeń dostępu jako decyzji użytkownika. Szczególnie: automatyczny grid charge i 6 TOU są dozwolone po testach live; ręczna zmiana może być nadpisana przy nowym planie; stała degradacja to 0,40 DKK/kWh rozładowania DC.


---

## EXECUTION CONTRACT


**Status:** dokumentacja projektowa. Uruchomienie rzeczywistych zapisów wymaga zamknięcia P0 w [OPEN_ITEMS.md](OPEN_ITEMS.md). Powiązania: [ENTITY_CONTRACT.md](HA_CONTRACT.md), [ARCHITECTURE.md](EXECUTION.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION.md).

**Granica sterowania:** executor ma operować **wyłącznie na encjach Home Assistant** i wysyłać polecenia przez natywne usługi HA. Nie istnieje w nim warstwa dostępu do rejestrów Modbus, klient Modbus, bezpośrednie sterowanie falownikiem ani modyfikacja ESPHome. Specyfikacja traktuje trzy encje prądowe HA jako przypisane do ich opisanych funkcji na podstawie założenia projektowego użytkownika; wymagania weryfikacji działania przed uruchomieniem automatyki pozostają aktualne.

## 1. Role

- **Planner** wyznacza plan, SOC, harmonogram i uzasadnienie; jego wynik to *intencja*, nie polecenie.
- **Capability registry** sprawdza, czy konkretna funkcja jest możliwa przez istniejące encje HA: `unknown`, `read_only`, `validated_write` lub `disabled`.
- **Executor** używa wyłącznie zweryfikowanych usług/encji HA, nigdy bezpośrednio Modbus lub firmware, i nie zakłada, że każdą moc może ustawić.
- **Observer** niezależnie mierzy rezultat fizyczny; stan encji po zapisie nie wystarcza.
- **Safety gate** sprawdza ograniczenia przed każdą akcją i podczas długich operacji.
- **Approval manager** wiąże pojedyncze zgody na celowy eksport baterii z niezmienną wersją propozycji.

## 2. Uprawnienia

| Tryb | Czynności |
| --- | --- |
| `monitor` | Odczyt pomiarów, diagnostyka; zero zapisów |
| `dry_run` | Symulacja i publikacja planu; zero zapisów |
| `supervised_test` | Jeden jawnie zatwierdzony test pojedynczej, zweryfikowanej funkcji ze sprawdzonym sposobem powrotu |
| `automatic_non_export` | Po P0 również autonomiczne `switch.sun12k_solar_sell` ON/OFF na podstawie ceny z HA i progu **0,40 DKK/kWh**; **nie** uprawnia do eksportu baterii [PV_EXPORT_POLICY.md](EXECUTION.md) |
| `automatic_with_approved_export` | Jak wyżej, dodatkowo w granicach ważnej zgody na konkretny eksport baterii |

Wzrost uprawnień **nie następuje automatycznie po restarcie**, zmianie wersji planu ani dodaniu encji. `monitor`/`dry_run` to domyślne tryby działania. Znaczenie encji przyjmujemy projektowo z kontraktu HA, natomiast nazwy ani opis YAML nie potwierdzają jeszcze skutku fizycznego nastaw.

## 3. Karta operacji — warunek dopuszczenia zapisu

Dla każdej operacji stworzyć rekord:

| Pole | Znaczenie |
| --- | --- |
| `capability_id` | Logiczna funkcja, np. zezwolenie na ładowanie z sieci |
| `entity_id / domain / service` | Konkretne, istniejące w HA źródło zapisu |
| `allowed_values / unit` | Granice, krok, jednostka i znaczenie znaku |
| `initial_state` | Odczyt urządzenia przed poleceniem, także nastawy fabryczne/harmonogram |
| `physical_effect` | Oczekiwany, niezależnie mierzalny rezultat |
| `feedback_source` | Encje pomiarowe, czas ustalenia, tolerancja, kryterium braku efektu |
| `stop_method / recovery_method` | Sprawdzona procedura przerwania, wznowienia i przywrócenia normalnego trybu |
| `loss_of_HA_behavior` | Wynik fizycznego testu zaniku HA i łączności; warunek niezależnego fail-safe |
| `validation_evidence / status` | Data, test, obserwacja i wynik; tylko `validated_write` dopuszcza akcję |

Użytkownik **zaakceptował automatyczne sterowanie zezwoleniem na eksport PV** `switch.sun12k_solar_sell` według progu 0,40 DKK/kWh bez przeliczeń ceny. Samo zezwolenie nie jest zgodą na eksport baterii. Przed live obowiązuje test skutku i możliwości bezpiecznego przełączenia. [PV_EXPORT_POLICY.md](EXECUTION.md).

Działanie złożone wymaga potwierdzenia, że **zestaw** akcji rzeczywiście realizuje zamierzony przepływ. `charge_power_kw = 2` nie może zostać „zrealizowane” samym włączeniem przełącznika grid charge. Podobnie globalne zezwolenie na eksport nie dowodzi bezpiecznego rozdzielenia PV i baterii.

### Własne granice prądu Energy Co-Pilot

Dla trzech regulatorów Deye executor stosuje **twarde zakresy polityki użytkownika** (włącznie): `number.sun12k_maximum_battery_charge_current` **0–50 A**, `number.sun12k_maximum_battery_discharge_current` **0–100 A**, `number.sun12k_maximum_battery_grid_charge_current` **0–50 A**. HA reklamuje błędne metadane ±16 777 220 A — **nie** wolno ich używać do wyznaczenia granic. Pełna tabela: [ENTITY_CONTRACT.md](HA_CONTRACT.md).

- Limity dotyczą docelowych wartości parametrów *prądowych* w A; nie zastępują limitów BMS, mocy falownika, temperatury ani definicji źródła ładowania.
- Każda żądana nastawa spoza przedziału jest **odrzucana** i logowana z kodem `CURRENT_LIMIT_OUT_OF_RANGE`. Nie robić cichego `clamp` i nie wysyłać polecenia.
- `0 A` jest dopuszczalną nastawą; użytkownik 20.10.2026 potwierdził, że falownik przyjmuje zadane wartości i reaguje prawidłowo. Nie wymagać ponownej deklaracji od użytkownika. Executor nadal ma egzekwować granice oraz weryfikować efekt polecenia przez aktualne HA przed uruchomieniem automatyki.
- Przed zmianą prądu moduł musi mieć status `validated_write`, potwierdzoną jednostkę, bezpieczne wartości, pomiar zwrotny i sposób wyjścia. Żadne z tych ograniczeń nie aktywuje automatyki samo.
- Encje `battery_controller.*` są zgodnie z wyjaśnieniem użytkownika osieroconymi pozostałościami i **nie służą do blokowania** Energy Co-Pilot, rozpoznawania konfliktów ani wyznaczania nastaw. Jedynie realnie zaobserwowany inny aktywny wykonawca może stanowić konflikt.

### Backend wykonawczy current-first i istniejący TOU

Projektowy kanał bieżących korekt to natywne usługi HA do encji limitu prądu baterii; szczegóły [CONTROL_STRATEGY.md](EXECUTION.md). To **górny limit**, nie polecenie dokładnej mocy. Aktywne TOU pozostaje w stanie zastanym; jego aktualny okres i SOC ograniczają realną wykonalność intencji. Osobna operacja ładowania z sieci wymaga warunków globalnego Grid Charge, limitu ogólnego, limitu sieci i zgody Grid Charge w TOU. Zmiana wyłącznie limitu w A **nie** jest gwarancją ładowania.

Urządzenie utrzymuje ostatnio zapisane nastawy po utracie HA. **Użytkownik 20.10.2026 zaakceptował taki stan oraz możliwe straty ekonomiczne do czasu powrotu HA** (np. nieoptymalną cenę grid charge/eksportu PV). Nie uznawać utraty HA za fizyczne wyłączenie działania. Tam, gdzie przyszła komenda `OFF` jest warunkiem *bezpieczeństwa fizycznego lub egzekucji konkretnej zgody na eksport baterii*, wymagany jest niezależny mechanizm ochrony; sama nieoptymalność ekonomiczna nie wymaga nowego sprzętowego wyłącznika. **Bezpieczny fizycznie limit prądu** i **ekonomicznie optymalna nastawa na dany kwadrans** to różne właściwości. Po restarcie konieczny nowy odczyt i plan, a nie odtworzenie dawnego polecenia.

Dynamiczne programowanie sześciu okien TOU stanowi **osobną, domyślnie nieaktywną zdolność**, dopiero po testach atomowości pozornej, granicy 00:00, powtarzalności dobowej i wycofania niekompletnej aktualizacji. Samo istnienie encji TOU nie nadaje prawa do ich zapisu.

## 4. Sekwencja pojedynczej akcji

1. **Snapshot i lock:** jedyny wykonawca operacji uzyskuje blokadę, zapisuje `plan_id`, `action_id`, slot UTC, wersję mapowania, bieżące pomiary i stan urządzenia.
2. **Walidacja:** aktualność planu/cen/SOC, kompletność pomiarów, rozdział źródeł energii, BMS i limity, stan innych automatyzacji, zweryfikowana zdolność, potrzebna zgoda, **test niezależnego fail-safe**.
3. **Idempotencja:** nie wysyłać komendy, gdy fizyczny stan już odpowiada zamierzeniu. Przy nieznanym skutku poprzedniego zapisu nie ponawiać w ciemno.
4. **Ostateczna kontrola tuż przed zapisem:** `plan_id` i zgoda wciąż aktualne; pomiary nie zmieniły się poza tolerancję; brak anulowania/STOP.
5. **Usługa HA:** wysłać tylko do zmapowanej `validated_write` usługi. Sekwencje wieloetapowe są nieatomowe: każdy krok wymaga potwierdzenia przed następnym.
6. **Weryfikacja:** po czasie ustalenia sprawdzić zarówno odczyt stanu, jak i **fizyczny efekt**; obserwować również zakazane skutki uboczne (np. niezamierzony eksport z baterii).
7. **Rezultat:** `confirmed`, `failed` albo `uncertain`, z `plan_id`, `action_id`, czasem, wartością zadaną, odczytaną i przyczyną. Samo powodzenie wywołania usługi oznacza najwyżej `applied`.
8. **Dalsze działanie:** tylko po potwierdzeniu przejść do kolejnej akcji; przy błędzie przerwać plan i wykonywać wyłącznie sprawdzoną procedurę wyjścia.

**Retry:** dopuszczalny jedynie po dowiedzeniu, że poprzedni zapis nie zadziałał, a operacja jest bezpieczna i idempotentna. Timeout z nieznanym efektem = `uncertain`, nie kolejne polecenie.

## 5. Stany wykonawcy

`disabled`, `monitoring`, `simulating`, `ready`, `validating`, `applying`, `verifying`, `confirmed`, `blocked`, `failed`, `uncertain`, `recovery_required`, `supervised_recovery`.

`blocked`: brak warunku bezpieczeństwa, aktualnej ceny, mapowania lub zgody.  
`uncertain`: rzeczywisty skutek polecenia nieznany; brak dalszych poleceń.  
`recovery_required`: w urządzeniu mogła pozostać aktywna dawna nastawa; przed powrotem wymagana weryfikacja.

Każda zmiana stanu ma `timestamp_utc`, kod przyczyny i powiązane `action_id`. Nie utożsamiać `planned`, `applied` i `confirmed`.

## 6. Propozycja i zgoda na eksport baterii

Propozycja określa: `proposal_id`, `plan_id`, okres UTC, `expires_at`, maksymalną energię eksportu baterii **kWh AC**, moc AC, ograniczenie SOC, przewidywany **dodatkowy** zysk w DKK względem planu bez eksportu baterii, ceny, sprawności, degradację i stan źródła pomiaru.

- Stany: `pending` → `approved` / `rejected` / `expired` / `revoked` / `consumed`. Brak reakcji nie jest akceptacją.
- Użytkownik zatwierdza w HA; powiadomienie może wskazywać propozycję, nie stanowi zgody samo w sobie.
- Zgoda dotyczy **tylko** niezmiennego `plan_id`, okna i limitów. Zmiana planu, ilości, godzin lub istotnych założeń ceny powoduje wygaśnięcie; nie wolno przenosić zgody.
- Przed startem i podczas każdego slotu ponownie sprawdzać plan, ceny, SOC, przepływy oraz **pozostałe kWh zgody**. Granica obowiązuje sumarycznie, nie osobno na każdy kwadrans.
- Jeśli nie da się niezależnie pomierzyć energii eksportowanej **z baterii**, nie można egzekwować limitu zgody → eksport baterii zablokowany.
- Gdy następuje utrata zgody podczas aktywnego eksportu, należy **zakończyć go wcześniej zweryfikowanym sposobem i potwierdzić stan fizyczny**. Jeśli brak takiego sposobu, funkcji tej w ogóle nie dopuszczać.

### Klasy ryzyka trwałej nastawy po utracie HA

Wg użytkownika **wszystkie** nastawy Deye z HA pozostają zapisane po zaniku HA. Executor musi klasyfikować każdą akcję przed aktywacją:

| Klasa | Przykład | Wymóg przy utracie HA |
| --- | --- | --- |
| `persistent_limit` — fizycznie bezpieczne maksimum | Zweryfikowany limit ładowania baterii, np. niski limit PV | **Dopuszczalne tylko po wykazaniu**, że trwała wartość nie powoduje fizycznego niebezpieczeństwa; brak przyszłej korekty może oznaczać **koszt ekonomiczny**, logowany osobno, nie domniemaną awarię BMS |
| `requires_autonomous_end` — czynność wymagająca zakończenia z powodów bezpieczeństwa lub zgody | Zatwierdzony eksport baterii z limitem kWh/czasu; dowolna akcja z fizycznym ograniczeniem czasu | Wymaga niezależnego, sprawdzonego zakończenia. **Grid charge w bezpiecznych limitach może pozostać aktywny po awarii HA za zgodą użytkownika**, mimo strat ekonomicznych; nie klasyfikować go automatycznie jako niebezpiecznego wyłącznie z powodu ceny |
| `multi_setting_persistent` — złożona nastawa | Zmiana sześciu przedziałów TOU | Wymaga bezpiecznego pośredniego i końcowego stanu oraz analizy powtórzenia harmonogramu po północy i następnego dnia |

**Interpretacja wymogu fail-safe:** nie oznacza konieczności mechanicznego resetu wszystkich bezpiecznych limitów przy zaniku HA. Oznacza dowiedzenie, że **fizyczny stan utrzymywany bez HA** pozostaje dopuszczalny i chroniony niezależnie przez falownik/BMS. Dla cykli zależnych od zakończenia w określonym czasie ten warunek nie jest spełniony samym ograniczeniem prądu. Brak stosownego dowodu blokuje tylko daną klasę działania. Sposób porównywania strategii: [CONTROL_STRATEGY.md](EXECUTION.md).

## 7. Anulowanie, konflikt, restart i awaria

| Zdarzenie | Działanie |
| --- | --- |
| Nowy `plan_id` przed akcją | Odrzuć starą akcję i przelicz warunki; stara zgoda na sprzedaż nie przechodzi do nowego planu |
| Nowy plan w trakcie operacji | Zatrzymaj dalsze kroki, zweryfikuj skutek ostatniego i zastosuj przetestowaną procedurę bezpiecznego wyjścia |
| Dane `unknown` / `unavailable` / przeterminowane | Zakaz nowych poleceń; aktywny tryb kończyć tylko zweryfikowaną procedurą |
| Usługa zwróciła sukces, brak efektu w pomiarach | `failed` lub `uncertain`; nie oznaczać jako sukces |
| Ręczna zmiana przy aktywnym Co-Pilot | Co-Pilot może nadpisać ją przy następnym planie; bez pętli zapisów. STOP i bezpieczeństwo mają pierwszeństwo |
| Restart HA lub integracji | Najpierw odczyt i uzgodnienie stanów; bez odtwarzania poprzedniej aktywnej akcji ani poprzedniej zgody |
| Wyłączenie/odinstalowanie | Wstrzymaj nowe akcje; nie twierdź, że urządzenie wróciło do normalnego trybu bez fizycznego dowodu |
| Awaria całego HA/Wi-Fi | Ostatnie nastawy Deye pozostają aktywne — **zaakceptowane przez użytkownika**. Fizyczna ochrona BMS/falownika i twarde min SOC 20% pozostają wymogiem; nie wykonywać nowych akcji. Po powrocie odczyt i nowy plan. Dla ograniczonych zgód, np. eksportu baterii, wymagać niezależnego zakończenia |

**Kluczowe:** brak nowych poleceń NIE wyłącza utrzymanej w falowniku nastawy. Przed automatyzacją trzeba wykazać bezpieczne zachowanie każdego aktywnego trybu także bez HA. Standardowej konfiguracji falownika ani działania resetu nie wolno zgadywać.

Przycisk STOP w HA wstrzymuje nowe akcje i może użyć **tylko sprawdzonej** procedury zatrzymania. Nie jest sprzętowym wyłącznikiem awaryjnym. Obsługa ponownego uruchomienia po awarii wymaga rekoncyliacji, a nie bezwarunkowego wznowienia.

**Audyt:** wszystkie walidacje, próby wywołania HA, potwierdzenia fizyczne, błędy i anulowania powiązać przez `action_id` z `decision_id` i `plan_id` w [DECISION_LOGGING.md](VALIDATION.md). Nie logować samej zmiany encji jako potwierdzonego fizycznego rezultatu.

## 8. Testy (na encjach fikcyjnych, nie na instalacji)

- `EXE-01` stary plan tuż przed zapisem → brak wywołania HA.
- `EXE-02` brak `validated_write` → brak wywołania, wskazana brakująca zdolność.
- `EXE-03` sukces API, brak fizycznego efektu → `failed/uncertain`.
- `EXE-04` timeout o nieznanym skutku → brak ślepego retry.
- `EXE-05` zmiana planu między walidacją i wysłaniem → anulowanie.
- `EXE-06` zgoda na inny plan lub przeterminowana → zero eksportu z baterii.
- `EXE-07` osiągnięty limit sumy kWh zgody → kolejny eksport niemożliwy.
- `EXE-08` utrata pomiaru podczas eksportu → tylko zweryfikowane przerwanie, `uncertain`.
- `EXE-09` restart ze starą aktywną nastawą → nie odtwarzać automatycznie starej komendy.
- `EXE-10` obca automatyzacja zmienia nastawę → konflikt i brak zapętlenia zapisów.
- `EXE-11` kliknięcie STOP → wstrzymanie nowych poleceń i nie zgłaszać sukcesu zatrzymania przed pomiarem.
- `EXE-12` brak fizycznego fail-safe bez HA → aktywacja automatyki niemożliwa.

## 9. Warunek odbioru

Dla **każdej** akcji konieczne są zweryfikowany fizyczny rezultat, ograniczenia, odczyt zwrotny, sposób zakończenia i niezależny fail-safe. Brak choćby jednego krytycznego elementu blokuje **tę funkcję**. Monitoring i dry-run pozostają dostępne.


---

## CONTROL STRATEGY


**Status:** decyzja architektoniczna dla Co-Pilot, oparta na obserwacjach użytkownika i istniejących encjach HA. **Nie jest potwierdzeniem fizycznej reakcji urządzenia.** Jest to kontrakt projektowy Codexa, nie instrukcja natychmiastowej zmiany nastaw.
Powiązania: [ENTITY_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION.md), [EXECUTION_CONTRACT.md](EXECUTION.md), [DECISION_LOGGING.md](VALIDATION.md), [OPEN_ITEMS.md](OPEN_ITEMS.md).

## 1. Rozstrzygnięcie: dwa poziomy, a nie TOU kontra prąd

**Decyzja użytkownika 20.10.2026:** Co-Pilot może autonomicznie sterować ładowaniem z sieci i sześcioma okresami TOU. Cel to minimum całkowitego kosztu w dostępnym horyzoncie, po uwzględnieniu strat i degradacji. Etapowa implementacja i bezpieczna walidacja TOU nadal obowiązują. Nie zakładać, że pojedynczy limit prądu zastępuje kontrolę docelowego/minimalnego SOC lub gwarantuje ładowanie z sieci.

- **Planner:** szuka ekonomicznie najlepszego planu w kwadransach na podstawie opublikowanych cen i prognoz; plan jest opisem *celu energetycznego*, nie gotowymi nastawami urządzenia.
- **Translator/current controller:** przekształca plan na **dopuszczalne limity prądowe**. Zgodnie z obserwacją użytkownika falownik **precyzyjnie egzekwuje zapisaną nastawę**; kontrola zwrotna wykrywa jedynie brak dostępnej energii, blokady fizyczne, utratę komunikacji lub zmianę stanu urządzenia, zamiast zakładać losowe błędy wykonania.
- **TOU:** obecny harmonogram pozostaje aktywny/zastany. Nie nadpisywać go „profilami 15-minutowymi”; zapisuje się trwale w falowniku, powtarza się co dobę, ma tylko sześć przedziałów i jest wrażliwy na zazębianie/czas 00:00.
- **Backtester:** odrębnie ocenia idealny plan energetyczny, plan **wykonywalny samą regulacją prądu** przy stałym TOU oraz opcjonalny plan z dynamicznym TOU. Nie raportować oszczędności idealnego planu jako oszczędności osiągalnych.
- **Executor:** zawsze używa wyłącznie encji HA i natywnych usług HA, nigdy bezpośredniego Modbus/rejestrów lub modyfikacji ESPHome.

Wynik: **preferencja current-first** dla prądów + **autonomiczne zezwolenie na eksport PV** według [PV_EXPORT_POLICY.md](EXECUTION.md), nie definitywne stwierdzenie, że TOU nie jest potrzebne. Wykorzystanie TOU wynika z *brakującej zdolności i policzonej korzyści*, nie z założenia, że wszystkie harmonogramy należy nadpisywać.

## 2. Potwierdzone obserwacje użytkownika — odróżnić od hipotez

- Przy drogiej sprzedaży PV przed południem użytkownik ograniczał prąd ładowania do ok. **5 A**, a następnie zwiększał go w godzinach tańszej sprzedaży. To jest oczekiwane zachowanie strategii.
- Użytkownik próbował obu regulatorów HA i obserwował, że zmiana jednego z nich nie zawsze dawała efekt.
- W TOU wartość **SOC głównie ogranicza rozładowanie**, a przy zaznaczonym **Grid Charge** wyznacza też poziom ładowania z sieci; **SOC w TOU nie reguluje ładowania z PV**.
- Błędy harmonogramu mogą wynikać z nakładających się przedziałów lub przejścia przez północ.
- Wszystkie nastawy, zarówno z ekranu falownika, jak i z encji HA, **pozostają zapisane w urządzeniu**. Utrata HA nie cofa ich.
- Aktualnie **eksport energii z baterii jest wyłączony**. Nie uznawać tego za gwarancję na przyszłość bez weryfikacji pozycji odpowiedzialnej za eksport.

Projektowo, zgodnie z decyzją użytkownika, przyjmujemy semantykę encji odpowiadającą nazwom; fizyczne potwierdzenie jest osobnym warunkiem aktywacji zapisu.

**Założenie potwierdzone przez użytkownika:** Deye wykonuje ustawione przez encję HA ograniczenie prądu **dokładnie i deterministycznie**, kiedy istnieją warunki do jego wykorzystania. Nie wprowadzać do optymalizatora hipotetycznej losowej niedokładności samego falownika. `maximum_*_current` oznacza **górną granicę**, więc nie można wymusić płynięcia określonego prądu, jeżeli PV, zapotrzebowanie/zezwolenie na ładowanie, SOC, BMS lub napięcie tego nie umożliwiają. To jest **ograniczenie warunków pracy**, a nie kwestia „AI” lub jakości wykonywania poleceń.

**Szczegółowy algorytm wyboru wartości amperów, wynikowe przepływy DC/AC i testy liczbowe:** [CURRENT_CONTROLLER_MODEL.md](EXECUTION.md). Niniejszy dokument wyznacza granice architektury, drugi opisuje jednoznaczne przeliczenia i reguły działania.

## 3. Kanały sterowania — encje, zakres i funkcja

| Intencja | Encja HA | Reguła projektowa / ograniczenie |
| --- | --- | --- |
| Ogólny górny limit prądu ładowania, w tym PV | `number.sun12k_maximum_battery_charge_current` | **0–50 A**; zmiana pozwala odroczyć przyjęcie PV, ale **nie** gwarantuje określonej mocy ani eksportu |
| Górny limit rozładowania | `number.sun12k_maximum_battery_discharge_current` | **0–100 A**; nie jest samodzielnym nastawieniem docelowego SOC ani kierunku rozładowania |
| Dodatkowy górny limit prądu ładowania **z sieci** | `number.sun12k_maximum_battery_grid_charge_current` | **0–50 A**; sam limit nie zezwala na ładowanie, a przy aktywnym niższym limicie ogólnym nie oczekiwać większego prądu |
| Ogólna zgoda na ładowanie z sieci | `switch.sun12k_grid_charge` | Nie jest poleceniem mocy ani osiągnięcia docelowego SOC; zależy od trybu/TOU |
| TOU włącz/wyłącz | `switch.sun12k_time_of_use` | **Domyślnie bez zapisów w current-first**; obecny stan i harmonogram zawsze uwzględnić w modelu |
| Zezwolenie Grid Charge w okresie TOU | `switch.sun12k_time_point_1_charge_enable` … `_6_charge_enable` | Może współdecydować o ładowaniu z sieci w danych okresach; **nie** stanowi sterowania PV |
| Czas / moc / SOC dla okresów TOU | `number.sun12k_time_point_1_start` … `_6_start`, `_1_power` … `_6_power`, `_1_capacity` … `_6_capacity` | Są to **nastawy trwałego harmonogramu**; bez osobnego, bezpiecznego mechanizmu publikacji nie używać do bieżących korekt |
| Autonomiczne zezwolenie na eksport PV | `switch.sun12k_solar_sell` | **Cena z `sensor.energi_data_spotpris` >= 0,40 DKK/kWh → ON; poniżej → OFF**, bez korekt ceny. Użytkownik upoważnił do samodzielnego sterowania po uruchomieniu live, ale nie do eksportu baterii bez osobnej zgody. [PV_EXPORT_POLICY.md](EXECUTION.md) |

**Ważne:** wartości prądu w amperach ograniczają dopuszczalny pobór/oddawanie po stronie baterii. Przy napięciu około 56 V limit **5 A odpowiada orientacyjnie 0,28 kW po stronie DC**, nie jest poleceniem ładowania stałą mocą 280 W ani gwarancją dodatkowego eksportu 280 W. Aktualne napięcie, BMS, SOC, dostępne PV, obciążenie i falownik determinują przepływ.

## 4. Sterowanie w czasie — jeden cykl

**Planowanie:** co 15 minut oraz po *rzeczywistym* nadejściu cen, zmianie SOC/produkcji/poboru i wykryciu istotnego odchylenia. Bez fikcyjnych cen po końcu opublikowanego horyzontu.

**Wybór intencji na bieżący slot:** na podstawie porównania wariantów ekonomicznych i dostępnej mocy PV wybierz np. `pv_export_priority`, `pv_store_priority`, `battery_to_home`, `grid_charge_candidate` lub `idle`. To nie są nowe encje ani tryby sprzętowe.

1. Zidentyfikuj **rzeczywisty obecny TOU** oraz ograniczenia SOC. Jeśli nie znasz aktywnego okresu/trybu, nie twierdź, że plan można wykonać.
2. Dla PV w wariancie *eksport-przed-magazynowaniem* przyjmij ograniczenie ogólnego prądu ładowania (np. ilustracyjne **5 A**, **nie** uniwersalny próg). Przy wariancie magazynowania większy dozwolony limit, wyliczony ze zdolności i rzeczywistej prognozy oraz potrzeb na resztę horyzontu (np. **50 A**, gdy uzasadnione).
3. Oblicz sugerowaną nastawę **z przewidywanego przepływu DC i aktualnego napięcia baterii**; uwzględnij, że to *ograniczenie maksimum*, a nie pełne odwzorowanie żądanej mocy. Rzeczywista moc PV ładowania może być mniejsza nawet przy wysokim limicie.
4. Dla ładowania z sieci sprawdź łączną logikę ogólnego limitu ładowania, dodatkowego limitu sieci, zgody Grid Charge i aktywnego TOU z celem SOC. **Nie zakładaj**, że samo ustawienie 50 A uruchomi ładowanie. Jeśli wymagane sterowanie SOC/oknem jest niedostępne w bieżącym wariancie → `not_executable`.
5. Dla „nie rozładowuj poniżej dynamicznego SOC” **sam limit rozładowania nie musi wystarczyć**, bo nie definiuje progu SOC. Dopóki nie ma zweryfikowanego sterowania dynamicznym minimum SOC, planowana energia pozostaje propozycją, a nie gwarantowanym działaniem.
6. Rozważ zmianę tylko wtedy, gdy przewidywana korzyść jest dodatnia **po stratach i degradacji**, a koszt błędu prognozy/zbędnego przełączania nie odwraca znaku. Nie wymyślać progu spot ani stałego celu nocnego SOC.
7. Dla każdego planu zapisz **oczekiwaną nastawę HA**, powód, cenę zakupu/sprzedaży, oczekiwany kierunek przepływu i brakujące zdolności do [DECISION_LOGGING.md](VALIDATION.md).
8. Przed zapisem w przyszłym executorze sprawdź P0, stan źródła i zgodę, wyślij natywną usługę HA, sprawdź niezależnie realny efekt (moc baterii i przepływ sieci), reaguj na niezgodność. Przy aktualnie dozwolonym jedynie `dry_run` zapisz intencję **bez** zapisu.

**Antyoscylacja:** wprowadzić techniczną politykę minimalnej zmiany nastawy i czasu pozostania w stabilnym stanie, ale parametry oszacować z rozdzielczości sterowania i pomiarów, a nie ustalać arbitralnego progu ekonomicznego. Ponowna optymalizacja nie powinna wymuszać identycznego zapisu co 15 minut.

## 5. Trwałość nastaw i utrata HA

**Fakt od użytkownika:** falownik utrzymuje **ostatnio zapisane** limity i TOU nawet gdy HA jest wyłączony. To nie jest ani automatyczny powrót do ustawień fabrycznych, ani zegar kończący plan. Wariant current-first musi uwzględnić:

- Limit ładowania PV **5 A pozostawiony przy utracie HA** może prowadzić do dalszego eksportu/niewykorzystania PV zamiast magazynowania. Jest to ryzyko ekonomiczne; nie uznawać go automatycznie za zagrożenie BMS.
- Ustawienie umożliwiające **ładowanie z sieci** może pozostać aktywne poza opłacalną godziną. Nie dopuszczać automatycznej jednorazowej operacji zależnej od przyszłego wyłączenia przez HA, jeśli brak udowodnionego sprzętowego zakończenia.
- Nastawa TOU może obowiązywać **kolejnego dnia**, mimo innych prognoz i cen. To zasadniczy argument przeciw automatycznemu nadpisywaniu TOU jako harmonogramu ceny na jeden dzień.
- Można rozważać osobno **utrzymujące się bezterminowo ograniczenia maksymalne**, które są bezpieczne fizycznie również po utracie HA, od **czasowo ryzykownych zezwoleń**. Każde ma własną kartę ryzyka: urządzenie, ekonomia, restart i pomiar.
- Po powrocie HA: odczyt rzeczywistych nastaw → wykrycie odchylenia od poprzedniego planu → nowy plan i ponowna walidacja; nigdy ślepe „dokończenie” starego slotu.
- **STOP w panelu HA nie jest sprzętowym odłączeniem.** Zatrzymuje nowe zapisy; przywrócenie nastaw wymaga osobno sprawdzonej ścieżki i fizycznego potwierdzenia.

Brak fizycznie zweryfikowanej niezależnej bariery bezpieczeństwa blokuje odpowiednie automatyczne działania, **nie** planowanie, monitorowanie i porównanie metod.

## 6. TOU jako alternatywny backend — kryteria dopuszczenia

Dynamiczne TOU ma sens, gdy jest **realnie potrzebne do sterowania SOC lub grid charge**, albo istotnie zmniejsza liczbę zależnych od HA przełączeń **bez** ryzyka trwałego złego planu. Samo istnienie sześciu slotów nie jest powodem użycia.

**Problem strukturalny:** Deye przechowuje **6 powtarzalnych okien dobowych**, a cena/przewidywana pogoda zmieniają się pomiędzy dniami. Harmonogram planowany na 15-minutowych slotach nie daje się zawsze skompresować do 6 przedziałów bez utraty jakości. Nie obiecywać pełnej realizacji 96 slotów poprzez 6 nastaw.

Przed implementacją zmian TOU wymagamy:
- aktualnego odczytu **wszystkich 6 przedziałów**, ich startów, SOC, mocy i przełączników, z ustaloną semantyką godziny początku/końca;
- walidatora: dokładnie ustalony porządek okien, brak niedozwolonych nakładań, brak nieustalonej interpretacji 00:00 i przejścia przez północ, format czasu (jednostka odczytu), kontrola 23/25 godzin przy DST;
- **bezpiecznej publikacji** zmian wieloencjowych: kolejność, brak chwilowego niepożądanego przedziału, odczyt każdej encji po zapisie, sposób wyjścia z częściowej aktualizacji — samo kilka udanych usług HA nie oznacza operacji atomowej;
- zachowania urządzenia po utracie HA i nazajutrz **udowodnionego na realnym harmonogramie**, a nie hipotetycznego;
- zakazu przypadkowego eksportu z baterii i zachowania indywidualnych zgód;
- backtestu pokazującego przewagę nad **current-first z niezmienianym TOU**, mierzoną w DKK i liczbie zmian nastaw, po uwzględnieniu ryzyka braku łączności.

Do czasu spełnienia warunków opcjonalny backend dynamicznego TOU pozostaje **wyłączony**, ale dane jego aktualnej konfiguracji powinny być wejściem do symulacji.

## 7. Warunek uczciwej oceny metod

Każdy przebieg symulacji liczyć dla **tych samych** cen, przyszłej prognozy, początkowego SOC, fizycznego PV i obciążenia, ograniczeń mocy oraz zasad wartości energii końcowej. Porównywać:

| Wariant | Cel porównania |
| --- | --- |
| `baseline_deye` | Obecne zachowanie Deye bez poleceń Co-Pilota (w tym istniejące TOU i eksport) |
| `ideal_dispatch` | Matematycznie optymalne przepływy **bez** uproszczenia do encji; górna granica możliwości, nie obietnica |
| `current_first` | Aktualne encje limitu prądu + istniejące TOU; **dokładnie respektowane limity**, przy uwzględnieniu dostępności PV, SOC, BMS i działania innych warunków falownika |
| `dynamic_tou` | Wariant opcjonalny, **tylko** po walidacji ograniczeń okien i bezpiecznego zapisu |

Metryki: `net_cost_dkk`, eksport PV kWh, ograniczona produkcja PV (jedynie przy wiarygodnych danych), import/eksport baterii, osiągnięty SOC, nieosiągnięte zadane moce, ilość zapisów na dobę, liczba niespełnionych ograniczeń i ryzyko powtórzenia planu po zaniku HA. Brak danych potrzebnych do wiarygodnego porównania = **wynik nieznany**, nie 0 DKK.

## 8. Scenariusze odbioru — fikcyjne encje HA

- `CTRL-01`: spot PV wysoki rano, niższy w południe, wystarczająca prognoza PV → current-first może wybrać niski limit prądu ładowania rano i większy w południe; nie wpisuje na stałe 5/50 A.
- `CTRL-02`: przy dostępnej energii, wolnej pojemności baterii i braku ostrzejszych ograniczeń nastawa 5 A ogranicza ładowanie do 5 A (około 0,28 kW DC przy 56 V); przy niedoborze PV lub limicie BMS faktyczny prąd może być mniejszy, **bez oznaczania tego jako błędu dokładności falownika**. Eksport nadwyżki zależy od zezwolenia eksportu.
- `CTRL-03`: ogólny limit ładowania 5 A, limit grid charge 50 A → dostępny limit ładowania sieciowego jest co najwyżej 5 A; nie 50 A.
- `CTRL-04`: ogólny limit 50 A, limit grid charge 5 A → ładowanie PV może korzystać z ogólnego limitu 50 A; ładowanie z sieci nie przekracza limitu 5 A.
- `CTRL-05`: grid charge globalnie ON, ale brak zezwolenia dla aktywnego TOU → samo 50 A na encji prądu nie jest dowodem wykonalnego ładowania z sieci.
- `CTRL-06`: żądanie minimalnego SOC 75% w obecnej konfiguracji TOU 20%, brak sterowania dynamicznym minimum → raport `missing_capabilities`, nie fikcyjne gwarantowane 75%.
- `CTRL-07`: poranny limit PV 5 A i utrata HA przed południem → limit zostaje 5 A; symulacja uwzględnia opóźnienie/stratę ekonomiczną, nie symuluje automatycznej zmiany do 50 A.
- `CTRL-08`: zezwolenie na ładowanie z sieci uzależnione od przyszłego OFF w HA, brak sprzętowego stopu → działanie wykonawcze zablokowane, choć plan może wskazywać korzyść.
- `CTRL-09`: zamiana slotów 23:30→00:00 i następnego 00:00→05:00 z nieustalonym formatem → dynamiczny zapis TOU zablokowany; nie zakładać poprawnej obsługi granicy doby.
- `CTRL-10`: siedem zmian ekonomicznie uzasadnionych w dobie → nie przypisywać ich automatycznie sześciu TOU; porównać dokładność obecnej konfiguracji current-first i możliwej kompresji.
- `CTRL-11`: usługa HA ustawiła limit, ale PV jest niedostępne albo SOC wynosi 100% → **nastawa jest przyjęta, lecz nie wymusza przepływu**; brak ładowania nie stanowi błędu wykonania. Osobno: jeśli w warunkach umożliwiających ładowanie nowy limit został przekroczony lub odczyt nastawy się nie zmienił, zgłosić niespójność.
- `CTRL-12`: dodatnia cena sprzedaży PV **poniżej 0,40 DKK/kWh** → automatyczne zezwolenie OFF nawet przy pełnej baterii; przy cenie powyżej progu brak fizycznej separacji baterii blokuje niebezpieczną akcję live, lecz nie symulację.
- `CTRL-13`: istniejące osierocone encje `battery_controller.*` → ignorowane jako źródła, sterowania i blokady.
- `CTRL-14`: current-first i TOU mają te same koszty netto w granicach niepewności **prognoz i kosztów**, nie niepewności precyzji wykonania nastawy; current-first wymaga mniej trwałych zmian → preferować current-first.
- `CTRL-15`: próba aktualizacji sześciu TOU kończy się na trzecim polu → brak raportu `success`, procedura przetestowanego odzyskiwania, brak nowych kroków.
- `CTRL-16`: znany model pokazuje, że current-first nie może zapewnić docelowego SOC przed nocą, a TOU może; raportować brakującą zdolność i potencjalny zysk TOU **bez** samoczynnego włączenia TOU.

**Warunek przekazania programiście:** każdy wariant symulacji musi podawać oddzielnie `intent`, `HA_setpoint`, `expected_physical_effect`, `measured_effect` (gdy jest), `plan_feasibility` i `reason`. Nie przeliczać zysku idealnego dispatchu na wykonywalne oszczędności.


---

## CURRENT CONTROLLER MODEL


**Status:** normatywny algorytm translacji intencji ekonomicznej na istniejące **encje Home Assistant**. Brak dostępu do Modbus i brak modyfikacji ESPHome. Wszystkie testy w tym dokumencie są **fiksturami symulacji**, nie testami wykonanymi na falowniku.
Powiązania: [CONTROL_STRATEGY.md](EXECUTION.md), [ENTITY_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION.md), [EXECUTION_CONTRACT.md](EXECUTION.md), [DECISION_LOGGING.md](VALIDATION.md).

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
- Co-Pilot używa ceny zakupu **wprost** z `sensor.energi_data_service` oraz ceny sprzedaży **wprost** z `sensor.energi_data_spotpris`, bez liczenia prowizji i taryf. Eksport PV przy cenie z HA co najmniej 0,40 DKK/kWh; [PV_EXPORT_POLICY.md](EXECUTION.md).

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

1. Zbierz opublikowane ceny zakupu i sprzedaży, prognozy PV/zużycia, SOC, napięcie, moce i aktywny okres TOU. Źródła i ich aktualność zgodnie z [ENTITY_CONTRACT.md](HA_CONTRACT.md).
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

Każda decyzja powinna zawierać: `decision_id`, slot UTC, ceny końcowe kupna i netto sprzedaży, dostępne PV, dom, SOC, napięcie baterii, aktywny TOU, proponowany limit A (wartość/krok), oczekiwany przepływ DC/AC, przewidywany koszt i alternatywę, czas ważności oraz przyczynę wyboru. Oddzielny wpis `command_applied` i `physical_observation` tylko po rzeczywistych działaniach. Więcej: [DECISION_LOGGING.md](VALIDATION.md).

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
- `CUR-15`: zakup i sprzedaż pobierane z odpowiednich encji HA bez jakichkolwiek korekt; żadnych prowizji ani taryf w Co-Pilot; próg PV export 0,40 DKK/kWh według [PV_EXPORT_POLICY.md](EXECUTION.md).
- `CUR-16`: wariant z wyższą ceną sprzedaży rano, ale niepewną jutrzejszą PV i dynamicznym celem SOC → algorytm optymalizuje cały horyzont, nie sztywną regułę „rano 5 A, w południe 50 A”.
- `CUR-17`: eksport PV wyłączony, bateria pełna → zmniejszenie prądu ładowania nie tworzy przychodu, a może skutkować ograniczeniem PV.
- `CUR-18`: przy awarii HA plan `grid_charge` wymagający przyszłego wyłączenia jest zablokowany bez niezależnego sposobu zakończenia, mimo dodatniego zysku prognozy.
- `CUR-19`: brak aktywnego `battery_controller.*` → osierocone encje historyczne ignorowane, nie tworzyć konfliktu.
- `CUR-20`: odwrócone źródło limitów PV/grid charge w mapowaniu → testy asercji ról HA nie pozwalają zamienić encji ładowania ogólnego z sieciowym.

**Warunek przekazania Codexowi:** każda testowana nastawa musi przejść kontrolę jednostek A↔kW, bilans SOC i energii, znane ograniczenia bieżącego TOU oraz rejestr decyzji. Dla wariantów bez danych fizycznych raportować `simulation_assumption`, nigdy `physically_verified`.


---

## PV EXPORT POLICY


**Status: decyzja użytkownika 20.10.2026.** Obowiązuje w projekcie; nie trzeba ponownie pytać o znaczenie ceny ani wysokość progu. Wdrożenie sprzętowe nadal wymaga ukończenia fazy monitor/dry-run i zatwierdzenia uruchomienia automatyki.

## 1. Ceny bez jakichkolwiek przeliczeń

**Użytkownik jednoznacznie ustalił:** Co-Pilot pobiera ceny dokładnie takie, jakie dostarcza HA, i **nie zajmuje się prowizjami, podatkami ani taryfami**. Dlatego:

```text
C_buy[t]      = sensor.energi_data_service.attributes.raw_*.price[t]
C_sell_net[t] = sensor.energi_data_spotpris.attributes.raw_*.price[t]
```

- Oba szeregi `raw_today/raw_tomorrow` wchodzą do planera **bez zmian wartości**.
- Co-Pilot nie prowadzi kalkulacji składników ceny, nie odejmuje i nie dodaje żadnych opłat.
- `current_price` służy do diagnostyki bieżącej ceny; różnica jego precyzji względem listy godzinowej nie jest powodem przeliczenia cen.

## 2. Cena minimalna i decyzja switch

**Konfigurowalna wartość początkowa:** `min_pv_export_price_dkk_kwh = 0.40` (DKK/kWh z encji HA, bez przeliczeń).

**Zasada podstawowa** (warunki dla decyzji na podstawie opublikowanej ceny bieżącej):

| Cena eksportu netto | Zezwolenie na eksport PV przez `switch.sun12k_solar_sell` |
| --- | --- |
| `C_sell_net < 0.40` | **OFF** — nie sprzedawać PV za cenę poniżej minimum |
| `C_sell_net >= 0.40` | **ON / eksport dozwolony**; planner może wykorzystać PV także na dom lub ładowanie baterii |

`ON` jest **zezwoleniem**, nie poleceniem wysłania całej nadwyżki PV na sprzedaż; przy cenie powyżej minimum Co-Pilot nadal optymalizuje magazynowanie, autokonsumpcję i eksport zgodnie z kosztem energii w całym znanym horyzoncie. `OFF` może powodować curtailment, gdy bateria jest pełna, co należy logować i uwzględnić w prognozie potencjalnej PV.

**Histereza cenowa:** nie dodawać arbitralnego marginesu cenowego modyfikującego próg (użytkownik podał dokładnie 0,40). Ograniczyć powtarzane zapisy tylko przy zmianie faktycznego stanu oraz stosować walidację świeżości/ważności ceny i potwierdzenie wykonania. Jedna stawka godzinowa nie powinna powodować zapisu co 15 minut bez zmiany decyzji.

### Warunek danych i utraty łączności

Próg 0,40 DKK/kWh oznacza cenę z HA. `raw_*.price` bywa zaokrąglone, a `current_price` dokładniejsze: jeśli oba aktualne odczyty prowadzą do **innej** decyzji przy progu, zastosuj `PRICE_THRESHOLD_AMBIGUOUS` i nie wydawaj komendy ON ([HA_PRICE_SERIES_CONTRACT.md](HA_CONTRACT.md)). Nie przesuwaj progu histerezą.

Po utracie HA, internetu albo źródła cen przełącznik Deye może pozostać **ON** i nadal eksportować w następnej godzinie poniżej progu. **Użytkownik 20.10.2026 zaakceptował utrzymanie ostatnich nastaw, także ryzyko ekonomiczne.** Nie wymagać osobnego sprzętowego wyłącznika wyłącznie po to, by zagwarantować próg cenowy podczas awarii. Nadal obowiązuje fizyczna separacja od eksportu baterii, zabezpieczenia Deye/BMS i odzyskanie stanu po ponownym połączeniu. Brak ceny: **bez nowych poleceń** oraz alarm, nie fałszywy komunikat „eksport bezpiecznie wyłączony”.

## 3. Autonomia i uprawnienia

- Użytkownik **upoważnił Co-Pilota do samodzielnego podejmowania decyzji o eksporcie PV**; docelowy wykonawca używa `switch.sun12k_solar_sell` przez usługę HA `switch.turn_on`/`switch.turn_off`, bez ręcznej zgody na każdy slot.
- Ta autonomia **nie oznacza zgody na celowe eksportowanie energii z baterii**. Taki eksport nadal wymaga osobnej, ważnej zgody na dany plan, limit i czas.
- **Potwierdzenie użytkownika 20.10.2026:** w obecnej konfiguracji `switch.sun12k_solar_sell` zezwala wyłącznie na eksport nadwyżki PV, natomiast sprzedaż z baterii jest wyłączona. Jest to stan konfiguracji, nie niezależna gwarancja dla innych nastaw TOU. Przed aktywacją zapisów live zweryfikować fizycznie separację oraz zachowanie ON/OFF; przy zmianie nastaw mogących włączyć eksport baterii wymagane ponowne sprawdzenie. Brak takiej weryfikacji ogranicza funkcję wykonawczą, ale **nie unieważnia reguły biznesowej**.
- Deye **zachowuje ostatnie nastawy po awarii HA**. Dla `OFF` jest to przede wszystkim ryzyko ekonomiczne (utracony eksport), dla `ON` trzeba uwzględnić możliwość przepływu z baterii przy innych nastawach TOU. Przed automatycznymi zapisami obowiązuje kontrakt bezpieczeństwa [EXECUTION_CONTRACT.md](EXECUTION.md).
- **Zgoda na autonomię projektową nie jest poleceniem wykonania teraz usług na HA**. Monitor/dry-run mogą od razu symulować tę politykę; fizyczny executor włączamy tylko po odrębnej zgodzie na uruchomienie i testach P0.

## 4. Wykorzystanie w modelu

W bazowym optymalizatorze MPC przy `C_sell_net < 0.40` obowiązuje `s_x=0` dla automatycznego eksportu PV; w `C_sell_net >= 0.40` jest dopuszczony przepływ `s_x>=0`, z fizycznymi limitami i ekonomiczną optymalizacją. Jeśli PV nie może zostać zużyte lub przyjęte do baterii przy wyłączonym eksporcie, jawnie wykazać `s_c` jako ograniczoną produkcję **tylko w symulacji i w granicach wiarygodnej prognozy**; nie uznawać prognozy minus produkcja za zmierzony curtailment.

W backtestach i baseline obowiązuje **ten sam próg i jednostki polityki Co-Pilot**, ale strategia porównawcza bazowa może utrzymywać inne, rzeczywiście istniejące ustawienia Deye; nie narzucać jej nowych reguł po fakcie. Log decyzji ma pokazać `sell_price_now`, próg 0,40, `pv_export_allowed`, proponowany przełącznik, status wykonania i koszt alternatywny braku eksportu. Zapisać powód `PV_EXPORT_BELOW_MIN_PRICE` / `PV_EXPORT_ALLOWED`.

## 5. Testy akceptacyjne — specyfikacja (nie wykonano)

- `PVE-01`: stawka encji spot 0,399 DKK/kWh → PV export OFF.
- `PVE-02`: stawka dokładnie 0,400 DKK/kWh → PV export ON (zezwolenie).
- `PVE-03`: stawka 0,401 DKK/kWh → PV export ON.
- `PVE-04`: 0,400 w encji HA → Co-Pilot przyjmuje 0,400 bez korekt; eksport PV dozwolony.
- `PVE-05`: 1,922 w `raw_today` → cena sprzedaży 1,922, bez dodatkowych działań.
- `PVE-06`: cena zakupu 2,406 z `energi_data_service` → 2,406 końcowo, bez ponownego naliczania taryf.
- `PVE-07`: 0,20 poniżej minimum, PV=3 kW, dom=1 kW, bateria pełna → `solar_sell` OFF; plan nie zapisuje 2 kW jako rzeczywistego eksportu.
- `PVE-08`: cena 0,80, PV=3 kW, dom=1 kW, bateria może się ładować → eksport dozwolony, ale wybór magazynowania/eksportu zależy od pełnego planu.
- `PVE-09`: cena poniżej progu, Deye przełącznik już OFF → brak powtórnego zapisu.
- `PVE-10`: cena powyżej progu, Deye przełącznik już ON → brak powtórnego zapisu.
- `PVE-11`: przejście z 0,39 na 0,41 → jedna zamierzona zmiana OFF→ON, o ile istnieje live approval i kompletne warunki wykonawcy.
- `PVE-12`: nieznana/stara cena lub `raw_today` z luką → nie wydawać automatycznej komendy przełącznika, zgłosić brak danych.
- `PVE-13`: wysoka cena eksportu i SOC pozwala na rozładowanie do domu, lecz brak zgody na eksport baterii → brak planowanego `b_x`, także gdy `solar_sell=ON`.
- `PVE-14`: `switch.sun12k_solar_sell` ON bez zweryfikowanej fizycznej separacji od eksportu baterii → brak zezwolenia na ryzykowny zapis w live; monitor/dry-run nadal pokazują decyzję polityki.
- `PVE-15`: HA przerwany po ustawieniu OFF → diagnostyka możliwej utraty eksportu, bez fikcyjnego twierdzenia, że Deye automatycznie włączy go ponownie.
- `PVE-16`: ceny na jutro nieopublikowane → nie programować jutra arbitralną ceną; replan dopiero po otrzymaniu prawidłowych cen.
- `PVE-17`: piętnaście minut po poprzedniej decyzji cena i stan pozostają identyczne → zero zbędnych zapisów switch.
- `PVE-18`: aktywny przyszły slot ma cenę sprzedaży 0,35 i sam PV mógłby przynieść przychód → zakaz eksportu zgodnie z **wybranym przez użytkownika progiem**, mimo dodatniej ceny.
- `PVE-19`: cena −0,10 → eksport OFF, cena pozostaje −0,10 bez obcinania do zera.
- `PVE-20`: dobrowolny ręczny tryb `monitor/dry_run` → propozycja ON/OFF i log, **bez** wywołania usługi HA.
- `PVE-21`: `raw_today.price=0,400` i potwierdzony bieżący `current_price=0,3996` → `PRICE_THRESHOLD_AMBIGUOUS`, brak komendy ON; test włącznego progu tylko przy zgodnych odczytach.
- `PVE-22`: przełącznik pozostał ON po utracie HA i w kolejnej godzinie cena spadła do 0,20 → stan ryzyka, bez fałszywej gwarancji OFF; po odzyskaniu HA wymagane sprawdzenie obecnego stanu i ceny przed dalszymi akcjami.

**Warunek odbioru:** testy sprawdzają użycie **niezmienionej ceny z HA** i autonomię tylko dla PV. Nie implementować żadnego rozliczania prowizji, podatków, taryf ani innych korekt cenowych.
