# Instrukcje dla Codexa — Energy Co-Pilot

Przeczytaj README.md i wszystkie dokumenty w requirements/ przed rozpoczęciem pracy. Jeśli dokumenty się różnią, zgłoś sprzeczność; **nie rozstrzygaj jej domysłem**. Historyczny kod, archiwalne commity i nazwy encji nie są dowodem działania aktualnej instalacji.

## Zakres

Buduj **niestandardową integrację Home Assistant** w custom_components/energy_copilot. Wykorzystuj natywne API HA, konfigurację przez UI (config flow/options flow) i aktualne zalecenia developers.home-assistant.io. Nie twórz osobnego serwera, kontenera, tokenów REST do własnej instancji HA ani zależności od LLM do decyzji wykonawczych. Algorytm ekonomiczny ma być deterministyczny i testowalny.

Nie modyfikuj ESPHome, rejestrów Modbus, firmware, istniejących automatyzacji HA ani sprzętowej konfiguracji falownika. Nie zapisuj tokenów, adresów prywatnych, surowych danych historii użytkownika, diagnostyki z sekretami.

## Kolejność pracy

1. Szkielet integracji: manifest, config flow, translations, entry setup/unload, testy. **Bez aktywnego sterowania**.
2. Konfigurowalne mapowanie istniejących encji HA i walidacja typów, jednostek, atrybutów, znaków mocy, aktualności i prognoz.
3. Deterministyczny silnik danych, model kosztów, plan, diagnostyka oraz encje prezentujące wyniki. **Od pierwszego dry-run obowiązkowy rejestr podstaw KAŻDEJ decyzji zgodny z requirements/DECISION_LOGGING.md**, widoczny w HA: ceny, prognozy, koszt alternatyw, decyzja, powód i status. Domyślnie tryb **monitor/dry-run**.
4. Testy z fikcyjnymi encjami i zanonimizowanymi, legalnie udostępnionymi danymi historycznymi; walidacja `walk-forward` bez przyszłych prognoz, z zachowaniem ograniczenia PV (curtailment), zgodnie z requirements/BACKTEST_VALIDATION.md. Bez wywołania usług sterujących.
5. Dopiero po spełnieniu blokad opisanych w OPEN_ITEMS.md przygotuj osobny, możliwy do włączenia przez użytkownika moduł wykonawczy. **Nie włączaj go samodzielnie**.

## Niezmienniki

- Nie utożsamiaj eksportu PV ze sprzedażą z baterii; przełącznik zezwolenia na eksport nie dowodzi kontroli źródła eksportowanej energii.
- Nie używaj number.sun12k_maximum_battery_grid_charge_current do poleceń bez potwierdzenia skutku fizycznego.
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
