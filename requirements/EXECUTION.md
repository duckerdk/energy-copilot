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

Polecenie już wykonane: nie powtarzaj. Timeout z nieznanym skutkiem: nie ponawiaj w ciemno. Sukces usługi HA to najwyżej `applied`; `confirmed` wymaga odczytu i odpowiedniej obserwacji. Wykonawca ma stany `planned`, `blocked`, `applying`, `applied`, `confirmed`, `failed`, `uncertain`, `recovery_required`; każda zmiana stanu do logu. Tylko jeden aktywny executor. Przycisk STOP zatrzymuje kolejne działania, nie obiecuje sprzętowego wyłączenia. W trybie `automatic` ARM włącza się po starcie/reload integracji. Nowe scenariusze 2.0.0 nie powodują żadnych dodatkowych zapisów poza normalnym bieżącym kwadransem. Przejściowy błąd wejścia lub planu nie rozbraja ARM: blokuje zapisy do uzyskania nowych poprawnych danych i planu. Niepewny wynik częściowego zapisu do urządzenia pozostaje `recovery_required`, bez ślepego ponowienia.

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

## Projekcja planu 2.0.0 na sześć TOU

- Każdy kwadrans w planie 2.0.0 przechodzi niezależne sprawdzenie: UTC/DST, SOC 20–100%, brak jednoczesnego ładowania i rozładowania, cel Grid Charge zaokrąglony do 1%, rozładowanie do dozwolonego minimum 20%, właściwa bieżąca pozycja 1–6.
- Deye utrzymuje **sześć czterogodzinnych slotów** z początkami 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 czasu lokalnego. Wykonawca może zmienić wartości **bieżącego** slotu co kwadrans po odczycie urządzenia. Nie ogłaszać dowolnej 96-slotowej harmonogramowej kontroli; każdy brak zgodnego TOU blokuje wykonanie.
- `tou_feasibility.status=modeled_quarterly_rewrites_only` oznacza poprawność projekcji komend, **nie** pewność fizycznie zrealizowanej energii. `hardware_execution_verified=false` i `executable=false` pozostają do czasu niezależnej walidacji działania falownika. Status `not_representable` jest blokadą nowego polecenia.
- Wybór przyszłej daty ładowania to plan. Jedyna nowa komenda dotyczy **aktualnego kwadransa**. Nie zapisuj prądów „na podstawie prognozy” — sprawdź osobną intencję celowego przesunięcia/rozciągnięcia ładowania.

### Aktualizacja bieżącego kwadransa (2.0.1)
- Po istotnej zmianie SOC i nowym planie executor nie utrzymuje poprzednio zapamiętanej decyzji tylko dlatego, że kwadrans już trwa. Plan częściowego bieżącego przedziału jest wykonalny od chwili odczytu i nadpisuje poprzednią decyzję z tego samego kwadransa.
- Przy wybranym `battery_discharge` SOC aktywnego TOU = **20%**. Bez tej decyzji wysoki próg może ochronić baterię, lecz musi wynikać ze zweryfikowanego planu ekonomicznego, a nie ze sztywnego dawkowania po kilka procent.
- Dziennik grupuje rewizje według faktycznego 15-minutowego okresu, mimo że plan przeliczany jest częściej; czas pobrania pomiarów pozostaje zachowany osobno. Żadna rewizja planu nie daje prawa do dodatkowej zmiany prądów: ich jedyne powody to przesunięcie lub rozciągnięcie ładowania.

## Reguły TOU i prądów
- Parametr `Maximum Battery Discharge Current` **nie istnieje w interfejsie Energy Co-Pilot**: nie czytaj encji, nie zapisuj, nie sprawdzaj wartości, nie blokuj wykonania na jego podstawie, nie podawaj go do planera ani dziennika. Zabezpieczenia sprzętowe pozostają po stronie Deye/BMS; rozładowaniem steruj wyłącznie SOC/TOU.
- Rozładowanie realizuj progiem SOC aktywnego TOU, bez sztucznego racjonowania energii na kolejne kwadranse. Zaokrąglenie nastaw SOC: **1%**, przy minimum 20%. Brak rozładowania nie może wymuszać progu 100% tylko dlatego, że prognozowany SOC jest wysoki.
- Przy Grid Charge ON cel TOU odzwierciedla jedynie zaplanowany przyrost z sieci, nie przyszły PV. Najpierw progi/flagę TOU i wymagane prądy, następnie Grid Charge ON. Przy wyłączaniu — najpierw Grid Charge OFF.
- **Prądów ładowania nie wolno regulować z żadnego innego powodu niż:** (a) przesunięcie w czasie ładowania PV albo (b) rozciągnięcie w czasie ładowania, np. z sieci. Planer musi jawnie wykazać wybrany cel, interwał i zakończenie; wykonawca nie może dobierać nowego limitu na podstawie bieżącej prognozowanej mocy, SOC lub samego Solar Sell. Planowany prąd to opis przepływu, **nie automatyczne zlecenie zapisu limitu**. Bez świadomej kampanii prądy pozostają bez zmian. Po jej końcu należy przywrócić uprzednią nastawę, z trwałym zapisem pochodzenia i ochroną świadomych zmian ręcznych; restart nie może pozostawić limitu 1 A. Dawne ograniczenia mogą być cofnięte tylko z udokumentowanej historii poleceń. Ładowanie naturalnej nadwyżki PV do 100% musi pozostać możliwe; nastawy prognozowanego SOC nie mogą być jej limitem.
- Drobne korzyści ekonomiczne nie mogą inicjować bezsensownych cykli: remis do 0,01 DKK, rozpoczęcie kampanii ładowania z sieci wymaga 0,10 DKK, kontynuacja 0,05 DKK. Ocena obejmuje całe opublikowane okno cenowe, nie tylko bieżący kwadrans. Dla 99% SOC nie inicjuj sieciowego doładowania do 100% bez istotnej korzyści; naturalne ładowanie PV do 100% jest dozwolone.
- TOU ma sześć fizycznych slotów. Plan 15-minutowy nie oznacza 96 niezależnych zapisów. Przejście granicy kwadransa, restart i częściowy błąd zapisu muszą mieć przewidywalny mechanizm recovery.

Testy i odbiór: [VALIDATION.md](VALIDATION.md). Rzeczywiste, jeszcze niepotwierdzone aspekty: [OPEN_ITEMS.md](OPEN_ITEMS.md).
