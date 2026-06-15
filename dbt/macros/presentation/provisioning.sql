{% macro provision_presentation_from_manifest(manifest_path, database_name=target.database, raw_schema=var('raw_schema'), presentation_schema=var('presentation_schema')) %}
    {% set manifest = fromyaml(read_file(manifest_path)) %}

    {% if manifest is none %}
        {{ exceptions.raise_compiler_error('Failed to parse manifest at ' ~ manifest_path) }}
    {% endif %}

    {% set outputs = [] %}
    {% for target_cfg in manifest['targets'] %}
        {% if target_cfg['object_name_suffix'] == '' %}
            {{ exceptions.raise_compiler_error('object_name_suffix is required for presentation provisioning') }}
        {% endif %}

        {% set object_suffix = target_cfg['object_name_suffix'] %}
        {% set raw_view = 'RAW_' ~ object_suffix %}
        {% set presentation_view = 'PRESENTATION_' ~ object_suffix %}
        {% set max_pub_view = 'MAX_PUBLICATION_' ~ object_suffix %}
        {% set current_revision_view = 'CURRENT_REVISION_' ~ object_suffix %}
        {% set reporting_columns = target_cfg.get('reporting_period_columns', []) %}

        {% do one_london_psds.create_presentation_view(
            database_name,
            presentation_schema,
            presentation_view,
            raw_schema,
            raw_view,
            reporting_columns
        ) %}

        {% do one_london_psds.create_max_publication_view(
            database_name,
            presentation_schema,
            max_pub_view,
            presentation_view
        ) %}

        {% do one_london_psds.create_current_revision_view(
            database_name,
            presentation_schema,
            current_revision_view,
            max_pub_view
        ) %}

        {% do outputs.append({'presentation_view': presentation_view, 'max_publication_view': max_pub_view, 'current_revision_view': current_revision_view}) %}
    {% endfor %}

    {{ return(outputs) }}
{% endmacro %}
