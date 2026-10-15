# Energy Co-Pilot — nowa koncepcja

**Stan: zebrano i zapisano cele oraz wymagania funkcjonalne (15.10.2026).** Nie wybrano jeszcze technologii, nie napisano nowego sterownika i nie zmieniano Home Assistant ani falownika.

## Aktualne założenia (obowiązujące)

- [Cele i wymagania funkcjonalne](requirements/GOALS_AND_REQUIREMENTS.md) — **minimalizacja końcowego rachunku netto w DKK**, dodatkowe KPI, decyzje automatyczne i sprzedaż z baterii wyłącznie za zgodą.
- [Istniejąca instalacja i dane](requirements/SYSTEM_BASELINE.md) — Deye SUN-12K-SP04LP3-EU, 2× BSLBATT, ESPHome/HA, ceny z Energi Data Service oraz PV Forecast.Solar.
- [Otwarte kwestie techniczne](requirements/OPEN_ITEMS.md) — w szczególności cena netto sprzedaży Vindstød, weryfikacja mapowania encji i szczegółowość prognoz.

**Istotny brak:** HA ma cenę spot i finalną cenę zakupu, **ale nie ma ceny sprzedaży netto**. Nie można rzetelnie ocenić opłacalności sprzedaży przed wyznaczeniem tego parametru. Potrzebne dane ekonomiczne zostaną ustalone w kolejnym etapie, bez zgadywania.

## Archiwum wcześniejszego projektu

- [Poprzednia dokumentacja v1–v5](archive/energy-copilot-v5/README.md) — encje, historia, poprzednia logika i przypadki testowe, **nie traktować jako nowej specyfikacji**.
- [Informacja o archiwizacji](archive/README.md).

## Porządki po poprzedniej implementacji

- [Lista kontrolna Home Assistant](cleanup/HOME_ASSISTANT.md).
- [Lista kontrolna serwera](cleanup/SERVER.md).

Nie usunięto nic z HA ani serwera. Nie modyfikowano ESPHome, Modbus, rejestrów ani konfiguracji Deye.

## Następny etap

Porównać dostępne **lokalne** rozwiązania zgodnie z nowymi wymaganiami. Nie wybierać rozwiązania ani nie implementować przed potwierdzeniem faktycznych możliwości integracji, metody kalkulacji ceny eksportu i bezpieczeństwa sterowania.
