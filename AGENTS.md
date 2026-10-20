# Instrukcje dla Codexa — Energy Co-Pilot

Przeczytaj README.md i wszystkie dokumenty w requirements/ przed rozpoczęciem pracy. Jeśli dokumenty się różnią, zgłoś sprzeczność; **nie rozstrzygaj jej domysłem**. Historyczny kod, archiwalne commity i nazwy encji nie są dowodem działania aktualnej instalacji.

## Zakres

Buduj **niestandardową integrację Home Assistant** w custom_components/energy_copilot. Wykorzystuj natywne API HA, konfigurację przez UI (config flow/options flow) i aktualne zalecenia developers.home-assistant.io. Nie twórz osobnego serwera, kontenera, tokenów REST do własnej instancji HA ani zależności od LLM do decyzji wykonawczych. Algorytm ekonomiczny ma być deterministyczny i testowalny.

**Granica techniczna:** pracuj wyłącznie z istniejącymi encjami Home Assistant — odczyty ich stanów i atrybutów oraz (po spełnieniu P0) natywne usługi HA skierowane do tych encji. **Nigdy nie implementuj własnego klienta Modbus, odczytu/zapisu rejestrów ani bezpośredniego połączenia z falownikiem.** Nie modyfikuj ESPHome, YAML, firmware, istniejących automatyzacji HA ani konfiguracji mostka. Plik `deye-esp.yaml` jest jedynie referencją objaśniającą mapę istniejących encji; adres rejestru nie jest polem konfiguracji Energy Co-Pilot. Nie zapisuj tokenów, adresów prywatnych, surowych danych historii użytkownika ani diagnostyki z sekretami.

## Kolejność pracy

1. Szkielet integracji: manifest, config flow, translations, entry setup/unload, testy. **Bez aktywnego sterowania**.
2. Konfigurowalne mapowanie istniejących encji HA i walidacja typów, jednostek, atrybutów, znaków mocy, aktualności i prognoz. **Parser cen:** [requirements/HA_PRICE_SERIES_CONTRACT.md](requirements/HA_PRICE_SERIES_CONTRACT.md). **BEZWZGLĘDNE: Co-Pilot używa zakupu z `sensor.energi_data_service` i sprzedaży z `sensor.energi_data_spotpris` bez żadnych zmian kwoty. Nie oblicza prowizji, podatków ani taryf, nie dodaje i nie odejmuje od ceny.** **Prognoza PV:** [requirements/PV_FORECAST_CONTRACT.md](requirements/PV_FORECAST_CONTRACT.md), użytkownik potwierdził obecność natywnej akcji HA `forecast_solar.get_forecast` w Narzędzia deweloperskie → Akcje; w M2 przetestuj odpowiedź `wh_period`/`watts`, wpis konfiguracji i jednostki. **Prognoza obciążenia:** [requirements/LOAD_FORECAST_CONTRACT.md](requirements/LOAD_FORECAST_CONTRACT.md), natywna historia Recorder sensora `sensor.home_energy_consumption` i deterministyczny, uczciwy model profilu; nie używaj encji `battery_controller.*`. **Bilans fizyczny:** [requirements/MEASUREMENT_CONTRACT.md](requirements/MEASUREMENT_CONTRACT.md). **Użytkownik podał dokładny wzór `home_energy_consumption = pv_sum + total_grid_power + battery_output_power`. Przyjmij go bez dyskusji jako operacyjną encję domu; zero residual jest konsekwencją wzoru, nie testem niezależności. Nie wymagaj nowych liczników ani przekładników.** Ponieważ w szablonie zastosowano `float(0)`, sprawdzaj dostępność 3 encji składowych, zanim użyjesz obliczonej wartości. Sprawdź dostępność akcji w tej wersji HA, nie zgaduj jej; nie żądaj ręcznego kopiowania atrybutów jako warunku projektowania. Gdy brak akcji, jawnie oznacz brak tej zdolności, bez dopowiadania profilu godzinowego z dziennej sumy.
3. Deterministyczny silnik danych, model kosztów, plan, diagnostyka oraz encje prezentujące wyniki. **Od pierwszego dry-run obowiązkowy rejestr podstaw KAŻDEJ decyzji zgodny z requirements/DECISION_LOGGING.md**, widoczny w HA: ceny, prognozy, koszt alternatyw, decyzja, powód i status. Domyślnie tryb **monitor/dry-run**.
4. Testy z fikcyjnymi encjami i zanonimizowanymi, legalnie udostępnionymi danymi historycznymi; walidacja `walk-forward` bez przyszłych prognoz, z zachowaniem ograniczenia PV (curtailment), zgodnie z requirements/BACKTEST_VALIDATION.md. Bez wywołania usług sterujących.
5. Dopiero po spełnieniu blokad opisanych w OPEN_ITEMS.md przygotuj osobny, możliwy do włączenia przez użytkownika moduł wykonawczy. **Nie włączaj go samodzielnie**.

**Sterowanie w czasie:** przeczytaj [requirements/CONTROL_STRATEGY.md](requirements/CONTROL_STRATEGY.md), [requirements/CURRENT_CONTROLLER_MODEL.md](requirements/CURRENT_CONTROLLER_MODEL.md) oraz [requirements/PV_EXPORT_POLICY.md](requirements/PV_EXPORT_POLICY.md). **Użytkownik zezwala Co-Pilot na autonomiczne ON/OFF `switch.sun12k_solar_sell` od progu ceny z HA `0,40 DKK/kWh`; eksport baterii wymaga osobnej zgody.** Bazowy translator planu używa istniejących encji HA do regulowania **limitów** prądu; zachowuje zastany TOU, dopóki nie udowodniono korzyści i bezpieczeństwa dynamicznego przepisywania okien. Same limity A nie realizują bezpośrednio mocy kW ani celu SOC. Każda nastawa Deye zostaje po utracie HA — uwzględnij to w planie i testach. Nie programuj zmian TOU według każdej ceny kwadransowej.

## Niezmienniki

- Nie utożsamiaj eksportu PV ze sprzedażą z baterii; przełącznik zezwolenia na eksport nie dowodzi kontroli źródła eksportowanej energii. **Cena PV export <0,40 z HA → OFF; >=0,40 → ON zezwolenia**, po osobnym dopuszczeniu trybu live i spełnieniu zabezpieczeń.
- Projektowo przyjmij właściwe funkcje trzech istniejących encji prądowych HA: `number.sun12k_maximum_battery_charge_current` 0–50 A (ładowanie ogólne, w tym PV), `number.sun12k_maximum_battery_discharge_current` 0–100 A (rozładowanie) oraz `number.sun12k_maximum_battery_grid_charge_current` 0–50 A (ładowanie z sieci). To założenia funkcjonalne bez pozwolenia na zapis; przed fizycznym sterowaniem konieczny nadzorowany test i P0.
- Nie zgaduj encji importu, eksportu, mocy baterii, docelowego SOC, rozładowania ani fabrycznego harmonogramu.
- Nie zapisuj nic do urządzeń przy unknown/unavailable, starych cenach/prognozach, niespójnych jednostkach, utracie potwierdzenia lub przeterminowanej zgodzie.
- Proponowany plan nie jest komendą; wywołanie usługi nie jest potwierdzeniem skutku. Wymagane osobne sprawdzenie odczytu i bezpieczny tryb wyjścia.
- Nie deklaruj, że awaria HA automatycznie przywróci fabryczny tryb: bez sprzętowo niezależnego mechanizmu jest to nieudowodnione.
- Nie buduj własnego frontendu, dopóki natywne encje HA i standardowy dashboard nie zostaną ocenione jako niewystarczające.

## Warunki oddania każdej zmiany

- Wskaż zrealizowany zakres, **niepotwierdzone założenia**, zmiany w dostępnych akcjach i aktualne blokady.
- Dodaj/uruchom odpowiednie testy pytest, lint i typowanie zgodnie z przyjętym narzędziem projektu. Obsłuż setup/unload, restart, braki danych i DST Europe/Copenhagen.
- Jeżeli jakikolwiek test był niemożliwy do wykonania, napisz to wprost; nie opisuj testów planowanych jako wykonanych.
- Aktualizuj dokumentację **tylko dla potwierdzonych zmian**; nie duplikuj tych samych wymagań w kolejnych plikach.
