# Integracja Home Assistant — REST API, autoryzacja i akcje

Dokument rozdziela historyczne fakty projektu od **aktualnej dokumentacji API Home Assistant**.  
Źródło oficjalne: https://developers.home-assistant.io/docs/api/rest/ (sprawdzone 15.10.2026).

## 1. Historyczny klient

W pierwotnych rozmowach wykorzystywano `HomeAssistantAPI` (wspomniany również plik `agent.py`):
- konfiguracja YAML: `home_assistant.url`, `home_assistant.token`, `home_assistant.verify_ssl`;
- sesja `requests.Session` i nagłówek `Authorization: Bearer ...`;
- metoda `call_service()` kierująca żądania `POST /api/services/{domain}/{service}`;
- historycznie wykonano test `light.turn_on` dla `light.gang_led_swiatlo`, co dowodziło działania wywołania usługi, **a nie poprawnej integracji energetycznej**;
- późniejsza wersja `v5.2` próbowała importować `ha_api_client`, lecz ten moduł nie istniał (`ModuleNotFoundError`);
- próbę uzupełnienia klienta o `get_entity_state()` zaproponowano, ale brak potwierdzenia poprawnego wdrożenia.

### Historyczna struktura config.yaml (schemat, bez wartości)

```yaml
home_assistant:
  url: "<URL_INSTANCJI_HA>"
  token: "<LONG_LIVED_ACCESS_TOKEN>"
  verify_ssl: true  # w oryginalnym config: pole istniało, jego wartość nieustalona
```

**Powyżej jest przykład struktury, nie odzyskany plik konfiguracyjny.** W repo nie zapisujemy tokenu ani prywatnego adresu użytkownika.

## 2. API HA — fakty z oficjalnej dokumentacji

| Operacja | HTTP | Ścieżka |
| --- | --- | --- |
| Sprawdzenie API | GET | `/api/` |
| Odczyt wszystkich stanów | GET | `/api/states` |
| Odczyt stanu encji | GET | `/api/states/{entity_id}` |
| Odczyt historii | GET | `/api/history/period/{timestamp}?filter_entity_id=...` |
| Lista usług | GET | `/api/services` |
| Wywołanie usługi | POST | `/api/services/{domain}/{service}` |

Nagłówki: `Authorization: Bearer TOKEN` oraz JSON przy odpowiednich żądaniach.

**Zasada krytyczna:** `POST /api/states/{entity_id}` tylko aktualizuje reprezentację stanu w HA; **nie jest poleceniem sterującym falownikiem**.

## 3. Historycznie potrzebne wyjścia sterowania — przykładowe dane do usług

Poniższe przykłady opisują **docelową postać wywołań**. **Nie były wykonane ani przetestowane na falowniku**.

### Sprzedaż energii

```text
POST /api/services/switch/turn_on
{"entity_id": "switch.sun12k_solar_sell"}
POST /api/services/switch/turn_off
{"entity_id": "switch.sun12k_solar_sell"}
```

### Ładowanie magazynu z sieci — odrębna funkcja

```text
POST /api/services/switch/turn_on
{"entity_id": "switch.sun12k_grid_charge"}
POST /api/services/switch/turn_off
{"entity_id": "switch.sun12k_grid_charge"}
```

### Limit prądu — odrębna funkcja wymagająca sprawdzenia semantyki

```text
POST /api/services/number/set_value
{"entity_id": "number.sun12k_maximum_battery_grid_charge_current", "value": 1}
```

W dokumencie logiki v5.1 wymieniano także `40 A`. **Dopuszczalnego zakresu encji, fizycznych skutków obu nastaw i kierunku energii nie potwierdzono**. Nie wolno uznać `1 A` za równoznaczne z wyłączeniem ładowania z sieci.

### Powiadomienie

Historyczny kanał `notify.mobile_app_pixel_7dk` pochodzi ze specyfikacji. Szczegóły dostępności tej usługi i sposób jej wywołania w aktualnej instalacji pozostają do weryfikacji.

## 4. Schemat odczytu stanu — przykład struktury z dokumentacji HA

```json
{
  "entity_id": "sensor.sun12k_battery_capacity",
  "state": "<WARTOSC_Z_HA>",
  "attributes": {},
  "last_changed": "<ISO_8601>",
  "last_updated": "<ISO_8601>"
}
```

To **schemat ilustrujący**, a nie odczyt realnej encji. Zwracane `state` jest zwykle tekstem — parsowanie liczb, jednostek i `attributes` należy wykonywać jawnie.

## 5. Bezpieczeństwo dostępu do urządzeń (do wdrożenia)

- **Nie publikować:** tokenów HA i LLM, prywatnych URL/IP, `config.yaml` ze sekretami, surowej historii użytkownika bez decyzji o udostępnieniu.
- Na obecnym etapie wykonywać **tylko odczyty**. Brak zweryfikowanej semantyki limitu prądu i reguł bezpieczeństwa.
- Przed zapisami ustalić zakres i skutki każdej usługi, odczytać bieżący stan i potwierdzić efekt na urządzeniu.
- Nie traktować odpowiedzi HTTP 200 za dowód osiągnięcia właściwego stanu fizycznego.
- Zdefiniować timeouty, obsługę 401/404, braków danych i `unavailable` zanim zostanie podłączony wykonawca komend.

Punkty bezpieczeństwa to **kryteria przyszłej implementacji**, nie funkcje działającej aplikacji.
