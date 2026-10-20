# Cele funkcjonalne — obowiązujące

## Cel ekonomiczny

Minimalizacja faktycznego **rachunku netto w DKK** w porównywalnym okresie:

**Koszt importowanej energii (z opłatami zmiennymi) − przychód netto z eksportu + marginalny koszt zużycia baterii wskutek dodatkowych cykli.**

Koszty stałe, podatki, bilansowanie, rozliczenia eksportu i sposób obciążenia baterii w modelu wymagają weryfikacji. Nie dodawać kosztu całego wcześniej zakupionego magazynu do każdej decyzji. Rozdzielać koszt rachunku od wewnętrznego kosztu degradacji; nie podawać wskaźnika wewnętrznego jako wartości faktury.

Drugorzędne KPI: import kWh, ważona wolumenem średnia cena zakupu DKK/kWh, eksport kWh i przychód netto, autokonsumpcja PV, straty i throughput baterii, skuteczność propozycji. Żaden z nich samodzielnie nie zastępuje wyniku netto.

## Dozwolone funkcje

| Funkcja | Wymagana decyzja |
| --- | --- |
| Zasilanie domu z PV / baterii | Standardowa funkcja falownika, bez koniecznej zmiany |
| Ładowanie baterii z PV | Automatyczne, gdy korzystne |
| Ładowanie baterii z sieci | Automatyczne, gdy korzystne i technicznie zweryfikowane |
| Eksport nadwyżki PV | Automatyczny, jeśli wykonalny, legalny i korzystny |
| Celowe rozładowanie baterii na eksport | **Osobne zatwierdzenie każdej propozycji przez użytkownika** |
| Ładowanie z sieci na późniejszą odsprzedaż | Dozwolone ekonomicznie, ale **sam eksport z baterii wymaga zgody** |
| Sterowanie dodatkowymi odbiornikami | Poza MVP |

Nie obowiązują historyczne: próg sprzedaży 0,4 DKK/kWh, sztywna rezerwa nocna, stały docelowy SOC, zakup tylko bez PV ani konieczność pełnej baterii wieczorem. Docelowy SOC może zmieniać się dynamicznie. Zadeklarowane granice SOC: 20–100%; faktyczne ograniczenia BMS/falownika mają pierwszeństwo. Użytkownik nie wymaga rezerwy na blackout.

## Cena i opłacalność

- **Zakup:** końcowa zmienna cena zakupu udostępniona w HA; użytkownik potwierdził uwzględnienie **wszystkich opłat i taryf**. Co-Pilot nie dolicza ich ponownie. Pozostaje sprawdzić strukturę przyszłej serii i daty.
- **Sprzedaż — reguła przekazana przez użytkownika:** netto = cena spot − **0,0215 DKK/kWh** prowizji Vindstød. Sprawdzić na rzeczywistych rozliczeniach, czy jest to komplet wszystkich zmiennych obciążeń; nie dopowiadać innych kwot.
- Ocena ładowania/rozładowania obejmuje sprawność w obie strony, koszt zużycia magazynu, limity mocy, koszty alternatywne przyszłego zasilania domu i skutki cen ujemnych.
- Prognozy mogą być niepewne; plan musi tolerować odchylenia i aktualizować się po istotnej zmianie danych.

## Zatwierdzanie eksportu z baterii

Propozycja pokazuje okres, energię kWh, szacowany **dodatkowy** wynik DKK po kosztach, SOC po operacji oraz przyjęte ceny/straty. Akcje: **Zatwierdź** / **Odrzuć**. Zgoda dotyczy tylko jednoznacznie identyfikowalnego planu, zakresu czasu i ilości; musi wygasnąć oraz zostać ponownie zweryfikowana tuż przed komendą. Brak odpowiedzi, zmiana planu albo nieważna zgoda = **zakaz eksportu z baterii**.

## Widoczność i mierzalność

W HA prezentować na żywo aktualne pomiary, plan i jego ważność, docelowy SOC, zamiar źródła ładowania (PV/sieć), zamiar wykorzystania baterii (dom/eksport), decyzję o eksporcie PV, szacunkowy koszt/zysk, uzasadnienie, tryb pracy, stan sterowania i błędy. Planowane intencje odróżniać od rzeczywistych pomiarów. W pierwszej kolejności używać natywnych encji HA.

Sukces wymaga testu na danych historycznych oraz porównania z rzeczywistym scenariuszem bazowym; nie przypisywać całej zmiany rachunku działaniu optymalizatora bez uwzględnienia pogody, obciążenia i cen.
