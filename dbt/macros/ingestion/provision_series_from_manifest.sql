{% macro provision_series_from_manifest(manifest_path) %}
    {#
    Provision the ingestion infrastructure for all targets defined in a dataset manifest.

    Iterates over manifest['targets'] and calls provision_target_pipeline for each.
    #}
    {% set manifest = fromyaml(read_file(manifest_path)) %}

    {% if manifest is none %}
        {{ exceptions.raise_compiler_error('Failed to parse manifest at ' ~ manifest_path) }}
    {% endif %}

    {% set series_id = manifest['series_id'] %}

    {% for target_cfg in manifest.get('targets', []) %}
        {% set sub_dataset_id = target_cfg.get('sub_dataset_id', series_id) %}
        {{ provision_target_pipeline(series_id, sub_dataset_id, target_cfg) }}
    {% endfor %}

    {{ log('✓ All targets provisioned for ' ~ series_id, info=true) }}
{% endmacro %}
