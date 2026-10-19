# Energy Co-Pilot — aktualny opis instalacji i danych (wg użytkownika)

**Data zebrania:** 15.10.2026; aktualizacja ustaleń: 19.10.2026.  
**Podstawa:** odpowiedzi użytkownika 1–36, zrzut Forecast.Solar, późniejsze uzgodnienie prowizji Vindstød oraz przekazane przez użytkownika diagnostyki Battery Controller 2.11.5. Nie wykonywano bezpośredniego połączenia z HA ani operacji sterowania.

## 1. Elementy fizyczne

| Komponent | Parametr |
| --- | --- |
| Falownik | **Deye SUN-12K-SP04LP3-EU** (oznaczenie podane przez użytkownika) |
| Magazyn | **2 × BSLBATT LiFePO4 51,2 V / 100 Ah / 5120 Wh** |
| Pojemność nominalna razem | **10,24 kWh** (2 × 5,12 kWh; wartość obliczona) |
| Przyjęta wcześniejsza energia użytkowa | Około **8 kWh**, zakres SOC **20–100%**; sprawność/energia netto wymagają osobnej weryfikacji |
| Koszt kompletu magazynu | **19 000 DKK** |
| Rezerwa na zanik zasilania | **Nie wymagana** |
| Możliwości falownika | Użytkownik potwierdził: kontrola ładowania PV, ładowania z sieci, wymuszonego rozładowania, minimalnego SOC, eksportu energii z baterii oraz fabryczny harmonogram |

**Bez nowych działań sprzętowych:** na potrzeby nowego projektu nie zmieniamy firmware, ESPHome ani rejestrów falownika.

## 2. Komunikacja i środowisko

- Home Assistant pracuje **w maszynie wirtualnej na serwerze**.
- Falownik udostępnia encje przez **customowy Modbus na ESP32**, komunikacja z HA przez **ESPHome po Wi‑Fi**.
- Dotychczasowe funkcje sterowania mają być wykorzystywane **poprzez już istniejące encje HA**.
- **Istniejący rejestr znanych encji (11 identyfikatorów)**: [ENTITIES.md](../archive/energy-copilot-v5/docs/ENTITIES.md) i [config/entities.yaml](../archive/energy-copilot-v5/config/entities.yaml). Stanowi bazę mapowania; nie jest potwierdzeniem aktualnych wartości i działania wszystkich encji. Nie wymaga ponownego przekazywania wykazu.
- Użytkownik potwierdza osobne pomiary chwilowej mocy: **importu, eksportu, ładowania i rozładowania baterii**.
- Brak dodatkowych odbiorników sterowalnych na obecnym etapie, możliwość przyszłej rozbudowy.

## 3. Źródła danych

| Dane | Źródło / dostępność | Co wiemy |
| --- | --- | --- |
| Cena spot | `sensor.energi_data_spotpris` | Historycznie znana encja HA; cena w DKK/kWh, potwierdzić bieżące atrybuty i dostępność |
| Cena zakupu z opłatami | `sensor.energi_data_service` | Znane źródło prognozy cen i finalnej ceny zakupu; przed implementacją potwierdzić format i jednostki atrybutów |
| Cena sprzedaży netto | **Wyliczana z ceny spot** | **`spotpris - 0,0215 DKK/kWh`** (ustalona prowizja Vindstød); osobna encja nie jest konieczna |
| Prognoza PV | **Forecast.Solar (integracja HA)** | Potwierdzona na zrzucie z 15.10.2026 |
| Historia pomiarów | **HA Recorder / karta Energia** | Użytkownik posiada historię z kilku lat wg standardowych ustawień HA; rozdzielczość starszych danych nieustalona |

### Co dokładnie widać na zrzucie Forecast.Solar

Integracja wskazuje producenta **Forecast.Solar** i sensory prognozy:
- estymowaną energię **w bieżącej i następnej godzinie**;
- energię przewidywaną **na pozostałą część dnia**;
- moc **teraz, za godzinę, za 12 h i za 24 h**;
- czas najwyższego szczytu mocy **dziś i jutro**;
- **„Solar forecast today”** i **„Solar forecast tomorrow”**.

Na wykonanym zrzucie pokazano odpowiednio **8,1 kWh na dziś** i **8,0 kWh na jutro**, a także **7,8 kWh pozostałe dziś**. To **przemijający odczyt z dnia zrzutu**, nie stała instalacji ani obietnica jakości prognoz. **Nie widać dokładnych entity_id ani kompletnej serii godzinowej** — nie należy ich wymyślać.

Wcześniejsze identyfikatory `sensor.energy_production_today` i `sensor.energy_production_tomorrow` są podane w starym archiwum, ale zrzut sam nie potwierdza ich aktualnych nazw.

## 4. Rozliczenia energii

- Obszar: **Nordjylland, Dania**, operator sieci **N1**.
- Zakup w ramach **Elforbundet / Vindstød**.
- **Vindstød** jest też odbiorcą nadwyżek PV.
- Do kalkulacji zakupu użytkownik ma w HA cenę końcową z opłatami.
- **Reguła ceny sprzedaży netto jest ustalona:** `cena_sprzedazy_netto_DKK_kWh = spotpris_DKK_kWh - 0,0215`; prowizja Vindstød wynosi **0,0215 DKK/kWh**. Formułę stosujemy do bieżącej i przyszłej ceny spot, z zachowaniem zgodności czasowej i jednostek; brak gotowej encji wyliczonej ceny nie jest brakiem reguły rozliczenia.
- Dokumentacja projektu odróżnia ceny **zakupu końcowego** z opłatami od cen **sprzedaży netto**; nie wolno używać ich zamiennie.

## 5. Rzeczy do zachowania bez zmian w obecnej instalacji

Home Assistant, pomiary importu/eksportu, rejestracja historii, Forecast.Solar, Energi Data Service, własne ESPHome/Modbus, fabryczne funkcje Deye. Nie ruszać ich w ramach definiowania nowego rozwiązania.

**Poziomy potwierdzenia:** parametry dostarczone przez użytkownika (deklaracje); pojemności sumaryczne (obliczenia); schemat API, jednostki konkretnych encji i mapowania harmonogramu (niezweryfikowane).
