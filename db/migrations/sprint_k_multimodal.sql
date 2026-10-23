-- Sprint K: !UI„ÍîgLpnìh
-- /ub„X∆…yÅgLÕàå(øf`

-- /(œiUÇú*/(	
CREATE EXTENSION IF NOT EXISTS vector;

-- ub„Xh
CREATE TABLE IF NOT EXISTS page_understanding_cache (
    id BIGSERIAL PRIMARY KEY,
    page_id TEXT UNIQUE NOT NULL,
    url_hash TEXT NOT NULL,
    visual_hash TEXT NOT NULL,
    screenshot_path TEXT,

    -- ub{·o
    page_type TEXT NOT NULL,
    page_type_confidence FLOAT NOT NULL DEFAULT 0.0,
    layout_pattern TEXT,

    -- çÑ„”ú
    understanding_data JSONB NOT NULL,
    visual_features JSONB,
    text_features JSONB,
    geometric_features JSONB,
    interaction_zones JSONB,

    -- '˝å(œ
    fusion_confidence FLOAT NOT NULL DEFAULT 0.0,
    processing_time_ms INT DEFAULT 0,
    fusion_version TEXT DEFAULT '1.0.0',

    -- ˆÙå«
    created_at TIMESTAMPTZ DEFAULT now(),
    last_accessed TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT now() + INTERVAL '24 hours',
    access_count INT DEFAULT 0,

    -- "
    INDEX(url_hash, visual_hash),
    INDEX(page_type),
    INDEX(expires_at),
    INDEX(last_accessed),
    INDEX(fusion_confidence)
);

-- ∆…yÅ"h
CREATE TABLE IF NOT EXISTS visual_features_index (
    id BIGSERIAL PRIMARY KEY,
    page_id TEXT NOT NULL,
    screenshot_hash TEXT UNIQUE NOT NULL,

    -- œyÅ(é¯<'"	
    layout_features_vector vector(512),
    color_features_vector vector(64),
    element_distribution_vector vector(128),

    -- ”ÑyÅ
    layout_features JSONB,
    color_palette JSONB,
    element_distribution JSONB,
    contrast_ratio FLOAT,
    visual_complexity FLOAT,

    created_at TIMESTAMPTZ DEFAULT now(),

    -- "
    INDEX(screenshot_hash),
    INDEX(page_id)
);

-- UIC ≠√7,h
CREATE TABLE IF NOT EXISTS ui_training_samples (
    id BIGSERIAL PRIMARY KEY,
    screenshot_hash TEXT NOT NULL,
    screenshot_path TEXT,

    -- C Ë·o
    element_bbox JSONB NOT NULL, -- [x, y, width, height]
    element_type TEXT NOT NULL,
    element_subtype TEXT,
    element_properties JSONB,

    -- Ë(œ
    user_label TEXT,
    confidence FLOAT DEFAULT 0.0,
    validated BOOLEAN DEFAULT false,
    validation_source TEXT, -- 'user', 'expert', 'model'

    -- 
á·o
    page_context JSONB,
    surrounding_elements JSONB,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    -- "
    INDEX(screenshot_hash),
    INDEX(element_type, validated),
    INDEX(confidence),
    INDEX(created_at)
);

-- gLÕàh
CREATE TABLE IF NOT EXISTS execution_feedback (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    page_id TEXT,
    execution_step_id TEXT,

    -- Õà{ãåÖπ
    feedback_type TEXT NOT NULL, -- 'explicit', 'implicit', 'system', 'correction'
    rating INT CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,

    -- †cpn
    correction_data JSONB,
    suggested_action JSONB,
    actual_action JSONB,

    -- ê·˜
    implicit_signals JSONB,
    user_behavior JSONB,

    -- gL
á
    execution_context JSONB,
    page_understanding JSONB,
    strategy_used TEXT,

    -- (7·o
    user_id BIGINT,
    device_id TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),

    -- "
    INDEX(session_id),
    INDEX(page_id),
    INDEX(feedback_type, created_at),
    INDEX(user_id, device_id),
    INDEX(rating)
);

-- A/Bûåh
CREATE TABLE IF NOT EXISTS ab_experiments (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,

    -- ûåMn
    experiment_type TEXT NOT NULL, -- 'strategy', 'ui_understanding', 'parameter'
    variants JSONB NOT NULL,
    traffic_split JSONB NOT NULL,

    -- ü
    success_metrics JSONB,
    primary_metric TEXT,

    -- ûå∂åˆÙ
    status TEXT DEFAULT 'draft', -- 'draft', 'running', 'completed', 'paused', 'cancelled'
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,

    -- 7,'åüH
    target_sample_size INT,
    minimum_effect_size FLOAT,
    confidence_level FLOAT DEFAULT 0.95,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    -- "
    INDEX(status, start_date),
    INDEX(experiment_type),
    INDEX(name)
);

-- A/BûåMh
CREATE TABLE IF NOT EXISTS ab_experiment_assignments (
    id BIGSERIAL PRIMARY KEY,
    experiment_id BIGINT NOT NULL REFERENCES ab_experiments(id),

    -- (7∆
    user_id BIGINT,
    device_id TEXT,
    session_id TEXT,

    -- M·o
    variant_name TEXT NOT NULL,
    variant_config JSONB,
    assignment_time TIMESTAMPTZ DEFAULT now(),

    -- ûå”ú
    conversion_events JSONB,
    success_metrics_values JSONB,

    -- ∂
    completed BOOLEAN DEFAULT false,
    excluded BOOLEAN DEFAULT false,
    exclusion_reason TEXT,

    -- "
    UNIQUE(experiment_id, user_id, device_id),
    INDEX(experiment_id, variant_name),
    INDEX(assignment_time),
    INDEX(completed, excluded)
);

-- !ãH,h
CREATE TABLE IF NOT EXISTS model_versions (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    model_type TEXT NOT NULL, -- 'layout_classifier', 'success_predictor', 'parameter_optimizer'

    -- !ã·o
    algorithm TEXT,
    hyperparameters JSONB,
    training_config JSONB,

    -- '˝
    performance_metrics JSONB,
    validation_scores JSONB,
    benchmark_results JSONB,

    -- !ãáˆ
    model_artifacts_path TEXT,
    model_size_bytes BIGINT,

    -- ≠√pn
    training_data_hash TEXT,
    training_data_size INT,
    training_duration_seconds INT,

    -- Ër·o
    status TEXT DEFAULT 'training', -- 'training', 'validated', 'deployed', 'deprecated', 'failed'
    deployment_config JSONB,
    deployment_timestamp TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    -- ¶_å"
    UNIQUE(model_name, version),
    INDEX(model_type, status),
    INDEX(created_at),
    INDEX(performance_metrics) -- ˘JSONB˙ÀGIN"
);

-- ÍîgL∞Uh
CREATE TABLE IF NOT EXISTS adaptive_execution_logs (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    page_id TEXT,

    -- Ve	È
    available_strategies JSONB,
    selected_strategy TEXT NOT NULL,
    strategy_selection_reason JSONB,
    strategy_confidence FLOAT,

    -- ¬p
    default_parameters JSONB,
    optimized_parameters JSONB,
    optimization_method TEXT,
    parameter_confidence FLOAT,

    -- gL—ß
    execution_start_time TIMESTAMPTZ DEFAULT now(),
    execution_end_time TIMESTAMPTZ,
    execution_duration_ms INT,

    -- gL”ú
    success BOOLEAN,
    failure_reason TEXT,
    intermediate_results JSONB,
    final_result JSONB,

    -- —ß
    performance_metrics JSONB,
    resource_usage JSONB,

    -- f`·˜
    learning_signals JSONB,
    model_updates JSONB,

    created_at TIMESTAMPTZ DEFAULT now(),

    -- "
    INDEX(session_id),
    INDEX(page_id),
    INDEX(selected_strategy),
    INDEX(success, execution_start_time),
    INDEX(created_at)
);

-- (øf`∂h
CREATE TABLE IF NOT EXISTS online_learning_state (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT UNIQUE NOT NULL,

    -- f`∂
    learning_enabled BOOLEAN DEFAULT true,
    learning_rate FLOAT DEFAULT 0.01,
    batch_size INT DEFAULT 32,

    -- !ãCÕÄX®	
    current_weights JSONB,
    weight_update_count BIGINT DEFAULT 0,

    -- '˝ﬂ*
    recent_performance JSONB,
    performance_history JSONB,

    -- f`pnﬂ°
    total_samples_processed BIGINT DEFAULT 0,
    positive_samples INT DEFAULT 0,
    negative_samples INT DEFAULT 0,

    -- ˆÙ·o
    last_update_time TIMESTAMPTZ DEFAULT now(),
    last_performance_check TIMESTAMPTZ DEFAULT now(),

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    -- "
    INDEX(model_name),
    INDEX(learning_enabled),
    INDEX(last_update_time)
);

-- ub¯<'"h(éÎ¿"¯<ub	
CREATE TABLE IF NOT EXISTS page_similarity_index (
    id BIGSERIAL PRIMARY KEY,
    page_id_1 TEXT NOT NULL,
    page_id_2 TEXT NOT NULL,

    -- ¯<'p
    visual_similarity FLOAT,
    layout_similarity FLOAT,
    content_similarity FLOAT,
    overall_similarity FLOAT,

    -- °óπ’
    similarity_method TEXT DEFAULT 'cosine',
    computed_at TIMESTAMPTZ DEFAULT now(),

    -- ¶_å"
    UNIQUE(page_id_1, page_id_2),
    INDEX(overall_similarity DESC),
    INDEX(page_id_1),
    INDEX(page_id_2)
);

-- ˙Ê—hÍ®Ù∞ updated_at Wµ
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- : ÅÑh˚†Ù∞Ê—h
CREATE TRIGGER update_ui_training_samples_updated_at
    BEFORE UPDATE ON ui_training_samples
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ab_experiments_updated_at
    BEFORE UPDATE ON ab_experiments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_model_versions_updated_at
    BEFORE UPDATE ON model_versions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_online_learning_state_updated_at
    BEFORE UPDATE ON online_learning_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ub„X˝p
CREATE OR REPLACE FUNCTION cleanup_expired_page_cache()
RETURNS void AS $$
BEGIN
    --  d«Ñub„X
    DELETE FROM page_understanding_cache WHERE expires_at < now();

    --  dˆÙ*øÓÑXÖ«7)	
    DELETE FROM page_understanding_cache
    WHERE last_accessed < now() - INTERVAL '7 days';

    -- Ù∞øÓﬂ°
    UPDATE page_understanding_cache
    SET last_accessed = now(), access_count = access_count + 1
    WHERE last_accessed < now() - INTERVAL '1 hour';
END;
$$ language 'plpgsql';

-- ub¯<'°ó˝p
CREATE OR REPLACE FUNCTION compute_page_similarity(
    page_id_a TEXT,
    page_id_b TEXT
) RETURNS FLOAT AS $$
DECLARE
    similarity_score FLOAT := 0.0;
    features_a JSONB;
    features_b JSONB;
BEGIN
    -- ∑÷$*ubÑyÅ
    SELECT visual_features INTO features_a
    FROM page_understanding_cache WHERE page_id = page_id_a;

    SELECT visual_features INTO features_b
    FROM page_understanding_cache WHERE page_id = page_id_b;

    -- ÄÑ¯<'°óûEî(- ÅÙBÑó’	
    IF features_a IS NOT NULL AND features_b IS NOT NULL THEN
        -- ŸÃîÂû∞wSÑyÅ¯<'°ó
        -- ÓM‘ﬁè:<\:`M&
        similarity_score := random();
    END IF;

    RETURN similarity_score;
END;
$$ language 'plpgsql';

-- (øf`∂Ù∞˝p
CREATE OR REPLACE FUNCTION update_online_learning_performance(
    model_name_param TEXT,
    new_performance JSONB
) RETURNS void AS $$
BEGIN
    INSERT INTO online_learning_state (
        model_name,
        recent_performance,
        last_performance_check
    ) VALUES (
        model_name_param,
        new_performance,
        now()
    )
    ON CONFLICT (model_name)
    DO UPDATE SET
        recent_performance = new_performance,
        last_performance_check = now(),
        updated_at = now();
END;
$$ language 'plpgsql';

-- A/Bûå”úê˝p
CREATE OR REPLACE FUNCTION analyze_ab_experiment_results(
    experiment_id_param BIGINT
) RETURNS JSONB AS $$
DECLARE
    result JSONB := '{}';
    variant_stats JSONB;
BEGIN
    -- °óÿSÑﬂ°pn
    SELECT jsonb_object_agg(
        variant_name,
        jsonb_build_object(
            'sample_size', COUNT(*),
            'conversion_rate',
            COUNT(*) FILTER (WHERE completed = true)::FLOAT / COUNT(*),
            'avg_success_score',
            AVG((success_metrics_values->>'primary_score')::FLOAT)
        )
    ) INTO variant_stats
    FROM ab_experiment_assignments
    WHERE experiment_id = experiment_id_param
      AND excluded = false
    GROUP BY variant_name;

    result := jsonb_build_object(
        'experiment_id', experiment_id_param,
        'variant_statistics', variant_stats,
        'analysis_timestamp', extract(epoch from now()),
        'total_participants', (
            SELECT COUNT(*)
            FROM ab_experiment_assignments
            WHERE experiment_id = experiment_id_param
              AND excluded = false
        )
    );

    RETURN result;
END;
$$ language 'plpgsql';

-- ÁpnÑ˝p
CREATE OR REPLACE FUNCTION cleanup_old_sprint_k_data()
RETURNS void AS $$
BEGIN
    -- «Ñub„X
    PERFORM cleanup_expired_page_cache();

    -- ÁÑgLÂ◊›Y —30)	
    DELETE FROM adaptive_execution_logs
    WHERE created_at < now() - INTERVAL '30 days';

    -- ÁÑÕàpn›Y —90)	
    DELETE FROM execution_feedback
    WHERE created_at < now() - INTERVAL '90 days';

    -- ÁÑ≠√7,›Yå¡«Ñ7,	
    DELETE FROM ui_training_samples
    WHERE created_at < now() - INTERVAL '180 days'
      AND validated = false;

    -- åÑA/Bûåpn›Y”úﬂ°	
    DELETE FROM ab_experiment_assignments
    WHERE experiment_id IN (
        SELECT id FROM ab_experiments
        WHERE status = 'completed'
          AND end_date < now() - INTERVAL '365 days'
    );
END;
$$ language 'plpgsql';

-- ˚†hË 
COMMENT ON TABLE page_understanding_cache IS 'Sprint K: ub„XhX®!çÑub„”ú';
COMMENT ON TABLE visual_features_index IS 'Sprint K: ∆…yÅ"h/˙éœÑ¯<'"';
COMMENT ON TABLE ui_training_samples IS 'Sprint K: UIC ≠√7,h(é!ã≠√åå¡';
COMMENT ON TABLE execution_feedback IS 'Sprint K: gLÕàh6∆(7å˚ﬂÕà(é(øf`';
COMMENT ON TABLE ab_experiments IS 'Sprint K: A/Bûåh°ÕÍîVeûå';
COMMENT ON TABLE model_versions IS 'Sprint K: !ãH,h°:hf`!ãÑH,åËr';
COMMENT ON TABLE adaptive_execution_logs IS 'Sprint K: ÍîgLÂ◊h∞UVe	Èå¬p«';
COMMENT ON TABLE online_learning_state IS 'Sprint K: (øf`∂hÙ§!ãÑûœf`∂';