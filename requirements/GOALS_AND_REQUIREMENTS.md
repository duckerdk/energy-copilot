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

**Nowa obowiązująca decyzja:** minimalna cena eksportu PV wynosi **0,40 DKK/kWh bezpośrednio z `sensor.energi_data_spotpris`** i Co-Pilot sam steruje `switch.sun12k_solar_sell` po zatwierdzeniu trybu live; [polityka eksportu](PV_EXPORT_POLICY.md). Nie obowiązują historyczne: sztywna rezerwa nocna, stały docelowy SOC, zakup tylko bez PV ani konieczność pełnej baterii wieczorem. Docelowy SOC może zmieniać się dynamicznie. Zadeklarowane granice SOC: 20–100%; faktyczne ograniczenia BMS/falownika mają pierwszeństwo. Użytkownik nie wymaga rezerwy na blackout.

## Cena i opłacalność

- **Zakup:** cena z `sensor.energi_data_service` **bez żadnych modyfikacji**; format przyszłych cen jest już udokumentowany w [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md).
- **Sprzedaż:** cena z `sensor.energi_data_spotpris` **bez żadnych modyfikacji**. Co-Pilot nie zajmuje się prowizjami, podatkami ani taryfami — cen używa dokładnie takich, jakie HA podaje. Automatyczny eksport PV dozwolony od **0,40 DKK/kWh** (wartość włącznie), zakaz poniżej progu. Szczegóły: [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md).
- Ocena ładowania/rozładowania obejmuje sprawność w obie strony, koszt zużycia magazynu, limity mocy, koszty alternatywne przyszłego zasilania domu i skutki cen ujemnych.
- Prognozy mogą być niepewne; plan musi tolerować odchylenia i aktualizować się po istotnej zmianie danych.

## Zatwierdzanie eksportu z baterii

Propozycja pokazuje okres, energię kWh, szacowany **dodatkowy** wynik DKK po kosztach, SOC po operacji oraz przyjęte ceny/straty. Akcje: **Zatwierdź** / **Odrzuć**. Zgoda dotyczy tylko jednoznacznie identyfikowalnego planu, zakresu czasu i ilości; musi wygasnąć oraz zostać ponownie zweryfikowana tuż przed komendą. Brak odpowiedzi, zmiana planu albo nieważna zgoda = **zakaz eksportu z baterii**.

## Widoczność i mierzalność

W HA prezentować na żywo aktualne pomiary, plan i jego ważność, docelowy SOC, zamiar źródła ładowania (PV/sieć), zamiar wykorzystania baterii (dom/eksport), decyzję o eksporcie PV, szacunkowy koszt/zysk, uzasadnienie, tryb pracy, stan sterowania i błędy. Planowane intencje odróżniać od rzeczywistych pomiarów. W pierwszej kolejności używać natywnych encji HA.

Sukces wymaga testu na danych historycznych oraz porównania z rzeczywistym scenariuszem bazowym; nie przypisywać całej zmiany rachunku działaniu optymalizatora bez uwzględnienia pogody, obciążenia i cen.
