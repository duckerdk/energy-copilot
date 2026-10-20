# Strategia sterowania w czasie: prąd baterii kontra TOU Deye

**Status:** decyzja architektoniczna dla Co-Pilot, oparta na obserwacjach użytkownika i istniejących encjach HA. **Nie jest potwierdzeniem fizycznej reakcji urządzenia.** Jest to kontrakt projektowy Codexa, nie instrukcja natychmiastowej zmiany nastaw.
Powiązania: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md), [DECISION_LOGGING.md](DECISION_LOGGING.md), [OPEN_ITEMS.md](OPEN_ITEMS.md).

## 1. Rozstrzygnięcie: dwa poziomy, a nie TOU kontra prąd

**Wariant bazowy do implementacji: sterowanie bieżącym limitem prądu przez encje HA, przy zachowaniu istniejącego harmonogramu TOU w stanie zastanym.** Dynamiczne programowanie sześciu okien TOU to **osobny, opcjonalny backend**, dopuszczalny dopiero po dowodzie przewagi i sprawdzeniu ryzyka. Nie zakładać, że pojedynczy limit prądu zastępuje kontrolę docelowego/minimalnego SOC lub gwarantuje ładowanie z sieci.

- **Planner:** szuka ekonomicznie najlepszego planu w kwadransach na podstawie opublikowanych cen i prognoz; plan jest opisem *celu energetycznego*, nie gotowymi nastawami urządzenia.
- **Translator/current controller:** przekształca plan na **dopuszczalne limity prądowe**. Zgodnie z obserwacją użytkownika falownik **precyzyjnie egzekwuje zapisaną nastawę**; kontrola zwrotna wykrywa jedynie brak dostępnej energii, blokady fizyczne, utratę komunikacji lub zmianę stanu urządzenia, zamiast zakładać losowe błędy wykonania.
- **TOU:** obecny harmonogram pozostaje aktywny/zastany. Nie nadpisywać go „profilami 15-minutowymi”; zapisuje się trwale w falowniku, powtarza się co dobę, ma tylko sześć przedziałów i jest wrażliwy na zazębianie/czas 00:00.
- **Backtester:** odrębnie ocenia idealny plan energetyczny, plan **wykonywalny samą regulacją prądu** przy stałym TOU oraz opcjonalny plan z dynamicznym TOU. Nie raportować oszczędności idealnego planu jako oszczędności osiągalnych.
- **Executor:** zawsze używa wyłącznie encji HA i natywnych usług HA, nigdy bezpośredniego Modbus/rejestrów lub modyfikacji ESPHome.

Wynik: **preferencja current-first**, nie definitywne stwierdzenie, że TOU nie jest potrzebne. Wykorzystanie TOU wynika z *brakującej zdolności i policzonej korzyści*, nie z założenia, że wszystkie harmonogramy należy nadpisywać.

## 2. Potwierdzone obserwacje użytkownika — odróżnić od hipotez

- Przy drogiej sprzedaży PV przed południem użytkownik ograniczał prąd ładowania do ok. **5 A**, a następnie zwiększał go w godzinach tańszej sprzedaży. To jest oczekiwane zachowanie strategii.
- Użytkownik próbował obu regulatorów HA i obserwował, że zmiana jednego z nich nie zawsze dawała efekt.
- W TOU wartość **SOC głównie ogranicza rozładowanie**, a przy zaznaczonym **Grid Charge** wyznacza też poziom ładowania z sieci; **SOC w TOU nie reguluje ładowania z PV**.
- Błędy harmonogramu mogą wynikać z nakładających się przedziałów lub przejścia przez północ.
- Wszystkie nastawy, zarówno z ekranu falownika, jak i z encji HA, **pozostają zapisane w urządzeniu**. Utrata HA nie cofa ich.
- Aktualnie **eksport energii z baterii jest wyłączony**. Nie uznawać tego za gwarancję na przyszłość bez weryfikacji pozycji odpowiedzialnej za eksport.

Projektowo, zgodnie z decyzją użytkownika, przyjmujemy semantykę encji odpowiadającą nazwom; fizyczne potwierdzenie jest osobnym warunkiem aktywacji zapisu.

**Założenie potwierdzone przez użytkownika:** Deye wykonuje ustawione przez encję HA ograniczenie prądu **dokładnie i deterministycznie**, kiedy istnieją warunki do jego wykorzystania. Nie wprowadzać do optymalizatora hipotetycznej losowej niedokładności samego falownika. `maximum_*_current` oznacza **górną granicę**, więc nie można wymusić płynięcia określonego prądu, jeżeli PV, zapotrzebowanie/zezwolenie na ładowanie, SOC, BMS lub napięcie tego nie umożliwiają. To jest **ograniczenie warunków pracy**, a nie kwestia „AI” lub jakości wykonywania poleceń.

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
| Zezwolenie na eksport | `switch.sun12k_solar_sell` | Nie utożsamiać zezwolenia eksportu PV z rozdzieleniem PV/baterii; brak zgody na celowy eksport baterii nadal obowiązuje |

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
7. Dla każdego planu zapisz **oczekiwaną nastawę HA**, powód, cenę zakupu/sprzedaży, oczekiwany kierunek przepływu i brakujące zdolności do [DECISION_LOGGING.md](DECISION_LOGGING.md).
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
- `CTRL-12`: przy dodatniej cenie sprzedaży PV, pełnej baterii i eksporterze PV wyłączonym/braku potwierdzonej separacji baterii → nie zakładać automatycznego, bezpiecznego eksportu PV.
- `CTRL-13`: istniejące osierocone encje `battery_controller.*` → ignorowane jako źródła, sterowania i blokady.
- `CTRL-14`: current-first i TOU mają te same koszty netto w granicach niepewności **prognoz i kosztów**, nie niepewności precyzji wykonania nastawy; current-first wymaga mniej trwałych zmian → preferować current-first.
- `CTRL-15`: próba aktualizacji sześciu TOU kończy się na trzecim polu → brak raportu `success`, procedura przetestowanego odzyskiwania, brak nowych kroków.
- `CTRL-16`: znany model pokazuje, że current-first nie może zapewnić docelowego SOC przed nocą, a TOU może; raportować brakującą zdolność i potencjalny zysk TOU **bez** samoczynnego włączenia TOU.

**Warunek przekazania programiście:** każdy wariant symulacji musi podawać oddzielnie `intent`, `HA_setpoint`, `expected_physical_effect`, `measured_effect` (gdy jest), `plan_feasibility` i `reason`. Nie przeliczać zysku idealnego dispatchu na wykonywalne oszczędności.
