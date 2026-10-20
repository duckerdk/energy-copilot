# Energy Co-Pilot — decyzje i wymagania (jedno źródło prawdy)

## Cel
Minimalizować **całkowity koszt energii w DKK w pełnym horyzoncie opublikowanych cen**: import minus przychód eksportowy + degradacja baterii, z uwzględnieniem sprawności, niepewności i wartości końcowego SOC. **Autokonsumpcja nie jest osobnym priorytetem**. Można kupować energię z sieci mimo dostępnej baterii, jeśli poprawia to wynik całego planu. Nie stosować sztywnego docelowego SOC ani reguły „najpierw PV/bateria”.

## Instalacja
- Home Assistant na VM; natywna integracja docelowo `custom_components/energy_copilot`. Dane i sterowanie **wyłącznie przez istniejące encje/usługi HA**. Bez własnego Modbus, zmian ESPHome, firmware, zewnętrznego serwera albo LLM w pętli sterowania.
- Deye SUN-12K-SP04LP3-EU; połączenie istniejącym ESPHome/ESP32; 2 × BSLBATT 51,2 V / 100 Ah / 5,12 kWh = 10,24 kWh nominalnie. Instalacja PV 8,4 kWp, wejścia DC PV1/PV2. Region Dania DK1.
- **Twarde minimum SOC 20%**, maksymalnie 100%; wyższe ograniczenia BMS/urządzenia mają pierwszeństwo. 8,192 kWh pomiędzy 20–100% to wartość nominalna, nie użyteczna energia AC.
- Granice polityki Co-Pilot: prąd ładowania baterii **0–50 A**, rozładowania **0–100 A**, ładowania z sieci **0–50 A**. To granice oprogramowania; BMS i sprzęt mogą narzucać ostrzejsze. Użytkownik potwierdził, że falownik przyjmuje nastawy prądowe i reaguje poprawnie. Nie pytać go ponownie o to samo.
- Użytkownik akceptuje **utrzymanie ostatnich nastaw falownika po awarii HA**, także możliwy koszt ekonomiczny. Nie zwalnia to z fizycznych ograniczeń bezpieczeństwa i ważności zgody na eksport baterii.

## Ceny i polityka ekonomiczna
- Zakup: `sensor.energi_data_service`. Sprzedaż: `sensor.energi_data_spotpris`. `raw_today/raw_tomorrow[*].price` używać **bez naliczania lub odejmowania podatków, taryf czy prowizji**; `current_price` może mieć inną dokładność. Obie wartości DKK/kWh.
- Minimalna cena autonomicznego **eksportu nadwyżki PV**: **0,40 DKK/kWh** włącznie. Poniżej: `switch.sun12k_solar_sell` OFF; przy/ponad: ON może zezwolić na eksport, ale nie wymusza jego ilości. Przy sprzecznych cenach z powodu zaokrąglenia nie włączać eksportu i zgłosić niejednoznaczność.
- **Stała degradacja baterii 0,40 DKK/kWh energii rozładowanej na DC**, naliczona **raz** przy rozładowaniu. Przy decyzji zakupowej na przyszłe ładowanie uwzględnić koszt przewidywanego rozładowania. To polityka użytkownika, nie empiryczny pomiar degradacji i nie próg eksportu PV.
- Straty konwersji odzwierciedlać w bilansie energetycznym, **nie naliczać ich dwukrotnie jako opłaty**. Sprawności 0,9487 i 0,97 w starych danych były jedynie założeniami, nie pomiarem. Cena nabycia baterii 19 000 DKK nie jest dodatkowym kosztem dziennego planu.
- Brak sztywnej rezerwy blackout. Dynamiczny cel SOC jest rezultatem optymalizacji z minimalnym 20%, a nie ustawionym na stałe procentem.

## Uprawnienia
- **Autonomiczne**: wybór limitów prądu, ładowanie z sieci (Grid Charge), modyfikowanie wszystkich **sześciu okresów TOU**, zezwolenie na eksport **PV** po uruchomieniu live. Każdorazowa zgoda na te operacje nie jest potrzebna; wdrożenie live wymaga walidacji i świadomego włączenia.
- W trybie automatycznym Co-Pilot jest **nadrzędny względem zwykłych ręcznych zmian nastaw**: przy kolejnym planie może je nadpisać. **STOP, wyłączenie automatyki, ograniczenia bezpieczeństwa i zgody mają pierwszeństwo**; zakaz pętli natychmiastowych nadpisań.
- `switch.sun12k_solar_sell` w **obecnej konfiguracji** pozwala wyłącznie na eksport nadwyżek PV; sprzedaż baterii jest wyłączona (potwierdzone przez użytkownika). Nie zakładać, że dowolna przyszła zmiana TOU nigdy tego nie naruszy.
- **Eksport z baterii zachować jako funkcję opcjonalną**; każda konkretna propozycja wymaga jawnej osobnej zgody, określającej plan, okres i limit kWh. Domyślnie zablokowany.
- Faza początkowa `monitor/dry_run`: zero zapisów do urządzenia. Przejście do live jest osobną decyzją; bezpieczeństwo wykonania: [EXECUTION.md](EXECUTION.md).

## Oczekiwany wynik integracji
Natywne encje HA, config/options flow, prognoza PV i zużycia, plan dla opublikowanych cen, wyjaśnienie decyzji i wariantów, przewidywane koszty/straty, stany `planned/applied/confirmed`, dziennik wszystkich decyzji, dashboard i UI zatwierdzania eksportu baterii. Raporty oszczędności rozróżniają wynik modelowany, backtest i rzeczywisty. Wymagania techniczne: [HA_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION.md](OPTIMIZATION.md), [VALIDATION.md](VALIDATION.md).
