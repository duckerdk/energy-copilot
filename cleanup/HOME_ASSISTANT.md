# Lista do usunięcia / odłączenia — Home Assistant

**Stan wiedzy: 15.10.2026.** Oparto na dokumentacji starego projektu i wcześniejszych ręcznych uruchomieniach. **Nie połączono się z żywym HA i niczego w nim nie usunięto.**

## Zasada

Usunąć można **wyłącznie elementy utworzone specjalnie dla starego Energy Co-Pilot**, które nie są wykorzystywane gdzie indziej. Stare skrypty były wykonywane na serwerze jako Python/REST. **Brak potwierdzenia instalacji specjalnej integracji, automatyzacji lub skryptu Home Assistant.** Samo istnienie encji w dokumencie nie znaczy, że została utworzona przez projekt.

## A. Do sprawdzenia i ewentualnego usunięcia

- [ ] **Dedykowane automatyzacje** oznaczone `Energy Co-Pilot`, `energy-copilot`, `PV Agent`, `AI Operator` (Ustawienia → Automatyzacje i sceny): usuwać tylko po weryfikacji celu i wyzwalaczy. **Dotąd nie potwierdzono żadnej nazwy**.
- [ ] **Dedykowane skrypty HA** sterujące falownikiem w imieniu starego projektu (Automatyzacje i sceny → Skrypty): tylko jeśli rzeczywiście istnieją i nie są używane przez inne automatyzacje.
- [ ] **Własne helpery** (np. `input_boolean`, `input_number`, `input_text`) dodane **wyłącznie** dla planera. Brak ustalonych identyfikatorów; nie kasować helperów falownika ani innych instalacji.
- [ ] **Wpisy YAML** w `configuration.yaml`, `automations.yaml`, `scripts.yaml`, `packages/`, `python_scripts/` dotyczące wyłącznie Co-Pilot (`shell_command`, `command_line`, `rest_command`, `template` lub skrypty). **Nie potwierdzono ich istnienia**.
- [ ] **Dedykowane add-ony / kontenery / integracje HACS**, jeśli nazwą lub konfiguracją wskazują na własny backend Energy Co-Pilot. **Brak dowodu, że były instalowane**.
- [ ] **Dashboard/karty** utworzone tylko do sterowania starym agentem. Nie kasować głównego panelu Energy ani kart pomiarów bez osobnej decyzji.
- [ ] **Long-lived access token** wydany wyłącznie dla Co-Pilot: wycofać po potwierdzeniu, że nie używają go inne skrypty/integracje. Historyczny plik serwera `config.yaml` zawierał pole `home_assistant.token`, ale nie mamy jego wartości ani informacji, czy był współdzielony. Token usuwa się z profilu konta HA; nie należy publikować go w GitHub.

**Jeżeli żaden z powyższych elementów nie istnieje, lista rzeczy do usunięcia z HA może być pusta.** To prawidłowy wynik, nie powód do skasowania encji.

## B. Zachować — wymienione identyfikatory nie są „śmieciami po projekcie”

| Identyfikator | Powód, aby nie usuwać |
| --- | --- |
| `sensor.energi_data_spotpris` | Cena spot; może służyć innym automatyzacjom lub nowemu systemowi |
| `sensor.energi_data_service` | Źródło prognozy cen |
| `sensor.sun12k_battery_capacity` | Stan baterii |
| `sensor.pv_sum` | Produkcja PV |
| `sensor.home_energy_consumption` | Zużycie domu |
| `sensor.energy_production_today` | Prognoza PV na dziś |
| `sensor.energy_production_tomorrow` | Prognoza PV na jutro |
| `switch.sun12k_solar_sell` | Fizyczna funkcja eksportu falownika |
| `switch.sun12k_grid_charge` | Fizyczna funkcja ładowania z sieci |
| `number.sun12k_maximum_battery_grid_charge_current` | Parametr sprzętowy; znaczenie wymaga potwierdzenia |
| `notify.mobile_app_pixel_7dk` | Ogólna usługa aplikacji mobilnej |

**Nie usuwać urządzenia/integracji falownika, pomiarów sieciowych, monitoringu energii, integracji cenowej ani prognoz PV** wyłącznie z powodu zakończenia starego projektu. `light.gang_led_swiatlo` był tylko testową lampą podczas próby API — również go nie usuwać.

## C. Procedura bezpiecznego uporządkowania

1. [ ] Wyszukać nazwy Energy Co-Pilot w UI HA i własnych plikach YAML. Zanotować tylko **rzeczywiście istniejące** elementy.
2. [ ] Przed usuwaniem sprawdzić, czy coś jest obecnie wywoływane przez automatyzację, skrypt lub inny system.
3. [ ] Wyłączyć (nie usuwać od razu) jedynie dedykowane automatyzacje i obserwować czy nic się nie psuje.
4. [ ] Przed zmianami zachować kopię ustawień HA; sekretów i backupu nie publikować w repo publicznym.
5. [ ] Usunąć potwierdzone osierocone obiekty; ewentualnie unieważnić **dedykowany** token.
6. [ ] Potwierdzić, że falownik, sensory, rejestrator historii i inne automatyzacje nadal działają.

## Stan weryfikacji

| Pozycja | Wynik |
| --- | --- |
| Dedykowane encje utworzone przez Energy Co-Pilot | **Nie zidentyfikowano** |
| Dedykowane automatyzacje / helpery / skrypty HA | **Niepotwierdzone** |
| Historyczna komunikacja | **Python + REST HA; odnotowano test światła** |
| Usuwanie w HA | **Nie wykonano** |

Archiwum techniczne: [Rejestr HA](../archive/energy-copilot-v5/docs/ENTITIES.md).
