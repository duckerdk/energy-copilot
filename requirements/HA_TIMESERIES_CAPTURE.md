# Następny odczyt HA: atrybuty przyszłych cen i prognoz

**Cel:** jednorazowo ustalić strukturę listy cen (czas, waluta, VAT/taryfy, dostępność jutra) i godzinowy profil potencjalnej produkcji PV. Poprzedni odczyt `wynik.txt` potwierdził bieżące `entity_id` i wartości, **nie pobierał atrybutów prognoz**.

Home Assistant → **Narzędzia deweloperskie → Szablony**. Wkleić poniższy szablon, wynik skopiować do pliku `ceny_prognozy.txt` i udostępnić. Działanie jest **wyłącznie odczytowe**, nie zmienia żadnej encji, nie wywołuje usług.

```jinja
{% set ids = [
  'sensor.energi_data_spotpris',
  'sensor.energi_data_service',
  'sensor.energy_production_today',
  'sensor.energy_production_today_remaining',
  'sensor.energy_production_tomorrow',
  'sensor.pv_forecast_next_24h'
] %}
{% set omit = ['friendly_name', 'icon', 'device_class',
               'state_class', 'attribution', 'unit_of_measurement'] %}
{% set keywords = ['price', 'pris', 'spot', 'tarif', 'tax', 'fee',
                  'forecast', 'today', 'tomorrow', 'period',
                  'hour', 'wh_', 'next', 'valid', 'start',
                  'end', 'raw', 'data', 'time', 'cost'] %}
{% set ns = namespace(records=[]) %}
{% for s in expand(ids) %}
  {% set attr = namespace(items=[]) %}
  {% for k, v in s.attributes.items() %}
    {% if k not in omit %}
      {% if v is mapping %}
        {% set desc = {
          'key': k, 'kind': 'mapping', 'length': v|count,
          'first_keys': (v.keys()|list)[:3],
          'last_keys': (v.keys()|list)[-3:],
          'first_item': ((v.items()|list)[0] if v|count else none)
        } %}
      {% elif v is sequence and v is not string %}
        {% set desc = {
          'key': k, 'kind': 'sequence', 'length': v|count,
          'first': v[:3], 'last': v[-3:]
        } %}
      {% else %}
        {% set desc = {
          'key': k, 'kind': 'scalar',
          'value': v if (keywords | select('in', k|lower) | list | count) else '<omitted>'
        } %}
      {% endif %}
      {% set attr.items = attr.items + [desc] %}
    {% endif %}
  {% endfor %}
  {% set ns.records = ns.records + [{
    'entity_id': s.entity_id,
    'state': s.state,
    'unit': s.attributes.get('unit_of_measurement'),
    'attributes': attr.items
  }] %}
{% endfor %}
{{ ns.records | tojson }}
```

**Prywatność:** wynik obejmuje tylko sześć wybranych sensorów i **fragmenty** ich atrybutów. Przed przesłaniem sprawdzić, czy atrybut nie zawiera lokalizacji, danych konta, prywatnego adresu URL lub tokenu — taki fragment usunąć. Odczyt nie zawiera historii domowników.

## Na podstawie wyniku sprawdzimy

1. Czy `sensor.energi_data_service` udostępnia serię przyszłych cen **końcowych**, czy jedynie wartość bieżącą i czy VAT/taryfy są rzeczywiście wliczone.
2. Czy `sensor.energi_data_spotpris` lub odpowiedni atrybut zawiera timestampowane spot na dziś/jutro, rozdzielczość i czas dostępności.
3. Czy Forecast.Solar dostarcza rozkład godzinowy `wh_hours`/`wh_period` lub podobny, z datami; jaki jest właściwy punkt pomiaru PV.
4. Czy `sensor.pv_forecast_next_24h` ma określoną jednostkę i okres, a jeśli nie — nie mapować go do modelu.
5. Czy wymagany jest kolejny **wąski** odczyt jednej listy po poznaniu jej rzeczywistych kluczy, czy wszystkie dane można mapować bez dalszego pytania.

Nie pobierać pełnych stanów innych urządzeń. Brak atrybutów prognoz oznacza, że trzeba znaleźć źródłową encję/integrację Forecast.Solar lub price series, ale **nie** wypełniać ich prognozami wymyślonymi przez model.
