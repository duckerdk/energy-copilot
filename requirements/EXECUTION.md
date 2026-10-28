# Wykonanie przez Home Assistant

**Zasady użytkownika i uprawnienia są wyłącznie w [REQUIREMENTS.md](REQUIREMENTS.md).** Dostępne encje i jakość danych opisuje [HA_CONTRACT.md](HA_CONTRACT.md). Ten plik opisuje tylko wykonanie i bezpieczeństwo.

## Tryby
- `monitor`: tylko odczyt.
- `dry_run`: plan i dziennik, **zero zapisów**.
- `supervised_test`: pojedynczy test zatwierdzony na instalacji z metodą powrotu.
- `automatic`: po włączeniu trybu live — autonomiczne limity prądu, Grid Charge, wszystkie sześć TOU i PV Solar Sell.
- `battery_export`: odrębna zdolność, każda konkretna operacja wymaga ważnej osobnej zgody.

Uprawnienia projektowe nie oznaczają, że obecne repo może już sterować falownikiem. **M1–M5 pozostają bez zapisów**. M6 wymaga sprawdzonego mapowania, aktualnych pomiarów i świadomego uruchomienia.

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

## Dziennik i dashboard
Każda decyzja, również `idle/blocked`, zawiera `decision_id`, `plan_id`, UTC, wejściowe ceny i wersje prognoz, jakość pomiarów, ocenę wariantów, koszt energii i degradacji, powód, wybraną akcję i status fizycznego potwierdzenia. Bez haseł i danych tajnych. W UI pokazać cenę zakupu/sprzedaży, SOC, PV, sieć, stan planera i działania, najbliższe akcje, historię, STOP oraz zatwierdzenie/odwołanie eksportu baterii. Retencję ograniczyć bez utraty audytu decyzji. Od v1.16.8 lokalny Store przechowuje do 6000 zdarzeń z ostatnich 30 dni i eksportuje je przez diagnostykę, a sensor diagnostyczny pokazuje 5 ostatnich. Koszt alternatywny w obecnym audycie jest liczony dla całego horyzontu (nie jest marginalnym kosztorysem pojedynczego kwadransa).

Testy i odbiór: [VALIDATION.md](VALIDATION.md).
