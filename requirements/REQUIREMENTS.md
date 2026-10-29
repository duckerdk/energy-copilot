# Energy Co-Pilot — decyzje i wymagania (jedno źródło prawdy)

## Cel
Minimalizować **całkowity koszt energii w DKK w pełnym horyzoncie opublikowanych cen**: import minus przychód eksportowy + degradacja baterii, z uwzględnieniem sprawności, niepewności i wartości końcowego SOC. **Autokonsumpcja nie jest osobnym priorytetem**. Można kupować energię z sieci mimo dostępnej baterii, jeśli poprawia to wynik całego planu. Nie stosować sztywnego docelowego SOC ani reguły „najpierw PV/bateria”.

## Instalacja
- Home Assistant na VM; natywna integracja docelowo `custom_components/energy_copilot`. Dane i sterowanie **wyłącznie przez istniejące encje/usługi HA**. Bez własnego Modbus, zmian ESPHome, firmware, zewnętrznego serwera albo LLM w pętli sterowania.
- Deye SUN-12K-SP04LP3-EU; połączenie istniejącym ESPHome/ESP32; 2 × BSLBATT 51,2 V / 100 Ah / 5,12 kWh = 10,24 kWh nominalnie. Instalacja PV 8,4 kWp, wejścia DC PV1/PV2. Region Dania DK1.
- **Twarde minimum SOC 20%**, maksymalnie 100%; wyższe ograniczenia BMS/urządzenia mają pierwszeństwo. 8,192 kWh pomiędzy 20–100% to wartość nominalna, nie użyteczna energia AC.
- Model uwzględnia dopuszczalną moc ładowania baterii **do 50 A** i z sieci **do 50 A** jako techniczną granicę symulacji, NIE jako polecenie nastawy. **`Maximum Battery Discharge Current` jest całkowicie poza zakresem Energy Co-Pilot:** żadnych odczytów, zapisów, weryfikacji, statusów, diagnostyki ani użycia tej nastawy jako parametru ograniczającego planer; zarządza nią wyłącznie falownik/BMS. Zaobserwowano, że fizyczne ustawienie 0 A zatrzymuje PV — integracja nie próbuje go odczytywać ani naprawiać. Sprzętowe zabezpieczenia pozostają po stronie falownika/BMS. Użytkownik potwierdził działanie zadawania prądów ładowania.
- Użytkownik akceptuje **utrzymanie ostatnich nastaw falownika po awarii HA**, także możliwy koszt ekonomiczny. Nie zwalnia to z fizycznych ograniczeń bezpieczeństwa i ważności zgody na eksport baterii.

## Ceny i polityka ekonomiczna
- Zakup: `sensor.energi_data_service`. Sprzedaż: `sensor.energi_data_spotpris`. `raw_today/raw_tomorrow[*].price` używać **bez naliczania lub odejmowania podatków, taryf czy prowizji**; `current_price` może mieć inną dokładność. Obie wartości DKK/kWh.
- Minimalna cena autonomicznego **eksportu nadwyżki PV**: **0,40 DKK/kWh** włącznie. Poniżej: `switch.sun12k_solar_sell` OFF; przy/ponad: ON może zezwolić na eksport, ale nie wymusza jego ilości. Przy sprzecznych cenach z powodu zaokrąglenia nie włączać eksportu i zgłosić niejednoznaczność.
- **Stała degradacja baterii 0,40 DKK/kWh energii rozładowanej na DC**, naliczona **raz** przy rozładowaniu. Przy decyzji zakupowej na przyszłe ładowanie uwzględnić koszt przewidywanego rozładowania. To polityka użytkownika, nie empiryczny pomiar degradacji i nie próg eksportu PV.
- Straty konwersji odzwierciedlać w bilansie energetycznym, **nie naliczać ich dwukrotnie jako opłaty**. Sprawności 0,9487 i 0,97 w starych danych były jedynie założeniami, nie pomiarem. Cena nabycia baterii 19 000 DKK nie jest dodatkowym kosztem dziennego planu.
- Brak sztywnej rezerwy blackout. Dynamiczny cel SOC jest rezultatem optymalizacji z minimalnym 20%, a nie ustawionym na stałe procentem.
- **Pełna energia w szczycie:** nie racjonować rozładowania do arbitralnego udziału energii na każdy kwadrans; przy wysokich cenach dostępne jest całe dopuszczalne energetycznie rozładowanie, zgodnie z planem i dolną granicą SOC. Nastawy SOC w TOU zmieniać w kroku **1%**, nie 5%.
- **Jedyna dopuszczalna przyczyna regulacji prądów ładowania:** (1) świadome przesunięcie ładowania z PV na późniejszy przedział lub (2) rozciągnięcie ładowania (w szczególności z sieci) na dłuższe korzystne okno. Żaden inny cel — zgodność z prognozowanym poborem, planowaną mocą, planowanym SOC, kompensacja niskiej PV, wysoki SOC ani sama flaga Solar Sell — nie uprawnia planera ani wykonawcy do zmiany prądu. Bez jednego z tych celów **brak jakiegokolwiek nowego zapisu prądu**. Po zakończeniu uzasadnionego czasowego ograniczenia przywracać udokumentowaną wcześniejszą nastawę, także po restarcie, wyłącznie gdy wiadomo, że ograniczenie wprowadziła integracja i odtąd nie zostało zmienione zewnętrznie. W żadnym przypadku prognozowany SOC nie jest ograniczeniem ładowania rzeczywistej nadwyżki PV do 100%. Nie inicjować kosmetycznego sieciowego doładowania 99→100%.

## Uprawnienia
- **Autonomiczne**: celowe zmiany limitów prądu **ładowania** (nie rozładowania), ładowanie z sieci (Grid Charge), modyfikowanie wszystkich **sześciu okresów TOU**, zezwolenie na eksport **PV** po uruchomieniu live. Każdorazowa zgoda na te operacje nie jest potrzebna; wdrożenie live wymaga walidacji i świadomego włączenia.
- W trybie automatycznym Co-Pilot jest **nadrzędny względem zwykłych ręcznych zmian nastaw**: przy kolejnym planie może je nadpisać. **STOP, wyłączenie automatyki, ograniczenia bezpieczeństwa i zgody mają pierwszeństwo**; zakaz pętli natychmiastowych nadpisań.
- `switch.sun12k_solar_sell` w **obecnej konfiguracji** pozwala wyłącznie na eksport nadwyżek PV; sprzedaż baterii jest wyłączona (potwierdzone przez użytkownika). Nie zakładać, że dowolna przyszła zmiana TOU nigdy tego nie naruszy.
- **Eksport z baterii zachować jako funkcję opcjonalną**; każda konkretna propozycja wymaga jawnej osobnej zgody, określającej plan, okres i limit kWh. Domyślnie zablokowany.
- Faza początkowa `monitor/dry_run`: zero zapisów do urządzenia. Przejście do live jest osobną decyzją; bezpieczeństwo wykonania: [EXECUTION.md](EXECUTION.md).

## Autostart, recovery i dziennik — decyzja użytkownika 28.10.2026

- W trybie `automatic` wykonawca jest domyślnie **ARM po uruchomieniu HA i po przeładowaniu integracji**. Tryby `monitor`/`dry_run` pozostają bez zapisów. Ręczny STOP zatrzymuje dalsze polecenia w bieżącej sesji; nie jest fizycznym wyłącznikiem awaryjnym.
- Chwilowy brak poprawnego pomiaru, prognozy albo wykonalnego planu **blokuje wyłącznie nowe zapisy**, nie zmienia intencji ARM i powoduje automatyczne wznowienie po ponownej walidacji. Nie używać poprzedniego, przeterminowanego kwadransa jako zastępczej komendy. Gdy zapis do urządzenia mógł zostać częściowo wykonany, blokada `recovery_required` wymaga dodatkowej ostrożności; nie wolno ślepo ponawiać niepewnego zapisu.
- Prowadzić trwały lokalny dziennik błędów, przyczyn blokady/odzyskania i decyzji `idle`, `grid_import`, `grid_charge`, `battery_discharge` i `pv_charge`; dołączać plan i kwadrans, źródła, ceny, SOC, koszty oraz rozdzielenie `planned`/`applied`. Przechowywać historię między restartami, z retencją 30 dni i ograniczeniem liczby zdarzeń; udostępniać ją w diagnostyce HA. Nie traktować wyniku optymalizatora jako dowodu fizycznego uzyskania zamierzonego przepływu.

## Polityka ujemnych chwilowych odczytów domu — decyzja użytkownika 20.10.2026

- `sensor.home_energy_consumption` jest szablonowym bilansem `PV + grid + battery`, a nie niezależnym licznikiem AC. Użytkownik potwierdził krótkie, sekundowe ujemne piki m.in. podczas przełączania źródeł PV/bateria i dużych skoków mocy; możliwe są przesunięcia czasowe aktualizacji Modbus. **Decyzja: do obliczeń w Energy Co-Pilot każdą skończoną, liczbową ujemną moc domu normalizować do 0 W, także w historii Recorder (15-minutowej integracji energii).** Sam czujnik HA, jego surowe dane i ESPHome pozostają bez zmian.
- **Nie przerabiać braków danych na zero:** poza jawnym wyjątkiem dla nocnych brzegów prognozy Forecast.Solar potwierdzonych zerem mocy na wschodzie/zachodzie słońca, `unknown`, `unavailable`, błędna jednostka, brak źródła PV/grid/battery, niezaufany stan szablonu podczas awarii źródła lub nieudokumentowana luka Recorder nadal oznaczają brak/niepewność danych, a nie 0 W. Normalizację wartości ujemnej wolno zastosować tylko w poprawnym kontekście dostępnych źródeł; zachować dotychczasowe zasady jakości dla pozostałych awarii.
- **Nie odrzucać całego 15-minutowego kwadransa tylko z powodu ujemnego piku.** Używać `max(0, P_dom)` w całkowaniu na odpowiednich odcinkach czasowych. Jawnie oznaczać poprawione fragmenty (liczba, łączny czas, udział, ew. wpływ na energię), rozdzielać energię oryginalną od skorygowanej w lokalnym audycie i nie nazywać skorygowanej serii niezależnym, zweryfikowanym pomiarem fizycznym. Nie publikować szczegółowej historii gospodarstwa w domyślnej diagnostyce.
- Polityka eliminuje nieuzasadnione odrzucanie historii z powodu pojedynczych ujemnych pików, **nie udowadnia poprawności fizycznego bilansu DC/AC** ani nie usuwa rozbieżności dodatnich powodowanych asynchronią. Przed M3/M5 ocenić błąd i wrażliwość profilu zużycia.

## Oczekiwany wynik integracji
Natywne encje HA, config/options flow, prognoza PV i zużycia, plan dla opublikowanych cen, wyjaśnienie decyzji i wariantów, przewidywane koszty/straty, stany `planned/applied/confirmed`, dziennik wszystkich decyzji, dashboard i UI zatwierdzania eksportu baterii. Raporty oszczędności rozróżniają wynik modelowany, backtest i rzeczywisty. Wymagania techniczne: [HA_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION.md](OPTIMIZATION.md), [VALIDATION.md](VALIDATION.md).

## Prognoza zużycia — decyzja użytkownika 22.10.2026
Budować prognozę zużycia domu na następne **7 dni** z **ostatnich 45 dni danych HA**, a nie z 365. **Ostatnie 7 dni mają najwyższą wagę, dni 8–14 wagę średnią, 15–45 mniejszą**; uwzględnić bieżącą zmianę nawyków także wtedy, gdy długa mediana pozostaje bez zmian. Rozróżniać dni robocze, wolne i święta, zachować **wykres w HA**. Nie mylić produkcji PV, zakupu z sieci, ładowania/rozładowania baterii ani fizycznego zużycia. Nie zmieniać zakresu uprawnień do sterowania.


## Dynamiczny zapas SOC na błąd prognozy — decyzja użytkownika 29.10.2026

- **Nie stosować stałego +10% ani wymuszenia 100% SOC.** Przed drogimi godzinami rozważyć **dynamiczny dodatkowy zapas 0–15 punktów procentowych SOC** wyłącznie przy potwierdzonym ryzyku niedoszacowania zużycia i ekonomicznej opłacalności wcześniejszego ładowania.
- Ryzyko obliczać z ostatniego, odseparowanego 7-dniowego holdoutu modelu 45-dniowego, szczególnie ze znaku błędu i 75. percentyla niedoszacowań w godzinach 16–22. Nie udawać, że błąd MAE jest prognozowaną dodatkową energią. Bez wystarczających danych, istotnego szczytu cen lub wykonalnego taniego okna: **brak dodatkowego ładowania** i jasny powód w diagnostyce.
- Nadmiarową energię kupować wyłącznie w rozciągniętym na kilka kwadransów oknie, po uwzględnieniu sprawności, degradacji, wartości końcowej SOC i możliwości wykorzystania PV. Wymóg ten nie daje dodatkowych uprawnień do manipulowania prądami: nadal tylko przesunięcie lub rozciągnięcie ładowania.
- Wyraźnie rozdzielać bazową prognozę domu, przyjęty zapas na niepewność, rzeczywiste dodatkowe ładowanie i szacowaną wartość unikniętego ryzyka. Pokazywać prawdziwy plan SOC, nie sztucznie podniesioną linię na wykresie. Pierwsza implementacja korzysta z jawnie oznaczonego, niekalibrowanego współczynnika ostrożności 0,65 i wymaga weryfikacji na żywym HA.

## Pełnohoryzontowy planer energii — decyzja użytkownika 22.10.2026

- Obliczać **cały nieprzerwany okres dostępnych, opublikowanych cen zakupu i sprzedaży**, przy dostępnej prognozie PV i zużycia, a nie pary 15/30-minutowe. Krok kwadransowy pozostaje tylko rozdzielczością bilansu i SOC.
- Wybierać godziny ładowania z sieci, gdy zabraknie korzystnej energii PV, i używać energii baterii podczas droższych godzin. **Dopuszczać kupowanie prądu z sieci mimo niepustej baterii**, jeżeli zachowanie energii na później zmniejsza koszt planu.
- Uwzględniać całe prognozowane PV: pokrywanie domu, magazynowanie nadwyżek, ewentualny eksport nadwyżek i pozostawianie pojemności na zapowiedziane PV. Pozwalać na kilka kolejnych godzin ładowania, rozładowania i powtarzające się cykle, a także świadomy brak cyklu.
- Ograniczenia fizyczne, polityka ceny zakupu/sprzedaży, degradacja 0,40 DKK/kWh DC, SOC min. 20%, eksport wyłącznie PV i sześć TOU pozostają obowiązujące. Model zużycia v1.11.0 **bez zmian**.
- Najpierw wdrożyć model w nieegzekwowalnym `dry_run`, wyraźnie rozdzielić fizyczny harmonogram 15-minutowy od harmonogramu wykonywalnego przez sześć okien TOU. Nie sugerować w HA możliwych do wykonania oszczędności, dopóki nie ma walidacji TOU i rzeczywistego baseline Deye.


## Potwierdzone zachowanie falownika — 23.10.2026

- Utrzymać istniejący priorytet **Load First** oraz **eksport z baterii OFF**. Nie planować zmiany tych nastaw w Co-Pilot.
- Użytkownik potwierdził na instalacji, że falownik **realizuje zadany prąd ładowania** (np. 12 A). Traktować ten fakt jako zweryfikowany w bieżącej konfiguracji, bez ponownego kwestionowania.
- Przy Solar Sell ON falownik sam eksportuje nadwyżkę po obsłużeniu domu i przyjęciu energii przez baterię w granicach zadanej nastawy. Planer określa celowe przesunięcia lub rozciągnięcia ładowania, a nie przestawia prądu na podstawie prognozy; dobiera **zezwolenie Solar Sell według ceny ≥0,40 DKK/kWh**, nie steruje ilością eksportu jako niezależnym poleceniem.
- Planer musi nadal uwzględniać finansową alternatywę sprzedaż–magazynowanie (i koszt późniejszego zakupu), zachowując ochronę przed eksportem z baterii.
