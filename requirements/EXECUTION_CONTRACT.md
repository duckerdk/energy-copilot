# Kontrakt wykonawcy poleceń Home Assistant

**Status:** dokumentacja projektowa. Uruchomienie rzeczywistych zapisów wymaga zamknięcia P0 w [OPEN_ITEMS.md](OPEN_ITEMS.md). Powiązania: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [ARCHITECTURE.md](ARCHITECTURE.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md).

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
| `automatic_non_export` | Tylko potwierdzone bezpieczne funkcje nieeksportujące baterii po P0 |
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

Działanie złożone wymaga potwierdzenia, że **zestaw** akcji rzeczywiście realizuje zamierzony przepływ. `charge_power_kw = 2` nie może zostać „zrealizowane” samym włączeniem przełącznika grid charge. Podobnie globalne zezwolenie na eksport nie dowodzi bezpiecznego rozdzielenia PV i baterii.

### Własne granice prądu Energy Co-Pilot

Dla trzech regulatorów Deye executor stosuje **twarde zakresy polityki użytkownika** (włącznie): `number.sun12k_maximum_battery_charge_current` **0–50 A**, `number.sun12k_maximum_battery_discharge_current` **0–100 A**, `number.sun12k_maximum_battery_grid_charge_current` **0–50 A**. HA reklamuje błędne metadane ±16 777 220 A — **nie** wolno ich używać do wyznaczenia granic. Pełna tabela: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md#limity-prądów-ustalone-przez-użytkownika--obowiązujące-dla-energy-co-pilot).

- Limity dotyczą docelowych wartości parametrów *prądowych* w A; nie zastępują limitów BMS, mocy falownika, temperatury ani definicji źródła ładowania.
- Każda żądana nastawa spoza przedziału jest **odrzucana** i logowana z kodem `CURRENT_LIMIT_OUT_OF_RANGE`. Nie robić cichego `clamp` i nie wysyłać polecenia.
- `0 A` jest dozwolone w polityce, ale dopóki nie zweryfikowano skutku fizycznego wartości 0 i jej dopuszczalności przez Deye, **nie wysyłać** jej do urządzenia. „Zero” nie oznacza automatycznie „wyłącz ładowanie”.
- Przed zmianą prądu moduł musi mieć status `validated_write`, potwierdzoną jednostkę, bezpieczne wartości, pomiar zwrotny i sposób wyjścia. Żadne z tych ograniczeń nie aktywuje automatyki samo.
- Encje `battery_controller.*` są zgodnie z wyjaśnieniem użytkownika osieroconymi pozostałościami i **nie służą do blokowania** Energy Co-Pilot, rozpoznawania konfliktów ani wyznaczania nastaw. Jedynie realnie zaobserwowany inny aktywny wykonawca może stanowić konflikt.

### Backend wykonawczy current-first i istniejący TOU

Projektowy kanał bieżących korekt to natywne usługi HA do encji limitu prądu baterii; szczegóły [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md). To **górny limit**, nie polecenie dokładnej mocy. Aktywne TOU pozostaje w stanie zastanym; jego aktualny okres i SOC ograniczają realną wykonalność intencji. Osobna operacja ładowania z sieci wymaga warunków globalnego Grid Charge, limitu ogólnego, limitu sieci i zgody Grid Charge w TOU. Zmiana wyłącznie limitu w A **nie** jest gwarancją ładowania.

Urządzenie utrzymuje ostatnio zapisane nastawy po utracie HA. Nie uruchamiać operacji wymagających przyszłej komendy `OFF` jako jedynej bariery bezpieczeństwa; zwłaszcza nieplanowanego długotrwałego grid charge lub eksportu baterii. **Bezpieczny fizycznie limit prądu** i **ekonomicznie optymalna nastawa na dany kwadrans** to różne właściwości. Po restarcie konieczny nowy odczyt i plan, a nie odtworzenie dawnego polecenia.

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

## 7. Anulowanie, konflikt, restart i awaria

| Zdarzenie | Działanie |
| --- | --- |
| Nowy `plan_id` przed akcją | Odrzuć starą akcję i przelicz warunki; stara zgoda na sprzedaż nie przechodzi do nowego planu |
| Nowy plan w trakcie operacji | Zatrzymaj dalsze kroki, zweryfikuj skutek ostatniego i zastosuj przetestowaną procedurę bezpiecznego wyjścia |
| Dane `unknown` / `unavailable` / przeterminowane | Zakaz nowych poleceń; aktywny tryb kończyć tylko zweryfikowaną procedurą |
| Usługa zwróciła sukces, brak efektu w pomiarach | `failed` lub `uncertain`; nie oznaczać jako sukces |
| Inna automatyzacja zmieniła nastawę | Zgłoś konflikt i `blocked`; nie walcz z nią ciągłym nadpisywaniem |
| Restart HA lub integracji | Najpierw odczyt i uzgodnienie stanów; bez odtwarzania poprzedniej aktywnej akcji ani poprzedniej zgody |
| Wyłączenie/odinstalowanie | Wstrzymaj nowe akcje; nie twierdź, że urządzenie wróciło do normalnego trybu bez fizycznego dowodu |
| Awaria całego HA/Wi-Fi | Wymaga uprzednio sprawdzonego **niezależnego** fail-safe urządzenia; jeśli go brak, automatyka jest niedopuszczalna |

**Kluczowe:** brak nowych poleceń NIE wyłącza utrzymanej w falowniku nastawy. Przed automatyzacją trzeba wykazać bezpieczne zachowanie każdego aktywnego trybu także bez HA. Standardowej konfiguracji falownika ani działania resetu nie wolno zgadywać.

Przycisk STOP w HA wstrzymuje nowe akcje i może użyć **tylko sprawdzonej** procedury zatrzymania. Nie jest sprzętowym wyłącznikiem awaryjnym. Obsługa ponownego uruchomienia po awarii wymaga rekoncyliacji, a nie bezwarunkowego wznowienia.

**Audyt:** wszystkie walidacje, próby wywołania HA, potwierdzenia fizyczne, błędy i anulowania powiązać przez `action_id` z `decision_id` i `plan_id` w [DECISION_LOGGING.md](DECISION_LOGGING.md). Nie logować samej zmiany encji jako potwierdzonego fizycznego rezultatu.

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
