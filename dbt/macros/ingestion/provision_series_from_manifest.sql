{% macro provision_series_from_manifest() %}
    {#
    Provision the ingestion infrastructure for all series defined in the manifest.
    
    Iterates over manifest targets and calls provision_target_pipeline for each.
    #}
    {% set manifest = load_manifest_safely() %}

    {% if manifest and manifest.get('series') %}
        {% for series_id, series in manifest['series'].items() %}
            {% if series.get('targets') %}
                {% for target in series['targets'] %}
                    {% set sub_dataset_id = target.get('sub_dataset_id', series_id) %}
                    {{ provision_target_pipeline(series_id, sub_dataset_id, target) }}
                {% endfor %}
            {% endif %}
        {% endfor %}
        {{ log('✓ All series provisioned', info=true) }}
    {% else %}
        {{ log('⚠ No manifest or series found', info=true) }}
    {% endif %}
{% endmacro %}
