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
| ARM-01 | restart integracji w trybie `automatic` | ARM domyślnie włączony; brak starych komend |
| ARM-02 | przejściowy `Degraded` lub `Blocked`, potem `Valid` + `Preview` | brak nowych zapisów podczas przerwy, ARM zachowany, automatyczne wznowienie |
| ARM-03 | awaria HA API w trakcie zapisu | `recovery_required`; bez ślepego retry |
| LOG-02 | restart HA oraz upływ 30 dni | zachowanie decyzji, przyczyn i kosztów do limitu 6000; retencja |

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

## Odbiór aktualnego M3 — v1.13.0

- [x] Automatyczne regresje `dry_run`: wielogodzinne i wielocyklowe planowanie, 15-minutowy bilans energii bez siatki 0,10 kWh SOC, zachowanie przy drogim/tańszym prądzie, brak nieopłacalnego dodatkowego cyklu.
- [x] Niezależny `simulate_candidate` sprawdza SOC, limity prądu, bilans PV/dom/bateria, brak eksportu baterii i niedozwolonego jednoczesnego importu/eksportu. Testowane również zmienne scenariusze.
- [x] `Solar Sell` planowane na podstawie przyszłej ceny sprzedaży ≥0,40 DKK/kWh, niezależnie od aktualnego stanu przełącznika; raportowane osobno cena zakupu, sprzedaży, przewidywane przepływy i prąd ładowania.
- [x] Jednoznaczne końce okresów `wh_period`, nierówne odcinki Forecast.Solar, potwierdzone zera nocne, źródłowe luki i brak fikcyjnego pokrycia. Recorder i jego braki nie są modyfikowane.
- [x] Historyczna prognoza domu 7 dni, dni robocze, święta i DST; 7-dniowy holdout trenowany bez danych z przyszłości oraz obserwacja później wykonanych kwadransów PV i domu. Wynik stanowi raport błędu, nie fizyczną kalibrację.
- [x] `monitor` i `dry_run` nie wykonują usług HA zapisujących do falownika; błąd planera nie zatrzymuje M1/M2.
- [ ] Potwierdzić powyższe na rzeczywistych danych pracy HA (dzień/noc, różne ceny i pory roku), porównać z **rzeczywistym** baseline Deye oraz skalibrować sprawności i błąd pochodnego pomiaru zużycia.
- [ ] Przed M6 sprawdzić translację fizycznego planu na sześć TOU, wykonanie prądu i niezawodny STOP/recovery; zachować `Load First` i zakaz eksportu baterii. Sam `dry_run` nie oznacza planu wykonalnego.

Otwarte punkty: [OPEN_ITEMS](OPEN_ITEMS.md).

## Natywne logowanie HA — v1.16.9

- W trybie automatycznym wpisy o decyzji, kwadransie, SOC, cenach i akcji muszą trafiać do **Aktywności** przez `logbook_entry` w formacie czytelnym bez JSON.
- Blokada i odzyskanie danych mają widoczne komunikaty; ARM pozostaje aktywny przy przejściowym błędzie.
- Po `applied` log musi rozróżniać rzeczywiście wysłane i potwierdzone nastawy od przypadku zgodności bez zapisu. Nie dodawać ogólnych komentarzy o przepływie energii.
- W **Logach systemowych → Core** ostrzeżenia/błędy trafiają na WARNING/ERROR, pozostałe informacje na INFO w surowym logu; widok skrócony HA pokazuje przede wszystkim ostrzeżenia i błędy.
- Awaria publikacji do Aktywności nie może zatrzymać sterowania ani uniemożliwić archiwizacji technicznej.

## Regresja czytelności — v1.16.10

- W **Aktywności** zdarzenie planowania posiada domenę `energy_copilot` oraz identyfikator encji `Decision journal` z rejestru HA (filtrowanie po urządzeniu); treść uzasadnia akcję.
- `Decision journal` nie przechodzi pomiędzy stanami `planned` i `blocked` (pozostaje `ready`); nie tworzy wtórnych, pozbawionych przyczyny wpisów.
- Dla kupowania energii z sieci zamiast rozładowania pokazać rzeczywisty planowany import, cenę i pierwszy późniejszy kwadrans rozładowania, jeśli istnieje; gdy późniejsza cena jest identyczna, nie twierdzić, że rozładowanie odłożono przez wzrost cen.
- Rozładowanie pokazuje wartość unikniętego zakupu, koszt degradacji i różnicę, o ile dostępne są odpowiednie dane wejściowe. Nigdy nie nazywać tego pełnym kontrfaktycznym wynikiem.
- Blokada pokazuje kod planera przetłumaczony na komunikat i tylko problemy istotne dla sterowania — historyczne ostrzeżenia nie mogą zagłuszyć realnego błędu.
- Zdanie o minimalizacji kosztu horyzontu nie może być jedynym uzasadnieniem decyzji.

## Kontrola dziennika wykonania — v1.16.11

- Test filtrowalnego wpisu `logbook_entry`: `domain=energy_copilot` oraz `entity_id` sensora z rejestru encji, w tym po zmianie jego identyfikatora przez użytkownika.
- Rzeczywiste `preview → blocked` wymaga opisania przyczyny planera i braku nowego planu. `input_quality` wskazuje tylko istotne źródła błędów; poprawna jakość z historycznym ostrzeżeniem nie generuje szumu w Aktywności.
- Wpisy `blocked` i `waiting` wskazują aktualny/następny kwadrans oraz konkretny powód; stałe blokady powodują wpis maksymalnie raz na kwadrans.
- Wykonawca podaje liczbę faktycznych zapisów i wartości przed/po; gdy nastawy są już zgodne, ma `commands_sent=0` i nie przypisuje sobie wykonania polecenia. Po częściowo nieudanym zapisie zawiera wszystkie ukończone zmiany i ostatnią niepotwierdzoną operację.
- Logi nie mogą zawierać obowiązkowego komentarza „Odczyt nastaw nie potwierdza jeszcze rzeczywistego przepływu energii” ani tautologicznego uzasadnienia o minimalizacji kosztu.
- Należy osobno potwierdzić prezentację w rzeczywistym UI użytkownika; CI nie może deklarować takiego odbioru.


## Regresje ekonomicznych uzasadnień — v1.16.12

- Zestawić wynik alternatywnego przeliczenia dla akcji `pv_charge` z osobno uruchomionym `optimize_horizon` na tych samych danych. Potwierdzić prawidłowe uwzględnienie przychodu z eksportu i brak zmiany bazowego dispatchu.
- Zestawić `grid_charge` z najlepszą alternatywą bez ładowania teraz. Dla zerowej różnicy kosztu nie wolno deklarować oszczędności, a przy nieudanym audycie nie wolno zgadywać przyczyny.
- Dla dwukrotnego przeliczenia kwadransa z małą zmianą PV (0,30 → 0,31 kWh) pokazać `Korekta planu` i zmiany SOC/energii; po przejściu granicy kwadransa ponownie `Plan` dla następnego kwadransa.
- Diagnostyczne przeliczenie porównawcze musi być odseparowane od zapisów falownika i mieć ograniczony czas. Dopiero użytkownik może odebrać wynik w rzeczywistej Aktywności HA.


## Regresje sterowania TOU i prądami — v1.16.13

- Dla `grid_import`, `pv_charge`, `battery_discharge`, `grid_charge` **żadnego zapisu** `number.sun12k_maximum_battery_discharge_current` (nawet jeśli aktualna nastawa wynosi np. 2 A). Adapter ma odrzucać zapis tego rejestru w każdej wartości, w tym 0 i 100 A.
- Zastane 0 A discharge powinno zatrzymać wszystkie nowe komendy przed pierwszym zapisem i wskazać kod `controller:discharge_current_zero`. Przy ręcznej korekcie odczytanej na następnym cyklu wykonawca wraca do obsługi planu; sam nie zmienia rejestru.
- Przy SOC 99%, braku ładowania z sieci, TOU SOC = 99% i Grid Charge OFF, bez limitowania discharge. Przy wzroście SOC o 3 pp w tym samym kwadransie próg TOU podąża za SOC; przy rozładowaniu planowany końcowy SOC staje się progiem.
- Gdy plan zawiera ładowanie z sieci oraz wzrost SOC wskutek PV, cel Grid Charge odpowiada tylko energii z sieci, nie całemu planowanemu końcowemu SOC.
- Prądy ładowania PV i z sieci zawsze legalne 1–50 A, wyliczane z kwadransowej energii i zmierzonego napięcia. Przy pierwszym przejściu z 0 A grid (starsza wersja) przywrócić 1 A. Przy Grid Charge OFF i istniejącym legalnym limicie, nie wysyłać zbędnych poleceń.
- Wszystkie inne testy sterowania, blokad, recovery, TOU rollover i logbook bez regresji. Odbiór rzeczywistego zachowania falownika musi wykonać użytkownik na HA, gdyż CI nie ma dostępu do instalacji.


## v1.16.14 — testy tolerancji i prądu

- SOC 99% → 100% przy różnicy modelowej 0,0096 DKK nie uruchamia ładowania z sieci; nie blokować przy tym naturalnego 100% od PV.
- 0,01 DKK = pomijalna różnica, 0,10 DKK do rozpoczęcia kampanii, 0,05 DKK dla jej kontynuacji. Porównanie na całym tanim oknie, bez odkładania pierwszego kwadransa w nieskończoność.
- Pięć godzin zbliżonych cen: bez BOOST na początku, rozłożyć sumę energii, nie naruszając walidatora fizycznego ani limitów prądowych; nie przenosić ładowania przed pierwotny termin.
- Przy SOC 99%, Grid Charge OFF i obecnych limitach 1 A oraz 7 A nie wysyłać żadnej komendy zmiany prądów. Sam Solar Sell ON nie jest wystarczającym uzasadnieniem 1 A.
- Limit dla PV zmieniać na 1 A tylko przy planie: sprzedaż PV teraz + ładowanie później. Przed zakończeniem sterowania przywrócić wcześniej zapamiętane ograniczenie, o ile użytkownik nie nadpisał go ręcznie.
- Limit prądu z sieci zmieniać jedynie przy rzeczywistym rozłożeniu ładowania na kilka tanich kwadransów lub gdy planowane ładowanie wymaga usunięcia zastanego 0 A.
- Sprawdzić HA replay/Lab po dodaniu bool `grid_charge_already_active` do metadanych; testy CI nie zastępują weryfikacji rzeczywistej instalacji.
