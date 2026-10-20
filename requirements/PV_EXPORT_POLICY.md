# Polityka automatycznego eksportu PV — Energy Co-Pilot

**Status: decyzja użytkownika 20.10.2026.** Obowiązuje w projekcie; nie trzeba ponownie pytać o znaczenie ceny ani wysokość progu. Wdrożenie sprzętowe nadal wymaga ukończenia fazy monitor/dry-run i zatwierdzenia uruchomienia automatyki.

## 1. Ceny bez jakichkolwiek przeliczeń

**Użytkownik jednoznacznie ustalił:** Co-Pilot pobiera ceny dokładnie takie, jakie dostarcza HA, i **nie zajmuje się prowizjami, podatkami ani taryfami**. Dlatego:

```text
C_buy[t]      = sensor.energi_data_service.attributes.raw_*.price[t]
C_sell_net[t] = sensor.energi_data_spotpris.attributes.raw_*.price[t]
```

- Oba szeregi `raw_today/raw_tomorrow` wchodzą do planera **bez zmian wartości**.
- Co-Pilot nie prowadzi kalkulacji składników ceny, nie odejmuje i nie dodaje żadnych opłat.
- `current_price` służy do diagnostyki bieżącej ceny; różnica jego precyzji względem listy godzinowej nie jest powodem przeliczenia cen.

## 2. Cena minimalna i decyzja switch

**Konfigurowalna wartość początkowa:** `min_pv_export_price_dkk_kwh = 0.40` (DKK/kWh z encji HA, bez przeliczeń).

**Zasada podstawowa** (warunki dla decyzji na podstawie opublikowanej ceny bieżącej):

| Cena eksportu netto | Zezwolenie na eksport PV przez `switch.sun12k_solar_sell` |
| --- | --- |
| `C_sell_net < 0.40` | **OFF** — nie sprzedawać PV za cenę poniżej minimum |
| `C_sell_net >= 0.40` | **ON / eksport dozwolony**; planner może wykorzystać PV także na dom lub ładowanie baterii |

`ON` jest **zezwoleniem**, nie poleceniem wysłania całej nadwyżki PV na sprzedaż; przy cenie powyżej minimum Co-Pilot nadal optymalizuje magazynowanie, autokonsumpcję i eksport zgodnie z kosztem energii w całym znanym horyzoncie. `OFF` może powodować curtailment, gdy bateria jest pełna, co należy logować i uwzględnić w prognozie potencjalnej PV.

**Histereza cenowa:** nie dodawać arbitralnego marginesu cenowego modyfikującego próg (użytkownik podał dokładnie 0,40). Ograniczyć powtarzane zapisy tylko przy zmianie faktycznego stanu oraz stosować walidację świeżości/ważności ceny i potwierdzenie wykonania. Jedna stawka godzinowa nie powinna powodować zapisu co 15 minut bez zmiany decyzji.

### Warunek danych i utraty łączności

Próg 0,40 DKK/kWh oznacza cenę z HA. `raw_*.price` bywa zaokrąglone, a `current_price` dokładniejsze: jeśli oba aktualne odczyty prowadzą do **innej** decyzji przy progu, zastosuj `PRICE_THRESHOLD_AMBIGUOUS` i nie wydawaj komendy ON ([HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md)). Nie przesuwaj progu histerezą.

Po utracie HA, internetu albo źródła cen przełącznik Deye może pozostać **ON** i nadal eksportować w następnej godzinie poniżej progu. Sam software HA nie daje gwarancji utrzymania minimum cenowego podczas awarii. Tryb live wymaga pokazania tego ryzyka użytkownikowi, ograniczenia czasowo ryzykownych zezwoleń zgodnie z P0 i skutecznej procedury odzyskania stanu. Brak ceny: **bez nowych poleceń** oraz alarm, nie fałszywy komunikat „eksport bezpiecznie wyłączony”.

## 3. Autonomia i uprawnienia

- Użytkownik **upoważnił Co-Pilota do samodzielnego podejmowania decyzji o eksporcie PV**; docelowy wykonawca używa `switch.sun12k_solar_sell` przez usługę HA `switch.turn_on`/`switch.turn_off`, bez ręcznej zgody na każdy slot.
- Ta autonomia **nie oznacza zgody na celowe eksportowanie energii z baterii**. Taki eksport nadal wymaga osobnej, ważnej zgody na dany plan, limit i czas.
- **Potwierdzenie użytkownika 20.10.2026:** w obecnej konfiguracji `switch.sun12k_solar_sell` zezwala wyłącznie na eksport nadwyżki PV, natomiast sprzedaż z baterii jest wyłączona. Jest to stan konfiguracji, nie niezależna gwarancja dla innych nastaw TOU. Przed aktywacją zapisów live zweryfikować fizycznie separację oraz zachowanie ON/OFF; przy zmianie nastaw mogących włączyć eksport baterii wymagane ponowne sprawdzenie. Brak takiej weryfikacji ogranicza funkcję wykonawczą, ale **nie unieważnia reguły biznesowej**.
- Deye **zachowuje ostatnie nastawy po awarii HA**. Dla `OFF` jest to przede wszystkim ryzyko ekonomiczne (utracony eksport), dla `ON` trzeba uwzględnić możliwość przepływu z baterii przy innych nastawach TOU. Przed automatycznymi zapisami obowiązuje kontrakt bezpieczeństwa [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md).
- **Zgoda na autonomię projektową nie jest poleceniem wykonania teraz usług na HA**. Monitor/dry-run mogą od razu symulować tę politykę; fizyczny executor włączamy tylko po odrębnej zgodzie na uruchomienie i testach P0.

## 4. Wykorzystanie w modelu

W bazowym optymalizatorze MPC przy `C_sell_net < 0.40` obowiązuje `s_x=0` dla automatycznego eksportu PV; w `C_sell_net >= 0.40` jest dopuszczony przepływ `s_x>=0`, z fizycznymi limitami i ekonomiczną optymalizacją. Jeśli PV nie może zostać zużyte lub przyjęte do baterii przy wyłączonym eksporcie, jawnie wykazać `s_c` jako ograniczoną produkcję **tylko w symulacji i w granicach wiarygodnej prognozy**; nie uznawać prognozy minus produkcja za zmierzony curtailment.

W backtestach i baseline obowiązuje **ten sam próg i jednostki polityki Co-Pilot**, ale strategia porównawcza bazowa może utrzymywać inne, rzeczywiście istniejące ustawienia Deye; nie narzucać jej nowych reguł po fakcie. Log decyzji ma pokazać `sell_price_now`, próg 0,40, `pv_export_allowed`, proponowany przełącznik, status wykonania i koszt alternatywny braku eksportu. Zapisać powód `PV_EXPORT_BELOW_MIN_PRICE` / `PV_EXPORT_ALLOWED`.

## 5. Testy akceptacyjne — specyfikacja (nie wykonano)

- `PVE-01`: stawka encji spot 0,399 DKK/kWh → PV export OFF.
- `PVE-02`: stawka dokładnie 0,400 DKK/kWh → PV export ON (zezwolenie).
- `PVE-03`: stawka 0,401 DKK/kWh → PV export ON.
- `PVE-04`: 0,400 w encji HA → Co-Pilot przyjmuje 0,400 bez korekt; eksport PV dozwolony.
- `PVE-05`: 1,922 w `raw_today` → cena sprzedaży 1,922, bez dodatkowych działań.
- `PVE-06`: cena zakupu 2,406 z `energi_data_service` → 2,406 końcowo, bez ponownego naliczania taryf.
- `PVE-07`: 0,20 poniżej minimum, PV=3 kW, dom=1 kW, bateria pełna → `solar_sell` OFF; plan nie zapisuje 2 kW jako rzeczywistego eksportu.
- `PVE-08`: cena 0,80, PV=3 kW, dom=1 kW, bateria może się ładować → eksport dozwolony, ale wybór magazynowania/eksportu zależy od pełnego planu.
- `PVE-09`: cena poniżej progu, Deye przełącznik już OFF → brak powtórnego zapisu.
- `PVE-10`: cena powyżej progu, Deye przełącznik już ON → brak powtórnego zapisu.
- `PVE-11`: przejście z 0,39 na 0,41 → jedna zamierzona zmiana OFF→ON, o ile istnieje live approval i kompletne warunki wykonawcy.
- `PVE-12`: nieznana/stara cena lub `raw_today` z luką → nie wydawać automatycznej komendy przełącznika, zgłosić brak danych.
- `PVE-13`: wysoka cena eksportu i SOC pozwala na rozładowanie do domu, lecz brak zgody na eksport baterii → brak planowanego `b_x`, także gdy `solar_sell=ON`.
- `PVE-14`: `switch.sun12k_solar_sell` ON bez zweryfikowanej fizycznej separacji od eksportu baterii → brak zezwolenia na ryzykowny zapis w live; monitor/dry-run nadal pokazują decyzję polityki.
- `PVE-15`: HA przerwany po ustawieniu OFF → diagnostyka możliwej utraty eksportu, bez fikcyjnego twierdzenia, że Deye automatycznie włączy go ponownie.
- `PVE-16`: ceny na jutro nieopublikowane → nie programować jutra arbitralną ceną; replan dopiero po otrzymaniu prawidłowych cen.
- `PVE-17`: piętnaście minut po poprzedniej decyzji cena i stan pozostają identyczne → zero zbędnych zapisów switch.
- `PVE-18`: aktywny przyszły slot ma cenę sprzedaży 0,35 i sam PV mógłby przynieść przychód → zakaz eksportu zgodnie z **wybranym przez użytkownika progiem**, mimo dodatniej ceny.
- `PVE-19`: cena −0,10 → eksport OFF, cena pozostaje −0,10 bez obcinania do zera.
- `PVE-20`: dobrowolny ręczny tryb `monitor/dry_run` → propozycja ON/OFF i log, **bez** wywołania usługi HA.
- `PVE-21`: `raw_today.price=0,400` i potwierdzony bieżący `current_price=0,3996` → `PRICE_THRESHOLD_AMBIGUOUS`, brak komendy ON; test włącznego progu tylko przy zgodnych odczytach.
- `PVE-22`: przełącznik pozostał ON po utracie HA i w kolejnej godzinie cena spadła do 0,20 → stan ryzyka, bez fałszywej gwarancji OFF; po odzyskaniu HA wymagane sprawdzenie obecnego stanu i ceny przed dalszymi akcjami.

**Warunek odbioru:** testy sprawdzają użycie **niezmienionej ceny z HA** i autonomię tylko dla PV. Nie implementować żadnego rozliczania prowizji, podatków, taryf ani innych korekt cenowych.
