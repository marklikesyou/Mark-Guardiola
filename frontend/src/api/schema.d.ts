export interface paths {
    "/api/v1/admin/data/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["refreshData"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getAdminJob"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/models/train": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["trainModels"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/fixtures/upcoming": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["listUpcomingFixtures"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["listLeagues"];
        put?: never;

        post: operations["createLeague"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getLeague"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;

        patch: operations["updateLeagueSettings"];
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/market/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["importMarket"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/players/{player_id}/outlook": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["getPlayerLeagueOutlook"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/recommendations/lineup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["recommendLineup"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/recommendations/market": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["recommendMarket"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/recommendations/matchup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["recommendMatchup"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/rosters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["listLeagueRosters"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/rosters/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;

        post: operations["importRoster"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;

        put: operations["replaceLeagueRules"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/leagues/{league_id}/teams/{fantasy_team_id}/budget": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;

        put: operations["updateFantasyTeamBudget"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/matches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["listMatches"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/players": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["listPlayers"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/players/{player_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getPlayer"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/players/{player_id}/recent-form": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getPlayerRecentForm"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/predictions/fixture/{match_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getFixturePredictions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/predictions/player/{player_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getPlayerPredictions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["getSystemStatus"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/teams": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["listTeams"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };

        get: operations["ready"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {

        BenchPlayerView: {

            display_name: string;

            photo_url?: string | null;

            player_id: string;

            roles: string[];

            utility: number;
        };

        BudgetView: {

            effective_at: string;

            fantasy_team_id: string;

            remaining_credits: string;

            total_credits: string;
        };

        BudgetWrite: {

            remaining_credits: number | string;
        };

        ExplanationView: {

            confidence: number;

            evidence_key: string;

            source_feature: string;

            text: string;
        };

        FantasyTeamView: {

            id: string;

            is_user_team: boolean;

            name: string;

            remaining_credits?: string | null;
        };

        FixturePrediction: {

            data_cutoff: string;
            match: components["schemas"]["MatchSummary"];

            players: components["schemas"]["PlayerFixturePrediction"][];

            prediction_cutoff: string;

            prediction_run_id: string;
        };

        Formation: {

            name: string;

            slots: string[];
        };

        FreshnessView: {

            latest_model_training: string | null;

            latest_prediction_cutoff: string | null;

            latest_successful_ingestion: string | null;
        };

        HTTPValidationError: {

            detail?: components["schemas"]["ValidationError"][];
        };

        HealthResponse: {

            service?: string;

            status?: "ok";

            timestamp: string;

            version: string;
        };

        ImportPlayer: {

            name: string;

            player_id?: string | null;

            purchase_price?: number | string | null;

            role?: string | null;

            team?: string | null;
        };

        ImportResolutionView: {

            candidates: components["schemas"]["ResolutionCandidateView"][];

            confidence: number;

            imported_name: string;

            selected_player_id: string | null;

            status: "resolved" | "ambiguous" | "unresolved";
        };

        ImportResult: {

            fantasy_team_id?: string | null;

            resolutions: components["schemas"]["ImportResolutionView"][];

            resolved_count: number;

            unresolved_count: number;
        };

        JobCreate: {

            parameters?: {
                [key: string]: unknown;
            };
        };

        JobStatus: "queued" | "running" | "succeeded" | "failed" | "cancelled";

        JobView: {

            completed_at: string | null;

            error: string | null;

            id: string;

            job_type: string;

            parameters: {
                [key: string]: unknown;
            };

            progress: number;

            queue_job_id: string | null;

            queued_at: string;

            result: {
                [key: string]: unknown;
            } | null;

            started_at: string | null;
            status: components["schemas"]["JobStatus"];
        };

        KickoffPrecision: "unknown" | "date" | "minute";

        LeagueCreate: {

            competition_id?: string | null;

            head_to_head_enabled?: boolean;

            local_identity?: string;
            mode: components["schemas"]["LeagueMode"];

            name: string;

            owner_display_name?: string;

            season_id?: string | null;

            team_name?: string;

            timezone?: string;

            total_credits?: number | string;
        };

        LeagueMode: "classic" | "mantra";

        LeaguePage: {

            items: components["schemas"]["LeagueSummary"][];
            meta: components["schemas"]["PageMeta"];
        };

        LeagueRulesView: {

            effective_from: string;

            formations?: components["schemas"]["Formation"][] | null;
            roster_constraints?: components["schemas"]["RosterConstraints"];
            scoring?: components["schemas"]["ScoringRules"];
            substitution_rules?: components["schemas"]["SubstitutionRules"];

            version: number;
        };

        LeagueRulesWrite: {

            formations?: components["schemas"]["Formation"][] | null;
            roster_constraints?: components["schemas"]["RosterConstraints"];
            scoring?: components["schemas"]["ScoringRules"];
            substitution_rules?: components["schemas"]["SubstitutionRules"];
        };

        LeagueSettingsWrite: {

            head_to_head_enabled?: boolean | null;

            name?: string | null;
        };

        LeagueSummary: {

            head_to_head_enabled: boolean;

            id: string;
            mode: components["schemas"]["LeagueMode"];

            name: string;
        };

        LeagueView: {

            competition_id: string | null;

            fantasy_teams: components["schemas"]["FantasyTeamView"][];

            head_to_head_enabled: boolean;

            id: string;
            mode: components["schemas"]["LeagueMode"];

            name: string;

            owner_user_id: string;
            rules: components["schemas"]["LeagueRulesView"];

            season_id: string | null;

            timezone: string;
        };

        LineupRecommendationRequest: {

            bench_size?: number | null;

            fantasy_team_id?: string | null;

            risk_mode?: components["schemas"]["RiskMode"];
        };

        LineupRecommendationView: {

            bench: components["schemas"]["BenchPlayerView"][];

            confidence: number;

            data_cutoff: string;

            decision_cutoff: string;

            evaluated_candidates?: number;

            expected_modifier?: number;

            expected_points: number;

            expected_substitutions?: number;

            explanations: components["schemas"]["ExplanationView"][];

            fantasy_team_id: string;

            formation: string;

            global_optimality_proven?: boolean;

            optimization_method?: string;

            p10_points: number;

            p90_points: number;

            recommendation_id: string;
            risk_mode: components["schemas"]["RiskMode"];

            search_scenarios?: number;

            starters: components["schemas"]["SelectedPlayerView"][];

            warnings?: string[];
        };

        MarketImportRequest: {

            players: components["schemas"]["ImportPlayer"][];

            replace_existing?: boolean;
        };

        MarketRecommendationItem: {

            affordability?: "affordable" | "unknown";

            asking_price: number | null;

            budget_efficiency: number | null;

            confidence: number;

            evaluation_method?: string;

            expected_improvement: number;

            explanations: components["schemas"]["ExplanationView"][];

            formation_after: string;

            formation_before: string;

            formation_schedule_after?: string[];

            formation_schedule_before?: string[];

            global_optimality_proven?: boolean;

            horizon_improvements: {
                [key: string]: number;
            };

            optimization_horizon?: number;

            recommendation_id: string;

            replace_name: string;

            replace_photo_url?: string | null;

            replace_player_id: string;

            role_flexibility_delta: number;

            target_name: string;

            target_photo_url?: string | null;

            target_player_id: string;

            value_over_replacement: number;
        };

        MarketRecommendationRequest: {

            fantasy_team_id?: string | null;

            horizon?: 1 | 3 | 5 | 10;

            limit?: number;

            recover_purchase_price?: boolean;
        };

        MarketRecommendationView: {

            data_cutoff: string;

            decision_cutoff: string;

            fantasy_team_id: string;

            items: components["schemas"]["MarketRecommendationItem"][];

            remaining_budget: number | null;

            warnings?: string[];
        };

        MatchPage: {

            items: components["schemas"]["MatchSummary"][];
            meta: components["schemas"]["PageMeta"];
        };

        MatchSummary: {

            away_score: number | null;
            away_team: components["schemas"]["TeamSummary"];

            home_score: number | null;
            home_team: components["schemas"]["TeamSummary"];

            id: string;

            kickoff_at: string;

            kickoff_precision?: components["schemas"]["KickoffPrecision"];

            matchweek: number | null;

            status: string;
        };

        MatchupRecommendationRequest: {

            fantasy_team_id?: string | null;

            opponent_fantasy_team_id: string;

            seed?: number;

            simulation_count?: number;
        };

        MatchupRecommendationView: {

            draw_probability: number;
            lineup: components["schemas"]["LineupRecommendationView"];

            loss_probability: number;

            opponent_fantasy_team_id: string;

            simulation_count: number;

            win_probability: number;
        };

        ModifierBand: {

            minimum_average: number;

            points: number;
        };

        PageMeta: {

            limit: number;

            offset: number;

            total: number;
        };

        PlayerDetail: {

            active: boolean;
            current_team?: components["schemas"]["TeamSummary"] | null;

            date_of_birth: string | null;

            display_name: string;

            height_cm: number | null;

            id: string;

            nationality_code: string | null;

            photo_source?: string | null;

            photo_url?: string | null;

            preferred_foot: string | null;

            primary_position: string | null;
        };

        PlayerFixtureOutlook: {

            available: boolean;

            confidence: number;

            expected_points: number;

            explanations: components["schemas"]["ExplanationView"][];
            football: components["schemas"]["PlayerFootballOutlook"];
            match: components["schemas"]["MatchSummary"];

            median_points: number;

            p10_points: number;

            p90_points: number;

            scoring_appearance_probability: number;
        };

        PlayerFixturePrediction: {

            data_cutoff: string;
            match: components["schemas"]["MatchSummary"];

            player_id: string;

            prediction_cutoff: string;

            prediction_run_id: string;

            values: components["schemas"]["PredictionValue"][];
        };

        PlayerFootballOutlook: {

            appearance_probability: number;

            assist_probability: number;

            clean_sheet_probability: number;

            goal_probability: number;

            mean_goals_conceded: number;

            mean_minutes: number;

            mean_saves: number;

            median_minutes: number;

            p10_minutes: number;

            p90_minutes: number;

            start_probability: number;
        };

        PlayerFormMatch: {

            assists: number | null;

            base_rating: number | null;

            field_sources: {
                [key: string]: string;
            };

            goals: number | null;

            is_home: boolean;

            kickoff_at: string;

            kickoff_precision?: components["schemas"]["KickoffPrecision"];

            match_id: string;

            matchweek: number | null;

            minutes: number;
            opponent: components["schemas"]["TeamSummary"];

            shots: number | null;

            sources: components["schemas"]["PlayerStatProvenance"][];

            started: boolean;
            team: components["schemas"]["TeamSummary"];

            xa: number | null;

            xg: number | null;
        };

        PlayerOutlookRequest: {

            horizon?: number;
        };

        PlayerOutlookView: {

            data_cutoff: string;

            decision_cutoff: string;

            fixtures: components["schemas"]["PlayerFixtureOutlook"][];

            league_id: string;

            model_versions: {
                [key: string]: string;
            };

            player_id: string;

            prediction_cutoff: string;

            prediction_run_id: string;
            recommendation_score: components["schemas"]["PlayerRecommendationScore"];

            requested_horizon: number;

            roles: string[];

            rules_version: number;

            scoring_role: string | null;

            seed: number;

            simulation_count: number;

            warnings?: string[];
        };

        PlayerPage: {

            items: components["schemas"]["PlayerSummary"][];
            meta: components["schemas"]["PageMeta"];
        };

        PlayerRecentFormView: {

            as_of: string;

            coverage?: "observed_player_matches";

            data_cutoff: string | null;

            items: components["schemas"]["PlayerFormMatch"][];

            limit: number;

            player_id: string;

            warnings?: string[];
        };

        PlayerRecommendationScore: {

            objective?: "expected_points";

            scope?: "individual_next_fixture";

            unit?: "fantasy_points";

            value: number;
        };

        PlayerStatProvenance: {

            adapter_version: string;

            available_at: string;

            event_time: string;

            field_provenance: {
                [key: string]: unknown;
            };

            ingested_at: string;

            ingestion_run_id: string;

            schema_version_id: string | null;

            source_id: string;

            source_key: string;

            source_name: string;

            source_priority: number;

            source_record_id: string;

            stat_id: string;
        };

        PlayerSummary: {

            active: boolean;

            display_name: string;

            id: string;

            nationality_code: string | null;

            photo_source?: string | null;

            photo_url?: string | null;

            primary_position: string | null;
        };

        PredictionValue: {

            expected_value: number;

            median: number;

            model_version: string;

            p10: number;

            p90: number;

            probability: number | null;

            reliability: number;

            target: string;
        };

        ReadyDependency: {

            detail?: string | null;

            name: string;

            ready: boolean;
        };

        ReadyResponse: {

            dependencies: components["schemas"]["ReadyDependency"][];

            status: "ready" | "not_ready";

            timestamp: string;
        };

        ResolutionCandidateView: {

            confidence: number;

            display_name: string;

            evidence: string[];

            photo_url?: string | null;

            player_id: string;
        };

        RiskMode: "balanced" | "floor" | "upside" | "matchup";

        RosterConstraints: {

            maximum_players?: number | null;

            minimum_players?: number;

            role_limits?: {
                [key: string]: number;
            };
        };

        RosterImportRequest: {

            fantasy_team_id?: string | null;

            fantasy_team_name?: string;

            is_user_team?: boolean;

            players: components["schemas"]["ImportPlayer"][];

            remaining_credits?: number | string | null;

            replace_existing?: boolean;
        };

        RosterIssue: {

            code: "minimum_players" | "maximum_players" | "role_limits" | "missing_roles";

            message: string;
        };

        RosterPlayerView: {

            active: boolean;

            display_name: string;

            photo_url?: string | null;

            player_id: string;

            primary_position: string | null;

            purchase_price: string | null;

            roles: string[];
        };

        RosterValidation: {

            issues: components["schemas"]["RosterIssue"][];

            player_count: number;

            valid: boolean;
        };

        RosterView: {
            fantasy_team: components["schemas"]["FantasyTeamView"];

            players: components["schemas"]["RosterPlayerView"][];
            validation?: components["schemas"]["RosterValidation"] | null;
        };

        ScoringRules: {

            appearance_minimum_minutes?: number;

            assist_points?: number;

            base_rating_enabled?: boolean;

            base_rating_fallback?: number;

            clean_sheet_points?: {
                [key: string]: number;
            };

            defensive_modifier_bands?: components["schemas"]["ModifierBand"][];

            defensive_modifier_enabled?: boolean;

            defensive_modifier_roles?: ("GK" | "DEF" | "MID" | "FWD")[];

            goal_conceded_points?: {
                [key: string]: number;
            };

            goal_points?: {
                [key: string]: number;
            };

            own_goal_points?: number;

            penalty_missed_points?: number;

            penalty_saved_points?: number;

            red_card_points?: number;

            save_points?: number;

            yellow_card_points?: number;
        };

        SelectedPlayerView: {

            appearance_probability: number;

            display_name: string;

            expected_points: number;

            photo_url?: string | null;

            player_id: string;

            slot: string;
        };

        SourceStatusView: {

            capabilities: string[];

            key: string;

            latest_attempt_status: string | null;

            latest_observation: string | null;

            latest_successful_ingestion: string | null;

            name: string;

            status: "available" | "stale" | "failed" | "unconfigured" | "unavailable";
        };

        SubstitutionRules: {

            allow_formation_change?: boolean;

            bench_size?: number | null;

            maximum_substitutions?: number;
        };

        SystemStatusView: {

            champion_models: number;
            freshness: components["schemas"]["FreshnessView"];

            incompatible_champion_models?: number;

            notices?: string[];

            queued_jobs: number;

            running_jobs: number;

            sources?: components["schemas"]["SourceStatusView"][];

            status: "healthy" | "updating" | "degraded";

            unresolved_blocking_issues: number;

            unresolved_quality_issues: number;

            upcoming_fixture_count?: number;

            warnings: string[];
        };

        TeamPage: {

            items: components["schemas"]["TeamSummary"][];
            meta: components["schemas"]["PageMeta"];
        };

        TeamSummary: {

            country_code: string | null;

            id: string;

            name: string;

            short_name: string | null;
        };

        ValidationError: {

            ctx?: Record<string, never>;

            input?: unknown;

            loc: (string | number)[];

            msg: string;

            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    refreshData: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JobCreate"];
            };
        };
        responses: {

            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getAdminJob: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    trainModels: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JobCreate"];
            };
        };
        responses: {

            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    listUpcomingFixtures: {
        parameters: {
            query?: {
                team_id?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MatchPage"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    listLeagues: {
        parameters: {
            query?: {
                local_identity?: string;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeaguePage"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    createLeague: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LeagueCreate"];
            };
        };
        responses: {

            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeagueView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getLeague: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeagueView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    updateLeagueSettings: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LeagueSettingsWrite"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeagueView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    importMarket: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarketImportRequest"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportResult"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getPlayerLeagueOutlook: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
                player_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlayerOutlookRequest"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlayerOutlookView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    recommendLineup: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LineupRecommendationRequest"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LineupRecommendationView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    recommendMarket: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarketRecommendationRequest"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketRecommendationView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    recommendMatchup: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MatchupRecommendationRequest"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MatchupRecommendationView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    listLeagueRosters: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RosterView"][];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    importRoster: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RosterImportRequest"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportResult"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replaceLeagueRules: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LeagueRulesWrite"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LeagueRulesView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    updateFantasyTeamBudget: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                league_id: string;
                fantasy_team_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BudgetWrite"];
            };
        };
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BudgetView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    listMatches: {
        parameters: {
            query?: {
                team_id?: string | null;
                status?: string | null;
                from_at?: string | null;
                to_at?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MatchPage"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    listPlayers: {
        parameters: {
            query?: {
                search?: string | null;
                position?: string | null;
                active?: boolean | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlayerPage"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getPlayer: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                player_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlayerDetail"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getPlayerRecentForm: {
        parameters: {
            query?: {
                limit?: number;
                as_of?: string | null;
            };
            header?: never;
            path: {
                player_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlayerRecentFormView"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getFixturePredictions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                match_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FixturePrediction"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getPlayerPredictions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                player_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlayerFixturePrediction"][];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    getSystemStatus: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemStatusView"];
                };
            };
        };
    };
    listTeams: {
        parameters: {
            query?: {
                search?: string | null;
                active?: boolean | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TeamPage"];
                };
            };

            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    ready: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {

            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadyResponse"];
                };
            };
        };
    };
}
