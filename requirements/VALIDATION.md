# Walidacja, kryteria odbioru i testy

**Testy poniżej to wymagania implementacyjne, nie wykonane wyniki.** Cele i decyzje: [REQUIREMENTS.md](REQUIREMENTS.md). Wykonywanie akcji: [EXECUTION.md](EXECUTION.md).

## Poziomy odbioru
- **M1**: poprawny manifest, config/options flow, typed runtime_data, setup/unload, brak wywołań HA zapisujących w stanie monitor/dry-run.
- **M2**: walidacja mapowania encji, próbek, ceny i czasu UTC/DST, Recorder, Forecast.Solar. Dane z brakami muszą mieć status jakości.
- **M3**: deterministyczne scenariusze planera, poprawne obliczenie kosztów, SOC, sprawności, fizycznych przepływów i planu możliwego do wykonania.
- **M4**: HA encje, log decyzji, dashboard, stan STOP, zgody na konkretny eksport baterii, bez wycieków tajnych danych.
- **M5**: powtarzalne testy i backtest `walk-forward`, porównanie z faktycznym baseline; brak danych oznaczyć jawnie.
- **M6**: rzeczywiste akcje wyłącznie po świadomym włączeniu live i osobno zatwierdzonych testach fizycznych. Nie wykonywać ich automatycznie w toku pracy Codexa.

## Regresje obowiązkowe
| ID | Sytuacja | Wynik |
|---|---|---|
| PRICE-01 | surowe ceny today/tomorrow, `tomorrow_valid=false`, DST 23/25h | Tylko opublikowane, kompletne ceny w UTC; żadnych zmyślonych slotów |
| PRICE-02 | `raw_price=0.400`, dokładne `current_price=0.3996` | `PRICE_THRESHOLD_AMBIGUOUS`, brak nowej komendy ON |
| PVE-01 | cena PV 0,399 / 0,400 / 0,401 DKK/kWh | OFF / ON / ON, jeżeli dane zgodne i tryb live zatwierdzony |
| PVE-02 | Solar Sell ON, HA znika, cena następnej godziny niższa | Ostatnia nastawa trwa; zaakceptowane ryzyko ekonomiczne, po powrocie reconcilation |
| MTR-01 | grid +1200/-2470 W, bateria +1000/-1000 W | Poprawny import/eksport i rozładowanie/ładowanie |
| MTR-02 | `home_energy_consumption` ma liczbę z `float(0)` dla niedostępnego źródła | `invalid_input` także historycznie |
| MTR-03 | `sensor.pv_sum=3034 W` | PV DC=3034 W; brak zależności od PV1/PV2 |
| MTR-04 | 15–40s rozrzutu świeżych raportów Modbus, skoki wejść, opóźniony dom | Dom as-of zachowany; różnica czasu raportów sama nie degraduje wejść; rzeczywisty `home_context_lag` nadal ostrzega |
| MTR-05 | Stałe przez wiele godzin PV=0 i dodatnie PV, dom, sieć i bateria | Zachowane bez odrzucenia z powodu wieku stanu; `unknown`/`unavailable` blokują |
| MTR-06 | Awaria i powrót PV/grid/battery, reload/unload | Stary dom blokowany, listener bez wycieku |
| MTR-07 | Syntetyczne 30min odczytów i limity okna | Liczniki przyjęć/odrzuceń i percentyle poprawne, bez surowych W; weryfikacja rzeczywistego okna HA osobno w OPEN_ITEMS |
| PVF-01 | brak/nieznana odpowiedź Forecast.Solar | Diagnostyka, bez wymyślonej prognozy |
| PVF-02 | pełny SOC, Solar Sell OFF, słoneczna pogoda | Brak nauki błędu prognozy z ograniczonej produkcji PV |
| LOAD-01 | historia Recorder z zamaskowanym zerem składowej | Odrzucenie slota z uczenia i backtestu |
| LOAD-02 | ważne liczbowe ujemne home, pozostałe źródła poprawne | `max(0, home)` w bieżących danych i całce odcinkowej; kwadrans zachowany, jawne agregaty czasu/liczby/kWh korekt |
| MTR-08 | Świeży dom zgodny / rozbieżny z sumą PV/grid/battery | Alert `derived_sum_time_uncertain` przy rozbieżności |
| MTR-09 | Wszystkie wymagane i opcjonalne role bez zmian przez 1–48 h | Zachowane z oryginalnym znacznikiem, bez sztucznego heartbeat; nieudostępniona/nieważna wartość odrzucana |
| MTR-10 | `pv_sum` unknown/unavailable i recovery | Nie odzyskiwać danych z zamaskowanego zera |
| QUALITY-01 | wyłącznie historyczne/informacyjne ograniczenia M2 | `Input quality=valid` dla wymaganych bieżących wejść, wszystkie ostrzeżenia zachowane, brak deklaracji gotowości planera |
| DIAG-01 | szczegółowy audyt lokalny zawiera próbki gospodarstwa | domyślny eksport recent/backfill tylko z agregatami, bez `events`, `home_w`, `source_w`; lokalny audyt bez zmian |
| ECON-01 | rozładowanie 2 kWh DC | Degradacja 0,80 DKK, dokładnie raz |
| ECON-02 | tanie ładowanie, przyszłe straty+degradacja przewyższają korzyść | Nie uruchamiać dodatkowego cyklu |
| SOC-01 | plan chce 15% SOC | `not_executable`, minimum 20% |
| CUR-01 | napięcie 56V, limit 5A/50A | Górne granice 0,28/2,8 kW DC, bez gwarancji przepływu |
| CUR-02 | próba 51 A ładowania/101 A rozładowania | Odrzucić, nie przycinać |
| CUR-03 | wymagana energia 0,64 kWh DC, 51,2 V; dostępne 15/30/60 minut | 50/25/12,5 A odpowiednio, bez przekroczenia ograniczeń SOC i prądu |
| CUR-04 | ta sama cena w dostępnych slotach, wariant 50 A i 25 A | Wybrać niższy prąd przy równym koszcie i tej samej dostarczonej energii; droższy wariant nie wygrywa tylko za łagodniejsze ładowanie |
| TOU-01 | potrzeba 7 niezależnych okien, falownik ma 6 | Nie raportować idealnego sterowania 7 oknami |
| TOU-02 | przerwanie zapisu po trzecim polu/00:00 | Nie oznaczać sukcesu, procedura recovery |
| CTRL-01 | ręczna zmiana przy włączonym Co-Pilot | Możliwość nadpisania przy następnym planie, bez pętli |
| CTRL-02 | STOP albo `dry_run` | Zero zapisów |
| EXP-01 | brak zgody na eksport baterii | `b_x=0` i brak sterowania eksportem baterii |
| EXP-02 | zgoda wygasła / limit energii przekroczony / brak niezależnego stopu | Zablokuj eksport baterii |
| EXE-01 | sukces HA API, brak dowodu skutku | `applied`, nie `confirmed` |
| EXE-02 | restart z utrwalonymi nastawami | Odczyt, nowy plan, bez odtwarzania starej komendy |
| LOG-01 | plan `idle`/`blocked` i porównanie alternatyw | Dziennik z cenami, czasem, kosztami, powodem i wersją planu |

## Backtest i wiarygodność oszczędności
Dla okresu t: odtwarzaj tylko opublikowane wtedy ceny i prognozy **sprzed** decyzji, wraz z pierwotnym SOC i ograniczeniami. Porównuj realny baseline Deye z wykonawczą alternatywą Co-Pilot przy tej samej pogodzie, obciążeniu, cenach, stanie baterii i granicach BMS. Pomijaj okresy z niedostępnymi historycznymi składowymi domu i podejrzanym curtailment; raportuj procent pokrycia. Wycena końcowego SOC nie może magicznie zerować pozostałej energii ani posługiwać się nieopublikowanymi cenami. Rozdzielić `simulated`, `backtested` i `observed`; brak testu fizycznego ≠ osiągnięty zysk.

## Audyt decyzji i dashboard
Każde `decision_id`, `plan_id`, start i ważność, dane wejściowe oraz ich wersje i jakość, koszt wariantów, degradację, przestawienie HA i jego rzeczywisty efekt przechowywać w dostępnej do przeszukania formie z ograniczoną retencją. Nie logować sekretów i obszernych surowych serii prywatnych. Pokazywać w HA stan trybu, SOC, bieżące i przyszłe ceny, plan kosztowy, powód wyboru, błędy/STOP oraz formularz konkretnej zgody na eksport baterii. Zmiana planu/warunków unieważnia zgodę.

**Odbiór:** wymienić dokładnie testy uruchomione, testy nieuruchomione, brakujące dowody i zmiany. Nie ogłaszać przejścia M6 po samym zaliczeniu Markdown CI.

## Regresja braku zmian HA
- Wszystkie role pomiarowe, także SOC, dodatnie PV, napięcie/prąd i liczniki dzienne: ważna liczba bez raportu przez 1, 8 lub 48 godzin nie wywołuje sama `Degraded`.
- `unknown`, `unavailable`, `NaN`, błędna jednostka, nieprawidłowy zakres, przyszły czas ponad 10 s: odrzucone również przy starym stanie.
- Awaria i recovery źródła pośredniczącego w bilansie domu: stare numeryczne `home` pozostaje zablokowane do właściwego raportu po odzyskaniu.
- Niespójna opcjonalna kontrola mocy bateria vs. V×I: ostrzeżenie o nieatomowym pomiarze, nie fałszywe `Degraded` głównego odczytu.
- Różne czasy poprawnych raportów nie są błędem synchronizacji. Wykryta awaria/recovery i rzeczywista rozbieżność wartości domu nadal wymagają weryfikacji.
- Brak prognozy w nocy nie degraduje wejść, a brak danych o zmierzchu pozostaje jawny, bez dopisywania Wh.
