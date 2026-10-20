# Pomocniczy odczyt HA: atrybuty prognoz PV

**Stan na 20.10.2026:** **format obu serii cen jest już potwierdzony** bezpośrednio na atrybutach HA i zamknięty w [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md). Nie wymaga dalszych pytań do użytkownika. Ten starszy szablon zachowujemy tylko jako pomoc w odczycie **godzinowych prognoz PV**, których struktury jeszcze nie pokazano. Dane cenowe z szablonu są zbędne do ponownej walidacji.

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

1. **Ceny: zamknięte** — obie encje mają `raw_today/raw_tomorrow` oraz flagę `tomorrow_valid`; patrz [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md).
2. Ustalić, czy Forecast.Solar dostarcza godzinowy rozkład `wh_hours`/`wh_period` lub podobny, z datami i jednostkami oraz jaki jest punkt pomiaru PV.
3. `sensor.pv_forecast_next_24h`: ustalić jednostkę i okres albo **nie** mapować do bilansu.

Nie pobierać pełnych stanów innych urządzeń. Brak atrybutów prognoz oznacza, że trzeba znaleźć źródłową encję/integrację Forecast.Solar lub price series, ale **nie** wypełniać ich prognozami wymyślonymi przez model.
