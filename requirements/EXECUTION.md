# Wykonanie przez Home Assistant

**Zasady użytkownika i uprawnienia są wyłącznie w [REQUIREMENTS.md](REQUIREMENTS.md).** Dostępne encje i jakość danych opisuje [HA_CONTRACT.md](HA_CONTRACT.md). Ten plik opisuje tylko wykonanie i bezpieczeństwo.

## Tryby
- `monitor`: tylko odczyt.
- `dry_run`: plan i dziennik, **zero zapisów**.
- `supervised_test`: pojedynczy test zatwierdzony na instalacji z metodą powrotu.
- `automatic`: po włączeniu trybu live — autonomiczne limity prądu, Grid Charge, wszystkie sześć TOU i PV Solar Sell.
- `battery_export`: odrębna zdolność, każda konkretna operacja wymaga ważnej osobnej zgody.

Tryb `automatic` posiada wykonawcę zapisującego nastawy przez usługi HA; pozostałe tryby odczytu nie zapisują. Testy repozytorium nie są upoważnieniem do fizycznych eksperymentów na falowniku. Dla każdej akcji obowiązują aktualne dane, bezpieczeństwo i możliwość recovery.

## Wykonawca
Przed każdą akcją: odczytaj aktualne HA, TOU, SOC, BMS, ceny i `plan_id`; sprawdź kompletność, granice prądowe, 20% SOC, dostępność i zgodę. Polecenia przez natywne `number.set_value` i `switch.turn_on/off`, bez własnego Modbus. Nie utożsamiaj ustawienia *maksymalnego* prądu z wymuszeniem konkretnych kW ani osiągnięciem celu SOC. Do prądu używaj dostępnego napięcia i obsługiwanego kroku; odrzucaj nielegalną wartość zamiast ją cicho przycinać.

Polecenie już wykonane: nie powtarzaj. Timeout z nieznanym skutkiem: nie ponawiaj w ciemno. Sukces usługi HA to najwyżej `applied`; `confirmed` wymaga odczytu i odpowiedniej obserwacji. Wykonawca ma stany `planned`, `blocked`, `applying`, `applied`, `confirmed`, `failed`, `uncertain`, `recovery_required`; każda zmiana stanu do logu. Tylko jeden aktywny executor. Przycisk STOP zatrzymuje kolejne działania, nie obiecuje sprzętowego wyłączenia. W trybie `automatic` ARM włącza się po starcie/reload integracji. Przejściowy błąd wejścia lub planu nie rozbraja ARM: blokuje zapisy do uzyskania nowych poprawnych danych i planu. Niepewny wynik częściowego zapisu do urządzenia pozostaje `recovery_required`, bez ślepego ponowienia.

## Dynamiczny TOU
Użytkownik **zezwolił na autonomiczną zmianę wszystkich sześciu okien**. To nie znaczy, że zapisy wielu encji są atomowe: odczytaj cały harmonogram, oceń efekt powtarzania w kolejną dobę, granicę 00:00, następstwo okien i częściową awarię w trakcie aktualizacji. Zadbaj o znaną kolejność zmian i możliwość odzyskania poprawnego układu. Nie deklaruj 96 niezależnych okresów sterowania na podstawie sześciu TOU. Grid Charge może zależeć od `switch.sun12k_grid_charge`, limitu ogólnego, limitu sieciowego i flagi charge w aktualnym TOU.

Ręczna zmiana zwykłej nastawy w trakcie aktywnej automatyki **może zostać nadpisana przy kolejnym planie**. Nie uruchamiaj wojny zapisów na każde zdarzenie HA. STOP, ochrona fizyczna i zgoda na eksport baterii mają pierwszeństwo.

## Utrata HA
Deye utrzymuje ostatnie parametry; **użytkownik akceptuje koszty ekonomiczne** nieoptymalnych nastaw podczas awarii. Nie wymagaj niezależnego wyłącznika tylko po to, by uniknąć straty finansowej. Brak HA nie jest równoznaczny z OFF, a po powrocie należy odczytać realny stan, unieważnić poprzedni plan i obliczyć nowy. Nie wolno naruszać fizycznego bezpieczeństwa falownika/BMS ani polityki minimum SOC.

## Eksport z baterii
Obecny Solar Sell zezwala tylko na nadwyżkę PV. Zmiana TOU lub pozostałych ustawień nie może przypadkowo włączyć eksportu baterii. Opcjonalna propozycja musi obejmować `proposal_id`, `plan_id`, czas, maksymalną energię eksportu z baterii [kWh AC], moc, SOC po operacji i korzyść po kosztach. Brak odpowiedzi = brak zgody. Zgoda wygasa przy zmianie warunków lub planu. Jeśli nie można fizycznie odróżnić eksportu baterii od eksportu PV, egzekwować kWh albo niezależnie zakończyć eksportu po zaniku HA, funkcja pozostaje `proposal_only` i nie wydaje komend.

## Dziennik i audyt wykonania
- Dla decyzji podawaj **co, dlaczego, na jakich danych i z jakim wynikiem**: czas lokalny i kwadrans, SOC, ceny, planowane PV/dom/sieć, koszty, działanie i powód. Stan i wynik zapisu mają osobne znaczenie.
- Zdarzenia planu, jego rewizji, blokad i zapisów trafiają do natywnej Aktywności HA; techniczna historia w diagnostyce ma retencję do 30 dni / 6000 zdarzeń. Brak potrzeby komentarzy ogólnych, pseudo-uzasadnień ani surowych struktur w logu użytkownika.
- Zmiana planu w tym samym kwadransie to **rewizja** z wartościami przed/po; stabilny plan nie może tworzyć szumu. Długotrwała blokada — maksymalnie jeden komunikat na kwadrans.
- Wykonawca odróżnia wysłany i odczytem potwierdzony zapis od braku komend. Nie nazywaj potwierdzenia nastawy pomiarem rzeczywistego przepływu.
- Uzasadnienie ekonomiczne wolno przypisać tylko rzeczywiście obliczonemu wariantowi kontrfaktycznemu na identycznych danych i horyzoncie; brak porównania albo różnicę bliską zeru pokaż wprost. Diagnostyczna dodatkowa optymalizacja nie może opóźniać ani blokować wykonawcy.

## Reguły TOU i prądów
- **Nigdy nie zapisuj** `number.sun12k_maximum_battery_discharge_current`. Zaobserwowano, że 0 A zatrzymuje PV; zastane 0 A blokuje nowe polecenia do ręcznego przywrócenia dodatniej wartości.
- Rozładowanie realizuj progiem SOC aktywnego TOU, bez sztucznego racjonowania energii na kolejne kwadranse. Zaokrąglenie nastaw SOC: **1%**, przy minimum 20%. Brak rozładowania nie może wymuszać progu 100% tylko dlatego, że prognozowany SOC jest wysoki.
- Przy Grid Charge ON cel TOU odzwierciedla jedynie zaplanowany przyrost z sieci, nie przyszły PV. Najpierw progi/flagę TOU i wymagane prądy, następnie Grid Charge ON. Przy wyłączaniu — najpierw Grid Charge OFF.
- Prądy ładowania można zmieniać w granicach 1–50 A **tylko w celu świadomego rozłożenia ładowania z sieci lub przesunięcia ładowania PV w czasie**. Sama prognoza PV, Solar Sell ON lub wysoki SOC nie uzasadniają przestawienia prądu na 1 A. Przywracaj wartość po zakończeniu czasowego ograniczenia, jeżeli użytkownik nie zmienił jej ręcznie.
- Drobne korzyści ekonomiczne nie mogą inicjować bezsensownych cykli: remis do 0,01 DKK, rozpoczęcie kampanii ładowania z sieci wymaga 0,10 DKK, kontynuacja 0,05 DKK. Ocena obejmuje całe opublikowane okno cenowe, nie tylko bieżący kwadrans. Dla 99% SOC nie inicjuj sieciowego doładowania do 100% bez istotnej korzyści; naturalne ładowanie PV do 100% jest dozwolone.
- TOU ma sześć fizycznych slotów. Plan 15-minutowy nie oznacza 96 niezależnych zapisów. Przejście granicy kwadransa, restart i częściowy błąd zapisu muszą mieć przewidywalny mechanizm recovery.

Testy i odbiór: [VALIDATION.md](VALIDATION.md). Rzeczywiste, jeszcze niepotwierdzone aspekty: [OPEN_ITEMS.md](OPEN_ITEMS.md).
